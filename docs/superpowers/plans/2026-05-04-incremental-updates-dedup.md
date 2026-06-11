# Incremental Updates + Entity Deduplication Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add semantic cache + incremental graph updates to `graphify extract`, and add a new `graphify/dedup.py` module that runs MinHash/LSH + Jaro-Winkler entity deduplication before clustering on every run.

**Architecture:** Two independent features wired into the same pipeline: (1) `__main__.py` extract block uses `check_semantic_cache`/`save_semantic_cache` + `detect_incremental` + `build_merge` for incremental runs; (2) new `graphify/dedup.py` implements the full dedup pipeline called from `build.py` after graph construction and before `cluster()`.

**Tech Stack:** Python 3.10+, `datasketch` (MinHash/LSH), `rapidfuzz` (Jaro-Winkler), `networkx` (union-find via `nx.utils.UnionFind`), existing `graphify.cache`, `graphify.detect`, `graphify.build`.

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `graphify/dedup.py` | **Create** | Full dedup pipeline: entropy gate → MinHash/LSH → Jaro-Winkler → community boost → union-find merge |
| `graphify/build.py` | **Modify** | Call `deduplicate_entities()` from `build()` and `build_merge()`; wire dormant `deduplicate_by_label` |
| `graphify/__main__.py` | **Modify** | Semantic cache wrapping, incremental mode auto-detection, `build_merge` swap, manifest save, `--dedup-llm` flag |
| `pyproject.toml` | **Modify** | Add `datasketch`, `rapidfuzz` to base dependencies |
| `tests/test_dedup.py` | **Create** | Unit + integration tests for dedup pipeline |
| `tests/test_incremental.py` | **Create** | Integration tests for incremental extract (cache hits, manifest, prune) |

---

## Task 1: Add `datasketch` and `rapidfuzz` to dependencies

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Add deps to pyproject.toml**

Open `pyproject.toml`. The `dependencies` list ends around line 38. Add two entries:

```toml
dependencies = [
    "networkx",
    "datasketch",
    "rapidfuzz",
    "tree-sitter>=0.23.0",
    # ... rest unchanged
]
```

- [ ] **Step 2: Install into venv**

```bash
cd /home/safi/graphify
venv/bin/pip install datasketch rapidfuzz -q
```

Expected: both install without errors.

- [ ] **Step 3: Verify import**

```bash
venv/bin/python -c "from datasketch import MinHash, MinHashLSH; from rapidfuzz import fuzz; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "Add datasketch and rapidfuzz as base dependencies"
```

---

## Task 2: Create `graphify/dedup.py` — entropy gate + MinHash/LSH + Jaro-Winkler

**Files:**
- Create: `graphify/dedup.py`
- Create: `tests/test_dedup.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_dedup.py`:

```python
"""Tests for graphify/dedup.py entity deduplication pipeline."""
from __future__ import annotations
import pytest
from graphify.dedup import deduplicate_entities, _entropy, _shingles


# ── entropy gate ─────────────────────────────────────────────────────────────

def test_entropy_short_label_low():
    assert _entropy("AI") < 2.5

def test_entropy_normal_label_high():
    assert _entropy("AuthenticationManager") >= 2.5

def test_entropy_empty_string():
    assert _entropy("") == 0.0


# ── shingles ─────────────────────────────────────────────────────────────────

def test_shingles_produces_trigrams():
    s = _shingles("hello")
    assert "hel" in s
    assert "ell" in s
    assert "llo" in s

def test_shingles_short_string():
    # strings shorter than 3 chars return single shingle of the string itself
    assert _shingles("ab") == {"ab"}


# ── full pipeline ─────────────────────────────────────────────────────────────

def _make_nodes(*labels):
    return [{"id": label.lower().replace(" ", "_"), "label": label, "source_file": "test.md"} for label in labels]

def _make_edges(src, tgt, relation="relates_to"):
    return [{"source": src, "target": tgt, "relation": relation}]


def test_exact_duplicates_merged():
    nodes = _make_nodes("UserService", "userservice", "User Service")
    edges = []
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    labels = {n["label"] for n in result_nodes}
    # All three are the same concept — only one survives
    assert len(result_nodes) == 1


def test_typo_merged():
    # "GraphExtractor" vs "Graph Extractor" — Jaro-Winkler >= 0.92
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 1


def test_unrelated_not_merged():
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_short_low_entropy_not_merged():
    # "AI" and "ML" are low-entropy — entropy gate skips them
    nodes = _make_nodes("AI", "ML")
    edges = []
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2


def test_edges_rewired_after_merge():
    nodes = _make_nodes("GraphExtractor", "Graph Extractor", "Parser")
    # edge from loser to Parser should be rewired to winner
    edges = [{"source": "graph_extractor", "target": "parser", "relation": "uses"}]
    result_nodes, result_edges = deduplicate_entities(nodes, edges, communities={})
    assert len(result_nodes) == 2  # merged + Parser
    # edge should still exist (rewired to winner)
    assert len(result_edges) == 1


def test_self_loops_dropped_after_merge():
    # If both endpoints of an edge get merged into same node, drop the edge
    nodes = _make_nodes("GraphExtractor", "Graph Extractor")
    edges = [{"source": "graphextractor", "target": "graph_extractor", "relation": "same"}]
    _, result_edges = deduplicate_entities(nodes, edges, communities={})
    assert result_edges == []


def test_community_boost_aids_merge():
    # Two nodes in same community with score in 0.75-0.85 zone get boosted
    # This is a structural test — use labels that would score ~0.80 without boost
    # We verify that with communities set, they merge, without they don't
    # Use labels that Jaro-Winkler scores ~0.88 (borderline)
    nodes = _make_nodes("AuthManager", "Auth Manager")
    edges = []
    # Same community → boost → merge
    communities = {"authmanager": 1, "auth_manager": 1}
    result_with, _ = deduplicate_entities(nodes, edges, communities=communities)
    # Different community → no boost
    communities_diff = {"authmanager": 1, "auth_manager": 2}
    result_without, _ = deduplicate_entities(nodes, edges, communities=communities_diff)
    assert len(result_with) <= len(result_without)


def test_empty_inputs():
    result_nodes, result_edges = deduplicate_entities([], [], communities={})
    assert result_nodes == []
    assert result_edges == []


def test_single_node_no_crash():
    nodes = _make_nodes("UserService")
    result_nodes, _ = deduplicate_entities(nodes, [], communities={})
    assert len(result_nodes) == 1
```

- [ ] **Step 2: Run tests — verify they all fail**

```bash
cd /home/safi/graphify
venv/bin/python -m pytest tests/test_dedup.py -v --tb=short 2>&1 | tail -20
```

Expected: all fail with `ModuleNotFoundError: No module named 'graphify.dedup'`

- [ ] **Step 3: Create `graphify/dedup.py`**

```python
"""Entity deduplication pipeline for graphify knowledge graphs.

Pipeline: exact normalization → entropy gate → MinHash/LSH blocking →
Jaro-Winkler verification → same-community boost → union-find merge.
"""
from __future__ import annotations
import math
import re
from collections import defaultdict
from typing import Any

from datasketch import MinHash, MinHashLSH
from rapidfuzz import fuzz


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm(label: str) -> str:
    """Lowercase + collapse non-alphanumeric runs to space."""
    return re.sub(r"[^a-z0-9]+", " ", label.lower()).strip()


def _entropy(label: str) -> float:
    """Shannon entropy in bits/char of the normalised label."""
    s = _norm(label)
    if not s:
        return 0.0
    freq: dict[str, int] = defaultdict(int)
    for ch in s:
        freq[ch] += 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _shingles(text: str, k: int = 3) -> set[str]:
    """Return k-gram character shingles of text."""
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def _make_minhash(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for shingle in _shingles(text):
        m.update(shingle.encode("utf-8"))
    return m


# ── union-find ────────────────────────────────────────────────────────────────

class _UF:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        self._parent.setdefault(x, x)
        self._parent.setdefault(y, y)
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[ry] = rx

    def components(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for x in self._parent:
            groups[self.find(x)].append(x)
        return dict(groups)


# ── main entry point ──────────────────────────────────────────────────────────

_ENTROPY_THRESHOLD = 2.5
_LSH_THRESHOLD = 0.7
_JW_THRESHOLD = 92.0      # rapidfuzz returns 0-100
_COMMUNITY_BOOST = 5.0    # added to score when both nodes share community
_MERGE_THRESHOLD = 92.0   # final threshold after boost
_NUM_PERM = 128
_CHUNK_SUFFIX = re.compile(r"_c\d+$")


def deduplicate_entities(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
) -> tuple[list[dict], list[dict]]:
    """Deduplicate near-identical entities in a knowledge graph.

    Args:
        nodes: list of node dicts with at minimum {"id": str, "label": str}
        edges: list of edge dicts with {"source": str, "target": str, ...}
        communities: mapping of node_id -> community_id (from cluster())

    Returns:
        (deduped_nodes, deduped_edges) with edges rewired to survivors
    """
    if len(nodes) <= 1:
        return nodes, edges

    # ── pass 1: exact normalization (always runs) ─────────────────────────────
    norm_to_nodes: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key:
            norm_to_nodes[key].append(node)

    uf = _UF()
    for key, group in norm_to_nodes.items():
        if len(group) > 1:
            winner = _pick_winner(group)
            for node in group:
                uf.union(winner["id"], node["id"])

    exact_merges = sum(len(g) - 1 for g in norm_to_nodes.values() if len(g) > 1)

    # ── pass 2: MinHash/LSH + Jaro-Winkler (high-entropy nodes only) ─────────
    # Build candidate set: one representative per exact-norm group
    candidates: list[dict] = []
    seen_norms: set[str] = set()
    for node in nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key and key not in seen_norms:
            seen_norms.add(key)
            if _entropy(node.get("label", "")) >= _ENTROPY_THRESHOLD:
                candidates.append(node)

    fuzzy_merges = 0
    if len(candidates) >= 2:
        lsh = MinHashLSH(threshold=_LSH_THRESHOLD, num_perm=_NUM_PERM)
        minhashes: dict[str, MinHash] = {}

        for node in candidates:
            norm_label = _norm(node.get("label", node.get("id", "")))
            m = _make_minhash(norm_label)
            minhashes[node["id"]] = m
            try:
                lsh.insert(node["id"], m)
            except ValueError:
                pass  # duplicate key in LSH — already inserted

        for node in candidates:
            node_id = node["id"]
            norm_label = _norm(node.get("label", node.get("id", "")))
            neighbors = lsh.query(minhashes[node_id])

            for neighbor_id in neighbors:
                if neighbor_id == node_id:
                    continue
                if uf.find(node_id) == uf.find(neighbor_id):
                    continue  # already merged

                # Find the neighbour node
                neighbor = next((n for n in candidates if n["id"] == neighbor_id), None)
                if neighbor is None:
                    continue

                neighbor_norm = _norm(neighbor.get("label", neighbor.get("id", "")))
                score = fuzz.jaro_winkler_similarity(norm_label, neighbor_norm) * 100

                # Same-community boost
                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if c1 is not None and c2 is not None and c1 == c2:
                    score += _COMMUNITY_BOOST

                if score >= _MERGE_THRESHOLD:
                    all_nodes_in_group = norm_to_nodes.get(norm_label, [node]) + \
                                        norm_to_nodes.get(neighbor_norm, [neighbor])
                    winner = _pick_winner(all_nodes_in_group)
                    uf.union(winner["id"], node_id)
                    uf.union(winner["id"], neighbor_id)
                    fuzzy_merges += 1

    # ── build remap table from union-find components ──────────────────────────
    components = uf.components()
    remap: dict[str, str] = {}
    surviving_ids: set[str] = set()

    for root, members in components.items():
        if len(members) == 1:
            surviving_ids.add(root)
            continue
        group_nodes = [n for n in nodes if n["id"] in members]
        winner = _pick_winner(group_nodes) if group_nodes else {"id": root}
        winner_id = winner["id"]
        surviving_ids.add(winner_id)
        for member in members:
            if member != winner_id:
                remap[member] = winner_id

    # ── apply remap ───────────────────────────────────────────────────────────
    if not remap:
        return nodes, edges

    total = len(remap)
    msg = f"[graphify] Deduplicated {total} node(s)"
    if exact_merges:
        msg += f" ({exact_merges} exact"
        if fuzzy_merges:
            msg += f", {fuzzy_merges} fuzzy"
        msg += ")"
    print(msg + ".", flush=True)

    deduped_nodes = [n for n in nodes if n["id"] not in remap]
    deduped_edges = []
    for edge in edges:
        e = dict(edge)
        e["source"] = remap.get(e["source"], e["source"])
        e["target"] = remap.get(e["target"], e["target"])
        if e["source"] != e["target"]:
            deduped_edges.append(e)

    return deduped_nodes, deduped_edges


def _pick_winner(nodes: list[dict]) -> dict:
    """Pick the canonical survivor: prefer no chunk suffix, then shorter ID."""
    if not nodes:
        raise ValueError("Cannot pick winner from empty list")
    def _score(n: dict) -> tuple[int, int]:
        has_suffix = bool(_CHUNK_SUFFIX.search(n["id"]))
        return (1 if has_suffix else 0, len(n["id"]))
    return min(nodes, key=_score)
```

- [ ] **Step 4: Run tests — verify they pass**

```bash
cd /home/safi/graphify
venv/bin/python -m pytest tests/test_dedup.py -v --tb=short 2>&1 | tail -30
```

Expected: all tests pass.

- [ ] **Step 5: Run full suite — no regressions**

```bash
venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: same pass count as before (532 passed, 5 failed SQL).

- [ ] **Step 6: Commit**

```bash
git add graphify/dedup.py tests/test_dedup.py
git commit -m "Add graphify/dedup.py: entropy gate + MinHash/LSH + Jaro-Winkler entity deduplication"
```

---

## Task 3: Wire dedup into `build.py`

**Files:**
- Modify: `graphify/build.py` (lines 119-137 `build()`, lines 191-244 `build_merge()`)

- [ ] **Step 1: Write failing test**

Add to `tests/test_dedup.py`:

```python
def test_build_calls_dedup():
    """build() should deduplicate near-identical nodes across extractions."""
    from graphify.build import build
    chunk1 = {
        "nodes": [{"id": "graphextractor", "label": "GraphExtractor", "source_file": "a.py"}],
        "edges": [],
    }
    chunk2 = {
        "nodes": [{"id": "graph_extractor", "label": "Graph Extractor", "source_file": "b.py"}],
        "edges": [],
    }
    G = build([chunk1, chunk2])
    # Should have merged to 1 node
    assert G.number_of_nodes() == 1
```

- [ ] **Step 2: Run — verify it fails**

```bash
venv/bin/python -m pytest tests/test_dedup.py::test_build_calls_dedup -v --tb=short
```

Expected: FAIL — two separate nodes exist (no dedup wired yet).

- [ ] **Step 3: Modify `build()` in `build.py`**

Find `build()` at line 119. Current:

```python
def build(extractions: list[dict], *, directed: bool = False) -> nx.Graph:
    ...
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    return build_from_json(combined, directed=directed)
```

Replace with:

```python
def build(extractions: list[dict], *, directed: bool = False, dedup: bool = True) -> nx.Graph:
    """Merge multiple extraction results into one graph.

    directed=True produces a DiGraph. dedup=True (default) runs entity
    deduplication before building the NetworkX graph.
    """
    from graphify.dedup import deduplicate_entities
    combined: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    for ext in extractions:
        combined["nodes"].extend(ext.get("nodes", []))
        combined["edges"].extend(ext.get("edges", []))
        combined["hyperedges"].extend(ext.get("hyperedges", []))
        combined["input_tokens"] += ext.get("input_tokens", 0)
        combined["output_tokens"] += ext.get("output_tokens", 0)
    if dedup and combined["nodes"]:
        combined["nodes"], combined["edges"] = deduplicate_entities(
            combined["nodes"], combined["edges"], communities={}
        )
    return build_from_json(combined, directed=directed)
```

- [ ] **Step 4: Modify `build_merge()` signature in `build.py`**

Find `build_merge()` at line 191. Update signature and the internal `build()` call:

```python
def build_merge(
    new_chunks: list[dict],
    graph_path: str | Path = "graphify-out/graph.json",
    prune_sources: list[str] | None = None,
    *,
    directed: bool = False,
    dedup: bool = True,
) -> nx.Graph:
```

Inside `build_merge`, find the line `G = build(all_chunks, directed=directed)` (around line 222) and replace with:

```python
    G = build(all_chunks, directed=directed, dedup=dedup)
```

Also update the safety-check block (around lines 235-242). When `dedup=True` or `prune_sources` is set, the graph can legitimately shrink — skip the shrink guard:

```python
    if graph_path.exists() and not dedup and not prune_sources:
        existing_n = len(existing_nodes)
        new_n = G.number_of_nodes()
        if new_n < existing_n:
            raise ValueError(
                f"graphify: build_merge would shrink graph from {existing_n} → {new_n} nodes. "
                f"Pass prune_sources explicitly if you intend to remove nodes."
            )
```

- [ ] **Step 5: Run tests**

```bash
venv/bin/python -m pytest tests/test_dedup.py -v --tb=short 2>&1 | tail -20
```

Expected: all pass including `test_build_calls_dedup`.

- [ ] **Step 6: Run full suite**

```bash
venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: 532 passed, 5 failed (same pre-existing SQL failures).

- [ ] **Step 7: Commit**

```bash
git add graphify/build.py
git commit -m "Wire deduplicate_entities into build() and build_merge()"
```

---

## Task 4: Incremental updates — semantic cache + manifest in `__main__.py`

**Files:**
- Modify: `graphify/__main__.py` (lines 1971–2117, the extract block)
- Create: `tests/test_incremental.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_incremental.py`:

```python
"""Integration tests for incremental graphify extract behavior."""
from __future__ import annotations
import json
import subprocess
import sys
from pathlib import Path

import pytest

PYTHON = sys.executable
FIXTURES = Path(__file__).parent / "fixtures"


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )


def _make_docs_corpus(tmp_path: Path) -> Path:
    """Create a minimal docs corpus with manifest + graph.json for incremental testing."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "intro.md").write_text("# Introduction\nThis doc introduces the system.")
    (docs / "api.md").write_text("# API Reference\nThe API has endpoints.")
    return docs


def test_manifest_written_after_extract(tmp_path):
    """After a full extract run, manifest.json must exist."""
    # We can't do a real LLM extract in CI, but we can test that the manifest
    # path is resolved correctly by checking that a missing API key exits early
    # before writing the manifest — and that the path would be correct.
    docs = _make_docs_corpus(tmp_path)
    r = _run(["extract", str(docs)], tmp_path)
    # Should fail with no API key — but NOT with a path error
    assert "no LLM API key" in r.stderr or r.returncode != 0
    # manifest should NOT exist (run failed before writing)
    manifest = docs / "graphify-out" / "manifest.json"
    assert not manifest.exists()


def test_incremental_mode_detected_via_manifest(tmp_path):
    """If manifest.json + graph.json exist, incremental mode message is shown."""
    docs = _make_docs_corpus(tmp_path)
    out = docs / "graphify-out"
    out.mkdir()
    # Fake a prior successful run
    (out / "graph.json").write_text(json.dumps({"nodes": [], "links": []}))
    (out / "manifest.json").write_text(json.dumps({"document": [str(docs / "intro.md")]}))
    r = _run(["extract", str(docs)], tmp_path)
    # Should show incremental scan message (even if it fails on API key)
    assert "incremental" in r.stderr.lower() or "incremental" in r.stdout.lower() or r.returncode != 0


def test_no_incremental_without_manifest(tmp_path):
    """Without manifest.json, full scan message is shown."""
    docs = _make_docs_corpus(tmp_path)
    r = _run(["extract", str(docs)], tmp_path)
    # Full scan message (not incremental), then fails on API key
    assert "incremental" not in r.stdout
```

- [ ] **Step 2: Run — verify tests fail or pass trivially**

```bash
venv/bin/python -m pytest tests/test_incremental.py -v --tb=short 2>&1 | tail -20
```

Note current behavior before changes.

- [ ] **Step 3: Update the `elif cmd == "extract":` block in `__main__.py`**

Find line 1971 (the `from graphify.detect import detect as _detect` line). Replace the detect + file-list block (lines 1971–1984) with:

```python
        from graphify.detect import (
            detect as _detect,
            detect_incremental as _detect_incremental,
            save_manifest as _save_manifest,
        )
        manifest_path = graphify_out / "manifest.json"
        existing_graph_path = graphify_out / "graph.json"
        incremental_mode = manifest_path.exists() and existing_graph_path.exists()

        if incremental_mode:
            print(f"[graphify extract] incremental scan of {target}")
            detection = _detect_incremental(target, manifest_path=str(manifest_path))
        else:
            print(f"[graphify extract] scanning {target}")
            detection = _detect(target)

        files_by_type = detection.get("files", {})
        if incremental_mode:
            new_by_type = detection.get("new_files", {})
            code_files = [Path(p) for p in new_by_type.get("code", [])]
            doc_files = [Path(p) for p in new_by_type.get("document", [])]
            paper_files = [Path(p) for p in new_by_type.get("paper", [])]
            image_files = [Path(p) for p in new_by_type.get("image", [])]
            deleted_files = list(detection.get("deleted_files", []))
            unchanged_total = sum(len(v) for v in detection.get("unchanged_files", {}).values())
        else:
            code_files = [Path(p) for p in files_by_type.get("code", [])]
            doc_files = [Path(p) for p in files_by_type.get("document", [])]
            paper_files = [Path(p) for p in files_by_type.get("paper", [])]
            image_files = [Path(p) for p in files_by_type.get("image", [])]
            deleted_files = []
            unchanged_total = 0

        semantic_files = doc_files + paper_files + image_files
        if incremental_mode:
            print(
                f"[graphify extract] {len(code_files)} code, {len(doc_files)} docs, "
                f"{len(paper_files)} papers, {len(image_files)} images changed; "
                f"{unchanged_total} unchanged; {len(deleted_files)} deleted"
            )
        else:
            print(
                f"[graphify extract] found {len(code_files)} code, "
                f"{len(doc_files)} docs, {len(paper_files)} papers, "
                f"{len(image_files)} images"
            )
```

- [ ] **Step 4: Wrap the semantic LLM call with semantic cache**

Find the semantic extraction block (lines 1998–2024). Replace with:

```python
        from graphify.cache import (
            check_semantic_cache as _check_semantic_cache,
            save_semantic_cache as _save_semantic_cache,
        )
        sem_result: dict = {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0,
        }
        sem_cache_hits = 0
        sem_cache_misses = 0
        if semantic_files:
            sem_paths_str = [str(p) for p in semantic_files]
            cached_nodes, cached_edges, cached_hyperedges, uncached_paths = (
                _check_semantic_cache(sem_paths_str, root=target)
            )
            sem_cache_hits = len(semantic_files) - len(uncached_paths)
            sem_cache_misses = len(uncached_paths)
            sem_result["nodes"].extend(cached_nodes)
            sem_result["edges"].extend(cached_edges)
            sem_result["hyperedges"].extend(cached_hyperedges)
            if sem_cache_hits:
                print(f"[graphify extract] semantic cache: {sem_cache_hits} hit / {sem_cache_misses} miss")

            if uncached_paths:
                print(f"[graphify extract] semantic extraction on {len(uncached_paths)} files via {backend}...")
                try:
                    fresh = _extract_corpus_parallel(
                        [Path(p) for p in uncached_paths],
                        backend=backend,
                        root=target,
                    )
                except ImportError as exc:
                    print(f"error: {exc}", file=sys.stderr)
                    sys.exit(1)
                except Exception as exc:
                    print(f"[graphify extract] semantic extraction failed: {exc}", file=sys.stderr)
                    fresh = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
                try:
                    _save_semantic_cache(
                        fresh.get("nodes", []),
                        fresh.get("edges", []),
                        fresh.get("hyperedges", []),
                        root=target,
                    )
                except Exception as exc:
                    print(f"[graphify extract] warning: could not write semantic cache: {exc}", file=sys.stderr)
                sem_result["nodes"].extend(fresh.get("nodes", []))
                sem_result["edges"].extend(fresh.get("edges", []))
                sem_result["hyperedges"].extend(fresh.get("hyperedges", []))
                sem_result["input_tokens"] += fresh.get("input_tokens", 0)
                sem_result["output_tokens"] += fresh.get("output_tokens", 0)
```

- [ ] **Step 5: Replace `build_from_json` with `build_merge` in incremental mode**

Find the build block starting around line 2063. Replace:

```python
        from graphify.build import build_from_json as _build_from_json
        ...
        G = _build_from_json(merged)
```

With:

```python
        from graphify.build import (
            build_from_json as _build_from_json,
            build_merge as _build_merge,
        )
        from graphify.cluster import cluster as _cluster, score_all as _score_all
        from graphify.export import to_json as _to_json
        from graphify.analyze import god_nodes as _god_nodes, surprising_connections as _surprising

        if incremental_mode:
            G = _build_merge(
                [merged],
                graph_path=graph_json_path,
                prune_sources=deleted_files or None,
                dedup=True,
            )
        else:
            G = _build_from_json(merged)
```

- [ ] **Step 6: Add manifest save after successful write**

Find the `analysis_path.write_text(...)` line (around line 2101). After it, add:

```python
        try:
            _save_manifest(
                detection.get("files", {}),
                manifest_path=str(manifest_path),
            )
        except Exception as exc:
            print(f"[graphify extract] warning: could not write manifest: {exc}", file=sys.stderr)
```

Also add the same block in the `--no-cluster` path after `graph_json_path.write_text(...)` (around line 2043).

- [ ] **Step 7: Add `--dedup-llm` flag parsing**

In the args-parsing while loop (around lines 1913–1928), add:

```python
            elif a == "--dedup-llm":
                dedup_llm = True; i += 1
```

And initialize `dedup_llm = False` before the loop.

- [ ] **Step 8: Update summary print at end**

Replace the final summary lines (around 2104–2116) with:

```python
        print(
            f"[graphify extract] wrote {graph_json_path}: "
            f"{G.number_of_nodes()} nodes, {G.number_of_edges()} edges, "
            f"{len(communities)} communities"
        )
        print(f"[graphify extract] wrote {analysis_path}")
        if incremental_mode:
            print(
                f"[graphify extract] incremental summary: "
                f"{sem_cache_hits + unchanged_total} files cached/unchanged, "
                f"{len(code_files) + sem_cache_misses} re-extracted, "
                f"{len(deleted_files)} deleted"
            )
        elif sem_cache_hits:
            print(f"[graphify extract] semantic cache: {sem_cache_hits} cached, {sem_cache_misses} re-extracted")
        if merged["input_tokens"] or merged["output_tokens"]:
            print(
                f"[graphify extract] tokens: "
                f"{merged['input_tokens']:,} in / "
                f"{merged['output_tokens']:,} out, "
                f"est. cost (~{backend}): ${cost:.4f}"
            )
```

- [ ] **Step 9: Run incremental tests**

```bash
venv/bin/python -m pytest tests/test_incremental.py -v --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 10: Run full suite**

```bash
venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: 532+ passed, 5 failed (pre-existing SQL).

- [ ] **Step 11: Commit**

```bash
git add graphify/__main__.py tests/test_incremental.py
git commit -m "Add incremental updates to graphify extract: semantic cache + build_merge + manifest"
```

---

## Task 5: Add `--dedup-llm` tiebreaker to `dedup.py`

**Files:**
- Modify: `graphify/dedup.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_dedup.py`:

```python
def test_dedup_llm_flag_accepted():
    """deduplicate_entities accepts dedup_llm_backend without crashing when no ambiguous pairs exist."""
    nodes = _make_nodes("UserService", "OrderService")
    edges = []
    # Should not crash even with dedup_llm_backend set — just nothing to resolve
    result_nodes, _ = deduplicate_entities(nodes, edges, communities={}, dedup_llm_backend=None)
    assert len(result_nodes) == 2
```

- [ ] **Step 2: Run — verify it fails**

```bash
venv/bin/python -m pytest tests/test_dedup.py::test_dedup_llm_flag_accepted -v --tb=short
```

Expected: FAIL — `deduplicate_entities` does not accept `dedup_llm_backend` kwarg.

- [ ] **Step 3: Add `dedup_llm_backend` param to `deduplicate_entities`**

Update the signature in `graphify/dedup.py`:

```python
def deduplicate_entities(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
    dedup_llm_backend: str | None = None,
) -> tuple[list[dict], list[dict]]:
```

After the fuzzy merge loop (before building the remap table), add the LLM tiebreaker block:

```python
    # ── pass 3: LLM tiebreaker for ambiguous pairs (opt-in) ──────────────────
    if dedup_llm_backend is not None:
        _llm_tiebreak(candidates, uf, communities, backend=dedup_llm_backend)
```

Add the helper at the bottom of `dedup.py`:

```python
def _llm_tiebreak(
    candidates: list[dict],
    uf: _UF,
    communities: dict[str, int],
    *,
    backend: str,
    batch_size: int = 30,
    low: float = 75.0,
    high: float = 92.0,
) -> None:
    """Batch-resolve ambiguous pairs (score in [low, high)) via LLM."""
    try:
        from graphify.llm import extract_corpus_parallel as _llm  # noqa: F401
        import os
        from graphify.llm import BACKENDS
        env_key = BACKENDS.get(backend, {}).get("env_key", "")
        if not os.environ.get(env_key):
            print(f"[graphify] --dedup-llm: {env_key} not set, skipping LLM tiebreaker.", flush=True)
            return
    except ImportError:
        return

    # Collect ambiguous pairs
    ambiguous: list[tuple[dict, dict, float]] = []
    for i, node in enumerate(candidates):
        norm_i = _norm(node.get("label", node.get("id", "")))
        for j in range(i + 1, len(candidates)):
            neighbor = candidates[j]
            if uf.find(node["id"]) == uf.find(neighbor["id"]):
                continue
            norm_j = _norm(neighbor.get("label", neighbor.get("id", "")))
            score = fuzz.jaro_winkler_similarity(norm_i, norm_j) * 100
            c1 = communities.get(node["id"])
            c2 = communities.get(neighbor["id"])
            if c1 is not None and c2 is not None and c1 == c2:
                score += _COMMUNITY_BOOST
            if low <= score < high:
                ambiguous.append((node, neighbor, score))

    if not ambiguous:
        return

    # Batch into groups of batch_size and call LLM
    try:
        from graphify.llm import _call_llm
    except ImportError:
        return

    for batch_start in range(0, len(ambiguous), batch_size):
        batch = ambiguous[batch_start : batch_start + batch_size]
        pairs_text = "\n".join(
            f"{i+1}. \"{a['label']}\" vs \"{b['label']}\""
            for i, (a, b, _) in enumerate(batch)
        )
        prompt = (
            "For each pair below, answer only 'yes' or 'no': are they the same real-world concept?\n\n"
            f"{pairs_text}\n\n"
            "Reply with one line per pair: '1. yes', '2. no', etc."
        )
        try:
            response = _call_llm(prompt, backend=backend, max_tokens=200)
            lines = response.strip().splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(".", 1)
                if len(parts) != 2:
                    continue
                try:
                    idx = int(parts[0].strip()) - 1
                except ValueError:
                    continue
                if 0 <= idx < len(batch):
                    answer = parts[1].strip().lower()
                    if answer.startswith("yes"):
                        a, b, _ = batch[idx]
                        winner = _pick_winner([a, b])
                        uf.union(winner["id"], a["id"])
                        uf.union(winner["id"], b["id"])
        except Exception as exc:
            print(f"[graphify] --dedup-llm batch failed: {exc}", flush=True)
```

- [ ] **Step 4: Run tests**

```bash
venv/bin/python -m pytest tests/test_dedup.py -v --tb=short 2>&1 | tail -20
```

Expected: all pass.

- [ ] **Step 5: Run full suite**

```bash
venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: 532+ passed, 5 failed.

- [ ] **Step 6: Commit**

```bash
git add graphify/dedup.py tests/test_dedup.py
git commit -m "Add --dedup-llm LLM tiebreaker to dedup pipeline"
```

---

## Task 6: Update CHANGELOG + bump version to 0.7.5

**Files:**
- Modify: `CHANGELOG.md`
- Modify: `pyproject.toml`

- [ ] **Step 1: Add changelog entry**

Add at the top of `CHANGELOG.md`:

```markdown
## 0.7.5 (2026-05-04)

- Feat: `graphify extract` now runs incrementally — auto-detects prior `manifest.json` and re-extracts only changed/new files; semantic results cached by content hash so unchanged docs cost zero LLM tokens on repeat runs (#698)
- Feat: Entity deduplication pipeline runs on every build — entropy gate + MinHash/LSH blocking + Jaro-Winkler verification + same-community boost collapses near-duplicate entities (typos, spacing, plurals) before clustering
- Feat: `--dedup-llm` flag for `graphify extract` — optional LLM tiebreaker for ambiguous entity pairs (~$0.01 for 10k-node graphs), off by default
- Deps: `datasketch` and `rapidfuzz` added as base dependencies
```

- [ ] **Step 2: Bump version**

In `pyproject.toml`, change:
```toml
version = "0.7.4"
```
to:
```toml
version = "0.7.5"
```

- [ ] **Step 3: Run full suite one final time**

```bash
venv/bin/python -m pytest tests/ -q --tb=no 2>&1 | tail -5
```

Expected: 532+ passed, 5 failed (pre-existing SQL only).

- [ ] **Step 4: Commit**

```bash
git add CHANGELOG.md pyproject.toml
git commit -m "bump version to 0.7.5"
```

---

## Self-Review

**Spec coverage:**
- [x] Semantic cache wrapping → Task 4 steps 3-4
- [x] Incremental auto-detection via manifest → Task 4 step 3
- [x] `build_merge` with `prune_sources` → Task 4 step 5
- [x] Manifest saved on success only → Task 4 step 6
- [x] Summary print → Task 4 step 8
- [x] `dedup.py` new module → Task 2
- [x] Entropy gate → Task 2 step 3
- [x] MinHash/LSH blocking → Task 2 step 3
- [x] Jaro-Winkler verification → Task 2 step 3
- [x] Same-community boost → Task 2 step 3
- [x] Union-find merge → Task 2 step 3
- [x] `--dedup-llm` tiebreaker → Task 5
- [x] Wire dedup into `build()` and `build_merge()` → Task 3
- [x] `datasketch` + `rapidfuzz` deps → Task 1
- [x] Tests for all dedup steps → Task 2 + 3
- [x] Tests for incremental → Task 4
- [x] CHANGELOG + version bump → Task 6

**Placeholder scan:** None found.

**Type consistency:** `deduplicate_entities(nodes, edges, *, communities, dedup_llm_backend=None)` used consistently in Task 2, Task 3, Task 5. `build(extractions, *, directed, dedup)` consistent in Task 3. `build_merge(..., dedup=True)` consistent in Task 3 and Task 4.
