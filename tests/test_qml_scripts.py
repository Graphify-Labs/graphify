"""QML-007-AC02/04 accepted script aliases, modules and shared-source isolation."""

import copy
import json

import pytest

from graphify.build import build_from_json
from graphify.extract import extract
from graphify.extractors.qml_facts import qml_metadata
from graphify.extractors.qml_scripts import collect_qml_scripts
from tests.qml_expression_helpers import extraction, nodes, single, target_edges


def test_literal_imported_helpers_and_library_do_not_inherit_document_ids(tmp_path):
    result = extraction(tmp_path, {"helper.js": ".pragma library\nfunction helper(n) { return n; }\nfunction unavailable() { return root.value; }",
        "Main.qml": 'import "helper.js" as H\nQtObject { id: root; property int value: H.helper(2); function run() { H.unavailable(); } }',
        "Other.qml": 'import "helper.js" as Different\nQtObject { id: root; property int value: Different.helper(3) }'})
    helper = single(result, "qml_script_function", "helper")
    for name in ("H.helper", "Different.helper"):
        assert target_edges(result, single(result, "call", name), "qml_script_call")[0]["target"] == helper["id"]
    script_read = single(result, "read", "root.value", "helper.js")
    assert qml_metadata(script_read)["status"] == "unavailable"
    assert qml_metadata(script_read)["reason"] == "script_runtime_context_unavailable"
    assert not target_edges(result, script_read)
    graph = build_from_json(result, directed=True, root=tmp_path)
    for site in nodes(result, "call", "H.helper"):
        assert graph.has_edge(site["id"], helper["id"])
    assert single(result, "script_file")["label"].startswith("QML script: ")


def test_mjs_explicit_exports_aliases_and_private_functions(tmp_path):
    result = extraction(tmp_path, {"helper.mjs": "function hidden() { return 1; }\nfunction local() { return hidden(); }\nexport { local as publicName };\nexport const arrow = (n) => local();",
        "Main.qml": 'import "helper.mjs" as H\nQtObject { property int good: H.publicName(); property int arrow: H.arrow(1); property int bad: H.hidden() }'})
    assert target_edges(result, single(result, "call", "H.publicName"))[0]["target"] == single(result, "qml_script_function", "local")["id"]
    assert target_edges(result, single(result, "call", "H.arrow"))[0]["target"] == single(result, "qml_script_function", "arrow")["id"]
    assert not target_edges(result, single(result, "call", "H.hidden"))
    assert qml_metadata(single(result, "call", "H.hidden"))["status"] == "unavailable"
    hidden = single(result, "call", "hidden", "helper.mjs")
    assert target_edges(result, hidden)[0]["target"] == single(result, "qml_script_function", "hidden")["id"]


def test_qmldir_exported_script_namespaces_keep_module_qualifiers(tmp_path):
    result = extraction(tmp_path, {"Public/Tools/qmldir": "module Public.Tools\nHelper 1.0 helper.js",
        "Public/Tools/helper.js": ".pragma library\nfunction calculate() { return 2; }",
        "Main.qml": "import Public.Tools 1.0 as Tools\nQtObject { property int value: Tools.Helper.calculate() }"})
    call = single(result, "call", "Tools.Helper.calculate")
    assert target_edges(result, call)[0]["target"] == single(result, "qml_script_function", "calculate")["id"]
    assert qml_metadata(call)["evidence"]


def test_accepted_script_dependencies_support_classic_and_esm_imports(tmp_path):
    result = extraction(tmp_path, {"dep.js": "function number() { return 1; }",
        "main.js": '.import "dep.js" as D\nfunction number() { return D.number(); }',
        "dep.mjs": "export function answer() { return 2; }",
        "main.mjs": "import {answer as renamed} from './dep.mjs'; export function number() { return renamed(); }",
        "Main.qml": 'import "main.js" as C\nimport "main.mjs" as E\nQtObject { property int value: C.number() + E.number() }'})
    assert target_edges(result, single(result, "call", "D.number", "main.js"))[0]["target"] == single(result, "qml_script_function", "number", "dep.js")["id"]
    assert target_edges(result, single(result, "call", "renamed", "main.mjs"))[0]["target"] == single(result, "qml_script_function", "answer", "dep.mjs")["id"]


def test_qt_directive_masking_preserves_original_utf8_crlf_expression_spans(tmp_path):
    source = "// café\r\n.pragma library\r\nfunction helper() { return unavailable; }\r\n"
    result = extraction(tmp_path, {"helper.js": source,
        "Main.qml": 'import "helper.js" as H\nQtObject { property int value: H.helper() }'})
    script_read = single(result, "read", "unavailable", "helper.js")
    span = qml_metadata(script_read)["span"]
    raw = (tmp_path / "helper.js").read_bytes()
    assert raw[span["start_byte"]:span["end_byte"]] == b"unavailable"
    assert span["start_row"] == 2
    assert script_read["source_location"] == "L3-L3"


def test_qt_directive_text_inside_comments_and_templates_is_not_active(tmp_path):
    source = '/*\n.pragma library\n.import "missing.js" as Wrong\n*/\nconst example = `\n.pragma library\n`;\nfunction helper() { return 1; }'
    result = extraction(tmp_path, {"helper.js": source,
        "Main.qml": 'import "helper.js" as H\nQtObject { property int value: H.helper() }'})
    assert qml_metadata(single(result, "script_file"))["pragma_library"] is False
    assert not nodes(result, "script_import")
    assert target_edges(result, single(result, "call", "H.helper"))


def test_script_overlay_retains_original_shared_js_nodes_and_never_executes(tmp_path):
    marker = tmp_path / "must-not-exist"
    script = tmp_path / "shared.js"
    script.write_text(f"function shared() {{ return 1; }}\nrequire('fs').writeFileSync('{marker.as_posix()}', 'bad');", encoding="utf-8")
    qml = tmp_path / "Main.qml"
    qml.write_text('import "shared.js" as H\nQtObject { property int value: H.shared() }', encoding="utf-8")
    baseline = extract([script], root=tmp_path, cache_root=tmp_path, parallel=False)
    mixed = extract([script, qml], root=tmp_path, cache_root=tmp_path, parallel=False)
    generic = [node for node in mixed["nodes"] if node["source_file"] == "shared.js" and not qml_metadata(node)]
    assert generic == baseline["nodes"]
    assert not marker.exists()
    assert all(node["label"].startswith("QML script: ") for node in nodes(mixed, "qml_script_function"))


def test_generic_js_calls_cannot_bind_to_qml_owned_expression_sites(tmp_path):
    """A matching occurrence label cannot become a shared JavaScript definition."""
    shared, web, qml = (tmp_path / name for name in ("shared.js", "web.js", "Main.qml"))
    shared.write_text("function invoke() { phantom(); }", encoding="utf-8")
    web.write_text("function web() { phantom(); }", encoding="utf-8")
    qml.write_text('import "shared.js" as H\nQtObject { property int value: H.invoke() }', encoding="utf-8")
    baseline = extract([shared, web], root=tmp_path, cache_root=tmp_path, parallel=False)
    mixed = extract([shared, web, qml], root=tmp_path, cache_root=tmp_path, parallel=False)
    generic_ids = {node["id"] for node in mixed["nodes"] if not qml_metadata(node)}
    generic_edges = [edge for edge in mixed["edges"] if edge["source"] in generic_ids]
    assert generic_edges == baseline["edges"]
    assert all(edge["target"] in generic_ids for edge in generic_edges)


def test_script_overlay_does_not_read_unaccepted_imports_or_network(tmp_path, monkeypatch):
    qml = tmp_path / "Main.qml"
    qml.write_text('import "outside.js" as H\nQtObject { property int value: H.run() }', encoding="utf-8")
    outside = tmp_path / "outside.js"
    outside.write_text("function run() {}", encoding="utf-8")
    from graphify.extractors.qml import extract_qml
    result = extract_qml(qml, root=tmp_path)
    before = copy.deepcopy(result)
    def forbidden(*args, **kwargs):
        raise AssertionError("script overlay expanded accepted corpus")
    monkeypatch.setattr(type(outside), "open", forbidden)
    collect_qml_scripts([qml], [result], root=tmp_path)
    assert result == before


@pytest.mark.parametrize("source,code", [("function broken( {", "QML_SCRIPT_SYNTAX"),
    (".pragma library\nexport function f() {}", "QML_SCRIPT_UNSUPPORTED")])
def test_imported_partial_or_unsupported_module_failure_is_explicit(tmp_path, source, code):
    script = tmp_path / "bad.mjs"
    script.write_text(source, encoding="utf-8")
    qml = tmp_path / "Main.qml"
    qml.write_text('import "bad.mjs" as H\nQtObject { property int value: H.f() }', encoding="utf-8")
    result = extract([qml, script], root=tmp_path, cache_root=tmp_path, parallel=False)
    assert result["qml_failures"] == [{"code": code, "source_file": "bad.mjs"}]
    assert not nodes(result, "qml_script_function")
    json.dumps(result)
