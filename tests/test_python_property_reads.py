"""Reading a `@property` runs its getter, so the read is a call of it.

`response.text` names no call, but runs `Response.text` when that is a property. Reads whose receiver
is typed the way a member call would be (`self`, a typed local or parameter, a `self.X` field bound to
one class) get a `references` edge with `context: property_read`, and only when the target is a property
spelled exactly like the read.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract

_RESPONSE = (
    "class Response:\n"
    "    def __init__(self):\n"
    "        self.count = 0\n"
    "        self._items = []\n"
    "\n"
    "    @property\n"
    "    def text(self):\n"
    "        return ''\n"
    "\n"
    "    @property\n"
    "    def items(self):\n"
    "        return self._items\n"
    "\n"
    "    def handle(self):\n"
    "        return self.text\n"
)


def _edges(tmp_path: Path, files: dict[str, str]):
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    r = extract(paths, root=tmp_path, cache_root=tmp_path / "graphify-out", parallel=False)
    nodes = {n["id"]: n for n in r["nodes"]}
    owner = {e["target"]: nodes[e["source"]]["label"] for e in r["edges"] if e["relation"] == "method"}
    return {(nodes[e["source"]]["label"], owner.get(e["target"], ""), nodes[e["target"]]["label"], e.get("context"))
            for e in r["edges"] if e["relation"] in ("calls", "references")}


def test_self_property_read_in_its_own_class(tmp_path: Path):
    edges = _edges(tmp_path, {"resp.py": _RESPONSE})
    assert (".handle()", "Response", ".text()", "property_read") in edges


def test_typed_local_and_parameter_reads_across_files(tmp_path: Path):
    edges = _edges(tmp_path, {
        "resp.py": _RESPONSE,
        "use.py": ("from resp import Response\n\n\n"
                   "def fetch():\n    r = Response()\n    return r.text\n\n\n"
                   "def show(r: Response):\n    return r.items\n"),
    })
    assert ("fetch()", "Response", ".text()", "property_read") in edges
    assert ("show()", "Response", ".items()", "property_read") in edges


def test_self_field_typed_receiver(tmp_path: Path):
    edges = _edges(tmp_path, {
        "resp.py": _RESPONSE,
        "client.py": ("from resp import Response\n\n\nclass Client:\n"
                      "    def __init__(self):\n        self.last = Response()\n\n"
                      "    def body(self):\n        return self.last.text\n"),
    })
    assert (".body()", "Response", ".text()", "property_read") in edges


def test_fields_method_references_and_stores_are_not_reads(tmp_path: Path):
    edges = _edges(tmp_path, {
        "resp.py": _RESPONSE,
        "use.py": ("from resp import Response\n\n\n"
                   "def poke():\n    r = Response()\n    r.count\n    cb = r.handle\n    r.text = 'x'\n    return cb\n"),
    })
    assert not any(e[0] == "poke()" and e[3] == "property_read" for e in edges), edges


def test_augmented_assignment_reads_the_property(tmp_path: Path):
    # `r.text += x` runs the getter before the setter.
    edges = _edges(tmp_path, {
        "resp.py": _RESPONSE,
        "use.py": "from resp import Response\n\n\ndef extend():\n    r = Response()\n    r.text += 'x'\n",
    })
    assert ("extend()", "Response", ".text()", "property_read") in edges


def test_underscored_field_does_not_reach_the_property_without_underscore(tmp_path: Path):
    # `_items` and `items` fold to one key in the resolver; the read names `_items`.
    edges = _edges(tmp_path, {
        "resp.py": _RESPONSE,
        "use.py": "from resp import Response\n\n\ndef raw():\n    r = Response()\n    return r._items\n",
    })
    assert not any(e[0] == "raw()" and e[3] == "property_read" for e in edges), edges


def test_property_inherited_from_a_base_in_another_file(tmp_path: Path):
    edges = _edges(tmp_path, {
        "base.py": "class Base:\n    @property\n    def name(self):\n        return 'b'\n",
        "child.py": "from base import Base\n\n\nclass Child(Base):\n    def greet(self):\n        return self.name\n",
    })
    assert (".greet()", "Base", ".name()", "property_read") in edges


def test_changed_files_rebuild_keeps_the_read_of_an_unchanged_property(tmp_path: Path):
    from graphify.watch import _rebuild_code

    files = {
        "resp.py": _RESPONSE,
        "use.py": "from resp import Response\n\n\ndef fetch():\n    r = Response()\n    return r.text\n",
    }
    roots = []
    for name in ("inc", "full"):
        root = tmp_path / name
        root.mkdir()
        for fname, body in files.items():
            (root / fname).write_text(body, encoding="utf-8")
        roots.append(root)
    inc, full = roots
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    for root in roots:
        p = root / "use.py"
        p.write_text(p.read_text(encoding="utf-8") + "# touched\n", encoding="utf-8")
    assert _rebuild_code(inc, changed_paths=[inc / "use.py"], no_cluster=True, acquire_lock=False)
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)

    def calls_of(root):
        g = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        return {(e["source"], e["target"]) for e in g.get("links", g.get("edges", []))
                if e["relation"] in ("calls", "references")}

    assert calls_of(inc) == calls_of(full)
    assert ("use_fetch", "resp_response_text") in calls_of(full)


def test_schema_bump_retires_entries_cached_without_property_reads(tmp_path: Path, monkeypatch):
    import graphify.cache as cache_mod
    from graphify.cache import save_cached
    from graphify.extract import extract_python

    files = {"resp.py": _RESPONSE}
    paths = []
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
        paths.append(tmp_path / name)
    current = cache_mod._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache_mod, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", 7)  # last schema without them
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    for p in paths:
        stale = extract_python(p)
        stale["raw_calls"] = [rc for rc in stale.get("raw_calls", []) if not rc.get("_python_attr_read")]
        for node in stale["nodes"]:
            node.pop("_py_property", None)
        save_cached(p, stale, root=tmp_path, cache_root=tmp_path, kind="ast")
    monkeypatch.setattr(cache_mod, "_AST_CACHE_SCHEMA", current)
    monkeypatch.setattr(cache_mod, "_cleaned_ast_dirs", set())
    r = extract(paths, root=tmp_path, cache_root=tmp_path, parallel=False)
    assert any(e["relation"] == "references" and e.get("context") == "property_read" for e in r["edges"])
