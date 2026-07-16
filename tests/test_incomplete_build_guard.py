"""Tests for the incomplete-build shrink-guard on `graphify extract`.

A full build writes the graph with `to_json(..., force=True)`, which bypasses the
#479 shrink guard. When this run's extraction was incomplete (an AST pass crashed
or some semantic chunks failed), forcing the write can silently overwrite a good
complete graph with a smaller partial one. The build now drops back to the shrink
guard (force=False) on an incomplete run — unless `--allow-partial` is passed —
and exits non-zero (before writing the manifest) if the guard refuses.
"""
from __future__ import annotations

import pytest

import graphify.__main__ as mainmod


def _make_docs_corpus(tmp_path):
    # Docs-only corpus: no code files, so AST extraction is skipped and the only
    # driver of incompleteness is the (stubbed) semantic chunk run.
    (tmp_path / "README.md").write_text("# Notes\nThe entry point overview.\n")
    (tmp_path / "GUIDE.md").write_text("# Guide\nHow to use the thing.\n")
    return tmp_path


def _seed_to_json_recorder(monkeypatch, *, returns=True):
    """Patch export.to_json to record the ``force`` it was called with and return
    a fixed bool (True = wrote, False = shrink guard refused)."""
    rec = {"called": False, "force": None}

    def _stub(G, communities, output_path, *, force=False, **kwargs):
        rec["called"] = True
        rec["force"] = force
        return returns

    monkeypatch.setattr("graphify.export.to_json", _stub)
    return rec


def _arm_extract(monkeypatch, tmp_path, *, chunk_total, chunk_succeeded, extra_argv=()):
    corpus = _make_docs_corpus(tmp_path)
    out_dir = tmp_path / "out"
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _stub_corpus(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            for i in range(chunk_succeeded):
                on_chunk(i, chunk_total, {"nodes": [], "edges": [], "hyperedges": []})
        return {
            "nodes": [{"id": "s1", "source_file": str(corpus / "README.md"),
                       "file_type": "document", "label": "Notes"}],
            "edges": [], "hyperedges": [], "input_tokens": 10, "output_tokens": 5,
        }

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub_corpus)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude",
         "--out", str(out_dir), *extra_argv],
    )
    return out_dir


def test_partial_extraction_refuses_to_shrink_existing_graph(monkeypatch, tmp_path, capsys):
    # 1 of 3 chunks succeeded -> incomplete; the shrink guard refuses (returns False).
    rec = _seed_to_json_recorder(monkeypatch, returns=False)
    out_dir = _arm_extract(monkeypatch, tmp_path, chunk_total=3, chunk_succeeded=1)

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    assert rec["called"] and rec["force"] is False, "incomplete build must not force the write"
    err = capsys.readouterr().err
    assert "Refusing to overwrite" in err
    # The manifest must not be stamped for a graph we declined to write.
    assert not (out_dir / "graphify-out" / "manifest.json").exists()


def test_partial_extraction_writes_when_not_shrinking(monkeypatch, tmp_path):
    # Incomplete run, but the new graph is not smaller -> the guard permits the
    # write. force is still False (guard active), and the CLI does not exit 1.
    rec = _seed_to_json_recorder(monkeypatch, returns=True)
    _arm_extract(monkeypatch, tmp_path, chunk_total=3, chunk_succeeded=1)

    mainmod.main()  # no SystemExit

    assert rec["called"] and rec["force"] is False


def test_allow_partial_forces_write_despite_incomplete(monkeypatch, tmp_path):
    rec = _seed_to_json_recorder(monkeypatch, returns=True)
    _arm_extract(monkeypatch, tmp_path, chunk_total=3, chunk_succeeded=1,
                 extra_argv=["--allow-partial"])

    mainmod.main()

    assert rec["called"] and rec["force"] is True, "--allow-partial must restore force=True"


def test_complete_extraction_keeps_force_write(monkeypatch, tmp_path):
    # All chunks succeeded -> a complete build legitimately keeps force=True so a
    # genuine dedup/deletion shrink still overwrites.
    rec = _seed_to_json_recorder(monkeypatch, returns=True)
    _arm_extract(monkeypatch, tmp_path, chunk_total=1, chunk_succeeded=1)

    mainmod.main()

    assert rec["called"] and rec["force"] is True


def _seed_existing_graph(gout, n):
    import json
    gout.mkdir(parents=True, exist_ok=True)
    (gout / "graph.json").write_text(
        json.dumps({"nodes": [{"id": f"keep{i}", "label": f"k{i}"} for i in range(n)],
                    "links": []}),
        encoding="utf-8",
    )


def _arm_no_cluster(monkeypatch, tmp_path, *, extra_argv=()):
    corpus = _make_docs_corpus(tmp_path)
    out_dir = tmp_path / "out"
    gout = out_dir / "graphify-out"
    _seed_existing_graph(gout, 5)  # existing complete graph
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test-fake-key")

    def _stub_corpus(paths, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        if on_chunk:
            on_chunk(0, 3, {"nodes": [], "edges": [], "hyperedges": []})  # 1 of 3 -> partial
        return {"nodes": [{"id": "s1", "source_file": str(corpus / "README.md"),
                           "file_type": "document", "label": "Notes"}],
                "edges": [], "hyperedges": [], "input_tokens": 1, "output_tokens": 1}

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _stub_corpus)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--no-cluster",
         "--out", str(out_dir), *extra_argv],
    )
    return gout / "graph.json"


def test_no_cluster_incomplete_build_refuses_to_shrink(tmp_path, monkeypatch, capsys):
    import json
    graph = _arm_no_cluster(monkeypatch, tmp_path)

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 1
    assert "Refusing to overwrite" in capsys.readouterr().err
    # The existing 5-node graph is untouched — the partial 1-node graph was refused.
    assert len(json.loads(graph.read_text())["nodes"]) == 5


def test_no_cluster_allow_partial_overwrites(tmp_path, monkeypatch):
    import json
    graph = _arm_no_cluster(monkeypatch, tmp_path, extra_argv=["--allow-partial"])

    with pytest.raises(SystemExit) as exc:
        mainmod.main()

    assert exc.value.code == 0  # the raw --no-cluster path exits 0 on success
    assert len(json.loads(graph.read_text())["nodes"]) == 1
