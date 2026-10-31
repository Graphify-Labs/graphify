"""Loader SDK authority cannot come from an incomplete source declaration."""
from __future__ import annotations

import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_loader_updates import assert_load, facts, fixture, products, source


@pytest.mark.parametrize("sdk_name,load,root", [
    ("QQmlApplicationEngine", 'QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ("QQmlApplicationEngine", 'QQmlApplicationEngine engine; engine.load(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ("QQmlComponent", 'QQmlEngine engine; QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ("QQmlComponent", 'QQmlEngine engine; QQmlComponent component(&engine); component.loadUrl(QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ("QQmlEngine", 'QQmlEngine engine; QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ("QQuickView", 'QQuickView view; view.setSource(QUrl("qrc:/ui/Main.qml"));', 'view.rootObject()'),
    ("QUrl", 'QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ("QString", 'QQmlApplicationEngine engine(QString("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
])
@pytest.mark.parametrize("shadow", [False, True])
def test_req_qml017_ac01_incomplete_sdk_declaration_cannot_authorize_loader(tmp_path, sdk_name, load, root, shadow):
    """Paired external SDK controls and unknown source classes reach JSON reload."""
    source = (f'class {sdk_name};\n' if shadow else '') + 'void use() { ' + load + f' auto root={root}; root->property("value"); }}'
    result = analysis(tmp_path, {
        'access.cpp': source,
        'Main.qml': 'import QtQml\nQtObject { property int value: 1 }',
        'ui.qrc': '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
    })
    access = sites(result, 'qml_access', 'property')[0]
    graph = build_from_json(result)
    output = tmp_path / 'graph.json'
    to_json(graph, {}, output)
    restored = load_node_link_graph(json.loads(output.read_text(encoding='utf-8')))
    target = qt_metadata(access).get('target_id')
    if shadow:
        assert not target
        assert not [data for _, _, data in restored.edges(data=True)
                    if data.get('_src') == access['id'] and data.get('context') == 'qt_cpp_qml_property_read']
    else:
        assert qt_metadata(access)['status'] == 'resolved' and target in restored


@pytest.mark.parametrize('prefix', ['if (ready) ', 'engine = factory(); '])
def test_req_qml017_ac04_uncertain_sdk_use_retains_observed_loader(tmp_path, prefix):
    """Static SDK type authority does not establish conditional/reassigned identity."""
    result = analysis(tmp_path, {
        'access.cpp': 'void use() { QQmlApplicationEngine engine; ' + prefix
                      + 'engine.load(QUrl("qrc:/ui/Main.qml")); }',
        'Main.qml': 'import QtQml\nQtObject {}',
        'ui.qrc': '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
    })
    loads = sites(result, 'qml_load')
    assert len(loads) == 1
    metadata = qt_metadata(loads[0])
    assert metadata['status'] == 'dynamic' and not metadata.get('target_id')


@pytest.mark.parametrize('operation', ['manual', 'watch'])
@pytest.mark.parametrize('form,sdk_name', [('engine_constructor', 'QQmlApplicationEngine'),
                                         ('component_load_url', 'QQmlComponent')])
def test_req_qml017_ac04_loader_forward_edits_retire_and_restore_targets(tmp_path, monkeypatch, operation, form, sdk_name):
    """Real SDK→forward→SDK→removed updates agree with complete fresh graphs."""
    cpp, expression = fixture(tmp_path, form)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GRAPHIFY_NO_TIPS', '1')
    original = cpp.read_bytes()
    initial = run(tmp_path, monkeypatch, operation)
    assert_load(initial, original, expression)
    retained = unrelated(initial)
    assert normalized(initial) == normalized(clean(tmp_path, tmp_path / '.cold'))
    cpp.write_bytes(f'class {sdk_name};\n'.encode() + original)
    rejected = run(tmp_path, monkeypatch, operation, [cpp])
    assert all(not md.get('target_id') for md in facts(rejected, 'qml_access').values())
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / '.rejected'))
    assert unrelated(rejected) == retained
    cpp.write_bytes(original)
    restored = run(tmp_path, monkeypatch, operation, [cpp])
    assert normalized(restored) == normalized(initial)
    assert normalized(restored) == normalized(clean(tmp_path, tmp_path / '.restored'))
    before_repeat = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [cpp])) == normalized(restored)
    assert products(tmp_path) == before_repeat
    cpp.write_bytes(source(form, removed=True)[0].encode())
    removed = run(tmp_path, monkeypatch, operation, [cpp])
    assert all(not md.get('target_id') for md in facts(removed, 'qml_access').values())
    assert normalized(removed) == normalized(clean(tmp_path, tmp_path / '.removed'))
    assert unrelated(removed) == retained


@pytest.mark.parametrize('operation', ['manual', 'watch'])
@pytest.mark.parametrize('fault', ['parse', 'publication'])
def test_req_qml017_ac04_loader_forward_failure_retains_products_and_recovers(tmp_path, monkeypatch, operation, fault):
    """Authority edits cannot advance accepted products through a failed update."""
    import graphify.watch as watch
    cpp, _ = fixture(tmp_path, 'engine_constructor')
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('GRAPHIFY_NO_TIPS', '1')
    original = cpp.read_bytes()
    initial = run(tmp_path, monkeypatch, operation)
    accepted = products(tmp_path)
    rejected_source = b'class QQmlApplicationEngine;\n' + original
    cpp.write_bytes(rejected_source)
    real_replace = watch.os_replace_with_fallback

    def fail_replace(start, destination):
        if str(destination).endswith('graph.json'):
            raise PermissionError('injected authority publication failure')
        return real_replace(start, destination)

    with monkeypatch.context() as failure:
        if fault == 'parse':
            cpp.write_bytes(rejected_source + b'void broken( {')
        else:
            failure.setattr(watch, 'os_replace_with_fallback', fail_replace)
        if operation == 'manual':
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failure, operation, [cpp])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[cpp], no_cluster=True)
    assert products(tmp_path) == accepted
    cpp.write_bytes(rejected_source)
    recovered = run(tmp_path, monkeypatch, operation, [cpp])
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / '.recovered'))
    assert normalized(recovered) != normalized(initial)
    assert all(not md.get('target_id') for md in facts(recovered, 'qml_access').values())
    repeated = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert products(tmp_path) == repeated
