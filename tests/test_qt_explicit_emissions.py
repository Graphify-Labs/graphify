"""REQ-QML-016-AC01/AC04 explicit Qt syntax persists without declared signals."""
import json

import pytest

from graphify.affected import affected_nodes
from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract
from graphify.extractors.qt_cpp_calls import calls
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_mapping import map_cpp
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites


SOURCE = '''class Backend : public QObject { Q_OBJECT
public: void run() { emit missing(1); missing(2); Q_EMIT missing(3); helper(); }
void helper() {}
};'''


def test_req_qml016_ac01_explicit_unknown_sites_do_not_admit_bare_calls(tmp_path):
    """Observed annotations are two source sites; the bare invocation stays generic."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    emissions = sites(result, "emission")
    assert len(emissions) == 2
    assert all(qt_metadata(node)["explicit_emit"] is True for node in emissions)
    assert all(qt_metadata(node)["status"] == "unavailable" and not qt_metadata(node)["target_id"] for node in emissions)
    original = (tmp_path / "events.cpp").read_bytes()
    assert [original[md["span"]["start_byte"]:md["span"]["end_byte"]]
            for node in emissions if (md := qt_metadata(node))] == [b"missing(1)", b"missing(3)"]
    ids = {node["id"] for node in emissions}
    assert not any(edge["source"] in ids and edge["relation"] == "calls" for edge in result["edges"])


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml016_ac01_long_comment_crlf_bom_and_unicode_keep_original_spans(tmp_path, marker):
    """Offset proof comes from accepted executable syntax and original disk bytes."""
    source = ("\ufeff// café 雪\nvoid run() { " + marker + " /* " + "reason " * 40
              + "*/\n object->missing(7); }\n").replace("\n", "\r\n")
    result = analysis(tmp_path, {"events.cpp": source})
    emissions = sites(result, "emission")
    assert len(emissions) == 1
    metadata = qt_metadata(emissions[0])
    assert metadata["explicit_emit"] and metadata["receiver_reference"] == "object"
    assert metadata["status"] == "unavailable" and not metadata["target_id"]
    assert (tmp_path / "events.cpp").read_bytes()[metadata["span"]["start_byte"]:metadata["span"]["end_byte"]] == b"object->missing(7)"


@pytest.mark.parametrize("body", [
    '// emit missing();\n/* Q_EMIT missing(); */\n',
    'const char *text = "emit missing()"; const char *raw = R"tag(Q_EMIT missing())tag";',
    'auto value = sizeof(emit missing());',
    'using Value = decltype(emit missing());',
    'auto value = noexcept(Q_EMIT missing());',
    'WRAP(emit missing());',
    '#define OBSERVATION emit missing()\n',
    'myemit(missing()); Q_EMIT_EXTRA(missing());',
])
def test_req_qml016_ac01_inert_macro_and_member_spellings_supply_no_explicit_role(tmp_path, body):
    """Quoted, macro-owned or unevaluated names cannot create unknown Qt events."""
    result = analysis(tmp_path, {"events.cpp": "class Backend : public QObject { Q_OBJECT public: void run() {\n" + body + "\n} };"})
    assert not sites(result, "emission")


def test_req_qml016_ac01_unsupported_macro_member_normalization_reports_rejection(tmp_path):
    """An existing Qt parse-view limitation remains explicit, without invented events."""
    path = tmp_path / "events.cpp"
    path.write_text("class Backend : public QObject { Q_OBJECT public: void run() { object.emit(missing()); object.Q_EMIT(missing()); } };", encoding="utf-8")
    result = extract([path], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert any(item["code"] == "QT_CPP_SYNTAX" for item in result["qml_failures"])
    assert not sites(result, "emission")


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml016_ac01_local_macro_override_cannot_inherit_qt_annotation_role(tmp_path, marker):
    """A preceding define/undef blocks SDK annotation proof without preprocessing."""
    source = f"#define {marker} ordinary\nclass Backend : public QObject {{ Q_OBJECT public: void run() {{ {marker} missing(1); }} }};"
    result = analysis(tmp_path, {"events.cpp": source})
    assert not sites(result, "emission")


def test_req_qml016_ac01_macro_override_order_preserves_prior_explicit_observation(tmp_path):
    """Later source shadowing cannot revoke an earlier lexical annotation occurrence."""
    source = '''class Backend : public QObject { Q_OBJECT public: void run() {
 emit missing(1);
#undef emit
 emit missing(2);
} };'''
    result = analysis(tmp_path, {"events.cpp": source})
    emitted = sites(result, "emission")
    assert len(emitted) == 1
    metadata = qt_metadata(emitted[0])
    span = metadata["span"]
    assert (tmp_path / "events.cpp").read_bytes()[span["start_byte"]:span["end_byte"]] == b"missing(1)"


def test_req_qml016_ac01_conditional_occurrence_keeps_uncertainty_without_delivery(tmp_path):
    """Accepted conditional source is observed once without claiming execution."""
    source = SOURCE.replace("emit missing(1);", "if (ready) emit missing(1);")
    result = analysis(tmp_path, {"events.cpp": source})
    emitted = sites(result, "emission")
    assert len(emitted) == 2
    assert [qt_metadata(node)["conditional"] for node in emitted] == [True, False]
    assert all(qt_metadata(node)["status"] == "unavailable" for node in emitted)


def test_req_qml016_ac01_declared_bare_inventory_still_observes_separate_occurrences(tmp_path):
    """The opt-in preserves known bare signals and cannot duplicate explicit sites."""
    result = analysis(tmp_path, {"events.cpp": SOURCE.replace("public: void run()", "signals: void missing(int value); public: void run()")})
    emitted = sites(result, "emission")
    assert len(emitted) == 3 and len({node["id"] for node in emitted}) == 3
    assert sum(qt_metadata(node)["explicit_emit"] for node in emitted) == 2
    assert all(qt_metadata(node)["status"] == "resolved" for node in emitted)


def test_req_qml016_ac01_default_call_collector_retains_existing_inventory_contract(tmp_path):
    """The shared syntax scanner opts in explicitly; default callers see no extra names."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    unit = read_cpp(tmp_path / "events.cpp", tmp_path)
    mapping = map_cpp(unit, result["nodes"], result["edges"], root=tmp_path)
    assert not list(calls(unit, mapping, {"unrelated"}))
    admitted = list(calls(unit, mapping, {"unrelated"}, include_explicit=True))
    assert len(admitted) == 2 and all(item["explicit_emit"] for item in admitted)


@pytest.mark.parametrize("directed", [False, True])
def test_req_qml016_ac04_unknown_emissions_reload_as_owned_unresolved_sites(tmp_path, directed):
    """New facts preserve callable containment, independent of an absent endpoint."""
    result = analysis(tmp_path, {"events.cpp": SOURCE})
    graph = build_from_json(result, root=tmp_path, directed=directed)
    path = tmp_path / "graph.json"
    assert to_json(graph, {}, str(path))
    reloaded = load_node_link_graph(json.loads(path.read_text(encoding="utf-8")))
    emissions = sites(result, "emission")
    assert len(emissions) == 2
    for node in emissions:
        metadata = qt_metadata(node)
        assert qt_metadata(reloaded.nodes[node["id"]]) == metadata
        assert metadata["owner_id"] in reloaded and reloaded.has_edge(metadata["owner_id"], node["id"])
        assert metadata["owner_id"] in {hit.node_id for hit in affected_nodes(reloaded, node["id"], relations=["contains"], depth=1)}
        assert not any(data.get("relation") == "calls" for _, _, data in reloaded.edges(node["id"], data=True))


@pytest.mark.parametrize("name,marker", [("connect", "emit"), ("disconnect", "Q_EMIT")])
@pytest.mark.parametrize("declared", [False, True])
def test_req_qml016_ac01_explicit_annotation_owns_emission_mechanism(tmp_path, name, marker, declared):
    """An explicit annotation takes precedence over a same-spelled Qt connection API."""
    declaration = f"signals: void {name}();" if declared else ""
    source = f"class Backend : public QObject {{ Q_OBJECT {declaration} public: void run() {{ {marker} {name}(); }} }};"
    result = analysis(tmp_path, {"events.cpp": source})
    selected = sites(result, "emission")
    assert len(selected) == 1, [(qt_metadata(n).get("kind"), qt_metadata(n).get("raw_name")) for n in result["nodes"] if qt_metadata(n)]
    md = qt_metadata(selected[0])
    assert md["explicit_emit"] is True
    assert md["status"] == ("resolved" if declared else "unavailable")


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml016_ac01_override_cannot_recover_annotation_by_prefix(tmp_path, marker):
    """Known bare signal admission cannot reauthorize a rejected annotation token."""
    source = f"#define {marker} ordinary\nclass Backend : public QObject {{ Q_OBJECT signals: void ready(); public: void run() {{ {marker} ready(); }} }};"
    result = analysis(tmp_path, {"events.cpp": source})
    selected = sites(result, "emission")
    assert len(selected) == 1
    assert qt_metadata(selected[0])["explicit_emit"] is False


@pytest.mark.parametrize("marker", ["emit", "Q_EMIT"])
def test_req_qml016_ac01_computed_receiver_keeps_full_explicit_source_site(tmp_path, marker):
    """An outer annotated call cannot reclassify its nested factory as a bare signal."""
    source = f"class Backend : public QObject {{ Q_OBJECT public: void run() {{ {marker} factory()->missing(1); }} }};"
    result = analysis(tmp_path, {"events.cpp": source})
    selected = sites(result, "emission")
    assert len(selected) == 1
    md = qt_metadata(selected[0])
    assert md["raw_name"] == "missing" and md["explicit_emit"] is True
    assert md["status"] == "unavailable" and not md["target_id"]
    assert (tmp_path / "events.cpp").read_bytes()[md["span"]["start_byte"]:md["span"]["end_byte"]] == b"factory()->missing(1)"
