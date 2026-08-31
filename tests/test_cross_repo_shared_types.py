"""`merge-graphs` links a type declaration two repos share (#3007).

Node ids are repo-prefixed, so a contract type both services declare arrives as
two unconnected nodes and a traversal cannot cross the repo boundary even though
both sides name the same type. The merge now adds a `same_type_as` edge between
declarations that agree on namespace and name and come from different repos.

Namespace agreement is what keeps this from linking two classes that merely
picked the same short name, so the cases below pin both halves of that rule.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable


def _run(args, cwd):
    return subprocess.run([PYTHON, "-m", "graphify"] + args, cwd=cwd,
                          capture_output=True, text=True)


def _type_node(node_id: str, label: str, namespace: str | None, source_file: str = "a.cs"):
    node: dict = {
        "id": node_id,
        "label": label,
        "source_file": source_file,
        "_callable_class": True,
        "_callable": True,
    }
    if namespace is not None:
        node["metadata"] = {"namespace": namespace}
    return node


def _write(p: Path, nodes: list[dict]):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": nodes, "links": [],
    }))


def _merge(tmp_path, left: list[dict], right: list[dict]):
    a = tmp_path / "svc_a" / "graphify-out" / "graph.json"
    b = tmp_path / "svc_b" / "graphify-out" / "graph.json"
    _write(a, left)
    _write(b, right)
    out = tmp_path / "merged.json"
    r = _run(["merge-graphs", str(a), str(b), "--out", str(out)], tmp_path)
    assert r.returncode == 0, f"merge failed: {r.stderr}"
    data = json.loads(out.read_text())
    links = [e for e in data["links"] if e.get("relation") == "same_type_as"]
    return links, data


def test_same_namespace_and_name_across_repos_are_linked(tmp_path):
    links, _ = _merge(
        tmp_path,
        [_type_node("evt", "OrderPlaced", "Contracts.Events")],
        [_type_node("evt", "OrderPlaced", "Contracts.Events")],
    )
    assert len(links) == 1
    endpoints = {links[0]["source"], links[0]["target"]}
    assert endpoints == {"svc_a::evt", "svc_b::evt"}
    assert links[0]["confidence"] == "INFERRED"


def test_same_name_in_different_namespaces_is_not_linked(tmp_path):
    # Two services with their own unrelated `Settings` class.
    links, _ = _merge(
        tmp_path,
        [_type_node("s", "Settings", "Catalog.Configuration")],
        [_type_node("s", "Settings", "Search.Configuration")],
    )
    assert links == []


def test_two_declarations_inside_one_repo_are_not_linked(tmp_path):
    # A partial class or a same-named type in two files of one repo is not a
    # cross-repo join, and merging them is #296's question, not this one.
    links, _ = _merge(
        tmp_path,
        [
            _type_node("one", "OrderPlaced", "Contracts.Events", "one.cs"),
            _type_node("two", "OrderPlaced", "Contracts.Events", "two.cs"),
        ],
        [_type_node("other", "Unrelated", "Contracts.Events")],
    )
    assert links == []


def test_a_type_with_no_namespace_is_not_linked(tmp_path):
    # Without a namespace the name alone is too weak to claim they are the same.
    links, _ = _merge(
        tmp_path,
        [_type_node("evt", "OrderPlaced", None)],
        [_type_node("evt", "OrderPlaced", None)],
    )
    assert links == []


def test_non_type_nodes_are_not_linked(tmp_path):
    method_a = {"id": "m", "label": ".Handle()", "source_file": "a.cs",
                "metadata": {"namespace": "Contracts.Events"}}
    method_b = dict(method_a)
    links, _ = _merge(tmp_path, [method_a], [method_b])
    assert links == []


def test_sourceless_stub_is_not_linked(tmp_path):
    # A stub minted for a dangling reference has no declaration behind it.
    stub = {"id": "evt", "label": "OrderPlaced", "_callable_class": True,
            "metadata": {"namespace": "Contracts.Events"}}
    links, _ = _merge(
        tmp_path,
        [stub],
        [_type_node("evt", "OrderPlaced", "Contracts.Events")],
    )
    assert links == []


def test_same_namespace_and_name_link_even_when_the_declarations_drift(tmp_path):
    """The join key is namespace+name, deliberately NOT structural. Two repos
    whose shared contract type has drifted (different source files, different
    surrounding members) still link — a shared contract navigable across repos is
    the point, and requiring structural equality would defeat it. This pins that
    boundary so a future change that tried to gate on member equality fails here."""
    links, _ = _merge(
        tmp_path,
        [
            _type_node("evt", "OrderPlaced", "Contracts.Events", "v1/order.cs"),
            _type_node("extra_a", "AuditLog", "Contracts.Events", "v1/audit.cs"),
        ],
        [
            _type_node("evt", "OrderPlaced", "Contracts.Events", "v2/order_placed.cs"),
            _type_node("extra_b", "Telemetry", "Contracts.Events", "v2/telemetry.cs"),
        ],
    )
    # Only the shared name links; the repo-unique AuditLog/Telemetry do not.
    assert len(links) == 1, links
    assert {links[0]["source"], links[0]["target"]} == {"svc_a::evt", "svc_b::evt"}
