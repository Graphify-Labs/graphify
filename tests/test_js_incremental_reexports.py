"""Caller-only rebuilds resolve calls through unchanged TypeScript barrels."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from graphify import extract as extract_mod
from graphify.watch import _rebuild_code


@pytest.fixture(autouse=True)
def _requires_typescript():
    pytest.importorskip("tree_sitter_typescript")


def _write_corpus(root: Path, *, local_binding: bool = False) -> Path:
    root.mkdir()
    files = {
        "store.ts": "export interface Store { save(): void; }\nexport function createStore() {}\n",
        "index.ts": 'export * from "./store";\n',
        "bridge.ts": (
            'import { createStore as imported } from "./index";\n'
            "const local = imported;\n"
            "export { local as openStore };\n"
            if local_binding
            else 'export { createStore as openStore } from "./index";\n'
        ),
        "decoy.ts": "export function createStore() {}\nexport function openStore() {}\n",
        "main.ts": (
            'import { openStore } from "./bridge";\n'
            'import type { Store } from "./index";\n'
            "export function run(store: Store) {\n  openStore();\n  store.save();\n}\n"
        ),
    }
    for name, body in files.items():
        (root / name).write_text(body, encoding="utf-8")
    return root / "main.ts"


def _calls(root: Path) -> list[tuple[str, str, str, str, str]]:
    graph = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    nodes = {node["id"]: node for node in graph["nodes"]}
    return sorted(
        (
            nodes[link["target"]]["label"],
            nodes[link["target"]]["source_file"],
            link["source_file"],
            link["source_location"],
            link["confidence"],
        )
        for link in graph["links"]
        if link["relation"] == "calls" and nodes[link["source"]]["label"] == "run()"
    )


def _expected_calls(function_line: int) -> list[tuple[str, str, str, str, str]]:
    return [
        (".save()", "store.ts", "main.ts", f"L{function_line + 1}", "INFERRED"),
        ("createStore()", "store.ts", "main.ts", f"L{function_line}", "EXTRACTED"),
    ]


def _watch(root: Path, *, changed: Path | None = None, force: bool = False) -> None:
    assert _rebuild_code(
        root,
        changed_paths=[changed] if changed else None,
        no_cluster=True,
        acquire_lock=False,
        force=force,
    )


def _cli(root: Path, *, force: bool = False) -> None:
    command = [sys.executable, "-m", "graphify", "extract", ".", "--code-only"]
    if force:
        command.append("--force")
    result = subprocess.run(
        command,
        cwd=root,
        env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr


@pytest.mark.parametrize("runner", ["cli", "watcher"])
@pytest.mark.parametrize("local_binding", [False, True])
def test_caller_only_edit_preserves_calls_through_unchanged_barrels(
    tmp_path, monkeypatch, runner, local_binding
):
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    caller = _write_corpus(tmp_path / "corpus", local_binding=local_binding)
    rebuild = _cli if runner == "cli" else _watch

    rebuild(caller.parent)
    assert _calls(caller.parent) == _expected_calls(4)

    # Shift both call sites so a preserved edge with stale provenance fails too.
    caller.write_text("// caller edit\n" + caller.read_text(encoding="utf-8"), encoding="utf-8")

    if runner == "watcher":
        batches = []
        extract = extract_mod.extract

        def record_extract(paths, **kwargs):
            batches.append(list(paths))
            return extract(paths, **kwargs)

        monkeypatch.setattr(extract_mod, "extract", record_extract)
        _watch(caller.parent, changed=caller)
        assert batches == [[caller]]
    else:
        _cli(caller.parent)

    incremental = _calls(caller.parent)
    rebuild(caller.parent, force=True)
    assert _calls(caller.parent) == _expected_calls(5)
    assert incremental == _calls(caller.parent)


def test_caller_edit_cannot_resolve_through_deleted_reexport_target(tmp_path, monkeypatch):
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    caller = _write_corpus(tmp_path / "corpus")
    _watch(caller.parent)
    assert _calls(caller.parent) == _expected_calls(4)

    (caller.parent / "store.ts").unlink()
    caller.write_text("// caller edit\n" + caller.read_text(encoding="utf-8"), encoding="utf-8")
    _watch(caller.parent, changed=caller)

    assert _calls(caller.parent) == []
