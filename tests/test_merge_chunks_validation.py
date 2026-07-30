"""Tests that `graphify merge-chunks` validates untrusted subagent chunk JSON.

merge-chunks concatenates agent-written `.graphify_chunk_*.json` files. Those are
untrusted output, so each is run through `validate_semantic_fragment` (caps + the
node/edge ID charset that blocks path-escape). An invalid chunk is skipped with a
warning; valid chunks still merge, but an all-invalid input set fails closed.
"""
import json
import hashlib
from pathlib import Path

import graphify.__main__ as mainmod
import pytest
from graphify.semantic_cleanup import snapshot_semantic_sources


def _write(path, obj):
    path.write_text(json.dumps(obj), encoding="utf-8")


def _run_merge(monkeypatch, argv):
    out_path = Path(argv[argv.index("--out") + 1])
    source = out_path.parent / "semantic-source.md"
    source.write_text("source evidence\n", encoding="utf-8")
    manifest = out_path.parent / "semantic-source-manifest.json"
    manifest.write_text(
        json.dumps(snapshot_semantic_sources([str(source)], out_path.parent)),
        encoding="utf-8",
    )
    provenance = {"source_file": str(source), "source_location": "L1"}
    for value in argv[2:argv.index("--out")]:
        chunk_path = Path(value)
        if not chunk_path.is_file():
            continue
        try:
            fragment = json.loads(chunk_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            continue
        if isinstance(fragment, dict):
            for node in fragment.get("nodes", []) if isinstance(fragment.get("nodes", []), list) else []:
                if isinstance(node, dict):
                    node.update(provenance)
            for edge in fragment.get("edges", []) if isinstance(fragment.get("edges", []), list) else []:
                if isinstance(edge, dict):
                    edge.setdefault("relation", "references")
                    edge.update(provenance)
            hyperedges = fragment.get("hyperedges", [])
            for hyperedge in hyperedges if isinstance(hyperedges, list) else []:
                if isinstance(hyperedge, dict):
                    hyperedge.setdefault("relation", "participate_in")
                    hyperedge.update(provenance)
            chunk_path.write_text(json.dumps(fragment), encoding="utf-8")
    argv = [
        *argv[:argv.index("--out")],
        "--source-manifest",
        str(manifest),
        "--manifest-sha256",
        hashlib.sha256(manifest.read_bytes()).hexdigest(),
        *argv[argv.index("--out"):],
    ]
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def test_merge_chunks_rejects_batch_with_path_escape_id(tmp_path, monkeypatch, capsys):
    good = tmp_path / ".graphify_chunk_0.json"
    _write(good, {"nodes": [{"id": "pkg.mod.good", "label": "G"}], "edges": [], "hyperedges": []})
    bad = tmp_path / ".graphify_chunk_1.json"
    # A node id with a path separator would escape the chunk directory (#825).
    _write(bad, {"nodes": [{"id": "../../etc/passwd", "label": "B"}], "edges": [], "hyperedges": []})
    out = tmp_path / "merged.json"

    with pytest.raises(SystemExit) as exc:
        _run_merge(
            monkeypatch,
            ["graphify", "merge-chunks", str(good), str(bad), "--out", str(out)],
        )

    assert exc.value.code == 1
    assert not out.exists()
    captured = capsys.readouterr()
    assert "invalid chunk" in captured.err
    assert "refusing to merge or write" in captured.err


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
    assert "invalid chunk" in err
    assert "refusing to merge or write" in err


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
    assert "invalid chunk" in err
    assert "refusing to merge or write" in err


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


def test_merge_chunks_sanitizes_validated_rationale_records(tmp_path, monkeypatch):
    c = tmp_path / ".graphify_chunk_0.json"
    sentence = (
        "This deliberately long rationale sentence explains why the documented "
        "decision was selected over the available alternatives."
    )
    _write(
        c,
        {
            "nodes": [
                {"id": "decision", "label": "Decision", "file_type": "document"},
                {"id": "why", "label": sentence, "file_type": "rationale"},
            ],
            "edges": [
                {"source": "why", "target": "decision", "relation": "rationale_for"}
            ],
            "hyperedges": [],
        },
    )
    out = tmp_path / "merged.json"

    _run_merge(monkeypatch, ["graphify", "merge-chunks", str(c), "--out", str(out)])

    merged = json.loads(out.read_text())
    assert [node["id"] for node in merged["nodes"]] == ["decision"]
    assert merged["nodes"][0]["rationale"] == sentence
    assert merged["edges"] == []


def test_merge_chunks_rejects_output_that_is_a_manifested_source(
    tmp_path, monkeypatch, capsys
):
    source = tmp_path / "semantic-source.md"
    source.write_text("source evidence\n", encoding="utf-8")
    chunk = tmp_path / ".graphify_chunk_0.json"
    _write(
        chunk,
        {
            "nodes": [
                {
                    "id": "evidence",
                    "label": "Evidence",
                    "source_file": str(source),
                    "source_location": "L1",
                }
            ],
            "edges": [],
            "hyperedges": [],
        },
    )

    with pytest.raises(SystemExit) as exc:
        _run_merge(
            monkeypatch,
            ["graphify", "merge-chunks", str(chunk), "--out", str(source)],
        )

    assert exc.value.code == 1
    assert source.read_text(encoding="utf-8") == "source evidence\n"
    assert "output path is a provenance source" in capsys.readouterr().err
