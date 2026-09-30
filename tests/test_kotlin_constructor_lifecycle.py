"""End-to-end lifecycle coverage for the bounded Kotlin constructor-local edge."""
from __future__ import annotations

import importlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.kotlin_constructor_locals import GRAPH_MARKER, SCHEMA
from graphify.watch import _rebuild_code


_PROVIDER = """package demo

class Service {
    fun run(enabled: Boolean) { }
}
"""

_CALLER = """package demo

fun caller() {
    val view = Service()
    view.run(true)
}
"""


def _graph(corpus: Path) -> dict:
    return json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _output_bytes(corpus: Path) -> dict[str, bytes]:
    out = corpus / "graphify-out"
    snapshots = {}
    for path in out.rglob("*"):
        relative = path.relative_to(out)
        if (
            not path.is_file()
            or path.name == ".pending_changes"
            or relative.parts[0] == "cache"
        ):
            continue
        snapshots[str(relative)] = path.read_bytes()
    return snapshots


def _calls(graph: dict) -> list[dict]:
    return [
        edge
        for edge in graph.get("links", graph.get("edges", []))
        if edge.get("relation") == "calls"
    ]


def _seed(corpus: Path) -> tuple[Path, Path]:
    corpus.mkdir()
    provider = corpus / "Provider.kt"
    caller = corpus / "Caller.kt"
    provider.write_text(_PROVIDER, encoding="utf-8")
    caller.write_text(_CALLER, encoding="utf-8")
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    return provider, caller


def _seed_clustered(corpus: Path) -> tuple[Path, Path]:
    corpus.mkdir()
    provider = corpus / "Provider.kt"
    caller = corpus / "Caller.kt"
    provider.write_text(_PROVIDER, encoding="utf-8")
    caller.write_text(_CALLER, encoding="utf-8")
    assert _rebuild_code(corpus, acquire_lock=False) is True
    return provider, caller


def _extract_cli(corpus: Path, *extra_args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "graphify",
            "extract",
            str(corpus),
            "--code-only",
            "--no-cluster",
            *extra_args,
        ],
        cwd=corpus,
        capture_output=True,
        text=True,
    )


def test_provider_change_rebuilds_unchanged_kotlin_caller_and_evicts_edge(tmp_path):
    """A provider-only edit replays the unchanged caller's raw proof."""
    corpus = tmp_path / "corpus"
    provider, _caller = _seed(corpus)
    before = _graph(corpus)
    assert any(
        edge.get("confidence") == "INFERRED" for edge in _calls(before)
    )

    provider.write_text(
        "package demo\n\nclass Service {\n    fun gone(enabled: Boolean) { }\n}\n",
        encoding="utf-8",
    )
    assert _rebuild_code(
        corpus, changed_paths=[provider], no_cluster=True, acquire_lock=False
    ) is True

    after = _graph(corpus)
    labels = {node["id"]: node["label"] for node in after["nodes"]}
    assert not any(
        labels.get(edge.get("target")) == ".run()" for edge in _calls(after)
    )
    assert after["graph"][GRAPH_MARKER] == SCHEMA


def test_cli_incremental_provider_change_rebuilds_unchanged_kotlin_caller(tmp_path):
    """The standalone extract command takes the same complete Kotlin path."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    provider = corpus / "Provider.kt"
    provider.write_text(_PROVIDER, encoding="utf-8")
    (corpus / "Caller.kt").write_text(_CALLER, encoding="utf-8")
    first = _extract_cli(corpus)
    assert first.returncode == 0, first.stderr

    provider.write_text(
        "package demo\n\nclass Service {\n    fun gone(enabled: Boolean) { }\n}\n",
        encoding="utf-8",
    )
    second = _extract_cli(corpus)
    assert second.returncode == 0, second.stderr

    after = _graph(corpus)
    labels = {node["id"]: node["label"] for node in after["nodes"]}
    assert not any(
        labels.get(edge.get("target")) == ".run()" for edge in _calls(after)
    )
    assert after["graph"][GRAPH_MARKER] == SCHEMA


def test_missing_graph_marker_migrates_unchanged_kotlin_sources(tmp_path):
    """An old graph receives the Kotlin batch even when only Python changed."""
    corpus = tmp_path / "corpus"
    _seed(corpus)
    graph_path = corpus / "graphify-out" / "graph.json"
    legacy = json.loads(graph_path.read_text(encoding="utf-8"))
    legacy.setdefault("graph", {}).pop(GRAPH_MARKER, None)
    graph_path.write_text(json.dumps(legacy), encoding="utf-8")

    other = corpus / "other.py"
    other.write_text("def keep():\n    return 1\n", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[other], no_cluster=True, acquire_lock=False
    ) is True

    migrated = _graph(corpus)
    assert migrated["graph"][GRAPH_MARKER] == SCHEMA
    assert any(edge.get("confidence") == "INFERRED" for edge in _calls(migrated))


def test_clustered_marker_migration_writes_unchanged_kotlin_sources(tmp_path):
    """Clustered rebuilds cannot return early before persisting migration."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "Provider.kt").write_text(_PROVIDER, encoding="utf-8")
    (corpus / "Caller.kt").write_text(_CALLER, encoding="utf-8")
    other = corpus / "other.py"
    other.write_text("def keep():\n    return 1\n", encoding="utf-8")
    assert _rebuild_code(corpus, acquire_lock=False) is True

    graph_path = corpus / "graphify-out" / "graph.json"
    legacy = json.loads(graph_path.read_text(encoding="utf-8"))
    legacy.setdefault("graph", {}).pop(GRAPH_MARKER, None)
    graph_path.write_text(json.dumps(legacy), encoding="utf-8")
    other.write_text("def keep():\n    return 2\n", encoding="utf-8")

    assert _rebuild_code(corpus, changed_paths=[other], acquire_lock=False) is True
    assert _graph(corpus)["graph"][GRAPH_MARKER] == SCHEMA


def test_final_kotlin_deletion_prunes_output_and_advances_marker(tmp_path):
    """A zero-live-Kotlin refresh needs no resolver receipt but still persists."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    provider = corpus / "Provider.kt"
    provider.write_text(_PROVIDER, encoding="utf-8")
    (corpus / "other.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True

    provider.unlink()
    assert _rebuild_code(
        corpus, changed_paths=[provider], no_cluster=True, acquire_lock=False
    ) is True

    after = _graph(corpus)
    assert all(not str(node.get("source_file", "")).endswith("Provider.kt") for node in after["nodes"])
    assert after["graph"][GRAPH_MARKER] == SCHEMA


def test_ignore_rule_refreshes_callers_when_provider_is_absent_from_changed_paths(tmp_path):
    """An ignore-file event still invalidates callers of its removed provider."""
    corpus = tmp_path / "corpus"
    _provider, _caller = _seed(corpus)
    ignore = corpus / ".graphifyignore"
    ignore.write_text("Provider.kt\n", encoding="utf-8")

    assert _rebuild_code(
        corpus, changed_paths=[ignore], no_cluster=True, acquire_lock=False
    ) is True

    after = _graph(corpus)
    labels = {node["id"]: node["label"] for node in after["nodes"]}
    assert "Service" not in labels.values()
    assert not any(
        labels.get(edge.get("target")) == ".run()" for edge in _calls(after)
    )


def test_incomplete_kotlin_batch_leaves_existing_graph_for_retry(tmp_path, monkeypatch):
    """A missing resolver receipt must not reconcile or write a partial graph."""
    corpus = tmp_path / "corpus"
    provider, _caller = _seed(corpus)
    before = _output_bytes(corpus)
    provider.write_text(
        "package demo\n\nclass Service {\n    fun gone(enabled: Boolean) { }\n}\n",
        encoding="utf-8",
    )

    extract_module = importlib.import_module("graphify.extract")
    real_extract = extract_module.extract

    def incomplete_extract(*args, **kwargs):
        result = real_extract(*args, **kwargs)
        result["_kotlin_constructor_local_complete"] = False
        return result

    monkeypatch.setattr(extract_module, "extract", incomplete_extract)
    assert _rebuild_code(corpus, changed_paths=[provider], no_cluster=True) is False
    assert _output_bytes(corpus) == before
    assert (corpus / "graphify-out" / ".pending_changes").exists()


@pytest.mark.parametrize(
    ("branch", "expected_state"),
    [
        ("raw", "advanced"),
        ("clustered", "advanced"),
        ("unchanged", "was unchanged"),
    ],
)
def test_manifest_failure_keeps_old_hashes_and_requeues_retry(
    tmp_path, monkeypatch, capsys, branch, expected_state
):
    """Each post-graph manifest path returns failure with an honest diagnosis."""
    corpus = tmp_path / "corpus"
    if branch == "raw":
        provider, _caller = _seed(corpus)
        no_cluster = True
    else:
        provider, _caller = _seed_clustered(corpus)
        no_cluster = False
    manifest_path = corpus / "graphify-out" / "manifest.json"
    old_manifest = manifest_path.read_bytes()
    if branch == "unchanged":
        provider.write_text(_PROVIDER + "\n// source-only change\n", encoding="utf-8")
    else:
        provider.write_text(
            "package demo\n\nclass Service {\n    fun gone(enabled: Boolean) { }\n}\n",
            encoding="utf-8",
        )

    detect_module = importlib.import_module("graphify.detect")

    def manifest_failed(*args, **kwargs):
        raise OSError("injected manifest failure")

    monkeypatch.setattr(detect_module, "save_manifest", manifest_failed)
    assert _rebuild_code(
        corpus, changed_paths=[provider], no_cluster=no_cluster, acquire_lock=False
    ) is False
    assert manifest_path.read_bytes() == old_manifest
    assert (corpus / "graphify-out" / ".pending_changes").exists()
    assert expected_state in capsys.readouterr().err

    monkeypatch.undo()
    assert _rebuild_code(corpus, changed_paths=[provider], no_cluster=no_cluster) is True
    assert not (corpus / "graphify-out" / ".pending_changes").exists()


def _has_run_edge(corpus: Path) -> bool:
    graph = _graph(corpus)
    labels = {node["id"]: node["label"] for node in graph["nodes"]}
    return any(labels.get(edge.get("target")) == ".run()" for edge in _calls(graph))


def _java_shadow(name: str = "Boolean") -> str:
    return f"package demo;\n\nclass {name} {{ }}\n"


def test_java_shadow_add_replays_unchanged_kotlin_caller(tmp_path):
    corpus = tmp_path / "corpus"
    _seed(corpus)
    java = corpus / "Shadow.java"
    java.write_text(_java_shadow(), encoding="utf-8")

    assert _rebuild_code(
        corpus, changed_paths=[java], no_cluster=True, acquire_lock=False
    ) is True
    assert not _has_run_edge(corpus)


def test_java_shadow_change_replays_unchanged_kotlin_caller(tmp_path):
    corpus = tmp_path / "corpus"
    _seed(corpus)
    java = corpus / "Shadow.java"
    java.write_text(_java_shadow("Other"), encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[java], no_cluster=True, acquire_lock=False
    ) is True
    assert _has_run_edge(corpus)

    java.write_text(_java_shadow(), encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[java], no_cluster=True, acquire_lock=False
    ) is True
    assert not _has_run_edge(corpus)


def test_java_shadow_deletion_restores_unchanged_kotlin_caller(tmp_path):
    corpus = tmp_path / "corpus"
    _seed(corpus)
    java = corpus / "Shadow.java"
    java.write_text(_java_shadow(), encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[java], no_cluster=True, acquire_lock=False
    ) is True
    assert not _has_run_edge(corpus)

    java.unlink()
    assert _rebuild_code(
        corpus, changed_paths=[java], no_cluster=True, acquire_lock=False
    ) is True
    assert _has_run_edge(corpus)


def test_ignored_java_shadow_restores_unchanged_kotlin_caller(tmp_path):
    corpus = tmp_path / "corpus"
    _seed(corpus)
    java = corpus / "Shadow.java"
    java.write_text(_java_shadow(), encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[java], no_cluster=True, acquire_lock=False
    ) is True
    assert not _has_run_edge(corpus)

    ignore = corpus / ".graphifyignore"
    ignore.write_text("Shadow.java\n", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[ignore], no_cluster=True, acquire_lock=False
    ) is True
    assert _has_run_edge(corpus)


@pytest.mark.parametrize(
    ("name", "source"),
    [
        ("Unsupported.scala", "object Unsupported {}\n"),
        ("Unsupported.groovy", "class Unsupported {}\n"),
        ("build.gradle", "class Unsupported {}\n"),
    ],
)
def test_unsupported_jvm_source_successfully_abstains_and_restores_on_delete(
    tmp_path, name, source
):
    corpus = tmp_path / "corpus"
    _seed(corpus)
    unsupported = corpus / name
    unsupported.write_text(source, encoding="utf-8")

    assert _rebuild_code(
        corpus, changed_paths=[unsupported], no_cluster=True, acquire_lock=False
    ) is True
    assert not _has_run_edge(corpus)
    assert _graph(corpus)["graph"][GRAPH_MARKER] == SCHEMA

    unsupported.unlink()
    assert _rebuild_code(
        corpus, changed_paths=[unsupported], no_cluster=True, acquire_lock=False
    ) is True
    assert _has_run_edge(corpus)


def test_cli_incremental_java_shadow_replays_unchanged_kotlin_caller(tmp_path):
    """CLI selection includes Java negative evidence with a live Kotlin caller."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "Provider.kt").write_text(_PROVIDER, encoding="utf-8")
    (corpus / "Caller.kt").write_text(_CALLER, encoding="utf-8")
    first = _extract_cli(corpus)
    assert first.returncode == 0, first.stderr
    assert _has_run_edge(corpus)

    java = corpus / "Shadow.java"
    java.write_text(_java_shadow(), encoding="utf-8")
    second = _extract_cli(corpus)
    assert second.returncode == 0, second.stderr
    assert not _has_run_edge(corpus)


def test_restoring_ignored_java_shadow_replays_unchanged_kotlin_caller(tmp_path):
    """A changed ignore file can reintroduce Java evidence absent from graph.json."""
    corpus = tmp_path / "corpus"
    _seed(corpus)
    java = corpus / "Shadow.java"
    java.write_text(_java_shadow(), encoding="utf-8")
    ignore = corpus / ".graphifyignore"
    ignore.write_text("Shadow.java\n", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[ignore], no_cluster=True, acquire_lock=False
    ) is True
    assert _has_run_edge(corpus)

    ignore.write_text("", encoding="utf-8")
    assert _rebuild_code(
        corpus, changed_paths=[ignore], no_cluster=True, acquire_lock=False
    ) is True
    assert not _has_run_edge(corpus)


def test_ignoring_all_jvm_sources_completes_final_kotlin_migration(tmp_path):
    """No live JVM path still refreshes when the prior graph owned Kotlin."""
    corpus = tmp_path / "corpus"
    provider, caller = _seed(corpus)
    (corpus / "other.py").write_text("def keep():\n    return 1\n", encoding="utf-8")
    ignore = corpus / ".graphifyignore"
    ignore.write_text("Provider.kt\nCaller.kt\n", encoding="utf-8")

    assert _rebuild_code(
        corpus, changed_paths=[ignore], no_cluster=True, acquire_lock=False
    ) is True
    graph = _graph(corpus)
    assert all(
        Path(str(node.get("source_file", ""))).name not in {provider.name, caller.name}
        for node in graph["nodes"]
    )
    assert graph["graph"][GRAPH_MARKER] == SCHEMA


def test_actual_kotlin_parse_error_preserves_watch_graph_and_requeues(tmp_path):
    """A parser error is a required-proof failure before watch publication."""
    corpus = tmp_path / "corpus"
    provider, _caller = _seed(corpus)
    before = _output_bytes(corpus)
    provider.write_text("package demo\n\nclass Service {\n", encoding="utf-8")

    assert _rebuild_code(
        corpus, changed_paths=[provider], no_cluster=True, acquire_lock=False
    ) is False
    assert _output_bytes(corpus) == before
    assert (corpus / "graphify-out" / ".pending_changes").exists()


def test_actual_kotlin_parse_error_hard_fails_cli_allow_partial(tmp_path):
    """--allow-partial cannot publish an incomplete required Kotlin batch."""
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    provider = corpus / "Provider.kt"
    provider.write_text(_PROVIDER, encoding="utf-8")
    (corpus / "Caller.kt").write_text(_CALLER, encoding="utf-8")
    first = _extract_cli(corpus)
    assert first.returncode == 0, first.stderr
    graph_path = corpus / "graphify-out" / "graph.json"
    before = graph_path.read_bytes()

    provider.write_text("package demo\n\nclass Service {\n", encoding="utf-8")
    failed = _extract_cli(corpus, "--allow-partial")
    assert failed.returncode == 1
    assert graph_path.read_bytes() == before
