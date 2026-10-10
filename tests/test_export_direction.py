"""Reloading graph.json must keep each edge's stored direction (#4066).

graph.json is written ``directed: false`` and carries true direction in each
link's arc order (#563), or in ``_src``/``_tgt`` markers on legacy
canonicalized files (#2309). A plain undirected ``node_link_graph`` load
re-orders each edge's endpoints by node-list position, so a link whose target
node precedes its source node comes back reversed.

query/path/explain (#2309, #2487), affected (#1174), merge-graphs (#2261) and
the MCP server already restore direction. These tests cover the remaining
reloaders: the export subcommands, the watch/update HTML re-render, and the git
merge driver, which writes the committed graph.json.
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable
# A fixed positive limit, so HTML rendering never depends on the caller's
# shell (GRAPHIFY_VIZ_NODE_LIMIT=0 disables it, e.g. on CI runners).
_VIZ_ENV = {"GRAPHIFY_VIZ_NODE_LIMIT": "5000"}


def _graph_json(tmp_path: Path) -> Path:
    """The `graphify extract` shape: undirected flag, direction in arc order.

    ``callee`` precedes ``caller`` in the node list, the exact condition under
    which an undirected load flips the edge. ``helper`` -> ``util`` is listed
    source-first, so it survives either way and guards against over-correction.
    """
    out = tmp_path / "graphify-out"
    out.mkdir()
    data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": "callee", "label": "callee()", "file_type": "code", "source_file": "a.py", "community": 0},
            {"id": "caller", "label": "caller()", "file_type": "code", "source_file": "a.py", "community": 0},
            {"id": "helper", "label": "helper()", "file_type": "code", "source_file": "a.py", "community": 0},
            {"id": "util", "label": "util()", "file_type": "code", "source_file": "a.py", "community": 0},
            # legacy canonicalized link: arc flipped, markers carry the truth
            {"id": "legacy_b", "label": "legacy_b()", "file_type": "code", "source_file": "a.py", "community": 0},
            {"id": "legacy_a", "label": "legacy_a()", "file_type": "code", "source_file": "a.py", "community": 0},
        ],
        "links": [
            {"source": "caller", "target": "callee", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "helper", "target": "util", "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "legacy_b", "target": "legacy_a", "_src": "legacy_a", "_tgt": "legacy_b",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = out / "graph.json"
    p.write_text(json.dumps(data))
    (out / ".graphify_analysis.json").write_text(json.dumps(
        {"communities": {"0": ["callee", "caller", "helper", "util", "legacy_a", "legacy_b"]}}))
    return p


TRUE_ARCS = {("caller", "callee"), ("helper", "util"), ("legacy_a", "legacy_b")}


def _run(args: list[str], cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess:
    env = dict(env if env is not None else os.environ, GRAPHIFY_NO_AUTO_REFRESH="1", **_VIZ_ENV)
    return subprocess.run([PYTHON, "-m", "graphify", *args], cwd=cwd,
                          capture_output=True, text=True, env=env)


def _html_arcs(html_path: Path) -> set[tuple[str, str]]:
    html = html_path.read_text(encoding="utf-8")
    return set(re.findall(r'"from": "([^"]+)", "to": "([^"]+)"', html))


def test_load_node_link_graph_stamps_stored_direction(tmp_path):
    from graphify.paths import load_node_link_graph

    G = load_node_link_graph(_graph_json(tmp_path))
    arcs = {(d.get("_src", u), d.get("_tgt", v)) for u, v, d in G.edges(data=True)}
    assert arcs == TRUE_ARCS


def test_export_html_draws_arrows_in_stored_direction(tmp_path):
    _graph_json(tmp_path)
    r = _run(["export", "html"], tmp_path)
    assert r.returncode == 0, r.stderr
    assert _html_arcs(tmp_path / "graphify-out" / "graph.html") == TRUE_ARCS


def test_export_cypher_merges_edges_in_stored_direction(tmp_path):
    _graph_json(tmp_path)
    r = _run(["export", "neo4j"], tmp_path)
    assert r.returncode == 0, r.stderr
    cypher = (tmp_path / "graphify-out" / "cypher.txt").read_text(encoding="utf-8")
    arcs = set(re.findall(r"MATCH \(a \{id: '([^']+)'\}\), \(b \{id: '([^']+)'\}\)", cypher))
    assert arcs == TRUE_ARCS


# Fake SDKs, imported by the subprocess through PYTHONPATH, that log the
# (src, tgt) of every relationship MERGE instead of talking to a database.
_FAKE_NEO4J = '''
import json, os
class _S:
    def __enter__(self): return self
    def __exit__(self, *a): return False
    def run(self, q, **p):
        if "src" in p:
            with open(os.environ["FAKE_ARC_LOG"], "a") as f:
                f.write(json.dumps([p["src"], p["tgt"]]) + "\\n")
class _D:
    def session(self, **k): return _S()
    def close(self): pass
class GraphDatabase:
    @staticmethod
    def driver(*a, **k): return _D()
'''

_FAKE_FALKORDB = '''
import json, os
class _G:
    def query(self, q, params=None):
        if params and "src" in params:
            with open(os.environ["FAKE_ARC_LOG"], "a") as f:
                f.write(json.dumps([params["src"], params["tgt"]]) + "\\n")
class FalkorDB:
    def __init__(self, *a, **k): pass
    def select_graph(self, name): return _G()
'''


def _push_arcs(tmp_path: Path, backend: str) -> set[tuple[str, str]]:
    fakes = tmp_path / "fakes"
    (fakes / backend).mkdir(parents=True)
    (fakes / backend / "__init__.py").write_text(
        _FAKE_NEO4J if backend == "neo4j" else _FAKE_FALKORDB)
    log = tmp_path / "arcs.log"
    env = {k: v for k, v in os.environ.items() if k not in ("NEO4J_PASSWORD", "FALKORDB_PASSWORD")}
    env["PYTHONPATH"] = os.pathsep.join([str(fakes), env.get("PYTHONPATH", "")])
    env["FAKE_ARC_LOG"] = str(log)
    r = _run(["export", backend, "--push", "bolt://localhost:7687", "--password", "x"], tmp_path, env)
    assert r.returncode == 0, r.stderr
    return {tuple(json.loads(line)) for line in log.read_text().splitlines()}


def test_export_neo4j_push_sends_stored_direction(tmp_path):
    _graph_json(tmp_path)
    assert _push_arcs(tmp_path, "neo4j") == TRUE_ARCS


def test_export_falkordb_push_sends_stored_direction(tmp_path):
    _graph_json(tmp_path)
    assert _push_arcs(tmp_path, "falkordb") == TRUE_ARCS


def test_export_obsidian_canvas_edges_in_stored_direction(tmp_path):
    """JSON Canvas draws the arrowhead at ``toNode`` by default."""
    _graph_json(tmp_path)
    r = _run(["export", "obsidian"], tmp_path)
    assert r.returncode == 0, r.stderr
    canvas = json.loads((tmp_path / "graphify-out" / "obsidian" / "graph.canvas").read_text())
    arcs = {(e["fromNode"][2:], e["toNode"][2:]) for e in canvas["edges"]}
    assert arcs == TRUE_ARCS


def test_watch_html_reconcile_draws_stored_direction(tmp_path, monkeypatch):
    """`graphify update`, `watch` and the git hooks re-render graph.html here."""
    from graphify.watch import _reconcile_graph_html

    for key, value in _VIZ_ENV.items():
        monkeypatch.setenv(key, value)
    gp = _graph_json(tmp_path)
    assert _reconcile_graph_html(gp.parent, json.loads(gp.read_text())) == "rendered"
    assert _html_arcs(gp.parent / "graph.html") == TRUE_ARCS


def test_merge_driver_keeps_stored_direction_in_arc_order(tmp_path):
    """Even a merge of three identical copies used to rewrite graph.json reversed."""
    gp = _graph_json(tmp_path)
    base, cur, oth = (tmp_path / n for n in ("base.json", "cur.json", "oth.json"))
    for p in (base, cur, oth):
        p.write_text(gp.read_text())
    r = _run(["merge-driver", str(base), str(cur), str(oth)], tmp_path)
    assert r.returncode == 0, r.stderr
    merged = json.loads(cur.read_text())
    # Arc order is the direction (what to_json writes); no markers left behind.
    assert {(l["source"], l["target"]) for l in merged["links"]} == TRUE_ARCS
    assert not any("_src" in l or "_tgt" in l for l in merged["links"])
