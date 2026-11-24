"""Solidity: calls, `super` calls and modifiers a contract inherits from a base
contract, usually declared in another file, bind through the contract's C3
linearization the way solc resolves them."""
from __future__ import annotations

import importlib.util as _ilu
import json
from pathlib import Path

import pytest

from graphify.extract import extract

pytestmark = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_solidity") is None,
    reason="tree-sitter-solidity not installed (optional [solidity] extra)",
)

_CONTEXT = (
    "pragma solidity ^0.8.20;\n"
    "abstract contract Context {\n"
    "    function _msgSender() internal view virtual returns (address) { return msg.sender; }\n"
    "}\n"
)
_OWNABLE = (
    "pragma solidity ^0.8.20;\n"
    'import {Context} from "./Context.sol";\n'
    "abstract contract Ownable is Context {\n"
    "    address private _owner;\n"
    "    modifier onlyOwner() { _checkOwner(); _; }\n"
    "    function owner() public view returns (address) { return _owner; }\n"
    "    function _checkOwner() internal view { require(owner() == _msgSender()); }\n"
    "}\n"
)


def _edges(tmp_path: Path, files: dict[str, str]) -> set[tuple[str, str, str, str]]:
    """(caller contract, caller, relation, callee contract.callee) for calls/uses edges."""
    for name, text in files.items():
        (tmp_path / name).write_text(text, encoding="utf-8")
    result = extract(sorted(tmp_path.glob("*.sol")), cache_root=tmp_path)
    nodes = {n["id"]: n for n in result["nodes"]}
    owner = {
        e["target"]: nodes[e["source"]]["label"]
        for e in result["edges"]
        if e["relation"] == "method" and e["source"] in nodes
    }
    return {
        (owner.get(e["source"], "?"), nodes[e["source"]]["label"], e["relation"],
         f"{owner.get(e['target'], '?')}.{nodes[e['target']]['label']}")
        for e in result["edges"]
        if e["relation"] in ("calls", "uses") and e["source"] in nodes and e["target"] in nodes
    }


def test_call_to_a_function_declared_in_a_base_contract_in_another_file(tmp_path: Path):
    edges = _edges(tmp_path, {"Context.sol": _CONTEXT, "Ownable.sol": _OWNABLE})
    assert ("Ownable", "_checkOwner()", "calls", "Context._msgSender()") in edges
    # the same-contract call keeps its edge
    assert ("Ownable", "_checkOwner()", "calls", "Ownable.owner()") in edges


def test_modifier_declared_in_a_base_contract(tmp_path: Path):
    edges = _edges(tmp_path, {
        "Context.sol": _CONTEXT,
        "Ownable.sol": _OWNABLE,
        "Vault.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {Ownable} from "./Ownable.sol";\n'
            "contract Vault is Ownable {\n"
            "    function sweep() external onlyOwner { _msgSender(); }\n"
            "}\n"
        ),
    })
    assert ("Vault", "sweep()", "uses", "Ownable.onlyOwner()") in edges
    # two levels up: Vault -> Ownable -> Context
    assert ("Vault", "sweep()", "calls", "Context._msgSender()") in edges


def test_super_call_binds_to_the_next_contract_in_the_linearization(tmp_path: Path):
    edges = _edges(tmp_path, {
        "Bases.sol": (
            "pragma solidity ^0.8.20;\n"
            "contract A { function hook(uint x) internal virtual {} }\n"
            "contract B is A { function hook(uint x) internal virtual override { super.hook(x); } }\n"
        ),
        "C.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {A, B} from "./Bases.sol";\n'
            "contract C is B {\n"
            "    function hook(uint x) internal override { super.hook(x); }\n"
            "}\n"
        ),
    })
    assert ("C", "hook()", "calls", "B.hook()") in edges
    assert ("B", "hook()", "calls", "A.hook()") in edges
    assert ("C", "hook()", "calls", "A.hook()") not in edges


def test_super_call_inside_a_boolean_expression(tmp_path: Path):
    # tree-sitter-solidity parses `x || super.f(y)` as a call of `(x || super).f`.
    edges = _edges(tmp_path, {
        "Iface.sol": (
            "pragma solidity ^0.8.20;\n"
            "contract ERC165 { function supportsInterface(bytes4 id) public view virtual returns (bool) { return false; } }\n"
        ),
        "Token.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {ERC165} from "./Iface.sol";\n'
            "contract Token is ERC165 {\n"
            "    function supportsInterface(bytes4 id) public view override returns (bool) {\n"
            "        return id == 0x01ffc9a7 || super.supportsInterface(id);\n"
            "    }\n"
            "}\n"
        ),
    })
    assert ("Token", "supportsInterface()", "calls", "ERC165.supportsInterface()") in edges


def test_the_last_listed_base_wins_like_solc(tmp_path: Path):
    # `contract D is A, B`: B is the more derived base, so a bare `g()` that
    # both declare runs B.g (C3 linearization D, B, A).
    edges = _edges(tmp_path, {
        "AB.sol": (
            "pragma solidity ^0.8.20;\n"
            "contract A { function g() internal virtual {} }\n"
            "contract B { function g() internal virtual {} }\n"
        ),
        "D.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {A, B} from "./AB.sol";\n'
            "contract D is A, B { function run() external { g(); this.g(); } }\n"
        ),
    })
    assert ("D", "run()", "calls", "B.g()") in edges
    assert ("D", "run()", "calls", "A.g()") not in edges


def test_same_arity_overloads_in_the_base_are_left_unbound(tmp_path: Path):
    edges = _edges(tmp_path, {
        "Base.sol": (
            "pragma solidity ^0.8.20;\n"
            "contract Base {\n"
            "    function put(uint x) internal {}\n"
            "    function put(address x) internal {}\n"
            "    function put(uint x, uint y) internal {}\n"
            "}\n"
        ),
        "Child.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {Base} from "./Base.sol";\n'
            "contract Child is Base { function run() external { put(1); put(1, 2); } }\n"
        ),
    })
    calls = {e for e in edges if e[1] == "run()"}
    # arity 2 is unique; arity 1 has two overloads, so no guess
    assert calls == {("Child", "run()", "calls", "Base.put()")}


def test_a_name_no_base_declares_is_never_matched_corpus_wide(tmp_path: Path):
    edges = _edges(tmp_path, {
        "Other.sol": "pragma solidity ^0.8.20;\ncontract Other { function helper() internal {} }\n",
        "Lone.sol": (
            "pragma solidity ^0.8.20;\n"
            "contract Lone { function run() external { helper(); require(true); } }\n"
        ),
    })
    assert not any(e[1] == "run()" for e in edges), edges


def test_changed_files_rebuild_keeps_inherited_calls(tmp_path: Path):
    from graphify.watch import _rebuild_code

    files = {
        "Context.sol": _CONTEXT,
        "Ownable.sol": _OWNABLE,
        "Vault.sol": (
            "pragma solidity ^0.8.20;\n"
            'import {Ownable} from "./Ownable.sol";\n'
            "contract Vault is Ownable {\n"
            "    function sweep() external onlyOwner { _msgSender(); }\n"
            "}\n"
        ),
    }
    roots = []
    for name in ("inc", "full"):
        root = tmp_path / name
        root.mkdir()
        for fname, text in files.items():
            (root / fname).write_text(text, encoding="utf-8")
        roots.append(root)
    inc, full = roots
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    for root in roots:
        p = root / "Vault.sol"
        p.write_text(p.read_text(encoding="utf-8") + "// touched\n", encoding="utf-8")
    assert _rebuild_code(inc, changed_paths=[inc / "Vault.sol"], no_cluster=True, acquire_lock=False)
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)

    def edges_of(root: Path) -> set[tuple[object, object, object]]:
        g = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        label = {n["id"]: n.get("label") for n in g["nodes"]}
        links = g.get("links", g.get("edges", []))
        return {
            (label.get(e["source"]), e["relation"], label.get(e["target"]))
            for e in links if e["relation"] in ("calls", "uses")
        }

    full_edges = edges_of(full)
    assert ("sweep()", "uses", "onlyOwner()") in full_edges
    assert ("sweep()", "calls", "_msgSender()") in full_edges
    assert edges_of(inc) == full_edges
