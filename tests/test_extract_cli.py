"""Helix-only tests for the ``graphify extract`` and ``update`` commands."""

from __future__ import annotations

from pathlib import Path

import pytest

import graphify.__main__ as mainmod
from graphify.helix.model import node_attributes
from graphify.helix.persistence import load_graph


def _run(monkeypatch, argv: list[str]) -> None:
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv", argv)
    mainmod.main()


def _corpus(tmp_path: Path, *, docs: bool = True) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / "app.py").write_text("def app():\n    return 1\n")
    if docs:
        (root / "design.md").write_text("# Design\nNative graph.\n")
    return root


def _semantic_result(paths, **kwargs):
    return {
        "nodes": [
            {
                "id": Path(path).stem,
                "label": Path(path).stem.title(),
                "file_type": "document",
                "source_file": Path(path).name,
            }
            for path in paths
        ],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 10,
        "output_tokens": 5,
        "failed_chunks": 0,
    }


def _node_sources(store: Path) -> set[str]:
    graph = load_graph(store).graph
    return {
        str(node_attributes(graph, node.id).get("source_file", ""))
        for node in graph.nodes()
    }


def test_code_only_extract_creates_only_native_store(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path, docs=False)
    output = tmp_path / "output"

    _run(monkeypatch, ["graphify", "extract", str(project), "--code-only", "--out", str(output)])

    store = output / "graphify-out" / "graph.helix"
    loaded = load_graph(store)
    assert loaded.graph.node_count > 0
    assert loaded.state["build"]["source_root"] == str(project.resolve())
    assert not (output / "graphify-out" / "graph.json").exists()
    assert not (project / "graphify-out").exists()


@pytest.mark.parametrize(
    "postgres_args",
    [["--postgres", "test-dsn"], ["--postgres=test-dsn"]],
)
@pytest.mark.parametrize("cluster_args", [[], ["--no-cluster"]])
def test_pathless_postgres_extract_initializes_empty_detection(
    monkeypatch, tmp_path, postgres_args, cluster_args
):
    """A pathless database extraction replaces, then yields to, a file corpus."""
    calls = []

    def _introspect(dsn):
        calls.append(dsn)
        return {
            "nodes": [
                {
                    "id": "postgresql_users",
                    "label": "users",
                    "type": "table",
                    "file_type": "code",
                    "source_file": "postgresql:/localhost/test",
                }
            ],
            "edges": [],
        }

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "app.py").write_text("def app():\n    return 1\n")
    launcher = tmp_path / "launcher"
    launcher.mkdir()
    monkeypatch.chdir(launcher)
    output = tmp_path / "output"
    store = output / "graphify-out" / "graph.helix"
    monkeypatch.setattr("graphify.pg_introspect.introspect_postgres", _introspect)

    _run(
        monkeypatch,
        [
            "graphify", "extract", str(corpus), "--code-only", "--no-cluster",
            "--out", str(output),
        ],
    )
    assert "app.py" in _node_sources(store)

    _run(
        monkeypatch,
        ["graphify", "extract", *postgres_args, *cluster_args, "--out", str(output)],
    )
    assert calls == ["test-dsn"]
    assert _node_sources(store) == {"postgresql:/localhost/test"}
    assert load_graph(store).state["incremental"]["files"] == {}

    _run(
        monkeypatch,
        [
            "graphify", "extract", str(corpus), "--code-only", "--no-cluster",
            "--out", str(output),
        ],
    )
    final_sources = _node_sources(store)
    assert "app.py" in final_sources
    assert "postgresql:/localhost/test" not in final_sources


def test_postgres_extraction_with_source_survives_incremental_update(
    monkeypatch, tmp_path
):
    """A mixed source/database corpus retains its database DTO on update."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    source = corpus / "app.py"
    source.write_text("def app():\n    return 1\n")
    output = tmp_path / "output"
    store = output / "graphify-out" / "graph.helix"
    monkeypatch.setattr(
        "graphify.pg_introspect.introspect_postgres",
        lambda _dsn: {
            "nodes": [
                {
                    "id": "postgresql_users",
                    "label": "users",
                    "file_type": "code",
                    "source_file": "postgresql:/localhost/test",
                }
            ],
            "edges": [],
        },
    )

    _run(
        monkeypatch,
        [
            "graphify", "extract", str(corpus), "--code-only", "--no-cluster",
            "--postgres", "test-dsn", "--out", str(output),
        ],
    )
    assert {"app.py", "postgresql:/localhost/test"} <= _node_sources(store)

    source.write_text("def app():\n    return 2\n")
    _run(
        monkeypatch,
        [
            "graphify", "update", str(corpus), "--no-cluster",
            "--changed", "app.py", "--out", str(output),
        ],
    )
    assert {"app.py", "postgresql:/localhost/test"} <= _node_sources(store)


def test_postgres_cli_reports_connection_error(monkeypatch, tmp_path, capsys):
    """Database failures use the normal CLI error path rather than a traceback."""
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(
        "graphify.pg_introspect.introspect_postgres",
        lambda _dsn: (_ for _ in ()).throw(ConnectionError("database unavailable")),
    )
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(
        mainmod.sys,
        "argv",
        ["graphify", "extract", "--postgres", "test-dsn", "--no-cluster"],
    )

    with pytest.raises(SystemExit) as exc_info:
        mainmod.main()

    assert exc_info.value.code == 1
    assert "error: database unavailable" in capsys.readouterr().err


def test_semantic_extract_persists_cache_and_tokens(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", _semantic_result)

    _run(monkeypatch, [
        "graphify", "extract", str(project), "--backend", "openai", "--out", str(output),
    ])

    loaded = load_graph(output / "graphify-out" / "graph.helix")
    assert loaded.state["semantic"]["used"] is True
    assert loaded.state["semantic"]["input_tokens"] == 10
    assert any(
        key.startswith("semantic:")
        for key in loaded.state["incremental"]["extraction_cache"]
    )


def test_failed_semantic_extract_does_not_activate_store(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(
        "graphify.llm.extract_corpus_parallel",
        lambda *args, **kwargs: {
            "nodes": [], "edges": [], "hyperedges": [],
            "input_tokens": 0, "output_tokens": 0, "failed_chunks": 1,
        },
    )

    with pytest.raises(SystemExit) as error:
        _run(monkeypatch, [
            "graphify", "extract", str(project), "--backend", "openai", "--out", str(output),
        ])

    assert error.value.code == 1
    assert not (output / "graphify-out" / "graph.helix").exists()


def test_missing_backend_fails_with_rebuild_unactivated(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr("graphify.llm.detect_backend", lambda: None)

    with pytest.raises(SystemExit) as error:
        _run(monkeypatch, ["graphify", "extract", str(project), "--out", str(output)])

    assert error.value.code == 1
    assert not (output / "graphify-out" / "graph.helix").exists()


def test_warm_semantic_cache_avoids_backend(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path)
    output = tmp_path / "output"
    calls = []

    def semantic(paths, **kwargs):
        calls.append(list(paths))
        return _semantic_result(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    argv = ["graphify", "extract", str(project), "--backend", "openai", "--out", str(output)]
    _run(monkeypatch, argv)
    _run(monkeypatch, argv)
    assert len(calls) == 1


def test_force_redispatches_warm_semantic_cache(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path)
    output = tmp_path / "output"
    calls = []

    def semantic(paths, **kwargs):
        calls.append(list(paths))
        return _semantic_result(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    base = ["graphify", "extract", str(project), "--backend", "openai", "--out", str(output)]
    _run(monkeypatch, base)
    _run(monkeypatch, [*base, "--force"])
    assert len(calls) == 2


def test_deep_cache_namespace_is_separate(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path)
    output = tmp_path / "output"
    calls = []

    def semantic(paths, **kwargs):
        calls.append(kwargs.get("deep_mode"))
        return _semantic_result(paths, **kwargs)

    monkeypatch.setattr("graphify.llm.extract_corpus_parallel", semantic)
    base = ["graphify", "extract", str(project), "--backend", "openai", "--out", str(output)]
    _run(monkeypatch, base)
    _run(monkeypatch, [*base, "--mode", "deep"])
    loaded = load_graph(output / "graphify-out" / "graph.helix")
    assert calls == [False, True]
    assert any(
        key.startswith("semantic-deep:")
        for key in loaded.state["incremental"]["extraction_cache"]
    )


def test_update_changed_file_and_deletion(monkeypatch, tmp_path: Path) -> None:
    project = _corpus(tmp_path, docs=False)
    second = project / "other.py"
    second.write_text("VALUE = 1\n")
    output = tmp_path / "output"
    _run(monkeypatch, ["graphify", "extract", str(project), "--code-only", "--out", str(output)])
    second.unlink()

    _run(monkeypatch, [
        "graphify", "update", str(project), "--changed", str(second), "--out", str(output),
    ])

    loaded = load_graph(output / "graphify-out" / "graph.helix")
    sources = {
        node_attributes(loaded.graph, node.id).get("source_file")
        for node in loaded.graph.nodes()
    }
    assert "other.py" not in sources


def test_json_graph_path_is_rejected(monkeypatch, tmp_path: Path) -> None:
    legacy = tmp_path / "graph.json"
    legacy.write_text("{}")
    with pytest.raises(SystemExit) as error:
        _run(monkeypatch, ["graphify", "query", "thing", "--graph", str(legacy)])
    assert error.value.code == 1
