"""The Swift member-call pass binds only targets Swift can call.

`_resolve_swift_member_calls` gates its callers on Swift; its targets must be
gated too, or a Swift `Inner.go()` binds a Python `class Inner: def go()`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

import graphify.extract as extract_module
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


# A `.h` header is C, C++ or ObjC, and only ObjC is a Swift target there.
# An ObjC method label carries a `+`/`-` sigil; C and C++ labels never do.

def _edges_from(result: dict, caller_nid: str) -> list[dict]:
    return [e for e in result["edges"] if e.get("source") == caller_nid]


def _only_caller(result: dict, use: Path) -> str:
    callers = _nodes_by_file(result, use, "useRun()")
    assert len(callers) == 1, callers
    return callers[0]


def _assert_no_edge_into(result: dict, caller_nid: str, header: Path) -> None:
    header_nids = _nids_in(result, header)
    assert header_nids, f"{header.name} was not extracted"
    wrong = [e for e in _edges_from(result, caller_nid) if e.get("target") in header_nids]
    assert not wrong, f"a Swift call must not bind a C/C++ target in {header.name}: {wrong}"


def _edge(result: dict, caller_nid: str, target_nid: str, relation: str) -> dict:
    found = [
        e for e in _edges_from(result, caller_nid)
        if e.get("target") == target_nid and e.get("relation") == relation
    ]
    assert found, (relation, target_nid, _edges_from(result, caller_nid))
    return found[0]


def _one(result: dict, file: Path, label: str) -> str:
    nids = _nodes_by_file(result, file, label)
    assert len(nids) == 1, (file.name, label, nids)
    return nids[0]


def test_swift_type_call_does_not_bind_cpp_class_method_in_h(tmp_path: Path):
    pytest.importorskip("tree_sitter_objc")
    pytest.importorskip("tree_sitter_cpp")
    base = tmp_path / "src"
    inner = _write(base / "Inner.h", "class Inner { public: static void go() {} };\n")
    widget = _write(base / "Widget.h", "@interface Widget\n+ (void)render;\n@end\n")
    holder = _write(base / "Holder.h", "@interface Holder\n+ (instancetype)shared;\n@end\n")
    use = _write(base / "Use.swift", (
        "func useRun() {\n    Inner.go()\n    Widget.render()\n    Holder.shared()\n}\n"
    ))
    result = _run([inner, widget, holder, use], tmp_path)

    caller = _only_caller(result, use)
    _assert_no_edge_into(result, caller, inner)
    # The ObjC class methods in a `.h` still bind, EXTRACTED (type-qualified).
    for header, label in ((widget, "+render"), (holder, "+shared")):
        edge = _edge(result, caller, _one(result, header, label), "calls")
        assert edge["confidence"] == "EXTRACTED", edge


def test_swift_instance_call_still_binds_objc_instance_method_in_h(tmp_path: Path):
    pytest.importorskip("tree_sitter_objc")
    base = tmp_path / "src"
    widget = _write(base / "Widget.h", "@interface Widget\n- (void)render;\n@end\n")
    use = _write(base / "Use.swift", (
        "func useRun() {\n    let w = Widget()\n    w.render()\n}\n"
    ))
    result = _run([widget, use], tmp_path)

    caller = _only_caller(result, use)
    edge = _edge(result, caller, _one(result, widget, "-render"), "calls")
    assert edge["confidence"] == "INFERRED", edge


def test_swift_call_to_cpp_class_emits_no_reference_in_h(tmp_path: Path):
    # The method is absent, so the old fallback was a type-only `references`
    # edge to the C++ class; the class owns only a sigil-less `.go()`.
    pytest.importorskip("tree_sitter_cpp")
    base = tmp_path / "src"
    inner = _write(base / "Inner.h", "class Inner { public: static void go() {} };\n")
    use = _write(base / "Use.swift", "func useRun() {\n    Inner.missing()\n}\n")
    result = _run([inner, use], tmp_path)

    _assert_no_edge_into(result, _only_caller(result, use), inner)


def test_swift_call_does_not_bind_cpp_operator_in_h(tmp_path: Path):
    # The C++ extractor labels an operator `.operator-()`: no leading sigil.
    pytest.importorskip("tree_sitter_cpp")
    base = tmp_path / "src"
    vec = _write(base / "Vec.h", (
        "class Vec { public: Vec operator-(const Vec& o) const;"
        " Vec operator+(const Vec& o) const { return o; } };\n"
    ))
    use = _write(base / "Use.swift", "func useRun() {\n    Vec.minus()\n}\n")
    result = _run([vec, use], tmp_path)

    _assert_no_edge_into(result, _only_caller(result, use), vec)


def _c_header_type_corpus() -> tuple[list[dict], list[dict], list[dict]]:
    # The C extractor emits no type node for a struct, so the corpus is built at
    # the resolver: a contained, sigil-less C type `Inner` in `Inner.h` and a
    # Swift `Inner.go()` with no such method. Without the gate the type-only
    # fallback binds `references useRun() -> Inner`.
    nodes = [
        {"id": "inner_h", "label": "Inner.h", "source_file": "src/Inner.h", "file_type": "code"},
        {"id": "inner_h_inner", "label": "Inner", "source_file": "src/Inner.h",
         "file_type": "code"},
        {"id": "use_userun", "label": "useRun()", "source_file": "src/Use.swift",
         "file_type": "code"},
    ]
    edges = [{"source": "inner_h", "target": "inner_h_inner", "relation": "contains",
              "source_file": "src/Inner.h"}]
    per_file = [{"raw_calls": [{
        "is_member_call": True, "receiver": "Inner", "callee": "go",
        "caller_nid": "use_userun", "source_file": "src/Use.swift", "source_location": "L2",
    }]}]
    return per_file, nodes, edges


def _resolved_into_inner(monkeypatch=None, gate=None) -> list[dict]:
    if gate is not None:
        assert monkeypatch is not None
        monkeypatch.setattr(extract_module, "_swift_header_target_ok", gate)
    per_file, nodes, edges = _c_header_type_corpus()
    extract_module._resolve_swift_member_calls(per_file, nodes, edges)
    return [
        e for e in edges
        if e.get("target") == "inner_h_inner" and e.get("relation") != "contains"
    ]


def test_swift_call_to_c_header_type_binds_nothing():
    assert not _resolved_into_inner(), "a Swift call must not bind a C type in a `.h`"


def test_c_header_type_corpus_reaches_the_gate(monkeypatch):
    # Control: with the `.h` gate open, the same corpus binds the C type, so the
    # test above fails if the gate is removed.
    edges = _resolved_into_inner(monkeypatch, lambda *_args: True)
    assert [e["relation"] for e in edges] == ["references"], edges


def test_swift_call_to_methodless_objc_class_loses_type_reference(tmp_path: Path):
    # Accepted loss: an ObjC class with no ObjC method looks like a C/C++ type,
    # so the type-only `references` fallback to it is dropped. A Swift
    # extension method on that class lives in `.swift` and still binds.
    pytest.importorskip("tree_sitter_objc")
    base = tmp_path / "src"
    bare = _write(base / "Bare.h", (
        "#import <Foundation/Foundation.h>\n"
        "@interface Bare : NSObject\n"
        "@property (nonatomic) int count;\n"
        "@end\n"
    ))
    ext = _write(base / "BareExt.swift", "extension Bare { func more() {} }\n")
    use = _write(base / "Use.swift", "func useRun() {\n    Bare.more()\n    Bare.ping()\n}\n")
    result = _run([bare, ext, use], tmp_path)

    caller = _only_caller(result, use)
    bare_nids = _nids_in(result, bare)
    assert bare_nids
    refs = [
        e for e in _edges_from(result, caller)
        if e.get("relation") == "references" and e.get("target") in bare_nids
    ]
    assert not refs, f"the accepted loss changed: {refs}"
    _edge(result, caller, _one(result, ext, ".more()"), "calls")


def _context(result: dict, changed: Path) -> tuple[list[dict], list[dict]]:
    # What an incremental rebuild hands the resolvers for the unchanged files:
    # their AST nodes and their contains/method edges (as `graphify update`).
    keys = ("id", "label", "source_file", "file_type", "type",
            "_callable", "_callable_class", "_swift_extension_only", "_swift_qualified")
    nodes = [
        {k: n[k] for k in keys if k in n} for n in result["nodes"]
        if n.get("source_file") and not str(n["source_file"]).endswith(changed.name)
    ]
    edges = [
        {k: e.get(k) for k in ("source", "target", "relation", "source_file")}
        for e in result["edges"]
        if e.get("relation") in ("contains", "method")
        and e.get("source_file") and not str(e["source_file"]).endswith(changed.name)
    ]
    return nodes, edges


@pytest.mark.parametrize("incremental", [False, True], ids=["full", "incremental"])
def test_swift_call_keeps_type_reference_to_objc_class_in_h(tmp_path: Path, incremental: bool):
    # An ObjC class in a `.h` owns a sigil method, so the type-only
    # `references` fallback still binds; also when the method is declared only
    # in the `.m` (the merged class node keeps the header's `source_file`).
    pytest.importorskip("tree_sitter_objc")
    base = tmp_path / "src"
    widget = _write(base / "Widget.h", "@interface Widget\n- (void)render;\n@end\n")
    holder = _write(base / "Holder.h", "@interface Holder\n+ (instancetype)shared;\n@end\n")
    gadget = _write(base / "Gadget.h", "@interface Gadget : NSObject\n@end\n")
    gadget_m = _write(base / "Gadget.m", (
        '#import "Gadget.h"\n'
        "@implementation Gadget\n"
        "- (void)spin {\n"
        "}\n"
        "@end\n"
    ))
    use = _write(base / "Use.swift", (
        "func useRun() {\n    Widget.missing()\n    Gadget.missing()\n    Holder.shared()\n}\n"
    ))
    full = _run([widget, holder, gadget, gadget_m, use], tmp_path)
    targets = (_one(full, widget, "Widget"), _one(full, gadget, "Gadget"))
    shared = _one(full, holder, "+shared")
    result = full
    if incremental:
        nodes, edges = _context(full, use)
        use.write_text(use.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        result = extract(
            [use], cache_root=tmp_path / "cache", root=base, parallel=False,
            resolution_context_nodes=nodes, resolution_context_edges=edges,
        )

    caller = _only_caller(result, use)
    for target in targets:
        edge = _edge(result, caller, target, "references")
        assert edge["confidence"] == "EXTRACTED", edge
    # A direct ObjC method target in a `.h` also binds on both paths.
    edge = _edge(result, caller, shared, "calls")
    assert edge["confidence"] == "EXTRACTED", edge
