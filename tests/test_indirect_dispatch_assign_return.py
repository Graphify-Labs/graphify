"""Indirect dispatch via assignment + return references — #1566 slice 2.

A function bound to a name (`cb = handler`) or returned from a factory
(`def make(): return handler`) is a real reference. It is emitted under `indirect_call`
via the shared resolve-and-emit guard. The VALUE side only -- the assignment TARGET is a
new local binding, not a reference -- so the shadow guard still holds: a param or local
named on the RHS is the local, not the module fn. The negatives pin that the false edges
#1565 fixed do not come back.
"""
import networkx as nx

from graphify.affected import affected_nodes
from graphify.extract import extract_python


def _extract(tmp_path, src):
    (tmp_path / "m.py").write_text(src)
    r = extract_python(tmp_path / "m.py")
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}
    return r, nid


def _ind(r):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "indirect_call"}


ASSIGN_RETURN = '''\
def handler(): ...
def other(): ...

def bind():
    cb = handler        # assignment reference
    return cb

def make():
    return other        # return reference
'''


def test_assignment_and_return_emit_indirect_call(tmp_path):
    r, nid = _extract(tmp_path, ASSIGN_RETURN)
    ind = _ind(r)
    assert (nid["bind"], nid["handler"]) in ind
    assert (nid["make"], nid["other"]) in ind
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (nid["bind"], nid["handler"]) not in calls     # not in the precise relation
    for e in r["edges"]:
        if e["relation"] == "indirect_call":
            assert e["context"] in ("assignment", "return") and e["confidence"] == "INFERRED"


MULTI = '''\
def f(): ...
def g(): ...

def via():
    a, b = f, g        # tuple-unpack assignment (expression_list RHS)
    return a
'''


def test_multiple_assignment_emits_for_each(tmp_path):
    r, nid = _extract(tmp_path, MULTI)
    ind = _ind(r)
    assert (nid["via"], nid["f"]) in ind and (nid["via"], nid["g"]) in ind


MODULE_ALIAS = '''\
def handler(): ...

CALLBACK = handler      # module-level alias / re-export
'''


def test_module_level_assignment_emits_indirect_call(tmp_path):
    r, nid = _extract(tmp_path, MODULE_ALIAS)
    assert (nid["m.py"], nid["handler"]) in _ind(r)


def test_assignment_feeds_affected(tmp_path):
    r, nid = _extract(tmp_path, ASSIGN_RETURN)
    g = nx.DiGraph()
    for n in r["nodes"]:
        g.add_node(n["id"], **n)
    for e in r["edges"]:
        g.add_edge(e["source"], e["target"], **e)
    affected = {h.node_id for h in affected_nodes(g, nid["handler"])}
    assert nid["bind"] in affected


# ── negatives: the inverted-shadow trap (must not reintroduce #1565's false edges) ──

PARAM_SHADOW = '''\
def handler(): ...

def via(handler):
    cb = handler        # `handler` is a PARAMETER, not the module fn
    return handler
'''


def test_param_shadow_emits_nothing(tmp_path):
    r, nid = _extract(tmp_path, PARAM_SHADOW)
    assert all(t != nid["handler"] for _s, t in _ind(r))


LOCAL_SHADOW = '''\
def handler(): ...

def via():
    handler = object()  # local DATA binding shadows the module fn
    cb = handler        # `handler` here is the local, not the module fn
    return handler
'''


def test_local_shadow_emits_nothing(tmp_path):
    r, nid = _extract(tmp_path, LOCAL_SHADOW)
    assert all(t != nid["handler"] for _s, t in _ind(r))


NON_CALLABLE = '''\
def handler(): ...

def via():
    cb = TIMEOUT        # TIMEOUT is not a callable def
    return cb
'''


def test_non_callable_value_emits_nothing(tmp_path):
    r, _nid = _extract(tmp_path, NON_CALLABLE)
    assert _ind(r) == set()
