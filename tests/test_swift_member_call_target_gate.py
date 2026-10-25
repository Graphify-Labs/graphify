"""The Swift member-call pass binds only targets Swift can call.

`_resolve_swift_member_calls` gates its callers on Swift; its targets must be
gated too, or a Swift `Inner.go()` binds a Python `class Inner: def go()`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify import resolver_registry
from graphify.extract import UNRESOLVED_CALLS_KEY, extract

pytest.importorskip("tree_sitter_swift")


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(files: list[Path], tmp_path: Path) -> dict:
    return extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)


def _nids_in(result: dict, file: Path) -> set[str]:
    return {
        n["id"] for n in result["nodes"]
        if str(n.get("source_file", "")).endswith(file.name)
    }


def _nodes_by_file(result: dict, file: Path, label: str) -> list[str]:
    return [
        n["id"] for n in result["nodes"]
        if n.get("label") == label and str(n.get("source_file", "")).endswith(file.name)
    ]


def _call_targets(result: dict, caller_nid: str) -> set[str]:
    return {
        e["target"] for e in result["edges"]
        if e.get("source") == caller_nid and e.get("relation") == "calls"
    }


def test_swift_member_call_does_not_bind_python_method(tmp_path: Path, monkeypatch):
    # The Python `Inner` is the only declaration of the name: the Swift call
    # binds nothing in Python and parks like a call on an unknown type.
    # The Python member-call pass is left out here so the edge count
    # measures the Swift pass alone.
    monkeypatch.setattr(resolver_registry, "_REGISTRY", [
        r for r in resolver_registry._REGISTRY if r.name != "python_member_calls"
    ])
    base = tmp_path / "src"
    app = _write(base / "app.swift", "func useRun() {\n    Inner.go()\n}\n")
    lib = _write(base / "lib.py", "class Inner:\n    def go(self):\n        pass\n")
    result = _run([app, lib], tmp_path)

    swift_nids = _nids_in(result, app)
    python_nids = _nids_in(result, lib)
    assert swift_nids and python_nids
    cross = [
        e for e in result["edges"]
        if e.get("source") in swift_nids and e.get("target") in python_nids
    ]
    assert not cross, f"a Swift call must not bind a Python target: {cross}"

    callers = _nodes_by_file(result, app, "useRun()")
    assert len(callers) == 1
    caller = next(n for n in result["nodes"] if n["id"] == callers[0])
    parked = (caller.get("metadata") or {}).get(UNRESOLVED_CALLS_KEY) or []
    assert any(p.get("callee") == "go" and p.get("receiver_type") == "Inner" for p in parked), (
        f"the unbound call parks like an unknown type: {parked}"
    )


def test_swift_member_call_still_binds_swift_method(tmp_path: Path):
    base = tmp_path / "src"
    inner = _write(base / "Inner.swift", "class Inner { static func go() {} }\n")
    use = _write(base / "Use.swift", "func useRun() {\n    Inner.go()\n}\n")
    result = _run([inner, use], tmp_path)

    callers = _nodes_by_file(result, use, "useRun()")
    assert len(callers) == 1
    go_nids = set(_nodes_by_file(result, inner, ".go()"))
    assert go_nids and go_nids <= _call_targets(result, callers[0])


def test_swift_member_call_binds_language_override_swift_target(tmp_path: Path):
    # `.graphifyrc` `language.swifttpl=swift`: the remapped file declares the
    # target, so it is a Swift target although its suffix is not `.swift`.
    base = tmp_path / "src"
    _write(base / ".graphifyrc", "language.swifttpl=swift\n")
    inner = _write(base / "Inner.swifttpl", "class Inner { static func go() {} }\n")
    use = _write(base / "Use.swift", "func useRun() {\n    Inner.go()\n}\n")
    result = _run([inner, use], tmp_path)

    callers = _nodes_by_file(result, use, "useRun()")
    assert len(callers) == 1
    go_nids = set(_nodes_by_file(result, inner, ".go()"))
    assert go_nids and go_nids <= _call_targets(result, callers[0])


def test_swift_member_call_still_binds_objc_interop(tmp_path: Path):
    # Swift<->ObjC interop (#1556) stays: an ObjC method, and a Swift extension
    # method folded onto the ObjC class node, are Swift targets.
    pytest.importorskip("tree_sitter_objc")
    base = tmp_path / "src"
    header = _write(base / "Widget.h", "@interface Widget\n- (void)render;\n@end\n")
    impl = _write(base / "Widget.m", (
        '#import "Widget.h"\n'
        "@implementation Widget\n"
        "- (void)render {\n"
        "}\n"
        "@end\n"
    ))
    extras = _write(base / "WidgetExtras.swift", (
        "extension Widget {\n"
        "    func describe() -> String {\n"
        '        return "widget"\n'
        "    }\n"
        "}\n"
    ))
    use = _write(base / "Use.swift", "func useRun() {\n    Widget.render()\n    Widget.describe()\n}\n")
    result = _run([header, impl, extras, use], tmp_path)

    callers = _nodes_by_file(result, use, "useRun()")
    assert len(callers) == 1
    labels = {
        n.get("label") for n in result["nodes"]
        if n["id"] in _call_targets(result, callers[0])
    }
    assert any("render" in str(label) for label in labels), labels
    assert ".describe()" in labels, labels
