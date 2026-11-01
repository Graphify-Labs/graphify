"""INC119: producer provenance survives real refresh, failed writes and source removal."""
from __future__ import annotations

from copy import deepcopy
import errno

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.paths import load_node_link_graph
from tests.cpp_direct_provenance_helpers import assert_function_targets, calls, functions, produce, source
from tests.qt_publication_faults import publication_fault
from tests.test_cpp_allocated_member_updates import cold_reference, full_fields
from tests.test_cpp_same_unit_updates import rejected
from tests.test_qt_final_incremental_parity import run, unrelated
from tests.test_qt_semantic_correction_updates import products


def helpers(graph, kind):
    return [(identity, node) for identity, node in graph.nodes(data=True)
            if node.get('label') == 'helper()' and node.get('source_file') == 'panel.cpp'
            and node.get('metadata', {}).get(kind)]


def assert_profile(graph, *, definition=True, prototype=True):
    """Read original source roles and the actual persisted logical call, never a storage key."""
    definitions, declarations = helpers(graph, 'cpp_function'), helpers(graph, 'cpp_prototype')
    assert len(definitions) == int(definition) and len(declarations) == int(prototype)
    targets = {identity for identity, _ in definitions}
    edges = [(left, right, data) for left, right, data in graph.edges(data=True)
             if data.get('context') == 'cpp_free_function' and data.get('relation') == 'calls']
    assert len(edges) == int(definition)
    if definition:
        left, right, data = edges[0]
        if graph.is_directed() or '_tgt' in data:
            assert data.get('_tgt', right) in targets
        else:
            # Raw legacy undirected calls retain endpoints without a new
            # logical-direction promise from this provenance correction.
            assert {left, right} & targets
        assert definitions[0][1]['metadata']['cpp_function']['role'] == 'definition'
    for _, node in declarations:
        assert node['metadata']['cpp_prototype']['role'] == 'declaration'


@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('force', [False, True])
def test_req_qml014_ac04_direct_producer_publication_failure_retains_body_and_recovers(tmp_path, monkeypatch, directed, force):
    """Actual replacement EIO cannot publish source removal early; repaired source restores the same body."""
    original = source()
    initial = produce(tmp_path, original, 'direct')
    graph = build_from_json(initial, root=tmp_path, directed=directed)
    output = tmp_path / 'accepted.json'
    assert to_json(graph, {}, str(output), force=True)
    assert_function_targets(load_node_link_graph(output), initial)
    accepted = output.read_bytes()
    old_target = calls(initial)[0]['target']
    # A real replacement declaration keeps the graph size stable so both
    # force profiles reach atomic replacement rather than the valid shrink gate.
    removed_raw = original.replace(b'void helper(){}', b'void replacement(){}')
    removed = produce(tmp_path, removed_raw, 'direct')
    assert not functions(removed) and not calls(removed)
    candidate = build_from_json(removed, root=tmp_path, directed=directed)
    source_facts = deepcopy((list(candidate.nodes(data=True)), list(candidate.edges(data=True))))
    with publication_fault(output, 'replace', monkeypatch) as fault:
        for _ in range(2):
            with pytest.raises(OSError) as failure:
                to_json(candidate, {}, str(output), force=force)
            assert failure.value.errno == errno.EIO and output.read_bytes() == accepted
            assert (list(candidate.nodes(data=True)), list(candidate.edges(data=True))) == source_facts
        assert fault.hits >= 2
    assert to_json(candidate, {}, str(output), force=force)
    assert old_target not in load_node_link_graph(output)
    repaired = produce(tmp_path, original, 'direct')
    recovered = build_from_json(repaired, root=tmp_path, directed=directed)
    assert calls(repaired)[0]['target'] == old_target
    assert to_json(recovered, {}, str(output), force=True)
    assert_function_targets(load_node_link_graph(output), repaired)
    final = output.read_bytes()
    assert to_json(recovered, {}, str(output), force=True) and output.read_bytes() == final
    assert (tmp_path / 'panel.cpp').read_bytes() == original


@pytest.mark.parametrize('operation', ['manual', 'watch'])
def test_req_qml022_ac06_provenance_refresh_source_removal_failed_write_and_repeat(tmp_path, monkeypatch, operation):
    """Real shared updates preserve source roles across QML/build edits and failed C++ removal."""
    cpp, qml, cmake = tmp_path / 'panel.cpp', tmp_path / 'Main.qml', tmp_path / 'CMakeLists.txt'
    original = source()
    cpp.write_bytes(original)
    qml.write_bytes(b'import QtQuick\nItem {property int revision:1}\n')
    cmake.write_bytes(b'qt_add_qml_module(app URI Public.Provenance VERSION 1.0 QML_FILES Main.qml SOURCES panel.cpp)\n')
    (tmp_path / 'keep.py').write_bytes(b'def helper():return 1\n\ndef retained():return helper()\n')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GRAPHIFY_NO_TIPS', '1')
    initial = run(tmp_path, monkeypatch, operation)
    assert_profile(initial)
    old_target = helpers(initial, 'cpp_function')[0][0]
    for changed, old, new in ((qml, b'revision:1', b'revision:2'), (cmake, b'VERSION 1.0', b'VERSION 1.1')):
        changed.write_bytes(changed.read_bytes().replace(old, new))
        current = run(tmp_path, monkeypatch, operation, [changed])
        assert_profile(current)
        assert cpp.read_bytes() == original
        assert full_fields(current) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    accepted = products(tmp_path)
    cpp.write_bytes(original.replace(b'void helper(){}', b''))
    with publication_fault(tmp_path / 'graphify-out/graph.json', 'replace', monkeypatch) as fault:
        for _ in range(2):
            rejected(tmp_path, monkeypatch, operation, cpp)
            assert products(tmp_path) == accepted
        assert fault.hits >= 2
    removed = run(tmp_path, monkeypatch, operation, [cpp])
    assert_profile(removed, definition=False)
    assert old_target not in removed
    cpp.write_bytes(original)
    repaired = run(tmp_path, monkeypatch, operation, [cpp])
    assert_profile(repaired)
    assert helpers(repaired, 'cpp_function')[0][0] == old_target
    assert unrelated(initial) == unrelated(repaired)
    assert full_fields(repaired) == full_fields(cold_reference(tmp_path, monkeypatch, operation))
    stable = products(tmp_path)
    run(tmp_path, monkeypatch, operation, [])
    assert products(tmp_path) == stable
