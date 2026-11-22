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
import unicodedata
from collections import Counter
from pathlib import Path

import pytest

_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL", "OLLAMA_HOST",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


def _extract(cwd: Path, *flags: str) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    env["PYTHONHASHSEED"] = "0"
    r = subprocess.run([sys.executable, "-m", "graphify", "extract", ".", "--code-only", *flags],
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
            Counter((e["source"], e["target"], e["relation"]) for e in g.get("links", g.get("edges", []))))


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


@pytest.mark.parametrize("removal", ["deleted", "import dropped"])
def test_a_removed_referrer_takes_the_placeholder_with_it(tmp_path: Path, removal: str) -> None:
    warm = _corpus(tmp_path / "warm")
    _extract(warm)
    if removal == "deleted":
        (warm / "dyn.ts").unlink()
    else:
        (warm / "dyn.ts").write_text("export async function load() { return 1; }\n")
    _extract(warm)
    nodes, edges = _shape(warm)
    assert "left_pad" not in nodes
    assert (nodes, edges) == _cold(warm, tmp_path)


def test_a_missing_manifest_keeps_the_placeholder(tmp_path: Path) -> None:
    warm = _corpus(tmp_path / "warm")
    _extract(warm)
    (warm / "graphify-out" / "manifest.json").unlink()
    (warm / "a.ts").write_text("export function foo() { return 2 }\n")
    _extract(warm)
    nodes, edges = _shape(warm)
    assert edges[("dyn", "left_pad", "dynamic_import")] == 1
    assert (nodes, edges) == _cold(warm, tmp_path)


def test_no_cluster_keeps_the_placeholder(tmp_path: Path) -> None:
    warm = _corpus(tmp_path / "warm")
    _extract(warm, "--no-cluster")
    (warm / "a.ts").write_text("export function foo() { return 2 }\n")
    _extract(warm, "--no-cluster")
    nodes, edges = _shape(warm)
    assert edges[("dyn", "left_pad", "dynamic_import")] == 1


def test_nfd_file_names_match_the_nfc_manifest(tmp_path: Path) -> None:
    # macOS hands out NFD names; manifest keys are NFC, graph sources keep the
    # spelling the scan saw. The placeholder must survive an edit of another file.
    warm = tmp_path / "warm"
    warm.mkdir()
    referrer = unicodedata.normalize("NFD", "\u00e9.ts")
    other = unicodedata.normalize("NFD", "\u00e0.ts")
    (warm / referrer).write_text("export async function load() { return await import('left-pad'); }\n")
    (warm / other).write_text("export function foo() { return 1 }\n")
    _extract(warm)
    (warm / other).write_text("export function foo() { return 2 }\n")
    _extract(warm)
    nodes, _ = _shape(warm)
    assert "left_pad" in nodes


def test_a_non_string_source_file_in_graph_json_does_not_crash(tmp_path: Path) -> None:
    # graph.json is persisted state that can be corrupt; the helper skips
    # non-string sources the way _stale_graph_sources does instead of raising.
    from graphify.cli import _placeholder_stale_sources

    warm = _corpus(tmp_path / "warm")
    _extract(warm)
    graph_path = warm / "graphify-out" / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["nodes"].append({"id": "bogus", "label": "bogus", "source_file": []})
    graph["links"].append({"source": "dyn", "target": "left_pad", "relation": "calls", "source_file": {}})
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    keep = _placeholder_stale_sources(
        graph_path, warm / "graphify-out" / "manifest.json", warm, ["left-pad"], set(), [warm / "a.ts"],
    )
    assert keep == {"left-pad"}
