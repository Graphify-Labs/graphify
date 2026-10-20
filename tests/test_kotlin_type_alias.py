"""Kotlin typealias declarations (#4553).

`typealias` (node type `type_alias`) was in neither `class_types` nor
`function_types`, so the declaration itself got no node. A property or
parameter typed as the alias still resolved the name through
`ensure_named_node`, which minted a sourceless stub and pointed every
`references` edge at that stub instead of the real, same-file declaration.
Kotlin now models a type alias as a node the same way Scala and TypeScript
already model their own type aliases.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    return r


def _edges(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def test_type_alias_gets_a_sourced_node(tmp_path):
    r = _extract(tmp_path, {
        "Click.kt": (
            "typealias ClickHandler = (Int) -> Unit\n"
            "class Button {\n"
            "    var onClick: ClickHandler? = null\n"
            "    fun handler(h: ClickHandler) { onClick = h }\n"
            "}\n"
        ),
    })
    alias = next(n for n in r["nodes"] if n["label"] == "ClickHandler")
    assert alias["source_file"], "the alias must not be a sourceless stub"
    assert alias["source_file"].endswith("Click.kt")


def test_type_alias_references_bind_to_the_real_node_not_a_stub(tmp_path):
    r = _extract(tmp_path, {
        "Click.kt": (
            "typealias ClickHandler = (Int) -> Unit\n"
            "class Button {\n"
            "    var onClick: ClickHandler? = null\n"
            "    fun handler(h: ClickHandler) { onClick = h }\n"
            "}\n"
        ),
    })
    alias = next(n for n in r["nodes"] if n["label"] == "ClickHandler")
    button = next(n for n in r["nodes"] if n["label"] == "Button")
    handler = next(n for n in r["nodes"] if n["label"] == ".handler()")
    refs = _edges(r, "references")
    assert (button["id"], alias["id"]) in refs
    assert (handler["id"], alias["id"]) in refs
    # Exactly one ClickHandler node exists -- the sourced one, not a second,
    # sourceless stub that references would otherwise collide onto.
    assert sum(1 for n in r["nodes"] if n["label"] == "ClickHandler") == 1


def test_type_alias_is_contained_by_its_file(tmp_path):
    r = _extract(tmp_path, {
        "Click.kt": "typealias ClickHandler = (Int) -> Unit\n",
    })
    alias = next(n for n in r["nodes"] if n["label"] == "ClickHandler")
    file_node = next(n for n in r["nodes"] if n["label"] == "Click.kt")
    assert (file_node["id"], alias["id"]) in _edges(r, "contains")
