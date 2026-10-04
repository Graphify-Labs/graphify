"""INC-QML-35: accepted prior import identity bounds external orphan retirement."""
from __future__ import annotations

import copy

import pytest

from graphify.build import _EXTERNAL_STUB_RELATIONS, _load_existing_graph, build_from_json
from graphify.export import to_json
from graphify.qt_orphan_cleanup import previous_import_targets, prune_stale_ast_orphans
from tests.test_qt_cpp_file_roles import cpp_fixture


@pytest.fixture
def prior(tmp_path):
    """Actual C++ import and builder-created external role survive the normal origin-classifying reload."""
    graph = build_from_json(cpp_fixture(tmp_path), root=tmp_path)
    path = tmp_path / "previous.json"
    assert to_json(graph, {}, str(path))
    loaded = _load_existing_graph(path)
    assert loaded is not None
    nodes, edges, hyperedges, directed = loaded
    payload = {"nodes": nodes, "links": edges, "hyperedges": hyperedges, "directed": directed}
    assert next(node for node in nodes if node["id"] == "missing")["_origin"] == "semantic"
    return payload


def targets(prior):
    return previous_import_targets(prior, import_relations=_EXTERNAL_STUB_RELATIONS)


def import_edge(prior):
    return next(edge for edge in prior["links"] if edge.get("relation") == "imports" and edge["target"] == "missing")


def removal(prior, node, *, complete=True, fresh=(), edges=(), hyperedges=()):
    result = {"nodes": [node], "edges": list(edges), "hyperedges": list(hyperedges)}
    before = copy.deepcopy(result)
    candidate = prune_stale_ast_orphans(result, fresh_ids=set(fresh), complete_refresh=complete,
                                       prior_import_ids=targets(prior))
    assert result == before
    return candidate["nodes"]


def test_actual_prior_import_proof_removes_only_unused_external_role_without_mutation(prior):
    """A generated endpoint needs both source-owned prior identity and absence of every live reference."""
    before = copy.deepcopy(prior)
    assert targets(prior) == {"missing"}
    node = next(node for node in prior["nodes"] if node["id"] == "missing")
    assert not removal(prior, node)
    assert prior == before
    # Persisted presentation properties do not convert a generated endpoint
    # into a source definition or alter its known import ownership.
    assert not removal(prior, {**node, "x": 20, "y": 30, "community_name": "Imports"})


@pytest.mark.parametrize("corruption", ["semantic", "unstamped", "relation_list", "relation_foreign", "context",
                                      "confidence", "source_file", "empty_source", "foreign_owner", "foreign_target",
                                      "owner_origin", "owner_source", "owner_role", "duplicate_owner", "duplicate_target",
                                      "partial_source", "partial_target", "foreign_marker", "list_marker", "reverse_directed"])
def test_corrupt_or_foreign_prior_import_has_no_cleanup_authority(prior, corruption):
    """Borrowed historical facts with missing/conflicting ownership cannot retire an external node."""
    edge = import_edge(prior)
    source, target = edge["source"], edge["target"]
    owner = next(node for node in prior["nodes"] if node["id"] == source)
    if corruption in {"semantic", "unstamped"}:
        edge["_origin"] = "semantic" if corruption == "semantic" else None
    elif corruption == "relation_list":
        edge["relation"] = ["imports"]
    elif corruption == "relation_foreign":
        edge["relation"] = "references"
    elif corruption == "context":
        edge["context"] = "qt_context_access"
    elif corruption == "confidence":
        edge["confidence"] = "INFERRED"
    elif corruption in {"source_file", "empty_source"}:
        edge["source_file"] = "unrelated.cpp" if corruption == "source_file" else ""
    elif corruption == "foreign_owner":
        edge["source"] = "absent"
    elif corruption == "foreign_target":
        edge["target"] = "absent"
    elif corruption in {"owner_origin", "owner_source", "owner_role"}:
        key = {"owner_origin": "_origin", "owner_source": "source_file", "owner_role": "file_type"}[corruption]
        owner[key] = "semantic" if corruption == "owner_origin" else "unrelated.cpp" if corruption == "owner_source" else "concept"
    elif corruption in {"duplicate_owner", "duplicate_target"}:
        identity = source if corruption == "duplicate_owner" else target
        prior["nodes"].append(copy.deepcopy(next(node for node in prior["nodes"] if node["id"] == identity)))
    else:
        edge["_src"], edge["_tgt"] = source, target
        if corruption == "partial_source":
            edge.pop("_tgt")
        elif corruption == "partial_target":
            edge.pop("_src")
        elif corruption == "foreign_marker":
            edge["_src"] = "private-needle\nforged"
        elif corruption == "list_marker":
            edge["_tgt"] = [target]
        else:
            prior["directed"] = True
            edge["_src"], edge["_tgt"] = target, source
    before = copy.deepcopy(prior)
    assert not targets(prior)
    node = next(node for node in prior["nodes"] if node["id"] == "missing")
    assert removal(prior, node) == [node]
    assert prior == before


@pytest.mark.parametrize("field", ["nodes", "links"])
@pytest.mark.parametrize("value", [None, {}])
def test_malformed_prior_groups_do_not_supply_proof(prior, field, value):
    prior[field] = value
    assert not targets(prior)


@pytest.mark.parametrize("role", ["foreign_origin", "ast_origin", "metadata", "empty_metadata", "callable", "type",
                                "source", "location", "label", "identity", "external_type"])
def test_authoritative_or_noncanonical_external_role_is_preserved(prior, role):
    """A same-name source/user/unsupported role cannot be erased by a known import target."""
    node = copy.deepcopy(next(node for node in prior["nodes"] if node["id"] == "missing"))
    key, value = {"foreign_origin": ("_origin", "authored"), "ast_origin": ("_origin", "ast"),
                  "metadata": ("metadata", {"native_endpoint": "accepted"}), "empty_metadata": ("metadata", {}),
                  "callable": ("_callable", False), "type": ("type", "class"), "source": ("source_file", "kept.cpp"),
                  "location": ("source_location", "L2"), "label": ("label", "authored label"),
                  "identity": ("id", "authored_missing"), "external_type": ("external", 1)}[role]
    node[key] = value
    assert removal(prior, node) == [node]


@pytest.mark.parametrize("reference", ["partial", "fresh", "ordinary", "nodes", "members", "node_ids"])
def test_live_reference_or_incomplete_refresh_preserves_import_endpoint(prior, reference):
    """Every existing hyperedge spelling, an ordinary edge and fresh identity keep the endpoint live."""
    node = next(node for node in prior["nodes"] if node["id"] == "missing")
    options = {"complete": reference != "partial", "fresh": ("missing",) if reference == "fresh" else (),
               "edges": ({"source": "kept", "target": "missing"},) if reference == "ordinary" else (),
               "hyperedges": ({reference: ["missing"]},) if reference in {"nodes", "members", "node_ids"} else ()}
    assert removal(prior, node, **options) == [node]


def test_complete_undirected_marker_pair_preserves_actual_prior_source_ownership(prior):
    edge = import_edge(prior)
    source, target = edge["source"], edge["target"]
    edge["source"], edge["target"] = target, source
    edge["_src"], edge["_tgt"] = source, target
    assert targets(prior) == {"missing"}
