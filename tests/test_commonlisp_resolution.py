"""Tests for cross-file Common Lisp call resolution.

A Common Lisp system spreads its functions across many files of one package
and calls them by bare name, with no receiver at the call site and no import
statement naming the target. The per-file extractor sees only the file it is
parsing, so most real calls have no candidate to bind to. It reports those as
raw_calls and graphify.commonlisp_resolution binds them against the merged
corpus. See that module's docstring for why the resolution rule differs from
the Pascal one it is modelled on.
"""
from __future__ import annotations

from graphify.extract import extract, extract_commonlisp


def _call_edge(graph: dict, src_label: str, tgt_label: str) -> dict | None:
    by_id = {n["id"]: n for n in graph["nodes"]}
    for e in graph.get("edges", graph.get("links", [])):
        if e.get("relation") != "calls":
            continue
        s = by_id.get(e.get("source"), {}).get("label")
        t = by_id.get(e.get("target"), {}).get("label")
        if s == src_label and t == tgt_label:
            return e
    return None


def _write(tmp_path, name: str, text: str):
    p = tmp_path / name
    p.write_text(text)
    return p


def test_single_file_extraction_reports_unresolved_call(tmp_path):
    """The gap this resolver closes: extracting the caller's file alone cannot
    see the callee's file, so no calls edge may be invented there, and the call
    must be reported rather than dropped."""
    b = _write(tmp_path, "b.lisp", "(defun caller (x) (helper x))\n")
    r = extract_commonlisp(b)
    assert _call_edge(r, "caller()", "helper()") is None
    rc = next((c for c in r["raw_calls"] if c["callee"] == "helper"), None)
    assert rc is not None
    assert rc["caller_nid"]
    assert rc["lang"] == "commonlisp"


def test_calls_resolve_across_files_by_name(tmp_path):
    a = _write(tmp_path, "a.lisp", "(defun helper (x) (* x 2))\n")
    b = _write(tmp_path, "b.lisp", "(defun caller (x) (helper x))\n")
    graph = extract([a, b], cache_root=tmp_path, parallel=False)
    edge = _call_edge(graph, "caller()", "helper()")
    assert edge is not None
    # A bare-name match across the corpus is weaker than a call the extractor
    # resolved inside one file, and is marked as such.
    assert edge.get("confidence") == "INFERRED"


def test_same_file_call_stays_extracted(tmp_path):
    """Control: the per-file path still resolves its own calls, at full
    confidence, so the resolver cannot pass by taking over everything."""
    a = _write(
        tmp_path, "a.lisp",
        "(defun helper (x) (* x 2))\n(defun local-caller (x) (helper x))\n",
    )
    graph = extract([a], cache_root=tmp_path, parallel=False)
    edge = _call_edge(graph, "local-caller()", "helper()")
    assert edge is not None
    assert edge.get("confidence") == "EXTRACTED"


def test_ambiguous_name_produces_no_edge(tmp_path):
    """Two definitions of one name in unrelated files is not a resolution.
    The single-candidate guard must drop it rather than pick one."""
    a = _write(tmp_path, "a.lisp", "(defun helper (x) 1)\n")
    b = _write(tmp_path, "b.lisp", "(defun helper (x) 2)\n")
    c = _write(tmp_path, "c.lisp", "(defun caller (x) (helper x))\n")
    graph = extract([a, b, c], cache_root=tmp_path, parallel=False)
    assert _call_edge(graph, "caller()", "helper()") is None


def test_standard_library_calls_produce_no_edges(tmp_path):
    """Calls into the standard library need no denylist: nothing in the corpus
    defines them, so they match no candidate. This is what keeps the graph from
    gaining a node for every CL function a program happens to call."""
    a = _write(tmp_path, "a.lisp", "(defun f (x) (car x) (format nil \"~a\" x) (mapcar #'identity x))\n")
    graph = extract([a], cache_root=tmp_path, parallel=False)
    labels = {str(n.get("label", "")).strip("()").lower() for n in graph["nodes"]}
    for stdlib in ("car", "format", "mapcar", "identity"):
        assert stdlib not in labels, f"{stdlib} must not become a node"


def test_commonlisp_resolver_registered():
    from graphify.resolver_registry import registered_resolvers
    names = {r.name for r in registered_resolvers()}
    assert "commonlisp_calls" in names
