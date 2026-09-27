"""C# named-tuple element names must not be collected as type references (#3796).

In tree-sitter-c-sharp a named tuple type `(int mode, string label)` is a
`tuple_type` whose children are `tuple_element` nodes carrying a `type` field
and a `name` field. The type-reference collector walks every named child, so
the element NAMES (`mode`, `label`) were minted as sourceless "type" nodes and
emitted `references` edges from the declaring member — one junk type node per
element, repeated in every file that declares such a signature. Only the
`type` field of each element should feed type-reference collection.
"""

from graphify.extract import extract

READER_CS = (
    "namespace Demo\n{\n    public class Reader\n    {\n"
    "        public static (int mode, string label) Read() => (1, \"a\");\n"
    "    }\n}\n"
)


def _extract_source(source: str):
    import os
    import tempfile
    from pathlib import Path

    d = Path(tempfile.mkdtemp())
    p = d / "Reader.cs"
    p.write_text(source)
    old = os.getcwd()
    try:
        os.chdir(d)
        return extract([Path("Reader.cs")], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)


def test_tuple_element_names_are_not_type_references():
    r = _extract_source(READER_CS)

    # Element NAMES must not be minted as type nodes.
    labels = {n["label"] for n in r["nodes"]}
    assert "mode" not in labels
    assert "label" not in labels

    # And no references edge may target a placeholder minted from a name.
    for e in r["edges"]:
        if e["relation"] != "references":
            continue
        target = next(n for n in r["nodes"] if n["id"] == e["target"])
        assert target["label"] not in ("mode", "label"), (
            f"references edge to tuple element name {target['label']}"
        )
