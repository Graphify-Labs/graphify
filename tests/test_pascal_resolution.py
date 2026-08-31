"""Tests for cross-file Pascal/Delphi inherited-method-call resolution.

The per-file Pascal/Delphi extractors resolve a call to the caller's own
class, its ancestor chain, or a file-level free function -- but only within
the single file being extracted. Real Delphi/MTM-style code very commonly
splits a class across two files (a generated base class + a manual
descendant that extends it in a separate unit), so a call from the
descendant to a method it inherits from the base falls outside any one
file's own scope. graphify.pascal_resolution closes that gap as a
corpus-wide, post-extraction pass. See its module docstring for the full
rationale.

Uses static fixtures under tests/fixtures/pascal_cross_file/ rather than
pytest's tmp_path: the Pascal extractor's cross-file class lookup
(_pascal_project_root) walks UP the directory tree looking for the highest
ancestor with 2+ .pas files, to find the project root. tmp_path lives under
the shared system temp directory, which on a dev machine can easily already
contain 2+ stray .pas files at some ancestor level (other tools' scratch
files, other tests' leftover fixtures) -- the walk-up then escalates past the
test's own directory and picks up unrelated files. tests/fixtures/ has no
such siblings above it, so it is a stable project root for these tests.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract, extract_pascal

FIXTURES = Path(__file__).parent / "fixtures" / "pascal_cross_file"
BASE = FIXTURES / "BaseGadget.pas"
OTHER = FIXTURES / "OtherGadget.pas"
DERIVED = FIXTURES / "DerivedGadget.pas"


def _find_raw_call(result: dict, callee: str) -> dict | None:
    for rc in result.get("raw_calls", []):
        if rc.get("callee") == callee:
            return rc
    return None


def _labels(nodes: list[dict]) -> dict[str, str]:
    return {n["id"]: str(n.get("label", "")) for n in nodes}


def _call_edge(graph: dict, src_label: str, tgt_label: str):
    labels = _labels(graph["nodes"])
    for e in graph["edges"]:
        if e.get("relation") != "calls":
            continue
        if labels.get(e.get("source")) == src_label and labels.get(e.get("target")) == tgt_label:
            return e
    return None


def test_single_file_extraction_reports_unresolved_inherited_call():
    """Sanity check for the gap this resolver closes: the per-file extractor
    alone cannot see BaseGadget.pas while extracting DerivedGadget.pas, so it
    must NOT emit a `calls` edge for Run -> Prepare, and must report it via
    raw_calls instead of silently dropping it."""
    r = extract_pascal(DERIVED)
    assert _call_edge(r, "Run()", "Prepare()") is None
    rc = _find_raw_call(r, "prepare")
    assert rc is not None
    assert rc["caller_nid"]


def test_calls_resolve_across_files_via_inherits_chain(tmp_path):
    # cache_root only controls where graphify-out/cache/ is written -- it has
    # no bearing on the Pascal cross-file class lookup, which is keyed off
    # each source path's own project root (see module docstring). Using
    # tmp_path here just keeps cache artifacts out of the repo.
    graph = extract([BASE, DERIVED], cache_root=tmp_path, parallel=False)
    edge = _call_edge(graph, "Run()", "Prepare()")
    assert edge is not None
    assert edge.get("confidence") == "EXTRACTED"


def test_cross_file_calls_do_not_cross_unrelated_classes(tmp_path):
    """TDerivedGadget inherits only from TBaseGadget. TOtherGadget declares an
    unrelated same-named Prepare in a third file -- Run() must resolve to
    TBaseGadget.Prepare, never to TOtherGadget.Prepare."""
    graph = extract([BASE, OTHER, DERIVED], cache_root=tmp_path, parallel=False)
    edge = _call_edge(graph, "Run()", "Prepare()")
    assert edge is not None
    node_by_id = {n["id"]: n for n in graph["nodes"]}
    target = node_by_id[edge["target"]]
    assert "BaseGadget.pas" in target.get("source_file", "")
    assert "OtherGadget.pas" not in target.get("source_file", "")


def test_pascal_resolver_registered():
    from graphify.resolver_registry import registered_resolvers
    names = {r.name for r in registered_resolvers()}
    assert "pascal_inherited_calls" in names
