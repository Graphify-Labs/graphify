"""Tests for unverified semantic document node shrink protection (#3203).

When an incremental extraction produces strictly fewer semantic document nodes
for an existing source file (prior > 1 and fresh < prior), it is treated as an
unverified semantic shrink. build_merge flags the anomaly on G.graph so the CLI
can arm the shrink guard (force=False) and prevent the under-produced source from
being stamped in manifest.json, preserving the existing graph and allowing
subsequent incremental runs to retry.
"""
from __future__ import annotations

import json
from pathlib import Path
import pytest

import graphify.__main__ as mainmod
from graphify.build import build_merge, merge_raw_extraction
import graphify.llm as llmmod


def _sem_node(sf: str, name: str) -> dict:
    """Semantic node without _origin."""
    stem = sf.replace("/", "_").replace(".", "_")
    return {
        "id": f"{stem}_{name}",
        "label": f"{sf} {name}",
        "file_type": "document",
        "source_file": sf,
    }


def _ast_node(sf: str, name: str) -> dict:
    """AST node with _origin='ast'."""
    stem = sf.replace("/", "_").replace(".", "_")
    return {
        "id": f"{stem}_{name}",
        "label": f"{sf} {name}",
        "file_type": "code",
        "source_file": sf,
        "_origin": "ast",
    }


def _write_graph(graph_path: Path, nodes, edges=()) -> None:
    graph_path.parent.mkdir(parents=True, exist_ok=True)
    graph_path.write_text(
        json.dumps({"nodes": list(nodes), "edges": list(edges), "hyperedges": []}),
        encoding="utf-8",
    )


# ── 1. Unit Tests for build_merge anomaly flagging ────────────────────────────

def test_build_merge_flags_unverified_semantic_shrink(tmp_path):
    """Semantic source with 3 prior nodes re-extracted with 1 node is flagged on G.graph."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"n{i}") for i in range(3)])

    chunk = {"nodes": [_sem_node("doc.md", "n0")], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)

    assert G.number_of_nodes() == 1
    assert "_unverified_semantic_shrink" in G.graph
    assert G.graph["_unverified_semantic_shrink"] == {"doc.md": (3, 1)}


def test_build_merge_flags_shrink_when_surviving_id_is_renamed(tmp_path):
    """Surviving semantic node renamed (n0 -> renamed_concept) still flags based on count."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"sec_{i}") for i in range(3)])

    chunk = {"nodes": [_sem_node("doc.md", "renamed_concept")], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)

    assert G.number_of_nodes() == 1
    assert G.graph.get("_unverified_semantic_shrink") == {"doc.md": (3, 1)}


def test_build_merge_own_file_shrink_remains_non_fatal(tmp_path):
    """build_merge must NOT raise an exception on own-file shrink; it returns G."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"n{i}") for i in range(10)])

    chunk = {"nodes": [_sem_node("doc.md", "n0")], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)
    assert G.number_of_nodes() == 1


def test_build_merge_does_not_flag_ast_code_shrink(tmp_path):
    """Deterministic AST/code shrinkage (10 -> 1) is never flagged as unverified semantic shrink."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_ast_node("mod.py", f"fn{i}") for i in range(10)])

    chunk = {"nodes": [_ast_node("mod.py", "fn0")], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)

    assert G.number_of_nodes() == 1
    assert "_unverified_semantic_shrink" not in G.graph


def test_build_merge_equal_count_different_ids_not_flagged(tmp_path):
    """10 -> 10 semantic nodes with completely different IDs is not flagged as a shrink."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"old_{i}") for i in range(10)])

    chunk = {"nodes": [_sem_node("doc.md", f"new_{i}") for i in range(10)], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)

    assert G.number_of_nodes() == 10
    assert "_unverified_semantic_shrink" not in G.graph


def test_build_merge_semantic_growth_not_flagged(tmp_path):
    """Semantic growth (3 -> 4) is unaffected."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"n{i}") for i in range(3)])

    chunk = {"nodes": [_sem_node("doc.md", f"n{i}") for i in range(4)], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)

    assert G.number_of_nodes() == 4
    assert "_unverified_semantic_shrink" not in G.graph


def test_build_merge_aggregates_multiple_chunks_per_source(tmp_path):
    """Multiple chunks for the same source are summed before comparison (2 + 2 = 4 >= 3 -> no shrink)."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"n{i}") for i in range(3)])

    chunk1 = {"nodes": [_sem_node("doc.md", "c1_a"), _sem_node("doc.md", "c1_b")], "edges": []}
    chunk2 = {"nodes": [_sem_node("doc.md", "c2_a"), _sem_node("doc.md", "c2_b")], "edges": []}

    G = build_merge([chunk1, chunk2], gp, dedup=False, root=tmp_path)
    assert G.number_of_nodes() == 4
    assert "_unverified_semantic_shrink" not in G.graph


def test_build_merge_source_specific_growth_cannot_mask_shrink(tmp_path):
    """Growth in B (3 -> 20) cannot mask unverified shrink in A (6 -> 2)."""
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(
        gp,
        [_sem_node("a.md", f"a{i}") for i in range(6)]
        + [_sem_node("b.md", f"b{i}") for i in range(3)],
    )

    chunk_a = {"nodes": [_sem_node("a.md", f"a{i}") for i in range(2)], "edges": []}
    chunk_b = {"nodes": [_sem_node("b.md", f"b{i}") for i in range(20)], "edges": []}

    G = build_merge([chunk_a, chunk_b], gp, dedup=False, root=tmp_path)
    assert G.number_of_nodes() == 22
    assert G.graph.get("_unverified_semantic_shrink") == {"a.md": (6, 2)}


def test_merge_raw_extraction_parity(tmp_path):
    """merge_raw_extraction also flags unverified semantic shrink."""
    gp = tmp_path / "graph.json"
    _write_graph(gp, [_sem_node("doc.md", f"n{i}") for i in range(5)])

    new = {"nodes": [_sem_node("doc.md", "n0")], "edges": [], "hyperedges": []}
    merged = merge_raw_extraction(new, gp, root=tmp_path)

    assert merged.get("_unverified_semantic_shrink") == {"doc.md": (5, 1)}


# ── 2. Integration / CLI Tests for #3203 Behavior ─────────────────────────────

def _run_cli():
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code
    return 0


def test_3203_e2e_repro_protected_and_manifest_unstamped(tmp_path, monkeypatch, capsys):
    """Reproduce #3203: Initial 3 nodes for README.md -> re-extracted with 1 node.
    The shrink guard refuses the overwrite, exits 1, and README.md is not stamped.
    """
    corpus = tmp_path / "repo"
    corpus.mkdir()
    readme = corpus / "README.md"
    guide = corpus / "GUIDE.md"
    readme.write_text("# Readme\nInitial content\n", encoding="utf-8")
    guide.write_text("# Guide\nGuide content\n", encoding="utf-8")

    out_dir = corpus / "graphify-out"

    # Step 1: Initial build (README: 3 nodes, GUIDE: 2 nodes)
    def _mock_llm_run1(files, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        res = {
            "nodes": [
                {"id": "readme_doc", "label": "Readme", "file_type": "document", "source_file": "README.md"},
                {"id": "readme_sec1", "label": "Section 1", "file_type": "document", "source_file": "README.md"},
                {"id": "readme_sec2", "label": "Section 2", "file_type": "document", "source_file": "README.md"},
                {"id": "guide_doc", "label": "Guide", "file_type": "document", "source_file": "GUIDE.md"},
                {"id": "guide_sec1", "label": "Guide Sec", "file_type": "document", "source_file": "GUIDE.md"},
            ],
            "edges": [], "hyperedges": [],
            "input_tokens": 10, "output_tokens": 10, "uncovered_files": [],
        }
        if on_chunk:
            on_chunk(0, 1, res)
        return res

    monkeypatch.setattr(llmmod, "extract_corpus_parallel", _mock_llm_run1)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "extract", str(corpus), "--backend", "claude"])
    code1 = _run_cli()
    assert code1 == 0

    graph1 = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    assert len(graph1["nodes"]) == 5

    manifest1 = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert "README.md" in manifest1
    initial_hash = manifest1["README.md"]["semantic_hash"]

    # Step 2: Edit README.md and re-extract returning only 1 node
    readme.write_text("# Readme\nEdited content\n", encoding="utf-8")

    def _mock_llm_run2(files, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        res = {
            "nodes": [
                {"id": "readme_doc_renamed", "label": "Readme Renamed", "file_type": "document", "source_file": "README.md"},
            ],
            "edges": [], "hyperedges": [],
            "input_tokens": 10, "output_tokens": 5, "uncovered_files": [],
        }
        if on_chunk:
            on_chunk(0, 1, res)
        return res

    monkeypatch.setattr(llmmod, "extract_corpus_parallel", _mock_llm_run2)
    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "extract", str(corpus), "--backend", "claude"])

    code2 = _run_cli()
    # The shrink guard arms and refuses overwrite because graph shrinks 5 -> 3
    assert code2 == 1

    err = capsys.readouterr().err
    assert "unverified semantic shrink detected for 'README.md' (3 -> 1 nodes)" in err
    assert "Refusing to overwrite" in err

    # The existing graph on disk is still the healthy 5-node graph
    graph2 = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    assert len(graph2["nodes"]) == 5

    # Manifest is NOT stamped with the new hash for README.md
    manifest2 = json.loads((out_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest2["README.md"]["semantic_hash"] == initial_hash


def test_3203_allow_partial_override_permits_intentional_reduction(tmp_path, monkeypatch, capsys):
    """Passing --allow-partial permits an intentional semantic reduction and stamps manifest."""
    corpus = tmp_path / "repo"
    corpus.mkdir()
    readme = corpus / "README.md"
    readme.write_text("# Readme\nInitial content\n", encoding="utf-8")

    out_dir = corpus / "graphify-out"

    def _mock_llm_run1(files, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        res = {
            "nodes": [
                {"id": "readme_doc", "label": "Readme", "file_type": "document", "source_file": "README.md"},
                {"id": "readme_sec1", "label": "Section 1", "file_type": "document", "source_file": "README.md"},
                {"id": "readme_sec2", "label": "Section 2", "file_type": "document", "source_file": "README.md"},
            ],
            "edges": [], "hyperedges": [],
            "input_tokens": 10, "output_tokens": 10, "uncovered_files": [],
        }
        if on_chunk:
            on_chunk(0, 1, res)
        return res

    monkeypatch.setattr(llmmod, "extract_corpus_parallel", _mock_llm_run1)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")

    monkeypatch.setattr(mainmod.sys, "argv", ["graphify", "extract", str(corpus), "--backend", "claude"])
    code1 = _run_cli()
    assert code1 == 0

    # Re-extract with --allow-partial
    readme.write_text("# Readme\nShortened content\n", encoding="utf-8")

    def _mock_llm_run2(files, **kwargs):
        on_chunk = kwargs.get("on_chunk_done")
        res = {
            "nodes": [
                {"id": "readme_doc", "label": "Readme", "file_type": "document", "source_file": "README.md"},
            ],
            "edges": [], "hyperedges": [],
            "input_tokens": 10, "output_tokens": 5, "uncovered_files": [],
        }
        if on_chunk:
            on_chunk(0, 1, res)
        return res

    monkeypatch.setattr(llmmod, "extract_corpus_parallel", _mock_llm_run2)
    monkeypatch.setattr(
        mainmod.sys, "argv",
        ["graphify", "extract", str(corpus), "--backend", "claude", "--allow-partial"],
    )

    code2 = _run_cli()
    assert code2 == 0

    # With override, the 1-node graph is persisted
    graph = json.loads((out_dir / "graph.json").read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 1
