"""Swift receiver writes whose type is not proven bind nothing.

A receiver write through a typealias, associatedtype, generic parameter, local
type or a `Self`-qualified path names a type the corpus type index cannot see,
so the old code resolved past it to an unrelated same-named type. The extractor
now rejects such a write at once (a sticky `scopes[name] = None`, the same mark
as two conflicting writes): the in-file bare-label bind and the corpus resolver
bind nothing for the name, and nothing is parked. Each input below bound a
wrong edge before this change; the plain-struct controls and the cache round
trip are guards.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.extract import extract, extract_swift

# Callees declared only here: the call in M.swift goes through the corpus resolver.
LIB = (
    "protocol P { func go() }\n"
    "struct Other { func go() {} }\n"
    "struct Box { struct State { func go() {} } }\n"
    "struct State { func go() {} }\n"
)

# name -> (M.swift source, Lib.swift needed, labels of the callers to check)
CASES = {
    "qualified_typealias": (
        "struct A {\n"
        "    struct Box { typealias State = Other }\n"
        "    func a(_ x: Box.State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        True, [".a()"]),
    "plain_typealias": (
        "struct A {\n"
        "    typealias State = Other\n"
        "    func a(_ x: State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        True, [".a()"]),
    "associatedtype": (
        "protocol A { associatedtype State: P }\n"
        "extension A {\n"
        "    func a(_ x: State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        True, [".a()"]),
    "local_struct_in_body": (
        "struct A {\n"
        "    func a() {\n"
        "        struct State { func go() {} }\n"
        "        let x = State()\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        True, [".a()"]),
    # The wrong edge was B.b -> A.State.go through the in-file bare label.
    "self_qualified_path": (
        "struct State { func go() {} }\n"
        "struct A {\n"
        "    struct State { func go() {} }\n"
        "    func a(_ x: Self.State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
        "struct B {\n"
        "    func b(_ x: State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".b()"]),
    "function_generic_prefix": (
        "protocol P { func go() }\n"
        "struct Box { struct State { func go() {} } }\n"
        "protocol Q { associatedtype State: P }\n"
        "struct A {\n"
        "    func a<Box: Q>(_ x: Box.State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
        "struct B {\n"
        "    func b(_ x: Box.State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "function_generic_prefix_single_write": (
        "protocol P { func go() }\n"
        "struct Box { struct State { func go() {} } }\n"
        "protocol Q { associatedtype State: P }\n"
        "struct A {\n"
        "    func a<Box: Q>(_ x: Box.State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "type_generic_optional": (
        "protocol P { func go() }\n"
        "struct State { func go() {} }\n"
        "struct A<State: P> {\n"
        "    func a(_ x: State?) {\n"
        "        x?.go()\n"
        "    }\n"
        "}\n"
        "struct B {\n"
        "    func b(_ x: State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "type_generic_single_write": (
        "protocol P { func go() }\n"
        "struct State { func go() {} }\n"
        "struct A<State: P> {\n"
        "    func a(_ x: State) {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    # A rejected upper-cased variable is not the type `X`: no `A.a -> X.go`,
    # no `references` to `X`, no parked call.
    "upper_param_type_with_go": (
        "struct X { func go() {} }\n"
        "struct Other { func go() {} }\n"
        "struct A {\n"
        "    typealias State = Other\n"
        "    func a(_ X: State) {\n"
        "        X.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "upper_param_type_without_go": (
        "struct X {}\n"
        "struct Other { func go() {} }\n"
        "struct A {\n"
        "    typealias State = Other\n"
        "    func a(_ X: State) {\n"
        "        X.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "upper_param_no_type": (
        "struct Other { func go() {} }\n"
        "struct A {\n"
        "    typealias State = Other\n"
        "    func a(_ X: State) {\n"
        "        X.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    # Binding sites the receiver table does not read.
    "typed_local": (
        "protocol P { func go() }\n"
        "struct State { func go() {} }\n"
        "struct A<State: P> {\n"
        "    func a(_ v: State) {\n"
        "        let x: State = v\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "typed_closure_param": (
        "protocol P { func go() }\n"
        "struct State { func go() {} }\n"
        "struct A<State: P> {\n"
        "    func a(_ v: [State]) {\n"
        "        v.forEach { (x: State) in\n"
        "            x.go()\n"
        "        }\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    "multi_binding_property": (
        "protocol P { func go() }\n"
        "struct State { func go() {} }\n"
        "struct A<State: P> {\n"
        "    var a: State, x: State\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".run()"]),
    "file_scope_binding": (
        "struct Other { func go() {} }\n"
        "struct State { func go() {} }\n"
        "struct A { typealias State = Other }\n"
        "var x: A.State = Other()\n"
        "func useIt() {\n"
        "    x.go()\n"
        "}\n",
        False, ["useIt()"]),
    "generic_factory_local_shadows_param": (
        "protocol P { func go() }\n"
        "protocol Q {\n"
        "    associatedtype R: P\n"
        "    static func make() -> R\n"
        "}\n"
        "struct State { func go() {} }\n"
        "struct A<Box: Q> {\n"
        "    func a(_ x: State) {\n"
        "        let x = Box.make()\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
    # An annotation does not hide an unproven factory initializer.
    "annotated_generic_factory": (
        "protocol P { func go() }\n"
        "protocol Q { static func make() -> any P }\n"
        "struct State: P { func go() {} }\n"
        "struct A<Box: Q> {\n"
        "    func a() {\n"
        "        let x: any P = Box.make()\n"
        "        x.go()\n"
        "    }\n"
        "}\n",
        False, [".a()"]),
}


def _receiver(case: str) -> str:
    return "X" if case.startswith("upper_param_") else "x"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _run(files: list[Path], tmp_path: Path) -> dict:
    return extract(files, cache_root=tmp_path / "cache", root=tmp_path / "src", parallel=False)


def _corpus(tmp_path: Path, source: str, with_lib: bool) -> tuple[list[Path], Path]:
    base = tmp_path / "src"
    main = _write(base / "M.swift", source)
    files = [main]
    if with_lib:
        files.insert(0, _write(base / "Lib.swift", LIB))
    return files, main


def _call_lines(source: str) -> set[str]:
    # The lines of the receiver's `.go()` calls (never a `func go()` declaration).
    return {
        f"L{i}" for i, line in enumerate(source.splitlines(), start=1)
        if ".go()" in line and "func " not in line
    }


def _callers(result: dict, label: str, main: Path) -> list[dict]:
    return [
        n for n in result["nodes"]
        if n.get("label") == label and str(n.get("source_file", "")).endswith(main.name)
    ]


@pytest.mark.parametrize("case", sorted(CASES))
def test_unproven_receiver_type_binds_nothing(tmp_path: Path, case: str):
    source, with_lib, caller_labels = CASES[case]
    files, main = _corpus(tmp_path, source, with_lib)
    result = _run(files, tmp_path)

    for label in caller_labels:
        _assert_binds_nothing(result, case, label, main, source)


def _assert_binds_nothing(result: dict, case: str, label: str, main: Path, source: str) -> None:
    # A rejected receiver binds nothing at all: no `calls`, no `references` on the
    # call line, no parked call.
    lines = _call_lines(source)
    callers = _callers(result, label, main)
    assert callers, f"{case}: caller {label} not extracted"
    for caller in callers:
        wrong = [
            e for e in result["edges"]
            if e.get("source") == caller["id"]
            and e.get("relation") in ("calls", "references")
            and e.get("source_location") in lines
        ]
        assert not wrong, f"{case}: {label} .go() bound {wrong}"
        parked = (caller.get("metadata") or {}).get("unresolved_calls") or []
        assert not [p for p in parked if isinstance(p, dict) and p.get("callee") == "go"], (
            f"{case}: {label} parked .go(): {parked}"
        )


@pytest.mark.parametrize("case", sorted(CASES))
def test_unproven_receiver_write_is_recorded_as_unknown(tmp_path: Path, case: str):
    # The rejection is a fact of the per-file result, scopes-only files included
    # (a rejected generic parameter leaves the table empty).
    source, with_lib, _labels = CASES[case]
    _files, main = _corpus(tmp_path, source, with_lib)
    table = extract_swift(main).get("swift_type_table")

    receiver = _receiver(case)
    assert table is not None
    assert receiver in table["scopes"] and table["scopes"][receiver] is None


def test_plain_struct_receiver_still_binds_same_file(tmp_path: Path):
    source = (
        "struct A { func go() {} }\n"
        "struct C {\n"
        "    var x: A\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    )
    files, main = _corpus(tmp_path, source, False)
    result = _run(files, tmp_path)

    by_id = {n["id"]: n for n in result["nodes"]}
    a_go = {
        e["target"] for e in result["edges"]
        if e.get("relation") == "method" and by_id.get(e["source"], {}).get("label") == "A"
    }
    run = _callers(result, ".run()", main)
    assert len(run) == 1 and len(a_go) == 1
    assert any(
        e.get("source") == run[0]["id"] and e.get("relation") == "calls"
        and e.get("target") in a_go
        for e in result["edges"]
    )


def test_plain_struct_receiver_still_binds_cross_file(tmp_path: Path):
    base = tmp_path / "src"
    lib = _write(base / "A.swift", "struct A { func go() {} }\n")
    main = _write(base / "M.swift", (
        "struct C {\n"
        "    var x: A\n"
        "    func run() {\n"
        "        x.go()\n"
        "    }\n"
        "}\n"
    ))
    result = _run([lib, main], tmp_path)

    by_id = {n["id"]: n for n in result["nodes"]}
    a_go = {
        e["target"] for e in result["edges"]
        if e.get("relation") == "method" and by_id.get(e["source"], {}).get("label") == "A"
    }
    run = _callers(result, ".run()", main)
    assert len(run) == 1 and len(a_go) == 1
    assert any(
        e.get("source") == run[0]["id"] and e.get("relation") == "calls"
        and e.get("target") in a_go
        for e in result["edges"]
    )


def _cached_payloads(cache: Path) -> list[tuple[Path, dict]]:
    payloads = []
    for path in cache.rglob("*.json"):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(payload, dict) and isinstance(payload.get("swift_type_table"), dict):
            payloads.append((path, payload))
    return payloads


def test_rejection_survives_cache_round_trip(tmp_path: Path):
    # A scopes-only result (the generic-parameter write is rejected, the table is
    # empty) and a single-write typealias result keep their None through the AST
    # cache, and the cached second run binds and parks nothing either.
    source, _with_lib, _labels = CASES["type_generic_single_write"]
    alias_source, _with_lib, _labels = CASES["plain_typealias"]
    base = tmp_path / "src"
    lib = _write(base / "Lib.swift", LIB)
    generic = _write(base / "M.swift", source)
    alias = _write(base / "N.swift", alias_source)
    files = [lib, generic, alias]

    first = _run(files, tmp_path)
    payloads = _cached_payloads(tmp_path / "cache")
    tables = [payload["swift_type_table"] for _path, payload in payloads]
    unknown = [t for t in tables if (t.get("scopes") or {}).get("x", "") is None]
    assert len(unknown) == 2, tables
    assert any(not t.get("table") for t in unknown), "scopes-only result not cached"
    # Mark the cached entries: the second run must replay them, not re-extract.
    for path, payload in payloads:
        sentinel = dict(payload["nodes"][0], id=f"cache_sentinel_{path.stem}",
                        label="CacheSentinel")
        payload["nodes"].append(sentinel)
        path.write_text(json.dumps(payload), encoding="utf-8")

    second = _run(files, tmp_path)

    assert len([n for n in second["nodes"] if n.get("label") == "CacheSentinel"]) == 2, (
        "the second run did not read the cached entries"
    )

    def _edges(result: dict) -> set[tuple]:
        return {
            (e.get("source"), e.get("target"), e.get("relation"), e.get("source_location"))
            for e in result["edges"]
        }

    assert _edges(second) == _edges(first)
    for result in (first, second):
        for main, src in ((generic, source), (alias, alias_source)):
            _assert_binds_nothing(result, "round trip", ".a()", main, src)
