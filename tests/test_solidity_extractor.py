"""Extraction coverage for solidity."""


from __future__ import annotations





import importlib.util as _ilu
import sys


from pathlib import Path





import pytest

from graphify.extract import extract

# tree-sitter-solidity is an optional extra, not installed by a default
# `uv sync`. Skip the grammar tests when it is absent; the missing-parser
# test below still runs because it simulates the absent grammar itself.
_needs_solidity = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_solidity") is None,
    reason="tree-sitter-solidity not installed (optional [solidity] extra)",
)





FIXTURE = Path(__file__).parent / "fixtures" / "new_languages" / "sample.sol"





def _edge_labels(result: dict, relation: str) -> set[tuple[str, str]]:
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    return {
        (labels.get(edge["source"], edge["source"]), labels.get(edge["target"], edge["target"]))
        for edge in result["edges"]
        if edge["relation"] == relation
    }


@_needs_solidity
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


@_needs_solidity
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


@_needs_solidity
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
    # Control: the single-library `using Lib for uint;` form must keep working
    # exactly as before while the using_alias form below is fixed.
    assert ("Counter", "Lib") in _edge_labels(result, "uses")
    assert len([edge for edge in result["edges"] if edge["relation"] == "imports_from"]) == 2


@_needs_solidity
def test_solidity_parent_dir_import_targets_the_real_file(tmp_path):
    utils = tmp_path / "contracts" / "utils"
    proxy = tmp_path / "contracts" / "proxy"
    utils.mkdir(parents=True)
    proxy.mkdir(parents=True)
    errors = utils / "Errors.sol"
    errors.write_text("library Errors { error FailedCall(); }\n", encoding="utf-8")
    clones = proxy / "Clones.sol"
    clones.write_text(
        'import {Errors} from "../utils/Errors.sol";\n'
        "library Clones { function clone() internal {} }\n",
        encoding="utf-8",
    )

    result = extract([clones, errors], cache_root=tmp_path, root=tmp_path)

    file_ids = {
        node["id"]: node["source_file"]
        for node in result["nodes"]
        if node.get("source_file") and node["label"] == Path(node["source_file"]).name
    }
    imports = [edge for edge in result["edges"] if edge["relation"] == "imports_from"]
    assert len(imports) == 1
    # `../utils/Errors.sol` from contracts/proxy/ is contracts/utils/Errors.sol,
    # not a dangling contracts/proxy/utils/errors.sol stub.
    assert Path(file_ids.get(imports[0]["target"], "")).as_posix().endswith("contracts/utils/Errors.sol")


@_needs_solidity
def test_solidity_using_free_function_set_emits_uses_edges(tmp_path):
    """`using {f1, f2} for T;` (free functions bound as members, legal since
    0.8.13) wraps each name in its own `using_alias` child instead of putting
    it directly under the using_directive the way `using Lib for T;` does.
    The extractor only looked at direct children, so it saw nothing to read
    and silently dropped the whole directive -- no edge at all, for either
    function."""
    source = tmp_path / "Counter.sol"
    source.write_text(
        "pragma solidity ^0.8.13;\n"
        "function freeAdd(uint a, uint b) pure returns (uint) { return a + b; }\n"
        "function freeSub(uint a, uint b) pure returns (uint) { return a - b; }\n"
        "contract Counter {\n"
        "  using {freeAdd, freeSub} for uint;\n"
        "  uint public count;\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    uses = _edge_labels(result, "uses")
    assert ("Counter", "freeAdd()") in uses
    assert ("Counter", "freeSub()") in uses


@_needs_solidity
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


def _calls_to(result: dict, kind: str) -> set[tuple[str, str, str]]:
    """(caller, target, target file name) for `calls` edges into an event/error."""
    nodes = {node["id"]: node for node in result["nodes"]}
    return {
        (nodes[e["source"]]["label"], nodes[e["target"]]["label"],
         Path(nodes[e["target"]].get("source_file", "")).name)
        for e in result["edges"]
        if e["relation"] == "calls" and e["source"] in nodes and e["target"] in nodes
        and nodes[e["target"]].get("metadata", {}).get("kind") == kind
    }


@_needs_solidity
def test_solidity_emit_revert_and_require_call_events_and_errors_of_the_same_contract(tmp_path):
    # tree-sitter-solidity parses `emit` / `revert` as statements, not
    # call_expressions, so neither linked to the declaration (OpenZeppelin:
    # 0 of 522 compiler-resolved uses), and an error's `error_parameter`s were
    # not counted, so `require(c, Err(x))` never matched it either.
    source = tmp_path / "Vault.sol"
    source.write_text(
        "pragma solidity ^0.8.20;\n"
        "contract Vault {\n"
        "    event Withdrawn(address who, uint256 amount);\n"
        "    error NotOwner(address caller);\n"
        "    error Paused();\n"
        "    address owner;\n"
        "    function withdraw(uint256 amount) external {\n"
        "        if (msg.sender != owner) revert NotOwner(msg.sender);\n"
        "        emit Withdrawn(msg.sender, amount);\n"
        "    }\n"
        "    function check(bool on) external view {\n"
        "        require(!on, Paused());\n"
        "        revert();\n"
        '        revert("plain");\n'
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([source], cache_root=tmp_path)

    assert _calls_to(result, "error") == {
        ("withdraw()", "NotOwner", "Vault.sol"),
        ("check()", "Paused", "Vault.sol"),
    }
    assert _calls_to(result, "event") == {("withdraw()", "Withdrawn", "Vault.sol")}


@_needs_solidity
def test_solidity_emit_and_revert_bind_events_and_errors_of_a_base_contract(tmp_path):
    (tmp_path / "Base.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "interface IVault { event Deposited(address who, uint256 amount); }\n"
        "contract Base is IVault { error ZeroAmount(); error TooLarge(uint256 max); }\n",
        encoding="utf-8",
    )
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {Base} from "./Base.sol";\n'
        "contract Vault is Base {\n"
        "    function deposit() external payable {\n"
        "        if (msg.value == 0) revert ZeroAmount();\n"
        "        require(msg.value < 10, TooLarge(10));\n"
        "        emit Deposited(msg.sender, msg.value);\n"
        "        revert ZeroAmount(1);\n"  # wrong arity: no such error
        "    }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _calls_to(result, "error") == {
        ("deposit()", "ZeroAmount", "Base.sol"),
        ("deposit()", "TooLarge", "Base.sol"),
    }
    assert _calls_to(result, "event") == {("deposit()", "Deposited", "Base.sol")}


@_needs_solidity
def test_solidity_qualified_revert_and_emit_bind_through_the_imported_type(tmp_path):
    (tmp_path / "Errors.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Errors { error InsufficientBalance(uint256 have, uint256 want); }\n"
        "interface Events { event Moved(uint256 amount); }\n",
        encoding="utf-8",
    )
    # Same library name in a file Vault.sol does not import: never a candidate.
    (tmp_path / "Other.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Errors { error InsufficientBalance(uint256 have, uint256 want); }\n",
        encoding="utf-8",
    )
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {Errors, Events} from "./Errors.sol";\n'
        "contract Vault {\n"
        "    function withdraw(uint256 have, uint256 amount) external {\n"
        "        if (have < amount) revert Errors.InsufficientBalance(have, amount);\n"
        "        emit Events.Moved(amount);\n"
        "        revert Missing.InsufficientBalance(have, amount);\n"
        "    }\n"
        "}\n",
        encoding="utf-8",
    )
    # Two imported files both declare `Errors`: ambiguous, so fail closed.
    (tmp_path / "Dup.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Errors { error InsufficientBalance(uint256 have, uint256 want); }\n",
        encoding="utf-8",
    )
    (tmp_path / "Ambiguous.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import "./Errors.sol";\n'
        'import "./Dup.sol";\n'
        "contract Ambiguous {\n"
        "    function f() external { revert Errors.InsufficientBalance(1, 2); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _calls_to(result, "error") == {("withdraw()", "InsufficientBalance", "Errors.sol")}
    assert _calls_to(result, "event") == {("withdraw()", "Moved", "Errors.sol")}


def _function_calls(result: dict) -> set[tuple[str, str, str]]:
    """(caller, target, target file name) for `calls` edges into a function."""
    return _calls_to(result, "function")


_MATH_LIB = (
    "pragma solidity ^0.8.20;\n"
    "library MathLib {\n"
    "    function max(uint256 a, uint256 b) internal pure returns (uint256) { return a > b ? a : b; }\n"
    "    function clamp(uint256 x, uint256 hi) internal pure returns (uint256) {\n"
    "        return MathLib.max(x, hi) == x ? hi : x;\n"
    "    }\n"
    "}\n"
)


@_needs_solidity
def test_solidity_library_call_binds_through_a_named_import(tmp_path):
    # Every `Lib.f()` was parked as a bare member call, which the shared
    # cross-file pass drops, so no library call got an edge (OpenZeppelin:
    # 0 of 208 compiler-resolved library calls).
    (tmp_path / "MathLib.sol").write_text(_MATH_LIB, encoding="utf-8")
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {MathLib} from "./MathLib.sol";\n'
        "contract Vault {\n"
        "    uint256 public cap;\n"
        "    function setCap(uint256 newCap) external { cap = MathLib.max(newCap, 1); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert ("setCap()", "max()", "MathLib.sol") in _function_calls(result)


@_needs_solidity
def test_solidity_library_call_binds_through_a_whole_file_import(tmp_path):
    (tmp_path / "TimeLib.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library TimeLib { function now48() internal view returns (uint48) { return uint48(block.timestamp); } }\n",
        encoding="utf-8",
    )
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import "./TimeLib.sol";\n'
        "contract Vault {\n"
        "    uint48 public updatedAt;\n"
        "    function touch() external { updatedAt = TimeLib.now48(); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _function_calls(result) == {("touch()", "now48()", "TimeLib.sol")}


@_needs_solidity
def test_solidity_qualified_call_inside_the_library_itself(tmp_path):
    source = tmp_path / "MathLib.sol"
    source.write_text(_MATH_LIB, encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    assert _function_calls(result) == {("clamp()", "max()", "MathLib.sol")}


@_needs_solidity
def test_solidity_library_call_binds_through_an_import_alias(tmp_path):
    (tmp_path / "MathLib.sol").write_text(_MATH_LIB, encoding="utf-8")
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {MathLib as M} from "./MathLib.sol";\n'
        "contract Vault {\n"
        "    function top(uint256 a) external pure returns (uint256) { return M.max(a, 1); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert ("top()", "max()", "MathLib.sol") in _function_calls(result)


@_needs_solidity
def test_solidity_negated_library_call_binds(tmp_path):
    # tree-sitter-solidity parses `!Lib.f(x)` as a call of the member
    # `(!Lib).f`, so the receiver read as `!MathLib` named no type.
    (tmp_path / "MathLib.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library MathLib { function isZero(uint256 a) internal pure returns (bool) { return a == 0; } }\n",
        encoding="utf-8",
    )
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {MathLib} from "./MathLib.sol";\n'
        "contract Vault {\n"
        "    function check(uint256 a) external pure { if (!MathLib.isZero(a)) revert(); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _function_calls(result) == {("check()", "isZero()", "MathLib.sol")}


@_needs_solidity
def test_solidity_library_call_from_a_free_function(tmp_path):
    (tmp_path / "MathLib.sol").write_text(_MATH_LIB, encoding="utf-8")
    (tmp_path / "Utils.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {MathLib} from "./MathLib.sol";\n'
        "function atLeastOne(uint256 a) pure returns (uint256) { return MathLib.max(a, 1); }\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert ("atLeastOne()", "max()", "MathLib.sol") in _function_calls(result)


@_needs_solidity
def test_solidity_require_with_a_qualified_error_binds_the_library_error(tmp_path):
    (tmp_path / "Errors.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Errors { error TooSmall(uint256 got); }\n",
        encoding="utf-8",
    )
    (tmp_path / "Vault.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {Errors} from "./Errors.sol";\n'
        "contract Vault {\n"
        "    function deposit(uint256 v) external pure { require(v > 1, Errors.TooSmall(v)); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _calls_to(result, "error") == {("deposit()", "TooSmall", "Errors.sol")}


@_needs_solidity
def test_solidity_library_call_fails_closed_when_ambiguous_or_not_a_type(tmp_path):
    (tmp_path / "A.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Dup { function f() internal pure {} }\n"
        "library Over {\n"
        "    function g(uint256 a) internal pure {}\n"
        "    function g(int256 a) internal pure {}\n"
        "    function h(uint256 a) internal pure {}\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "B.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Dup { function f() internal pure {} }\n",
        encoding="utf-8",
    )
    # Declares `Hidden`, but Caller.sol does not import it.
    (tmp_path / "C.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "library Hidden { function k() internal pure {} }\n",
        encoding="utf-8",
    )
    (tmp_path / "Caller.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import "./A.sol";\n'
        'import "./B.sol";\n'
        "contract Caller {\n"
        "    function run(uint256 x) external {\n"
        "        Dup.f();\n"  # two imported files declare Dup
        "        Over.g(x);\n"  # two overloads of the same arity
        "        Over.h(x, x);\n"  # no h with two parameters
        "        Hidden.k();\n"  # not imported
        "        x.h(x);\n"  # a value receiver, not a type
        "    }\n"
        "    function ok(uint256 x) external { Over.h(x); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _function_calls(result) == {("ok()", "h()", "A.sol")}


@_needs_solidity
def test_solidity_fixture_uses_normal_extract_path(tmp_path):
    result = extract([FIXTURE], cache_root=tmp_path)

    labels = {node["label"] for node in result["nodes"]}
    assert {'run()', 'helper()', 'Sample'} <= labels
    assert ('run()', 'helper()') in _edge_labels(result, "calls")


@_needs_solidity
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
