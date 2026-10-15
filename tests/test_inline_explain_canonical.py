"""The skill fallback must interpret Graphify's canonical directed:false links."""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[1]
FRAGMENTS = [
    ROOT / "tools/skillgen/fragments/references/query/default.md",
]


def _script(fragment: Path) -> str:
    section = fragment.read_text(encoding="utf-8").split("## For /graphify explain", 1)[1]
    for block in section.split("```bash")[1:]:
        command = block.split("```", 1)[0].strip()
        if '-c "' in command and "print('CONNECTIONS:')" in command:
            lines = command.splitlines()
            assert lines[-1] == '"'
            return "\n".join(lines[1:-1]).replace('\\"', '"').replace("term = 'NODE_NAME'", "term = 'Center'")
    raise AssertionError("missing inline explain command")


@pytest.mark.parametrize("directed", [False, True])
@pytest.mark.parametrize("fragment", FRAGMENTS, ids=["shared"])
def test_canonical_explain_keeps_direction_parallel_edges_and_call_sites(tmp_path, fragment, directed):
    graph_dir = tmp_path / "graphify-out"
    graph_dir.mkdir()
    graph = {
        "directed": directed, "multigraph": True, "graph": {},
        "nodes": [{"id": n.lower(), "label": n, "source_file": f"{n.lower()}.py"}
                  for n in ["Center", "Caller", "Dependency"]],
        "links": [
            {"source": "caller", "target": "center", "key": 0, "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "caller.py", "source_location": "L4"},
            {"source": "caller", "target": "center", "key": 1, "relation": "uses",
             "confidence": "INFERRED", "source_file": "caller.py", "source_location": "L5"},
            {"source": "dependency", "target": "center", "key": 0,
             "_src": "center", "_tgt": "dependency", "relation": "imports",
             "confidence": "EXTRACTED", "source_file": "center.py", "source_location": "L2"},
            {"source": "center", "target": "center", "key": 0, "relation": "recurses",
             "confidence": "EXTRACTED", "source_file": "center.py", "source_location": "L8"},
        ],
    }
    (graph_dir / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    result = subprocess.run([sys.executable, "-c", _script(fragment)], cwd=tmp_path,
                            capture_output=True, text=True, check=True)
    assert "<-- Caller [calls] [EXTRACTED] caller.py:L4" in result.stdout
    assert "<-- Caller [uses] [INFERRED] caller.py:L5" in result.stdout
    assert "--> Dependency [imports] [EXTRACTED] center.py:L2" in result.stdout
    assert result.stdout.count("[recurses]") == 1
