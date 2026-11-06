"""Python member calls on a receiver whose class is known from the function itself.

Before this, `obj.method()` produced a `calls` edge only for `self`/`cls` receivers and
module aliases, so `affected Client.send` missed every caller that wrote

  A. `def f(client: Client): client.send()`        (annotated parameter, incl. Optional/str/`| None`)
  B. `client = Client(); client.send()`            (local bound from a constructor call)
  C. `with Client() as client: client.send()`      (context manager on a constructor call)

The receiver's class is used only when the binding is unambiguous inside the function
(one class, never rebound to something else) and the class is unique by name and visible
from the caller's file (same file or imported), mirroring the TS receiver gate (#2553).
Everything else emits no edge rather than a guess.
"""
from __future__ import annotations

from graphify.extract import extract

_CLIENT = "class Client:\n    def send(self):\n        return 1\n"
_CACHE = "class Cache:\n    def send(self):\n        return 2\n"


def _calls(tmp_path, files: dict[str, str]):
    # A real package, so `from .client import Client` binds to the class node.
    files = {"pkg/__init__.py": "", **{f"pkg/{n}": b for n, b in files.items()}}
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files],
                cache_root=tmp_path / "graphify-out", parallel=False)
    lbl = {n["id"]: n["label"] for n in r["nodes"]}
    edges = [e for e in r["edges"] if e["relation"] == "calls"]
    return {(lbl.get(e["source"]), lbl.get(e["target"])) for e in edges}, edges, r


def _has(calls, caller, callee=".send()"):
    return any(s == f"{caller}()" and t == callee for s, t in calls)


def test_annotated_parameter_receiver(tmp_path):
    calls, edges, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "use.py": "from .client import Client\n\ndef run(c: Client):\n    return c.send()\n",
    })
    assert _has(calls, "run")
    edge = next(e for e in edges if e["source"].endswith("_run"))
    assert edge["confidence"] == "INFERRED"
    assert edge["confidence_score"] == 0.85


def test_optional_string_and_union_annotations(tmp_path):
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "use.py": (
            "from typing import Optional\nfrom .client import Client\n\n"
            "def opt(c: Optional[Client]):\n    return c.send()\n\n"
            "def fwd(c: 'Client'):\n    return c.send()\n\n"
            "def union(c: Client | None = None):\n    return c.send()\n"
        ),
    })
    assert _has(calls, "opt") and _has(calls, "fwd") and _has(calls, "union")


def test_local_constructor_and_with_binding(tmp_path):
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "use.py": (
            "from .client import Client\n\n"
            "def local():\n    c = Client()\n    return c.send()\n\n"
            "def ctx():\n    with Client() as c:\n        return c.send()\n"
        ),
    })
    assert _has(calls, "local") and _has(calls, "ctx")


def test_module_qualified_typing_wrapper(tmp_path):
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "use.py": ("import typing\nfrom .client import Client\n\n"
                   "def run(c: typing.Optional[Client]):\n    return c.send()\n"),
    })
    assert _has(calls, "run")


def test_same_method_name_resolves_to_annotated_class(tmp_path):
    _, edges, r = _calls(tmp_path, {
        "client.py": _CLIENT,
        "cache.py": _CACHE,
        "use.py": "from .client import Client\n\ndef run(c: Client):\n    return c.send()\n",
    })
    files = {n["id"]: str(n.get("source_file", "")) for n in r["nodes"]}
    targets = [files[e["target"]] for e in edges if e["source"].endswith("_run")]
    assert targets and all(t.endswith("client.py") for t in targets)


def test_unknown_or_ambiguous_receivers_emit_no_edge(tmp_path):
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "cache.py": _CACHE,
        "use.py": (
            "from .client import Client\nfrom .cache import Cache\n\n"
            "def untyped(c):\n    return c.send()\n\n"
            "def rebound(c: Client):\n    c = Cache()\n    return c.send()\n\n"
            "def from_func():\n    c = make()\n    return c.send()\n\n"
            "def container(cs: list[Client]):\n    return cs.send()\n\n"
            "def loop(cs):\n    for c in cs:\n        c.send()\n\n"
            "def caught():\n    try:\n        pass\n    except Exception as c:\n        c.send()\n"
        ),
    })
    for caller in ("untyped", "rebound", "from_func", "container", "loop", "caught"):
        assert not _has(calls, caller), caller


def test_rebinding_in_an_inner_scope_emits_no_edge(tmp_path):
    # Calls inside a lambda or a nested class body belong to the enclosing function,
    # so a name those scopes (or match/import/nonlocal) bind must lose its type.
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "cache.py": _CACHE,
        "use.py": (
            "from .client import Client\nfrom .cache import Cache\n\n"
            "def lam(c: Client):\n    return lambda c: c.send()\n\n"
            "def klass(c: Client):\n    class K:\n        c = Cache()\n        c.send()\n    return K\n\n"
            "def matched(c: Client, v):\n    match v:\n        case c:\n            return c.send()\n\n"
            "def imported(c: Client):\n    import c\n    return c.send()\n\n"
            "def nonloc(c: Client):\n    def inner():\n        nonlocal c\n        c = Cache()\n"
            "    inner()\n    return c.send()\n\n"
            "def unpacked(c: Client):\n    with Cache() as (c, d):\n        return c.send()\n\n"
            "def star(*c: Client):\n    return c.send()\n\n"
            "def other_lambda(c: Client):\n    f = lambda x: x\n    return c.send()\n"
        ),
    })
    for caller in ("lam", "klass", "matched", "imported", "nonloc", "unpacked", "star"):
        assert not _has(calls, caller), caller
    assert _has(calls, "other_lambda")


def test_class_not_visible_from_caller_emits_no_edge(tmp_path):
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "use.py": "def run(c: 'Client'):\n    return c.send()\n",
    })
    assert not _has(calls, "run")


def test_nested_functions_and_nested_class_methods_reach_the_file(tmp_path):
    # A nested def's `contains` parent is its enclosing function, and a nested
    # class's is its outer class: the visibility check must climb to the file.
    calls, _, _ = _calls(tmp_path, {
        "client.py": _CLIENT,
        "use.py": (
            "from .client import Client\n\n"
            "def outer():\n    def inner(c: Client):\n        return c.send()\n    return inner\n\n"
            "class K:\n    def run(self):\n        def callback(c: Client):\n            return c.send()\n"
            "        return callback\n\n"
            "def a():\n    def b():\n        def deep():\n            c = Client()\n            return c.send()\n"
            "        return deep\n    return b\n\n"
            "class Outer:\n    class Inner:\n        def go(self, c: Client):\n            return c.send()\n\n"
            "def hidden():\n    def nope(c: 'Unknown'):\n        return c.send()\n    return nope\n"
        ),
    })
    for caller in ("inner", "callback", "deep", ".go"):  # methods are labeled .name()
        assert _has(calls, caller), caller
    assert not _has(calls, "nope")


def test_duplicate_class_name_emits_no_edge(tmp_path):
    calls, _, _ = _calls(tmp_path, {
        "a/__init__.py": "",
        "a/client.py": _CLIENT,
        "b/__init__.py": "",
        "b/client.py": _CLIENT,
        "use.py": "from .a.client import Client\n\ndef run(c: Client):\n    return c.send()\n",
    })
    assert not _has(calls, "run")


def test_warm_cache_matches_cold(tmp_path):
    files = {
        "client.py": _CLIENT,
        "use.py": "from .client import Client\n\ndef run(c: Client):\n    return c.send()\n",
    }
    _, cold, _ = _calls(tmp_path, files)
    _, warm, _ = _calls(tmp_path, files)
    key = lambda e: (e["source"], e["target"], e["confidence"])  # noqa: E731
    assert sorted(map(key, cold)) == sorted(map(key, warm))
    assert any(e["source"].endswith("_run") for e in warm)
