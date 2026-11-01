"""Qt6.12 property modifier syntax over the pinned older QML grammar.

Only error-owned contextual modifier tokens are repaired for parsing. Equal-byte
substitutions preserve AST ranges; every fact still reads the original source.
The analyzer records modifiers without enforcing QML engine override semantics.
"""
from __future__ import annotations

from graphify.extractors.qml_facts import text

_SUBSTITUTIONS = {b"virtual": b"default", b"override": b"readonly"}
_OVERRIDE = {"virtual", "override", "final"}


def _walk(root):
    pending = [root]
    while pending:
        node = pending.pop()
        yield node
        pending.extend(node.children)


def recover_property_modifiers(source, parser, tree, *, validate=None):
    """Accept a repair only when every changed token becomes an actual modifier.

    Clean declarations, JS identifiers, strings/comments and unrelated errors
    cannot borrow this compatibility path. A failed reparse retains the original
    failure, so recovery never suppresses malformed expressions or punctuation.
    """
    if not tree.root_node.has_error:
        return tree
    replacements = {}
    for node in _walk(tree.root_node):
        if node.children or node.type not in {"identifier", "override"}:
            continue
        token = source[node.start_byte:node.end_byte]
        if token not in _SUBSTITUTIONS:
            continue
        ancestor = node.parent
        while ancestor is not None and ancestor.type != "ERROR":
            if ancestor.type in {"function_declaration", "statement_block", "string", "template_string", "comment"}:
                break
            ancestor = ancestor.parent
        if ancestor is not None and ancestor.type == "ERROR":
            replacements[node.start_byte, node.end_byte] = _SUBSTITUTIONS[token]
    if not replacements:
        return tree
    parsed = bytearray(source)
    for (start, end), value in replacements.items():
        parsed[start:end] = value
    recovered = parser.parse(bytes(parsed))
    if validate is not None:
        validate(recovered.root_node)
    if recovered.root_node.has_error:
        return tree
    modifiers = {(node.start_byte, node.end_byte) for node in _walk(recovered.root_node)
                 if node.type == "ui_property_modifier" and node.parent.type == "ui_property"}
    return recovered if replacements.keys() <= modifiers else tree


def valid_property_modifiers(root, source):
    """Reject documented mutually exclusive/duplicate override-family syntax."""
    for node in _walk(root):
        if node.type == "ui_property":
            names = [text(child, source) for child in node.named_children
                     if child.type == "ui_property_modifier"]
            if len([name for name in names if name in _OVERRIDE]) > 1:
                return False
    return True


def modifier_fields(modifiers):
    """Source modifiers provide no runtime override/type/provider proof."""
    if _OVERRIDE.intersection(modifiers):
        return {"modifier_status": "source_only", "modifier_reason": "override_semantics_require_engine"}
    return {}
