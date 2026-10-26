from __future__ import annotations

from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(files: list[Path], tmp_path: Path) -> dict:
    return extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)


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


def _fixture(base: Path) -> tuple[list[Path], Path, Path, Path]:
    outer = _write(base / "Layout/Outer.swift", (
        "struct Outer {\n"
        "    struct Inner {\n"
        "        func go() {}\n"
        "    }\n"
        "}\n"
    ))
    concatenated = _write(base / "Layout/OuterInner.swift", (
        "struct OuterInner {\n"
        "    func go() {}\n"
        "}\n"
    ))
    user = _write(base / "Views/User.swift", (
        "class User {\n"
        "    var x: Outer.Inner\n\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    return [outer, concatenated, user], outer, concatenated, user


def test_member_call_through_nested_type_annotation(tmp_path: Path):
    # `x: Outer.Inner; x.go()` binds the go() declared in Outer.Inner.
    files, outer, _concatenated, user = _fixture(tmp_path / "src")
    result = _run(files, tmp_path)

    run_nids = _nodes_by_file(result, user, ".run()")
    assert len(run_nids) == 1
    targets = _call_targets(result, run_nids[0])
    go_nids = _nodes_by_file(result, outer, ".go()")
    assert len(go_nids) == 1
    assert go_nids[0] in targets


def test_member_call_dotted_type_does_not_bind_concatenated_label(tmp_path: Path):
    # The old label key turned `Outer.Inner` into `outerinner`, which bound the
    # unrelated top-level `OuterInner.go()`. It must never be a target.
    files, _outer, concatenated, user = _fixture(tmp_path / "src")
    result = _run(files, tmp_path)

    run_nids = _nodes_by_file(result, user, ".run()")
    assert len(run_nids) == 1
    wrong_go = set(_nodes_by_file(result, concatenated, ".go()"))
    wrong_type = set(_nodes_by_file(result, concatenated, "OuterInner"))
    assert wrong_go
    targets = _call_targets(result, run_nids[0])
    assert not (targets & (wrong_go | wrong_type))
    for e in result["edges"]:
        if e.get("source") == run_nids[0]:
            assert e["target"] not in wrong_go | wrong_type


def test_static_call_to_nested_type_binds_nested_not_shadowing_top_level(tmp_path: Path):
    # `Inner.go()` written inside `extension Outer` is looked up from Outer, so it
    # binds Outer.Inner even when a top-level `Inner` exists.
    base = tmp_path / "src"
    nested = _write(base / "Outer.swift", (
        "struct Outer {\n"
        "    struct Inner {\n"
        "        static func go() {}\n"
        "    }\n"
        "}\n"
    ))
    top = _write(base / "Inner.swift", "struct Inner {\n    static func go() {}\n}\n")
    ext = _write(base / "OuterExt.swift", (
        "extension Outer {\n"
        "    func f() {\n"
        "        Inner.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([nested, top, ext], tmp_path)

    f_nids = _nodes_by_file(result, ext, ".f()")
    assert len(f_nids) == 1
    targets = _call_targets(result, f_nids[0])
    assert set(_nodes_by_file(result, nested, ".go()")) <= targets
    assert not (set(_nodes_by_file(result, top, ".go()")) & targets)


def test_factory_returned_nested_type_receiver_binds_return_target(tmp_path: Path):
    base = tmp_path / "src"
    outer = _write(base / "Outer.swift", (
        "struct Outer {\n"
        "    struct Inner {\n"
        "        func go() {}\n"
        "    }\n"
        "}\n"
    ))
    factory = _write(base / "ServiceFactory.swift", (
        "class ServiceFactory {\n"
        "    static func make() -> Outer.Inner {\n"
        "        return Outer.Inner()\n"
        "    }\n"
        "}\n"
    ))
    consumer = _write(base / "Consumer.swift", (
        "struct Consumer {\n"
        "    func run() {\n"
        "        let x = ServiceFactory.make()\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([outer, factory, consumer], tmp_path)

    run_nids = _nodes_by_file(result, consumer, ".run()")
    assert len(run_nids) == 1
    assert set(_nodes_by_file(result, outer, ".go()")) <= _call_targets(result, run_nids[0])


def test_python_static_call_does_not_bind_swift_type(tmp_path: Path):
    # raw calls of every language share the resolver; a Python `Inner.go()` must
    # not reach the same-named Swift type through the Swift index.
    base = tmp_path / "src"
    swift = _write(base / "Inner.swift", "class Inner {\n    static func go() {}\n}\n")
    py_def = _write(base / "inner.py", "class Inner:\n    @staticmethod\n    def go():\n        pass\n")
    py_use = _write(base / "use.py", "def run():\n    Inner.go()\n")
    result = _run([swift, py_def, py_use], tmp_path)

    swift_go = set(_nodes_by_file(result, swift, ".go()")) | set(_nodes_by_file(result, swift, "Inner"))
    callers = [n["id"] for n in result["nodes"] if str(n.get("source_file", "")).endswith("use.py")]
    for e in result["edges"]:
        if e.get("source") in callers:
            assert e["target"] not in swift_go


def test_uppercase_static_factory_keeps_return_type_binding(tmp_path: Path):
    # `Factory.Make()` is recorded as the dotted path "Factory.Make"; it
    # names no type, so it is retried as factory `Factory`, method `Make`.
    base = tmp_path / "src"
    types = _write(base / "Types.swift", (
        "class Widget {\n"
        "    func go() {}\n"
        "}\n"
        "class Factory {\n"
        "    static func Make() -> Widget {\n"
        "        return Widget()\n"
        "    }\n"
        "}\n"
    ))
    consumer = _write(base / "Consumer.swift", (
        "struct Consumer {\n"
        "    func run() {\n"
        "        let x = Factory.Make()\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([types, consumer], tmp_path)

    run_nids = _nodes_by_file(result, consumer, ".run()")
    assert len(run_nids) == 1
    go_nids = _nodes_by_file(result, types, ".go()")
    assert len(go_nids) == 1
    assert go_nids[0] in _call_targets(result, run_nids[0])


def test_factory_return_nested_type_with_top_level_namesake_binds(tmp_path: Path):
    # The fold binds the exact return nid, so a top-level `Inner` beside
    # `Outer.Inner` must not void the binding, nor receive the call.
    base = tmp_path / "src"
    outer = _write(base / "Outer.swift", (
        "struct Outer {\n"
        "    struct Inner {\n"
        "        func go() {}\n"
        "    }\n"
        "}\n"
    ))
    top = _write(base / "Inner.swift", (
        "struct Inner {\n"
        "    func go() {}\n"
        "}\n"
    ))
    factory = _write(base / "ServiceFactory.swift", (
        "class ServiceFactory {\n"
        "    static func make() -> Outer.Inner {\n"
        "        return Outer.Inner()\n"
        "    }\n"
        "}\n"
    ))
    consumer = _write(base / "Consumer.swift", (
        "struct Consumer {\n"
        "    func run() {\n"
        "        let x = ServiceFactory.make()\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([outer, top, factory, consumer], tmp_path)

    run_nids = _nodes_by_file(result, consumer, ".run()")
    assert len(run_nids) == 1
    targets = _call_targets(result, run_nids[0])
    nested_go = _nodes_by_file(result, outer, ".go()")
    assert len(nested_go) == 1
    assert nested_go[0] in targets
    assert not set(_nodes_by_file(result, top, ".go()")) & targets


def test_member_call_same_param_name_in_two_types_binds_nothing(tmp_path: Path):
    # `x` names a different nested `State` in each type of one file; the flat
    # per-file table cannot tell them apart (fail closed), so neither call binds.
    base = tmp_path / "src"
    views = _write(base / "Views.swift", (
        "struct A {\n"
        "    struct State {\n"
        "        func go() {}\n"
        "    }\n"
        "    var x: State\n\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
        "struct B {\n"
        "    struct State {\n"
        "        func go() {}\n"
        "    }\n"
        "    var x: State\n\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([views], tmp_path)

    go_nids = set(_nodes_by_file(result, views, ".go()"))
    run_nids = _nodes_by_file(result, views, ".run()")
    assert len(go_nids) == 2
    assert len(run_nids) == 2
    for run_nid in run_nids:
        assert not _call_targets(result, run_nid) & go_nids


def test_dotted_typealias_annotation_does_not_bind_case_folded_factory(tmp_path: Path):
    # `x: Factory.Make` names a typealias (no node), so the dotted retry tries
    # factory `Factory`, method `Make`; only `make()` exists, which must not match.
    base = tmp_path / "src"
    types = _write(base / "Types.swift", (
        "class Widget {\n"
        "    func go() {}\n"
        "}\n"
        "struct Factory {\n"
        "    typealias Make = Int\n"
        "    static func make() -> Widget {\n"
        "        return Widget()\n"
        "    }\n"
        "}\n"
    ))
    consumer = _write(base / "Consumer.swift", (
        "class Consumer {\n"
        "    var x: Factory.Make\n\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([types, consumer], tmp_path)

    run_nids = _nodes_by_file(result, consumer, ".run()")
    assert len(run_nids) == 1
    go_nids = set(_nodes_by_file(result, types, ".go()"))
    assert len(go_nids) == 1
    assert not _call_targets(result, run_nids[0]) & go_nids


def test_factory_methods_differing_in_case_bind_nothing(tmp_path: Path):
    # Node ids are caseless, so `Make()` and `make()` of one type are one node
    # with two return types: the factory binds neither, whatever the edge order.
    base = tmp_path / "src"
    widget = _write(base / "Widget.swift", "class Widget {\n    func go() {}\n}\n")
    other = _write(base / "Other.swift", "class Other {\n    func go() {}\n}\n")
    factory = _write(base / "Factory.swift", (
        "class Factory {\n"
        "    static func Make() -> Widget {\n"
        "        return Widget()\n"
        "    }\n"
        "    static func make() -> Other {\n"
        "        return Other()\n"
        "    }\n"
        "}\n"
    ))
    consumer = _write(base / "Consumer.swift", (
        "struct Consumer {\n"
        "    func run() {\n"
        "        let x = Factory.Make()\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([widget, other, factory, consumer], tmp_path)

    run_nids = _nodes_by_file(result, consumer, ".run()")
    assert len(run_nids) == 1
    targets = _call_targets(result, run_nids[0])
    go_nids = (set(_nodes_by_file(result, widget, ".go()"))
               | set(_nodes_by_file(result, other, ".go()")))
    assert len(go_nids) == 2
    assert not go_nids & targets


def test_conflicting_scope_member_call_not_parked_for_cross_repo(tmp_path: Path):
    # A None scope (conflicting same-file writes) is a local ambiguity, not a type declared elsewhere:
    # parking it would let merge-graphs bind `x.go()` to a foreign `State`.
    base = tmp_path / "src"
    views = _write(base / "Views.swift", (
        "struct A {\n"
        "    struct State {\n"
        "        func go() {}\n"
        "    }\n"
        "    var x: State\n\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
        "struct B {\n"
        "    struct State {\n"
        "        func go() {}\n"
        "    }\n"
        "    var x: State\n\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([views], tmp_path)

    run_nodes = [
        n for n in result["nodes"]
        if n.get("label") == ".run()" and str(n.get("source_file", "")).endswith(views.name)
    ]
    assert len(run_nodes) == 2
    for node in run_nodes:
        parked = (node.get("metadata") or {}).get("unresolved_calls") or []
        assert parked == []


def test_ruby_type_qualified_call_does_not_bind_swift_type_without_type_table(tmp_path: Path):
    # No Swift file yields a type table here; a Ruby `Inner.go()` must not bind
    # the Swift-only `Inner.go()` (gt1 r1 F1: base behaviour of the removed early return).
    base = tmp_path / "src"
    swift = _write(base / "Inner.swift", "class Inner {\n    static func go() {}\n}\n")
    ruby = _write(base / "use.rb", "def run\n  Inner.go()\nend\n")
    result = _run([swift, ruby], tmp_path)

    swift_go = set(_nodes_by_file(result, swift, ".go()"))
    assert swift_go
    ruby_nids = {
        n["id"] for n in result["nodes"]
        if str(n.get("source_file", "")).endswith(ruby.name)
    }
    assert ruby_nids
    assert not any(
        e.get("relation") == "calls" and e.get("source") in ruby_nids
        and e.get("target") in swift_go
        for e in result["edges"]
    )


def test_ruby_call_does_not_bind_swift_type_when_a_swift_type_table_exists(tmp_path: Path):
    # The Swift member-call pass handles Swift callers only: with a Swift type
    # table in the corpus, a Ruby `Inner.go()` still binds nothing in Swift.
    base = tmp_path / "src"
    swift = _write(base / "Inner.swift", (
        "class Inner {\n    static func go() {}\n}\n"
        "class Holder {\n    let inner: Inner = Inner()\n    func f() {\n        inner.go()\n    }\n}\n"
    ))
    ruby = _write(base / "use.rb", "def run\n  Inner.go()\nend\n")
    result = _run([swift, ruby], tmp_path)

    swift_go = set(_nodes_by_file(result, swift, ".go()"))
    assert swift_go
    holder_f = _nodes_by_file(result, swift, ".f()")
    assert len(holder_f) == 1 and swift_go <= _call_targets(result, holder_f[0]), (
        "the Swift caller must still bind (a type table exists)"
    )
    ruby_nids = {
        n["id"] for n in result["nodes"]
        if str(n.get("source_file", "")).endswith(ruby.name)
    }
    assert ruby_nids
    assert not any(
        e.get("relation") == "calls" and e.get("source") in ruby_nids
        and e.get("target") in swift_go
        for e in result["edges"]
    )


def test_member_call_in_language_override_swift_file_binds(tmp_path: Path):
    # `.graphifyrc` `language.swifttpl=swift`: a remapped file is a Swift caller,
    # so its typed member call binds like one in a `.swift` file (gt1 r2 F2).
    base = tmp_path / "src"
    _write(base / ".graphifyrc", "language.swifttpl=swift\n")
    inner = _write(base / "Inner.swift", "class Inner { static func go() {} }\n")
    use = _write(base / "Use.swifttpl", (
        "class Holder {\n"
        "    let inner: Inner = Inner()\n"
        "    func run() {\n"
        "        inner.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([inner, use], tmp_path)

    run_nids = _nodes_by_file(result, use, ".run()")
    assert len(run_nids) == 1
    go_nids = set(_nodes_by_file(result, inner, ".go()"))
    assert go_nids and go_nids <= _call_targets(result, run_nids[0])
