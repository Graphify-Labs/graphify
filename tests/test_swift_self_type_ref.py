"""Swift `Self` must not mint a sourceless god node.

A `-> Self` (or `: Self`) annotation names the enclosing type, not a corpus
symbol. The Swift type-ref pass treated the `Self` type_identifier as a type
reference and ran it through the sourceless-stub path, fabricating a node with
the bare id `self` that every `Self`-returning method in the corpus collapses
onto — the same keyword-type god node Rust's `Self` was fixed for. A genuine
type (including the `Int`/`String` builtin hubs) is unaffected.
"""
from pathlib import Path

from graphify.extract import extract


def test_self_return_type_mints_no_stub(tmp_path):
    (tmp_path / "w.swift").write_text(
        "class Widget {\n"
        "    func copy() -> Self { return self }\n"
        "}\n"
    )
    r = extract([tmp_path / "w.swift"], cache_root=tmp_path, parallel=False)
    assert not any(n["id"] == "self" for n in r["nodes"])
    assert not any(e.get("target") == "self" for e in r["edges"])


def test_self_parameter_type_mints_no_stub(tmp_path):
    (tmp_path / "n.swift").write_text(
        "class Node {\n"
        "    func link(_ other: Self) -> Self { return self }\n"
        "}\n"
    )
    r = extract([tmp_path / "n.swift"], cache_root=tmp_path, parallel=False)
    assert not any(n["id"] == "self" for n in r["nodes"])


def test_self_is_not_a_cross_file_god_node(tmp_path):
    (tmp_path / "a.swift").write_text(
        "class A {\n    func dup() -> Self { return self }\n}\n")
    (tmp_path / "b.swift").write_text(
        "class B {\n    func dup() -> Self { return self }\n}\n")
    r = extract(sorted(tmp_path.glob("*.swift")), cache_root=tmp_path, parallel=False)
    assert not any(n["id"] == "self" for n in r["nodes"])


def test_real_return_type_still_referenced(tmp_path):
    # The guard must not suppress a genuine user return type.
    (tmp_path / "m.swift").write_text(
        "class Money {}\n"
        "class Account {\n"
        "    func balance() -> Money { return Money() }\n"
        "}\n"
    )
    r = extract([tmp_path / "m.swift"], cache_root=tmp_path, parallel=False)
    money_ids = [n["id"] for n in r["nodes"] if n.get("label") == "Money"]
    assert money_ids
    assert any(
        e.get("relation") == "references" and e.get("target") in money_ids
        for e in r["edges"]
    )
