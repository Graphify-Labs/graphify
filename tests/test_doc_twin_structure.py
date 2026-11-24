"""Document twin reconciliation must preserve real Markdown structure (#5272)."""
from copy import deepcopy

import pytest

from graphify.build import build_from_json
from graphify.extract import extract


@pytest.mark.parametrize("dedup", [True, False])
@pytest.mark.parametrize("text, expected", [
    ("---\nstatus: approved\n---\n# Doc\n", {"guide", "guide_doc"}),
    ("# API\n\n## API Doc\n", {"guide", "guide_api", "guide_api_doc"}),
])
def test_real_markdown_doc_headings_survive(tmp_path, dedup, text, expected):
    path = tmp_path / "guide.md"
    path.write_text(text, encoding="utf-8")
    raw = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    graph = build_from_json(deepcopy(raw), dedup=dedup)
    assert expected <= set(graph)
    assert graph.nodes["guide"]["node_kind"] == "page"
    assert len(graph.edges) == len(raw["edges"])
    if "status: approved" in text:
        assert graph.nodes["guide"]["frontmatter"]["status"] == "approved"


@pytest.mark.parametrize("origin", ["semantic", None])
def test_genuine_doc_twin_keeps_page_metadata_and_semantic_tier(origin):
    page = {"id": "guide", "label": "guide.md", "file_type": "document",
            "source_file": "guide.md", "source_location": "L1", "_origin": "ast",
            "node_kind": "page", "frontmatter": {"status": "approved"}}
    semantic = {"id": "guide_doc", "label": "Guide", "file_type": "document",
                "source_file": "guide.md", "source_location": None,
                "rationale": "Conceptual guide"}
    if origin:
        semantic["_origin"] = origin
    raw = {"nodes": [page, semantic], "edges": []}
    graph = build_from_json(raw)
    assert set(graph) == {"guide_doc"}
    survivor = graph.nodes["guide_doc"]
    assert survivor["frontmatter"] == {"status": "approved"}
    assert survivor["node_kind"] == "page"
    assert survivor["label"] == "Guide"
    assert survivor["rationale"] == "Conceptual guide"
    assert survivor.get("_origin") != "ast"
    assert survivor["source_location"] is None


@pytest.mark.parametrize("candidate", [
    {"node_kind": "heading"}, {"_origin": "ast"},
])
def test_structural_doc_candidate_is_not_a_semantic_twin(candidate):
    raw = {"nodes": [
        {"id": "guide", "label": "guide.md", "file_type": "document",
         "source_file": "guide.md", "node_kind": "page", "_origin": "ast"},
        {"id": "guide_doc", "label": "Doc", "file_type": "document",
         "source_file": "guide.md", **candidate},
    ], "edges": []}
    assert set(build_from_json(raw)) == {"guide", "guide_doc"}
