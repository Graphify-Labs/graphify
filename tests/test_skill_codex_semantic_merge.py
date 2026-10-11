"""Regression coverage for Codex's in-memory B2 results and shared B3 merge."""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

from tools.skillgen import gen


def _codex_skill() -> str:
    artifacts = gen.render_all(gen.load_platforms(), only="codex")
    return next(a.content for a in artifacts if a.path == "graphify/skill-codex.md")


def _python_blocks(body: str, start: str, end: str) -> list[str]:
    section = body.split(start, 1)[1].split(end, 1)[0]
    sources = []
    for block in re.findall(r"```bash\n(.*?)```", section, re.S):
        match = re.search(r' -c "\n(.*)\n"\s*$', block, re.S)
        if match:
            sources.append(match.group(1).replace('\\"', '"'))
    return sources


def _run(source: str, *, cwd: Path, corpus: Path, spec: Path) -> None:
    source = source.replace("INPUT_PATH", corpus.as_posix()).replace("SPEC_PATH", spec.as_posix())
    subprocess.run([sys.executable, "-c", source], cwd=cwd, check=True,
                   capture_output=True, text=True)


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


def test_codex_chunk_results_survive_b3_merge_cache_and_all_cached_rerun(tmp_path):
    skill = _codex_skill()
    b0 = _python_blocks(skill, "**Step B0", "**Step B1")
    b3 = _python_blocks(skill, "**Step B3", "#### Part C")
    part_c = _python_blocks(skill, "#### Part C", "\n### ")[:1]
    assert len(b0) == 1 and len(b3) == 3 and len(part_c) == 1

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

    # B0 prepares this run. Codex has each successful in-memory response written
    # to its own chunk file before the shared B3 merge consumes the files.
    _run(b0[0], cwd=tmp_path, corpus=corpus, spec=spec)
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

    for source in b3 + part_c:
        _run(source, cwd=tmp_path, corpus=corpus, spec=spec)

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
    for source in b0 + b3 + part_c:
        _run(source, cwd=tmp_path, corpus=corpus, spec=spec)
    assert not list(out.glob(".graphify_chunk_*.json"))
    extraction = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    assert {node["id"] for node in extraction["nodes"]} == {
        "ast_node", "semantic_one", "semantic_two"
    }
