"""Public hand-checked QML inputs and structural assertions for production tests."""
from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any


# Independent declarations-only contract: JS bodies and expressions remain opaque
# in QML-01, while owner scopes and imported spellings remain inspectable.
DECLARATIONS = '''import QtQuick
import QtQuick.Controls 6.5 as Controls
import "widgets" as Local
import "helpers.js" as Helpers
Item {
    id: root
    property int count: 1
    required property string title
    readonly property int doubled: count * 2
    default property list<QtObject> extras
    property alias editorText: editor.text
    signal activated(int value, string label)
    function bump(step: int): int {
        count += step;
        activated(count, title);
        return count;
    }
    Controls.TextField {
        id: editor
        property string caption: "kept"
        text: root.title
    }
}
'''

DECLARATION_KINDS = {"file", "component", "inline_component", "object", "property_group", "property", "signal", "function", "import"}


def write_qml(root: Path, relative: str = "Main.qml", source: str = DECLARATIONS) -> Path:
    """Write only synthetic input, retaining original UTF-8 and line endings."""
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(source.encode("utf-8"))
    return path


def qml(node: dict[str, Any]) -> dict[str, Any]:
    return node["metadata"]["qml"]


def by_kind(result: dict[str, Any], kind: str) -> list[dict[str, Any]]:
    return [node for node in result["nodes"] if qml(node)["kind"] == kind]


def one(result: dict[str, Any], kind: str, name: str | None = None) -> dict[str, Any]:
    selected = by_kind(result, kind)
    if name is not None:
        selected = [node for node in selected if qml(node)["raw_name"] == name]
    assert len(selected) == 1, (kind, name, len(selected))
    return selected[0]


def canonical(result: dict[str, Any]) -> str:
    """Compare facts without assuming parallel/cache emission list ordering."""
    facts = {key: sorted(result.get(key, []), key=lambda item: json.dumps(item, sort_keys=True)) for key in ("nodes", "edges", "raw_calls", "diagnostics")}
    return json.dumps(facts, ensure_ascii=False, sort_keys=True)


def assert_contains(result: dict[str, Any], parent: dict[str, Any], child: dict[str, Any]) -> None:
    assert any(edge["source"] == parent["id"] and edge["target"] == child["id"] and edge["relation"] == "contains" for edge in result["edges"])


def assert_spans(result: dict[str, Any], source: bytes) -> None:
    """Independently recompute zero-based byte/point positions from original input."""
    for node in result["nodes"]:
        span = qml(node)["span"]
        assert 0 <= span["start_byte"] <= span["end_byte"] <= len(source)
        for side in ("start", "end"):
            offset = span[f"{side}_byte"]
            prefix = source[:offset]
            assert span[f"{side}_row"] == prefix.count(b"\n")
            assert span[f"{side}_column"] == offset - prefix.rfind(b"\n") - 1
        assert node["source_location"].startswith(f'L{span["start_row"] + 1}')


def assert_no_machine_paths(value: Any, root: Path) -> None:
    """Check nested values even when exception repr/JSON doubled Windows separators."""
    if isinstance(value, dict):
        for child in value.values():
            assert_no_machine_paths(child, root)
    elif isinstance(value, (list, tuple)):
        for child in value:
            assert_no_machine_paths(child, root)
    elif isinstance(value, str):
        assert root.as_posix() not in re.sub(r"[\\/]+", "/", value)


# Probe the built package in a fresh interpreter, never importing its source
# checkout. Core absence is forced before imports at the optional-library boundary.
WHEEL_PROBE = r'''
import importlib.abc
import json
from pathlib import Path
import sys

target, source_root, mode = map(Path, sys.argv[1:])
sys.path.insert(0, str(target))

class MissingOptionalGrammar(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == "tree_sitter_language_pack" or fullname.startswith("tree_sitter_language_pack."):
            raise ModuleNotFoundError("QML optional parser unavailable in core-only probe")

if str(mode) == "core":
    sys.meta_path.insert(0, MissingOptionalGrammar())
    for name in list(sys.modules):
        if name.startswith("tree_sitter_language_pack"):
            del sys.modules[name]

import graphify
from graphify.extractors.qml import extract_qml
from graphify.extract import extract_python

assert Path(graphify.__file__).resolve().is_relative_to(target.resolve())
qml_result = extract_qml(source_root / "Main.qml", root=source_root)
python_result = extract_python(source_root / "safe.py", root=source_root)
assert any(node["label"] == "safe()" for node in python_result["nodes"])
print(json.dumps({"qml": qml_result, "python_ok": True}))
'''
