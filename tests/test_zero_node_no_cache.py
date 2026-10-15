"""#1666 — an extractable source file that yields zero nodes must not be cached,
and must be surfaced.

Every supported file produces at least a file node, so a zero-node result is
anomalous (a transient batch/parallel hiccup). Caching it made the empty
byte-stable across runs and silently blinded affected/explain to the file. We
now skip the cache write for a zero-node result (so a rerun self-heals) and warn.
"""
from __future__ import annotations

from pathlib import Path

import graphify.extract as ex


def test_zero_node_result_not_cached_then_self_heals(tmp_path, capsys, monkeypatch):
    f = tmp_path / "thing.rb"
    f.write_text("class Foo\n  def bar; end\nend\n")

    real = ex._safe_extract_with_xaml_root

    def _empty(extractor, path, root):
        return {"nodes": [], "edges": []}

    # First run: force a zero-node extraction for this file.
    monkeypatch.setattr(ex, "_safe_extract_with_xaml_root", _empty)
    ex.extract([f], cache_root=tmp_path / "out", parallel=False)

    err = capsys.readouterr().err
    assert "zero nodes" in err and "thing.rb" in err, err

    # Second run with the real extractor: because the empty was NOT cached, the
    # file re-extracts and lands in the graph (self-heal).
    monkeypatch.setattr(ex, "_safe_extract_with_xaml_root", real)
    r2 = ex.extract([f], cache_root=tmp_path / "out", parallel=False)
    assert any(str(n.get("source_file", "")).endswith("thing.rb") for n in r2["nodes"])


def test_normal_file_still_cached(tmp_path):
    # Guard against over-correction: a normal (non-empty) result must still cache.
    f = tmp_path / "ok.rb"
    f.write_text("class Bar\n  def baz; end\nend\n")
    r1 = ex.extract([f], cache_root=tmp_path / "out", parallel=False)
    assert r1["nodes"]
    from graphify.cache import load_cached
    assert load_cached(f, tmp_path / "out") is not None, "non-empty result should be cached"


def test_no_warning_when_all_files_produce_nodes(tmp_path, capsys):
    f = tmp_path / "fine.rb"
    f.write_text("module M\n  def self.go; end\nend\n")
    ex.extract([f], cache_root=tmp_path / "out", parallel=False)
    err = capsys.readouterr().err
    assert "zero nodes" not in err


def test_intentionally_skipped_data_json_does_not_warn(tmp_path, capsys):
    """Data-shaped JSON is deliberately excluded from the code graph, so its
    explicit ``skipped`` result must not be reported as a failed extraction that
    will retry forever."""
    f = tmp_path / "records.json"
    f.write_text('[{"id": 1}, {"id": 2}]\n', encoding="utf-8")

    result = ex.extract([f], cache_root=tmp_path / "out", parallel=False)

    assert result["nodes"] == []
    assert "zero nodes" not in capsys.readouterr().err
