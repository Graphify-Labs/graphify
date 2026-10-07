"""Extraction coverage for r."""


from __future__ import annotations





import importlib.util as _ilu
import sys


from pathlib import Path





import pytest

from graphify.extract import extract, extract_r

# tree-sitter-language-pack is an optional extra, not installed by a default
# `uv sync`. Skip the grammar tests when it is absent; the missing-parser
# test below still runs because it simulates the absent grammar itself.
_needs_r = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_language_pack") is None,
    reason="tree-sitter-language-pack not installed (optional [r] extra)",
)





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.r"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


@_needs_r
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


@_needs_r
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


@_needs_r
def test_r_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'run()', 'double()'} <= labels
    assert ('run()', 'double()') in _edge_labels(result, "calls")


@_needs_r
def test_r_malformed_tail_comments_and_strings_do_not_create_phantoms(tmp_path):
    source = tmp_path / 'broken.R'
    source.write_text('valid <- function() 1\n"ghost <- function() 2"\n# hidden <- function() 3\nbroken(\n', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert 'valid()' in labels
    assert labels.isdisjoint({'ghost()', 'hidden()'})


@_needs_r
def test_r_namespaced_r6class_extracts_the_class_body(tmp_path):
    """`R6::R6Class(...)` is the idiomatic library()-free way to define an R6
    class. The qualified name never matched the class-constructor set, so the
    class collapsed to a plain variable and every method was dropped."""
    source = tmp_path / "counter.R"
    source.write_text(
        'Counter <- R6::R6Class("Counter",\n'
        "  public = list(\n"
        "    increment = function() self$count,\n"
        "    report = function() print(1)\n"
        "  )\n"
        ")\n",
        encoding="utf-8",
    )
    result = extract_r(source)
    labels = {node["label"] for node in result["nodes"]}
    assert {"Counter", "increment()", "report()"} <= labels
    methods = _edge_labels(result, "method")
    assert ("Counter", "increment()") in methods
    assert ("Counter", "report()") in methods


@_needs_r
def test_r_namespaced_setrefclass_is_recognised(tmp_path):
    """A namespace-qualified `methods::setRefClass` declares a class too."""
    source = tmp_path / "acc.R"
    source.write_text(
        'Acc <- methods::setRefClass("Acc",\n'
        "  methods = list(add = function(x) x)\n"
        ")\n",
        encoding="utf-8",
    )
    result = extract_r(source)
    labels = {node["label"] for node in result["nodes"]}
    assert {"Acc", "add()"} <= labels
    assert ("Acc", "add()") in _edge_labels(result, "method")


@_needs_r
def test_r6_self_and_private_method_calls_resolve(tmp_path):
    """R6 methods reach their siblings through `self$` / `private$`, never as a
    bare name. Those intra-class calls were dropped because walk_calls only
    handled a bare identifier callee."""
    source = tmp_path / "counter.R"
    source.write_text(
        'Counter <- R6Class("Counter",\n'
        "  public = list(\n"
        "    increment = function() self$report(),\n"
        "    report = function() print(1)\n"
        "  ),\n"
        "  private = list(\n"
        "    log = function() private$fmt(),\n"
        "    fmt = function() 2\n"
        "  )\n"
        ")\n",
        encoding="utf-8",
    )
    result = extract_r(source)
    calls = _edge_labels(result, "calls")
    assert ("increment()", "report()") in calls, "self$ call dropped"
    assert ("log()", "fmt()") in calls, "private$ call dropped"


def test_r_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.R"
    source.write_text('run <- function() 1\n', encoding="utf-8")
    monkeypatch.setitem(sys.modules, 'tree_sitter_language_pack', None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[r]"' in capsys.readouterr().err


@_needs_r
def test_r_symbol_only_bindings_have_distinct_ids(tmp_path):
    source = tmp_path / "ops.R"
    source.write_text(
        "`%||%` <- function(a, b) a\n"
        "`%>%` <- function(a, b) b\n"
        "`%+%` <- 42\n",
        encoding="utf-8",
    )
    result = extract_r(source)
    by_label = {node["label"]: node for node in result["nodes"]}
    assert {"`%||%`()", "`%>%`()", "`%+%`"} <= by_label.keys()
    assert len({by_label[label]["id"] for label in by_label}) == len(by_label)
    file_id = by_label["ops.R"]["id"]
    for label in ("`%||%`()", "`%>%`()", "`%+%`"):
        assert (file_id, by_label[label]["id"]) in {
            (edge["source"], edge["target"])
            for edge in result["edges"] if edge["relation"] == "contains"
        }


@_needs_r
def test_r_symbol_only_function_with_external_call_terminates(tmp_path):
    import json
    import subprocess

    source = tmp_path / "ops.R"
    source.write_text(
        "`%||%` <- function(a, b) if (is.null(a)) b else a\n",
        encoding="utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-c",
         "import json, sys; from pathlib import Path; "
         "from graphify.extractors.r import extract_r; "
         "print(json.dumps(extract_r(Path(sys.argv[1]))))", str(source)],
        check=True, capture_output=True, text=True, timeout=10,
    )
    result = json.loads(completed.stdout)
    assert "`%||%`()" in {node["label"] for node in result["nodes"]}
    assert any(call["callee"] == "is.null" for call in result["raw_calls"])


@_needs_r
def test_r_operator_fallback_does_not_collide_with_ordinary_binding(tmp_path):
    from graphify.build import build

    source = tmp_path / "ops.R"
    operator = "`%||%` <- function(a, b) a\n"
    ordinary = "operator_60257c7c2560 <- function(a, b) b\n"
    ids_by_order = []
    for declarations in (operator + ordinary, ordinary + operator):
        source.write_text(
            declarations
            + "ordinary_call <- function() operator_60257c7c2560(1, 2)\n"
            + "operator_call <- function() `%||%`(1, 2)\n",
            encoding="utf-8",
        )
        result = extract_r(source)
        by_label = {node["label"]: node for node in result["nodes"]}
        assert {"`%||%`()", "operator_60257c7c2560()"} <= by_label.keys()
        assert ("ordinary_call()", "operator_60257c7c2560()") in _edge_labels(result, "calls")
        assert ("operator_call()", "`%||%`()") in _edge_labels(result, "calls")
        ids_by_order.append({label: node["id"] for label, node in by_label.items()})
        graph = build([result])
        assert by_label["`%||%`()"]["id"] in graph
        assert by_label["operator_60257c7c2560()"]["id"] in graph
    assert ids_by_order[0] == ids_by_order[1]


@_needs_r
def test_r_operator_scope_keeps_nested_binding_identity(tmp_path):
    source = tmp_path / "ops.R"
    source.write_text(
        "`%||%` <- function() { inner <- function() 1; inner() }\n"
        "operator_60257c7c2560 <- function() { inner <- function() 2; inner() }\n",
        encoding="utf-8",
    )
    result = extract_r(source)
    inners = [node for node in result["nodes"] if node["label"] == "inner()"]
    assert len(inners) == 2
    for label in ("`%||%`()", "operator_60257c7c2560()"):
        owner = next(node["id"] for node in result["nodes"] if node["label"] == label)
        contained = {
            edge["target"] for edge in result["edges"]
            if edge["source"] == owner and edge["relation"] == "contains"
        }
        called = {
            edge["target"] for edge in result["edges"]
            if edge["source"] == owner and edge["relation"] == "calls"
        }
        assert len(contained) == 1
        assert called == contained
