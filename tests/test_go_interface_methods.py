"""Regression coverage for method requirements declared in a Go interface.

The interface body carries the type's contract. Before the fix the extractor
only handled interface embedding and generic type-set constraints, so an
interface like ``type Reader interface { Read(p []byte) (int, error) }`` became
an empty node with no members - the method requirements were dropped entirely.
"""

from pathlib import Path

from graphify.extract import extract


def _extract(root: Path) -> dict:
    return extract(
        sorted(root.rglob("*.go")),
        cache_root=root,
        root=root,
        parallel=False,
    )


def _methods_of(result: dict, type_label: str) -> set[str]:
    """Labels of nodes reached by a ``method`` edge from the named type."""
    by_id = {node["id"]: node for node in result["nodes"]}
    type_ids = {nid for nid, n in by_id.items() if n.get("label") == type_label}
    return {
        by_id[edge["target"]]["label"].strip(".()")
        for edge in result["edges"]
        if edge.get("relation") == "method" and edge.get("source") in type_ids
    }


def test_interface_method_requirements_are_extracted(tmp_path: Path) -> None:
    """Each method requirement becomes a method node under the interface."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    (tmp_path / "shape.go").write_text(
        "package repro\n\n"
        "type Shape interface {\n"
        "\tArea() float64\n"
        "\tPerimeter() (float64, error)\n"
        "}\n"
    )

    result = _extract(tmp_path)
    assert _methods_of(result, "Shape") == {"Area", "Perimeter"}


def test_interface_embedding_still_produces_a_heritage_edge(tmp_path: Path) -> None:
    """A bare embedded interface stays an ``embeds`` edge, not a method."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    (tmp_path / "rw.go").write_text(
        "package repro\n\n"
        "type Reader interface {\n"
        "\tRead(p []byte) (int, error)\n"
        "}\n\n"
        "type ReadCloser interface {\n"
        "\tReader\n"
        "\tClose() error\n"
        "}\n"
    )

    result = _extract(tmp_path)
    by_id = {node["id"]: node for node in result["nodes"]}
    rc_ids = {nid for nid, n in by_id.items() if n.get("label") == "ReadCloser"}
    reader_ids = {nid for nid, n in by_id.items() if n.get("label") == "Reader"}

    # The embedded interface is heritage, not a method of ReadCloser.
    assert any(
        edge.get("relation") == "embeds"
        and edge.get("source") in rc_ids
        and edge.get("target") in reader_ids
        for edge in result["edges"]
    )
    # Only the directly declared method requirement is a method of ReadCloser.
    assert _methods_of(result, "ReadCloser") == {"Close"}
    assert _methods_of(result, "Reader") == {"Read"}


def test_interface_method_is_distinct_from_a_concrete_method(tmp_path: Path) -> None:
    """An interface's ``Area`` and a struct's ``Area`` are two separate nodes."""
    (tmp_path / "go.mod").write_text("module example.com/repro\n\ngo 1.22\n")
    (tmp_path / "shape.go").write_text(
        "package repro\n\n"
        "type Shape interface {\n"
        "\tArea() float64\n"
        "}\n\n"
        "type Rect struct{ W, H float64 }\n\n"
        "func (r Rect) Area() float64 { return r.W * r.H }\n"
    )

    result = _extract(tmp_path)
    by_id = {node["id"]: node for node in result["nodes"]}
    shape_ids = {nid for nid, n in by_id.items() if n.get("label") == "Shape"}
    rect_ids = {nid for nid, n in by_id.items() if n.get("label") == "Rect"}

    shape_area = {
        edge["target"]
        for edge in result["edges"]
        if edge.get("relation") == "method" and edge.get("source") in shape_ids
    }
    rect_area = {
        edge["target"]
        for edge in result["edges"]
        if edge.get("relation") == "method" and edge.get("source") in rect_ids
    }
    assert shape_area and rect_area
    assert shape_area.isdisjoint(rect_area), "interface and struct methods collapsed"
