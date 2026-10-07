"""A semantic run where every doc/paper/image hits the cache must still reach
Part C with its cached nodes.

Part C reads ``graphify-out/.graphify_semantic.json`` unconditionally, and the
only Part B step that writes it is the Step B3 merge. A body that routes the
all-cached case straight to Part C crashes there with ``FileNotFoundError``;
working around that with an empty file drops every cached node. Running B3 with
no new chunks also means a ``.graphify_chunk_*.json`` left by an interrupted run
would be merged as if it were fresh, so Step B0 must clear those before dispatch.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.cache import save_semantic_cache  # noqa: E402
from tools.skillgen import gen  # noqa: E402

_ROUTING_PREFIX = "Only dispatch subagents for files listed in"


def _split_host_bodies():
    arts = gen.render_all(gen.load_platforms())
    bodies = [a for a in arts
              if "check_semantic_cache(" in a.content
              and "references/extraction-spec.md" in a.content]
    assert bodies, "no rendered split-host skill body runs the semantic cache check"
    return bodies


def test_all_cached_run_is_routed_through_the_b3_merge():
    for a in _split_host_bodies():
        routing = next(ln for ln in a.content.splitlines() if ln.startswith(_ROUTING_PREFIX))
        assert "skip to Part C directly" not in routing, a.path
        assert "still run Step B3" in routing, a.path


def _python_blocks(body: str, start: str, end: str) -> list[str]:
    section = body.split(start, 1)[1].split(end, 1)[0]
    sources = []
    for block in re.findall(r"```bash\n(.*?)```", section, re.S):
        m = re.search(r' -c "\n(.*)\n"\s*$', block, re.S)
        if m:
            sources.append(m.group(1).replace('\\"', '"'))
    return sources


def test_all_cached_run_reaches_part_c_with_cached_nodes_and_no_stale_chunks(tmp_path):
    platforms = gen.load_platforms()
    body = next(a.content for a in gen.render_all(platforms, only="claude")
                if a.path == "graphify/skill.md")
    b0 = _python_blocks(body, "**Step B0", "**Step B1")
    b3 = _python_blocks(body, "**Step B3", "#### Part C")
    part_c = _python_blocks(body, "#### Part C", "\n### ")[:1]
    assert len(b0) == 1 and len(b3) == 3 and len(part_c) == 1

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    doc = corpus / "notes.md"
    doc.write_text("# Notes\nCached content.\n", encoding="utf-8")
    spec = tmp_path / "extraction-spec.md"
    spec.write_text("# spec\n", encoding="utf-8")
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / ".graphify_detect.json").write_text(
        json.dumps({"files": {"document": [doc.as_posix()]}}), encoding="utf-8")
    (out / ".graphify_ast.json").write_text(
        json.dumps({"nodes": [{"id": "ast_node", "label": "a", "source_file": "a.py"}],
                    "edges": []}), encoding="utf-8")
    save_semantic_cache(
        [{"id": "cached_node", "label": "Notes", "source_file": doc.as_posix()}], [], [],
        root=corpus, prompt_file=spec)
    (out / ".graphify_chunk_01.json").write_text(
        json.dumps({"nodes": [{"id": "stale_node", "label": "old", "source_file": "x.md"}],
                    "edges": []}), encoding="utf-8")

    for src in b0 + b3 + part_c:
        src = src.replace("INPUT_PATH", corpus.as_posix()).replace("SPEC_PATH", spec.as_posix())
        subprocess.run([sys.executable, "-c", src], cwd=tmp_path, check=True,
                       capture_output=True, text=True)

    extract = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    ids = {n["id"] for n in extract["nodes"]}
    assert {"ast_node", "cached_node"} <= ids
    assert "stale_node" not in ids
