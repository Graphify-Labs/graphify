"""#1972 end-to-end: top-level `calls` edges must survive into graph.json.

The unit tests in test_extract.py assert on `extract()`'s return value. That is
not the surface users consume, and the gap mattered: the first cut of this fix
attributed top-level calls to the FILE node, every one of those tests passed,
and the edges still never reached graph.json.

The built graph is an undirected ``nx.Graph`` (build.py:673), so a node pair
holds exactly one edge and the last write wins (build.py:836-838, :968). Edges
are inserted sorted by relation, and every top-level callee is a symbol the file
already ``contains`` (same file) or ``imports`` (cross-file) — both of which
sort after ``calls``. A file-sourced calls edge is therefore overwritten by the
structural edge on the identical pair. Attributing to a synthetic per-file entry
node avoids the collision, matching what the bash extractor has always done.

These tests run the real CLI against a temp repo and read the exported file, so
a regression at any layer between the extractor and the export fails here.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", "--code-only", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def _graph(repo: Path) -> dict:
    return json.loads((repo / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _edges(graph: dict, relation: str) -> list[tuple[str, str]]:
    links = graph.get("links", graph.get("edges", []))
    return [(e["source"], e["target"]) for e in links if e.get("relation") == relation]


def _repo(tmp_path: Path, name: str, body: str) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / name).write_text(body, encoding="utf-8")
    return repo


def test_rake_toplevel_call_survives_to_graph_json(tmp_path):
    """The reporter's exact repro from PR #2016: a call inside a rake task block.

    Before the entry-node change the exported graph held only the `contains`
    edge; the `calls` edge was created by the extractor and then overwritten.
    """
    repo = _repo(
        tmp_path, "build.rake",
        "def compile\n  1\nend\n\ntask :build do\n  compile()\nend\n",
    )
    r = _run(repo)
    assert r.returncode == 0, f"extract failed: {r.stderr}"

    graph = _graph(repo)
    calls = _edges(graph, "calls")
    ids = {n["id"] for n in graph["nodes"]}
    entry_ids = {i for i in ids if "__entry" in str(i)}
    compile_id = next(n["id"] for n in graph["nodes"] if n.get("label") == "compile()")

    assert entry_ids, f"no entry node in the exported graph; nodes={sorted(ids)}"
    assert any(s in entry_ids and t == compile_id for s, t in calls), (
        "the top-level call did not survive into graph.json — this is the exact "
        f"failure reported on PR #2016. calls={calls}"
    )


def test_python_toplevel_call_survives_to_graph_json(tmp_path):
    """Same guarantee for the shared engine path, not just the rake shape."""
    repo = _repo(tmp_path, "toplevel.py", "def tally():\n    return 1\n\ntally()\n")
    r = _run(repo)
    assert r.returncode == 0, f"extract failed: {r.stderr}"

    graph = _graph(repo)
    calls = _edges(graph, "calls")
    entry_ids = {n["id"] for n in graph["nodes"] if "__entry" in str(n["id"])}
    tally_id = next(n["id"] for n in graph["nodes"] if n.get("label") == "tally()")

    assert any(s in entry_ids and t == tally_id for s, t in calls), (
        f"top-level tally() missing from the exported graph. calls={calls}"
    )


def test_entry_node_is_reachable_from_its_file_in_graph_json(tmp_path):
    """An entry node with no `contains` edge from its file would be an orphan in
    the exported graph — present, but unreachable when walking from the file."""
    repo = _repo(tmp_path, "toplevel.py", "def tally():\n    return 1\n\ntally()\n")
    assert _run(repo).returncode == 0

    graph = _graph(repo)
    entry_ids = {n["id"] for n in graph["nodes"] if "__entry" in str(n["id"])}
    file_ids = {n["id"] for n in graph["nodes"]
                if str(n.get("label", "")).endswith((".py", ".rake", ".rb", ".js"))}
    contains = _edges(graph, "contains")

    assert entry_ids, "expected an entry node"
    assert any(s in file_ids and t in entry_ids for s, t in contains), (
        f"entry node not contained by its file: contains={contains}"
    )
