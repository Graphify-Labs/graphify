"""Java fields must be nodes with inbound edges, via LanguageConfig.value_types.

The shared engine dispatched on classes, functions, imports and calls. A
Java constant is a field_declaration and none of those, so it never
became a node and reading one was not recorded as a relation.

Observed on a 14-file Java codebase using five constants each read in
exactly one method: none of the five was a node, while all five reading
methods were. `graphify query <constant>` answered 1/5; after this
change, 5/5.

value_types is opt-in per language and empty everywhere else, which is
what every language did implicitly before the field existed. Go declares
its own values in extractors/go.py because it does not use this engine.
"""
import pytest

from graphify.extract import extract


def _extract(tmp_path, glob):
    return extract(sorted(tmp_path.glob(glob)), cache_root=tmp_path, parallel=False)


def _node_by_label(result, label):
    for n in result["nodes"]:
        if (n.get("label") or "").strip(".()") == label:
            return n
    return None


def _has_edge(result, src_label, tgt_label, relation):
    src = _node_by_label(result, src_label)
    tgt = _node_by_label(result, tgt_label)
    if src is None or tgt is None:
        return False
    return any(
        e.get("source") == src["id"]
        and e.get("target") == tgt["id"]
        and e.get("relation") == relation
        for e in result["edges"]
    )


@pytest.fixture
def gilded(tmp_path):
    (tmp_path / "GildedRose.java").write_text(
        "package shop;\n"
        "\n"
        "public class GildedRose {\n"
        "    private static final int MAX_QUALITY = 50;\n"
        "    private static final int UNUSED_LIMIT = 99;\n"
        "\n"
        "    private int clamp(int quality) {\n"
        "        return Math.min(MAX_QUALITY, quality);\n"
        "    }\n"
        "}\n"
    )
    return _extract(tmp_path, "*.java")


def test_fields_become_nodes(gilded):
    node = _node_by_label(gilded, "MAX_QUALITY")
    assert node is not None, "MAX_QUALITY is not a node"
    assert node.get("value_kind") == "field"


def test_reading_a_field_is_an_edge(gilded):
    assert _has_edge(gilded, "clamp", "MAX_QUALITY", "references")


def test_unread_field_has_no_reader(gilded):
    assert not _has_edge(gilded, "clamp", "UNUSED_LIMIT", "references")


def test_field_read_from_a_sibling_file(tmp_path):
    (tmp_path / "Limits.java").write_text(
        "package shop;\n"
        "\n"
        "public class Limits {\n"
        "    public static final int MAX_QUALITY = 50;\n"
        "}\n"
    )
    (tmp_path / "Rose.java").write_text(
        "package shop;\n"
        "\n"
        "public class Rose {\n"
        "    private int clamp(int quality) {\n"
        "        return Math.min(MAX_QUALITY, quality);\n"
        "    }\n"
        "}\n"
    )
    result = _extract(tmp_path, "*.java")
    assert _has_edge(result, "clamp", "MAX_QUALITY", "references")


def test_a_language_without_value_types_is_unchanged(tmp_path):
    # Python does not set value_types, so a module-level constant stays out
    # of the graph exactly as before. The field is opt-in on purpose: every
    # language behaved this way until one of them asked for more.
    (tmp_path / "m.py").write_text("LIMIT = 50\n\n\ndef clamp(q):\n    return min(LIMIT, q)\n")
    result = _extract(tmp_path, "*.py")
    assert _node_by_label(result, "LIMIT") is None
