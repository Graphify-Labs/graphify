"""Reflective dispatch via getattr string literals — #1566 slice 3.

``getattr(obj, "handler")`` names a callable by a string literal; the attribute is
looked up by that exact name, so it resolves to a callable def of the same label and is
emitted under ``indirect_call`` (context ``"getattr"``, INFERRED). Only a PLAIN string
literal is resolvable — a variable, f-string, concatenation, or any expression is dynamic
and emits nothing.

The scope rule is the INVERSE of the identifier paths (#1565 args, #1566 assignment /
return): a string is an attribute name, never shadowed by a param/local, so a getattr
whose name collides with a same-named parameter STILL emits. ``test_..._not_shadowed_by_param``
pins that — reusing the identifier shadow guard here would be a false NEGATIVE.
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


BASIC = '''\
def handler(): ...
def other(): ...

def dispatch(obj):
    fn = getattr(obj, "handler")     # string-literal attribute name
    return fn()
'''


def test_getattr_string_literal_emits_indirect_call(tmp_path):
    r, nid = _extract(tmp_path, BASIC)
    assert (nid["dispatch"], nid["handler"]) in _ind(r)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    assert (nid["dispatch"], nid["handler"]) not in calls     # not in the precise relation
    for e in r["edges"]:
        if e["relation"] == "indirect_call" and e["target"] == nid["handler"]:
            assert e["context"] == "getattr" and e["confidence"] == "INFERRED"


DEFAULT_ARG = '''\
def handler(): ...

def dispatch(obj):
    return getattr(obj, "handler", None)()   # 3-arg form, called inline
'''


def test_getattr_with_default_emits(tmp_path):
    r, nid = _extract(tmp_path, DEFAULT_ARG)
    assert (nid["dispatch"], nid["handler"]) in _ind(r)


MODULE_LEVEL = '''\
import sys
def handler(): ...

HANDLER = getattr(sys.modules[__name__], "handler")   # module-level reflective alias
'''


def test_module_level_getattr_emits(tmp_path):
    r, nid = _extract(tmp_path, MODULE_LEVEL)
    assert (nid["m.py"], nid["handler"]) in _ind(r)


def test_getattr_feeds_affected(tmp_path):
    r, nid = _extract(tmp_path, BASIC)
    g = nx.DiGraph()
    for n in r["nodes"]:
        g.add_node(n["id"], **n)
    for e in r["edges"]:
        g.add_edge(e["source"], e["target"], **e)
    affected = {h.node_id for h in affected_nodes(g, nid["handler"])}
    assert nid["dispatch"] in affected


# ── the scope rule: a string is an attribute name, NOT shadowed by a local ──

PARAM_COLLISION = '''\
def handler(): ...

def via(handler):                        # param `handler` shadows the IDENTIFIER
    return getattr(handler, "handler")   # but the STRING "handler" -> module fn regardless
'''


def test_getattr_string_not_shadowed_by_param(tmp_path):
    # The identifier arg `handler` is correctly skipped (it is the shadowing param), but
    # the string "handler" names an attribute and must still resolve to the module fn.
    # Applying the identifier shadow guard to the string would be a false NEGATIVE.
    r, nid = _extract(tmp_path, PARAM_COLLISION)
    got = [e for e in r["edges"]
           if e["relation"] == "indirect_call"
           and (e["source"], e["target"]) == (nid["via"], nid["handler"])]
    assert got and all(e["context"] == "getattr" for e in got)


# ── negatives: a dynamic name is unresolvable → no edge ──

DYNAMIC = '''\
def handler(): ...

def via(obj, name, evt):
    a = getattr(obj, name)           # variable name -- unresolvable
    b = getattr(obj, f"on_{evt}")    # f-string -- dynamic
    c = getattr(obj, "on_" + evt)    # concatenation -- dynamic
    return a, b, c
'''


def test_dynamic_getattr_names_emit_nothing(tmp_path):
    r, nid = _extract(tmp_path, DYNAMIC)
    assert all(s != nid["via"] for s, _t in _ind(r))


NON_CALLABLE = '''\
TIMEOUT = 30

def via(obj):
    return getattr(obj, "TIMEOUT")   # resolves to a data name, not a callable
'''


def test_getattr_non_callable_name_emits_nothing(tmp_path):
    r, _nid = _extract(tmp_path, NON_CALLABLE)
    assert _ind(r) == set()


METHOD_NOT_BUILTIN = '''\
def handler(): ...

class Registry:
    def getattr(self, name): ...      # a METHOD named getattr, not the builtin

def via(reg):
    return reg.getattr("handler")     # reg.getattr(...) is the method, not the builtin
'''


def test_method_named_getattr_is_not_the_builtin(tmp_path):
    r, nid = _extract(tmp_path, METHOD_NOT_BUILTIN)
    assert all(t != nid["handler"] for _s, t in _ind(r))
