"""The generated skill must scope fresh chunks before destructive update merges."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from tools.skillgen import gen

REPO_ROOT = Path(__file__).resolve().parent.parent


def _python_blocks(body: str, start: str, end: str) -> list[str]:
    section = body.split(start, 1)[1].split(end, 1)[0]
    sources = []
    for block in re.findall(r"```bash\n(.*?)```", section, re.S):
        match = re.search(r' -c "\n(.*)\n"\s*$', block, re.S)
        if match:
            sources.append(match.group(1).replace('\\"', '"'))
    return sources


@pytest.mark.parametrize("source_form", ["relative", "absolute"])
def test_generated_update_retains_undispatched_rich_nodes(tmp_path, source_form):
    """A growing graph must not hide replacement of rich foreign nodes by a stub."""
    artifacts = gen.render_all(gen.load_platforms(), only="claude")
    body = next(a.content for a in artifacts if a.path == "graphify/skill.md")
    update = next(a.content for a in artifacts
                  if a.path == "graphify/skills/claude/references/update.md")
    b3 = _python_blocks(body, "**Step B3", "#### Part C")
    part_c = _python_blocks(body, "#### Part C", "\n### ")[:1]
    merge = next(src for src in _python_blocks(update, "Then:", "Then run Steps")
                 if "G = build_merge(" in src)

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    for filename in ("fresh.md", "foreign.md", "cached.md"):
        (corpus / filename).write_text(f"# {filename}\n", encoding="utf-8")
    spec = tmp_path / "spec.md"
    spec.write_text("# Spec\n", encoding="utf-8")
    output = tmp_path / "graphify-out"
    output.mkdir()

    def node(nid, filename):
        source = str(corpus / filename) if source_form == "absolute" else filename
        return {"id": nid, "label": nid, "file_type": "document", "source_file": source}

    rich = [node(f"foreign_rich_{i}", "foreign.md") for i in range(23)]
    cached = node("cached_real", "cached.md")
    prior = build_from_json({"nodes": rich + [cached], "edges": []}, root=corpus)
    assert to_json(prior, {}, output / "graph.json")
    fresh = [node(f"fresh_{i}", "fresh.md") for i in range(35)]
    payload = {
        "nodes": fresh + [node("foreign_stub", "foreign.md")],
        "edges": [
            {"source": "fresh_0", "target": "foreign_rich_0", "relation": "references",
             "source_file": fresh[0]["source_file"], "confidence": "EXTRACTED"},
            {"source": "fresh_0", "target": "foreign_stub", "relation": "references",
             "source_file": fresh[0]["source_file"], "confidence": "INFERRED"},
        ],
        "hyperedges": [{"id": "foreign_h", "nodes": ["fresh_0", "fresh_1"],
                        "source_file": node("unused", "foreign.md")["source_file"]}],
        "input_tokens": 10, "output_tokens": 5,
    }
    files = {"document": [str(corpus / name)
                          for name in ("fresh.md", "foreign.md", "cached.md")]}
    sidecars = {
        ".graphify_chunk_01.json": payload,
        ".graphify_cached.json": {"nodes": [cached], "edges": [], "hyperedges": []},
        ".graphify_ast.json": {"nodes": [], "edges": []},
        ".graphify_incremental.json": {"files": files, "deleted_files": [],
                                       "new_files": {"document": [str(corpus / "fresh.md")]}},
    }
    for filename, data in sidecars.items():
        (output / filename).write_text(json.dumps(data), encoding="utf-8")
    (output / ".graphify_uncached.txt").write_text(
        str(corpus / "fresh.md") + "\n", encoding="utf-8")
    logs = []
    for source in b3 + part_c + [merge]:
        source = source.replace("INPUT_PATH", corpus.as_posix()).replace(
            "SPEC_PATH", spec.as_posix()).replace("IS_DIRECTED", "False")
        result = subprocess.run(
            [sys.executable, "-c", source], cwd=tmp_path, check=True,
            capture_output=True, text=True,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        logs.append(result.stdout)

    merged = json.loads((output / ".graphify_extract.json").read_text(encoding="utf-8"))
    assert {n["id"] for n in merged["nodes"]} == {
        n["id"] for n in rich + [cached] + fresh
    }
    assert {(e["source"], e["target"]) for e in merged["edges"]} == {
        ("fresh_0", "foreign_rich_0")
    }
    assert merged["hyperedges"] == []
    fresh_result = json.loads(
        (output / ".graphify_semantic_new.json").read_text(encoding="utf-8"))
    assert {n["id"] for n in fresh_result["nodes"]} == {n["id"] for n in fresh}
    assert "foreign.md" in "".join(logs) and "out-of-scope" in "".join(logs)
