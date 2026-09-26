"""Extraction coverage for r."""


from __future__ import annotations





import sys


from pathlib import Path





from graphify.extract import extract





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.r"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def test_r_functions_and_calls_are_extracted(tmp_path):
    source = tmp_path / "analysis.R"
    source.write_text(
        "helper <- function(x) x + 1\n"
        "run <- function(x) helper(x)\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert "helper()" in labels
    assert "run()" in labels
    assert ("run()", "helper()") in _edge_labels(result, "calls")


def test_r_assignments_sources_and_classes_are_extracted(tmp_path):
    helper = tmp_path / "helpers.R"
    helper.write_text("shared <- function(x) x\n", encoding="utf-8")
    source = tmp_path / "analysis.R"
    source.write_text(
        'library(dplyr)\n'
        'require("ggplot2")\n'
        'source("helpers.R")\n'
        "answer <- 42\n"
        "function(x) x -> right_assigned\n"
        "outer <- function(x) {\n"
        "  inner <- function(y) y\n"
        "  inner(x)\n"
        "  shared(x)\n"
        "  pkg::shared(x)\n"
        "  get(\"shared\")(x)\n"
        "}\n"
        'Person <- R6Class("Person", inherit = BasePerson, '
        "public = list(run = function(x) outer(x)))\n",
        encoding="utf-8",
    )

    result = extract([source, helper], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {
        "answer", "right_assigned()", "outer()", "inner()", "Person", "run()",
        "dplyr", "ggplot2",
    } <= labels
    calls = _edge_labels(result, "calls")
    assert ("outer()", "inner()") in calls
    assert ("outer()", "shared()") in calls
    assert ("outer()", "pkg::shared()") in calls
    assert ("run()", "outer()") in calls
    assert ("outer()", "outer()") not in calls
    assert ("Person", "BasePerson") in _edge_labels(result, "inherits")
    assert any(edge["relation"] == "imports_from" for edge in result["edges"])


def test_r_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'run()', 'double()'} <= labels
    assert ('run()', 'double()') in _edge_labels(result, "calls")


def test_r_malformed_tail_comments_and_strings_do_not_create_phantoms(tmp_path):
    source = tmp_path / 'broken.R'
    source.write_text('valid <- function() 1\n"ghost <- function() 2"\n# hidden <- function() 3\nbroken(\n', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert 'valid()' in labels
    assert labels.isdisjoint({'ghost()', 'hidden()'})


def test_r_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.R"
    source.write_text('run <- function() 1\n', encoding="utf-8")
    monkeypatch.setitem(sys.modules, 'tree_sitter_language_pack', None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[r]"' in capsys.readouterr().err
