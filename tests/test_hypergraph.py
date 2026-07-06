"""Tests for hyperedge support in graphify."""
from __future__ import annotations
import json
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from graphify.build import build_from_json
from graphify.export import attach_hyperedges, to_json
from graphify.report import generate


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

SAMPLE_EXTRACTION = {
    "nodes": [
        {"id": "BasicAuth", "label": "BasicAuth", "file_type": "code", "source_file": "auth.py"},
        {"id": "DigestAuth", "label": "DigestAuth", "file_type": "code", "source_file": "auth.py"},
        {"id": "Request", "label": "Request", "file_type": "code", "source_file": "http.py"},
        {"id": "Response", "label": "Response", "file_type": "code", "source_file": "http.py"},
        {"id": "BaseClient", "label": "BaseClient", "file_type": "code", "source_file": "client.py"},
    ],
    "edges": [
        {"source": "BasicAuth", "target": "Request", "relation": "uses", "confidence": "EXTRACTED", "confidence_score": 1.0, "source_file": "auth.py"},
    ],
    "hyperedges": [
        {
            "id": "auth_flow",
            "label": "Auth Flow",
            "nodes": ["BasicAuth", "DigestAuth", "Request", "Response", "BaseClient"],
            "relation": "participate_in",
            "confidence": "INFERRED",
            "confidence_score": 0.75,
            "source_file": "auth.py",
        }
    ],
    "input_tokens": 10,
    "output_tokens": 5,
}

SAMPLE_DETECTION = {
    "total_files": 3,
    "total_words": 500,
    "files": {"code": ["auth.py", "http.py", "client.py"]},
    "skipped_sensitive": [],
    "warning": None,
}


# ---------------------------------------------------------------------------
# 1. Hyperedges survive build_from_json round-trip
# ---------------------------------------------------------------------------

def test_build_from_json_stores_hyperedges():
    G = build_from_json(SAMPLE_EXTRACTION)
    assert "hyperedges" in G.graph
    assert len(G.graph["hyperedges"]) == 1
    assert G.graph["hyperedges"][0]["id"] == "auth_flow"


def test_build_from_json_relativizes_hyperedge_source_file(tmp_path):
    """build_from_json(root=...) must relativize hyperedge source_file like it
    already does for nodes and edges. to_json writes G.graph['hyperedges']
    verbatim and has no root parameter, so an absolute path emitted by a semantic
    subagent would otherwise leak into graph.json (#1418)."""
    base = tmp_path.resolve()
    abs_doc = base / "docs" / "CLAUDE.md"
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "document", "source_file": str(abs_doc)},
        ],
        "edges": [],
        "hyperedges": [
            {
                "id": "arch",
                "label": "Architecture",
                "nodes": ["a"],
                "relation": "participate_in",
                "confidence": "INFERRED",
                "confidence_score": 0.75,
                "source_file": str(abs_doc),
            }
        ],
    }
    G = build_from_json(extraction, root=str(base))
    assert G.graph["hyperedges"][0]["source_file"] == "docs/CLAUDE.md"
    # Anchor: the node path is relativized the same way (the contract this mirrors).
    assert G.nodes["a"]["source_file"] == "docs/CLAUDE.md"


def test_build_from_json_no_hyperedges():
    extraction = {**SAMPLE_EXTRACTION, "hyperedges": []}
    G = build_from_json(extraction)
    assert G.graph.get("hyperedges", []) == []


def test_build_from_json_missing_hyperedges_key():
    extraction = {k: v for k, v in SAMPLE_EXTRACTION.items() if k != "hyperedges"}
    G = build_from_json(extraction)
    assert G.graph.get("hyperedges", []) == []


# ---------------------------------------------------------------------------
# 2. attach_hyperedges deduplicates by id
# ---------------------------------------------------------------------------

def test_attach_hyperedges_adds_new():
    G = nx.Graph()
    attach_hyperedges(G, [{"id": "auth_flow", "label": "Auth Flow", "nodes": ["A", "B", "C"]}])
    assert len(G.graph["hyperedges"]) == 1


def test_attach_hyperedges_deduplicates():
    G = nx.Graph()
    h = {"id": "auth_flow", "label": "Auth Flow", "nodes": ["A", "B", "C"]}
    attach_hyperedges(G, [h])
    attach_hyperedges(G, [h])  # second call with same id should not duplicate
    assert len(G.graph["hyperedges"]) == 1


def test_attach_hyperedges_multiple_different_ids():
    G = nx.Graph()
    attach_hyperedges(G, [
        {"id": "flow_a", "label": "Flow A", "nodes": ["A", "B", "C"]},
        {"id": "flow_b", "label": "Flow B", "nodes": ["D", "E", "F"]},
    ])
    assert len(G.graph["hyperedges"]) == 2


def test_attach_hyperedges_skips_entry_without_id():
    G = nx.Graph()
    attach_hyperedges(G, [{"label": "No ID", "nodes": ["A", "B", "C"]}])
    assert G.graph.get("hyperedges", []) == []


# ---------------------------------------------------------------------------
# 3. to_json includes hyperedges key
# ---------------------------------------------------------------------------

def test_to_json_includes_hyperedges():
    G = build_from_json(SAMPLE_EXTRACTION)
    communities = {0: list(G.nodes())}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    to_json(G, communities, path)
    data = json.loads(Path(path).read_text())
    assert "hyperedges" in data
    assert len(data["hyperedges"]) == 1
    assert data["hyperedges"][0]["id"] == "auth_flow"


def test_to_json_hyperedges_empty_when_none():
    extraction = {**SAMPLE_EXTRACTION, "hyperedges": []}
    G = build_from_json(extraction)
    communities = {0: list(G.nodes())}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    to_json(G, communities, path)
    data = json.loads(Path(path).read_text())
    assert "hyperedges" in data
    assert data["hyperedges"] == []


# ---------------------------------------------------------------------------
# 4. Hyperedges loaded from graph.json via build_from_json
# ---------------------------------------------------------------------------

def test_hyperedges_roundtrip_via_json_file():
    """Write graph.json then reload it - hyperedges must survive."""
    G = build_from_json(SAMPLE_EXTRACTION)
    communities = {0: list(G.nodes())}
    with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as f:
        path = f.name
    to_json(G, communities, path)

    # Reload the JSON as if build_from_json were called on it
    data = json.loads(Path(path).read_text())
    G2 = build_from_json({
        "nodes": [{"id": n["id"], **{k: v for k, v in n.items() if k != "id"}} for n in data["nodes"]],
        "edges": [{"source": e["source"], "target": e["target"], **{k: v for k, v in e.items() if k not in ("source", "target")}} for e in data.get("links", [])],
        "hyperedges": data.get("hyperedges", []),
    })
    assert G2.graph.get("hyperedges", []) != []
    assert G2.graph["hyperedges"][0]["id"] == "auth_flow"


# ---------------------------------------------------------------------------
# 5. Report includes hyperedges section when hyperedges present
# ---------------------------------------------------------------------------

def _make_report(G):
    communities = {0: list(G.nodes())}
    cohesion = {0: 1.0}
    labels = {0: "All"}
    gods = [{"label": "BasicAuth", "degree": 2}]
    surprises = []
    return generate(G, communities, cohesion, labels, gods, surprises, SAMPLE_DETECTION, {"input": 10, "output": 5}, ".")


def test_report_includes_hyperedges_section():
    G = build_from_json(SAMPLE_EXTRACTION)
    report = _make_report(G)
    assert "## Hyperedges (group relationships)" in report
    assert "Auth Flow" in report
    assert "INFERRED 0.75" in report


def test_report_includes_hyperedge_node_list():
    G = build_from_json(SAMPLE_EXTRACTION)
    report = _make_report(G)
    # Node IDs should appear in the report line
    assert "BasicAuth" in report
    assert "DigestAuth" in report


# ---------------------------------------------------------------------------
# 6. Report skips hyperedges section when none present
# ---------------------------------------------------------------------------

def test_report_skips_hyperedges_section_when_empty():
    extraction = {**SAMPLE_EXTRACTION, "hyperedges": []}
    G = build_from_json(extraction)
    report = _make_report(G)
    assert "## Hyperedges" not in report


def test_report_skips_hyperedges_section_when_key_missing():
    extraction = {k: v for k, v in SAMPLE_EXTRACTION.items() if k != "hyperedges"}
    G = build_from_json(extraction)
    report = _make_report(G)
    assert "## Hyperedges" not in report


# ---------------------------------------------------------------------------
# 7. Hyperedge member-key alias normalization (#1561)
# ---------------------------------------------------------------------------

def _alias_extraction():
    """Three hyperedges, one per member-key spelling: nodes / members / node_ids."""
    return {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "m.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "m.py"},
            {"id": "c", "label": "C", "file_type": "code", "source_file": "m.py"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "he_nodes", "label": "canon", "nodes": ["a", "b", "c"]},
            {"id": "he_members", "label": "alias1", "members": ["a", "b", "c"]},
            {"id": "he_node_ids", "label": "alias2", "node_ids": ["a", "b", "c"]},
        ],
    }


def test_build_normalizes_member_aliases_to_nodes():
    G = build_from_json(_alias_extraction())
    hes = {he["id"]: he for he in G.graph["hyperedges"]}
    for hid in ("he_nodes", "he_members", "he_node_ids"):
        assert hes[hid]["nodes"] == ["a", "b", "c"], hid
        # alias keys are dropped post-normalization
        assert "members" not in hes[hid]
        assert "node_ids" not in hes[hid]


def test_build_dedups_alias_members_preserving_order():
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "m.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "m.py"},
        ],
        "edges": [],
        "hyperedges": [{"id": "h", "label": "x", "members": ["a", "a", "b"]}],
    }
    G = build_from_json(extraction)
    assert G.graph["hyperedges"][0]["nodes"] == ["a", "b"]
    assert "members" not in G.graph["hyperedges"][0]


def test_build_canonical_nodes_wins_over_alias():
    extraction = {
        "nodes": [
            {"id": "a", "label": "A", "file_type": "code", "source_file": "m.py"},
            {"id": "b", "label": "B", "file_type": "code", "source_file": "m.py"},
            {"id": "x", "label": "X", "file_type": "code", "source_file": "m.py"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "h", "label": "x", "nodes": ["a", "b"], "members": ["x"]},
        ],
    }
    G = build_from_json(extraction)
    he = G.graph["hyperedges"][0]
    assert he["nodes"] == ["a", "b"]  # canonical untouched
    assert "members" not in he  # stray alias dropped


def test_build_rekeys_alias_keyed_hyperedge_members():
    """Alias normalization must run BEFORE the semantic id-remap loop so a
    `members`-keyed hyperedge's refs get rekeyed alongside `nodes`-keyed ones."""
    # Non-AST node whose id uses the OLD short stem (`mod_foo`) for source_file
    # pkg/mod.py -> new canonical stem pkg_mod -> remap mod_foo => pkg_mod_foo.
    extraction = {
        "nodes": [
            {"id": "mod_foo", "label": "foo", "file_type": "code", "source_file": "pkg/mod.py"},
            {"id": "mod_bar", "label": "bar", "file_type": "code", "source_file": "pkg/mod.py"},
        ],
        "edges": [],
        "hyperedges": [
            {"id": "h", "label": "x", "members": ["mod_foo", "mod_bar"]},
        ],
    }
    G = build_from_json(extraction)
    he = G.graph["hyperedges"][0]
    assert he["nodes"] == ["pkg_mod_foo", "pkg_mod_bar"]


def test_build_warns_once_per_aliased_hyperedge(capsys):
    build_from_json(_alias_extraction())
    err = capsys.readouterr().err
    # one warning each for the two alias hyperedges, none for the nodes-keyed one
    assert err.count("normalizing") == 2
    assert "he_members" in err and "members" in err
    assert "he_node_ids" in err and "node_ids" in err
    assert "he_nodes" not in err
