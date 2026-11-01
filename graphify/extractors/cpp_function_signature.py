"""Bounded source proof for primitive free-function parameter equivalence.

This is deliberately narrower than signature identity. Named types, aliases,
templates, callbacks, CV/pointer/reference adjustments and variadics do not gain
canonical body-join authority merely because two signature hashes agree.
"""
from __future__ import annotations

from graphify.extractors.base import _read_text
from graphify.extractors.cpp_empty_default_proof import ErasedDefaultLimitError, erased_default_parameters
from graphify.extractors.cpp_source_views import span_contains


_PRIMITIVES = {"void", "bool", "char", "signed char", "unsigned char", "short", "short int", "unsigned short", "unsigned short int",
               "int", "signed", "signed int", "unsigned", "unsigned int", "long", "long int", "unsigned long", "unsigned long int",
               "long long", "long long int", "unsigned long long", "unsigned long long int", "float", "double", "long double",
               "wchar_t", "char8_t", "char16_t", "char32_t"}


def parameter_facts(function, source):
    """Return arity and canonical primitive tokens from the actual function binding."""
    params = function.child_by_field_name("parameters")
    if params is None:
        return {"canonical_parameters": [], "canonical_status": "unsupported", "min_args": None, "max_args": None,
                "arity_status": "unsupported", "arity_reason": "parameter_list_unavailable", "erased_default_parameters": []}
    values = [child for child in params.named_children if "parameter_declaration" in child.type]
    variadic = any(child.type == "..." for child in params.children)
    required = sum(child.child_by_field_name("default_value") is None for child in values)
    maximum = None if variadic else len(values)
    if len(values) == 1 and _read_text(values[0], source) == "void":
        values, required, maximum = [], 0, 0
    try:
        recovered = erased_default_parameters(function, source)
    except ErasedDefaultLimitError:
        recovered, arity_status = (), "unsupported"
    else:
        arity_status = "available"
    minimum = required - len(recovered) if arity_status == "available" else None
    canonical = [] if len(values) <= 50 else None
    for parameter in values:
        if canonical is None:
            break
        type_node = parameter.child_by_field_name("type")
        declarator = parameter.child_by_field_name("declarator")
        if (type_node is None or type_node.type not in {"primitive_type", "sized_type_specifier"}
                or declarator is not None and declarator.type not in {"identifier", "field_identifier"}
                or any(child.type == "type_qualifier" for child in parameter.children)):
            canonical = None
            break
        spelling = " ".join(_read_text(type_node, source).split())
        if spelling not in _PRIMITIVES:
            canonical = None
            break
        canonical.append(spelling)
    return {"canonical_parameters": canonical or [],
            "canonical_status": "available" if canonical is not None and not variadic else "unsupported",
            "min_args": minimum, "max_args": maximum, "arity_status": arity_status,
            "arity_reason": "" if arity_status == "available" else "erased_default_parameter_limit",
            "ast_required_args": required, "erased_default_parameters": [record.fact(source) for record in recovered]}


def valid_parameter_facts(fact):
    """Cached source transport must retain exact types and bounded arity agreement."""
    minimum, maximum = fact.get("min_args"), fact.get("max_args")
    canonical, status = fact.get("canonical_parameters"), fact.get("canonical_status")
    arity, proofs = fact.get("arity_status"), fact.get("erased_default_parameters")
    if (maximum is not None and (type(maximum) is not int or maximum < 0)
            or type(canonical) is not list or len(canonical) > 50
            or any(not isinstance(value, str) or value not in _PRIMITIVES for value in canonical)
            or type(status) is not str or status not in {"available", "unsupported"}
            or type(arity) is not str or arity not in {"available", "unsupported"}
            or type(proofs) is not list or len(proofs) > 50):
        return False
    if arity == "unsupported":
        return (minimum is None and proofs == [] and fact.get("arity_reason") in
                ("parameter_list_unavailable", "erased_default_parameter_limit"))
    required = fact.get("ast_required_args")
    if (type(minimum) is not int or minimum < 0 or maximum is not None and maximum < minimum
            or type(required) is not int or required < 0 or maximum is not None and required > maximum
            or minimum != required - len(proofs) or fact.get("arity_reason") != ""):
        return False
    prior_end, span = -1, fact.get("span")
    for proof in proofs:
        if not isinstance(proof, dict) or proof.get("mechanism") != "empty_default_cpp_view":
            return False
        parameter, default = proof.get("parameter_span"), proof.get("default_span")
        if (not isinstance(parameter, dict) or not isinstance(default, dict)
                or not span_contains(span, parameter) or not span_contains(span, default)
                or not parameter["end_byte"] <= default["start_byte"]
                or parameter["start_byte"] < prior_end):
            return False
        prior_end = default["end_byte"]
    return (status == "unsupported" and canonical == []
            or status == "available" and maximum == len(canonical))
