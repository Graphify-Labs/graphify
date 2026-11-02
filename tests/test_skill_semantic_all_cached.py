"""A semantic run where every doc/paper/image hits the cache must still reach
Part C with its cached nodes.

Part C reads ``graphify-out/.graphify_semantic.json`` unconditionally, and the
only Part B step that writes it is the B3 merge. A body that routes the
all-cached case straight to Part C crashes there with ``FileNotFoundError``;
working around that with an empty file drops every cached node. Running B3 with
no new chunks also means a ``.graphify_chunk_*.json`` left by an interrupted run
would be merged as if it were fresh, so the cache-check step must clear those
before dispatch.

These flows used to be inline ``python -c`` blocks; with #197 they are
``graphify pipeline cache-check`` / ``merge-semantic`` / ``merge-extraction``, so
the test drives the real subcommands and checks the same invariants.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.cache import save_semantic_cache  # noqa: E402
from tools.skillgen import gen  # noqa: E402

_ROUTING_PREFIX = "Only dispatch subagents for files listed in"


def _gx(*args: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _split_host_bodies():
    arts = gen.render_all(gen.load_platforms())
    bodies = [a for a in arts
              if "graphify pipeline cache-check" in a.content
              and "references/extraction-spec.md" in a.content]
    assert bodies, "no rendered split-host skill body runs the semantic cache check"
    return bodies


def test_all_cached_run_is_routed_through_the_b3_merge():
    for a in _split_host_bodies():
        routing = next(ln for ln in a.content.splitlines() if ln.startswith(_ROUTING_PREFIX))
        assert "skip to Part C directly" not in routing, a.path
        assert "still run Step B3" in routing, a.path


def test_all_cached_run_reaches_part_c_with_cached_nodes_and_no_stale_chunks(tmp_path):
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

    # B0: cache-check clears the stale chunk and finds the cached hit.
    p = _gx("pipeline", "cache-check", str(corpus), "--prompt-file", str(spec), cwd=tmp_path)
    assert p.returncode == 0, p.stderr
    assert not (out / ".graphify_chunk_01.json").exists(), "stale chunk must be cleared"
    uncached = (out / ".graphify_uncached.txt").read_text(encoding="utf-8")
    assert uncached.strip() == "", "every file is cached, so nothing is uncached"

    # Every file cached => skip B1/B2 and merge-chunks; go straight to the merge.
    assert _gx("pipeline", "merge-semantic", cwd=tmp_path).returncode == 0
    assert _gx("pipeline", "merge-extraction", cwd=tmp_path).returncode == 0

    extract = json.loads((out / ".graphify_extract.json").read_text(encoding="utf-8"))
    ids = {n["id"] for n in extract["nodes"]}
    assert {"ast_node", "cached_node"} <= ids
    assert "stale_node" not in ids
