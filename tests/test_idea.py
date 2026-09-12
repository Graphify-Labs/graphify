from __future__ import annotations

import base64
import errno
import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.idea import (
    _safe_stem,
    _write_new,
    create_idea_graph,
    cytoscape_elements,
    render_cytoscape_html,
)


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


def test_cytoscape_elements_reject_non_obsidian_note_uri():
    with pytest.raises(ValueError, match="obsidian"):
        cytoscape_elements(
            _response(),
            title="Tool library",
            idea_text="Neighbors share tools.",
            note_uri="javascript:alert(1)",
        )


def test_cytoscape_elements_accept_weighted_degree_spelling():
    response = _response()
    attributes = response["entriesAndGraphOfContext"]["graph"]["graphologyGraph"]["nodes"][0][
        "attributes"
    ]
    attributes.pop("weighedDegree")
    attributes["weightedDegree"] = 11

    elements = cytoscape_elements(
        response,
        title="Tool library",
        idea_text="Neighbors share tools.",
        note_uri="obsidian://open?vault=Notes&file=Ideas%2FTool+library",
    )

    tools = next(item["data"] for item in elements if item["data"]["id"] == "concept:tools")
    assert tools["degree"] == 11


def test_cytoscape_elements_normalize_edge_endpoint_keys():
    response = _response()
    edge = response["entriesAndGraphOfContext"]["graph"]["graphologyGraph"]["edges"][0]
    edge["source"] = " tools "
    edge["target"] = " neighbors "

    elements = cytoscape_elements(
        response,
        title="Tool library",
        idea_text="Neighbors share tools.",
        note_uri="obsidian://open?vault=Notes&file=Ideas%2FTool+library",
    )

    graph_edge = next(item["data"] for item in elements if item["data"].get("kind") == "infranodus")
    assert graph_edge["source"] == "concept:tools"
    assert graph_edge["target"] == "concept:neighbors"


def test_cytoscape_elements_preserve_numeric_zero_node_ids():
    response = _response()
    graph = response["entriesAndGraphOfContext"]["graph"]["graphologyGraph"]
    graph["nodes"] = [
        {"key": 0, "attributes": {"degree": 1}},
        {"key": 1, "attributes": {"degree": 1}},
    ]
    graph["edges"] = [{"source": 0, "target": 1, "attributes": {"weight": 1}}]

    elements = cytoscape_elements(
        response,
        title="Numbered concepts",
        idea_text="Connect zero to one.",
        note_uri="obsidian://open?vault=Notes&file=Ideas%2FNumbers",
    )

    ids = {item["data"]["id"] for item in elements}
    assert {"concept:0", "concept:1"} <= ids
    edge = next(item["data"] for item in elements if item["data"].get("kind") == "infranodus")
    assert edge["source"] == "concept:0"
    assert edge["target"] == "concept:1"


def test_render_cytoscape_html_escapes_script_breakouts_and_js_line_separators():
    elements = [
        {
            "data": {
                "id": "idea",
                "content": "</script><img src=x onerror=alert(1)>\u2028next",
            }
        }
    ]

    output = render_cytoscape_html("Safe", elements)

    assert "</script><img" not in output
    assert "\u2028" not in output
    assert "const elements = JSON.parse(atob('" in output


def test_render_cytoscape_html_sanitizes_node_links_at_render_boundary():
    elements = [
        {
            "data": {
                "id": "unsafe",
                "label": "Unsafe",
                "note_uri": "javascript:alert(1)",
                "graph_url": "https://infranodus.com.evil.example/graph",
            }
        }
    ]

    output = render_cytoscape_html("Unsafe links", elements)
    payload_match = re.search(r"atob\('([^']+)'\)", output)
    assert payload_match is not None
    payload = json.loads(base64.b64decode(payload_match.group(1)))

    assert payload[0]["data"]["note_uri"] == ""
    assert payload[0]["data"]["graph_url"] == ""


@pytest.mark.parametrize("title", ["---", "...", "@@@"])
def test_safe_stem_rejects_titles_without_letters_or_numbers(title):
    with pytest.raises(ValueError, match="letter or number"):
        _safe_stem(title)


def test_safe_stem_accepts_non_ascii_letters():
    assert _safe_stem("アイデア") == "アイデア"


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
    payload_match = re.search(r"atob\('([^']+)'\)", graph_text)
    assert payload_match is not None
    payload = json.loads(base64.b64decode(payload_match.group(1)))
    payload_text = json.dumps(payload)
    assert "obsidian://open" in payload_text
    assert "concept:tools" in payload_text


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


def test_write_new_uses_unique_temp_file_and_preserves_existing_target(tmp_path):
    target = tmp_path / "idea.html"
    target.write_text("original")
    stale_temp = tmp_path / ".idea.html.tmp"
    stale_temp.symlink_to(tmp_path / "outside")

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        _write_new(target, "replacement", force=False)

    assert target.read_text() == "original"
    assert stale_temp.is_symlink()
    assert not (tmp_path / "outside").exists()
    assert list(tmp_path.glob(".idea.html.*.tmp")) == []


def test_write_new_atomically_creates_new_target(tmp_path):
    target = Path(tmp_path) / "idea.html"

    _write_new(target, "content", force=False)

    assert target.read_text() == "content"


def test_write_new_reports_filesystem_without_hard_links(tmp_path, monkeypatch):
    target = tmp_path / "idea.html"

    def reject_hard_link(source, destination):
        raise OSError(errno.EOPNOTSUPP, "hard links unsupported")

    monkeypatch.setattr("graphify.idea.os.link", reject_hard_link)

    with pytest.raises(OSError, match="atomic no-overwrite publication"):
        _write_new(target, "content", force=False)

    assert not target.exists()
    assert list(tmp_path.glob(".idea.html.*.tmp")) == []


def test_create_idea_graph_preserves_note_when_html_commit_fails(tmp_path, monkeypatch):
    import graphify.idea as idea_module

    vault = tmp_path / "Notes"
    vault.mkdir()
    output = tmp_path / "idea.html"
    original_write = idea_module._write_new

    def fail_html(path, content, *, force):
        if path.suffix == ".html":
            raise FileExistsError("concurrent graph")
        return original_write(path, content, force=force)

    monkeypatch.setattr(idea_module, "_write_new", fail_html)

    with pytest.raises(FileExistsError, match="concurrent graph"):
        create_idea_graph(
            text="New text",
            title="Tool library",
            vault=vault,
            output_path=output,
            response=_response(),
        )

    assert (vault / "Ideas" / "Tool library.md").exists()
    assert not output.exists()


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


def test_graph_url_with_control_characters_is_not_rendered(tmp_path):
    vault = tmp_path / "Notes"
    vault.mkdir()
    response = _response()
    response["entriesAndGraphOfContext"]["graphUrl"] = (
        "https://infranodus.com/example\njavascript:alert(1)"
    )

    note, graph = create_idea_graph(
        text="New text",
        title="Tool library",
        vault=vault,
        output_path=tmp_path / "idea.html",
        response=response,
    )

    assert "javascript:" not in note.read_text()
    assert "javascript:" not in graph.read_text()


def test_create_idea_graph_rejects_non_object_response(tmp_path):
    vault = tmp_path / "Notes"
    vault.mkdir()

    with pytest.raises(ValueError, match="JSON object"):
        create_idea_graph(
            text="New text",
            title="Tool library",
            vault=vault,
            output_path=tmp_path / "idea.html",
            response=[],
        )


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


def test_idea_cli_reports_filesystem_errors(tmp_path, monkeypatch, capsys):
    import graphify.idea as idea_module

    vault = tmp_path / "Notes"
    vault.mkdir()
    response_path = tmp_path / "response.json"
    response_path.write_text(json.dumps(_response()))

    def fail_write(**_kwargs):
        raise PermissionError("permission denied")

    monkeypatch.setattr(idea_module, "create_idea_graph", fail_write)

    with pytest.raises(SystemExit) as exc:
        idea_module.main(
            [
                "New idea",
                "--vault",
                str(vault),
                "--response",
                str(response_path),
            ]
        )

    assert exc.value.code == 2
    assert "permission denied" in capsys.readouterr().err
