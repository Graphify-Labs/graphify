"""Source-owned C# field declarations, separate from receiver-type inference.

The generic walker supplies the accepted containing type and ID allocator. This
helper reads only direct variable declarators; initializers and function-local
variables cannot become class fields or callable declarations.
"""
from __future__ import annotations

import base64
import hashlib

from graphify.extractors.base import _read_text


class FieldOccurrences:
    """One producer run owns repeated declaration identities, not runtime values."""

    def __init__(self, reserved_names=None):
        self.counts = {}
        self.reserved_names = {owner: frozenset(name.removeprefix("@") for name in names)
                               for owner, names in (reserved_names or {}).items()}

    def identify(self, base, owner, name, syntax):
        key = (owner, name)
        occurrence = self.counts.get(key, 0)
        self.counts[key] = occurrence + 1
        if not occurrence and name.removeprefix("@") not in self.reserved_names.get(owner, ()):
            return base, occurrence
        # The ordinary source-name allocator cannot emit ':'. This separate
        # declaration-role suffix cannot collide with a future named member;
        # full span digest keeps repeated conditional alternatives distinct.
        location = f"{syntax.start_byte}:{syntax.end_byte}"
        return base + "::field-declaration::" + hashlib.sha256(location.encode()).hexdigest(), occurrence


def field_declarations(node, source):
    """Yield actual field names and original declarator coordinates."""
    if node.type != "field_declaration" or node.has_error:
        return []
    variables = next((child for child in node.named_children if child.type == "variable_declaration"), None)
    if variables is None:
        return []
    type_node = variables.child_by_field_name("type")
    if type_node is None or type_node.is_missing:
        return []
    modifiers = [_read_text(child, source) for child in node.named_children if child.type == "modifier"]
    parent, conditional = node.parent, False
    while parent:
        conditional = conditional or parent.type in {"preproc_if", "preproc_elif", "preproc_else"}
        parent = parent.parent
    # Display metadata follows upstream escaping. A separate bounded raw value
    # preserves generic/nullable spellings without turning display text into
    # type-resolution authority; unusually large types remain explicit unknowns.
    declared_type = _read_text(type_node, source)
    literal = declared_type.encode("utf-8")
    type_fields = ({"declared_type_b64": base64.b64encode(literal).decode("ascii"), "type_status": "source_only"}
                   if len(literal) <= 384 else {"declared_type_b64": "", "type_status": "unsupported",
                                               "type_reason": "field_type_literal_limit"})
    values = []
    for syntax in variables.named_children:
        if syntax.type != "variable_declarator" or syntax.has_error:
            continue
        name = syntax.child_by_field_name("name")
        if name is None or name.type != "identifier" or name.is_missing:
            continue
        raw_name = _read_text(name, source)
        if not raw_name:
            continue
        values.append((raw_name, syntax, {"contract_version": 1, "kind": "field",
            "declared_type": declared_type, "modifiers": modifiers, "conditional": conditional, **type_fields,
            "span": {"start_byte": syntax.start_byte, "end_byte": syntax.end_byte,
                     "start_row": syntax.start_point.row, "end_row": syntax.end_point.row,
                     "start_column": syntax.start_point.column, "end_column": syntax.end_point.column}}))
    return values
