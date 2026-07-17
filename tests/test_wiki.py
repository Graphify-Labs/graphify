import re
import pytest

from graphify.wiki import to_wiki
from tests.native_helpers import graph_from_payload


COMMUNITIES = {0: ["n1", "n2"], 1: ["n3", "n4"]}
LABELS = {0: "Parsing Layer", 1: "Rendering Layer"}
GODS = [{"id": "n1", "label": "parse", "degree": 2}]


def _graph():
    return graph_from_payload(
        [
            {"id": "n1", "label": "parse", "file_type": "code", "source_file": "parser.py"},
            {"id": "n2", "label": "validate", "file_type": "code", "source_file": "parser.py"},
            {"id": "n3", "label": "render", "file_type": "code", "source_file": "renderer.py"},
            {"id": "n4", "label": "stream", "file_type": "code", "source_file": "renderer.py"},
        ],
        [
            {"source": "n1", "target": "n2", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "n1", "target": "n3", "relation": "references", "confidence": "INFERRED"},
            {"source": "n3", "target": "n4", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    )


def test_wiki_writes_index_communities_and_god_node(tmp_path):
    count = to_wiki(
        _graph(), COMMUNITIES, tmp_path, community_labels=LABELS,
        cohesion={0: 0.85, 1: 0.72}, god_nodes_data=GODS,
    )
    assert count == 3
    assert {path.name for path in tmp_path.glob("*.md")} == {
        "index.md", "Parsing_Layer.md", "Rendering_Layer.md", "parse.md"
    }
    assert "0.85" in (tmp_path / "Parsing_Layer.md").read_text()
    assert "Rendering Layer" in (tmp_path / "Parsing_Layer.md").read_text()
    assert "Parsing Layer" in (tmp_path / "parse.md").read_text()


def test_wiki_links_resolve_to_real_files(tmp_path):
    to_wiki(_graph(), COMMUNITIES, tmp_path, community_labels=LABELS, god_nodes_data=GODS)
    filenames = {path.name for path in tmp_path.glob("*.md")}
    targets = set()
    for path in tmp_path.glob("*.md"):
        targets.update(re.findall(r"\[[^]]+\]\(([^)]+\.md)\)", path.read_text()))
    assert targets <= filenames


def test_stale_members_are_dropped_and_all_stale_fails(tmp_path, capsys):
    communities = {0: ["n1", "ghost"], 1: ["n3", "n4"]}
    assert to_wiki(_graph(), communities, tmp_path, community_labels=LABELS) == 2
    assert "stale" in capsys.readouterr().err.lower()
    with pytest.raises(ValueError, match="stale"):
        to_wiki(_graph(), {0: ["ghost"]}, tmp_path, community_labels=LABELS)


def test_large_community_has_truncation_notice(tmp_path):
    ids = [f"n{i}" for i in range(30)]
    graph = graph_from_payload(
        [{"id": node, "label": node, "source_file": "many.py"} for node in ids],
        [
            {"source": ids[index], "target": ids[index + 1], "relation": "calls"}
            for index in range(len(ids) - 1)
        ],
    )
    to_wiki(graph, {0: ids}, tmp_path, community_labels={0: "Large"})
    assert "and 5 more nodes" in (tmp_path / "Large.md").read_text()


def test_empty_communities_refuse_to_clear_existing_wiki(tmp_path):
    existing = tmp_path / "keep.md"
    existing.write_text("keep")
    with pytest.raises(ValueError, match="empty"):
        to_wiki(_graph(), {}, tmp_path)
    assert existing.read_text() == "keep"
