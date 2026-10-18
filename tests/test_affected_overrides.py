"""`affected` on a method that overrides a supertype member must reach the callers bound to that member.

A call site names the declared type: `visitor.head()` with `visitor: NodeVisitor` binds to
`NodeVisitor.head`, and at runtime runs `FormattingVisitor.head`. Changing the override therefore
affects those callers, although no edge points at the override. The overridden member is walked as a
stepping stone (it did not change), unless a real edge reaches it too.
"""
from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.affected import affected_nodes, load_graph
from graphify.extract import extract


def _graph(*edges: tuple[str, str, str]) -> nx.DiGraph:
    g = nx.DiGraph()
    for src, tgt, rel in edges:
        for nid in (src, tgt):
            if nid not in g:
                g.add_node(nid, label=f".{nid.split('.')[-1]}()" if "." in nid else nid)
        g.add_edge(src, tgt, relation=rel)
    return g


def _hits(g, seed, depth=2):
    return {h.node_id: h.depth for h in affected_nodes(g, seed, depth=depth)}


def test_caller_of_the_overridden_interface_method_is_affected():
    g = _graph(
        ("Visitor", "Visitor.head", "method"),
        ("Impl", "Impl.head", "method"),
        ("Impl", "Visitor", "implements"),
        ("walk", "Visitor.head", "calls"),
    )
    hits = _hits(g, "Impl.head")
    assert hits.get("walk") == 1
    assert "Visitor.head" not in hits, "the overridden member did not change"


def test_override_through_a_superclass_chain():
    g = _graph(
        ("Root", "Root.close", "method"),
        ("Mid", "Root", "inherits"),
        ("Leaf", "Mid", "inherits"),
        ("Leaf", "Leaf.close", "method"),
        ("client", "Root.close", "calls"),
        ("outer", "client", "calls"),
    )
    hits = _hits(g, "Leaf.close")
    assert hits == {"client": 1, "outer": 2}


def test_overridden_member_reached_by_a_real_edge_is_reported():
    # An overload in the base calls the abstract member the subclass overrides;
    # both share one node, so the base member really is a caller.
    g = _graph(
        ("Base", "Base.read", "method"),
        ("Base.read", "Base.read_all", "calls"),
        ("Base", "Base.read_all", "method"),
        ("Impl", "Base", "inherits"),
        ("Impl", "Impl.read", "method"),
        ("Base.read_all", "Base.read", "calls"),
    )
    hits = _hits(g, "Impl.read")
    assert hits.get("Base.read_all") == 1


def test_recursive_overridden_member_is_a_caller_of_the_override():
    # `Base.m` calling `m()` on its own object dispatches to `Impl.m` for an Impl
    # instance, so the self-loop is a real edge into it: Base.m is affected.
    g = _graph(
        ("Base", "Base.m", "method"),
        ("Base.m", "Base.m", "calls"),
        ("Impl", "Base", "inherits"),
        ("Impl", "Impl.m", "method"),
    )
    assert _hits(g, "Impl.m") == {"Base.m": 1}


def test_same_depth_keeps_the_depth_limit_exact():
    # depth=1 must still list the supertype member's direct callers.
    g = _graph(
        ("Iface", "Iface.run", "method"),
        ("Impl", "Iface", "implements"),
        ("Impl", "Impl.run", "method"),
        ("a", "Iface.run", "calls"),
        ("b", "a", "calls"),
    )
    assert _hits(g, "Impl.run", depth=1) == {"a": 1}


def test_unrelated_same_named_method_is_not_walked():
    g = _graph(
        ("Other", "Other.head", "method"),
        ("Impl", "Impl.head", "method"),
        ("walk", "Other.head", "calls"),
    )
    assert "walk" not in _hits(g, "Impl.head")


def test_inheritance_cycle_terminates():
    g = _graph(
        ("A", "B", "inherits"),
        ("B", "A", "inherits"),
        ("A", "A.m", "method"),
        ("B", "B.m", "method"),
        ("x", "B.m", "calls"),
    )
    assert _hits(g, "A.m") == {"x": 1}


def test_undirected_graph_is_unchanged():
    g = _graph(
        ("Visitor", "Visitor.head", "method"),
        ("Impl", "Impl.head", "method"),
        ("Impl", "Visitor", "implements"),
        ("walk", "Visitor.head", "calls"),
    ).to_undirected()
    # no edge direction, no way to tell a subtype from a supertype: no expansion
    assert "walk" not in _hits(g, "Impl.head")


def _extract_graph(tmp_path: Path, files: dict[str, str]) -> nx.Graph:
    paths = []
    for name, body in files.items():
        p = tmp_path / name
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    # loaded the way `graphify affected` loads graph.json (parallel edges kept)
    graph_json = tmp_path / "graph.json"
    graph_json.write_text(json.dumps({"nodes": result["nodes"], "links": result["edges"]}), encoding="utf-8")
    return load_graph(graph_json)


def _node(g, label, id_suffix):
    return next(n for n, a in g.nodes(data=True) if a.get("label") == label and n.endswith(id_suffix))


def test_java_interface_caller_end_to_end(tmp_path: Path):
    g = _extract_graph(tmp_path, {
        "NodeVisitor.java": "interface NodeVisitor { void head(String n); }\n",
        "Printer.java": "class Printer implements NodeVisitor { public void head(String n) {} }\n",
        "Walker.java": "class Walker { void walk(NodeVisitor v) { v.head(\"x\"); } }\n",
    })
    hits = _hits(g, _node(g, ".head()", "printer_head"))
    assert _node(g, ".walk()", "walker_walk") in hits


def test_typescript_abstract_method_caller_end_to_end(tmp_path: Path):
    g = _extract_graph(tmp_path, {
        "cache.ts": "export abstract class Cache { abstract connect(): void; }\n",
        "db.ts": ('import { Cache } from "./cache";\n'
                  "export class DbCache extends Cache { connect(): void {} }\n"),
        "app.ts": ('import { Cache } from "./cache";\n'
                   "export function boot(c: Cache) { c.connect(); }\n"),
    })
    hits = _hits(g, _node(g, ".connect()", "dbcache_connect"))
    assert _node(g, "boot()", "app_boot") in hits


def test_python_base_method_caller_end_to_end(tmp_path: Path):
    g = _extract_graph(tmp_path, {
        "base.py": "class Base:\n    def run(self):\n        pass\n\n    def go(self):\n        self.run()\n",
        "impl.py": "from base import Base\n\n\nclass Impl(Base):\n    def run(self):\n        pass\n",
    })
    hits = _hits(g, _node(g, ".run()", "impl_impl_run"))
    assert _node(g, ".go()", "base_base_go") in hits
