"""Tests for the R extractor and its corpus-wide resolver.

R needs both halves to produce a usable graph, so they are tested together.
The extractor can only see one file, and in R that is not enough to tell a base
call (``sum``) from a sibling-file one (``format_row``) — nothing in the syntax
or the file distinguishes them. The extractor therefore emits unresolved calls
as ``raw_calls`` and ``graphify.r_resolution`` decides, dropping whatever the
corpus does not define.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import pytest

from graphify.extract import extract, extract_r

FIXTURES = Path(__file__).parent / "fixtures"

# tree-sitter-language-pack is the optional [r] extra: it carries the r-lib R
# grammar, which has no standalone PyPI wheel.
needs_r = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_language_pack") is None,
    reason="tree-sitter-language-pack not installed (optional [r] extra)",
)

pytestmark = needs_r


def _labels(result: dict) -> list[str]:
    return [n["label"] for n in result["nodes"]]


def _edges(result: dict, relation: str) -> list[dict]:
    return [e for e in result["edges"] if e["relation"] == relation]


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_r_finds_functions_across_every_binding_form() -> None:
    """`<-`, `=`, `<<-`, `\\(x)` and right-assign all define a function in R."""
    r = extract_r(FIXTURES / "sample.R")
    assert "error" not in r
    labels = _labels(r)
    for name in ("compute_moments()", "rescale()", "report_moments()",
                 "cache_result()", "square_it()", "summarise()"):
        assert name in labels, f"{name} missing from {labels}"


def test_r_nested_function_is_defined_by_its_enclosing_function() -> None:
    r = extract_r(FIXTURES / "sample.R")
    by_id = {n["id"]: n["label"] for n in r["nodes"]}
    defines = {(by_id.get(e["source"]), by_id.get(e["target"]))
               for e in _edges(r, "defines")}
    assert ("compute_moments()", "normalise_weights()") in defines


def test_r_resolves_same_file_calls() -> None:
    r = extract_r(FIXTURES / "sample.R")
    by_id = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(by_id.get(e["source"]), by_id.get(e["target"]))
             for e in _edges(r, "calls")}
    assert ("compute_moments()", "rescale()") in calls
    assert ("compute_moments()", "normalise_weights()") in calls


def test_r_call_edges_have_call_context() -> None:
    r = extract_r(FIXTURES / "sample.R")
    call_edges = _edges(r, "calls")
    assert call_edges
    assert all(e.get("context") == "call" for e in call_edges)


def test_r_base_calls_produce_no_edge() -> None:
    """`sum`, `cat`, `vapply` are base R. Nothing defines them, so nothing links.

    They stay in raw_calls, where the resolver drops them for want of a
    definition — the alternative would be ~1,300 hardcoded base names.
    """
    r = extract_r(FIXTURES / "sample.R")
    labels = _labels(r)
    for base in ("sum()", "cat()", "vapply()", "invisible()"):
        assert base not in labels
    assert {"sum", "cat", "vapply"} <= {rc["callee"] for rc in r["raw_calls"]}


def test_r_finds_package_imports() -> None:
    r = extract_r(FIXTURES / "sample.R")
    imported = {n["label"] for e in _edges(r, "imports")
                for n in r["nodes"] if n["id"] == e["target"]}
    # library(stats), requireNamespace("jsonlite"), and the stats::sd call
    assert {"stats", "jsonlite"} <= imported


def test_r_import_edges_have_import_context() -> None:
    r = extract_r(FIXTURES / "sample.R")
    import_edges = _edges(r, "imports")
    assert import_edges
    assert all(e.get("context") == "import" for e in import_edges)


def test_r_emits_no_dangling_edges() -> None:
    """Every endpoint the extractor emits must be a node it also emits.

    build_from_json silently drops an edge whose endpoint is missing and the
    health check counts it as corruption, so an extractor that guesses at
    targets degrades the graph without failing.
    """
    r = extract_r(FIXTURES / "sample.R")
    ids = {n["id"] for n in r["nodes"]}
    dangling = [(e["source"], e["target"]) for e in r["edges"]
                if e["source"] not in ids or e["target"] not in ids]
    assert dangling == []


def test_r_resolver_links_calls_across_files(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.R", "caller <- function() format_row(1)\n")
    b = _write(tmp_path / "b.R", "format_row <- function(x) x\n")
    result = extract([a, b], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {(by_id.get(e["source"]), by_id.get(e["target"]))
             for e in result["edges"] if e["relation"] == "calls"}
    assert ("caller()", "format_row()") in calls


def test_r_resolver_skips_ambiguous_callee(tmp_path: Path) -> None:
    """Two definitions of one name is the god-node case: emit nothing."""
    a = _write(tmp_path / "a.R", "caller <- function() helper(1)\n")
    b = _write(tmp_path / "b.R", "helper <- function(x) x\n")
    c = _write(tmp_path / "c.R", "helper <- function(x) x + 1\n")
    result = extract([a, b, c], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    calls = {(by_id.get(e["source"]), by_id.get(e["target"]))
             for e in result["edges"] if e["relation"] == "calls"}
    assert not any(src == "caller()" and tgt == "helper()" for src, tgt in calls)


def test_r_resolver_links_sourced_files(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.R", 'source("b.R")\n')
    b = _write(tmp_path / "b.R", "helper <- function(x) x\n")
    result = extract([a, b], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    imports = {(by_id.get(e["source"]), by_id.get(e["target"]))
               for e in result["edges"] if e["relation"] == "imports"}
    assert ("a.R", "b.R") in imports


def test_r_resolver_links_joined_paths_through_a_wrapper(tmp_path: Path) -> None:
    """`source_once(paper_path("sub", "b.R"))` is the shape real projects use.

    The path is built by a helper from string literals, so a bare-string-literal
    reader sees nothing. The joined literal is matched by trailing path segments
    against the corpus, so only a file that exists can be linked.
    """
    a = _write(tmp_path / "a.R", 'source_once(paper_path("sub", "b.R"))\n')
    b = _write(tmp_path / "sub" / "b.R", "helper <- function(x) x\n")
    result = extract([a, b], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(by_id.get(e["source"]), by_id.get(e["target"]))
            for e in result["edges"] if e["relation"] == "references"}
    assert ("a.R", "b.R") in refs


def test_r_resolver_ignores_paths_outside_the_corpus(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.R", 'source("nowhere/missing.R")\n')
    result = extract([a], cache_root=tmp_path)
    ids = {n["id"] for n in result["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in result["edges"])


def test_r_uppercase_and_lowercase_suffix_both_dispatch() -> None:
    from graphify.extract import _get_extractor
    assert _get_extractor(Path("x.R")) is extract_r
    assert _get_extractor(Path("x.r")) is extract_r


# --- roxygen documentation and S3 dispatch -----------------------------------


def test_r_roxygen_marks_exported_functions() -> None:
    r = extract_r(FIXTURES / "sample_roxygen.R")
    exported = {n["label"] for n in r["nodes"] if n.get("exported")}
    assert {"new_moments()", "print.moments()", "describe()"} <= exported
    assert "summarise_moments()" not in exported, "undocumented helper is not public API"


def test_r_roxygen_records_family() -> None:
    r = extract_r(FIXTURES / "sample_roxygen.R")
    fams = {n["label"]: n.get("doc_family") for n in r["nodes"] if n.get("doc_family")}
    assert fams.get("new_moments()") == "moments"


def test_r_roxygen_emits_seealso_and_template_refs() -> None:
    r = extract_r(FIXTURES / "sample_roxygen.R")
    kinds = {(rc["kind"], rc["ref_name"]) for rc in r["raw_calls"] if "ref_name" in rc}
    assert ("doc_ref", "summarise_moments") in kinds
    assert ("template_ref", "param-shared") in kinds


def test_r_non_call_records_carry_no_callee() -> None:
    """The shared cross-file pass turns any `callee` into a calls edge (#1668)."""
    r = extract_r(FIXTURES / "sample_roxygen.R")
    non_calls = [rc for rc in r["raw_calls"]
                 if rc.get("kind") in ("doc_ref", "template_ref",
                                       "s3_method", "s3_generic", "s3_class_site")]
    assert non_calls
    assert all("callee" not in rc for rc in non_calls)


def test_r_seealso_resolves_to_a_references_edge(tmp_path: Path) -> None:
    """@seealso names a function the documenting one never calls."""
    a = _write(tmp_path / "a.R", "#' @seealso \\code{\\link{helper}}\ncaller <- function() 1\n")
    b = _write(tmp_path / "b.R", "helper <- function(x) x\n")
    result = extract([a, b], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(by_id.get(e["source"]), by_id.get(e["target"]))
            for e in result["edges"] if e.get("context") == "doc"}
    assert ("caller()", "helper()") in refs


def test_r_template_resolves_to_the_man_roxygen_file(tmp_path: Path) -> None:
    a = _write(tmp_path / "a.R", "#' @template param-step\ncaller <- function() 1\n")
    tpl = _write(tmp_path / "man-roxygen" / "param-step.R", "#' @param step months per period\n")
    result = extract([a, tpl], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    refs = {(by_id.get(e["source"]), by_id.get(e["target"]))
            for e in result["edges"] if e.get("context") == "doc"}
    assert ("caller()", "param-step.R") in refs


def test_r_s3_method_links_to_the_class_constructor(tmp_path: Path) -> None:
    src = (FIXTURES / "sample_roxygen.R").read_text(encoding="utf-8")
    a = _write(tmp_path / "a.R", src)
    result = extract([a], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    s3 = {(by_id.get(e["source"]), by_id.get(e["target"]))
          for e in result["edges"] if e.get("context") == "s3"}
    assert ("print.moments()", "new_moments()") in s3


def test_r_s3_prefers_a_usemethod_generic_over_the_class_site(tmp_path: Path) -> None:
    src = (FIXTURES / "sample_roxygen.R").read_text(encoding="utf-8")
    a = _write(tmp_path / "a.R", src)
    result = extract([a], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    s3 = {(by_id.get(e["source"]), by_id.get(e["target"]))
          for e in result["edges"] if e.get("context") == "s3"}
    assert ("describe.moments()", "describe()") in s3


def test_r_ordinary_dotted_name_is_not_an_s3_method(tmp_path: Path) -> None:
    """`my.helper` splits into a generic and class the corpus never evidences."""
    src = (FIXTURES / "sample_roxygen.R").read_text(encoding="utf-8")
    a = _write(tmp_path / "a.R", src)
    result = extract([a], cache_root=tmp_path)
    by_id = {n["id"]: n["label"] for n in result["nodes"]}
    s3_sources = {by_id.get(e["source"]) for e in result["edges"] if e.get("context") == "s3"}
    assert "my.helper()" not in s3_sources
