"""INC-QML-111: allocator exclusions share the existing constructor source owner."""
from __future__ import annotations

import base64
from copy import deepcopy

import pytest
from tree_sitter import Language, Parser
import tree_sitter_cpp

from graphify.extract import extract_cpp
from graphify.extractors.base import _file_stem
from graphify.extractors.cpp_constructors import constructor_candidate_ids
from graphify.extractors.cpp_identity import CppIdentity
from graphify.extractors.qt_cpp_syntax import read_cpp


@pytest.mark.parametrize("raw", [
    b"class Panel{public:Panel(int value=0){}void run(){}};",
    b"class Panel{public:Panel(int value);};Panel::Panel(int value){}",
    b"namespace Public{struct Outer{struct Inner{Inner(int value){}};};}",
    b"Public::Panel::Panel(int value){}",
    b"class Panel{public:Panel(Unknown value){}};",
    b"#if FEATURE\nclass Panel{public:Panel(int value){}};\n#endif\n",
    b"void owner(){struct Panel{Panel(int value){}};}",
    b"namespace{struct Panel{Panel(int value){}};}",
    b"struct Panel{void (*panel)(int);void run(){}};",
    b"struct Panel{void Panel(){}};void Ordinary(){}",
    b"struct Box{Box(int value){}};struct box{box(int value){}};",
])
def test_req_qml022_ac06_constructor_exclusions_match_actual_source_producer_without_mutation(tmp_path, raw):
    """A reservation query matches real source facts, preserving unsupported and ordinary roles."""
    path = tmp_path / "unit.cpp"
    path.write_bytes(raw)
    result = extract_cpp(path)
    unit = read_cpp(path, tmp_path)
    identities = CppIdentity(unit.tree, unit.source, _file_stem(path))
    original = path.read_bytes(), path.stat().st_mtime_ns
    records = {key: dict(value) for key, value in identities.records.items()}
    state = deepcopy((identities.declarations, identities.aliases, identities.member_nodes))
    candidates = constructor_candidate_ids(unit.tree, raw, identities)
    expected = {node["id"] for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")}
    assert isinstance(candidates, frozenset) and candidates == expected
    assert constructor_candidate_ids(unit.tree, raw, identities) == candidates
    assert identities.records == records
    assert (identities.declarations, identities.aliases, identities.member_nodes) == state
    assert (path.read_bytes(), path.stat().st_mtime_ns) == original


@pytest.mark.parametrize("profile", ["lf", "bom_crlf"])
def test_req_qml022_ac06_constructor_query_uses_original_pointer_signature_bytes(tmp_path, profile):
    """The equal-byte compatibility AST cannot substitute reference identity for an original pointer."""
    raw = b"struct Panel{Panel(Panel * = nullptr){}};\n"
    if profile == "bom_crlf":
        raw = b"\xef\xbb\xbf// \xcf\x80 original\r\n" + raw.replace(b"\n", b"\r\n")
    path = tmp_path / "unit.cpp"
    path.write_bytes(raw)
    result = extract_cpp(path)
    node, = [node for node in result["nodes"] if node.get("metadata", {}).get("cpp_constructor")]
    fact = node["metadata"]["cpp_constructor"]
    assert b"self:Panel*" in base64.b64decode(fact["signature_b64"])
    unit = read_cpp(path, tmp_path)
    identities = CppIdentity(unit.tree, unit.source, _file_stem(path))
    assert constructor_candidate_ids(unit.tree, raw, identities) == frozenset({node["id"]})


def test_req_qml022_ac06_partial_constructor_tree_supplies_no_allocator_exclusions():
    """The source query retains the original producer's whole-tree rejection boundary."""
    raw = b"struct Panel{Panel(int value){} }; void broken( {"
    root = Parser(Language(tree_sitter_cpp.language())).parse(raw).root_node
    assert root.has_error
    identities = CppIdentity(root, raw, "unit")
    assert constructor_candidate_ids(root, raw, identities) == frozenset()
