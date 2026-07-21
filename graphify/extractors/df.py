"""OpenEdge Data Definitions (`.df`) extractor.

Parses Progress/OpenEdge `.df` schema dumps with tree-sitter-df
(https://github.com/usagi-coffee/tree-sitter-df) and emits **table** and
**sequence** nodes, so that ABL code (see abl.py) which references a table via
`FIND` / `FOR EACH` / `DEFINE BUFFER ... FOR` / `CREATE` resolves onto the
schema and the graph is actually connected (code -> schema).

Granularity — TABLE + SEQUENCE only. A single `.df` can hold tens of thousands
of `ADD FIELD` and thousands of `ADD INDEX` statements (gco.df: 31k fields,
4.5k indexes); materialising each as a node would swamp the graph and make it
unreadable. Fields/indexes are instead counted per table and carried on the
owning table's `contains` edge context (and as node attributes).

Node IDs are GLOBAL — `_make_id(name)`, not file-scoped — on purpose:
  - the same table dumped in several `.df` variants (e.g. gco.df + gcow1951.df)
    collapses to a single node by id;
  - an ABL `uses` edge whose target is `_make_id(table_name)` lands on the
    table node directly, with no label-uniqueness requirement.
IDs are casefolded by graphify's `normalize_id`, so ABL's case-insensitive
table names match the `.df` names regardless of casing.

The tree-sitter-df grammar does not know every field/index tuning keyword
(MAX-WIDTH, LENGTH, VIEW-AS, ORDER, ...), so large dumps parse with localized
ERROR nodes inside the tuning bodies. tree-sitter error recovery keeps the
`add_table_statement` / `add_field_statement` / `add_index_statement` /
`add_sequence_statement` structure intact, so the entity names we rely on are
still extracted correctly.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _make_id, _read_text

# The grammar's top node.
_ROOT = "source_code"


def _field(node, name: str):
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def _unquote(node, source: bytes) -> str:
    """Text of a string_literal name node, with surrounding quotes stripped."""
    if node is None:
        return ""
    t = _read_text(node, source).strip()
    if len(t) >= 2 and t[0] in "\"'" and t[-1] == t[0]:
        t = t[1:-1]
    return t.strip()


def extract_df(path: Path) -> dict:
    """Extract tables and sequences (with field/index counts) from a `.df` dump."""
    try:
        import tree_sitter_df as tsdf
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-df not installed"}

    try:
        language = Language(tsdf.language())
        parser = Parser(language)
        source = path.read_bytes()
        root = parser.parse(source).root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, *, shared: bool = False, **extra) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            node = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            }
            # A DB table/sequence is a single logical entity even when several `.df`
            # dumps of the same database (e.g. gco.df + gcow1951.df) redefine it.
            # graphify's `_disambiguate_colliding_node_ids` exempts type=module/
            # namespace from path-salting, so tagging schema nodes `type: "module"`
            # makes same-name entities across dumps COLLAPSE onto one global-id node
            # (make_id(name)) instead of splitting into per-file duplicates — which
            # would otherwise break the unique-label rewire that binds ABL `uses`
            # edges onto the table. `module` (not `namespace`) is kept so the node
            # stays "type-like" and remains a valid rewire target.
            if shared:
                node["type"] = "module"
            node.update(extra)
            nodes.append(node)

    file_nid = _make_id(str_path)
    add_node(file_nid, path.name, 1)

    # ── Single walk: collect tables/sequences and tally fields/indexes ──────────
    tables: dict[str, int] = {}          # table name -> definition line
    sequences: dict[str, int] = {}       # sequence name -> definition line
    field_counts: dict[str, int] = {}    # table name -> nb of ADD FIELD
    index_counts: dict[str, int] = {}    # table name -> nb of ADD INDEX

    def walk(node) -> None:
        t = node.type
        if t == "add_table_statement":
            name = _unquote(_field(node, "table"), source)
            if name and name not in tables:
                tables[name] = node.start_point[0] + 1
        elif t == "add_field_statement":
            tbl = _unquote(_field(node, "table"), source)
            if tbl:
                field_counts[tbl] = field_counts.get(tbl, 0) + 1
        elif t == "add_index_statement":
            tbl = _unquote(_field(node, "table"), source)
            if tbl:
                index_counts[tbl] = index_counts.get(tbl, 0) + 1
        elif t == "add_sequence_statement":
            name = _unquote(_field(node, "sequence"), source)
            if name and name not in sequences:
                sequences[name] = node.start_point[0] + 1
        for child in node.children:
            walk(child)

    walk(root)

    # ── Materialise table nodes (global id) + contains edges ────────────────────
    for name, line in tables.items():
        nid = _make_id(name)  # GLOBAL id: ABL `uses` edges target this exact id.
        nfields = field_counts.get(name, 0)
        nindexes = index_counts.get(name, 0)
        add_node(nid, name, line, shared=True, field_count=nfields, index_count=nindexes)
        edges.append({
            "source": file_nid,
            "target": nid,
            "relation": "contains",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
            "context": f"table ({nfields} fields, {nindexes} indexes)",
        })

    for name, line in sequences.items():
        nid = _make_id(name)
        add_node(nid, name, line, shared=True)
        edges.append({
            "source": file_nid,
            "target": nid,
            "relation": "contains",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
            "context": "sequence",
        })

    return {"nodes": nodes, "edges": edges}
