"""Python `self.m()` / `cls.m()` / `super().m()` where `m` is defined on a base class in
another file.

The in-file pass (`_self_call_target`) already walks base classes declared in the same
file. A base imported from another module was invisible to it, so `Flask.__init__ ->
App.__init__` (flask/app.py -> flask/sansio/app.py) and every other inherited call
across modules had no `calls` edge.

`_resolve_python_member_calls` now walks the caller's class up a single-inheritance chain
across files and binds the first class that owns `m`. It stops, with no edge, at a class
with two or more bases (MRO order across files is not modelled), a base the edge list
cannot show (`mod.Base`, `Generic[T]`), a base outside the corpus, a base the class's
file neither defines nor imports, and `super(Cls, obj)` with arguments.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from graphify.extract import extract

_BASE = "class Base:\n    def m(self):\n        return 1\n"


def _write(root: Path, files: dict[str, str]) -> list[Path]:
    files = {"pkg/__init__.py": "", **{f"pkg/{n}": b for n, b in files.items()}}
    paths = []
    for name, body in files.items():
        p = root / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    return paths


def _calls(tmp_path, files: dict[str, str]):
    r = extract(_write(tmp_path, files), cache_root=tmp_path / "graphify-out", parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    edges = [e for e in r["edges"] if e["relation"] == "calls"]
    return nodes, edges


def _hits(nodes, edges, caller: str, callee: str = ".m()") -> list[str]:
    """Stems of the files whose `callee` the method `caller` calls."""
    return sorted(
        Path(nodes[e["target"]]["source_file"]).stem
        for e in edges
        if nodes[e["source"]]["label"] == f".{caller}()" and nodes[e["target"]]["label"] == callee
    )


def test_self_call_reaches_a_base_method_in_another_file(tmp_path):
    nodes, edges = _calls(tmp_path, {
        "base.py": _BASE,
        "use.py": "from .base import Base\n\nclass C(Base):\n    def run(self):\n        return self.m()\n",
    })
    assert _hits(nodes, edges, "run") == ["base"]
    edge = next(e for e in edges if nodes[e["source"]]["label"] == ".run()")
    assert edge["confidence"] == "EXTRACTED"  # same rule as the in-file base walk


def test_super_and_cls_calls_reach_the_base(tmp_path):
    nodes, edges = _calls(tmp_path, {
        "base.py": _BASE + "    @classmethod\n    def build(cls):\n        return cls()\n",
        "use.py": (
            "from .base import Base\n\nclass C(Base):\n"
            "    def m(self):\n        return super().m()\n"
            "    @classmethod\n    def make(cls):\n        return cls.build()\n"
        ),
    })
    assert _hits(nodes, edges, "m") == ["base"]
    assert _hits(nodes, edges, "make", ".build()") == ["base"]


def test_the_nearest_definition_wins_across_two_levels(tmp_path):
    nodes, edges = _calls(tmp_path, {
        "a.py": _BASE + "    def n(self):\n        return 2\n",
        "b.py": "from .a import Base\n\nclass Mid(Base):\n    def m(self):\n        return 3\n",
        "use.py": (
            "from .b import Mid\n\nclass C(Mid):\n"
            "    def run(self):\n        return self.m()\n"
            "    def other(self):\n        return self.n()\n"
        ),
    })
    assert _hits(nodes, edges, "run") == ["b"]  # Mid.m overrides Base.m
    assert _hits(nodes, edges, "other", ".n()") == ["a"]  # through Mid, which has no n


def test_chains_the_walk_cannot_order_emit_no_edge(tmp_path):
    nodes, edges = _calls(tmp_path, {
        "base.py": _BASE,
        "other.py": "class Other:\n    def m(self):\n        return 2\n",
        "use.py": (
            "import lib\nfrom typing import Generic, TypeVar\n"
            "from .base import Base\nfrom .other import Other\nT = TypeVar('T')\n\n"
            "class TwoBases(Base, Other):\n    def run(self):\n        return self.m()\n\n"
            "class Opaque(lib.Thing, Base):\n    def run(self):\n        return self.m()\n\n"
            "class Generic_(Base, Generic[T]):\n    def run(self):\n        return self.m()\n\n"
            "class SuperArgs(Base):\n    def m(self):\n        return super(Base, self).m()\n\n"
            "class Missing(Base):\n    def run(self):\n        return self.zzz()\n\n"
            "class Nested(Base):\n    def run(self):\n        def inner():\n            return self.m()\n"
            "        return inner\n"
        ),
    })
    calls_into = {(nodes[e["source"]]["label"], Path(nodes[e["target"]]["source_file"]).stem)
                  for e in edges if nodes[e["target"]]["label"] in (".m()", ".zzz()")}
    assert not {c for c in calls_into if c[1] in ("base", "other")}, calls_into


def test_a_base_from_outside_or_not_imported_emits_no_edge(tmp_path):
    nodes, edges = _calls(tmp_path, {
        "base.py": _BASE,
        "external.py": "from lib import Base\n\nclass C(Base):\n    def run(self):\n        return self.m()\n",
        "unimported.py": "class D(Base):\n    def run(self):\n        return self.m()\n",
    })
    assert _hits(nodes, edges, "run") == []


def _rebuild_calls(root: Path) -> set[tuple[str, str]]:
    g = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    return {(e["source"], e["target"]) for e in g.get("links", g.get("edges", [])) if e["relation"] == "calls"}


_CHAIN = {
    "base.py": _BASE,
    "mid.py": "import lib\nfrom .base import Base\n\nclass Mid(lib.Thing, Base):\n    pass\n",
    "child.py": "from .base import Base\n\nclass Child(Base):\n    def run(self):\n        return self.m()\n",
    "grand.py": "from .mid import Mid\n\nclass Grand(Mid):\n    def run(self):\n        return self.m()\n",
    # Two hops through a class in an unchanged file: Deep -> Plain -> Base.
    "plain.py": "from .base import Base\n\nclass Plain(Base):\n    pass\n",
    "deep.py": "from .plain import Plain\n\nclass Deep(Plain):\n    def run(self):\n        return self.m()\n",
}
_CHANGED = ("child.py", "grand.py", "deep.py")


def test_changed_files_rebuild_matches_a_full_build(tmp_path):
    """The changed file's base sits in an unchanged file (a name stub in that batch),
    and an unchanged class's opaque base must still stop the walk."""
    from graphify.watch import _rebuild_code

    inc, full = tmp_path / "inc", tmp_path / "full"
    for root in (inc, full):
        _write(root, _CHAIN)
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    for root in (inc, full):
        for name in _CHANGED:
            p = root / "pkg" / name
            p.write_text(p.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    assert _rebuild_code(
        inc, changed_paths=[inc / "pkg" / name for name in _CHANGED],
        no_cluster=True, acquire_lock=False,
    )
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)
    assert _rebuild_calls(inc) == _rebuild_calls(full)
    assert ("pkg_child_child_run", "pkg_base_base_m") in _rebuild_calls(full)
    assert ("pkg_deep_deep_run", "pkg_base_base_m") in _rebuild_calls(full)
    assert not any(t == "pkg_base_base_m" and s.startswith("pkg_grand") for s, t in _rebuild_calls(full))


def test_incremental_extract_matches_a_full_extract(tmp_path):
    env = dict(os.environ, PYTHONHASHSEED="0")
    inc, full = tmp_path / "inc", tmp_path / "full"
    for root in (inc, full):
        _write(root, _CHAIN)

    def run(root: Path) -> None:
        r = subprocess.run([sys.executable, "-m", "graphify", "extract", str(root), "--code-only", "--no-cluster"],
                           cwd=root, env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr[-2000:]

    run(inc)
    for root in (inc, full):
        for name in _CHANGED:
            p = root / "pkg" / name
            p.write_text(p.read_text(encoding="utf-8") + "\n# touched\n", encoding="utf-8")
    run(inc)
    run(full)
    assert _rebuild_calls(inc) == _rebuild_calls(full)
    assert ("pkg_child_child_run", "pkg_base_base_m") in _rebuild_calls(full)
    assert ("pkg_deep_deep_run", "pkg_base_base_m") in _rebuild_calls(full)
    assert not any(t == "pkg_base_base_m" and s.startswith("pkg_grand") for s, t in _rebuild_calls(full))


def test_schema_bump_retires_entries_cached_without_the_opaque_base_marker(tmp_path, monkeypatch):
    """An entry from schema 6 has no `python_opaque_bases` marker; replaying it would
    walk through `Mid(lib.Thing, Base)` and bind `Grand.run -> Base.m`."""
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import extract_python

    paths = _write(tmp_path, _CHAIN)
    current_schema = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 6)  # last schema without the marker
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_python(p)
        for node in stale["nodes"]:
            (node.get("metadata") or {}).pop("python_opaque_bases", None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")

    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current_schema)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    assert not [e for e in r["edges"] if e["relation"] == "calls"
                and nodes[e["source"]]["label"] == ".run()" and nodes[e["source"]]["source_file"].endswith("grand.py")
                and nodes[e["target"]]["label"] == ".m()"]
