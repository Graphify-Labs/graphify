"""Original C++ identifier leaves bound annotation-name token recovery.

Byte regular-expression boundaries treat UTF-8 and universal-character names as
ASCII punctuation. The raw parser leaf, before any recovery, owns the complete
identifier and prevents a familiar suffix/prefix from becoming a Qt annotation.
"""
from __future__ import annotations


def identifier_fragment(tree, start, end):
    """Reject only a spelling embedded inside a larger original identifier."""
    leaf = tree.descendant_for_byte_range(start, end)
    return bool(leaf is not None and "identifier" in leaf.type
                and (leaf.start_byte < start or end < leaf.end_byte))
