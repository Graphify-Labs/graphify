"""Restored v8 extraction regressions against native Helix state."""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

import graphify.__main__ as mainmod
from graphify.cache import check_semantic_cache, save_semantic_cache
from graphify.helix.model import node_attributes
from graphify.helix.persistence import HelixEmbeddedStore, load_graph


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def _make_corpus(tmp_path: Path, *, second_doc: bool = False) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "main.py").write_text("def main():\n    return 1\n")
    (root / "README.md").write_text("# Readme\nNative storage.\n")
    if second_doc:
        (root / "OTHER.md").write_text("# Other\nSecond document.\n")
    return root


def _semantic(paths, **kwargs):
    return {
        "nodes": [
            {
                "id": f"semantic-{Path(path).stem}",
                "label": Path(path).stem,
                "file_type": "document",
                "source_file": Path(path).name,
            }
            for path in paths
        ],
        "edges": [], "hyperedges": [], "input_tokens": 10,
        "output_tokens": 5, "failed_chunks": 0,
    }


def _extract_argv(project: Path, output: Path, *extra: str) -> list[str]:
    return [
        "graphify", "extract", str(project), "--backend", "openai",
        "--out", str(output), *extra,
    ]


def _store(output: Path) -> Path:
    return output / "graphify-out" / "graph.helix"


def _sources(store: Path) -> set[str]:
    graph = load_graph(store).graph
    return {
        str(node_attributes(graph, node.id).get("source_file", ""))
        for node in graph.nodes()
    }


def _semantic_cache(store: Path) -> dict:
    return load_graph(store).state["incremental"]["extraction_cache"]


def test_extract_exits_nonzero_when_all_semantic_chunks_fail(monkeypatch, tmp_path, capsys):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel",
        lambda *a, **k: {
            "nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0,
            "output_tokens": 0, "failed_chunks": 2,
        },
    )

    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, _extract_argv(project, output))

    assert exc.value.code == 1
    assert "active generation was left unchanged" in capsys.readouterr().err
    assert not _store(output).exists()


def test_extract_succeeds_when_at_least_one_chunk_completes(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic)

    _run(monkeypatch, _extract_argv(project, output))

    loaded = load_graph(_store(output))
    assert loaded.graph.node_count > 0
    assert loaded.state["semantic"]["input_tokens"] == 10


def test_incremental_partial_run_preserves_untouched_semantic_hash(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path, second_doc=True)
    output = tmp_path / "out"
    dispatched: list[list[str]] = []

    def semantic(paths, **kwargs):
        dispatched.append(sorted(Path(path).name for path in paths))
        return _semantic(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    _run(monkeypatch, _extract_argv(project, output))
    before = copy.deepcopy(_semantic_cache(_store(output)))
    other_key = next(key for key in before if key.endswith(":OTHER.md"))
    (project / "README.md").write_text("# Readme\nChanged.\n")

    _run(monkeypatch, _extract_argv(project, output))

    after = _semantic_cache(_store(output))
    assert dispatched[-1] == ["README.md"]
    assert after[other_key] == before[other_key]


def test_truncated_doc_semantic_hash_is_cleared_for_requeue(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    calls = 0

    def semantic(paths, **kwargs):
        nonlocal calls
        calls += 1
        result = _semantic(paths, **kwargs)
        if calls == 2:
            for node in result["nodes"]:
                node["_partial"] = True
        return result

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    _run(monkeypatch, _extract_argv(project, output))
    (project / "README.md").write_text("# Readme\nChanged.\n")
    _run(monkeypatch, _extract_argv(project, output))
    partial = _semantic_cache(_store(output))
    readme_key = next(
        key for key in partial
        if key.startswith("semantic:") and key.endswith(":README.md")
    )
    assert partial[readme_key]["partial"] is True

    _run(monkeypatch, _extract_argv(project, output))
    assert calls == 3
    assert _semantic_cache(_store(output))[readme_key]["partial"] is False


def test_manifest_stamps_freshly_extracted_semantic_docs(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic)
    _run(monkeypatch, _extract_argv(project, output))

    loaded = load_graph(_store(output))
    assert loaded.state["incremental"]["files"]["README.md"]["content_hash"]
    assert any(key.endswith(":README.md") for key in _semantic_cache(_store(output)))
    assert not (_store(output).parent / "manifest.json").exists()


def test_stamped_manifest_files_normalizes_both_sides(tmp_path):
    doc = tmp_path / "docs" / "Guide.md"
    doc.parent.mkdir()
    doc.write_text("# Guide")
    state = {}
    saved = save_semantic_cache(
        [{"id": "guide", "source_file": str(doc)}], [], root=tmp_path,
        allowed_source_files=["docs/Guide.md"], cache=state,
    )
    assert saved == 1
    assert next(iter(state)).endswith(":docs/Guide.md")


def test_stamped_manifest_files_counts_hyperedge_only_docs(tmp_path):
    doc = tmp_path / "relationships.md"
    doc.write_text("# Relationships")
    state = {}
    saved = save_semantic_cache(
        [], [], [{"id": "h", "nodes": ["a", "b"], "source_file": "relationships.md"}],
        root=tmp_path, allowed_source_files=[doc], cache=state,
    )
    assert saved == 1
    result = next(iter(state.values()))["result"]
    assert result["nodes"] == [] and len(result["hyperedges"]) == 1


def test_manifest_stamps_hyperedge_only_docs(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    doc = project / "README.md"
    state = {}
    save_semantic_cache(
        [], [], [{"id": "h", "nodes": ["a", "b"], "source_file": doc.name}],
        root=project, cache=state,
    )
    nodes, edges, hyperedges, uncached = check_semantic_cache(
        [str(doc)], state, root=project
    )
    assert not nodes and not edges and not uncached
    assert [edge["id"] for edge in hyperedges] == ["h"]


def test_extract_mode_deep_dispatches_over_warm_cache(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    calls: list[bool] = []

    def semantic(paths, **kwargs):
        calls.append(bool(kwargs.get("deep_mode")))
        return _semantic(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    _run(monkeypatch, _extract_argv(project, output))
    _run(monkeypatch, _extract_argv(project, output, "--mode", "deep"))
    assert calls == [False, True]


def test_extract_force_flag_redispatches_and_stamps_manifest(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    calls = 0

    def semantic(paths, **kwargs):
        nonlocal calls
        calls += 1
        return _semantic(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    _run(monkeypatch, _extract_argv(project, output))
    _run(monkeypatch, _extract_argv(project, output, "--force"))
    assert calls == 2
    assert any(key.endswith(":README.md") for key in _semantic_cache(_store(output)))


def test_extract_graphify_force_env_redispatches(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    calls = 0

    def semantic(paths, **kwargs):
        nonlocal calls
        calls += 1
        return _semantic(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    _run(monkeypatch, _extract_argv(project, output))
    monkeypatch.setenv("GRAPHIFY_FORCE", "1")
    _run(monkeypatch, _extract_argv(project, output))
    assert calls == 2


def test_cache_check_mode_deep_reads_deep_namespace(monkeypatch, tmp_path, capsys):
    project = _make_corpus(tmp_path)
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic)
    _run(monkeypatch, _extract_argv(project, project, "--mode", "deep"))
    files = tmp_path / "files.txt"
    files.write_text(str(project / "README.md") + "\n")

    _run(monkeypatch, [
        "graphify", "cache-check", str(files), "--root", str(project), "--deep",
    ])
    assert "Cache: 1 hit, 0 miss" in capsys.readouterr().out


def test_extract_codeonly_succeeds_without_api_key(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)
    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--out", str(output),
    ])
    assert load_graph(_store(output)).graph.node_count > 0


def test_missing_manifest_code_only_preserves_semantic_layer(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic)
    _run(monkeypatch, _extract_argv(project, output))
    assert any("README.md" in source for source in _sources(_store(output)))

    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--out", str(output),
    ])
    assert any("README.md" in source for source in _sources(_store(output)))


def test_extract_out_keeps_project_root_clean(monkeypatch, tmp_path):
    project = _make_corpus(tmp_path)
    output = tmp_path / "elsewhere"
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic)
    _run(monkeypatch, _extract_argv(project, output))
    assert _store(output).is_dir()
    assert not (project / "graphify-out").exists()


def test_extract_without_key_still_errors_when_docs_present(monkeypatch, tmp_path, capsys):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)
    with pytest.raises(SystemExit) as exc:
        _run(monkeypatch, ["graphify", "extract", str(project), "--out", str(output)])
    assert exc.value.code == 1
    assert "no LLM backend is configured" in capsys.readouterr().err
    assert not _store(output).exists()


def test_extract_timing_flag_emits_stage_timings(monkeypatch, tmp_path, capsys):
    project = _make_corpus(tmp_path)
    output = tmp_path / "out"
    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--no-cluster",
        "--out", str(output), "--timing",
    ])
    err = capsys.readouterr().err
    assert "[graphify timing] detect:" in err
    assert "[graphify timing] total:" in err

    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--no-cluster",
        "--out", str(tmp_path / "without-timing"),
    ])
    assert "graphify timing" not in capsys.readouterr().err


def _two_file_corpus(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "x.py").write_text("def secret():\n    return 42\n")
    (project / "keep.py").write_text("def kept():\n    return 1\n")
    return project


def test_incremental_extract_prunes_newly_excluded_file_not_in_manifest(monkeypatch, tmp_path):
    project = _two_file_corpus(tmp_path)
    output = tmp_path / "out"
    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--out", str(output),
    ])
    (project / ".graphifyignore").write_text("x.py\n")
    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--out", str(output),
    ])
    sources = _sources(_store(output))
    assert not any(source.endswith("x.py") for source in sources)
    assert any(source.endswith("keep.py") for source in sources)


def test_incremental_extract_prunes_excluded_file_listed_in_manifest(monkeypatch, tmp_path):
    project = _two_file_corpus(tmp_path)
    output = tmp_path / "out"
    argv = ["graphify", "extract", str(project), "--code-only", "--out", str(output)]
    _run(monkeypatch, argv)
    assert "x.py" in load_graph(_store(output)).state["incremental"]["files"]
    (project / ".graphifyignore").write_text("x.py\n")
    _run(monkeypatch, argv)
    _run(monkeypatch, argv)
    loaded = load_graph(_store(output))
    assert "x.py" not in loaded.state["incremental"]["files"]
    assert not any(source.endswith("x.py") for source in _sources(_store(output)))


def test_no_cluster_incremental_prunes_newly_excluded_file(monkeypatch, tmp_path, capsys):
    project = _two_file_corpus(tmp_path)
    output = tmp_path / "out"
    argv = [
        "graphify", "extract", str(project), "--code-only", "--no-cluster",
        "--out", str(output),
    ]
    _run(monkeypatch, argv)
    capsys.readouterr()
    (project / ".graphifyignore").write_text("x.py\n")
    _run(monkeypatch, argv)
    assert "deleted" not in capsys.readouterr().out
    assert not any(source.endswith("x.py") for source in _sources(_store(output)))


def test_cache_check_prompt_file_scopes_hits_to_that_prompt(monkeypatch, tmp_path, capsys):
    project = _make_corpus(tmp_path)
    _run(monkeypatch, [
        "graphify", "extract", str(project), "--code-only", "--out", str(project),
    ])
    store_path = project / "graphify-out" / "graph.helix"
    loaded = load_graph(store_path)
    state = copy.deepcopy(dict(loaded.state))
    cache = state["incremental"]["extraction_cache"]
    spec = tmp_path / "extraction-spec.md"
    spec.write_text("PROMPT V1")
    save_semantic_cache(
        [{"id": "d", "source_file": "README.md"}], [], root=project,
        prompt_file=spec, cache=cache,
    )
    with HelixEmbeddedStore(store_path) as store:
        store.replace_state(state, previous_state=loaded.state)
    files = tmp_path / "files.txt"
    files.write_text(str(project / "README.md") + "\n")
    base = [
        "graphify", "cache-check", str(files), "--root", str(project),
        "--prompt-file", str(spec),
    ]
    _run(monkeypatch, base)
    assert "Cache: 1 hit, 0 miss" in capsys.readouterr().out

    spec.write_text("PROMPT V2")
    os.utime(spec, ns=(0, 0))
    _run(monkeypatch, base)
    assert "Cache: 0 hit, 1 miss" in capsys.readouterr().out
