"""Source-proven ordinary C++ member joins, including literal using namespaces.

Qualified source spelling, one declaration/body signature and accepted class
ownership must agree before changing an implementation ID. A basename never binds
it, including when both source occurrences belong to one translation unit.
"""
from __future__ import annotations

from pathlib import Path
import hashlib
import re

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.cpp_class_proof import class_fact
from graphify.extractors.cpp_constructors import _decoded, _encoded, _identifier, _signature, _span, _store, _walk
from graphify.extractors.cpp_identity import CppIdentity, lexical_scope, qualified_function_id
from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_constructor_binding import within_class

_HEADERS = {".h", ".hh", ".hpp", ".hxx"}
_IMPL = {".cpp", ".cc", ".cxx", ".c++"}


def _member_signature(declarator, source):
    parameter_signature = _signature(declarator, source)
    if not parameter_signature:
        return ""
    qualifiers = [_read_text(child, source) for child in declarator.children
                  if child.type in {"type_qualifier", "ref_qualifier"}]
    return hashlib.sha256("\0".join([parameter_signature, *qualifiers]).encode()).hexdigest()


def _visible_usings(root, source, scope, position):
    values = []
    for node in _walk(root):
        if node.type != "using_declaration" or node.start_byte >= position:
            continue
        literal = _read_text(node, source).strip()
        prefix = "using namespace "
        target = literal[len(prefix):].removesuffix(";").strip() if literal.startswith(prefix) else ""
        local = lexical_scope(node, source)
        parent, conditional = node.parent, False
        while parent:
            conditional |= parent.type.startswith("preproc_")
            parent = parent.parent
        if (not conditional and local is not None and _identifier(target)
                and (not local or scope == local or scope.startswith(local + "::"))):
            values.append(_encoded(target))
    unique = sorted(set(values))
    # Discarding an overflowed alternative could turn real ambiguity into a
    # false singleton owner. Keep the member fact, but give no join authority.
    return unique if len(unique) <= 50 else None


def augment_cpp_members(root, source, nodes, path, *, identities=None):
    """Stamp bounded original AST facts before corpus canonicalization."""
    if root.has_error:
        return
    # Generic allocation can salt a class away from its colliding file ID.
    # Reuse that run-owned mapping; standalone callers retain the original path.
    identities = identities or CppIdentity(root, source, _file_stem(path))
    by_id = {node["id"]: node for node in nodes}
    guards = IncludeGuardIndex(root)
    for item in _walk(root):
        if item.type != "function_declarator":
            continue
        syntax = item.parent
        while syntax and syntax.type not in {"field_declaration", "function_definition"}:
            syntax = syntax.parent
        if syntax is None or syntax.child_by_field_name("type") is None:
            continue
        name_node = item.child_by_field_name("declarator")
        name = _read_text(name_node, source) if name_node else ""
        signature, scope = _member_signature(item, source), lexical_scope(syntax, source)
        if not _identifier(name) or not signature or scope is None:
            continue
        parent = syntax.parent
        while parent and parent.type not in {"class_specifier", "struct_specifier", "translation_unit", "namespace_definition"}:
            parent = parent.parent
        record = identities.record(parent) if parent else None
        if record:
            owner, member, role = record["qualified"], name, "declaration"
            nid = _make_id(identities.declaration_id(record), name)
        elif syntax.type == "function_definition" and "::" in name:
            raw_owner, member = name.rsplit("::", 1)
            owner = "::".join(filter(None, (scope, raw_owner)))
            role = "definition"
            nid = qualified_function_id(_file_stem(path), syntax, name, source, identities=identities)
        else:
            continue
        nid = identities.member_id(item) or nid
        target = by_id.get(nid)
        if (target is None or not _identifier(owner) or not _identifier(member)
                or str(target.get("label", "")).removeprefix(".").removesuffix("()") != name
                or target.get("source_location") != f"L{syntax.start_point.row + 1}"):
            continue
        parent, conditional = syntax.parent, False
        while parent:
            conditional |= parent.type.startswith("preproc_") and not guards.accepts(parent)
            parent = parent.parent
        usings = _visible_usings(root, source, scope, syntax.start_byte) if role == "definition" else []
        _store(target, "cpp_member", {
            "contract_version": 1, "owner_b64": _encoded(owner), "name_b64": _encoded(name),
            "scope_b64": _encoded(scope), "member_b64": _encoded(member), "signature": signature,
            "role": role, "span": _span(syntax),
            "ambiguous": usings is None or conditional or identities.member_ambiguous(item),
            "using_b64": usings or [], "using_status": "unsupported" if usings is None else "resolved",
        })


def member_fact(node):
    value = node.get("metadata", {}).get("cpp_member")
    if (not isinstance(value, dict) or type(value.get("contract_version")) is not int
            or value["contract_version"] != 1 or type(value.get("ambiguous")) is not bool
            or value.get("role") not in {"declaration", "definition"}
            or node.get("_callable") is not True or node.get("_callable_class") is True
            or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("signature", "")))):
        return {}
    name, owner, member = (_decoded(value.get(key)) for key in ("name_b64", "owner_b64", "member_b64"))
    scope = "" if value.get("scope_b64") == "" else _decoded(value.get("scope_b64"))
    span = value.get("span", {})
    if (not name or not owner or not member or not isinstance(value.get("scope_b64"), str)
            or (value["scope_b64"] and not scope)
            or str(node.get("label", "")).removesuffix("()").removeprefix(".") != name
            or name.rsplit("::", 1)[-1] != member or not isinstance(span, dict)
            or any(type(span.get(key)) is not int or span[key] < 0 for key in
                   ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"))
            or span["end_byte"] <= span["start_byte"] or span["end_row"] < span["start_row"]
            or (span["end_row"] == span["start_row"]
                and span["end_column"] - span["start_column"] != span["end_byte"] - span["start_byte"])
            or node.get("source_location") != f"L{span['start_row'] + 1}"
            or not node.get("source_file")):
        return {}
    expected = scope if value["role"] == "declaration" else "::".join(filter(None, (scope, name.rsplit("::", 1)[0])))
    usings = value.get("using_b64")
    if (expected != owner or not isinstance(usings, list) or len(usings) > 50
            or any(not _decoded(item) for item in usings)):
        return {}
    return value


def _siblings(header, implementation):
    left, right = Path(str(header)), Path(str(implementation))
    return left.suffix.lower() in _HEADERS and right.suffix.lower() in _IMPL and left.with_suffix("") == right.with_suffix("")


def _definition_occurrence(node, fact):
    """Accepted-context copies retain one original file/declarator occurrence."""
    path = node.get("source_file")
    if not isinstance(path, str) or not path:
        return None
    span = fact["span"]
    coordinates = tuple(span[key] for key in ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"))
    return (path, coordinates, fact["owner_b64"], fact["name_b64"], fact["signature"])


def proven_member_pairs(nodes, edges):
    """Query unique source pairs without changing identities, metadata or edges.

    Both canonical navigation and direct call scope consume this exact proof.
    Returned triples borrow the actual body, declaration and allocated class;
    only the explicit canonicalization owner may mutate them afterward.
    """
    owners, prototypes = {}, {}
    for node in nodes:
        fact = class_fact(node)
        if fact and fact["is_definition"] and not fact["ambiguous"]:
            owners.setdefault(_decoded(fact["qualified_name_b64"]), []).append(node)
        fact = member_fact(node)
        if fact and fact["role"] == "declaration" and not fact["ambiguous"]:
            prototypes.setdefault((_decoded(fact["owner_b64"]), _decoded(fact["member_b64"]), fact["signature"]), []).append(node)
    pairs = []
    for node in nodes:
        fact = member_fact(node)
        if not fact or fact["role"] != "definition" or fact["ambiguous"]:
            continue
        # Original file containment proves this is an accepted definition site;
        # copying a plausible member fact onto an arbitrary callable is unsafe.
        file_id = _make_id(str(node["source_file"]))
        file_nodes = [item for item in nodes if item["id"] == file_id
                      and item.get("source_file") == node["source_file"]
                      and item.get("source_location") == "L1"
                      and not item.get("_callable") and not item.get("_callable_class")]
        if len(file_nodes) != 1 or not any(
                edge.get("source") == file_id and edge.get("target") == node["id"]
                and edge.get("relation") == "contains" and edge.get("confidence") == "EXTRACTED"
                and edge.get("source_file") == node["source_file"]
                and edge.get("source_location") == node["source_location"] for edge in edges):
            continue
        raw_owner = _decoded(fact["owner_b64"])
        names = {raw_owner} | {_decoded(item) + "::" + raw_owner for item in fact["using_b64"]}
        candidates = [(name, owner) for name in names for owner in owners.get(name, ())
                      if owner.get("source_file") == node.get("source_file")
                      or _siblings(owner.get("source_file"), node.get("source_file"))]
        if len(candidates) != 1:
            continue
        name, owner = candidates[0]
        found = prototypes.get((name, _decoded(fact["member_b64"]), fact["signature"]), ())
        found = [target for target in found if target.get("source_file") == owner.get("source_file")
                 and within_class(target, member_fact(target), owner)
                 and any(edge.get("source") == owner["id"] and edge.get("target") == target["id"]
                         and edge.get("relation") == "method" and edge.get("confidence") == "EXTRACTED"
                         and edge.get("source_file") == owner.get("source_file")
                         and edge.get("source_location") == target.get("source_location") for edge in edges)]
        if len(found) != 1:
            continue
        pairs.append((node, found[0], owner))
    # Copies of one accepted source occurrence are not competing bodies. Two
    # distinct bodies retain their source facts/IDs for conservative resolution.
    counts = {}
    for node, target, _ in pairs:
        counts.setdefault(id(target), set()).add(_definition_occurrence(node, member_fact(node)))
    return tuple((node, target, owner) for node, target, owner in pairs
                 if None not in counts[id(target)] and len(counts[id(target)]) == 1)


def canonicalize_cpp_members(nodes, edges, raw_calls=()):
    """Join after producer call reconciliation, using actual occurrence identities."""
    from graphify.extractors.cpp_member_remap import plan_member_remap
    pairs, changes = plan_member_remap(proven_member_pairs(nodes, edges), edges, raw_calls)
    dropped = set()
    for node, target, owner in pairs:
        name = _decoded(class_fact(owner)["qualified_name_b64"])
        fact = member_fact(node)
        fact["bound_owner_b64"] = _encoded(name)
        if node.get("source_file") == target.get("source_file"):
            # Navigation retains the original body without replacing the strict
            # declaration proof or lending its span new native authority.
            target.update(definition_file=node["source_file"], definition_location=node["source_location"],
                          definition_span=dict(fact["span"]))
            dropped.add(id(node))
        else:
            node["id"] = target["id"]
    for carrier, key, identity in changes:
        carrier[key] = identity
    nodes[:] = [node for node in nodes if id(node) not in dropped]


def member_merge_allowed(group):
    facts = [member_fact(node) for node in group]
    if not any("cpp_member" in node.get("metadata", {}) for node in group):
        return True
    if any(not fact or fact["ambiguous"] for fact in facts):
        return False
    # The later generic sibling-ID merger must preserve an earlier rejection
    # of competing bodies, rather than selecting one navigation site by order.
    definitions = {_definition_occurrence(node, fact) for node, fact in zip(group, facts) if fact["role"] == "definition"}
    if None in definitions or len(definitions) > 1:
        return False
    return (len({fact["signature"] for fact in facts}) == 1
            and len({_decoded(fact.get("bound_owner_b64", fact["owner_b64"])) for fact in facts}) == 1)
