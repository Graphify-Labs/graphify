"""Accepted C++ class source proof guards mapping and sibling canonicalization."""
from __future__ import annotations

from graphify.extractors.cpp_constructors import _decoded, _fact, _span


def class_fact(node):
    """Share the existing bounded transport/span/label contract, not a basename."""
    return _fact(node, "cpp_class") if node.get("_callable_class") is True else {}


def class_matches(node, qualified, syntax):
    fact = class_fact(node)
    if not fact or _decoded(fact["qualified_name_b64"]) != qualified:
        return False
    # A forward declaration denotes its exact qualified canonical class. A
    # complete body's authority additionally requires its original byte span.
    return syntax.child_by_field_name("body") is None or fact["span"] == _span(syntax)


def class_merge_allowed(group):
    facts = [class_fact(node) for node in group]
    if not any(isinstance(node.get("metadata"), dict) and "cpp_class" in node["metadata"] for node in group):
        return True
    if any(not fact or fact["ambiguous"] for fact in facts):
        return False
    return (len({_decoded(fact["qualified_name_b64"]) for fact in facts}) == 1
            and sum(fact["is_definition"] for fact in facts) <= 1)


def class_body_keeper(group, default):
    """A forward header must not replace an implementation's complete-body span."""
    complete = [node for node in group if class_fact(node).get("is_definition") is True]
    return complete[0] if len(complete) == 1 else default
