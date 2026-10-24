"""`affected <path>` must find the file node for a file whose basename is shared.

#4698: a path query resolves through ``source_file``, which matches every node in
the file, so resolution ends in ``_prefer_file_node``. Its three passes each
assume something the graph no longer guarantees:

- the file node's label is the bare basename — false since #2032 relabelled
  colliding basenames to their shortest unique path suffix (``alpha/hooks.py``);
- the file node is the only node at ``L1`` — false whenever the module's
  docstring (a ``rationale`` node, located on the docstring's own line) or a
  one-line top-level definition also lands on line 1;
- the label is the bare basename again.

Both preconditions must hold to fail: a unique basename, or a second node below
L1, resolves today. The graph-level tests pin the resolver against the exact node
shapes; the CLI tests run the repro from the issue end to end.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import networkx as nx

from graphify.affected import load_graph, resolve_seed

PYTHON = sys.executable

_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)


def _graph_with_shared_basename(
    *, extra_l1: tuple[str, str, str] | None = None
) -> nx.DiGraph:
    """The nodes #2032's relabel plus the rationale pass leave in the file.

    ``extra_l1`` is an ``(id, label, file_type)`` second node on line 1, or
    ``None`` for the control where only the file node is on L1.
    """
    graph = nx.DiGraph()
    graph.add_node(
        "app_alpha_hooks",
        label="alpha/hooks.py",
        source_file="app/alpha/hooks.py",
        source_location="L1",
        file_type="code",
    )
    graph.add_node(
        "app_alpha_hooks_check",
        label="check()",
        source_file="app/alpha/hooks.py",
        source_location="L4",
        file_type="code",
    )
    if extra_l1 is not None:
        node_id, label, file_type = extra_l1
        graph.add_node(
            node_id,
            label=label,
            source_file="app/alpha/hooks.py",
            source_location="L1",
            file_type=file_type,
        )
    return graph


def test_shared_basename_with_module_docstring_on_l1_resolves_file_node():
    """The reported shape: disambiguated label plus a docstring rationale on L1."""
    graph = _graph_with_shared_basename(
        extra_l1=(
            "app_alpha_hooks_rationale_1",
            "Checks a request before it runs.",
            "rationale",
        )
    )

    assert resolve_seed(graph, "app/alpha/hooks.py") == "app_alpha_hooks"


def test_shared_basename_with_one_line_definition_on_l1_resolves_file_node():
    """No docstring, but ``def check(...): ...`` on line 1 is an L1 code node.

    The rationale node is only the common way to get a second node on L1; the
    tie is the defect, not the docstring.
    """
    graph = _graph_with_shared_basename(
        extra_l1=("app_alpha_hooks_check", "check()", "code")
    )

    assert resolve_seed(graph, "app/alpha/hooks.py") == "app_alpha_hooks"


def test_shared_basename_resolves_from_absolute_path(tmp_path):
    """#2706 made absolute-path seeds repo-relative; the file-node pick must hold."""
    graph = _graph_with_shared_basename(
        extra_l1=(
            "app_alpha_hooks_rationale_1",
            "Checks a request before it runs.",
            "rationale",
        )
    )

    absolute = str(tmp_path / "app" / "alpha" / "hooks.py")
    assert resolve_seed(graph, absolute, root=tmp_path) == "app_alpha_hooks"


def test_ambiguous_file_shaped_labels_still_refuse_to_guess():
    """Two nodes both claiming a path form of the file must not be guessed between."""
    graph = nx.DiGraph()
    for node_id in ("one", "two"):
        graph.add_node(
            node_id,
            label="alpha/hooks.py",
            source_file="app/alpha/hooks.py",
            source_location="L1",
        )

    assert resolve_seed(graph, "app/alpha/hooks.py") is None


def _run_graphify(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    return subprocess.run(
        [PYTHON, "-m", "graphify"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
        env=env,
    )


def _write_repro(root: Path, *, head: str) -> None:
    """The issue's minimal repro: two same-named modules, one consumer.

    ``head`` is what precedes ``def check(...)``: the module docstring (an L1
    rationale node), a plain comment (no rationale node), or nothing.
    """
    (root / "app" / "alpha").mkdir(parents=True)
    (root / "app" / "beta").mkdir(parents=True)
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "alpha" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "beta" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "main.py").write_text(
        "from app.alpha.hooks import check\n"
        "\n"
        "\n"
        "def handle(request):\n"
        "    return check(request)\n",
        encoding="utf-8",
    )
    body = head + "def check(request):\n    return bool(request)\n"
    for crate in ("alpha", "beta"):
        (root / "app" / crate / "hooks.py").write_text(body, encoding="utf-8")


def _build(root: Path) -> dict:
    result = _run_graphify(
        ["update", str(root), "--force", "--no-cluster"], cwd=root
    )
    assert result.returncode == 0, result.stderr[-2000:]
    return json.loads(
        (root / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    )


def _file_node_id(graph: dict, source_file: str) -> str:
    matches = [
        node["id"]
        for node in graph["nodes"]
        if node.get("source_file") == source_file
        and node.get("source_location") == "L1"
        and node.get("file_type") == "code"
        and "/" in str(node.get("label", ""))
    ]
    assert len(matches) == 1, f"expected one disambiguated file node, got {matches}"
    return matches[0]


def test_affected_cli_resolves_shared_basename_with_docstring(tmp_path):
    """End to end on the issue's repro: the command must not report no match."""
    _write_repro(tmp_path, head='"""Checks a request before it runs."""\n\n\n')
    graph = _build(tmp_path)

    file_node = _file_node_id(graph, "app/alpha/hooks.py")
    assert graph["nodes"] and resolve_seed(
        load_graph(tmp_path / "graphify-out" / "graph.json"),
        "app/alpha/hooks.py",
        root=tmp_path,
    ) == file_node

    result = _run_graphify(["affected", "app/alpha/hooks.py"], cwd=tmp_path)
    assert "No unique node match" not in result.stdout
    assert "main.py" in result.stdout


def test_affected_cli_resolves_shared_basename_without_docstring(tmp_path):
    """Control: the same layout without the L1 rationale node already works.

    Keeps the boundary of the bug pinned, so a fix cannot regress the case that
    was never broken.
    """
    _write_repro(tmp_path, head="# Checks a request before it runs.\n\n\n")
    graph = _build(tmp_path)

    file_node = _file_node_id(graph, "app/alpha/hooks.py")
    assert resolve_seed(
        load_graph(tmp_path / "graphify-out" / "graph.json"),
        "app/alpha/hooks.py",
        root=tmp_path,
    ) == file_node
