"""REQ-QML-016-AC01/AC04 accepted ancestral event endpoint identities."""
import json
import copy

import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata, update_qt
from graphify.paths import load_node_link_graph
from graphify.qt_event_index import QtEventIndex
from graphify.serve import _query_graph_text
from tests.qt_analysis_helpers import analysis, sites


SOURCE = '''class Grand : public QObject { Q_OBJECT
signals: void changed(int value);
public slots: void accept(int value) {}
};
class Middle : public Grand { Q_OBJECT };
class Child : public Middle { Q_OBJECT
public: void run() { emit changed(1); }
};
void wire(Child *sender, Child *receiver) {
 QObject::connect(sender, &Child::changed, receiver, &Child::accept);
 QObject::connect(sender, SIGNAL(changed(int)), receiver, SLOT(accept(int)));
 QObject::disconnect(sender, &Child::changed, receiver, &Child::accept);
}
'''


def test_req_qml016_ac01_grandparent_endpoints_use_declaring_members(tmp_path):
    """A three-level class has one ancestor signal and receiver declaration."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    emission = sites(result, "emission")[0]
    signal = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "changed")
    receiver = next(node for node in sites(result, "member") if qt_metadata(node)["raw_name"] == "accept")
    assert qt_metadata(emission)["status"] == "resolved"
    assert qt_metadata(emission)["target_id"] == signal["id"]
    for event in sites(result, "connect") + sites(result, "disconnect"):
        assert qt_metadata(event)["status"] == "resolved"
        assert qt_metadata(event)["signal_target_id"] == signal["id"]
        assert qt_metadata(event)["receiver_target_id"] == receiver["id"]


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml016_ac04_ancestor_edges_reach_reload_query_and_affected(tmp_path, directed):
    """Exact source bytes and typed mechanisms survive actual durable consumers."""
    source = ("\ufeff// café 雪\n" + SOURCE).replace("\n", "\r\n")
    result = analysis(tmp_path, {"events.cpp": source})
    index = QtEventIndex(result["nodes"])
    resolved = index.member({"form": "member_pointer", "class_name": "Child", "member_name": "changed"},
                            "Child", role="signal")
    assert resolved.status == "resolved"
    signal = next(node for node in sites(result, "member") if node["id"] == resolved.target_id)
    raw = (tmp_path / "events.cpp").read_bytes()
    span = qt_metadata(signal)["span"]
    assert raw[span["start_byte"]:span["end_byte"]] == b"void changed(int value);"
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    reloaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    for node in sites(result, "class"):
        assert qt_metadata(reloaded.nodes[node["id"]]) == qt_metadata(node)
    accepted = QtEventIndex([{"id": identity, **data} for identity, data in reloaded.nodes(data=True)])
    assert accepted.member({"form": "member_pointer", "class_name": "Child", "member_name": "changed"},
                           "Child", role="signal").target_id == resolved.target_id
    native_sites = sites(result, "emission") + sites(result, "connect") + sites(result, "disconnect")
    for node in native_sites:
        assert reloaded.nodes[node["id"]]["metadata"] == graph.nodes[node["id"]]["metadata"]
        assert not any(data.get("relation") == "calls" for _, _, data in reloaded.edges(node["id"], data=True))
    assert reloaded.has_edge(native_sites[0]["id"], signal["id"])
    hits = {hit.node_id for hit in affected_nodes(reloaded, signal["id"], depth=3)}
    assert all(node["id"] in hits for node in native_sites)
    assert qt_metadata(native_sites[0])["owner_id"] in hits
    assert "Qt emission: changed" in _query_graph_text(reloaded, "Child changed", token_budget=4000)


@pytest.mark.parametrize("control", ["own_ordinary", "middle_ordinary", "own_wrong_signature", "private"])
def test_req_qml016_ac01_shadowing_precedes_role_signature_and_visibility(tmp_path, control):
    """A first same-name declaration cannot fall through to a convenient signal."""
    source = SOURCE
    if control == "own_ordinary":
        source = source.replace("public: void run()", "public: void changed(int value) {} void run()")
    elif control == "middle_ordinary":
        source = source.replace("public Grand { Q_OBJECT", "public Grand { Q_OBJECT public: void changed(int value) {}")
    elif control == "own_wrong_signature":
        source = source.replace("public: void run()", "signals: void changed(double value); public: void run()")
    else:
        source = source.replace("signals: void changed", "private: Q_SIGNAL void changed")
    result = analysis(tmp_path, {"events.cpp": source})
    events = sites(result, "connect")
    if control in {"own_ordinary", "middle_ordinary"}:
        assert all(qt_metadata(node)["signal_status"] != "resolved" for node in events)
    elif control == "own_wrong_signature":
        assert qt_metadata(events[0])["signal_status"] == "resolved"
        target = next(node for node in result["nodes"] if node["id"] == qt_metadata(events[0])["signal_target_id"])
        assert qt_metadata(target)["class_name"] == "Child"
        assert qt_metadata(events[1])["signal_status"] == "unavailable"
    else:
        assert qt_metadata(events[0])["signal_status"] == "unavailable"
        assert qt_metadata(events[1])["status"] == "resolved"


@pytest.mark.parametrize("conflict", [False, True])
def test_req_qml016_ac01_diamond_deduplicates_declarations_and_rejects_conflicts(tmp_path, conflict):
    """Repeated canonical paths are one fact; distinct branch declarations compete."""
    extra = "signals: void changed(int value);" if conflict else ""
    source = SOURCE.replace("class Middle : public Grand { Q_OBJECT };", f'''class Left : public Grand {{ Q_OBJECT }};
class Right : public Grand {{ Q_OBJECT {extra} }};
class Middle : public Left, public Right {{ Q_OBJECT }};''')
    result = analysis(tmp_path, {"events.cpp": source})
    event = sites(result, "connect")[0]
    assert qt_metadata(event)["signal_status"] == ("ambiguous" if conflict else "resolved")
    if conflict:
        assert len(qt_metadata(event)["signal_candidates"]) == 2
    else:
        target = qt_metadata(sites(result, "emission")[0])["target_id"]
        assert qt_metadata(next(node for node in result["nodes"] if node["id"] == target))["class_name"] == "Grand"


@pytest.mark.parametrize("control", ["forward", "duplicate", "unknown_branch", "cycle", "conditional_alias"])
def test_req_qml016_ac01_unproven_ancestry_cannot_choose_an_endpoint(tmp_path, control):
    """Incomplete, ambiguous, cyclic or hidden base authority rejects static joins."""
    source = SOURCE
    if control == "forward":
        source = source.replace("class Middle : public Grand { Q_OBJECT };", "class Middle;")
    elif control == "duplicate":
        source += "\nclass Middle : public Grand { Q_OBJECT };\n"
    elif control == "unknown_branch":
        source = source.replace("public Middle {", "public Middle, public Missing {")
    elif control == "cycle":
        source = source.replace("public Grand {", "public Child {")
    else:
        source = source.replace("class Middle : public Grand", "#if SELECT\nusing Base = Grand;\n#endif\nclass Middle : public Base")
    result = analysis(tmp_path, {"events.cpp": source})
    assert all(qt_metadata(node).get("signal_status") != "resolved" for node in sites(result, "connect"))
    assert qt_metadata(sites(result, "emission")[0])["status"] != "resolved"


@pytest.mark.parametrize("depth,expected", [(31, "resolved"), (32, "unavailable")])
def test_req_qml016_ac01_ancestor_traversal_has_a_fail_closed_32_class_budget(tmp_path, depth, expected):
    """The last admitted class resolves; an additional class is never truncated to proof."""
    chain = "class Grand : public QObject { Q_OBJECT signals: void changed(int value); };\n"
    previous = "Grand"
    for number in range(depth):
        current = f"Level{number}"
        chain += f"class {current} : public {previous} {{ Q_OBJECT }};\n"
        previous = current
    chain += f"void wire({previous} *object) {{ QObject::connect(object, &{previous}::changed, object, [](int value){{}}); }}"
    result = analysis(tmp_path, {"events.cpp": chain})
    assert qt_metadata(sites(result, "connect")[0])["signal_status"] == expected
    if expected == "unavailable":
        assert qt_metadata(sites(result, "connect")[0])["signal_reason"] == "inheritance_cycle_or_limit"


def test_req_qml016_ac01_lexical_namespace_and_alias_bases_keep_exact_authority(tmp_path):
    """An unrelated global class cannot replace a namespaced aliased ancestor."""
    source = "namespace Public {\n" + SOURCE.replace("class Middle : public Grand", "using Alias = Grand;\nclass Middle : public Alias") + "}\n"
    source += "class Grand: public QObject {Q_OBJECT signals: void changed(double value);};"
    result = analysis(tmp_path, {"events.cpp": source})
    assert all(qt_metadata(event)["status"] == "resolved" for event in sites(result, "connect"))
    target = qt_metadata(sites(result, "emission")[0])["target_id"]
    assert qt_metadata(next(node for node in result["nodes"] if node["id"] == target))["class_name"] == "Public::Grand"


@pytest.mark.parametrize("selected", [False, True])
def test_req_qml016_ac01_ancestor_overloads_require_the_literal_selector(tmp_path, selected):
    """Recursive lookup preserves signature selection rather than choosing one overload."""
    source = SOURCE.replace("void changed(int value);", "void changed(int value); void changed(double value);")
    if selected:
        source = source.replace("&Child::changed", "qOverload<int>(&Child::changed)")
    result = analysis(tmp_path, {"events.cpp": source})
    event = sites(result, "connect")[0]
    assert qt_metadata(event)["signal_status"] == ("resolved" if selected else "ambiguous")
    assert qt_metadata(sites(result, "connect")[1])["status"] == "resolved"
    if selected:
        target = qt_metadata(event)["signal_target_id"]
        assert qt_metadata(next(node for node in result["nodes"] if node["id"] == target))["parameter_types"] == ["int"]


def test_req_qml016_ac01_competing_branch_role_cannot_disambiguate_cpp_name(tmp_path):
    """An ordinary branch member still competes with a differently owned signal."""
    source = SOURCE.replace("class Middle : public Grand { Q_OBJECT };", '''class Other : public QObject {
Q_OBJECT public: void changed(int value) {}
};
class Middle : public Grand, public Other { Q_OBJECT };''')
    result = analysis(tmp_path, {"events.cpp": source})
    assert all(qt_metadata(event)["signal_status"] == "ambiguous" for event in sites(result, "connect"))


@pytest.mark.parametrize("control", ["base_status", "base_count", "base_shape", "class_status", "member_status"])
def test_req_qml016_ac01_reloaded_incomplete_proof_is_rejected_without_mutation(tmp_path, control):
    """Corrupted accepted transport or status cannot synthesize an ancestral edge."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    nodes = copy.deepcopy(result["nodes"])
    if control == "member_status":
        node = next(node for node in nodes if qt_metadata(node).get("raw_name") == "changed")
        update_qt(node, status="unavailable")
    else:
        node = next(node for node in nodes if qt_metadata(node).get("kind") == "class"
                    and qt_metadata(node)["class_name"] == "Middle")
        update_qt(node, **{"base_status": {"canonical_base_status": "unavailable"},
                          "base_count": {"canonical_base_names": []},
                          "base_shape": {"bases": None},
                          "class_status": {"status": "ambiguous"}}[control])
    before = copy.deepcopy(nodes)
    answer = QtEventIndex(nodes).member({"form": "member_pointer", "class_name": "Child", "member_name": "changed"},
                                      "Child", role="signal")
    assert answer.status == "unavailable" and nodes == before


def test_req_qml016_ac01_explicit_ancestor_qualification_requires_receiver_compatibility(tmp_path):
    """Grandparent qualification accepts Child identity and rejects an unrelated object."""
    result = analysis(tmp_path, {"events.cpp": SOURCE + "class Other : public QObject { Q_OBJECT };"})
    index = QtEventIndex(result["nodes"])
    endpoint = {"form": "member_pointer", "class_name": "Grand", "member_name": "changed"}
    assert index.member(endpoint, "Child", role="signal").status == "resolved"
    answer = index.member(endpoint, "Other", role="signal")
    assert answer.status == "unavailable" and answer.reason == "object_member_type_mismatch"
