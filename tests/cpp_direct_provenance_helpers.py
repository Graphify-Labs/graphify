"""Neutral source/consumer helpers for direct C++ declaration provenance."""
from __future__ import annotations

import base64
from copy import deepcopy
import json

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extract import extract, extract_cpp
from graphify.graph_direction import logical_endpoints
from graphify.paths import load_node_link_graph
from tests.cpp_same_unit_helpers import validate_span


BODY = 'struct Panel{void run();};\nvoid Panel::run(){helper();}\n'


def source(shape='late_anonymous', newline='bom_crlf'):
    cases = {
        'ordinary': 'void helper(){}\n' + BODY,
        'late_anonymous': 'void helper(){}\n' + BODY + 'namespace{void helper();}\n',
        'late_named': 'void helper(){}\n' + BODY + 'namespace Other{void helper();}\n',
        'separate_named': 'namespace Left{void helper(){}}\nnamespace Right{void helper(){}\n' + BODY + '}\n',
        'canonical_global': 'void helper();\nvoid helper(){}\n' + BODY,
        'canonical_named': 'namespace Public{void helper();}\nnamespace Public{void helper(){}\n' + BODY + '}\n',
        'prototype_only': 'void helper();\n' + BODY,
        'partial': 'void helper(){}\n' + BODY + 'namespace{void incomplete(\n',
    }
    raw = ('// π original source\n' + cases[shape]).encode()
    return b'\xef\xbb\xbf' + raw.replace(b'\n', b'\r\n') if newline == 'bom_crlf' else raw


def produce(root, raw, mode):
    """Each public owner reads the same bytes; facade cold/warm results must agree."""
    path = root / 'panel.cpp'
    path.write_bytes(raw)
    if mode == 'direct':
        return extract_cpp(path)
    result = extract([path], root=root, cache_root=root, parallel=False)
    assert result == extract([path], root=root, cache_root=root, parallel=False)
    assert not result.get('failed_sources') and not result.get('qml_failures')
    return result


def functions(result):
    return [(node, node['metadata']['cpp_function']) for node in result['nodes']
            if node.get('metadata', {}).get('cpp_function')
            and base64.b64decode(node['metadata']['cpp_function']['name_b64']) == b'helper']


def prototypes(result):
    return [(node, node['metadata']['cpp_prototype']) for node in result['nodes']
            if node.get('metadata', {}).get('cpp_prototype') and node.get('label') == 'helper()']


def calls(result):
    targets = {node['id'] for node, _ in functions(result)}
    return [edge for edge in result['edges'] if edge.get('relation') == 'calls'
            and edge.get('target') in targets and edge.get('context') == 'cpp_free_function']


def assert_source(result, raw):
    """Verify original source roles, byte witnesses and distinct raw declaration identities."""
    occurrences = [*functions(result), *prototypes(result)]
    assert len({node['id'] for node, _ in occurrences}) == len(occurrences)
    for node, fact in occurrences:
        fragment = validate_span(raw, fact)
        assert b'helper' in fragment and node['source_location'] == f"L{fact['span']['start_row'] + 1}"
        assert fact['role'] == ('definition' if 'cpp_function' in node['metadata'] else 'declaration')
        for scope in fact.get('namespace_proof', []):
            assert b'namespace' in validate_span(raw, scope)
        for scope in fact.get('anonymous_scope_proof', {}).get('scopes', []):
            assert b'namespace' in validate_span(raw, scope)


def public_roundtrip(root, result, directed):
    """Exercise assembly, actual atomic export, public path load and a second assembly."""
    graph = build_from_json(deepcopy(result), root=root, directed=directed)
    output = root / 'accepted.json'
    assert to_json(graph, {}, str(output), force=True)
    loaded = load_node_link_graph(output)
    rebuilt = build_from_json(json.loads(output.read_text(encoding='utf-8')), root=root, directed=directed)
    return graph, loaded, rebuilt


def assert_function_targets(graph, result):
    """Every real helper call still reaches its original definition and member caller."""
    raw_calls = calls(result)
    for edge in raw_calls:
        expected = next(node for node, _ in functions(result) if node['id'] == edge['target'])
        assert edge['target'] in graph and edge['source'] in graph
        assert graph.nodes[edge['target']]['metadata']['cpp_function'] == expected['metadata']['cpp_function']
        assert graph.nodes[edge['target']]['source_location'] == expected['source_location']
        assert any(data.get('relation') == 'calls' and data.get('context') == 'cpp_free_function'
                   and data.get('confidence') == 'EXTRACTED'
                   and logical_endpoints(left, right, data, directed=graph.is_directed()) == (edge['source'], edge['target'])
                   for left, right, data in graph.edges(data=True))
