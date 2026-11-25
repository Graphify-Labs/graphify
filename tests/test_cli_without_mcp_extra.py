"""Graph-reading commands must run without the optional `mcp` extra (#5320)."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

# Runs the CLI with every package the `mcp` extra brings in made unimportable:
# a None entry in sys.modules makes `import name` raise ModuleNotFoundError.
_RUN_WITHOUT_MCP_EXTRA = """
import sys
for name in ("anyio", "mcp", "starlette"):
    sys.modules[name] = None
from graphify.__main__ import main
sys.argv = ["graphify", *sys.argv[1:]]
main()
"""


@pytest.fixture
def graph_path(tmp_path):
    graph = {
        "directed": True,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "app_load", "label": "load_orders()", "file_type": "code",
             "source_file": "app.py", "source_location": "L1", "community": 0},
            {"id": "app_save", "label": "save_orders()", "file_type": "code",
             "source_file": "app.py", "source_location": "L5", "community": 0},
        ],
        "links": [
            {"source": "app_load", "target": "app_save", "relation": "calls",
             "confidence": "EXTRACTED", "source_file": "app.py",
             "source_location": "L2", "weight": 1.0},
        ],
    }
    out = tmp_path / "graphify-out"
    out.mkdir()
    path = out / "graph.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    return path


@pytest.mark.parametrize("args", [
    ["explain", "save_orders"],
    ["query", "save_orders"],
    ["path", "load_orders", "save_orders"],
    ["affected", "save_orders"],
    ["benchmark"],
], ids=lambda args: args[0])
def test_graph_command_runs_without_mcp_extra(graph_path, args):
    tail = [str(graph_path)] if args[0] == "benchmark" else ["--graph", str(graph_path)]
    result = subprocess.run(
        [sys.executable, "-c", _RUN_WITHOUT_MCP_EXTRA, *args, *tail],
        cwd=graph_path.parent.parent, capture_output=True, text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    if args[0] != "benchmark":
        # The command's own target node (the last positional arg) must appear in
        # its output. Asserting on a *caller* instead is cwd-fragile for `query`,
        # whose downstream BFS from the node need not reach its callers.
        assert args[-1] in result.stdout
