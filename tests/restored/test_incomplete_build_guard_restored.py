"""Restored incomplete-build guards using atomic native generations."""

from __future__ import annotations

from pathlib import Path

import pytest

import graphify.__main__ as mainmod
from graphify.helix.persistence import load_graph


def _docs(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "README.md").write_text("# Notes\nThe entry point overview.\n")
    (root / "GUIDE.md").write_text("# Guide\nHow to use the thing.\n")
    return root


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def _semantic(*, failed_chunks: int = 0, node_count: int = 1):
    def run(paths, **kwargs):
        path = Path(paths[0])
        return {
            "nodes": [
                {
                    "id": f"semantic-{index}", "label": f"Semantic {index}",
                    "source_file": path.name, "file_type": "document",
                }
                for index in range(node_count)
            ],
            "edges": [], "hyperedges": [], "input_tokens": 10,
            "output_tokens": 5, "failed_chunks": failed_chunks,
        }
    return run


def _seed_complete(monkeypatch, project: Path, output: Path) -> Path:
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(node_count=5))
    _run(monkeypatch, [
        "graphify", "extract", str(project), "--backend", "openai",
        "--no-cluster", "--out", str(output),
    ])
    return output / "graphify-out" / "graph.helix"


def _assert_generation_unchanged(store: Path, generation: str, counts: tuple[int, int]) -> None:
    loaded = load_graph(store)
    assert loaded.generation == generation
    assert (loaded.graph.node_count, loaded.graph.edge_count) == counts


def test_partial_extraction_refuses_to_shrink_existing_graph(monkeypatch, tmp_path, capsys):
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = _seed_complete(monkeypatch, project, output)
    before = load_graph(store)
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(failed_chunks=2))

    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai",
            "--out", str(output), "--force",
        ])

    assert exc.value.code == 1
    assert "active generation was left unchanged" in capsys.readouterr().err
    _assert_generation_unchanged(
        store, before.generation, (before.graph.node_count, before.graph.edge_count)
    )


def test_partial_extraction_writes_when_not_shrinking(monkeypatch, tmp_path):
    """Native activation is stricter: any failed chunk is rejected, regardless of size."""
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = _seed_complete(monkeypatch, project, output)
    before = load_graph(store)
    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel", _semantic(failed_chunks=1, node_count=8)
    )

    with pytest.raises(SystemExit):
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai",
            "--out", str(output), "--force",
        ])

    _assert_generation_unchanged(
        store, before.generation, (before.graph.node_count, before.graph.edge_count)
    )


def test_allow_partial_forces_write_despite_incomplete(monkeypatch, tmp_path):
    """The retired escape hatch cannot bypass atomic-generation verification."""
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = _seed_complete(monkeypatch, project, output)
    before = load_graph(store)
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(failed_chunks=1))

    with pytest.raises(SystemExit):
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai",
            "--out", str(output), "--force", "--allow-partial",
        ])

    _assert_generation_unchanged(
        store, before.generation, (before.graph.node_count, before.graph.edge_count)
    )


def test_complete_extraction_keeps_force_write(monkeypatch, tmp_path):
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = _seed_complete(monkeypatch, project, output)
    generation = load_graph(store).generation
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(node_count=2))

    _run(monkeypatch, [
        "graphify", "extract", str(project), "--backend", "openai",
        "--out", str(output), "--force",
    ])

    assert load_graph(store).generation != generation


def test_no_cluster_incomplete_build_refuses_to_shrink(tmp_path, monkeypatch, capsys):
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = _seed_complete(monkeypatch, project, output)
    before = load_graph(store)
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(failed_chunks=1))

    with pytest.raises(SystemExit):
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai",
            "--no-cluster", "--out", str(output), "--force",
        ])

    assert "active generation was left unchanged" in capsys.readouterr().err
    _assert_generation_unchanged(
        store, before.generation, (before.graph.node_count, before.graph.edge_count)
    )


def test_no_cluster_allow_partial_overwrites(tmp_path, monkeypatch):
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = _seed_complete(monkeypatch, project, output)
    generation = load_graph(store).generation
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(failed_chunks=1))

    with pytest.raises(SystemExit):
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai",
            "--no-cluster", "--out", str(output), "--force", "--allow-partial",
        ])

    assert load_graph(store).generation == generation


def test_no_cluster_incomplete_build_fails_closed_on_malformed_existing_graph(
    tmp_path, monkeypatch, capsys
):
    project = _docs(tmp_path)
    output = tmp_path / "out"
    store = output / "graphify-out" / "graph.helix"
    store.mkdir(parents=True)
    sentinel = store / "corrupt-sentinel"
    sentinel.write_text("do not replace")
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic(failed_chunks=1))

    with pytest.raises(SystemExit):
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai",
            "--no-cluster", "--out", str(output),
        ])

    assert sentinel.read_text() == "do not replace"
    assert capsys.readouterr().err
