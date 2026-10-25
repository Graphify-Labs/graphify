"""Same-file Swift constructor calls to nested types bind to the caller's own type.

The extractor's bare-label map holds one node per label, so `State()` inside
`A.runA()` and inside `B.runB()` used to bind to one `State`. A label that names
a nested type, or 2+ types of the file, now stays a raw call and extract() binds
it through the caller's lexical scope (INFERRED, `context == "constructor"`).
A unique top-level type keeps the extractor's EXTRACTED same-file binding.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_id(result: dict, label: str) -> str:
    matches = [n["id"] for n in result["nodes"] if n.get("label") == label]
    assert len(matches) == 1, (label, matches)
    return matches[0]


def _parent_label(result: dict, nid: str) -> str:
    labels = {n["id"]: n.get("label", "") for n in result["nodes"]}
    parents = [
        labels.get(e["source"], "") for e in result["edges"]
        if e.get("relation") == "contains" and e.get("target") == nid
    ]
    assert len(parents) == 1, (nid, parents)
    return parents[0]


def _calls_from(result: dict, caller_nid: str) -> list[dict]:
    return [
        e for e in result["edges"]
        if e.get("relation") == "calls" and e.get("source") == caller_nid
    ]


def test_same_file_nested_constructor_binds_own_type(tmp_path: Path):
    src = _write(tmp_path / "src/Features.swift", (
        "struct A {\n"
        "    struct State {}\n"
        "    func runA() {\n"
        "        State()\n"
        "    }\n"
        "}\n"
        "\n"
        "struct B {\n"
        "    struct State {}\n"
        "    func runB() {\n"
        "        State()\n"
        "    }\n"
        "}\n"
    ))
    result = extract([src], cache_root=tmp_path / "cache")

    state_nids = [n["id"] for n in result["nodes"] if n.get("label") == "State"]
    assert len(set(state_nids)) == 2, state_nids

    for caller_label, owner_label in ((".runA()", "A"), (".runB()", "B")):
        calls = _calls_from(result, _node_id(result, caller_label))
        assert len(calls) == 1, (caller_label, calls)
        edge = calls[0]
        assert edge["target"] in state_nids
        assert _parent_label(result, edge["target"]) == owner_label
        assert edge["confidence"] == "INFERRED"
        assert edge.get("context") == "constructor"

    run_a_target = _calls_from(result, _node_id(result, ".runA()"))[0]["target"]
    run_b_target = _calls_from(result, _node_id(result, ".runB()"))[0]["target"]
    assert run_a_target != run_b_target


def test_same_file_top_level_constructor_stays_extracted(tmp_path: Path):
    src = _write(tmp_path / "src/Foo.swift", (
        "struct Foo {}\n"
        "\n"
        "func make() {\n"
        "    Foo()\n"
        "}\n"
    ))
    result = extract([src], cache_root=tmp_path / "cache")

    calls = _calls_from(result, _node_id(result, "make()"))
    assert len(calls) == 1, calls
    edge = calls[0]
    assert edge["target"] == _node_id(result, "Foo")
    assert edge["confidence"] == "EXTRACTED"
    assert edge.get("context") == "call"


_NESTED_STATE = (
    "struct A {\n"
    "    struct State {}\n"
    "    func runA() {\n"
    "        State()\n"
    "    }\n"
    "}\n"
)
_FREE_STATE = "func State() {}\n"
_FILE_SCOPE_CALLER = "func make() {\n    State()\n}\n"



@pytest.mark.parametrize("free_first", [False, True], ids=["type_first", "function_first"])
def test_nested_constructor_hides_same_named_free_function(tmp_path: Path, free_first: bool):
    # Inside `A`, the nested `A.State` hides a top-level
    # `func State()`, whichever is declared last in the file; a file-scope
    # caller still calls the free function.
    parts = [_FREE_STATE, _NESTED_STATE] if free_first else [_NESTED_STATE, _FREE_STATE]
    src = _write(tmp_path / "src/Mixed.swift", "\n".join(parts + [_FILE_SCOPE_CALLER]))
    result = extract([src], cache_root=tmp_path / "cache")

    type_nid = _node_id(result, "State")
    func_nid = _node_id(result, "State()")

    run_a_calls = _calls_from(result, _node_id(result, ".runA()"))
    assert len(run_a_calls) == 1, run_a_calls
    assert run_a_calls[0]["target"] == type_nid
    assert run_a_calls[0]["confidence"] == "INFERRED"
    assert run_a_calls[0].get("context") == "constructor"

    # A file-scope caller never binds to the nested type. When the free
    # function is declared last it is the bare-label hit and keeps its
    # EXTRACTED edge; declared first, the bare-label map holds the type, the
    # call is deferred and the lexical lookup finds no file-scope `State`
    # type: no edge rather than a wrong one.
    make_calls = _calls_from(result, _node_id(result, "make()"))
    assert all(e["target"] != type_nid for e in make_calls), make_calls
    if not free_first:
        assert len(make_calls) == 1, make_calls
        assert make_calls[0]["target"] == func_nid
        assert make_calls[0]["confidence"] == "EXTRACTED"
