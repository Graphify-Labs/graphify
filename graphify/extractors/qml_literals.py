"""Plain source literal evidence for static C++ objectName/property joins."""
from __future__ import annotations

import json


def literal_fields(syntax, source):
    if syntax and syntax.type == "expression_statement" and len(syntax.named_children) == 1:
        syntax = syntax.named_children[0]
    if syntax is None or syntax.type != "string":
        return {}
    value = source[syntax.start_byte:syntax.end_byte].decode()
    try:
        decoded = json.loads(value) if value.startswith('"') else value[1:-1] if value.startswith("'") and "\\" not in value else None
    except ValueError:
        return {}
    return {"literal_value": decoded} if isinstance(decoded, str) and len(decoded.encode()) <= 256 else {}
