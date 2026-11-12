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


_ROLES = (
    "pragma solidity ^0.8.20;\n"
    "contract Roles {\n"
    "    event RoleGranted(bytes32 role, address account);\n"
    "    function hasRole(bytes32 role, address account) public view returns (bool) { return false; }\n"
    "    function grantRole(bytes32 role, address account) public { _grantRole(role, account); }\n"
    "    function _grantRole(bytes32 role, address account) internal returns (bool) {\n"
    "        if (hasRole(role, account)) return false;\n"
    "        emit RoleGranted(role, account);\n"
    "        return true;\n"
    "    }\n"
    "}\n"
)


_IERC20 = (
    "pragma solidity ^0.8.20;\n"
    "interface IERC20 {\n"
    "    function transfer(address to, uint256 value) external returns (bool);\n"
    "    function balanceOf(address who) external view returns (uint256);\n"
    "}\n"
)
# Implements IERC20: a call on an IERC20 value must not be guessed to land here.
_TOKEN = (
    "pragma solidity ^0.8.20;\n"
    'import {IERC20} from "./IERC20.sol";\n'
    "contract Token is IERC20 {\n"
    "    function transfer(address to, uint256 value) external returns (bool) { return true; }\n"
    "    function balanceOf(address who) external view returns (uint256) { return 0; }\n"
    "}\n"
)


def _calls_by_line(result: dict) -> set[tuple[str, str, str, str]]:
    """(caller, caller line, target, target line) for every `calls` edge."""
    nodes = {node["id"]: node for node in result["nodes"]}
    return {
        (nodes[e["source"]]["label"], nodes[e["source"]]["source_location"],
         nodes[e["target"]]["label"], nodes[e["target"]]["source_location"])
        for e in result["edges"]
        if e["relation"] == "calls" and e["source"] in nodes and e["target"] in nodes
    }


@_needs_solidity
def test_solidity_underscore_member_gets_its_own_node_and_calls(tmp_path):
    # make_id drops the leading `_`, so `_grantRole(bytes32,address)` and
    # `grantRole(bytes32,address)` shared one id: `_grantRole` vanished and
    # its calls were credited to `grantRole` (OpenZeppelin: 38 functions).
    source = tmp_path / "Roles.sol"
    source.write_text(_ROLES, encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    functions = {n["label"]: n for n in result["nodes"] if n["metadata"]["kind"] == "function"}
    assert {"grantRole()", "_grantRole()", "hasRole()"} <= set(functions)
    assert functions["grantRole()"]["id"] != functions["_grantRole()"]["id"]
    assert _calls_by_line(result) == {
        ("grantRole()", "L5", "_grantRole()", "L6"),
        ("_grantRole()", "L6", "hasRole()", "L4"),
        ("_grantRole()", "L6", "RoleGranted", "L3"),
    }


@_needs_solidity
def test_solidity_underscore_salt_changes_only_the_clashing_id(tmp_path):
    # Only the `_` spelling is salted, as C# does (#4415): the public name and
    # every member that clashes with nothing keep the id they had.
    source = tmp_path / "Roles.sol"
    source.write_text(_ROLES, encoding="utf-8")

    result = extract([source], cache_root=tmp_path)

    ids = {n["label"]: n["id"] for n in result["nodes"]}
    contract = ids["Roles"]
    assert ids["grantRole()"] == f"{contract}_function_grantrole_2_bytes32_address"
    assert ids["hasRole()"] == f"{contract}_function_hasrole_2_bytes32_address"
    assert ids["RoleGranted"] == f"{contract}_event_rolegranted_rolegranted"
    assert ids["_grantRole()"].startswith(f"{contract}_function_grantrole_2_bytes32_address_")


@_needs_solidity
def test_solidity_underscore_free_function_and_inherited_call_land_right(tmp_path):
    (tmp_path / "Base.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "function _scale(uint256 x) pure returns (uint256) { return x * 2; }\n"
        "function scale(uint256 x) pure returns (uint256) { return _scale(x); }\n"
        "abstract contract Base {\n"
        "    function mint(address to) public { _mint(to); }\n"
        "    function _mint(address to) internal {}\n"
        "}\n",
        encoding="utf-8",
    )
    (tmp_path / "Token.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {Base} from "./Base.sol";\n'
        "contract Token is Base {\n"
        "    function airdrop(address to) external { _mint(to); }\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)

    assert _calls_by_line(result) == {
        ("scale()", "L3", "_scale()", "L2"),
        ("mint()", "L5", "_mint()", "L6"),
        ("airdrop()", "L4", "_mint()", "L6"),
    }


def _typed_receiver_corpus(tmp_path: Path, vault: str) -> dict:
    (tmp_path / "IERC20.sol").write_text(_IERC20, encoding="utf-8")
    (tmp_path / "Token.sol").write_text(_TOKEN, encoding="utf-8")
    (tmp_path / "Vault.sol").write_text(vault, encoding="utf-8")
    return extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)


_SAFE_CAST = (
    "pragma solidity ^0.8.20;\n"
    "library SafeCast {\n"
    "    function toUint48(uint256 value) internal pure returns (uint48) { return uint48(value); }\n"
    "    function toUint48(int256 value) internal pure returns (uint48) { return uint48(uint256(value)); }\n"
    "}\n"
)
_SETS = (
    "pragma solidity ^0.8.20;\n"
    "library EnumerableSet {\n"
    "    struct AddressSet { address[] values; }\n"
    "    struct UintSet { uint256[] values; }\n"
    "    function add(AddressSet storage set, address value) internal returns (bool) { return true; }\n"
    "    function add(UintSet storage set, uint256 value) internal returns (bool) { return true; }\n"
    "}\n"
)


def _using_corpus(tmp_path: Path, files: dict[str, str]) -> dict:
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    return extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)


@_needs_solidity
def test_solidity_call_on_a_typed_state_variable_binds_the_interface_method(tmp_path):
    # `token.transfer()` was parked as a qualified call on the type `token`,
    # which names no type, so no call on a typed value got an edge
    # (OpenZeppelin: 0 of 74 compiler-resolved calls).
    result = _typed_receiver_corpus(tmp_path, (
        "pragma solidity ^0.8.20;\n"
        'import {IERC20} from "./IERC20.sol";\n'
        "contract Vault {\n"
        "    IERC20 public token;\n"
        "    function pay(address to, uint256 v) external { token.transfer(to, v); }\n"
        "}\n"
    ))

    # The interface's own declaration, not Token's implementation.
    assert _function_calls(result) == {("pay()", "transfer()", "IERC20.sol")}


@_needs_solidity
def test_solidity_call_on_a_typed_parameter_local_or_return_variable_binds(tmp_path):
    result = _typed_receiver_corpus(tmp_path, (
        "pragma solidity ^0.8.20;\n"
        'import {IERC20} from "./IERC20.sol";\n'
        "contract Vault {\n"
        "    function viaParam(IERC20 t, address to) external { t.transfer(to, 1); }\n"
        "    function viaLocal(address a) external view returns (uint256) {\n"
        "        IERC20 local = IERC20(a);\n"
        "        return local.balanceOf(a);\n"
        "    }\n"
        "    function viaReturn(address a) external returns (IERC20 out) {\n"
        "        out = IERC20(a);\n"
        "        out.transfer(a, 2);\n"
        "    }\n"
        "}\n"
    ))

    assert _function_calls(result) == {
        ("viaParam()", "transfer()", "IERC20.sol"),
        ("viaLocal()", "balanceOf()", "IERC20.sol"),
        ("viaReturn()", "transfer()", "IERC20.sol"),
    }


@_needs_solidity
def test_solidity_call_on_a_type_conversion_binds_through_the_base_contract(tmp_path):
    # `IERC20(a).transfer()` and `Ownable(x).owner()`, with `owner` declared
    # in Ownable's base: walked through the type's linearization.
    (tmp_path / "Base.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "abstract contract OwnableBase { function owner() public view returns (address) { return address(0); } }\n"
        "abstract contract Ownable is OwnableBase {}\n",
        encoding="utf-8",
    )
    result = _typed_receiver_corpus(tmp_path, (
        "pragma solidity ^0.8.20;\n"
        'import {IERC20} from "./IERC20.sol";\n'
        'import {Ownable} from "./Base.sol";\n'
        "contract Vault {\n"
        "    function pay(address a) external { IERC20(a).transfer(a, 1); }\n"
        "    function ownerOf(address x) external view returns (address) { return Ownable(x).owner(); }\n"
        "}\n"
    ))

    assert _function_calls(result) == {
        ("pay()", "transfer()", "IERC20.sol"),
        ("ownerOf()", "owner()", "Base.sol"),
    }


@_needs_solidity
def test_solidity_using_for_binds_a_library_call_on_a_typed_value(tmp_path):
    # `x.toUint48()` calls `SafeCast.toUint48(x)`, but it was parked as a
    # qualified call on a type named `x`, so no `using` call got an edge
    # (OpenZeppelin: 0 of 228 compiler-resolved calls). The overload is the
    # one whose first parameter takes the receiver's type.
    result = _using_corpus(tmp_path, {
        "SafeCast.sol": _SAFE_CAST,
        "Vault.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {SafeCast} from "./SafeCast.sol";\n'
            "contract Vault {\n"
            "    using SafeCast for uint256;\n"
            "    uint48 public at;\n"
            "    function touch(uint x) external { at = x.toUint48(); }\n"
            "}\n"
        ),
    })

    assert _function_calls(result) == {("touch()", "toUint48()", "SafeCast.sol")}
    toUint48 = [n for n in result["nodes"] if n["label"] == "toUint48()"]
    target = next(e["target"] for e in result["edges"] if e["relation"] == "calls")
    assert next(n for n in toUint48 if n["id"] == target)["metadata"]["first_param_type"] == "uint256"


@_needs_solidity
def test_solidity_using_for_binds_on_a_library_struct_through_a_mapping_and_a_base(tmp_path):
    # `using EnumerableSet for EnumerableSet.AddressSet; _set.add(a)`: the
    # struct is `AddressSet` inside the library and `EnumerableSet.AddressSet`
    # outside it; the receiver may be a mapping element or a base contract's
    # state variable.
    result = _using_corpus(tmp_path, {
        "EnumerableSet.sol": _SETS,
        "Base.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {EnumerableSet} from "./EnumerableSet.sol";\n'
            "abstract contract Base { EnumerableSet.AddressSet internal _inherited; }\n"
        ),
        "Roles.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {EnumerableSet} from "./EnumerableSet.sol";\n'
            'import {Base} from "./Base.sol";\n'
            "contract Roles is Base {\n"
            "    using EnumerableSet for EnumerableSet.AddressSet;\n"
            "    EnumerableSet.AddressSet private _set;\n"
            "    mapping(bytes32 => EnumerableSet.AddressSet) private _members;\n"
            "    function direct(address a) external { _set.add(a); }\n"
            "    function element(bytes32 r, address a) external { _members[r].add(a); }\n"
            "    function inherited(address a) external { _inherited.add(a); }\n"
            "}\n"
        ),
    })

    assert _function_calls(result) == {
        ("direct()", "add()", "EnumerableSet.sol"),
        ("element()", "add()", "EnumerableSet.sol"),
        ("inherited()", "add()", "EnumerableSet.sol"),
    }
    lines = {
        next(n for n in result["nodes"] if n["id"] == e["target"])["source_location"]
        for e in result["edges"] if e["relation"] == "calls"
    }
    assert lines == {"L5"}  # add(AddressSet, ..), not add(UintSet, ..)


@_needs_solidity
def test_solidity_using_for_star_and_file_level_directives_bind(tmp_path):
    # `using A for *` attaches every function whose first parameter takes the
    # receiver; a file-level directive applies to every contract and free
    # function of the file. A value type declared in a library reads as
    # `Time.Delay` on both sides.
    result = _using_corpus(tmp_path, {
        "SafeCast.sol": _SAFE_CAST,
        "Time.sol": (
            "pragma solidity ^0.8.20;\n"
            "library Time {\n"
            "    type Delay is uint112;\n"
            "    function get(Delay self) internal pure returns (uint32) { return 0; }\n"
            "}\n"
        ),
        "Vault.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {SafeCast} from "./SafeCast.sol";\n'
            'import {Time} from "./Time.sol";\n'
            "using SafeCast for uint256;\n"
            "function free(uint256 x) pure returns (uint48) { return x.toUint48(); }\n"
            "contract Vault {\n"
            "    using Time for *;\n"
            "    Time.Delay private _delay;\n"
            "    function cast(uint256 x) external pure returns (uint48) { return x.toUint48(); }\n"
            "    function delay() external view returns (uint32) { return _delay.get(); }\n"
            "}\n"
        ),
    })

    assert _function_calls(result) == {
        ("free()", "toUint48()", "SafeCast.sol"),
        ("cast()", "toUint48()", "SafeCast.sol"),
        ("delay()", "get()", "Time.sol"),
    }


@_needs_solidity
def test_solidity_typed_receiver_through_a_reexport_a_base_state_variable_or_a_getter(tmp_path):
    # OpenZeppelin imports IERC20 through ERC20.sol (`import {IERC20} from
    # "../ERC20.sol"`), tests call `hevm.prank()` on a base contract's
    # variable, and `token().clock()` calls on a function's result.
    (tmp_path / "Base.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import {IERC20} from "./IERC20.sol";\n'
        "abstract contract Base {\n"
        "    IERC20 internal constant hevm = IERC20(address(1));\n"
        "    function token() public view returns (IERC20) { return hevm; }\n"
        "}\n",
        encoding="utf-8",
    )
    result = _typed_receiver_corpus(tmp_path, (
        "pragma solidity ^0.8.20;\n"
        'import {Base, IERC20} from "./Base.sol";\n'
        "contract Vault is Base {\n"
        "    function viaBase(address a) external { hevm.transfer(a, 1); }\n"
        "    function viaResult(address a) external view returns (uint256) { return token().balanceOf(a); }\n"
        "    function viaReexport(address a) external { IERC20(a).transfer(a, 3); }\n"
        "}\n"
    ))

    assert _function_calls(result) == {
        ("viaBase()", "transfer()", "IERC20.sol"),
        ("viaResult()", "token()", "Base.sol"),  # the inherited call itself
        ("viaResult()", "balanceOf()", "IERC20.sol"),
        ("viaReexport()", "transfer()", "IERC20.sol"),
    }


@_needs_solidity
def test_solidity_using_function_set_and_global_directive_bind(tmp_path):
    # `using {add} for Price global;` on the type's declaration applies in
    # every file that uses Price; `using {L.twice, half} for uint256;`
    # attaches a library function and a free function.
    result = _using_corpus(tmp_path, {
        "Price.sol": (
            "pragma solidity ^0.8.20;\n"
            "type Price is uint128;\n"
            "using {add, eq as ==} for Price global;\n"
            "function add(Price a, Price b) pure returns (Price) { return a; }\n"
            "function eq(Price a, Price b) pure returns (bool) { return true; }\n"
        ),
        "Math.sol": (
            "pragma solidity ^0.8.20;\n"
            "library L { function twice(uint256 x) internal pure returns (uint256) { return 2 * x; } }\n"
            "function half(uint256 x) pure returns (uint256) { return x / 2; }\n"
        ),
        "Shop.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {Price} from "./Price.sol";\n'
            'import {L, half} from "./Math.sol";\n'
            "contract Shop {\n"
            "    using {L.twice, half} for uint256;\n"
            "    function total(Price a, Price b) external pure returns (Price) { return a.add(b); }\n"
            "    function scale(uint256 x) external pure returns (uint256) { return x.twice().half() + x.half(); }\n"
            "}\n"
        ),
    })

    assert _function_calls(result) == {
        ("total()", "add()", "Price.sol"),
        ("scale()", "twice()", "Math.sol"),
        ("scale()", "half()", "Math.sol"),  # x.half(); x.twice().half() is chained, untyped
    }


@_needs_solidity
def test_solidity_typed_receiver_fails_closed_when_ambiguous_or_untyped(tmp_path):
    (tmp_path / "Over.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "interface IOver {\n"
        "    function f(uint256 a) external;\n"
        "    function f(bytes32 a) external;\n"
        "    function g(uint256 a) external;\n"
        "}\n"
        "contract Getter { uint256 public total; }\n"
        "contract GetterChild is Getter {}\n",
        encoding="utf-8",
    )
    # A second, unrelated IERC20 makes the name ambiguous in Mixed.sol only.
    (tmp_path / "Other.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        "interface IERC20 { function transfer(address to, uint256 value) external returns (bool); }\n",
        encoding="utf-8",
    )
    (tmp_path / "Mixed.sol").write_text(
        "pragma solidity ^0.8.20;\n"
        'import "./IERC20.sol";\n'
        'import "./Other.sol";\n'
        "contract Mixed { function m(IERC20 t) external { t.transfer(address(0), 1); } }\n",
        encoding="utf-8",
    )
    result = _typed_receiver_corpus(tmp_path, (
        "pragma solidity ^0.8.20;\n"
        'import {IOver, GetterChild} from "./Over.sol";\n'
        "contract Vault {\n"
        "    function run(IOver o, GetterChild c, uint256 x) external {\n"
        "        o.f(x);\n"  # two overloads of the same arity
        "        o.g(x, x);\n"  # no g with two parameters
        "        c.total();\n"  # a public state variable's getter, not a function
        "        unknown.g(x);\n"  # not declared anywhere: no type
        "        x.g(x);\n"  # uint256 has no member g
        "    }\n"
        "    function ok(IOver o) external { o.g(1); }\n"
        "}\n"
    ))

    assert _function_calls(result) == {("ok()", "g()", "Over.sol")}


@_needs_solidity
def test_solidity_using_for_fails_closed_when_unknown_ambiguous_or_out_of_scope(tmp_path):
    result = _using_corpus(tmp_path, {
        "SafeCast.sol": _SAFE_CAST,
        "Dup.sol": (
            "pragma solidity ^0.8.20;\n"
            "library Dup { function toUint48(uint256 value) internal pure returns (uint48) { return 0; } }\n"
        ),
        "Vault.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {SafeCast} from "./SafeCast.sol";\n'
            'import {Dup} from "./Dup.sol";\n'
            "contract Other {\n"
            "    using SafeCast for uint256;\n"  # not inherited by Vault (0.7+)
            "}\n"
            "contract Vault is Other {\n"
            "    using SafeCast for int256;\n"
            "    function run(uint256 x, int256 i, uint64 small) external {\n"
            "        x.toUint48();\n"  # only Other attaches SafeCast to uint256
            "        small.toUint48();\n"  # uint64 is no uint256: no exact match
            "        unknown.toUint48();\n"  # no declared type
            "    }\n"
            "    function ok(int256 i) external pure returns (uint48) { return i.toUint48(); }\n"
            "}\n"
            "contract Both {\n"
            "    using SafeCast for uint256;\n"
            "    using Dup for uint256;\n"
            "    function two(uint256 x) external pure { x.toUint48(); }\n"  # two libraries fit
            "}\n"
        ),
    })

    assert _function_calls(result) == {("ok()", "toUint48()", "SafeCast.sol")}


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
