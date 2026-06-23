"""GraphQL SDL extractor for graphify.

Parses a single ``.graphqls`` / ``.graphql`` schema file into graphify's
per-file ``{"nodes": [...], "edges": [...]}`` shape, using graphql-core as the
parser (tree-sitter has no GraphQL grammar).

Extracted node kinds (stored in the ``type`` field):
  gql_type, gql_input, gql_interface, gql_enum, gql_scalar, gql_union,
  gql_field, gql_input_field, gql_enum_value, gql_operation

Edges:
  <type>   --contains-->   <field>
  <field>  --references--> <named type of the field>
  <op>     --references--> <argument input type>
  <op>     --returns-->    <return type>

Wired into extract.py via ``_get_extractor`` for the .graphqls/.graphql suffixes.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    from graphql import parse
    from graphql.language import ast as _A
    _HAVE_GRAPHQL = True
except Exception:  # graphql-core not installed — degrade to no-op
    _HAVE_GRAPHQL = False

ROOT_OPS = {"Mutation", "Query", "Subscription"}


def _nid(*parts: str) -> str:
    return "gql_" + "_".join(p.lower() for p in parts if p)


def _unwrap(t) -> str | None:
    """NonNull/List wrapper -> underlying named type name."""
    while isinstance(t, (_A.NonNullTypeNode, _A.ListTypeNode)):
        t = t.type
    return t.name.value if isinstance(t, _A.NamedTypeNode) else None


def _line(node) -> int:
    try:
        return node.loc.start_token.line
    except Exception:
        return 1


def extract_graphql_sdl(path: Path) -> dict[str, Any]:
    """Per-file extractor: parse one SDL file into graphify nodes/edges."""
    if not _HAVE_GRAPHQL:
        return {"nodes": [], "edges": [], "error": "graphql-core not installed"}
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"read error: {exc}"}
    try:
        doc = parse(text)
    except Exception as exc:  # malformed SDL must not abort extraction
        return {"nodes": [], "edges": [], "error": f"graphql parse error: {exc}"}

    sp = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()

    def node(_id: str, label: str, line: int, kind: str) -> str:
        if _id not in seen:
            seen.add(_id)
            nodes.append({
                "id": _id,
                "label": label,
                "file_type": "code",
                "type": kind,
                "source_file": sp,
                "source_location": f"L{line}",
            })
        return _id

    def edge(src: str, dst: str | None, relation: str, line: int) -> None:
        if dst is None:
            return
        edges.append({
            "source": src,
            "target": dst,
            "relation": relation,
            "source_file": sp,
            "source_location": f"L{line}",
        })

    def fields(type_id: str, type_name: str, field_nodes, kind: str) -> None:
        for fld in field_nodes or []:
            fname = fld.name.value
            fid = node(_nid(type_name, fname), f"{type_name}.{fname}", _line(fld), kind + "_field")
            edge(type_id, fid, "contains", _line(fld))
            edge(fid, _maybe(_unwrap(fld.type)), "references", _line(fld))

    def _maybe(name: str | None) -> str | None:
        return _nid(name) if name else None

    def operations(field_nodes) -> None:
        for op in field_nodes or []:
            oid = node(_nid("op", op.name.value), op.name.value, _line(op), "gql_operation")
            for arg in getattr(op, "arguments", []) or []:
                edge(oid, _maybe(_unwrap(arg.type)), "references", _line(op))
            edge(oid, _maybe(_unwrap(op.type)), "returns", _line(op))

    for d in doc.definitions:
        if isinstance(d, (_A.ObjectTypeDefinitionNode, _A.ObjectTypeExtensionNode,
                          _A.InterfaceTypeDefinitionNode)):
            name = d.name.value
            if name in ROOT_OPS:
                operations(d.fields)
            else:
                tid = node(_nid(name), name, _line(d), "gql_type")
                fields(tid, name, d.fields, "gql")
        elif isinstance(d, (_A.InputObjectTypeDefinitionNode, _A.InputObjectTypeExtensionNode)):
            name = d.name.value
            tid = node(_nid(name), name, _line(d), "gql_input")
            fields(tid, name, d.fields, "gql_input")
        elif isinstance(d, _A.EnumTypeDefinitionNode):
            name = d.name.value
            tid = node(_nid(name), name, _line(d), "gql_enum")
            for v in d.values or []:
                vid = node(_nid(name, v.name.value), f"{name}.{v.name.value}", _line(v), "gql_enum_value")
                edge(tid, vid, "contains", _line(v))
        elif isinstance(d, _A.UnionTypeDefinitionNode):
            name = d.name.value
            tid = node(_nid(name), name, _line(d), "gql_union")
            for m in d.types or []:
                edge(tid, _nid(m.name.value), "references", _line(d))
        elif isinstance(d, _A.ScalarTypeDefinitionNode):
            node(_nid(d.name.value), d.name.value, _line(d), "gql_scalar")

    return {"nodes": nodes, "edges": edges}
