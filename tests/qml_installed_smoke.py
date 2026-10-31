"""Run with an isolated interpreter to verify a clean installed Graphify wheel.

This intentionally uses no pytest/source-checkout imports. CI supplies either
the qml extra or --core-only, then checks an actual production entry point.
"""
from __future__ import annotations

import importlib.metadata
import json
from pathlib import Path
import sys
import tempfile


def offline_guard(event, _args):
    if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
        raise RuntimeError("Analysis attempted a network/process operation")


def native_module_smoke(root):
    """Installed facade joins accepted build membership and literal resources."""
    from graphify.build import build_from_json
    from graphify.extract import extract
    from graphify.extractors.qml_facts import qml_metadata
    from graphify.extractors.qt_cpp_facts import qt_metadata

    root.mkdir()
    files = {
        "backend.h": 'class Backend : public QObject { Q_OBJECT QML_ELEMENT '
                     'Q_PROPERTY(int count READ count) public: int count() { return 1; } '
                     'Q_INVOKABLE int next(int value) { return value; } };',
        "Main.qml": 'import Installed.Tools 1.0\nBackend { property int copied: count; '
                    'function run() { next(1) } }',
        "loader.cpp": 'void load(){ QQmlApplicationEngine engine; '
                      'engine.load(QUrl("qrc:/ui/Main.qml")); }',
        "CMakeLists.txt": 'qt_add_qml_module(installed URI Installed.Tools VERSION 1.0 '
                          'QML_FILES Main.qml SOURCES backend.h loader.cpp)',
        "resources.qrc": '<RCC><qresource prefix="/ui"><file alias="Main.qml">'
                         'Main.qml</file></qresource></RCC>',
    }
    paths = []
    for name, source in files.items():
        path = root / name
        path.write_text(source, encoding="utf-8")
        paths.append(path)
    result = extract(paths, root=root, cache_root=root, parallel=False)
    assert not result["failed_sources"] and not result["qml_failures"]
    graph = build_from_json(result, root=root, directed=True)
    call = next(edge for edge in result["edges"] if edge.get("context") == "qml_js_call")
    proof = qt_metadata(call)["native_endpoint"]
    assert proof["canonical_target_id"] == call["target"]
    assert graph.nodes[call["target"]]["source_file"] == "backend.h"
    assert graph.nodes[call["target"]]["label"].endswith(".next()")
    assert graph.has_edge(call["source"], call["target"])
    assert qt_metadata(graph.nodes[proof["provider_id"]])["kind"] == "registration"
    modules = [graph.nodes[item] for item in proof["evidence"]
               if qml_metadata(graph.nodes[item]).get("kind") == "qt_module"]
    assert len(modules) == 1 and modules[0]["source_file"] == "CMakeLists.txt"
    assert qml_metadata(modules[0])["uri"] == "Installed.Tools"
    loader = next(node for node in result["nodes"] if qt_metadata(node).get("kind") == "qml_load")
    component = next(node for node in result["nodes"] if qml_metadata(node).get("kind") == "component")
    assert qt_metadata(loader)["status"] == "resolved"
    assert qt_metadata(loader)["target_id"] == component["id"]
    edge = graph.edges[loader["id"], component["id"]]
    assert edge["context"] == "qt_cpp_qml_load" and edge["source_file"] == "loader.cpp"


def main():
    sys.addaudithook(offline_guard)
    from graphify.extract import extract, extract_python
    from graphify.extractors.qml import extract_qml
    from graphify.extractors.qml_metadata import extract_qmldir
    from graphify.extractors.qml_facts import qml_metadata
    from graphify.build import build_from_json
    from graphify.detect import FileType, classify_file
    from graphify.validate import validate_extraction

    assert "site-packages" in (sys.modules["graphify"].__file__ or "")
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "Main.qml"
        path.write_text('import "helpers.js" as Tools\nItem { id: root; property int value: 3; property int derived: value + Tools.twice(value); signal ready(int eventValue); onReady: { value = Tools.twice(eventValue) } function twice() { return value * 2; } }', encoding="utf-8")
        assert classify_file(path) == FileType.CODE
        metadata = root / "qmldir"
        original = b'\xef\xbb\xbfmodule Sample.Tools\r\nThing 1.0 Thing.qml\r\n'
        metadata.write_bytes(original)
        declarations = extract_qmldir(metadata, root=root)
        module = next(node for node in declarations["nodes"] if qml_metadata(node)["kind"] == "module")
        assert qml_metadata(module)["span"]["start_byte"] == 3
        assert qml_metadata(module)["span"]["end_byte"] == original.index(b'\r\n')
        from graphify.extractors.qt_cpp_facts import qt_metadata
        native = root / "Backend.cpp"
        native.write_text("class Backend : public QObject { Q_OBJECT public: void tick() { emit ready(1); } signals: void ready(int value); };", encoding="utf-8")
        cpp = extract([native], root=root, cache_root=root, parallel=False)
        assert not cpp["qml_failures"] and not cpp["failed_sources"]
        emissions = [node for node in cpp["nodes"] if qt_metadata(node).get("kind") == "emission"]
        assert len(emissions) == 1 and qt_metadata(emissions[0])["status"] == "resolved"
        assert any(edge.get("context") == "qt_signal_emit" for edge in cpp["edges"])
        result = extract_qml(path, root=root)
        if "--core-only" in sys.argv:
            assert result["diagnostics"][0]["code"] == "QML_PARSER_MISSING"
            assert result["nodes"] == []
            python = root / "main.py"
            python.write_text("def safe():\n    return 1\n", encoding="utf-8")
            assert any(n["label"] == "safe()" for n in extract_python(python, root=root)["nodes"])
        else:
            script = root / "helpers.js"
            script.write_text('.pragma library\nfunction twice(value) { return value * 2; }', encoding="utf-8")
            assert not result.get("error")
            declarations = {(n["metadata"]["qml"]["kind"], n["metadata"]["qml"]["raw_name"])
                            for n in result["nodes"] if "raw_name" in n["metadata"]["qml"]}
            assert {("component", "Main"), ("property", "value"), ("function", "twice")} <= declarations
            batch = extract([path, script], root=root, cache_root=root, parallel=False)
            assert not batch["failed_sources"] and not batch["qml_failures"]
            assert validate_extraction(batch) == []
            graph = build_from_json(batch, directed=True, root=root)
            assert graph.number_of_nodes() == len(batch["nodes"])
            assert {"qml_binding_read", "qml_script_call", "qml_signal_subscription"} <= {
                edge.get("context") for edge in batch["edges"]}
            native_module_smoke(root / "native-profile")
    print(json.dumps({"python": sys.version.split()[0], "graphify": importlib.metadata.version("graphifyy"),
                      "tree_sitter": importlib.metadata.version("tree-sitter"),
                      "mode": "core-only" if "--core-only" in sys.argv else "qml", "status": "passed"}))


if __name__ == "__main__":
    main()
