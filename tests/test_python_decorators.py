"""Regression tests: Python decorator references (#2154).

Applying a Python decorator emitted no edge to the decorator symbol, so
`affected <decorator>` answered "No affected nodes found" for every function it
wraps — a silent false negative on reverse-impact queries.

TS/JS already emitted these edges (`_ts_emit_decorator_edges`); the Python
`decorated_definition` branch walked its children only to propagate the parent
class id (#1050) and never looked at the `decorator` children. Python now emits
the same shape: `references` edges with context="decorator" from the decorated
function/class to the decorator symbol, resolved through the same
sourceless-stub path as type references so an imported decorator collapses onto
its real definition.
"""
from pathlib import Path

from graphify.extract import _file_stem, _make_id, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _stem(file: str) -> str:
    return _file_stem(Path(file))


def _func_nid(file: str, func: str) -> str:
    return _make_id(_stem(file), func)


def _class_nid(file: str, cls: str) -> str:
    return _make_id(_stem(file), cls)


def _method_nid(file: str, cls: str, method: str) -> str:
    return _make_id(_class_nid(file, cls), method)


def _deco_edges(result: dict, owner_nid: str) -> set[str]:
    """Decorator-reference edge targets emitted from owner_nid."""
    return {
        e["target"]
        for e in result["edges"]
        if e["source"] == owner_nid
        and e["relation"] == "references"
        and e.get("context") == "decorator"
    }


def test_module_level_function_decorator(tmp_path):
    # The issue repro: decorator imported from another module, applied to a
    # module-level function. Target is the sourceless stub the rewire collapses.
    f = _write(tmp_path / "pkg" / "consumer.py",
               "from deco import my_decorator\n"
               "\n"
               "@my_decorator\n"
               "def business_logic():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("my_decorator") in _deco_edges(
        r, _func_nid("pkg/consumer.py", "business_logic"))


def test_same_file_decorator_resolves_to_local_definition(tmp_path):
    # Decorator defined above its use in the same file: the edge must point at
    # the real local node, not a stub.
    f = _write(tmp_path / "pkg" / "local.py",
               "def my_decorator(fn):\n"
               "    return fn\n"
               "\n"
               "@my_decorator\n"
               "def business_logic():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _func_nid("pkg/local.py", "my_decorator") in _deco_edges(
        r, _func_nid("pkg/local.py", "business_logic"))


def test_decorator_with_arguments(tmp_path):
    # `@deco(arg)` is a `call` node; the head symbol is its `function` field.
    f = _write(tmp_path / "pkg" / "args.py",
               "from deco import retry\n"
               "\n"
               "@retry(times=3)\n"
               "def flaky():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("retry") in _deco_edges(r, _func_nid("pkg/args.py", "flaky"))


def test_attribute_decorator_targets_the_symbol_not_the_module(tmp_path):
    # `@app.route("/")` is an `attribute` under a `call`; the target is `route`,
    # matching _ts_decorator_name's member_expression handling.
    f = _write(tmp_path / "pkg" / "web.py",
               "import app\n"
               "\n"
               "@app.route(\"/\")\n"
               "def index():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    targets = _deco_edges(r, _func_nid("pkg/web.py", "index"))
    assert _make_id("route") in targets
    assert _make_id("app") not in targets


def test_stacked_decorators_all_emit(tmp_path):
    f = _write(tmp_path / "pkg" / "stack.py",
               "from deco import a, b, c\n"
               "\n"
               "@a\n"
               "@b\n"
               "@c\n"
               "def target():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    targets = _deco_edges(r, _func_nid("pkg/stack.py", "target"))
    assert {_make_id("a"), _make_id("b"), _make_id("c")} <= targets


def test_decorated_method_owner_is_class_qualified(tmp_path):
    # Guards the #1050 interaction: the owner must be the class-qualified method
    # id, not a bare module-level id.
    f = _write(tmp_path / "pkg" / "svc.py",
               "from deco import traced\n"
               "\n"
               "class Service:\n"
               "    @traced\n"
               "    def handle(self):\n"
               "        pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("traced") in _deco_edges(
        r, _method_nid("pkg/svc.py", "Service", "handle"))


def test_property_still_class_qualified(tmp_path):
    # #1050 regression guard: @property/@staticmethod must not change the
    # method node's class-qualified id.
    f = _write(tmp_path / "pkg" / "prop.py",
               "class Config:\n"
               "    @property\n"
               "    def name(self):\n"
               "        return 1\n")
    r = extract([f], cache_root=tmp_path)
    assert any(n["id"] == _method_nid("pkg/prop.py", "Config", "name")
               for n in r["nodes"])


def test_decorated_class(tmp_path):
    f = _write(tmp_path / "pkg" / "model.py",
               "from registry import register_model\n"
               "\n"
               "@register_model\n"
               "class Point:\n"
               "    x: int\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("register_model") in _deco_edges(
        r, _class_nid("pkg/model.py", "Point"))


def test_stdlib_class_decorator_emits_no_edge(tmp_path):
    # @dataclass is ambient stdlib vocabulary (_PYTHON_DECORATOR_NOISE): no
    # decorator edge and no sourceless `dataclass` stub node.
    f = _write(tmp_path / "pkg" / "dc.py",
               "from dataclasses import dataclass\n"
               "\n"
               "@dataclass\n"
               "class Point:\n"
               "    x: int\n")
    r = extract([f], cache_root=tmp_path)
    assert _deco_edges(r, _class_nid("pkg/dc.py", "Point")) == set()
    assert not any(n["id"] == _make_id("dataclass") for n in r["nodes"])


def test_builtin_method_decorators_emit_no_edge_or_stub(tmp_path):
    # @property / @staticmethod must not fabricate stub nodes or decorator
    # edges — they would appear on nearly every class-heavy file.
    f = _write(tmp_path / "pkg" / "builtins.py",
               "class Config:\n"
               "    @property\n"
               "    def name(self):\n"
               "        return 1\n"
               "\n"
               "    @staticmethod\n"
               "    def make():\n"
               "        return Config()\n")
    r = extract([f], cache_root=tmp_path)
    assert _deco_edges(r, _method_nid("pkg/builtins.py", "Config", "name")) == set()
    assert _deco_edges(r, _method_nid("pkg/builtins.py", "Config", "make")) == set()
    node_ids = {n["id"] for n in r["nodes"]}
    assert _make_id("property") not in node_ids
    assert _make_id("staticmethod") not in node_ids


def test_functools_wraps_does_not_rewire_onto_local_wraps(tmp_path):
    # The demonstrated false positive: a corpus defining its own top-level
    # `def wraps(...)` while another file uses `@functools.wraps` got a false
    # decorator edge onto the local `wraps` via the unique-function rewire.
    _write(tmp_path / "pkg" / "gift.py",
           "def wraps(thing):\n"
           "    return thing\n")
    f = _write(tmp_path / "pkg" / "util.py",
               "import functools\n"
               "\n"
               "def logged(fn):\n"
               "    @functools.wraps(fn)\n"
               "    def inner(*args, **kwargs):\n"
               "        return fn(*args, **kwargs)\n"
               "    return inner\n")
    r = extract([tmp_path / "pkg" / "gift.py", f], cache_root=tmp_path)
    local_wraps = _func_nid("pkg/gift.py", "wraps")
    assert not any(
        e["target"] == local_wraps
        and e["relation"] == "references"
        and e.get("context") == "decorator"
        for e in r["edges"]
    )


def test_undecorated_function_emits_no_decorator_edge(tmp_path):
    f = _write(tmp_path / "pkg" / "plain.py",
               "def plain():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _deco_edges(r, _func_nid("pkg/plain.py", "plain")) == set()


def test_attribute_decorator_local_receiver_targets_class_method(tmp_path):
    # `app = _App()` then `@app.get(...)`: the receiver is a locally-
    # instantiated local class, so the edge must land on `_App.get`, not a
    # bare "get" stub free to collide with an unrelated same-named def
    # elsewhere in the corpus (#2315).
    routes = _write(tmp_path / "pkg" / "routes.py",
                     "class _App:\n"
                     "    def get(self, path):\n"
                     "        pass\n"
                     "\n"
                     "app = _App()\n"
                     "\n"
                     "@app.get(\"/health\")\n"
                     "def health():\n"
                     "    pass\n"
                     "\n"
                     "@app.get(\"/status\")\n"
                     "def status():\n"
                     "    pass\n")
    unrelated = _write(tmp_path / "pkg" / "settings_store.py",
                        "def get(key):\n"
                        "    pass\n")
    r = extract([routes, unrelated], cache_root=tmp_path)
    unrelated_nid = _func_nid("pkg/settings_store.py", "get")
    method_nid = _method_nid("pkg/routes.py", "_App", "get")
    # The edge must land on a node that actually exists, not a dangling id.
    assert method_nid in {n["id"] for n in r["nodes"]}
    for func in ("health", "status"):
        targets = _deco_edges(r, _func_nid("pkg/routes.py", func))
        assert unrelated_nid not in targets
        assert method_nid in targets


def test_attribute_decorator_local_receiver_same_file_unrelated_def(tmp_path):
    # Same collision shape, but the unrelated `def get` lives in the SAME
    # file as the decorated function, at the same (module) scope, which the
    # scoped-id fast path in ensure_named_node would otherwise match directly.
    f = _write(tmp_path / "pkg" / "mixed.py",
               "class _App:\n"
               "    def get(self, path):\n"
               "        pass\n"
               "\n"
               "app = _App()\n"
               "\n"
               "def get(key):\n"
               "    pass\n"
               "\n"
               "@app.get(\"/health\")\n"
               "def health():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    unrelated_nid = _func_nid("pkg/mixed.py", "get")
    method_nid = _method_nid("pkg/mixed.py", "_App", "get")
    # The edge must land on a node that actually exists, not a dangling id.
    assert method_nid in {n["id"] for n in r["nodes"]}
    targets = _deco_edges(r, _func_nid("pkg/mixed.py", "health"))
    assert unrelated_nid not in targets
    assert method_nid in targets


def test_bare_decorator_still_emits_edge(tmp_path):
    # Regression guard for #2154: a plain identifier decorator is unaffected
    # by the attribute-receiver handling added for #2315.
    f = _write(tmp_path / "pkg" / "bare.py",
               "def my_decorator(fn):\n"
               "    return fn\n"
               "\n"
               "@my_decorator\n"
               "def business_logic():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _func_nid("pkg/bare.py", "my_decorator") in _deco_edges(
        r, _func_nid("pkg/bare.py", "business_logic"))


def test_deep_attribute_decorator_does_not_bind_unrelated_def(tmp_path):
    # `@a.b.c(...)`: the receiver is a compound attribute chain, not a plain
    # identifier, so it can't be resolved to a local class either. It must not
    # bind to an unrelated module-level `def c` elsewhere in the corpus.
    deep = _write(tmp_path / "pkg" / "deep.py",
                  "import a\n"
                  "\n"
                  "@a.b.c(\"/x\")\n"
                  "def handler():\n"
                  "    pass\n")
    unrelated = _write(tmp_path / "pkg" / "other.py",
                        "def c():\n"
                        "    pass\n")
    r = extract([deep, unrelated], cache_root=tmp_path)
    unrelated_nid = _func_nid("pkg/other.py", "c")
    targets = _deco_edges(r, _func_nid("pkg/deep.py", "handler"))
    assert unrelated_nid not in targets
