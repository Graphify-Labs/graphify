"""Extraction coverage for solidity."""


from __future__ import annotations





import sys


from pathlib import Path





from graphify.extract import extract





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.sol"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


def test_solidity_contract_members_and_calls_are_extracted(tmp_path):
    source = tmp_path / "Counter.sol"
    source.write_text(
        "pragma solidity ^0.8.0;\n"
        "contract Counter {\n"
        "  uint public count;\n"
        "  event Counted(uint value);\n"
        "  function increment() public { record(); }\n"
        "  function record() internal {}\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"Counter", "increment()", "record()", "Counted"} <= labels
    assert ("increment()", "record()") in _edge_labels(result, "calls")


def test_solidity_free_functions_and_their_calls_are_extracted(tmp_path):
    # File-level (free) functions — legal since Solidity 0.7 — live outside any
    # contract. Before the fix the extractor only descended into named type
    # declarations, so both free functions and the call between them vanished.
    source = tmp_path / "Utils.sol"
    source.write_text(
        "pragma solidity ^0.8.0;\n"
        "function halve(uint x) pure returns (uint) { return x / 2; }\n"
        "function quarter(uint x) pure returns (uint) { return halve(halve(x)); }\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {"halve()", "quarter()"} <= labels
    assert ("quarter()", "halve()") in _edge_labels(result, "calls")


def test_solidity_types_imports_inheritance_overloads_and_modifiers(tmp_path):
    (tmp_path / "Base.sol").write_text(
        "contract Base { function baseRun() internal {} }\n", encoding="utf-8"
    )
    (tmp_path / "Lib.sol").write_text(
        "library Lib { function touch(uint value) internal {} }\n", encoding="utf-8"
    )
    source = tmp_path / "Counter.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        'import "./Base.sol";\n'
        'import "./Lib.sol";\n'
        "contract Counter is Base {\n"
        " using Lib for uint;\n"
        " struct Item { uint value; }\n"
        " enum State { On, Off }\n"
        " event Changed(uint value);\n"
        " error Failed();\n"
        " uint public count;\n"
        " modifier guarded() { _; }\n"
        " constructor() {}\n"
        " function run() public guarded { record(); this.record(1); }\n"
        " function record() internal {}\n"
        " function record(uint value) internal {}\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(
        [source, tmp_path / "Base.sol", tmp_path / "Lib.sol"], cache_root=tmp_path
    )

    labels = [node["label"] for node in result["nodes"]]
    assert {
        "Counter", "Base", "Lib", "Item", "value", "State", "On", "Off",
        "Changed", "Failed", "count", "guarded()", "constructor()", "run()",
    } <= set(labels)
    assert labels.count("record()") == 2
    assert ("Counter", "Base") in _edge_labels(result, "inherits")
    assert ("run()", "guarded()") in _edge_labels(result, "uses")
    assert len([edge for edge in result["edges"] if edge["relation"] == "imports_from"]) == 2


def test_solidity_enum_values_emit_case_of_not_contains(tmp_path):
    """A Solidity enum value is a discriminant case, so it must get a `case_of`
    edge like every other language with enums (Java #1719, C#, Swift, Rust,
    VB.NET), not the `contains` edge used for real declared members. Solidity
    was routing enum values through the same `contains` path as struct fields.
    The relation also matters to resolution: `case_of` targets are excluded
    from constructor binding, so an enum value named like a type can no longer
    be mistaken for one.
    """
    source = tmp_path / "Status.sol"
    source.write_text(
        "pragma solidity ^0.8.0;\n"
        "contract Order {\n"
        "  enum Status { Pending, Shipped, Delivered }\n"
        "  struct Point { uint x; uint y; }\n"
        "  Status public status;\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    case_of = _edge_labels(result, "case_of")
    contains = _edge_labels(result, "contains")
    # Each enum value hangs off its enum via case_of, not contains.
    assert ("Status", "Pending") in case_of
    assert ("Status", "Shipped") in case_of
    assert ("Status", "Delivered") in case_of
    assert ("Status", "Pending") not in contains
    # A real struct field is a declaration, not a case: it keeps `contains`.
    assert ("Point", "x") in contains
    assert ("Point", "x") not in case_of


def test_solidity_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'run()', 'helper()', 'Sample'} <= labels
    assert ('run()', 'helper()') in _edge_labels(result, "calls")


def test_solidity_malformed_tail_comments_and_strings_do_not_create_phantoms(tmp_path):
    source = tmp_path / 'Broken.sol'
    source.write_text('contract Kept { function valid() public {} string constant text = "function Ghost()"; /* function Hidden() {} */', encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    labels = {node["label"].casefold() for node in result["nodes"]}
    assert 'valid()' in labels
    assert labels.isdisjoint({'ghost()', 'hidden()'})


def test_solidity_missing_parser_reports_install_hint(tmp_path, monkeypatch, capsys):
    source = tmp_path / "missing.sol"
    source.write_text('contract Missing {}\n', encoding="utf-8")
    monkeypatch.setitem(sys.modules, 'tree_sitter_solidity', None)

    result = extract([source], cache_root=tmp_path)

    assert result["nodes"] == []
    assert 'pip install "graphifyy[solidity]"' in capsys.readouterr().err
