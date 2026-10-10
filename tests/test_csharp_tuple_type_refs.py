"""C# named-tuple element names must not be collected as type references (#3796).

In tree-sitter-c-sharp a named tuple type `(int mode, string label)` is a
`tuple_type` whose children are `tuple_element` nodes carrying a `type` field
and a `name` field. The type-reference collector walked every named child, so
the element NAMES (`mode`, `label`) were minted as sourceless "type" nodes and
emitted `references` edges from the declaring member — one junk type node per
element, repeated in every file that declares such a signature. Only the
`type` field of each element should feed type-reference collection.

The tests use user-defined element types on purpose: they must verify both
halves of the fix — element names are excluded, AND the real element type
references are still collected.
"""

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract_source(source: str):
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
    r = _extract_source(
        "namespace Demo\n{\n    public class Reader\n    {\n"
        "        public static (int mode, string label) Read() => (1, \"a\");\n"
        "    }\n}\n"
    )

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


def test_user_defined_tuple_element_types_are_still_referenced():
    # A named tuple whose element types are user-defined classes: the type
    # references must be kept (only the NAMES are excluded, not the types).
    r = _extract_source(
        "namespace Demo\n{\n"
        "    public class Mode { }\n"
        "    public class Label { }\n"
        "    public class Reader\n    {\n"
        "        public static (Mode mode, Label label) Read() => (null!, null!);\n"
        "    }\n}\n"
    )

    labels = {n["label"] for n in r["nodes"]}
    # User-defined element types are still minted/kept.
    assert "Mode" in labels
    assert "Label" in labels
    # Element names still excluded.
    assert "mode" not in labels
    assert "label" not in labels

    # The declaring member references its tuple element types.
    refs = {
        next(n for n in r["nodes"] if n["id"] == e["target"])["label"]
        for e in r["edges"]
        if e["relation"] == "references"
    }
    assert "Mode" in refs
    assert "Label" in refs
