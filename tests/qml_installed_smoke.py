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
    from graphify.build import build_from_json
    from graphify.detect import FileType, classify_file
    from graphify.validate import validate_extraction

    assert "site-packages" in sys.modules["graphify"].__file__
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        path = root / "Main.qml"
        path.write_text('Item { id: root; property int value: 3; function twice() { return value * 2; } }', encoding="utf-8")
        assert classify_file(path) == FileType.CODE
        result = extract_qml(path, root=root)
        if "--core-only" in sys.argv:
            assert result["diagnostics"][0]["code"] == "QML_PARSER_MISSING"
            assert result["nodes"] == []
            python = root / "main.py"
            python.write_text("def safe():\n    return 1\n", encoding="utf-8")
            assert any(n["label"] == "safe()" for n in extract_python(python, root=root)["nodes"])
        else:
            assert not result.get("error")
            declarations = {(n["metadata"]["qml"]["kind"], n["metadata"]["qml"]["raw_name"])
                            for n in result["nodes"] if "raw_name" in n["metadata"]["qml"]}
            assert {("component", "Main"), ("property", "value"), ("function", "twice")} <= declarations
            batch = extract([path], root=root, cache_root=root, parallel=False)
            assert not batch["failed_sources"] and not batch["qml_failures"]
            assert validate_extraction(batch) == []
            graph = build_from_json(batch, directed=True, root=root)
            assert graph.number_of_nodes() == len(batch["nodes"])
    print(json.dumps({"python": sys.version.split()[0], "graphify": importlib.metadata.version("graphifyy"),
                      "tree_sitter": importlib.metadata.version("tree-sitter"),
                      "mode": "core-only" if "--core-only" in sys.argv else "qml", "status": "passed"}))


if __name__ == "__main__":
    main()
