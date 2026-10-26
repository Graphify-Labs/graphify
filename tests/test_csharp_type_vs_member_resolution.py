from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.csharp import _build_csharp_type_def_index, _type_def_sort_key


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_by_id(result: dict, nid: str) -> dict | None:
    return next((n for n in result["nodes"] if n.get("id") == nid), None)


def _edge_targets(result: dict, context: str, label: str) -> list[dict]:
    """Nodes targeted by `references` edges of the given context, for a label."""
    out = []
    for edge in result["edges"]:
        if edge.get("relation") != "references" or edge.get("context") != context:
            continue
        node = _node_by_id(result, edge.get("target"))
        if node is not None and node.get("label") == label:
            out.append(node)
    return out


def _type_def(result: dict, label: str) -> dict:
    defs = [
        n for n in result["nodes"]
        if n.get("label") == label and n.get("source_file") and n.get("_callable_class")
    ]
    assert len(defs) == 1, f"expected one {label} type definition, got {defs}"
    return defs[0]


CONTEXT = "App.Data"

# The context sorts BEFORE the entity by filename on purpose. The index tie-breaks on
# (source_file, line), so with the property still in the running it wins on filename
# alone -- which is the realistic layout, an entity class and its DbContext in separate
# files. Putting both in one file lets the line-number ordering mask the bug.
DBCONTEXT = """namespace App.Data;

public class AppContext
{
    public DbSet<Widget> Widget { get; set; }
}
"""

ENTITY = """namespace App.Data;

public class Widget
{
    public int Id { get; set; }
}
"""

CONSUMER = """using System.Collections.Generic;
using App.Data;

namespace App.Services;

public static class WidgetAdapter
{
    public static string Describe(Widget widget) => widget.Id.ToString();

    public static int CountAll(List<Widget> widgets) => widgets.Count;
}
"""


def _corpus(tmp_path: Path) -> list[Path]:
    return [
        _write(tmp_path / "AppContext.cs", DBCONTEXT),
        _write(tmp_path / "Widget.cs", ENTITY),
        _write(tmp_path / "Service.cs", CONSUMER),
    ]


def test_type_reference_binds_to_the_type_not_a_same_named_property(tmp_path: Path):
    """A DbSet<T> property named after its own element type must not absorb type refs.

    `public DbSet<Widget> Widget` puts a PROPERTY named Widget in the same
    (namespace, name) bucket as the CLASS Widget, and the property used to win the
    type-definition index -- so every cross-file `Widget` type reference pointed at the
    property and the class kept only its own file's `contains` edge.
    """
    result = extract(_corpus(tmp_path), cache_root=tmp_path)

    widget_class = _type_def(result, "Widget")
    assert widget_class.get("source_file", "").endswith("Widget.cs")

    for context in ("parameter_type", "generic_arg"):
        targets = _edge_targets(result, context, "Widget")
        assert targets, f"no {context} reference to Widget was emitted"
        for node in targets:
            assert node["id"] == widget_class["id"], (
                f"{context} reference bound to {node['id']} "
                f"({node.get('source_location')}) instead of the class"
            )


def test_the_same_named_property_keeps_its_own_member_edge(tmp_path: Path):
    """Excluding members from the TYPE index must not delete or orphan the member."""
    result = extract(_corpus(tmp_path), cache_root=tmp_path)

    prop = [
        n for n in result["nodes"]
        if n.get("label") == "Widget"
        and str(n.get("source_file", "")).endswith("AppContext.cs")
    ]
    assert len(prop) == 1, "the DbSet property node should still exist"
    assert not prop[0].get("_callable_class"), "a property is not a type declaration"

    owner = next(n for n in result["nodes"] if n.get("label") == "AppContext")
    assert any(
        e.get("source") == owner["id"] and e.get("target") == prop[0]["id"]
        for e in result["edges"]
    ), "AppContext should still own its Widget property"


def test_every_csharp_type_kind_still_resolves(tmp_path: Path):
    """Guard the discriminator: `_callable_class` must cover all type declarations.

    Filtering the index on `_callable_class` would silently break resolution for any
    type kind that does not carry it, so pin the whole set rather than just classes.
    """
    kinds = _write(
        tmp_path / "Kinds.cs",
        "namespace App.Kinds;\n\n"
        "public class AClass {}\n"
        "public interface AnInterface {}\n"
        "public enum AnEnum { One }\n"
        "public record ARecord(int X);\n"
        "public struct AStruct { public int Y; }\n"
        "public abstract class AnAbstract {}\n"
        "public static class AStatic {}\n",
    )
    user = _write(
        tmp_path / "User.cs",
        "using App.Kinds;\n\n"
        "namespace App.Use;\n\n"
        "public class Consumer\n"
        "{\n"
        "    public void A(AClass a) {}\n"
        "    public void B(AnInterface b) {}\n"
        "    public void C(AnEnum c) {}\n"
        "    public void D(ARecord d) {}\n"
        "    public void E(AStruct e) {}\n"
        "    public void F(AnAbstract f) {}\n"
        "    public void G(AStatic g) {}\n"
        "}\n",
    )
    result = extract([kinds, user], cache_root=tmp_path)

    for label in ("AClass", "AnInterface", "AnEnum", "ARecord", "AStruct", "AnAbstract", "AStatic"):
        definition = _type_def(result, label)
        targets = _edge_targets(result, "parameter_type", label)
        assert targets, f"{label} lost its parameter_type reference"
        assert all(n["id"] == definition["id"] for n in targets), (
            f"{label} reference did not bind to its declaration"
        )


def test_type_def_index_skips_members(tmp_path: Path):
    nodes = [
        {
            "id": "cls", "label": "Widget", "file_type": "code",
            "source_file": "Ctx.cs", "source_location": "L5",
            "_callable_class": True, "metadata": {"namespace": CONTEXT},
        },
        {
            "id": "prop", "label": "Widget", "file_type": "code",
            "source_file": "Ctx.cs", "source_location": "L12",
            "metadata": {"namespace": CONTEXT},
        },
    ]
    assert _build_csharp_type_def_index(nodes) == {(CONTEXT, "Widget"): "cls"}


def test_type_def_tie_break_orders_by_line_number_not_lexically():
    """`L12` sorts before `L5` as a string, so the tie-break has to parse the line."""
    early = {"id": "a", "source_file": "F.cs", "source_location": "L5"}
    late = {"id": "b", "source_file": "F.cs", "source_location": "L12"}
    assert sorted([late, early], key=_type_def_sort_key)[0]["id"] == "a"

    unparseable = {"id": "c", "source_file": "F.cs", "source_location": ""}
    assert sorted([early, unparseable], key=_type_def_sort_key)[0]["id"] == "c"
