"""Corrupt graph.json produces an actionable error, not a raw traceback (#1536/#1537).

With the FalkorDB backend the graph lives in the engine, so most former
json.loads callers no longer touch graph.json at all: `build_merge` reads its
base from the store, and `affected.connect_graph` opens a store connection. Two
paths still parse the file and so still need the guarantee:

  * ``diagnostics._read_json_file``  (``graphify diagnose``)
  * ``serve._import_graph_json_into_store`` — the one-time back-compat import of
    a pre-FalkorDB / ``--no-cluster`` graph.json.

A truncated / invalid file (incomplete write, power loss, manual edit) must
produce a clear, actionable error at each — never a raw traceback.
"""
from __future__ import annotations

import pytest

from graphify.diagnostics import _read_json_file
from graphify.serve import _connect_graph, _import_graph_json_into_store

_CORRUPT = '{"nodes": [{"id": "a", "labe'   # truncated mid-object


def _corrupt(tmp_path):
    p = tmp_path / "graph.json"
    p.write_text(_CORRUPT, encoding="utf-8")
    return p


def test_diagnostics_read_corrupt_raises_runtimeerror(tmp_path):
    p = _corrupt(tmp_path)
    with pytest.raises(RuntimeError, match=r"Cannot parse|corrupted"):
        _read_json_file(p)


def test_backcompat_import_of_corrupt_json_reports_no_graph(monkeypatch, tmp_path, capsys, _require_falkordb):
    """A corrupt graph.json must not surface as a JSONDecodeError traceback.

    The import declines the file, so the caller falls through to the ordinary
    "no graph built" guidance — actionable, not a stack trace (#1536/#1537).
    """
    p = _corrupt(tmp_path)
    with pytest.raises(SystemExit):
        _connect_graph(str(p))
    err = capsys.readouterr().err
    assert "No graph found" in err
    assert "Re-run /graphify" in err


def test_valid_graph_still_imports(tmp_path, _require_falkordb):
    """Happy path unchanged: a well-formed graph.json loads without raising."""
    p = tmp_path / "graph.json"
    p.write_text(
        '{"nodes": [{"id": "a", "label": "a", "file_type": "code"}], "edges": []}',
        encoding="utf-8",
    )
    _read_json_file(p)
    G = _connect_graph(str(p))
    assert G.number_of_nodes() == 1


def test_import_helper_declines_corrupt_file(tmp_path, store):
    """The import helper itself returns False rather than raising, so a corrupt
    file can never abort a connect with a decode traceback."""
    assert _import_graph_json_into_store(_corrupt(tmp_path), store) is False
