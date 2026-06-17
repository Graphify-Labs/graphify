"""Tests for Solidity (.sol) AST extraction."""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import (
    _SOLIDITY_REMAPPINGS_CACHE,
    _make_id,
    extract_solidity,
    _get_extractor,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures"


def _labels(result: dict) -> list[str]:
    return [n["label"] for n in result.get("nodes", [])]


def _edge_pairs(result: dict, relation: str, *, context: str | None = None) -> set[tuple[str, str]]:
    node_by_id = {n["id"]: n["label"] for n in result.get("nodes", [])}
    pairs: set[tuple[str, str]] = set()
    for edge in result.get("edges", []):
        if edge.get("relation") != relation:
            continue
        if context is not None and edge.get("context") != context:
            continue
        src = node_by_id.get(edge.get("source", ""), edge.get("source", ""))
        tgt = node_by_id.get(edge.get("target", ""), edge.get("target", ""))
        pairs.add((src, tgt))
    return pairs


def _import_targets(result: dict) -> set[str]:
    return {str(e.get("target") or "") for e in result.get("edges", []) if e.get("relation") == "imports"}


def test_solidity_in_code_extensions():
    assert ".sol" in CODE_EXTENSIONS


def test_solidity_dispatched():
    assert _get_extractor(Path("contracts/Token.sol")) is extract_solidity


def test_extract_solidity_no_error():
    result = extract_solidity(FIXTURES / "sample.sol")
    assert "error" not in result


def test_extract_solidity_entities():
    result = extract_solidity(FIXTURES / "sample.sol")
    labels = _labels(result)
    assert "Token" in labels
    assert "IToken" in labels
    assert "SafeMath" in labels
    assert "Point" in labels
    assert "Status" in labels
    assert "Transfer" in labels
    assert any(".transfer()" in label for label in labels)
    assert any(".constructor()" in label for label in labels)
    assert any(".whenActive()" in label for label in labels)
    assert any(".receive()" in label for label in labels)
    assert any(".fallback()" in label for label in labels)
    assert any(".deployChild()" in label for label in labels)


def test_extract_solidity_relative_imports_resolve():
    result = extract_solidity(FIXTURES / "sample.sol")
    targets = _import_targets(result)
    base_path = FIXTURES / "solidity" / "Base.sol"
    iface_path = FIXTURES / "solidity" / "interfaces" / "IERC20.sol"
    assert _make_id(str(base_path)) in targets
    assert _make_id(str(iface_path)) in targets
    assert _make_id("IERC20") in targets


def test_extract_solidity_inheritance_and_implements():
    result = extract_solidity(FIXTURES / "sample.sol")
    assert ("Token", "Base") in _edge_pairs(result, "inherits")
    assert ("Token", "IToken") in _edge_pairs(result, "implements")


def test_extract_solidity_using_directive():
    result = extract_solidity(FIXTURES / "sample.sol")
    assert ("Token", "SafeMath") in _edge_pairs(result, "uses")


def test_extract_solidity_field_references():
    result = extract_solidity(FIXTURES / "sample.sol")
    assert ("Token", "IERC20") in _edge_pairs(result, "references", context="field")


def test_extract_solidity_emits():
    result = extract_solidity(FIXTURES / "sample.sol")
    assert ("Token", "Transfer") in _edge_pairs(result, "emits")


def test_extract_solidity_instantiates():
    result = extract_solidity(FIXTURES / "sample.sol")
    assert any(
        src.endswith("deployChild()") or ".deployChild()" in src
        for src, tgt in _edge_pairs(result, "instantiates")
        if tgt == "Token"
    )


def test_extract_solidity_calls_and_raw_calls():
    result = extract_solidity(FIXTURES / "sample.sol")
    calls = _edge_pairs(result, "calls", context="call")
    raw = result.get("raw_calls", [])
    raw_callees = {rc["callee"] for rc in raw}
    assert not any(callee.strip("()") == "require" for _, callee in calls)
    assert "require" not in raw_callees
    assert any(
        rc["callee"] == "transfer" and rc.get("receiver") == "underlying"
        for rc in raw
    )


def test_extract_solidity_no_dangling_edges():
    result = extract_solidity(FIXTURES / "sample.sol")
    node_ids = {n["id"] for n in result["nodes"]}
    for edge in result["edges"]:
        assert edge["source"] in node_ids
        if edge["relation"] not in ("imports", "imports_from", "re_exports"):
            assert edge["target"] in node_ids


def test_extract_solidity_foundry_remapping_txt(tmp_path):
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    (tmp_path / "remappings.txt").write_text("@vendor/=vendor/\n", encoding="utf-8")
    vendor_dir = tmp_path / "vendor"
    vendor_dir.mkdir()
    target = vendor_dir / "Target.sol"
    target.write_text("pragma solidity ^0.8.0; contract Target {}\n", encoding="utf-8")
    consumer = tmp_path / "Consumer.sol"
    consumer.write_text(
        'pragma solidity ^0.8.0;\nimport "@vendor/Target.sol";\ncontract Consumer {}\n',
        encoding="utf-8",
    )
    result = extract_solidity(consumer)
    assert "error" not in result
    assert _make_id(str(target.resolve())) in _import_targets(result)


def test_extract_solidity_foundry_toml_remapping(tmp_path):
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    (tmp_path / "foundry.toml").write_text(
        '[profile.default]\nremappings = ["@oz/=lib/oz/"]\n',
        encoding="utf-8",
    )
    lib_dir = tmp_path / "lib" / "oz"
    lib_dir.mkdir(parents=True)
    target = lib_dir / "ERC20.sol"
    target.write_text("pragma solidity ^0.8.0; contract ERC20 {}\n", encoding="utf-8")
    consumer = tmp_path / "Consumer.sol"
    consumer.write_text(
        'pragma solidity ^0.8.0;\nimport "@oz/ERC20.sol";\ncontract Consumer {}\n',
        encoding="utf-8",
    )
    result = extract_solidity(consumer)
    assert "error" not in result
    assert _make_id(str(target.resolve())) in _import_targets(result)


def test_extract_solidity_multi_contract():
    result = extract_solidity(FIXTURES / "sample.sol")
    labels = _labels(result)
    # sample.sol has Token, IToken interface, SafeMath library, Point struct, Status enum
    assert "IToken" in labels
    assert "SafeMath" in labels
    assert "Point" in labels
    assert "Status" in labels
    assert "Token" in labels


def test_extract_solidity_abstract_contract(tmp_path):
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    f = tmp_path / "Abstract.sol"
    f.write_text(
        "pragma solidity ^0.8.0;\n"
        "abstract contract Base {\n"
        "    function foo() virtual internal returns (uint256);\n"
        "}\n"
        "contract Child is Base {\n"
        "    function foo() internal override returns (uint256) { return 1; }\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract_solidity(f)
    assert "error" not in result
    assert "Base" in _labels(result)
    assert "Child" in _labels(result)
    assert ("Child", "Base") in _edge_pairs(result, "inherits")


def test_extract_solidity_interface_no_iprefix(tmp_path):
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    f = tmp_path / "NoPrefix.sol"
    f.write_text(
        "pragma solidity ^0.8.0;\n"
        "interface Transferable {\n"
        "    function transfer(address to, uint256 amount) external;\n"
        "}\n"
        "contract Wallet is Transferable {\n"
        "    function transfer(address to, uint256 amount) external override {}\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract_solidity(f)
    assert "error" not in result
    assert "Transferable" in _labels(result)
    assert "Wallet" in _labels(result)
    assert ("Wallet", "Transferable") in _edge_pairs(result, "implements")


def test_extract_solidity_malformed_import_no_crash(tmp_path):
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    f = tmp_path / "Malformed.sol"
    f.write_text(
        'pragma solidity ^0.8.0;\n'
        'import {Foo} from "";\n'
        'contract Bar {}\n',
        encoding="utf-8",
    )
    result = extract_solidity(f)
    assert "error" not in result
    assert "Bar" in _labels(result)


def test_extract_solidity_primitive_type_filtering(tmp_path):
    """Built-in types must NOT create spurious references edges (#1362)."""
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    f = tmp_path / "Primitive.sol"
    f.write_text(
        "pragma solidity ^0.8.0;\n"
        "contract P {\n"
        "    uint128 public a;\n"
        "    bytes32 public b;\n"
        "    fixed128x18 public c;\n"
        "    ufixed256x18 public d;\n"
        "    IERC20 public token;\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract_solidity(f)
    refs = list(_edge_pairs(result, "references", context="field"))
    ref_targets = {t for _, t in refs}
    assert "uint128" not in ref_targets, f"uint128 should be filtered, got refs: {refs}"
    assert "bytes32" not in ref_targets, f"bytes32 should be filtered, got refs: {refs}"
    assert "fixed128x18" not in ref_targets, f"fixed128x18 should be filtered, got refs: {refs}"
    assert "ufixed256x18" not in ref_targets, f"ufixed256x18 should be filtered, got refs: {refs}"
    # User-defined type must still create a reference
    assert "IERC20" in ref_targets, f"IERC20 should be referenced, got refs: {refs}"


def test_import_remapping_traversal_guard(tmp_path):
    """A malicious remapping that redirects outside the project tree is blocked (#1362)."""
    from graphify.extract import _resolve_solidity_import_path, _SOLIDITY_REMAPPINGS_CACHE
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    (tmp_path / ".git").mkdir()
    (tmp_path / "remappings.txt").write_text("evil/=../../../../tmp/\n")
    victim = tmp_path / "src" / "Token.sol"
    victim.parent.mkdir()
    victim.write_text("contract T {}")
    # Remapped path escapes the .git root → should be blocked
    assert _resolve_solidity_import_path("evil/secret.sol", str(victim)) is None


def test_import_traversal_guard(tmp_path):
    """Relative imports escaping the project tree must be rejected (#1362)."""
    from graphify.extract import _resolve_solidity_import_path, _SOLIDITY_REMAPPINGS_CACHE
    _SOLIDITY_REMAPPINGS_CACHE.clear()
    (tmp_path / ".git").mkdir()
    victim = tmp_path / "src" / "Token.sol"
    victim.parent.mkdir()
    victim.write_text("contract T {}")
    # Escapes above .git root
    assert _resolve_solidity_import_path("../../etc/passwd", str(victim)) is None
    # Stays within .git root
    (tmp_path / "Foo.sol").write_text("contract F {}")
    assert _resolve_solidity_import_path("../Foo.sol", str(victim)) is not None


def test_extract_solidity_base_file():
    result = extract_solidity(FIXTURES / "solidity" / "Base.sol")
    assert "error" not in result
    assert "Base" in _labels(result)
    assert any(".onlyOwner()" in label for label in _labels(result))
