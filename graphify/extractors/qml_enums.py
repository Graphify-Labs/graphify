"""Source-owned QML enum values; literal admission never evaluates JavaScript."""
from __future__ import annotations

import re

from graphify.extractors.qml_facts import field, qml_metadata, text


def _integer(syntax, source):
    """Keep unsupported, fractional and out-of-range values explicitly uncertain."""
    raw = text(syntax, source).strip()
    if not re.fullmatch(r"[+-]?(?:0[xX][0-9a-fA-F]+|0[bB][01]+|0[oO][0-7]+|0|[1-9][0-9]*)", raw):
        return None
    sign, digits = (-1, raw[1:]) if raw.startswith("-") else (1, raw.lstrip("+"))
    value = sign * int(digits, 0 if digits[:2].lower() in {"0x", "0b", "0o"} else 10)
    return value if -(2**31) <= value < 2**31 else None


def add_enum_members(facts, syntax, owner):
    """Each value has an enum owner and stable identity, even for duplicate names.

    Implicit progression resumes only from a supported explicit integer. Unknown
    expressions cannot silently turn the next declaration into a guessed value.
    """
    body = syntax.child_by_field_name("body")
    metadata = qml_metadata(owner)
    next_value = 0
    for item in body.named_children if body else ():
        if item.type not in {"identifier", "enum_assignment"}:
            continue
        value_syntax = item.child_by_field_name("value")
        name = field(item, "name", facts.source) if value_syntax else text(item, facts.source)
        value = _integer(value_syntax, facts.source) if value_syntax else next_value
        if value is not None and not -(2**31) <= value < 2**31:
            value = None
        facts.add("enum_member", name, item, owner,
                  semantic_key=f"{owner['id']}:{name}", owner_id=owner["id"], enum_id=owner["id"],
                  enum_name=metadata["raw_name"], component_key=metadata["component_key"],
                  object_scope_key=metadata["object_scope_key"],
                  name_valid=name[:1].isupper() and metadata["raw_name"][:1].isupper(),
                  explicit_value=value_syntax is not None, value_expression=text(value_syntax, facts.source),
                  value=value, value_status="resolved" if value is not None else "unsupported")
        next_value = value + 1 if value is not None else None
