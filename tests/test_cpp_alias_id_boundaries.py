"""INC-QML-112: literal alias collision census keeps legacy and lexical boundaries."""
from __future__ import annotations

import hashlib

import pytest
from tree_sitter import Language, Parser
import tree_sitter_cpp

from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.cpp_alias_ids import CppAliasIds
from graphify.extractors.engine import _cpp_alias_names
from tests.cpp_alias_helpers import declarations, produce, references, source


def census(raw, stem="fixture"):
    root = Parser(Language(tree_sitter_cpp.language())).parse(raw).root_node
    index = CppAliasIds(root, raw, stem, alias_names=_cpp_alias_names)
    pending, aliases = [root], []
    while pending:
        node = pending.pop()
        if node.type in {"alias_declaration", "type_definition"}:
            aliases.extend((node, name) for name in _cpp_alias_names(node, raw))
        pending.extend(reversed(node.named_children))
    return index, aliases


@pytest.mark.parametrize("form", ["using", "typedef"])
def test_req_qml008_ac02_alias_collision_identity_ignores_order_lines_and_target_edits(form):
    """Only the literal qualified alias names own the collision salt; target interpretation is separate."""
    identities = []
    lines = source(form).splitlines(keepends=True)
    reordered = b"".join([*lines[:2], *reversed(lines[2:4]), *lines[4:]])
    for raw in (source(form), source(form).replace(b"First", b"Temporary").replace(b"Second", b"First").replace(b"Temporary", b"Second"), reordered,
                b"// line shift\n" + source(form)):
        index, aliases = census(raw)
        identities.append({name: index.candidate(node, name, _make_id("fixture", name)) for node, name in aliases})
    assert identities[0] == identities[1] == identities[2] == identities[3]
    assert len(set(identities[0].values())) == 2


def test_req_qml008_ac02_alias_census_is_bound_to_actual_tree_and_original_candidate():
    """A new tree or a different allocator input cannot borrow an earlier occurrence's candidate."""
    raw = source()
    index, aliases = census(raw)
    other, foreign = census(raw)
    for (node, name), (different, _) in zip(aliases, foreign):
        original = _make_id("fixture", name)
        assert index.candidate(node, name, original) != original
        assert index.candidate(different, name, original) == original
        assert index.candidate(node, name, "foreign") == "foreign"
        assert other.candidate(node, name, original) == original


def test_req_qml008_ac02_literal_alias_resembling_generated_domain_keeps_own_legacy_id():
    """The generated candidate cannot swallow another admitted literal alias spelling."""
    crafted = "cppalias_" + hashlib.sha256(b"Alias").hexdigest() + "_Alias"
    raw = source() + f"using {crafted} = First;\n".encode()
    index, aliases = census(raw)
    identities = {name: index.candidate(node, name, _make_id("fixture", name)) for node, name in aliases}
    assert len(set(identities.values())) == 3
    assert identities[crafted] == _make_id("fixture", crafted)
    assert isinstance(index.reserved_ids, frozenset)
    assert index.reserved_ids == frozenset(identities.values()) | {_make_id("fixture", name) for _, name in aliases}


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml008_ac02_noncolliding_aliases_preserve_existing_ids(tmp_path, mode):
    """The literal-name correction leaves ordinary aliases in the existing allocator domain."""
    result = produce(tmp_path, source(names=("Upper", "Lower")), mode=mode)
    for node in declarations(result, ("Upper", "Lower")):
        if mode == "direct":
            assert node["id"] == _make_id(_file_stem(tmp_path / "types.cpp"), node["label"])
        else:
            assert node["id"].endswith("_" + node["label"].lower())
    assert {node["label"] for node in references(result).values()} == {"Upper", "Lower"}


def test_req_qml008_ac02_same_exact_alias_name_is_not_a_distinct_collision_bucket():
    """Repeated exact spelling does not become two invented literal names or target-derived IDs."""
    raw = b"using Alias=First;\nusing Alias=Second;\n"
    index, aliases = census(raw)
    assert len(aliases) == 2
    assert {index.candidate(node, name, _make_id("fixture", name)) for node, name in aliases} == {"fixture_alias"}


@pytest.mark.parametrize("wrapper", ["struct Outer{%s};", "struct Outer{struct Inner{%s};};",
                                      "struct Outer{\n#if FEATURE\n%s\n#endif\n};"])
def test_req_qml003_ac04_class_aliases_keep_existing_public_graph_exclusion(tmp_path, wrapper):
    """The admitted producer remains file/namespace only; no invented class-alias containment."""
    raw = ("struct First{};struct Second{};" + wrapper % "using Alias=First;typedef Second alias;").encode()
    result = produce(tmp_path, raw)
    assert not declarations(result)
    index, aliases = census(raw)
    assert not aliases


@pytest.mark.parametrize("mode", ["direct", "facade"])
def test_req_qml003_ac04_namespace_aliases_keep_file_containment_and_lexical_reference(tmp_path, mode):
    """Namespace membership stays in lexical lookup, preserving the established public file edge."""
    result = produce(tmp_path, source(scope="separate", names=("Alias", "Alias")), mode=mode)
    aliases = declarations(result, ("Alias",))
    assert len(aliases) == 2
    file_node, = [node for node in result["nodes"] if node.get("label") == "types.cpp"]
    for alias in aliases:
        assert any(edge["source"] == file_node["id"] and edge["target"] == alias["id"]
                   and edge.get("relation") == "contains" for edge in result["edges"])
    refs = references(result)
    assert refs["UsesUpper"]["id"] != refs["UsesLower"]["id"]


@pytest.mark.parametrize("raw", [b"namespace {using Alias=First;using alias=Second;}",
                                  b"namespace " + b"N" * 385 + b" {using Alias=First;using alias=Second;}",
                                  b"namespace " + b"N" * 200 + b" {namespace " + b"M" * 200
                                  + b" {using Alias=First;using alias=Second;}}"],
                         ids=["anonymous", "oversized-name", "oversized-nested-scope"])
def test_req_qml022_ac06_unavailable_qualified_alias_scope_cannot_invent_a_collision_name(raw):
    """Anonymous and oversized scopes preserve the existing unavailable lexical profile."""
    index, aliases = census(raw)
    assert len(aliases) == 2
    for node, name in aliases:
        original = _make_id("fixture", name)
        assert index.candidate(node, name, original) == original
        assert original in index.reserved_ids  # Negative allocation protection needs no namespace authority.
