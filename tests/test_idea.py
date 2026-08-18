from __future__ import annotations

import json
import os
import subprocess
import sys

import pytest

from graphify.idea import create_idea_graph, cytoscape_elements


def _response():
    return {
        "entriesAndGraphOfContext": {
            "graphUrl": "https://infranodus.com/example",
            "extendedGraphSummary": {
                "mainTopics": [{"name": "shared tools"}],
                "contentGaps": ["trust and maintenance"],
            },
            "graph": {
                "graphologyGraph": {
                    "nodes": [
                        {
                            "key": "tools",
                            "attributes": {
                                "community": 0,
                                "degree": 3,
                                "weighedDegree": 7,
                            },
                        },
                        {
                            "key": "neighbors",
                            "attributes": {
                                "community": 1,
                                "degree": 2,
                                "weighedDegree": 4,
                            },
                        },
                    ],
                    "edges": [
                        {
                            "source": "tools",
                            "target": "neighbors",
                            "attributes": {"weight": 3},
                        }
                    ],
                }
            },
        }
    }


def test_cytoscape_elements_include_clickable_idea_and_concepts():
    elements = cytoscape_elements(
        _response(),
        title="Tool library",
        idea_text="Neighbors share tools.",
        note_uri="obsidian://open?vault=Notes&file=Ideas%2FTool+library",
    )
    nodes = {item["data"]["id"]: item["data"] for item in elements if "source" not in item["data"]}
    assert nodes["idea"]["kind"] == "idea"
    assert nodes["idea"]["note_uri"].startswith("obsidian://open")
    assert nodes["concept:tools"]["graph_url"] == "https://infranodus.com/example"
    assert any(item["data"].get("kind") == "idea-context" for item in elements)


def test_create_idea_graph_writes_obsidian_note_and_cytoscape_html(tmp_path):
    vault = tmp_path / "Notes"
    vault.mkdir()
    output = tmp_path / "idea.html"

    note, graph = create_idea_graph(
        text="Neighbors share tools and teach repair skills.",
        title="Tool library",
        vault=vault,
        output_path=output,
        response=_response(),
    )

    assert note == vault / "Ideas" / "Tool library.md"
    assert graph == output
    note_text = note.read_text()
    graph_text = graph.read_text()
    assert "Open the clickable Cytoscape graph" in note_text
    assert "shared tools" in note_text
    assert "cytoscape@3.33.1" in graph_text
    assert "obsidian://open" in graph_text
    assert "concept:tools" in graph_text


def test_create_idea_graph_refuses_to_overwrite_note(tmp_path):
    vault = tmp_path / "Notes"
    note = vault / "Ideas" / "Tool library.md"
    note.parent.mkdir(parents=True)
    note.write_text("personal content")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        create_idea_graph(
            text="New text",
            title="Tool library",
            vault=vault,
            output_path=tmp_path / "idea.html",
            response=_response(),
        )
    assert note.read_text() == "personal content"


def test_create_idea_graph_blocks_folder_escape(tmp_path):
    vault = tmp_path / "Notes"
    vault.mkdir()

    with pytest.raises(ValueError, match="inside the vault"):
        create_idea_graph(
            text="New text",
            title="Tool library",
            vault=vault,
            folder="../outside",
            output_path=tmp_path / "idea.html",
            response=_response(),
        )


def test_untrusted_graph_url_is_not_rendered(tmp_path):
    vault = tmp_path / "Notes"
    vault.mkdir()
    response = _response()
    response["entriesAndGraphOfContext"]["graphUrl"] = "javascript:alert(1)"

    note, graph = create_idea_graph(
        text="New text",
        title="Tool library",
        vault=vault,
        output_path=tmp_path / "idea.html",
        response=response,
    )

    assert "javascript:" not in note.read_text()
    assert "javascript:" not in graph.read_text()


def test_idea_cli_supports_offline_infranodus_response(tmp_path):
    vault = tmp_path / "Notes"
    vault.mkdir()
    response_path = tmp_path / "response.json"
    response_path.write_text(json.dumps(_response()))
    output = tmp_path / "clickable.html"
    env = dict(os.environ)

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "graphify",
            "idea",
            "Neighbors share tools and teach repair skills.",
            "--title",
            "Tool library",
            "--vault",
            str(vault),
            "--response",
            str(response_path),
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        env=env,
    )

    assert result.returncode == 0, result.stderr
    assert (vault / "Ideas" / "Tool library.md").exists()
    assert output.exists()
    assert "Clickable graph:" in result.stdout
