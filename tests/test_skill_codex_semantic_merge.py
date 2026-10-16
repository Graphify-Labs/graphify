"""Regression coverage for Codex's in-memory B2 results and shared B3 merge.

With #197 the B0/B3/Part C blocks are ``graphify pipeline`` subcommands, not
inline ``python -c``. This exercises the step functions those commands dispatch
to (``graphify.pipeline``), so the behaviour the old blocks proved is preserved.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify import pipeline as pl
from tools.skillgen import gen


def _codex_skill() -> str:
    artifacts = gen.render_all(gen.load_platforms(), only="codex")
    return next(a.content for a in artifacts if a.path == "graphify/skill-codex.md")


def test_codex_b2_persists_each_result_and_fails_closed():
    skill = _codex_skill()
    b2 = skill.split("**Step B2", 1)[1].split("**Step B3", 1)[0]

    assert "write each result to its matching" in b2
    assert "graphify-out/.graphify_chunk_NN.json" in b2
    assert "Do not aggregate results or write `graphify-out/.graphify_semantic_new.json` in B2" in b2
    assert "If any subagent fails, returns no result or invalid JSON" in b2
    assert "stop before Step B3" in b2
    assert "save cache" in b2
    assert "leave the existing graph and semantic cache untouched" in b2
    assert "read back from its expected chunk file" in b2
    assert "Empty lists are valid extraction results" in b2


def test_codex_b0_b3_part_c_are_pipeline_commands():
    """The conversion target: B0/B3/Part C call the pipeline, no inline Python."""
    skill = _codex_skill()
    b0 = skill.split("**Step B0", 1)[1].split("**Step B1", 1)[0]
    b3 = skill.split("**Step B3", 1)[1].split("#### Part C", 1)[0]
    part_c = skill.split("#### Part C", 1)[1].split("\n### ", 1)[0]

    assert "graphify pipeline cache-check" in b0
    assert b3.count("graphify pipeline") == 3  # merge-chunks, save-cache, merge-semantic
    assert "graphify pipeline merge-extraction" in part_c
    assert " -c \"" not in b0 + b3 + part_c


def test_codex_chunk_results_survive_b3_merge_cache_and_all_cached_rerun(tmp_path):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    docs = [corpus / "one.md", corpus / "two.md"]
    for doc in docs:
        doc.write_text("semantic source", encoding="utf-8")
    spec = tmp_path / "extraction-spec.md"
    spec.write_text("# extraction spec\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_detect.json").write_text(
        json.dumps({"files": {"document": [doc.as_posix() for doc in docs]}}),
        encoding="utf-8",
    )
    (out / ".graphify_ast.json").write_text(
        json.dumps({"nodes": [{"id": "ast_node", "label": "AST"}], "edges": []}),
        encoding="utf-8",
    )

    # B0 prepares this run (the cache-check command clears stale chunks too).
    pl.step_cache_check(corpus, out=tmp_path, prompt_file=spec)
    chunks = [
        {
            "nodes": [{"id": "semantic_one", "label": "One", "source_file": docs[0].as_posix()}],
            "edges": [{"source": "semantic_one", "target": "semantic_two", "relation": "references"}],
            "hyperedges": [],
            "input_tokens": 11,
            "output_tokens": 5,
        },
        {
            "nodes": [{"id": "semantic_two", "label": "Two", "source_file": docs[1].as_posix()}],
            "edges": [],
            "hyperedges": [],
            "input_tokens": 13,
            "output_tokens": 7,
        },
    ]
    for index, chunk in enumerate(chunks, start=1):
        (out / f".graphify_chunk_{index:02}.json").write_text(
            json.dumps(chunk), encoding="utf-8")

    # B3: merge-chunks -> save-cache -> merge-semantic; Part C: merge-extraction.
    _run_b3_and_part_c(corpus, tmp_path, spec)

    semantic = json.loads((out / ".graphify_semantic.json").read_text(encoding="utf-8"))
    assert {node["id"] for node in semantic["nodes"]} == {"semantic_one", "semantic_two"}
    assert semantic["edges"] == chunks[0]["edges"]
    assert semantic["input_tokens"] == 24
    assert semantic["output_tokens"] == 12
    extraction = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    assert {node["id"] for node in extraction["nodes"]} == {
        "ast_node", "semantic_one", "semantic_two"
    }

    # Cache writes from B3 must serve the next run without B2, while B0 removes
    # any chunks left by the preceding run before the empty B3 merge.
    pl.step_cache_check(corpus, out=tmp_path, prompt_file=spec)
    _run_b3_and_part_c(corpus, tmp_path, spec)
    assert not list(out.glob(".graphify_chunk_*.json"))
    extraction = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    assert {node["id"] for node in extraction["nodes"]} == {
        "ast_node", "semantic_one", "semantic_two"
    }


def _run_b3_and_part_c(corpus: Path, out_root: Path, spec: Path) -> None:
    """The three B3 subcommands plus Part C, as the skill issues them."""
    pl.step_merge_chunks(out=out_root)
    pl.step_save_cache(corpus, out=out_root, prompt_file=spec)
    pl.step_merge_semantic(out=out_root)
    pl.step_merge_extraction(out=out_root)
