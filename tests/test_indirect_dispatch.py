"""Indirect dispatch edges.

A function passed BY NAME as a call argument (`executor.submit(fn)`, `Thread(target=fn)`) is a
real dependency, but the callee-only call scan never recorded it — so `affected` (blast radius)
dropped those callers. These tests pin that such calls now emit a distinct `indirect_call` edge
(leaving the precise `calls` relation untouched) and that `affected` picks them up.
"""
import networkx as nx

from graphify.affected import affected_nodes
from graphify.extract import extract_python

SRC = '''\
import threading


def handler(x):
    return x * 2


def direct():
    return handler(1)                          # direct call -> `calls`


def via_submit(pool):
    pool.submit(handler, 1)                    # indirect: positional arg


def via_thread():
    threading.Thread(target=handler).start()   # indirect: keyword arg
'''


def _build(tmp_path):
    (tmp_path / "dispatch.py").write_text(SRC)
    r = extract_python(tmp_path / "dispatch.py")
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}   # labels are "handler()"
    return r, nid


def test_emits_indirect_call_edges_and_keeps_calls_precise(tmp_path):
    r, nid = _build(tmp_path)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    indirect = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "indirect_call"}
    handler = nid["handler"]

    # the direct caller stays a `calls` edge — precise relation not regressed
    assert (nid["direct"], handler) in calls
    # the two indirect callers are captured, and under the DISTINCT relation
    assert (nid["via_submit"], handler) in indirect
    assert (nid["via_thread"], handler) in indirect
    assert (nid["via_submit"], handler) not in calls

    for e in (e for e in r["edges"] if e["relation"] == "indirect_call"):
        assert e["context"] == "argument" and e["confidence"] == "INFERRED"


def test_affected_includes_indirect_callers(tmp_path):
    r, nid = _build(tmp_path)
    g = nx.DiGraph()
    for n in r["nodes"]:
        g.add_node(n["id"], **n)
    for e in r["edges"]:
        g.add_edge(e["source"], e["target"], **e)

    affected = {h.node_id for h in affected_nodes(g, nid["handler"])}
    # blast radius of `handler` now includes the dispatchers it used to drop
    assert nid["via_submit"] in affected
    assert nid["via_thread"] in affected
