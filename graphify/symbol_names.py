"""Shared symbol normalization for raw parser names and rendered graph labels."""
from __future__ import annotations


def normalize_symbol_name(value: object, *, graph_label: bool = False) -> str:
    """Return a comparable symbol name without rewriting source-language syntax."""

    text = str(value or "").strip().removeprefix(".")
    # Extracted callable labels add exactly one trailing ``()`` for display.
    # Compiler and parked-call names are raw symbols, where parentheses may be
    # meaningful syntax (operators and function-pointer conversions).
    if graph_label and text.endswith("()"):
        text = text[:-2]
    return text.strip()
