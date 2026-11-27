"""An incremental update must give the same ids as a full build when files collide.

``sample.c`` and ``sample.h`` (or ``index.ts`` and ``index.js``) produce the same
raw node ids, and extract() salts them apart with the source path. It can only do
that for files extracted in one batch, and an update re-extracted just the changed
file: the edited file fell back to the bare id a full build never uses, and a
deleted file left its sibling on a salted id. Each test compares the update's
graph with a fresh full build of the same tree.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


# Both incremental entry points: `update` (watch._rebuild_code) and a repeated
# `extract` on an existing graph (the CLI's own incremental path).
_COMMANDS = {
    "update": ["update", "."],
    "extract": ["extract", ".", "--code-only", "--no-cluster"],
}


def _update(project: Path, command: str = "update") -> None:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    env["GRAPHIFY_BACKEND"] = "none"
    result = subprocess.run(
        [sys.executable, "-m", "graphify", *_COMMANDS[command]],
        cwd=project, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr


def _shape(project: Path) -> tuple[set[str], set[tuple[str, str, str]]]:
    graph = json.loads((project / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    nodes = {node["id"] for node in graph["nodes"]}
    edges = {
        (edge["source"], edge["target"], edge["relation"])
        for edge in graph.get("links", graph.get("edges", []))
    }
    return nodes, edges


def _write_tree(root: Path) -> None:
    (root / "src").mkdir(parents=True)
    (root / "src" / "math.h").write_text(
        "struct point { int x; int y; };\nint add(int a, int b);\n", encoding="utf-8"
    )
    (root / "src" / "math.c").write_text(
        '#include "math.h"\n'
        "int add(int a, int b) { return a + b; }\n"
        "int twice(int a) { return add(a, a); }\n",
        encoding="utf-8",
    )
    (root / "api").mkdir()
    (root / "api" / "index.ts").write_text(
        "export class Client { get(): number { return 1 } }\n", encoding="utf-8"
    )
    (root / "api" / "index.js").write_text(
        "class Client { get() { return 2 } }\nmodule.exports = { Client }\n",
        encoding="utf-8",
    )


def _touch(path: Path) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write("// touched\n")


@pytest.mark.parametrize("command", sorted(_COMMANDS))
@pytest.mark.parametrize(
    "change",
    [
        pytest.param(lambda root: _touch(root / "src" / "math.c"), id="edit-c-source"),
        pytest.param(lambda root: _touch(root / "api" / "index.js"), id="edit-js-twin"),
        pytest.param(lambda root: (root / "src" / "math.h").unlink(), id="delete-header"),
        pytest.param(lambda root: (root / "api" / "index.js").unlink(), id="delete-js-twin"),
        pytest.param(
            lambda root: (root / "src" / "math.cpp").write_text(
                "int sub(int a, int b) { return a - b; }\n", encoding="utf-8"
            ),
            id="add-third-sibling",
        ),
    ],
)
def test_update_matches_full_build_for_colliding_files(tmp_path, change, command):
    incremental = tmp_path / "incremental"
    _write_tree(incremental)
    _update(incremental, command)
    change(incremental)
    _update(incremental, command)

    full = tmp_path / "full"
    _write_tree(full)
    change(full)
    _update(full, command)

    inc_nodes, inc_edges = _shape(incremental)
    full_nodes, full_edges = _shape(full)
    assert inc_nodes == full_nodes, (
        f"only in update: {sorted(inc_nodes - full_nodes)}; "
        f"only in full build: {sorted(full_nodes - inc_nodes)}"
    )
    assert inc_edges == full_edges


def test_update_drops_reference_node_whose_only_referrer_was_deleted(tmp_path):
    """A sourceless base-type node must go with the last file that referenced it."""
    incremental = tmp_path / "incremental"
    incremental.mkdir()
    (incremental / "lists.kt").write_text(
        "class LoggingList<T> : MutableList<T> by ArrayList()\n", encoding="utf-8"
    )
    (incremental / "other.kt").write_text("class Other\n", encoding="utf-8")
    _update(incremental)
    before, _ = _shape(incremental)
    assert "mutablelist" in before

    (incremental / "lists.kt").unlink()
    _update(incremental)

    full = tmp_path / "full"
    full.mkdir()
    shutil.copy(incremental / "other.kt", full / "other.kt")
    _update(full)
    assert _shape(incremental) == _shape(full)
