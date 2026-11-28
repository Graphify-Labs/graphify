"""Calls through injected fields and annotated method results keep provenance."""

from pathlib import Path

import pytest

from graphify.extract import extract


FILES = {
    "models.py": (
        "class Task:\n"
        "    def complete(self): pass\n"
    ),
    "repository.py": (
        "from models import Task\n"
        "class TaskRepository:\n"
        "    def add(self, title) -> Task: return Task()\n"
        "    def get(self, key) -> Task: return Task()\n"
        "    def all(self) -> list[Task]: return []\n"
    ),
    "services.py": (
        "from models import Task\n"
        "from repository import TaskRepository\n"
        "class TaskService:\n"
        "    def __init__(self, repository: TaskRepository):\n"
        "        self.repository = repository\n"
        "    def create_task(self, title):\n"
        "        return self.repository.add(title)\n"
        "    def complete_task(self, key):\n"
        "        task = self.repository.get(key)\n"
        "        task.complete()\n"
        "    def pending_tasks(self):\n"
        "        return self.repository.all()\n"
    ),
}


def _project(root: Path, overrides=None):
    files = {**FILES, **(overrides or {})}
    for name, text in files.items():
        (root / name).write_text(text, encoding="utf-8")
    return extract([root / name for name in files], root=root, cache_root=root, parallel=False)


def _edge(result, source, target):
    return next((edge for edge in result["edges"]
                 if edge["source"] == source and edge["target"] == target
                 and edge["relation"] == "calls"), None)


@pytest.mark.parametrize(("caller", "callee", "line"), [
    ("create_task", "add", "L7"),
    ("complete_task", "get", "L9"),
    ("pending_tasks", "all", "L12"),
])
def test_injected_parameter_types_reach_member_calls(tmp_path, caller, callee, line):
    result = _project(tmp_path)
    edge = _edge(result, f"services_taskservice_{caller}", f"repository_taskrepository_{callee}")
    assert edge is not None
    assert edge["confidence"] == "INFERRED"
    assert edge["source_location"] == line
    assert edge["source_file"].endswith("services.py")


def test_annotated_method_result_types_the_local_receiver(tmp_path):
    result = _project(tmp_path)
    edge = _edge(result, "services_taskservice_complete_task", "models_task_complete")
    assert edge is not None
    assert edge["confidence"] == "INFERRED"
    assert edge["source_location"] == "L10"


@pytest.mark.parametrize("body", [
    "        task = self.repository.get(key)\n        task = unknown()\n        task.complete()\n",
    "        task = wrap(self.repository.get(key))\n        task.complete()\n",
    "        task = unknown.get(self.repository.get(key))\n        task.complete()\n",
    "        task = self.repository.get(key)\n        return lambda task: task.complete()\n",
    "        task = self.repository.get(key)\n        task = self.repository.get(key)\n        task.complete()\n",
])
def test_unknown_rebound_and_shadowed_results_do_not_guess(tmp_path, body):
    service = FILES["services.py"].split("    def complete_task")[0]
    service += "    def complete_task(self, key):\n" + body
    result = _project(tmp_path, {"services.py": service})
    assert _edge(result, "services_taskservice_complete_task", "models_task_complete") is None


@pytest.mark.parametrize("replacement", ["repository", "repository: TaskRepository"])
def test_untyped_or_rebound_injection_stays_unknown(tmp_path, replacement):
    service = FILES["services.py"].replace("repository: TaskRepository", replacement)
    if ": TaskRepository" in replacement:
        service = service.replace("        self.repository = repository", "        repository = unknown()\n        self.repository = repository")
    result = _project(tmp_path, {"services.py": service})
    assert _edge(result, "services_taskservice_create_task", "repository_taskrepository_add") is None


@pytest.mark.parametrize("annotation", ["", " -> list[Task]", " -> Task | Other", " -> Task | int", " -> Task | Unknown"])
def test_return_annotations_must_name_one_scalar_class(tmp_path, annotation):
    repository = FILES["repository.py"].replace(
        "    def get(self, key) -> Task:", f"    def get(self, key){annotation}:"
    )
    repository += "class Other:\n    def complete(self): pass\n"
    result = _project(tmp_path, {"repository.py": repository})
    assert _edge(result, "services_taskservice_complete_task", "models_task_complete") is None


def test_cache_and_changed_file_rebuild_preserve_calls(tmp_path):
    cold = _project(tmp_path)
    warm = _project(tmp_path)
    key = lambda r: sorted((e["source"], e["target"], e["confidence"])  # noqa: E731
                           for e in r["edges"] if e["relation"] == "calls")
    assert key(cold) == key(warm)
    assert _edge(warm, "services_taskservice_complete_task", "models_task_complete") is not None
    service = tmp_path / "services.py"
    service.write_text(service.read_text() + "\n# changed\n")
    context_nodes = [n for n in cold["nodes"] if n.get("source_file") != "services.py"]
    context_edges = [e for e in cold["edges"] if e.get("source_file") != "services.py"]
    changed = extract(
        [service], root=tmp_path, cache_root=tmp_path, parallel=False,
        resolution_context_nodes=context_nodes, resolution_context_edges=context_edges,
    )
    for caller, target in [
        ("create_task", "repository_taskrepository_add"),
        ("complete_task", "repository_taskrepository_get"),
        ("complete_task", "models_task_complete"),
        ("pending_tasks", "repository_taskrepository_all"),
    ]:
        assert _edge(changed, f"services_taskservice_{caller}", target) is not None


def test_changed_file_watch_rebuild_keeps_unchanged_return_annotations(tmp_path):
    import json

    from graphify.watch import _rebuild_code

    _project(tmp_path)
    assert _rebuild_code(tmp_path, no_cluster=True, acquire_lock=False, force=True)
    service = tmp_path / "services.py"
    service.write_text(service.read_text() + "\n# changed\n")
    assert _rebuild_code(tmp_path, changed_paths=[service], no_cluster=True, acquire_lock=False)
    graph = json.loads((tmp_path / "graphify-out/graph.json").read_text())
    assert _edge({"edges": graph.get("links", graph.get("edges", []))}, "services_taskservice_complete_task", "models_task_complete") is not None


def test_changed_file_cli_extract_keeps_unchanged_return_annotations(tmp_path):
    import json
    import os
    import subprocess
    import sys

    _project(tmp_path)
    command = [sys.executable, "-m", "graphify", "extract", str(tmp_path), "--code-only", "--no-cluster"]
    env = dict(os.environ, GRAPHIFY_BACKEND="none")
    for changed in (False, True):
        if changed:
            service = tmp_path / "services.py"
            service.write_text(service.read_text() + "\n# changed\n")
        run = subprocess.run(command, cwd=tmp_path, env=env, capture_output=True, text=True)
        assert run.returncode == 0, run.stderr[-2000:]
        graph = json.loads((tmp_path / "graphify-out/graph.json").read_text())
        assert _edge({"edges": graph.get("links", graph.get("edges", []))}, "services_taskservice_complete_task", "models_task_complete") is not None


def test_schema_change_retires_cached_calls_without_type_provenance(tmp_path, monkeypatch):
    import graphify.cache as cache
    from graphify.cache import save_cached
    from graphify.extract import extract_python

    _project(tmp_path)
    schema = cache._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache, "_EXTRACTOR_VERSION", "same-version")
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", 25)
    monkeypatch.setattr(cache, "_cleaned_ast_dirs", set())
    for path in sorted(tmp_path.glob("*.py")):
        result = extract_python(path, root=tmp_path)
        for node in result["nodes"]:
            node.pop("_py_return_type", None)
        for call in result.get("raw_calls", []):
            for marker in ("_python_self_attr_type", "_python_receiver_factory", "_python_call_site"):
                call.pop(marker, None)
        save_cached(path, result, root=tmp_path, cache_root=tmp_path, kind="ast")
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", schema)
    result = extract(sorted(tmp_path.glob("*.py")), root=tmp_path, cache_root=tmp_path, parallel=False)
    assert _edge(result, "services_taskservice_complete_task", "models_task_complete") is not None
