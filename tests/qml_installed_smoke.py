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
    print(json.dumps({"python": sys.version.split()[0], "graphify": importlib.metadata.version("graphifyy"),
                      "tree_sitter": importlib.metadata.version("tree-sitter"),
                      "mode": "core-only" if "--core-only" in sys.argv else "qml", "status": "passed"}))


if __name__ == "__main__":
    main()
