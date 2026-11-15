"""PEP 673 `Self` must not mint a sourceless god node.

A `-> Self` (or `: Self`, or `typing.Self`) annotation names the enclosing
class, not a corpus symbol. The Python type-ref pass treated the bare
identifier `Self` as a type reference and ran it through the sourceless-stub
path, fabricating a node with the bare id `self` that every `Self`-annotated
method in the corpus collapses onto — the same keyword-type god node Rust's
`Self` was fixed for. It is now dropped, matching how the `-> "ClassName"`
self forward-ref is already left unresolved.
"""
from pathlib import Path

from graphify.extract import extract


def _sourceless(r):
    return [(n["id"], n.get("label")) for n in r["nodes"] if not n.get("source_file")]


def test_self_return_annotation_mints_no_stub(tmp_path):
    (tmp_path / "b.py").write_text(
        "from typing import Self\n"
        "class Builder:\n"
        "    def set(self, x) -> Self:\n"
        "        return self\n"
    )
    r = extract([tmp_path / "b.py"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []
    assert not any(n["id"] == "self" for n in r["nodes"])


def test_typing_qualified_self_mints_no_stub(tmp_path):
    (tmp_path / "b.py").write_text(
        "import typing\n"
        "class Node:\n"
        "    def clone(self) -> typing.Self:\n"
        "        return self\n"
        "    def link(self, other: typing.Self) -> None:\n"
        "        pass\n"
    )
    r = extract([tmp_path / "b.py"], cache_root=tmp_path, parallel=False)
    assert _sourceless(r) == []


def test_self_is_not_a_cross_file_god_node(tmp_path):
    (tmp_path / "a.py").write_text(
        "from typing import Self\n"
        "class A:\n"
        "    def f(self) -> Self:\n"
        "        return self\n"
    )
    (tmp_path / "b.py").write_text(
        "from typing import Self\n"
        "class B:\n"
        "    def g(self) -> Self:\n"
        "        return self\n"
    )
    r = extract(sorted(tmp_path.glob("*.py")), cache_root=tmp_path, parallel=False)
    assert not any(n["id"] == "self" for n in r["nodes"])
    assert not any(e.get("target") == "self" for e in r["edges"])


def test_real_return_type_still_referenced(tmp_path):
    # The guard must not suppress a genuine user return type.
    (tmp_path / "m.py").write_text(
        "class Foo:\n"
        "    pass\n"
        "class B:\n"
        "    def make(self) -> Foo:\n"
        "        return Foo()\n"
    )
    r = extract([tmp_path / "m.py"], cache_root=tmp_path, parallel=False)
    foo_ids = [n["id"] for n in r["nodes"] if n.get("label") == "Foo"]
    assert foo_ids
    assert any(
        e.get("relation") == "references" and e.get("target") in foo_ids
        for e in r["edges"]
    )
