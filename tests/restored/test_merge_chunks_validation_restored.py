"""Tests that `graphify merge-chunks` validates untrusted subagent chunk JSON.

merge-chunks concatenates agent-written `.graphify_chunk_*.json` files. Those are
untrusted output, so each is run through `validate_semantic_fragment` (caps + the
node/edge ID charset that blocks path-escape). An invalid chunk is skipped with a
warning; valid chunks still merge, but an all-invalid input set fails closed.
"""
import json

import graphify.__main__ as mainmod
import pytest


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def _run_merge(monkeypatch, argv):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def test_merge_chunks_skips_chunk_with_path_escape_id(tmp_path, monkeypatch, capsys):
    good = tmp_path / ".graphify_chunk_0.json"
    _write(good, {"nodes": [{"id": "pkg.mod.good", "label": "G"}], "edges": [], "hyperedges": []})
    bad = tmp_path / ".graphify_chunk_1.json"
    # A node id with a path separator would escape the chunk directory (#825).
    _write(bad, {"nodes": [{"id": "../../etc/passwd", "label": "B"}], "edges": [], "hyperedges": []})
    out = tmp_path / "merged.json"

    _run_merge(monkeypatch, ["graphify", "merge-chunks", str(good), str(bad), "--out", str(out)])

    merged = json.loads(out.read_text())
    assert {n["id"] for n in merged["nodes"]} == {"pkg.mod.good"}
    captured = capsys.readouterr()
    assert "skipping invalid chunk" in captured.err
    assert "Merged 1 of 2 chunks" in captured.out


def test_merge_chunks_fails_closed_when_every_chunk_is_invalid(tmp_path, monkeypatch, capsys):
    bad = tmp_path / ".graphify_chunk_0.json"
    _write(bad, {"nodes": "not-a-list", "edges": []})
    out = tmp_path / "merged.json"
    out.write_text('{"previous": "semantic result"}', encoding="utf-8")

    with pytest.raises(SystemExit) as exc:
        _run_merge(monkeypatch, ["graphify", "merge-chunks", str(bad), "--out", str(out)])

    assert exc.value.code == 1
    assert json.loads(out.read_text()) == {"previous": "semantic result"}
    err = capsys.readouterr().err
    assert "skipping invalid chunk" in err
    assert "no valid chunks to merge" in err


def test_merge_chunks_accepts_valid_empty_chunk(tmp_path, monkeypatch):
    """A valid fragment may legitimately contain no entities; it still counts."""
    empty = tmp_path / ".graphify_chunk_0.json"
    _write(empty, {"nodes": [], "edges": [], "hyperedges": []})
    out = tmp_path / "merged.json"

    _run_merge(monkeypatch, ["graphify", "merge-chunks", str(empty), "--out", str(out)])

    merged = json.loads(out.read_text())
    assert merged["nodes"] == []
    assert merged["edges"] == []


def test_merge_chunks_fails_closed_without_chunk_arguments(tmp_path, monkeypatch, capsys):
    out = tmp_path / "merged.json"

    with pytest.raises(SystemExit) as exc:
        _run_merge(monkeypatch, ["graphify", "merge-chunks", "--out", str(out)])

    assert exc.value.code == 1
    assert not out.exists()
    assert "no valid chunks to merge" in capsys.readouterr().err


def test_merge_chunks_fails_closed_on_unmatched_glob(tmp_path, monkeypatch, capsys):
    out = tmp_path / "merged.json"
    out.write_text('{"previous": true}', encoding="utf-8")
    unmatched = str(tmp_path / ".graphify_chunk_*.json")

    with pytest.raises(SystemExit) as exc:
        _run_merge(monkeypatch, ["graphify", "merge-chunks", unmatched, "--out", str(out)])

    assert exc.value.code == 1
    assert json.loads(out.read_text()) == {"previous": True}
    err = capsys.readouterr().err
    assert "skipping invalid chunk" in err
    assert "no valid chunks to merge" in err


def test_merge_chunks_accepts_synonym_file_type(tmp_path, monkeypatch):
    # file_type synonyms (markdown/tool/framework/...) are coerced by build, not
    # a validation failure — the chunk must merge, not be silently dropped (#840).
    c = tmp_path / ".graphify_chunk_0.json"
    _write(c, {"nodes": [{"id": "pkg.readme", "label": "Readme", "file_type": "markdown"},
                         {"id": "pkg.tool", "label": "Tool", "file_type": "tool"}],
               "edges": [], "hyperedges": []})
    out = tmp_path / "merged.json"
    _run_merge(monkeypatch, ["graphify", "merge-chunks", str(c), "--out", str(out)])
    merged = json.loads(out.read_text())
    assert {n["id"] for n in merged["nodes"]} == {"pkg.readme", "pkg.tool"}


def test_merge_chunks_accepts_unicode_id(tmp_path, monkeypatch):
    # build's normalize_id preserves Unicode identifiers; validation must not
    # reject a chunk that uses them.
    c = tmp_path / ".graphify_chunk_0.json"
    _write(c, {"nodes": [{"id": "mod_处理数据", "label": "handler", "file_type": "code"}],
               "edges": [], "hyperedges": []})
    out = tmp_path / "merged.json"
    _run_merge(monkeypatch, ["graphify", "merge-chunks", str(c), "--out", str(out)])
    merged = json.loads(out.read_text())
    assert {n["id"] for n in merged["nodes"]} == {"mod_处理数据"}


def test_validate_semantic_fragment_accepts_synonyms_and_unicode():
    from graphify.semantic_cleanup import validate_semantic_fragment
    frag = {"nodes": [{"id": "mod_处理", "file_type": "markdown"},
                      {"id": "a.b::C.d", "file_type": "tool"}],
            "edges": [], "hyperedges": []}
    assert validate_semantic_fragment(frag) == []


def test_validate_semantic_fragment_still_blocks_path_escape():
    from graphify.semantic_cleanup import validate_semantic_fragment
    errs = validate_semantic_fragment({"nodes": [{"id": "../../etc/passwd"}],
                                       "edges": [], "hyperedges": []})
    assert errs


def test_merge_chunks_merges_valid_chunks(tmp_path, monkeypatch):
    c0 = tmp_path / ".graphify_chunk_0.json"
    _write(c0, {"nodes": [{"id": "a", "label": "A"}], "edges": [], "hyperedges": [],
               "input_tokens": 10, "output_tokens": 5})
    c1 = tmp_path / ".graphify_chunk_1.json"
    _write(c1, {"nodes": [{"id": "b", "label": "B"}], "edges": [], "hyperedges": [],
               "input_tokens": 7, "output_tokens": 3})
    out = tmp_path / "merged.json"

    _run_merge(monkeypatch, ["graphify", "merge-chunks", str(c0), str(c1), "--out", str(out)])

    merged = json.loads(out.read_text())
    assert {n["id"] for n in merged["nodes"]} == {"a", "b"}
    assert merged["input_tokens"] == 17
    assert merged["output_tokens"] == 8
