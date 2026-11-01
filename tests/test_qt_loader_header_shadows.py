"""INC-QML-24: an accepted included forward class is not external SDK proof."""
import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.export import to_json
from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import read_cpp
from graphify.extractors.qt_cpp_type_aliases import IncludedAliasShadows
from graphify.paths import load_node_link_graph
from tests.qt_analysis_helpers import analysis, sites
from tests.test_qt_final_incremental_parity import clean, normalized, run, unrelated
from tests.test_qt_semantic_correction_updates import products


FORMS = [
    ("QQmlApplicationEngine", 'QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ("QQmlApplicationEngine", 'QQmlApplicationEngine engine; engine.load(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ("QQmlComponent", 'QQmlEngine engine; QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ("QQmlComponent", 'QQmlEngine engine; QQmlComponent component(&engine); component.loadUrl(QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ("QQmlEngine", 'QQmlEngine engine; QQmlComponent component(&engine, QUrl("qrc:/ui/Main.qml"));', 'component.create()'),
    ("QQuickView", 'QQuickView view; view.setSource(QUrl("qrc:/ui/Main.qml"));', 'view.rootObject()'),
    ("QUrl", 'QQmlApplicationEngine engine(QUrl("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
    ("QString", 'QQmlApplicationEngine engine(QString("qrc:/ui/Main.qml"));', 'engine.rootObjects().first()'),
]


def fixture(root, form=FORMS[1], *, header="", include=True):
    _, load, handle = form
    sources = {
        "shadow.h": header,
        "access.cpp": ('#include "shadow.h"\n' if include else '') +
                      'void use() { ' + load + f' auto root={handle}; root->property("value"); }}',
        "Main.qml": 'import QtQml\nQtObject { property int value: 1 }',
        "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>',
        "keep.py": 'def helper(): return 7\n\ndef retained(): return helper()\n',
    }
    return analysis(root, sources)


@pytest.mark.parametrize("form", FORMS)
@pytest.mark.parametrize("shadow", [False, True])
def test_req_qml017_ac01_included_forward_class_blocks_sdk_loader_and_wrapper_authority(tmp_path, form, shadow):
    sdk, _, _ = form
    result = fixture(tmp_path, form, header=f"class {sdk};" if shadow else "// no source type shadow")
    access = sites(result, "qml_access", "property")[0]
    metadata = qt_metadata(access)
    graph = build_from_json(result, root=tmp_path, directed=True)
    output = tmp_path / "proof.json"
    assert to_json(graph, {}, output, force=True)
    payload = json.loads(output.read_text(encoding="utf-8"))
    restored = load_node_link_graph(payload)
    span = metadata["span"]
    assert (tmp_path / "access.cpp").read_bytes()[span["start_byte"]:span["end_byte"]] == b'root->property("value")'
    links = [edge for edge in payload["links"] if edge["source"] == access["id"]
             and edge.get("context") == "qt_cpp_qml_property_read"]
    if shadow:
        assert not metadata.get("target_id") and not links
        # The generic source forward survives even though no SDK/API target is supplied.
        assert any(node.get("metadata", {}).get("cpp_class", {}).get("is_definition") is False
                   and node["source_file"] == "shadow.h" for node in result["nodes"])
    else:
        assert metadata["status"] == "resolved" and len(links) == 1
        assert restored.has_edge(access["id"], metadata["target_id"])
        assert not restored.has_edge(metadata["target_id"], access["id"])


@pytest.mark.parametrize("header,include", [
    ("class QQmlApplicationEngine;", False),
    ("namespace Other { class QQmlApplicationEngine; }", True),
])
def test_req_qml017_ac01_unincluded_and_other_namespace_forwards_cannot_retarget_sdk(tmp_path, header, include):
    result = fixture(tmp_path, header=header, include=include)
    access = sites(result, "qml_access", "property")[0]
    assert qt_metadata(access)["status"] == "resolved" and qt_metadata(access)["target_id"]


@pytest.mark.parametrize("corruption", ["transport", "span", "line", "origin", "absolute", "outside"])
def test_req_qml017_ac04_included_class_shadow_rejects_corrupt_source_provenance(tmp_path, corruption):
    result = fixture(tmp_path, header="class QQmlApplicationEngine;")
    shadow = copy.deepcopy(next(node for node in result["nodes"]
                                if node["source_file"] == "shadow.h" and node.get("metadata", {}).get("cpp_class")))
    fact = shadow["metadata"]["cpp_class"]
    if corruption == "transport":
        fact["qualified_name_b64"] = "invalid!"
    elif corruption == "span":
        fact["span"]["start_row"] = True
    elif corruption == "line":
        shadow["source_location"] = "L99"
    elif corruption == "origin":
        shadow["_origin"] = "semantic"
    else:
        shadow["source_file"] = "/outside/shadow.h" if corruption == "absolute" else "../shadow.h"
    before = copy.deepcopy(shadow)
    with pytest.raises(ValueError, match="QT_METADATA"):
        IncludedAliasShadows(read_cpp(tmp_path / "access.cpp", tmp_path), [shadow])
    assert shadow == before


@pytest.mark.parametrize("operation", ["manual", "watch"])
def test_req_qml017_ac04_header_only_forward_edits_match_cold_warm_and_restore(tmp_path, monkeypatch, operation):
    fixture(tmp_path, header="// no source shadow")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GRAPHIFY_NO_TIPS", "1")
    initial = run(tmp_path, monkeypatch, operation)
    source = tmp_path / "shadow.h"
    original_cpp = (tmp_path / "access.cpp").read_bytes()
    initial_targets = [qt_metadata(data).get("target_id") for _, data in initial.nodes(data=True)
                       if qt_metadata(data).get("kind") == "qml_access"]
    assert len(initial_targets) == 1 and initial_targets[0]
    source.write_text("class QQmlApplicationEngine;", encoding="utf-8")
    rejected = run(tmp_path, monkeypatch, operation, [source])
    assert all(not qt_metadata(data).get("target_id") for _, data in rejected.nodes(data=True)
               if qt_metadata(data).get("kind") == "qml_access")
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / ".rejected"))
    assert normalized(rejected) == normalized(clean(tmp_path, tmp_path / ".rejected"))
    assert unrelated(rejected) == unrelated(initial)
    source.write_text("// no source shadow", encoding="utf-8")
    restored = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(restored) == normalized(initial) == normalized(clean(tmp_path, tmp_path / ".restored"))
    assert (tmp_path / "access.cpp").read_bytes() == original_cpp
    before_repeat = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(restored)
    assert products(tmp_path) == before_repeat


@pytest.mark.parametrize("operation", ["manual", "watch"])
@pytest.mark.parametrize("fault", ["parse", "publication"])
def test_req_qml017_ac04_header_shadow_failure_preserves_products_and_retries(tmp_path, monkeypatch, operation, fault):
    import graphify.watch as watch

    fixture(tmp_path, header="// no source shadow")
    monkeypatch.chdir(tmp_path)
    initial = run(tmp_path, monkeypatch, operation)
    source = tmp_path / "shadow.h"
    before = products(tmp_path)
    source.write_text("class QQmlApplicationEngine;", encoding="utf-8")
    replace = watch.os_replace_with_fallback

    def fail_graph(start, destination):
        if destination.name == "graph.json":
            raise PermissionError("public header-shadow publication failure")
        return replace(start, destination)

    with monkeypatch.context() as failure:
        if fault == "parse":
            source.write_text("class QQmlApplicationEngine; void broken( {", encoding="utf-8")
        else:
            failure.setattr(watch, "os_replace_with_fallback", fail_graph)
        if operation == "manual":
            with pytest.raises(SystemExit) as rejected:
                run(tmp_path, failure, operation, [source])
            assert rejected.value.code == 1
        else:
            assert not watch._rebuild_code(tmp_path, changed_paths=[source], no_cluster=True)
    assert products(tmp_path) == before
    source.write_text("class QQmlApplicationEngine;", encoding="utf-8")
    recovered = run(tmp_path, monkeypatch, operation, [source])
    assert normalized(recovered) == normalized(clean(tmp_path, tmp_path / ".recovered")) != normalized(initial)
    assert all(not qt_metadata(data).get("target_id") for _, data in recovered.nodes(data=True)
               if qt_metadata(data).get("kind") == "qml_access")
    current = products(tmp_path)
    assert normalized(run(tmp_path, monkeypatch, operation, [])) == normalized(recovered)
    assert products(tmp_path) == current


@pytest.mark.parametrize("visible", [False, True])
def test_req_qml017_ac01_transitive_header_shadow_requires_prior_literal_include(tmp_path, visible):
    form = FORMS[1]
    fixture(tmp_path, form, header="class QQmlApplicationEngine;")
    access = (tmp_path / "access.cpp").read_text(encoding="utf-8").replace('#include "shadow.h"\n', '')
    include = '#include "bridge.h"\n'
    result = analysis(tmp_path, {"access.cpp": include + access if visible else access + "\n" + include,
                               "bridge.h": '#include "shadow.h"\n',
                               "shadow.h": "class QQmlApplicationEngine;",
                               "Main.qml": 'import QtQml\nQtObject { property int value: 1 }',
                               "ui.qrc": '<RCC><qresource prefix="/ui"><file>Main.qml</file></qresource></RCC>'})
    metadata = qt_metadata(sites(result, "qml_access", "property")[0])
    assert bool(metadata.get("target_id")) is not visible


def test_req_qml017_ac04_class_shadow_walk_overflow_rejects_instead_of_discarding_header(tmp_path):
    """No header is opened or guessed by lookup; accepted include paths own its bound."""
    result = fixture(tmp_path, header="class QQmlApplicationEngine;")
    shadow = copy.deepcopy(next(node for node in result["nodes"]
                                if node["source_file"] == "shadow.h" and node.get("metadata", {}).get("cpp_class")))
    # Test the public dependency snapshot at its actual traversal seam. It is
    # already accepted source metadata, not a fake resolution or parser result.
    includes = []
    for index in range(129):
        name, target = ("shadow.h" if index == 0 else f"part{index}.h"), f"part{index + 1}.h"
        includes.append({"id": f"include{index}", "label": "Qt type_include: " + target,
                         "source_file": name, "source_location": "L1-L1", "file_type": "code", "_origin": "ast",
                         "metadata": {"qt": {"contract_version": 1, "kind": "type_include", "raw_name": target,
                                             "value": target, "span": {"start_byte": 0, "end_byte": 24,
                                             "start_row": 0, "end_row": 0, "start_column": 0, "end_column": 24}}}})
    index = IncludedAliasShadows(read_cpp(tmp_path / "access.cpp", tmp_path), [shadow, *includes])
    position = (tmp_path / "access.cpp").read_bytes().index(b"engine.load")
    from graphify.extractors.qt_cpp_syntax import QtCppError
    with pytest.raises(QtCppError, match="128"):
        index.class_declared((), "unrelated", position)
