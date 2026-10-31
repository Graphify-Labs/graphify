"""Literal provider expression provenance rooted in one lexical declaration."""
from __future__ import annotations

import re

from graphify.extractors.qt_cpp_api_shape import api_shape


def provider_expression(expression, identities, types, position):
    """Bounded zero-argument public API chains never execute a getter or factory."""
    match = re.fullmatch(r"\s*&?\s*(this|[A-Za-z_]\w*)((?:\s*(?:->|\.)\s*[A-Za-z_]\w*\s*(?:\(\s*\))?)*)\s*", expression)
    if not match or len(expression.encode()) > 384:
        return {}
    reference = match[1]
    steps = [{"operator": item[1], "name": item[2], "role": "call" if item[3] else "field"}
             for item in re.finditer(r"(->|\.)\s*([A-Za-z_]\w*)\s*(\(\s*\))?", match[2])]
    if len(steps) > 8:
        return {}
    spelling, declared_at = identities.declared_type_binding(reference, position)
    if reference == "this":
        owner = identities.mapping.owner_at(position)
        spelling, declared_at = (owner.get("class_name", "") + "*", owner["span"]["start_byte"]) if owner else ("", position)
    shape = api_shape(spelling, allow_value=True)
    ids, reason = types.resolve_class(shape[0], declared_at) if shape else ([], "provider_type_shape_unsupported")
    return {"provider_reference": reference, "provider_expression_steps": steps,
            "provider_root_type_spelling": spelling, "provider_root_address_of": expression.lstrip().startswith("&"),
            "provider_root_type_id": ids[0] if len(ids) == 1 and not reason else "",
            "provider_type_reason": reason,
            "provider_type_status": "resolved" if len(ids) == 1 and not reason else "unsupported" if not shape else "unavailable"}
