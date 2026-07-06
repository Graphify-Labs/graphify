"""Corrupt graph.json produces an actionable error, not a raw traceback (#1536/#1537).

Three load paths call json.loads on graph.json — build_merge (`--update`),
affected.load_graph (`graphify prs`), and diagnostics._read_json_file
(`graphify diagnose`). A truncated / invalid file (incomplete write, power loss,
manual edit) must raise a clear RuntimeError with recovery guidance at each.
"""
from __future__ import annotations

import pytest

from graphify.build import build_merge
from graphify.affected import load_graph
from graphify.diagnostics import _read_json_file

_CORRUPT = '{"nodes": [{"id": "a", "labe'   # truncated mid-object


def _corrupt(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text(_CORRUPT, encoding="utf-8")
    return p


def test_build_merge_corrupt_graph_raises_runtimeerror(tmp_path):
    p = _corrupt(tmp_path)
    with pytest.raises(RuntimeError, match=r"Cannot read .*incremental merge|rebuild"):
        build_merge([], graph_path=p, dedup=False)


def test_affected_load_graph_corrupt_raises_runtimeerror(tmp_path):
    p = _corrupt(tmp_path)
    with pytest.raises(RuntimeError, match=r"Cannot read graph file|regenerate"):
        load_graph(p)


def test_diagnostics_read_corrupt_raises_runtimeerror(tmp_path):
    p = _corrupt(tmp_path)
    with pytest.raises(RuntimeError, match=r"Cannot parse|corrupted"):
        _read_json_file(p)


def test_valid_graph_still_loads(tmp_path):
    """Happy path unchanged: a well-formed graph.json loads without raising."""
    p = tmp_path / "graph.json"
    p.write_text(
        '{"nodes": [{"id": "a", "label": "a", "file_type": "code"}], "edges": []}',
        encoding="utf-8",
    )
    # none of these should raise
    load_graph(p)
    _read_json_file(p)
    build_merge([], graph_path=p, dedup=False)
