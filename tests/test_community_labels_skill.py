"""Curated community labels must reach the persisted graph.json (#2490).

Two guards:

1. The ``to_json`` export gate: nodes get ``community_name`` only when the
   ``community_labels`` kwarg is passed, so any Step-5 flow that curates labels
   but omits the kwarg ships a graph.json without community names.

2. A template lint over the generated ``graphify/skill*.md`` bodies (and the
   fragments they render from): the Step-5 / post-labels code block — the one
   that builds the curated ``labels = LABELS_DICT`` dict — must re-export
   ``graphify-out/graph.json`` with ``community_labels=labels``. This locks the
   #2490 fix so a future template edit cannot silently drop the kwarg again.
"""
from __future__ import annotations

import json
import tempfile
from pathlib import Path

import networkx as nx
import pytest

from graphify.export import to_json

REPO_ROOT = Path(__file__).resolve().parent.parent
FRAGMENTS_DIR = REPO_ROOT / "tools" / "skillgen" / "fragments" / "core"


def _two_community_graph() -> tuple[nx.Graph, dict[int, list[str]]]:
    G = nx.Graph()
    G.add_node("n1", label="Database", community=0, source_file="app/db.py", type="code")
    G.add_node("n2", label="Server", community=0, source_file="app/srv.py", type="code")
    G.add_node("n3", label="Cache", community=1, source_file="infra/cache.py", type="code")
    G.add_edge("n1", "n2", relation="calls")
    communities = {0: ["n1", "n2"], 1: ["n3"]}
    return G, communities


def test_to_json_community_labels_kwarg_writes_community_name():
    """Passing community_labels stamps community_name on that community's nodes."""
    G, communities = _two_community_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        assert to_json(G, communities, str(out), community_labels={0: "X"})
        data = json.loads(out.read_text())
        by_id = {n["id"]: n for n in data["nodes"]}
        assert by_id["n1"]["community_name"] == "X"
        assert by_id["n2"]["community_name"] == "X"
        # A community missing from a non-empty labels dict gets the placeholder.
        assert by_id["n3"]["community_name"] == "Community 1"


def test_to_json_without_labels_kwarg_writes_no_community_name():
    """Omitting the kwarg is the #2490 bug shape: no node carries community_name."""
    G, communities = _two_community_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        assert to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        assert all("community_name" not in n for n in data["nodes"])


# --- template lint -----------------------------------------------------------

def _code_blocks(markdown: str) -> list[str]:
    """Fenced code blocks of a markdown body, fence lines excluded."""
    blocks: list[str] = []
    current: list[str] | None = None
    for line in markdown.splitlines():
        if line.lstrip().startswith("```"):
            if current is None:
                current = []
            else:
                blocks.append("\n".join(current))
                current = None
            continue
        if current is not None:
            current.append(line)
    return blocks


def _skill_bodies() -> list[Path]:
    paths = sorted(REPO_ROOT.glob("graphify/skill*.md"))
    assert paths, "no generated graphify/skill*.md found"
    return paths


@pytest.mark.parametrize("path", _skill_bodies(), ids=lambda p: p.name)
def test_skill_step5_reexports_graph_json_with_curated_labels(path: Path):
    """Every post-labels (LABELS_DICT) block re-exports graph.json with the kwarg.

    The Step-5 block is the only place the curated labels dict exists, so it is
    the block that must call ``to_json(..., community_labels=labels)``. Any
    ``to_json(...graphify-out/graph.json...)`` call in that block without the
    kwarg would ship graph.json nodes with no ``community_name`` (#2490).
    """
    text = path.read_text(encoding="utf-8")
    post_labels_blocks = [
        b for b in _code_blocks(text) if "labels = LABELS_DICT" in b
    ]
    assert post_labels_blocks, f"{path.name}: no Step-5 (LABELS_DICT) code block found"
    for block in post_labels_blocks:
        assert "to_json(G, communities, 'graphify-out/graph.json', community_labels=labels)" in block, (
            f"{path.name}: the post-labels Step-5 block must re-export "
            f"graphify-out/graph.json with community_labels=labels (#2490)"
        )
        # No label-less graph.json export may coexist in the post-labels block.
        for line in block.splitlines():
            if "to_json(" in line and "graphify-out/graph.json" in line:
                assert "community_labels=labels" in line, (
                    f"{path.name}: post-labels to_json call is missing "
                    f"community_labels=labels: {line.strip()!r}"
                )


@pytest.mark.parametrize(
    "fragment", sorted(FRAGMENTS_DIR.glob("*.md")), ids=lambda p: p.name
)
def test_core_fragments_step5_reexport_with_curated_labels(fragment: Path):
    """Same lint at the source of truth: the core fragments skillgen renders from."""
    text = fragment.read_text(encoding="utf-8")
    post_labels_blocks = [
        b for b in _code_blocks(text) if "labels = LABELS_DICT" in b
    ]
    assert post_labels_blocks, f"{fragment.name}: no Step-5 (LABELS_DICT) code block found"
    for block in post_labels_blocks:
        assert "to_json(G, communities, 'graphify-out/graph.json', community_labels=labels)" in block, (
            f"{fragment.name}: the post-labels Step-5 block must re-export "
            f"graphify-out/graph.json with community_labels=labels (#2490)"
        )
