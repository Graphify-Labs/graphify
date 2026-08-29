"""Tests for deterministic R extraction and extensionless Rscript routing."""
from pathlib import Path

from graphify.extract import _get_extractor, extract_r

FIXTURES = Path(__file__).parent / "fixtures"


def test_r_extracts_imports_functions_nested_scope_and_calls() -> None:
    result = extract_r(FIXTURES / "sample.r")

    labels = {node["label"] for node in result["nodes"]}
    assert {
        "sample.r",
        "normalize_values()",
        "identity_value()",
        "make_scaler()",
        "scale_one()",
        "analyze()",
    } <= labels
    ids = {node["label"]: node["id"] for node in result["nodes"]}

    relations = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in result["edges"]
    }
    assert (ids["sample.r"], "dplyr", "imports") in relations
    assert (ids["sample.r"], "jsonlite", "imports") in relations
    assert (
        ids["make_scaler()"],
        ids["scale_one()"],
        "contains",
    ) in relations
    assert (
        ids["analyze()"],
        ids["normalize_values()"],
        "calls",
    ) in relations
    assert (
        ids["analyze()"],
        ids["identity_value()"],
        "calls",
    ) in relations

    raw_calls = {(call["caller_nid"], call["callee"]) for call in result["raw_calls"]}
    assert (ids["analyze()"], "median") in raw_calls
    assert not any(callee == "fake" for _, callee in raw_calls)


def test_extensionless_rscript_routes_to_r_extractor(tmp_path: Path) -> None:
    script = tmp_path / "analyze"
    script.write_text(
        "#!/usr/bin/env Rscript\n"
        "run <- function(values) {\n"
        "  mean(values)\n"
        "}\n"
    )

    assert _get_extractor(script) is extract_r
    result = extract_r(script)
    assert any(node["label"] == "run()" for node in result["nodes"])


def test_r_invalid_utf8_is_replaced_without_dropping_symbols(tmp_path: Path) -> None:
    source = tmp_path / "legacy.r"
    source.write_bytes(b"# legacy annotation: \xff\nrun <- function(value) value\n")

    result = extract_r(source)
    assert "error" not in result
    assert any(node["label"] == "run()" for node in result["nodes"])
