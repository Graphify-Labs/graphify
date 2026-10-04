"""REQ-QML-008/016 native alias changes through real updates and consumers.

Synthetic headers and source enter the production facade, CLI/watch writers and
directed JSON loader. Alias uncertainty cannot retain an old resolved endpoint.
"""
from __future__ import annotations

import pytest
import networkx as nx

from graphify.affected import affected_nodes, load_graph
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.qt_analysis_state import QT_STATE_FILE
from graphify.watch import _rebuild_code
from tests.test_qt_cpp_upgrade_invalidation import cli
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated


def project(root, alias="using Sender = Types::Original;"):
    """Accepted canonical classes remain in a header while alias sites change."""
    declaration = '''class NAME : public QObject { Q_OBJECT
 Q_PROPERTY(int value READ value NOTIFY changed)
 public: int value() { return 1; }
 signals: void changed(int value);
};
'''
    header = declaration.replace("NAME", "Sender")
    header += "namespace Types {\n" + declaration.replace("NAME", "Original")
    header += declaration.replace("NAME", "Other") + "}\n"
    header += "class Receiver : public QObject { Q_OBJECT public: void accept(int value) {} };\n"
    (root / "types.hpp").write_bytes(header.encode())
    (root / "keep.py").write_text("def helper(): return 7\n\ndef retained(): return helper()\n", encoding="utf-8")
    (root / "Main.qml").write_text(
        "import Demo 1.0\nThing { property int displayed: value; onChanged: (value) => {} }\n", encoding="utf-8")
    path = root / "events.cpp"
    source = '''#include "types.hpp"
namespace Bridge {
ALIAS
void wire(Sender *sender, Receiver *receiver) {
 QObject::connect(sender, &Sender::changed, receiver, &Receiver::accept);
 emit sender->changed(1);
}
void install() { qmlRegisterType<Sender>("Demo", 1, 0, "Thing"); }
}
'''.replace("ALIAS", alias)
    path.write_bytes(source.encode())
    return path


def facts(graph, kind):
    return [(identity, qt_metadata(data)) for identity, data in graph.nodes(data=True)
            if qt_metadata(data).get("kind") == kind]


def member(graph, class_name, name):
    matches = [(identity, md) for identity, md in facts(graph, "member")
               if md.get("class_name") == class_name and md.get("raw_name") == name]
    assert len(matches) == 1
    return matches[0]


def link(graph, source, target, context):
    matches = [data for _, candidate, data in graph.out_edges(source, data=True)
               if candidate == target and data.get("context") == context]
    assert len(matches) == 1
    return matches[0]


def assert_endpoints(root, expected):
    """Qt role endpoints and QML canonical endpoints retain distinct identities."""
    graph = load_graph(root / "graphify-out/graph.json")
    assert isinstance(graph, (nx.DiGraph, nx.MultiDiGraph))
    assert graph.is_directed()
    signal_id, signal = member(graph, expected, "changed")
    properties = [(identity, md) for identity, md in facts(graph, "property")
                  if md.get("class_name") == expected and md.get("raw_name") == "value"]
    assert len(properties) == 1
    property_id, prop = properties[0]
    assert prop["read"] == "value" and signal_id != property_id
    canonical_signal = signal["generic_target_id"]
    connection_id, connection = facts(graph, "connect")[0]
    emission_id, emission = facts(graph, "emission")[0]
    registration_id, registration = facts(graph, "registration")[0]
    assert connection["status"] == emission["status"] == "resolved"
    assert connection["signal_target_id"] == emission["target_id"] == signal_id
    assert registration["class_id"] == signal["class_id"]
    assert graph.nodes[canonical_signal]["source_file"] == "types.hpp"
    signal_roles = [identity for identity, md in facts(graph, "event_endpoint")
                    if md.get("owner_id") == connection_id and md.get("role") == "signal"]
    assert len(signal_roles) == 1
    role_id = signal_roles[0]
    link(graph, role_id, signal_id, "qt_connect_signal")
    link(graph, emission_id, signal_id, "qt_signal_emit")
    assert not graph.has_edge(signal_id, role_id) and not graph.has_edge(signal_id, emission_id)
    handlers = [(identity, qml_metadata(data)) for identity, data in graph.nodes(data=True)
                if qml_metadata(data).get("kind") == "handler"]
    assert len(handlers) == 1
    handler_id, handler = handlers[0]
    assert handler["resolved_target_id"] == canonical_signal
    link(graph, handler_id, canonical_signal, "qml_signal_subscription")
    assert not graph.has_edge(canonical_signal, handler_id)
    reads = [(source, target, data) for source, target, data in graph.edges(data=True)
             if data.get("context") == "qml_binding_read" and qt_metadata(data).get("native_endpoint")]
    assert len(reads) == 1
    proof = qt_metadata(reads[0][2])["native_endpoint"]
    assert proof["class_id"] == signal["class_id"]
    assert reads[0][1] != signal_id and reads[0][1] != canonical_signal
    impacted = {hit.node_id for hit in affected_nodes(graph, signal_id, depth=2)}
    assert {role_id, connection_id, emission_id}.issubset(impacted)
    assert handler_id in {hit.node_id for hit in affected_nodes(graph, canonical_signal, depth=2)}
    for identity in (connection_id, emission_id, registration_id):
        assert not any(data.get("relation") == "calls" for _, _, data in graph.out_edges(identity, data=True))
    return graph, (connection_id, emission_id, registration_id, handler_id)


def setup(root, monkeypatch):
    monkeypatch.chdir(root)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    monkeypatch.setenv("GRAPHIFY_QML_IMPORT_ROOTS", '["."]')


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("style", ["using", "typedef"])
def test_alias_type_edit_and_removal_refreshes_native_qml_cold_warm_consumers(
    tmp_path, monkeypatch, operation, style
):
    """Changing or removing a namespace alias must replace every affected endpoint."""
    alias = ("using Sender = Types::TARGET;" if style == "using" else "typedef Types::TARGET Sender;")
    source = project(tmp_path, alias.replace("TARGET", "Original"))
    setup(tmp_path, monkeypatch)
    cache = tmp_path / ".cold-cache"
    cold, warm = clean(tmp_path, cache), clean(tmp_path, cache)
    assert normalized(cold) == normalized(warm)
    initial = run(tmp_path, monkeypatch, operation)
    assert normalized(initial) == normalized(cold)
    directed, sites = assert_endpoints(tmp_path, "Types::Original")
    untouched = unrelated(directed)
    source.write_bytes(source.read_bytes().replace(b"Types::Original", b"Types::Other"))
    edited = run(tmp_path, monkeypatch, operation, [source])
    changed, _ = assert_endpoints(tmp_path, "Types::Other")
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edit-cache"))
    assert normalized(edited) == normalized(clean(tmp_path, tmp_path / ".edit-cache"))
    assert unrelated(changed) == untouched
    # Removal makes the unqualified spelling denote the actual global Sender;
    # old Types::Other relationships must not survive in persisted consumers.
    source.write_bytes(source.read_bytes().replace(alias.replace("TARGET", "Other").encode(), b""))
    removed = run(tmp_path, monkeypatch, operation, [source])
    restored, _ = assert_endpoints(tmp_path, "Sender")
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / ".removed-cache"))
    assert unrelated(restored) == untouched
    assert all(identity in directed for identity in sites)
    before = (tmp_path / "graphify-out/graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(removed)
    assert (tmp_path / "graphify-out/graph.json").read_bytes() == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_unprovable_alias_replaces_old_edges_without_global_name_fallback(tmp_path, monkeypatch, operation):
    """A valid but dynamic alias is coverage uncertainty, not stale success."""
    source = project(tmp_path)
    setup(tmp_path, monkeypatch)
    run(tmp_path, monkeypatch, operation)
    assert_endpoints(tmp_path, "Types::Original")
    source.write_bytes(source.read_bytes().replace(b"using Sender = Types::Original;",
                                                  b"using Sender = decltype(factory());"))
    updated = run(tmp_path, monkeypatch, operation, [source])
    directed = load_graph(tmp_path / "graphify-out/graph.json")
    assert facts(directed, "connect")[0][1]["signal_status"] != "resolved"
    assert facts(directed, "emission")[0][1]["status"] != "resolved"
    assert not facts(directed, "registration")[0][1].get("class_id")
    assert not [data for _, _, data in directed.edges(data=True)
                if data.get("context") in {"qt_connect_signal", "qt_signal_emit", "qml_signal_subscription"}]
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".uncertain-cache"))


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_bad_native_alias_input_retains_outputs_then_recovers_and_repeats(tmp_path, monkeypatch, operation):
    """The real fail-closed writer preserves graph, manifest, marker and analysis stamp."""
    source = project(tmp_path)
    setup(tmp_path, monkeypatch)
    initial = run(tmp_path, monkeypatch, operation)
    assert_endpoints(tmp_path, "Types::Original")
    original = source.read_bytes()
    out = tmp_path / "graphify-out"
    products = [out / name for name in ("graph.json", "manifest.json", ".graphify_root", QT_STATE_FILE)]
    before = {path: path.read_bytes() for path in products}
    source.write_bytes(original.replace(b"using Sender = Types::Original;", b"using Sender = ;"))
    if operation == "manual":
        with pytest.raises(SystemExit) as rejected:
            cli(tmp_path, monkeypatch, "update", force=True)
        assert rejected.value.code not in (None, 0)
    else:
        assert not _rebuild_code(tmp_path, changed_paths=[source], no_cluster=True, force=True)
    assert before == {path: path.read_bytes() for path in products}
    source.write_bytes(original)
    repaired = run(tmp_path, monkeypatch, operation, [source])
    assert_endpoints(tmp_path, "Types::Original")
    assert normalized(repaired) == normalized(initial)
    # Recovery uses the existing update envelope (without first-scan inventory),
    # but every persisted source node/edge above must match the accepted graph.
    repaired_bytes = (out / "graph.json").read_bytes()
    assert normalized(run(tmp_path, monkeypatch, operation, [source])) == normalized(initial)
    assert repaired_bytes == (out / "graph.json").read_bytes()


@pytest.mark.parametrize("alias", ["using Sender = Types::Other;", "typedef Types::Other Sender;",
                                  "typedef Types::Other First, Sender;",
                                  "#if ENABLED\nusing Sender = Types::Other;\n#endif"])
@pytest.mark.parametrize("header_name", ["types.hpp", "alias.hpp"])
def test_accepted_header_alias_cannot_resolve_outer_global_native_or_qml_endpoint(
    tmp_path, monkeypatch, alias, header_name
):
    """Includes admit alias shadow evidence, even when a header has no Qt token.

    Cross-unit aliases are conservatively unavailable. Their declaration must
    still block wrong global registration, connection and emission endpoints.
    """
    source = project(tmp_path, alias="")
    header = tmp_path / header_name
    existing = header.read_bytes() if header.exists() else b""
    header.write_bytes(existing + ("namespace Bridge {\n" + alias + "\n}\n").encode())
    if header_name != "types.hpp":
        source.write_bytes(b'#include "alias.hpp"\n' + source.read_bytes())
    setup(tmp_path, monkeypatch)
    run(tmp_path, monkeypatch, "watch")
    graph = load_graph(tmp_path / "graphify-out/graph.json")
    wrong, md = member(graph, "Sender", "changed")
    assert facts(graph, "registration")[0][1].get("class_id") != md["class_id"]
    assert facts(graph, "connect")[0][1].get("signal_target_id") != wrong
    assert facts(graph, "emission")[0][1].get("target_id") != wrong
    assert not [data for _, _, data in graph.edges(data=True)
                if data.get("context") in {"qt_connect_signal", "qt_signal_emit", "qml_signal_subscription"}]


def test_transitive_header_alias_owns_shadow_but_not_prior_source_use(tmp_path, monkeypatch):
    """Accepted include chains preserve order; projection never expands the corpus."""
    source = project(tmp_path, alias="")
    (tmp_path / "alias.hpp").write_text("namespace Bridge { using Sender = Types::Other; }\n", encoding="utf-8")
    (tmp_path / "wrapper.hpp").write_text('#include "alias.hpp"\n', encoding="utf-8")
    original = source.read_bytes()
    source.write_bytes(original + b'#include "wrapper.hpp"\n')
    setup(tmp_path, monkeypatch)
    run(tmp_path, monkeypatch, "watch")
    assert_endpoints(tmp_path, "Sender")
    source.write_bytes(b'#include "wrapper.hpp"\n' + original)
    updated = run(tmp_path, monkeypatch, "watch", [source])
    assert facts(updated, "registration")[0][1]["reason"] == "native_type_included_alias_unavailable"
    assert not facts(updated, "emission")[0][1].get("target_id")
    assert normalized(updated) == normalized(clean(tmp_path, tmp_path / ".include-cache"))
    header = tmp_path / "alias.hpp"
    header.write_text("// The alias has been removed.\n", encoding="utf-8")
    refreshed = run(tmp_path, monkeypatch, "watch", [header])
    assert_endpoints(tmp_path, "Sender")
    assert normalized(refreshed) == normalized(clean(tmp_path, tmp_path / ".header-edit-cache"))


@pytest.mark.parametrize("field,value", [("_origin", "foreign"), ("source_location", "L999")])
def test_included_alias_fact_corruption_rejects_provenance_instead_of_resolving_outer_type(
    tmp_path, monkeypatch, field, value
):
    """A real published alias occurrence is immutable input; corrupt authority fails closed."""
    from copy import deepcopy
    from graphify.extractors.qt_cpp_type_aliases import IncludedAliasShadows
    from graphify.extractors.qt_cpp_syntax import read_cpp
    source = project(tmp_path, alias="")
    with (tmp_path / "types.hpp").open("ab") as header:
        header.write(b"namespace Bridge { using Sender = Types::Other; }\n")
    setup(tmp_path, monkeypatch)
    graph = run(tmp_path, monkeypatch, "watch")
    aliases = [deepcopy(data) for _, data in graph.nodes(data=True) if qt_metadata(data).get("kind") == "type_alias"]
    assert len(aliases) == 1
    aliases[0][field] = value
    with pytest.raises(ValueError, match="QT_METADATA"):
        IncludedAliasShadows(read_cpp(source, tmp_path), aliases)


def test_fresh_alias_header_uses_borrowed_qt_context_without_mutating_it(tmp_path, monkeypatch):
    """The facade publishes fresh alias facts even when only the header changes."""
    from copy import deepcopy
    from graphify.extract import extract
    project(tmp_path)
    setup(tmp_path, monkeypatch)
    graph = run(tmp_path, monkeypatch, "watch")
    context = [dict(data, id=identity) for identity, data in graph.nodes(data=True)
               if data.get("source_file") == "types.hpp"]
    before = deepcopy(context)
    header = tmp_path / "alias.hpp"
    header.write_text("namespace Bridge { using Sender = Types::Other; }\n", encoding="utf-8")
    result = extract([header], root=tmp_path, parallel=False, refresh_native=True,
                     resolution_context_nodes=context)
    assert not result["qml_failures"] and not result.get("qt_failures")
    assert len([node for node in result["nodes"] if qt_metadata(node).get("kind") == "type_alias"]) == 1
    assert context == before
