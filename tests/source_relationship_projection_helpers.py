"""Neutral source facts and public persistence helpers for INC127's caller frame."""
from __future__ import annotations

from copy import deepcopy
import json

from graphify.extract import extract
from graphify.graph_direction import logical_endpoints
from graphify.paths import load_node_link_graph
from graphify.source_relationships import FIELD


def storage(raw, profile):
    """Select storage only; the optional marker grants no native target authority."""
    if profile:
        raw["graph"] = {FIELD: {"contract_version": 1}}
    return raw


def imports(root, profile):
    """Use actual neutral Python declarations/imports, without executing corpus code."""
    root.mkdir(parents=True, exist_ok=True)
    first, second = root / "alpha.py", root / "beta.py"
    first.write_bytes(b"import beta\n\ndef entry(): return 1\n")
    second.write_bytes(b"def helper(): return 2\n")
    raw = extract([first, second], root=root, cache_root=root, parallel=False)
    assert not raw.get("failed_sources") and not raw.get("error")
    target = next(node["id"] for node in raw["nodes"] if node.get("label") == "beta.py")
    edge = next(edge for edge in raw["edges"] if edge.get("relation") == "imports")
    assert edge["target"] == target
    return storage(raw, profile), edge, target


def calls(profile, *, imported=False, import_first=False):
    """Author only the supported raw transport; production owns all admission rules."""
    caller = "z_caller" if import_first else "a_caller"
    importer = "a_importer" if import_first else "z_importer"
    raw = {"nodes": [
        {"id": caller, "label": "invoke", "type": "function",
         "source_file": "caller.py", "source_location": "L1"},
        {"id": importer, "label": "module", "type": "file",
         "source_file": "imports.py", "source_location": "L1"}], "edges": []}
    if imported:
        raw["edges"].append({"source": importer, "target": "signal", "relation": "imports",
                             "context": "import", "confidence": "EXTRACTED",
                             "source_file": "imports.py", "source_location": "L1"})
    raw["edges"].append({"source": caller, "target": "signal", "relation": "calls",
                         "context": "call", "confidence": "EXTRACTED",
                         "source_file": "caller.py", "source_location": "L1"})
    return storage(raw, profile), caller


def arcs(graph, relation):
    """Read logical direction through the public direction contract, not storage order."""
    result = set()
    for left, right, data in graph.edges(data=True):
        if data.get("relation") == relation:
            pair = logical_endpoints(left, right, data, directed=graph.is_directed())
            assert pair is not None
            result.add(pair)
    return result


def state(graph):
    return deepcopy((graph.graph, list(graph.nodes(data=True)), list(graph.edges(data=True))))


def readback(path):
    """The PATH loader, rather than only in-memory JSON, owns consumer acceptance."""
    return load_node_link_graph(path), json.loads(path.read_text(encoding="utf-8"))


def observations(payload):
    """Expose complete records without copying a primary record's authority to a peer."""
    return [(link, record) for link in payload["links"]
            for record in [link, *link.get("also_seen", [])]]
