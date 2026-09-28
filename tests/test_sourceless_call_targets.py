"""Regression tests for unresolved external call targets (#3156)."""

from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _nodes(result: dict) -> dict[str, dict]:
    return {node["id"]: node for node in result["nodes"]}


def _labelled_edges(result: dict, nodes: dict[str, dict], label: str) -> list[dict]:
    return [
        edge
        for edge in result["edges"]
        if nodes.get(edge.get("target"), {}).get("label") == label
    ]


def test_sourceless_external_call_target_is_not_emitted(tmp_path: Path):
    """A type-reference stub must not become a project-wide calls hub."""
    typed = tmp_path / "typed.py"
    typed.write_text(
        "from fastapi import HTTPException\n"
        "\n"
        "def typed_error() -> HTTPException:\n"
        "    return HTTPException(status_code=400)\n",
        encoding="utf-8",
    )
    caller = tmp_path / "caller.py"
    caller.write_text(
        "def bare_error():\n"
        "    return HTTPException(status_code=401)\n",
        encoding="utf-8",
    )

    result = extract([typed, caller], cache_root=tmp_path, root=tmp_path)
    nodes = _nodes(result)
    external = [node for node in nodes.values() if node.get("label") == "HTTPException"]

    assert len(external) == 1
    assert external[0].get("source_file") == ""
    references = _labelled_edges(result, nodes, "HTTPException")
    assert any(edge.get("context") == "return_type" for edge in references)
    assert not any(edge.get("relation") == "calls" for edge in references)


def test_source_backed_exception_call_is_preserved(tmp_path: Path):
    """A project-defined exception with the same name remains a real call target."""
    definitions = tmp_path / "exceptions.py"
    definitions.write_text(
        "class HTTPException(Exception):\n"
        "    pass\n",
        encoding="utf-8",
    )
    caller = tmp_path / "api.py"
    caller.write_text(
        "from exceptions import HTTPException\n"
        "\n"
        "def raise_error():\n"
        "    return HTTPException()\n",
        encoding="utf-8",
    )

    result = extract([definitions, caller], cache_root=tmp_path, root=tmp_path)
    nodes = _nodes(result)
    calls = _labelled_edges(result, nodes, "HTTPException")

    assert any(
        edge.get("relation") == "calls"
        and nodes[edge["target"]].get("source_file") == "exceptions.py"
        for edge in calls
    ), calls
