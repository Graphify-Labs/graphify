"""Regression coverage for the generated code-only incremental update workflow.

The Codex runbook skips semantic extraction for code-only updates, but its shared
incremental merge still consumes ``.graphify_extract.json``. Exercise the actual
rendered workflow with a clean intermediate directory so this contract cannot
drift again.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402


def _artifact(artifact_path: str) -> str:
    artifacts = gen.render_all(gen.load_platforms(), only="codex")
    return next(artifact.content for artifact in artifacts if artifact.path == artifact_path)


def _python_blocks(section: str) -> list[str]:
    sources = []
    for block in re.findall(r"```bash\n(.*?)```", section, re.S):
        match = re.search(r' -c "\n(.*)\n"\s*$', block, re.S)
        if match:
            sources.append(match.group(1).replace('\\"', '"'))
    return sources


def _section(body: str, start: str, end: str) -> str:
    return body.split(start, 1)[1].split(end, 1)[0]


def _run_code(script: str, *, cwd: Path, root: Path) -> subprocess.CompletedProcess[str]:
    script = script.replace("INPUT_PATH", root.as_posix()).replace("IS_DIRECTED", "False")
    env = {
        **os.environ,
        "GRAPHIFY_OUT": "graphify-out",
        "PYTHONPATH": str(REPO_ROOT),
    }
    return subprocess.run(
        [sys.executable, "-c", script],
        cwd=cwd,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )


def test_codex_code_only_update_materializes_and_merges_fresh_ast(tmp_path: Path):
    update = _artifact("graphify/skills/codex/references/update.md")
    core = _artifact("graphify/skill-codex.md")
    code_only_route = _section(update, "If `code_only` is True:", "If `code_only` is False")
    mixed_route = _section(update, "If `code_only` is False", "If no new files exist")

    # A code-only update skips semantic extraction, but it must still overwrite
    # any stale semantic sidecar and run Part C before the shared disk merge.
    assert ".graphify_semantic.json" in code_only_route
    assert ".graphify_extract.json" in code_only_route
    assert "empty" in code_only_route.lower()
    assert "Part C" in code_only_route
    assert "skip semantic cache checks/writes and subagents" in code_only_route.lower()
    assert "if new_total == 0 and not deleted:" in update
    assert "run the full Steps 3A–3C pipeline as normal" in mixed_route

    ast_blocks = _python_blocks(_section(
        core,
        "#### Part A - Structural extraction for code files",
        "#### Part B - Semantic extraction",
    ))
    empty_semantic_blocks = _python_blocks(_section(core, "**Fast path:**", "**MANDATORY"))
    part_c_blocks = _python_blocks(_section(
        core,
        "#### Part C - Merge AST + semantic into final extraction",
        "### Step 4 - Build graph",
    ))
    merge_blocks = [
        source for source in _python_blocks(update)
        if "from graphify.build import build_merge" in source
    ]
    assert len(ast_blocks) == 1
    assert len(empty_semantic_blocks) == 1
    assert len(part_c_blocks) == 1
    assert len(merge_blocks) == 1

    root = tmp_path
    changed = root / "changed.py"
    changed.write_text("def replacement():\n    return 2\n", encoding="utf-8")
    added = root / "added.py"
    added.write_text("def added_symbol():\n    return 3\n", encoding="utf-8")
    notes = root / "notes.md"
    notes.write_text("# Existing semantic source\n", encoding="utf-8")
    deleted = root / "deleted.py"
    out = tmp_path / "graphify-out"
    out.mkdir()

    # Normal cleanup leaves no final extraction. Seed a stale semantic sidecar
    # to ensure the fast path replaces it rather than carrying it into Part C.
    extraction_path = out / ".graphify_extract.json"
    semantic_path = out / ".graphify_semantic.json"
    assert not extraction_path.exists()
    semantic_path.write_text(json.dumps({
        "nodes": [{"id": "stale_semantic", "label": "stale"}],
        "edges": [],
        "hyperedges": [],
    }), encoding="utf-8")
    (out / ".graphify_detect.json").write_text(json.dumps({
        "files": {"code": [str(changed), str(added)]},
    }), encoding="utf-8")

    # Preserve a real semantic-cache entry across this AST-only update. The
    # code-only route must not read or rewrite semantic cache state.
    cache_seed = """
import os
from pathlib import Path
from graphify.cache import save_semantic_cache

root = Path(os.environ["GRAPHIFY_TEST_ROOT"])
saved = save_semantic_cache(
    [{"id": "cached_notes", "label": "cached", "source_file": str(root / "notes.md")}],
    [], [], root=root,
)
assert saved == 1
"""
    cache_env = {
        **os.environ,
        "GRAPHIFY_OUT": "graphify-out",
        "GRAPHIFY_TEST_ROOT": str(root),
        "PYTHONPATH": str(REPO_ROOT),
    }
    subprocess.run(
        [sys.executable, "-c", cache_seed],
        cwd=tmp_path,
        env=cache_env,
        check=True,
        capture_output=True,
        text=True,
    )
    semantic_cache = out / "cache" / "semantic"
    cache_before = {
        path.relative_to(semantic_cache).as_posix(): path.read_bytes()
        for path in semantic_cache.rglob("*") if path.is_file()
    }

    graph_path = out / "graph.json"
    graph_path.write_text(json.dumps({
        "nodes": [
            {"id": "old_changed", "label": "old function", "source_file": "changed.py",
             "source_location": "L1", "_origin": "ast"},
            {"id": "changed_summary", "label": "summary", "source_file": "changed.py",
             "source_location": None},
            {"id": "old_deleted", "label": "deleted function", "source_file": "deleted.py",
             "source_location": "L1", "_origin": "ast"},
            {"id": "old_unchanged", "label": "untouched", "source_file": "keep.py",
             "source_location": "L1", "_origin": "ast"},
            {"id": "notes_summary", "label": "notes", "source_file": "notes.md",
             "source_location": None},
        ],
        "edges": [
            {"source": "old_changed", "target": "old_deleted", "relation": "calls",
             "source_file": "changed.py", "source_location": "L1", "_origin": "ast"},
            {"source": "notes_summary", "target": "changed_summary", "relation": "references",
             "source_file": "notes.md"},
            {"source": "old_deleted", "target": "old_unchanged", "relation": "calls",
             "source_file": "deleted.py", "source_location": "L1", "_origin": "ast"},
        ],
        "hyperedges": [],
    }), encoding="utf-8")
    (out / ".graphify_incremental.json").write_text(json.dumps({
        "deleted_files": [str(deleted)],
        "new_files": {"code": [str(changed), str(added)]},
        "files": {"code": [str(changed), str(added)], "document": [str(notes)]},
    }), encoding="utf-8")

    _run_code(ast_blocks[0], cwd=tmp_path, root=root)
    _run_code(empty_semantic_blocks[0], cwd=tmp_path, root=root)
    semantic = json.loads(semantic_path.read_text(encoding="utf-8"))
    assert semantic["nodes"] == []
    _run_code(part_c_blocks[0], cwd=tmp_path, root=root)

    extraction = json.loads(extraction_path.read_text(encoding="utf-8"))
    extraction_ids = {node["id"] for node in extraction["nodes"]}
    assert any("replacement" in node_id for node_id in extraction_ids)
    assert any("added_symbol" in node_id for node_id in extraction_ids)
    assert "stale_semantic" not in extraction_ids

    _run_code(merge_blocks[0], cwd=tmp_path, root=root)
    cache_after = {
        path.relative_to(semantic_cache).as_posix(): path.read_bytes()
        for path in semantic_cache.rglob("*") if path.is_file()
    }
    assert cache_after == cache_before
    merged = json.loads(extraction_path.read_text(encoding="utf-8"))
    merged_nodes = {node["id"]: node for node in merged["nodes"]}
    assert "old_changed" not in merged_nodes
    assert "old_deleted" not in merged_nodes
    assert "changed_summary" in merged_nodes
    assert "notes_summary" in merged_nodes
    assert "old_unchanged" in merged_nodes
    assert any("replacement" in node_id for node_id in merged_nodes)
    assert any("added_symbol" in node_id for node_id in merged_nodes)
    assert all(node.get("source_file") != "deleted.py" for node in merged["nodes"])
    assert any(edge["relation"] == "references" for edge in merged["edges"])
