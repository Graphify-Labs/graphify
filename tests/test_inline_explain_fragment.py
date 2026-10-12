"""Behavioral regression tests for the generated explain fallback."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


QUERY_FRAGMENT = (
    Path(__file__).parents[1]
    / "tools/skillgen/fragments/references/query/default.md"
)
EXPLAIN_FRAGMENTS = (
    pytest.param(QUERY_FRAGMENT, id="shared-query-reference"),
    pytest.param(
        Path(__file__).parents[1] / "tools/skillgen/fragments/core/aider.md",
        id="aider-monolith",
    ),
    pytest.param(
        Path(__file__).parents[1] / "tools/skillgen/fragments/core/devin.md",
        id="devin-monolith",
    ),
)


def _inline_explain_script(fragment: Path) -> str:
    text = fragment.read_text(encoding="utf-8")
    section = text.split("## For /graphify explain", 1)[1]
    command = next(
        candidate
        for block in section.split("```bash")[1:]
        if '-c "' in (candidate := block.split("```", 1)[0])
        and "print('CONNECTIONS:')" in candidate
    ).strip()
    lines = command.splitlines()
    assert lines[0].endswith('-c "')
    assert lines[-1] == '"'
    script = "\n".join(lines[1:-1]).replace('\\"', '"')
    return script.replace("term = 'NODE_NAME'", "term = 'Center'")


def _run_inline_explain(tmp_path: Path, graph_data: dict, fragment: Path) -> str:
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    (graph_dir / "graph.json").write_text(
        json.dumps(graph_data), encoding="utf-8"
    )
    result = subprocess.run(
        [sys.executable, "-c", _inline_explain_script(fragment)],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


@pytest.mark.parametrize("fragment", EXPLAIN_FRAGMENTS)
def test_inline_explain_lists_all_directed_relationships_and_metadata(tmp_path, fragment):
    graph_data = {
        "directed": True, "multigraph": True, "graph": {},
        "nodes": [
            {"id": "center", "label": "Center"},
            {"id": "incoming", "label": "Incoming"},
            {"id": "outgoing", "label": "Outgoing"},
            {"id": "bidirectional", "label": "Bidirectional"},
        ],
        "links": [
            {"source": "incoming", "target": "center", "key": 0,
             "relation": "calls", "confidence": "EXTRACTED",
             "source_file": "incoming.py", "source_location": "L12",
             "confidence_score": 0.98},
            {"source": "incoming", "target": "center", "key": 1,
             "relation": "uses", "confidence": "INFERRED",
             "source_file": "incoming.py", "source_location": "L13",
             "context": "shared state"},
            {"source": "center", "target": "outgoing", "key": 0,
             "relation": "imports", "confidence": "EXTRACTED",
             "source_file": "center.py", "source_location": "L4"},
            {"source": "center", "target": "outgoing", "key": 1,
             "relation": "references", "confidence": "AMBIGUOUS",
             "source_file": "center.py", "source_location": "L5",
             "weight": 0.4},
            {"source": "center", "target": "center", "key": 0,
             "relation": "recurses", "confidence": "EXTRACTED",
             "source_file": "center.py", "source_location": "L8"},
            {"source": "center", "target": "bidirectional", "key": 0,
             "relation": "contains", "confidence": "EXTRACTED",
             "source_file": "center.py", "source_location": "L10"},
            {"source": "bidirectional", "target": "center", "key": 0,
             "relation": "belongs_to", "confidence": "INFERRED",
             "source_file": "other.py", "source_location": "L3"},
        ],
    }

    out = _run_inline_explain(tmp_path, graph_data, fragment)

    expected = {
        '  <-- Incoming [calls] [EXTRACTED] confidence_score=0.98 source_file="incoming.py" source_location="L12"',
        '  <-- Incoming [uses] [INFERRED] context="shared state" source_file="incoming.py" source_location="L13"',
        '  --> Outgoing [imports] [EXTRACTED] source_file="center.py" source_location="L4"',
        '  --> Outgoing [references] [AMBIGUOUS] source_file="center.py" source_location="L5" weight=0.4',
        '  --> Center [recurses] [EXTRACTED] source_file="center.py" source_location="L8"',
        '  --> Bidirectional [contains] [EXTRACTED] source_file="center.py" source_location="L10"',
        '  <-- Bidirectional [belongs_to] [INFERRED] source_file="other.py" source_location="L3"',
    }
    for connection in expected:
        assert connection in out
    assert out.count("[recurses]") == 1
    assert sum(line.startswith("  <--") for line in out.splitlines()) == 3
    assert sum(line.startswith("  -->") for line in out.splitlines()) == 4


@pytest.mark.parametrize("fragment", EXPLAIN_FRAGMENTS)
def test_inline_explain_retains_undirected_neighbor_output(tmp_path, fragment):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "center", "label": "Center"},
            {"id": "other", "label": "Other", "source_file": "other.py"},
        ],
        "links": [
            {"source": "other", "target": "center", "relation": "uses",
             "confidence": "EXTRACTED", "source_file": "edge-site.py",
             "source_location": "L9", "context": "legacy output"},
        ],
    }

    out = _run_inline_explain(tmp_path, graph_data, fragment)

    connections = [line for line in out.splitlines() if line.startswith("  --")]
    assert connections == ["  --uses--> Other [EXTRACTED] (other.py)"]
