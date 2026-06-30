"""Indirect dispatch via collection literals (dispatch tables) — #1566 slice 1.

A function referenced as a VALUE inside a dict/list/tuple/set literal
(`ROUTES = {"x": handler}`, `HOOKS = [on_start]`) is a real dependency. It is emitted
under the distinct INFERRED `indirect_call` relation, reusing the call-argument guards:
resolve only to a callable def, and skip a param/local shadow. Positives (module + function
level, all four literal kinds) plus the shadow / non-callable negatives.
"""
import networkx as nx

from graphify.affected import affected_nodes
from graphify.extract import extract_python


def _extract(tmp_path, src):
    (tmp_path / "m.py").write_text(src)
    r = extract_python(tmp_path / "m.py")
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}
    return r, nid


def _indirect(r):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "indirect_call"}


MODULE_TABLE = '''\
def create_user(): ...
def delete_user(): ...
def on_start(): ...
def on_stop(): ...

ROUTES = {"create": create_user, "delete": delete_user}   # module-level dict registry
HOOKS = [on_start, on_stop]                                # module-level list
'''


def test_module_level_dict_and_list_emit_indirect_call(tmp_path):
    r, nid = _extract(tmp_path, MODULE_TABLE)
    ind = _indirect(r)
    f = nid["m.py"]
    assert (f, nid["create_user"]) in ind
    assert (f, nid["delete_user"]) in ind
    assert (f, nid["on_start"]) in ind
    assert (f, nid["on_stop"]) in ind
    for e in r["edges"]:
        if e["relation"] == "indirect_call":
            assert e["context"] == "collection" and e["confidence"] == "INFERRED"
    # never leaks into the precise `calls` relation
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (f, nid["create_user"]) not in calls


def test_collection_dispatch_feeds_affected(tmp_path):
    r, nid = _extract(tmp_path, MODULE_TABLE)
    g = nx.DiGraph()
    for n in r["nodes"]:
        g.add_node(n["id"], **n)
    for e in r["edges"]:
        g.add_edge(e["source"], e["target"], **e)
    affected = {h.node_id for h in affected_nodes(g, nid["create_user"])}
    assert nid["m.py"] in affected   # the module that registers it is in the blast radius


FUNCTION_TABLE = '''\
def create_user(): ...

def setup():
    routes = {"create": create_user}    # function-level dispatch table
    return routes
'''


def test_function_level_collection_emits_indirect_call(tmp_path):
    r, nid = _extract(tmp_path, FUNCTION_TABLE)
    assert (nid["setup"], nid["create_user"]) in _indirect(r)


TUPLE_SET = '''\
def a(): ...
def b(): ...

PAIR = (a, b)        # tuple
UNIQUE = {a, b}      # set
'''


def test_tuple_and_set_literals_emit_indirect_call(tmp_path):
    r, nid = _extract(tmp_path, TUPLE_SET)
    ind = _indirect(r)
    f = nid["m.py"]
    assert (f, nid["a"]) in ind and (f, nid["b"]) in ind


# ── negatives: the guards must hold for collections too ──────────────────────

PARAM_SHADOW = '''\
def handler(): ...

def setup(handler):
    routes = {"x": handler}      # `handler` is a PARAMETER, not the module fn
    return routes
'''


def test_param_shadow_in_collection_emits_nothing(tmp_path):
    r, nid = _extract(tmp_path, PARAM_SHADOW)
    assert all(t != nid["handler"] for _s, t in _indirect(r))


LOCAL_SHADOW = '''\
def config(): ...

def use():
    config = {"k": 1}        # local DATA binding shadows config()
    table = {"c": config}    # `config` here is the local dict, not the fn
    return table
'''


def test_local_shadow_in_collection_emits_nothing(tmp_path):
    r, nid = _extract(tmp_path, LOCAL_SHADOW)
    assert (nid["use"], nid["config"]) not in _indirect(r)


NON_CALLABLE = '''\
def handler(): ...

TIMEOUT = 30
CONFIG = {"timeout": TIMEOUT, "label": "ready"}   # data values, not callables
'''


def test_non_callable_collection_values_emit_nothing(tmp_path):
    r, _nid = _extract(tmp_path, NON_CALLABLE)
    # TIMEOUT is not a callable def; the string is not an identifier -> no indirect edges
    assert _indirect(r) == set()
