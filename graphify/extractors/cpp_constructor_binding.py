"""Exact parent and signature proof for constructor declaration/body joins."""
from __future__ import annotations

import hashlib

from graphify.extractors.base import _make_id
from graphify.extractors.cpp_identity import qualified_class_id
from graphify.extractors.cpp_constructor_signature import constructor_signature


def within_class(node, fact, owner):
    """An extracted parent edge cannot authorize a prototype relocated outside its source class."""
    span, parent_span = fact["span"], owner["metadata"]["cpp_class"]["span"]
    return (owner.get("source_file") == node.get("source_file")
            and parent_span["start_byte"] < span["start_byte"] < span["end_byte"] < parent_span["end_byte"]
            and (parent_span["start_row"], parent_span["start_column"]) < (span["start_row"], span["start_column"])
            and (span["end_row"], span["end_column"]) < (parent_span["end_row"], parent_span["end_column"]))


def inline_owner(node, fact, owners, edges):
    """An inline body requires one complete source-owned containing class."""
    if fact.get("ambiguous") or fact.get("owner_bound") is not True or len(owners) != 1:
        return False
    owner = owners[0]
    return (within_class(node, fact, owner)
            and any(edge.get("source") == owner["id"] and edge.get("target") == node["id"]
                    and edge.get("relation") == "method" and edge.get("confidence") == "EXTRACTED"
                    and edge.get("source_file") == node.get("source_file")
                    and edge.get("source_location") == node.get("source_location") for edge in edges))


def id_authorized(node, owner, signature):
    """Signature transport cannot redirect an occurrence into another class."""
    expected = _make_id(qualified_class_id("", owner), owner.rsplit("::", 1)[-1], "cppctor", signature)
    # Only the file prefix changes during root remapping. Owner and signature
    # must remain the exact producer suffix before and after that operation.
    return node["id"] == expected or str(node["id"]).endswith("_" + expected)


def syntax_matches(node, declaration, source, owner, *, definition_site=False):
    """A Qt source occurrence selects its actual signature and original span."""
    from graphify.extractors.cpp_constructors import _fact, _span
    fact = _fact(node, "cpp_constructor")
    if not fact:
        return False
    payload = constructor_signature(declaration, source, owner)
    if not payload or fact.get("ambiguous") or hashlib.sha256(payload).hexdigest() != fact["signature"]:
        return False
    span = fact.get("definition_span") if definition_site else fact["span"]
    return span == _span(declaration)


def bind_constructors(nodes, edges):
    """Join unique complete classes and exact matching overload declarations."""
    from graphify.extractors.cpp_constructors import _fact, _decoded
    from graphify.extractors.cpp_constructor_type_authority import ConstructorTypeAuthority
    classes = {}
    declarations = {}
    type_authority = ConstructorTypeAuthority(nodes)
    class_ids = {node["id"] for node in nodes if node.get("_callable_class") is True}
    for node in nodes:
        fact = _fact(node, "cpp_class")
        name = _decoded(fact.get("qualified_name_b64"))
        if (name and fact.get("is_definition") is True and not fact.get("ambiguous")
                and node.get("_callable_class") is True and type_authority.source_span_authorized(node, fact)):
            classes.setdefault(name, []).append(node)
        fact = _fact(node, "cpp_constructor")
        if fact.get("role") == "declaration":
            fact["type_authorized"] = type_authority.authorized(node, fact)
            declarations.setdefault(_decoded(fact.get("owner_b64")), []).append(node)
    for node in nodes:
        fact = _fact(node, "cpp_constructor")
        if fact.get("role") != "definition":
            continue
        if not type_authority.authorized(node, fact):
            fact.update(owner_bound=False, type_authorized=False)
            continue
        fact["type_authorized"] = True
        owners = classes.get(_decoded(fact.get("owner_b64")), [])
        if inline_owner(node, fact, owners, edges):
            continue  # Accepted inline body already has its exact class parent.
        fact["owner_bound"] = False
        prototypes = [item for item in declarations.get(_decoded(fact.get("owner_b64")), [])
                      if _fact(item, "cpp_constructor").get("signature") == fact.get("signature")]
        if len(owners) != 1 or len(prototypes) != 1 or fact.get("ambiguous"):
            continue
        prototype = prototypes[0]
        declaration = _fact(prototype, "cpp_constructor")
        owner = owners[0]
        if (declaration.get("ambiguous") or declaration.get("signature") != fact.get("signature")
                or not type_authority.authorized(prototype, declaration)
                or not within_class(prototype, declaration, owner)
                or not any(edge.get("source") == owner["id"] and edge.get("target") == prototype["id"]
                           and edge.get("relation") == "method" and edge.get("confidence") == "EXTRACTED"
                           and edge.get("source_file") == owner.get("source_file")
                           and edge.get("source_location") == prototype.get("source_location")
                           for edge in edges)):
            continue
        # Definition provenance and any pre-existing real parent remain authoritative.
        if (not any(edge.get("target") == node["id"] and edge.get("relation") == "contains"
                    and edge.get("confidence") == "EXTRACTED" and edge.get("source_file") == node.get("source_file")
                    for edge in edges)
                or any(edge.get("target") == node["id"] and (edge.get("relation") == "method"
                       or (edge.get("relation") == "contains" and edge.get("source") in class_ids))
                       and edge.get("confidence") == "EXTRACTED" and edge.get("source") != owner["id"]
                       for edge in edges)
                or any(edge.get("target") == prototype["id"] and (edge.get("relation") == "method"
                       or (edge.get("relation") == "contains" and edge.get("source") in class_ids))
                       and edge.get("confidence") == "EXTRACTED" and edge.get("source") != owner["id"]
                       for edge in edges)):
            continue
        fact["owner_bound"] = True
        declaration["definition_span"] = dict(fact["span"])
        if not any(edge.get("source") == owner["id"] and edge.get("target") == node["id"]
                   and edge.get("relation") == "method" for edge in edges):
            edges.append({"source": owner["id"], "target": node["id"], "relation": "method",
                          "confidence": "EXTRACTED", "context": "cpp_constructor_owner",
                          "source_file": owner["source_file"], "source_location": prototype["source_location"], "weight": 1.0})
