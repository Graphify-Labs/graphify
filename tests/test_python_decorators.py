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


def test_pytest_fixture_does_not_rewire_onto_local_fixture(tmp_path):
    # #2732: qualified pytest decorators must not resolve to same-named corpus
    # functions through the global decorator rewire, and no sourceless stub may
    # be fabricated for a pytest decorator tail.
    _write(tmp_path / "pkg" / "locals.py",
           "def fixture():\n"
           "    return \"local helper\"\n"
           "def parametrize():\n"
           "    return \"local parametrize\"\n")
    cases = (("db", "@pytest.fixture\n"),
             ("param", "@pytest.mark.parametrize(\"x\", [1, 2])\n"))
    for name, deco in cases:
        _write(tmp_path / "pkg" / f"case_{name}.py",
               "import pytest\n"
               "\n"
               f"{deco}"
               f"def {name}(x=None):\n"
               "    return x or {}\n")
    paths = [tmp_path / "pkg" / "locals.py"]
    paths += sorted(tmp_path.glob("pkg/case_*.py"))
    r = extract(paths, cache_root=tmp_path)
    for name, _ in cases:
        source_nid = _func_nid(f"pkg/case_{name}.py", name)
        for local in ("fixture", "parametrize"):
            assert _func_nid("pkg/locals.py", local) not in _deco_edges(
                r, source_nid), f"spurious decorator edge onto local {local}()"
    for tail in ("fixture", "parametrize"):
        assert not any(n["id"] == _make_id(tail) for n in r["nodes"]), f"stub {tail}()"


def test_corpus_owned_fixture_decorator_keeps_its_edge(tmp_path):
    # #2732 guard against the naive fix: corpus-owned bare `@fixture` decorators
    # must keep their edge — pytest suppression is by qualified path / import
    # scope, never by folding the tail name into the noise set.
    f = _write(tmp_path / "pkg" / "own.py",
               "def fixture(fn):\n"
               "    return fn\n"
               "\n"
               "@fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _func_nid("pkg/own.py", "fixture") in _deco_edges(
        r, _func_nid("pkg/own.py", "setup"))


def test_local_decorator_shadows_pytest_import(tmp_path):
    # A top-level `def fixture(fn)` rebinds the imported name: at the `@fixture`
    # site it is the corpus's own decorator, so the scan must not suppress it.
    f = _write(tmp_path / "pkg" / "own.py",
               "from pytest import fixture\n"
               "\n"
               "def fixture(fn):\n"
               "    return fn\n"
               "\n"
               "@fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _func_nid("pkg/own.py", "fixture") in _deco_edges(
        r, _func_nid("pkg/own.py", "setup"))


def test_pytest_alias_in_with_shadows_import(tmp_path):
    # A module-level `with ctx() as fixture` rebinds the imported name; the
    # binding persists after the block. (`except ... as` is not modelled.)
    f = _write(tmp_path / "pkg" / "with_alias.py",
               "from pytest import fixture\n"
               "\n"
               "def ctx():\n"
               "    pass\n"
               "with ctx() as fixture:\n"
               "    pass\n"
               "\n"
               "@fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("fixture") in _deco_edges(
        r, _func_nid("pkg/with_alias.py", "setup")), (
        "with-as rebinding must retain the decorator edge")


def test_pytest_import_is_valid_before_later_rebinding(tmp_path):
    # Binding resolution is source-ordered, not whole-file: `@fixture` before a
    # local `def fixture` is still pytest; after it, it is the local decorator.
    f = _write(tmp_path / "pkg" / "case.py",
               "from pytest import fixture\n"
               "\n"
               "@fixture\n"
               "def test_before():\n"
               "    pass\n"
               "\n"
               "def fixture(fn):\n"
               "    return fn\n"
               "\n"
               "@fixture\n"
               "def test_after():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert not _deco_edges(r, _func_nid("pkg/case.py", "test_before")), (
        "pre-rebinding @fixture must still be suppressed as pytest vocabulary")
    assert _func_nid("pkg/case.py", "fixture") in _deco_edges(
        r, _func_nid("pkg/case.py", "test_after")), (
        "post-rebinding @fixture must resolve to the local decorator")


def test_pytest_alias_shadowed_is_no_longer_suppressed(tmp_path):
    # Same ordering rule for module aliases: `pt` is pytest until it is rebound,
    # so the decorator before the rebinding is suppressed and the one after is not.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest as pt\n"
               "\n"
               "@pt.fixture\n"
               "def before():\n"
               "    pass\n"
               "\n"
               "pt = local_module\n"
               "\n"
               "@pt.fixture\n"
               "def after():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert not _deco_edges(r, _func_nid("pkg/case.py", "before")), (
        "pre-rebinding @pt.fixture must be suppressed as pytest vocabulary")
    assert _make_id("fixture") in _deco_edges(
        r, _func_nid("pkg/case.py", "after")), (
        "post-rebinding @pt.fixture must not be suppressed")


def test_pytest_from_import_alias_is_suppressed(tmp_path):
    # `from pytest import fixture as fx` binds the LOCAL name `fx`, which is what
    # the import-scope scan must record (not the imported symbol `fixture`).
    _write(tmp_path / "pkg" / "locals.py",
           "def fixture():\n"
           "    return \"local helper\"\n")
    f = _write(tmp_path / "pkg" / "case.py",
               "from pytest import fixture as fx\n"
               "\n"
               "@fx\n"
               "def db():\n"
               "    return {}\n")
    r = extract([tmp_path / "pkg" / "locals.py", f], cache_root=tmp_path)
    assert _func_nid("pkg/locals.py", "fixture") not in _deco_edges(
        r, _func_nid("pkg/case.py", "db")), (
        "spurious decorator edge onto local fixture()")


def test_pytest_import_aliased_is_suppressed(tmp_path):
    # `import pytest as pt` + `@pt.fixture` / `@pt.mark.parametrize` — the
    # module alias must be recognised so the decorators are treated as pytest
    # vocabulary rather than corpus code.
    _write(tmp_path / "pkg" / "locals.py",
           "def fixture():\n"
           "    return \"local helper\"\n"
           "def parametrize():\n"
           "    return \"local parametrize\"\n")
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest as pt\n"
               "\n"
               "@pt.fixture\n"
               "def db():\n"
               "    return {}\n"
               "\n"
               "@pt.mark.parametrize(\"x\", [1])\n"
               "def test_x(x):\n"
               "    pass\n")
    r = extract([tmp_path / "pkg" / "locals.py", f], cache_root=tmp_path)
    assert _func_nid("pkg/locals.py", "fixture") not in _deco_edges(
        r, _func_nid("pkg/case.py", "db")), (
        "spurious decorator edge onto local fixture()")
    assert _func_nid("pkg/locals.py", "parametrize") not in _deco_edges(
        r, _func_nid("pkg/case.py", "test_x")), (
        "spurious decorator edge onto local parametrize()")
    assert not any(n["id"] == _make_id("fixture") for n in r["nodes"])


def test_pytest_self_decorated_fixture_is_suppressed(tmp_path):
    # The decorator expression is evaluated before the wrapped name is bound, so
    # `@fixture def fixture()` still decorates pytest's fixture (source order).
    f = _write(tmp_path / "pkg" / "case.py",
               "from pytest import fixture\n"
               "\n"
               "@fixture\n"
               "def fixture():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert not _deco_edges(r, _func_nid("pkg/case.py", "fixture")), (
        "self-decorated @fixture must be suppressed as pytest vocabulary")


def test_pytest_decorator_on_class_method_is_suppressed(tmp_path):
    # Class-body decorators still match the module-level import; no sourceless
    # `fixture` stub may be fabricated for corpus rewiring.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest\n"
               "\n"
               "class Tests:\n"
               "    @pytest.fixture\n"
               "    def db(self):\n"
               "        pass\n")
    r = extract([f], cache_root=tmp_path)
    assert not _deco_edges(r, _method_nid("pkg/case.py", "Tests", "db")), (
        "class-method @pytest.fixture must be suppressed as pytest vocabulary")


def test_pytest_decorator_on_nested_function_is_suppressed(tmp_path):
    # The binding scan does not descend into function bodies, but the qualified
    # path `pytest.fixture` matches the module-level import directly.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest\n"
               "\n"
               "def make_test():\n"
               "    @pytest.fixture\n"
               "    def fixture():\n"
               "        pass\n"
               "    return fixture\n")
    r = extract([f], cache_root=tmp_path)
    assert not _deco_edges(r, _func_nid("pkg/case.py", "fixture")), (
        "nested @pytest.fixture must be suppressed as pytest vocabulary")


def test_pytest_module_alias_shadowed_by_for_target(tmp_path):
    # Same scope model as `_python_module_bound_names`: `for pytest in ...`
    # rebinds the module name, so the later decorator keeps its edge.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest\n"
               "\n"
               "for pytest in [1, 2]:\n"
               "    pass\n"
               "\n"
               "@pytest.fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("fixture") in _deco_edges(
        r, _func_nid("pkg/case.py", "setup")), (
        "for-target rebinding must unsuppress the decorator")


def test_pytest_module_alias_shadowed_by_walrus(tmp_path):
    # Same for the walrus operator: `(pytest := ...)` rebinds the module name
    # before the decorator, so the decorator edge is retained.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest\n"
               "\n"
               "(pytest := local_module)\n"
               "\n"
               "@pytest.fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("fixture") in _deco_edges(
        r, _func_nid("pkg/case.py", "setup")), (
        "walrus rebinding must unsuppress the decorator")


def test_stacked_pytest_and_custom_decorators(tmp_path):
    # Suppression is per-decorator-node: the custom decorator edge must survive
    # on either side of a suppressed @pytest.fixture.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest\n"
               "\n"
               "def custom(fn):\n"
               "    return fn\n"
               "\n"
               "@custom\n"
               "@pytest.fixture\n"
               "def a():\n"
               "    pass\n"
               "\n"
               "@pytest.fixture\n"
               "@custom\n"
               "def b():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    for func in ("a", "b"):
        edges = _deco_edges(r, _func_nid("pkg/case.py", func))
        assert _func_nid("pkg/case.py", "custom") in edges, (
            f"custom decorator on {func} must keep its edge")
        assert "fixture" not in edges, (
            f"pytest decorator on {func} must be suppressed")


def test_unbound_pytest_qualified_decorator_keeps_edge(tmp_path):
    # #2732 boundary: suppression needs binding evidence — an unimported
    # `@pytest.fixture` where `pytest` is the corpus's own function keeps its edge.
    f = _write(tmp_path / "pkg" / "case.py",
               "def pytest():\n"
               "    return object()\n"
               "\n"
               "@pytest.fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("fixture") in _deco_edges(
        r, _func_nid("pkg/case.py", "setup")), (
        "unimported @pytest.fixture must not be assumed to be pytest")


def test_pytest_mark_import_with_local_parametrize(tmp_path):
    # Root-name resolution governs: `mark` is bound from pytest, so `@mark.parametrize`
    # is suppressed even when the corpus defines its own `parametrize`.
    f = _write(tmp_path / "pkg" / "case.py",
               "from pytest import mark\n"
               "\n"
               "def parametrize():\n"
               "    return 1\n"
               "\n"
               "@mark.parametrize(\"x\", [1, 2])\n"
               "def test_x(x):\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert not _deco_edges(r, _func_nid("pkg/case.py", "test_x")), (
        "@mark.parametrize must be suppressed as pytest vocabulary")


def test_pytest_unbound_by_del_keeps_edge(tmp_path):
    # `del pytest` removes the module binding, so a later @pytest.fixture is the
    # corpus's own reference and keeps its decorator edge.
    f = _write(tmp_path / "pkg" / "case.py",
               "import pytest\n"
               "\n"
               "del pytest\n"
               "\n"
               "@pytest.fixture\n"
               "def setup():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _make_id("fixture") in _deco_edges(
        r, _func_nid("pkg/case.py", "setup")), (
        "del rebinding must unsuppress the decorator")


def test_undecorated_function_emits_no_decorator_edge(tmp_path):
    f = _write(tmp_path / "pkg" / "plain.py",
               "def plain():\n"
               "    pass\n")
    r = extract([f], cache_root=tmp_path)
    assert _deco_edges(r, _func_nid("pkg/plain.py", "plain")) == set()
