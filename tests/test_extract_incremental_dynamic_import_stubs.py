"""An incremental `graphify extract` keeps unresolved `import()` targets (#4161).

The target node's source_file is the specifier (``left-pad``), never a scanned
file, so the stale-source sweep read it as deleted and pruned a node and a
dynamic_import edge that a full extract of the same tree keeps. `graphify
update` already guards this (tests/test_incremental_unscanned_placeholders.py);
these are the `extract` twins.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_HOST",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


def _extract(cwd: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    env["PYTHONHASHSEED"] = "0"
    r = subprocess.run([sys.executable, "-m", "graphify", "extract", ".", "--code-only"],
                       cwd=cwd, capture_output=True, text=True, env=env)
    assert r.returncode == 0, r.stdout + r.stderr


def _corpus(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "a.ts").write_text("export function foo() { return 1 }\n")
    (root / "main.ts").write_text("import { foo } from './a';\nexport function run() { return foo(); }\n")
    (root / "dyn.ts").write_text("export async function load() { return await import('left-pad'); }\n")
    return root


def _shape(root: Path) -> tuple[set, Counter]:
    g = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    return ({n["id"] for n in g["nodes"]},
            Counter((e["source"], e["target"], e["relation"]) for e in g["links"]))


def _cold(warm: Path, tmp_path: Path) -> tuple[set, Counter]:
    cold = tmp_path / "cold"
    shutil.copytree(warm, cold, ignore=shutil.ignore_patterns("graphify-out"))
    _extract(cold)
    return _shape(cold)


EDITS = {
    # dyn.ts is carried over unchanged: nothing re-emits the stub its edge points at.
    "unrelated file": ("a.ts", "export function foo() { return 2 }\n"),
    # dyn.ts is re-extracted and emits the stub again; the prune removed it anyway.
    "referrer": ("dyn.ts", "export async function load() { const m = await import('left-pad'); return m; }\n"),
}


@pytest.mark.parametrize("edit", sorted(EDITS))
def test_incremental_extract_keeps_dynamic_import_targets(tmp_path: Path, edit: str) -> None:
    warm = _corpus(tmp_path / "warm")
    _extract(warm)
    name, text = EDITS[edit]
    (warm / name).write_text(text)
    _extract(warm)
    nodes, edges = _shape(warm)
    assert "left_pad" in nodes
    assert edges[("dyn", "left_pad", "dynamic_import")] == 1
    assert (nodes, edges) == _cold(warm, tmp_path)


def test_a_deleted_scanned_file_is_still_pruned(tmp_path: Path) -> None:
    # main.ts still points at a.ts's nodes, but manifest.json lists a.ts and a.ts
    # produced nodes with a location: it was a real file, so it is pruned.
    warm = _corpus(tmp_path / "warm")
    _extract(warm)
    (warm / "a.ts").unlink()
    _extract(warm)
    nodes, edges = _shape(warm)
    assert not {"a", "a_foo"} & nodes
    assert edges[("dyn", "left_pad", "dynamic_import")] == 1
