"""INC119: producer-owned C++ bodies/prototypes cannot become semantic ghosts."""
from __future__ import annotations

import base64
from copy import deepcopy

import pytest

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.graph_direction import logical_endpoints
from tests.cpp_direct_provenance_helpers import (
    assert_function_targets, assert_source, calls, functions, produce, prototypes, public_roundtrip, source,
)


@pytest.mark.parametrize('mode', ['direct', 'facade'])
@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('shape', ['ordinary', 'late_anonymous', 'late_named'])
@pytest.mark.parametrize('newline', ['lf', 'bom_crlf'])
def test_req_qml022_ac06_direct_source_body_and_foreign_prototype_survive_consumers(tmp_path, mode, directed, shape, newline):
    """A later different-scope prototype must not replace the preceding called source body."""
    raw = source(shape, newline)
    result = produce(tmp_path, raw, mode)
    assert_source(result, raw)
    edge, = calls(result)
    target, = functions(result)
    assert edge['target'] == target[0]['id'] and base64.b64decode(target[1]['namespace_b64']) == b''
    declarations = prototypes(result)
    assert len(declarations) == (0 if shape == 'ordinary' else 1)
    if declarations:
        assert declarations[0][1]['scope_status'] == ('anonymous' if shape == 'late_anonymous' else 'named')
    for graph in public_roundtrip(tmp_path, result, directed):
        assert_function_targets(graph, result)
        for node, fact in declarations:
            assert node['id'] in graph and graph.nodes[node['id']]['metadata']['cpp_prototype'] == fact
        assert not any(qt_metadata(data).get('native_endpoint') for _, _, data in graph.edges(data=True))
    assert (tmp_path / 'panel.cpp').read_bytes() == raw


@pytest.mark.parametrize('mode', ['direct', 'facade'])
@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('layout', ['separate_lines', 'same_line'])
def test_req_qml022_ac02_same_named_source_namespace_bodies_stay_distinct(tmp_path, mode, directed, layout):
    """Original namespace roles keep two same-label bodies distinct and calls bound to Right."""
    raw = source('separate_named')
    if layout == 'same_line':
        raw = raw.replace(b'\r\nnamespace Right', b' namespace Right')
    result = produce(tmp_path, raw, mode)
    assert_source(result, raw)
    bodies = functions(result)
    assert {base64.b64decode(fact['namespace_b64']) for _, fact in bodies} == {b'Left', b'Right'}
    assert len({node['source_location'] for node, _ in bodies}) == (1 if layout == 'same_line' else 2)
    edge, = calls(result)
    assert base64.b64decode(next(fact['namespace_b64'] for node, fact in bodies if node['id'] == edge['target'])) == b'Right'
    for graph in public_roundtrip(tmp_path, result, directed):
        assert_function_targets(graph, result)
        for node, fact in bodies:
            assert node['id'] in graph and graph.nodes[node['id']]['metadata']['cpp_function'] == fact


@pytest.mark.parametrize('mode', ['direct', 'facade'])
@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('shape', ['canonical_global', 'canonical_named'])
def test_req_qml022_ac06_legitimate_declaration_body_keeps_the_actual_definition(tmp_path, mode, directed, shape):
    """A valid same-entity declaration/body may canonicalize while retaining called definition provenance."""
    raw = source(shape)
    result = produce(tmp_path, raw, mode)
    assert_source(result, raw)
    assert len(calls(result)) == len(functions(result)) == 1
    for graph in public_roundtrip(tmp_path, result, directed):
        assert_function_targets(graph, result)
        # Canonical projection need not expose an extra declaration node.
        assert any(data.get('metadata', {}).get('cpp_function', {}).get('role') == 'definition'
                   for _, data in graph.nodes(data=True))


@pytest.mark.parametrize('directed', [False, True])
@pytest.mark.parametrize('shape', ['ordinary', 'separate_named'])
def test_req_qml022_ac06_richer_semantic_record_cannot_erase_a_direct_definition(tmp_path, directed, shape):
    """Existing unique-ghost merging and ambiguous-AST deferral preserve actual source endpoints."""
    result = produce(tmp_path, source(shape), 'direct')
    semantic = {'id': 'semantic-helper', 'label': 'helper()', 'file_type': 'code', '_origin': 'semantic',
                'source_file': str(tmp_path / 'panel.cpp'), 'source_location': 'L999',
                'description': 'A richer semantic mention supplies no source declaration or scope.',
                'metadata': {'notes': {'tokens': ['unproved', 'description']}}, 'weight': 99}
    result['nodes'].append(deepcopy(semantic))
    for graph in public_roundtrip(tmp_path, result, directed):
        assert_function_targets(graph, result)
        assert ('semantic-helper' in graph) is (shape == 'separate_named')
        if 'semantic-helper' in graph:
            assert not graph.nodes['semantic-helper'].get('metadata', {}).get('cpp_function')
        assert not any(qt_metadata(data).get('native_endpoint') for _, _, data in graph.edges(data=True))


@pytest.mark.parametrize('mode', ['direct', 'facade'])
@pytest.mark.parametrize('shape', ['prototype_only', 'partial'])
def test_req_qml022_ac02_provenance_does_not_invent_a_missing_or_partial_definition(tmp_path, mode, shape):
    """A declaration supplies no body; a malformed trailing declaration cannot replace an earlier body."""
    raw = source(shape)
    result = produce(tmp_path, raw, mode)
    assert_source(result, raw)
    if shape == 'prototype_only':
        assert not functions(result) and not calls(result)
    else:
        # Partial input retains the existing generic call, not the stricter
        # source-owned free-call authority that requires a complete parse.
        assert len(functions(result)) == 1 and not calls(result)
        target = functions(result)[0][0]['id']
        generic, = [edge for edge in result['edges'] if edge.get('target') == target
                    and edge.get('relation') == 'calls' and edge.get('context') == 'call']
        assert not any(node.get('label') == 'incomplete()' for node, _ in prototypes(result))
    for graph in public_roundtrip(tmp_path, result, False):
        assert_function_targets(graph, result)
        if shape == 'partial':
            assert target in graph and graph.nodes[target]['metadata']['cpp_function'] == functions(result)[0][1]
            assert any(data.get('context') == 'call'
                       and logical_endpoints(left, right, data, directed=graph.is_directed()) == (generic['source'], target)
                       for left, right, data in graph.edges(data=True))
        assert not any(qt_metadata(data).get('native_endpoint') for _, _, data in graph.edges(data=True))
