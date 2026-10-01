"""Package-level Go var/const must become nodes (#2360).

Go codebases express enums, sentinel values, and policy data as package-level
const/var. Before this fix, extract_go only walked function/method/type/import
declarations, so those identifiers were absent from the graph and could not
seed vocabulary expansion or references edges.
"""
from __future__ import annotations

from graphify.extract import extract, extract_go


def _labels(result):
    return {n.get("label") for n in result["nodes"]}


def _edge_label_pairs(result, relation):
    id_to_label = {n["id"]: n.get("label") for n in result["nodes"]}
    pairs = set()
    for e in result["edges"]:
        if e.get("relation") != relation:
            continue
        src = id_to_label.get(e["source"])
        tgt = id_to_label.get(e["target"])
        if src is not None and tgt is not None:
            pairs.add((src, tgt))
    return pairs


def test_go_package_level_var_const_emit_nodes(tmp_path):
    src = tmp_path / "policy.go"
    src.write_text(
        "package demo\n"
        "\n"
        "var DefaultBlacklist = []string{\"vape\", \"box cutter\"}\n"
        "\n"
        "const ReasonDisallowedObject = \"DISALLOWED_OBJECT\"\n"
        "\n"
        "const (\n"
        "\tCheckQRStatus         = \"qr_status\"\n"
        "\tCheckDisallowedObject = \"disallowed_object\"\n"
        ")\n"
        "\n"
        "func Blacklist() []string { return DefaultBlacklist }\n",
        encoding="utf-8",
    )

    result = extract_go(src)
    assert "error" not in result
    labels = _labels(result)
    assert {
        "DefaultBlacklist",
        "ReasonDisallowedObject",
        "CheckQRStatus",
        "CheckDisallowedObject",
        "Blacklist()",
    } <= labels

    contains = _edge_label_pairs(result, "contains")
    assert ("policy.go", "DefaultBlacklist") in contains
    assert ("policy.go", "ReasonDisallowedObject") in contains
    assert ("policy.go", "CheckQRStatus") in contains
    assert ("policy.go", "CheckDisallowedObject") in contains


def test_go_package_level_var_multi_name_spec(tmp_path):
    src = tmp_path / "multi.go"
    src.write_text(
        "package demo\n"
        "\n"
        "var a, b = 1, 2\n"
        "\n"
        "const (\n"
        "\tX, Y = 3, 4\n"
        ")\n",
        encoding="utf-8",
    )

    result = extract_go(src)
    assert {"a", "b", "X", "Y"} <= _labels(result)


def test_go_blank_identifier_var_not_emitted(tmp_path):
    src = tmp_path / "blank.go"
    src.write_text(
        "package demo\n"
        "\n"
        "var _ = 1\n"
        "var Kept = 2\n",
        encoding="utf-8",
    )

    result = extract_go(src)
    labels = _labels(result)
    assert "Kept" in labels
    assert "_" not in labels


def test_go_in_file_var_reference_edge(tmp_path):
    src = tmp_path / "policy.go"
    src.write_text(
        "package demo\n"
        "\n"
        "var DefaultBlacklist = []string{\"a\"}\n"
        "\n"
        "func Blacklist() []string { return DefaultBlacklist }\n",
        encoding="utf-8",
    )

    result = extract_go(src)
    assert ("Blacklist()", "DefaultBlacklist") in _edge_label_pairs(result, "references")


def test_go_cross_file_const_reference_edge(tmp_path):
    policy = tmp_path / "policy.go"
    policy.write_text(
        "package demo\n"
        "\n"
        "var DefaultBlacklist = []string{\"vape\"}\n"
        "\n"
        "const ReasonDisallowedObject = \"DISALLOWED_OBJECT\"\n"
        "\n"
        "const CheckQRStatus = \"qr_status\"\n"
        "\n"
        "func Blacklist() []string { return DefaultBlacklist }\n",
        encoding="utf-8",
    )
    use = tmp_path / "use.go"
    use.write_text(
        "package demo\n"
        "\n"
        "func Classify(obj string) string {\n"
        "\tfor _, b := range DefaultBlacklist {\n"
        "\t\tif b == obj {\n"
        "\t\t\treturn ReasonDisallowedObject\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn CheckQRStatus\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(
        [policy, use],
        cache_root=tmp_path,
        parallel=False,
    )
    labels = _labels(result)
    assert {
        "DefaultBlacklist",
        "ReasonDisallowedObject",
        "CheckQRStatus",
        "Blacklist()",
        "Classify()",
    } <= labels

    refs = _edge_label_pairs(result, "references")
    assert ("Classify()", "DefaultBlacklist") in refs
    assert ("Classify()", "ReasonDisallowedObject") in refs
    assert ("Classify()", "CheckQRStatus") in refs
    assert ("Blacklist()", "DefaultBlacklist") in refs
