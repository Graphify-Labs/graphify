"""Original empty-default evidence over the actual accepted C++ parser view.

An unchanged source tail never supplies a default guess. The sidecar requires
the precise `= {}` omission produced by the compatibility adapter, an actual
parameter/callable binding and unchanged original comma/closing delimiters.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from graphify.extractors.cpp_declarators import callable_declarator

_EMPTY = re.compile(rb"\s*(?P<default>=\s*\{\s*\})\s*")


class ErasedDefaultLimitError(ValueError):
    """A bounded source-provenance list cannot silently lose optional parameters."""

    code = "CPP_SOURCE_DEFAULTS_LIMIT"


@dataclass(frozen=True)
class ErasedDefaultParameter:
    parameter_span: tuple[int, int]
    default_span: tuple[int, int]
    mechanism: str = "empty_default_cpp_view"

    def fact(self, original_source):
        from graphify.extractors.qt_cpp_syntax import source_span
        return {"parameter_span": source_span(original_source, *self.parameter_span),
                "default_span": source_span(original_source, *self.default_span), "mechanism": self.mechanism}


def _owned(function, original_source):
    declaration = function.parent
    while declaration is not None and declaration.type not in {"declaration", "field_declaration", "function_definition"}:
        if declaration.type in {"parameter_list", "argument_list", "init_declarator"}:
            return False
        declaration = declaration.parent
    if declaration is None or function.has_error or not any(callable_declarator(item, original_source) == function
            for item in declaration.children_by_field_name("declarator")):
        return False
    if declaration.type == "function_definition":
        body = declaration.child_by_field_name("body")
        return not any(child.has_error for child in declaration.children if child != body)
    return not declaration.has_error


def erased_default_parameters(function, original_source):
    """Return immutable exact spans, bounded to the durable generic metadata limit."""
    from graphify.extractors.qt_cpp_syntax import lexical_code
    if function.type != "function_declarator" or not _owned(function, original_source):
        return ()
    params = function.child_by_field_name("parameters")
    if params is None or params.text is None or params.end_byte > len(original_source):
        return ()
    view = params.text
    delimiters = [child.start_byte for child in params.children if child.type in {",", ")"}]
    records, cursor = [], 0
    for parameter in params.named_children:
        if parameter.type != "parameter_declaration" or parameter.has_error:
            continue  # Existing AST defaults retain their own primary evidence.
        while cursor < len(delimiters) and delimiters[cursor] < parameter.end_byte:
            cursor += 1
        if cursor >= len(delimiters):
            continue
        start, end = parameter.end_byte, delimiters[cursor]
        original = original_source[start:end]
        changed = view[start - params.start_byte:end - params.start_byte]
        match = _EMPTY.fullmatch(lexical_code(original))
        if (match is None or not original or original == changed or len(changed) != len(original)
                or lexical_code(changed).strip()):
            continue
        first, last = start + match.start("default"), start + match.end("default")
        # A statement elsewhere cannot lend a copied empty-default shape. Every
        # changed non-newline byte belongs to this exact default omission.
        left, right = match.span("default")
        if (any(byte not in b" \t\r\n" for byte in changed[left:right])
                or original[:left] != changed[:left] or original[right:] != changed[right:]
                or [(i, byte) for i, byte in enumerate(original) if byte in (10, 13)]
                   != [(i, byte) for i, byte in enumerate(changed) if byte in (10, 13)]):
            continue
        records.append(ErasedDefaultParameter((parameter.start_byte, parameter.end_byte), (first, last)))
        if len(records) > 50:
            raise ErasedDefaultLimitError("Erased C++ default provenance exceeds fifty parameters")
    return tuple(records)
