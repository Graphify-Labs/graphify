"""A Kotlin `typealias` is a named type and must be extracted as a sourced node.

`typealias ClickHandler = (Int) -> Unit` parses as `type_alias`, which was in
neither `class_types` nor `function_types`, so the declaration was dropped. But
a property or parameter typed as the alias (`var onClick: ClickHandler?`,
`fun handler(h: ClickHandler)`) still ran the name `ClickHandler` through
`ensure_named_node`, which minted a *sourceless* stub and pointed the
`references` edge at it — even though the alias is declared in the same file.
That is a provenance violation (a real source-backed declaration losing to a
sourceless god node). Scala and TypeScript already model type aliases as nodes;
`type_alias` has an `identifier` name and no body, so adding it to the Kotlin
`class_types` emits a clean empty type node those references bind to.
"""
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, body: str):
    (tmp_path / "m.kt").write_text(body)
    return extract([tmp_path / "m.kt"], cache_root=tmp_path, parallel=False)


def _node(r, label):
    return next((n for n in r["nodes"] if n.get("label") == label), None)


def test_typealias_is_a_sourced_node_not_a_sourceless_stub(tmp_path):
    r = _extract(
        tmp_path,
        "typealias ClickHandler = (Int) -> Unit\n"
        "class Button {\n"
        "    var onClick: ClickHandler? = null\n"
        "    fun handler(h: ClickHandler) { onClick = h }\n"
        "}\n",
    )
    alias = _node(r, "ClickHandler")
    assert alias is not None, "typealias declaration was dropped"
    assert alias.get("source_file"), (
        f"typealias ClickHandler is a sourceless god node: {alias}"
    )
    assert not any(
        (not n.get("source_file")) and n.get("label") == "ClickHandler"
        for n in r["nodes"]
    )
    refs_to_alias = {
        e["source"]
        for e in r["edges"]
        if e["relation"] == "references" and e["target"] == alias["id"]
    }
    assert refs_to_alias, "references to the typealias did not bind to it"
