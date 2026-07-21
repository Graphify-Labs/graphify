"""OpenEdge ABL (Progress 4GL) extractor.

Parses `.p`, `.w`, `.i`, `.cls` sources with tree-sitter-abl and emits the same
node/edge shape as the other language extractors (see extractors/go.py for the
canonical pattern).

Structural nodes:
  - file node
  - class_definition / interface_definition (with super -> inherits, interface -> implements)
  - procedure_definition (internal procedures)
  - function_definition / function_forward_definition
  - method / constructor / destructor / property / event definitions (members of the class)

Relationship edges:
  - RUN <proc>                -> calls (internal proc) or runs (external .p program)
  - <fn>(...)                 -> calls (user function)
  - USING <type>              -> imports_from (a class)
  - { include.i }             -> includes (an include file)
  - FIND/FOR/BUFFER/CREATE t  -> uses (a DB table; resolves onto a df.py node)
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text

# The grammar's top node.
_ROOT = "source_code"

# Class-member definition node types, walked with the enclosing class as scope.
_MEMBER_DEFS = {
    "method_definition",
    "constructor_definition",
    "destructor_definition",
    "property_definition",
    "event_definition",
}

# Every routine/type definition node. Call-scanning skips these during recursion
# because each one is scanned separately with its own node as the caller.
_DEF_NODES = _MEMBER_DEFS | {
    "class_definition",
    "interface_definition",
    "procedure_definition",
    "function_definition",
    "function_forward_definition",
}


def _name_text(node, source: bytes) -> str:
    """Full source text of a name node (identifier / qualified_name / scoped_name / ...)."""
    if node is None:
        return ""
    return _read_text(node, source).strip()


def _field(node, name: str):
    try:
        return node.child_by_field_name(name)
    except Exception:
        return None


def _first_identifier(node, source: bytes) -> str:
    """Fallback: first identifier-ish descendant text, for nodes with no `name` field."""
    stack = list(node.children)
    while stack:
        c = stack.pop(0)
        if c.type in ("identifier", "qualified_name", "scoped_name", "procedure_name",
                      "nested_type_name", "type_name"):
            return _read_text(c, source).strip()
        stack.extend(c.children)
    return ""


def extract_abl(path: Path) -> dict:
    """Extract classes, procedures, functions, methods, and RUN/USING/include edges."""
    try:
        import tree_sitter_abl as tsabl
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-abl not installed"}

    try:
        language = Language(tsabl.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    # (nid, body_node) pairs to scan later for call/run/function_call edges.
    routine_bodies: list[tuple[str, object]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def stub_node(name: str, line: int) -> str:
        """SOURCELESS stub for a cross-file reference target, so the corpus-level
        rewire can collapse it onto the real definition (see go.py ensure_named_node)."""
        nid = _make_id(name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return nid

    def walk(node, class_nid: str | None) -> None:
        t = node.type

        if t in ("class_definition", "interface_definition"):
            name_node = _field(node, "name")
            cname = _name_text(name_node, source) or _first_identifier(node, source) or stem
            line = node.start_point[0] + 1
            cnid = _make_id(stem, cname)
            add_node(cnid, cname, line)
            add_edge(file_nid, cnid, "contains", line)
            # Inheritance / interfaces.
            super_node = _field(node, "super")
            if super_node is not None:
                sname = _name_text(super_node, source)
                if sname:
                    add_edge(cnid, stub_node(sname, line), "inherits", line, context="super")
            iface_node = _field(node, "interface")
            if iface_node is not None:
                iname = _name_text(iface_node, source)
                if iname:
                    add_edge(cnid, stub_node(iname, line), "implements", line, context="interface")
            for child in node.children:
                walk(child, cnid)
            return

        if t == "procedure_definition":
            name_node = _field(node, "name")
            pname = _name_text(name_node, source) or _first_identifier(node, source)
            if pname:
                line = node.start_point[0] + 1
                pnid = _make_id(stem, pname)
                add_node(pnid, f"{pname}()", line)
                add_edge(file_nid, pnid, "contains", line)
                body = _field(node, "body") or node
                routine_bodies.append((pnid, body))
            return

        if t in ("function_definition", "function_forward_definition"):
            name_node = _field(node, "name")
            fname = _name_text(name_node, source) or _first_identifier(node, source)
            if fname:
                line = node.start_point[0] + 1
                fnid = _make_id(stem, fname)
                add_node(fnid, f"{fname}()", line)
                add_edge(file_nid, fnid, "contains", line)
                if t == "function_definition":
                    routine_bodies.append((fnid, node))
            return

        if t in _MEMBER_DEFS:
            name_node = _field(node, "name")
            mname = _name_text(name_node, source) or _first_identifier(node, source)
            line = node.start_point[0] + 1
            if t == "constructor_definition":
                mname = mname or "constructor"
            elif t == "destructor_definition":
                mname = mname or "destructor"
            if mname:
                parent = class_nid or file_nid
                mnid = _make_id(parent, mname)
                add_node(mnid, f".{mname}()", line)
                add_edge(parent, mnid, "method" if class_nid else "contains", line)
                body = _field(node, "body") or node
                if t in ("method_definition", "constructor_definition", "destructor_definition",
                         "property_definition", "event_definition"):
                    routine_bodies.append((mnid, body))
            return

        # File-level USING / include references (not inside a routine body).
        if t in ("using_statement", "using_phrase"):
            tname = _first_identifier(node, source)
            if tname:
                add_edge(file_nid, stub_node(tname, node.start_point[0] + 1),
                         "imports_from", node.start_point[0] + 1, context="using")
            return

        if t == "include_file_reference":
            file_field = _field(node, "file")
            inc = _name_text(file_field, source) if file_field is not None else _first_identifier(node, source)
            if inc:
                inc = inc.strip("{}").strip()
                add_edge(file_nid, stub_node(inc, node.start_point[0] + 1),
                         "includes", node.start_point[0] + 1, context="include")
            return

        for child in node.children:
            walk(child, class_nid)

    walk(root, None)

    # ── Call / RUN resolution, scanning each routine body ──────────────────────
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    # ── Table (schema) references ──────────────────────────────────────────────
    # DB table refs surface as identifier-typed `table`/`record` fields on
    # find/for/create/buffer/delete statements, plus `like` on LIKE phrases.
    # These `uses` edges target stub_node(table) whose global id == the `.df`
    # extractor's table id (both make_id(name)), so they collapse onto the real
    # schema node (see df.py). Temp/work-tables defined in this file are NOT DB
    # tables, so we gather and exclude them to avoid phantom schema nodes.
    _TABLE_REF_FIELDS = ("table", "record", "like")
    temp_tables: set[str] = set()

    def _collect_temp_tables(node) -> None:
        if node.type in ("temp_table_definition", "work_table_definition"):
            nm = _name_text(_field(node, "name"), source)
            if nm:
                temp_tables.add(nm.casefold())
        for child in node.children:
            _collect_temp_tables(child)

    _collect_temp_tables(root)

    seen_table_pairs: set[tuple[str, str]] = set()

    def emit_table_ref(node, caller_nid: str) -> None:
        for fname in _TABLE_REF_FIELDS:
            fnode = _field(node, fname)
            if fnode is None or fnode.type != "identifier":
                continue
            tname = _read_text(fnode, source).strip()
            if not tname or tname.casefold() in temp_tables:
                continue
            pair = (caller_nid, tname.casefold())
            if pair in seen_table_pairs:
                continue
            seen_table_pairs.add(pair)
            add_edge(caller_nid, stub_node(tname, node.start_point[0] + 1),
                     "uses", node.start_point[0] + 1, context="table")

    def emit_call(node, caller_nid: str) -> None:
        t = node.type
        callee: str | None = None
        relation = "calls"
        if t == "run_statement":
            proc = _field(node, "procedure")
            if proc is not None:
                callee = _name_text(proc, source)
                # RUN of a file path (foo.p / "foo.p") is an external program.
                if callee and (callee.lower().endswith((".p", ".w", ".r")) or '"' in callee or "'" in callee):
                    relation = "runs"
        elif t == "run_procedure_phrase":
            proc = _field(node, "procedure")
            if proc is not None:
                callee = _name_text(proc, source)
                relation = "runs"
        elif t == "function_call":
            fn = _field(node, "function")
            if fn is not None:
                callee = _name_text(fn, source)

        if not callee:
            return
        callee = callee.strip().strip("\"'").strip()
        # For qualified/object access keep the last segment as the call label.
        simple = callee.replace(":", ".").rsplit(".", 1)[-1] if callee else callee
        if not simple:
            return
        tgt_nid = label_to_nid.get(simple) or label_to_nid.get(callee)
        if tgt_nid and tgt_nid != caller_nid:
            pair = (caller_nid, tgt_nid)
            if pair not in seen_call_pairs:
                seen_call_pairs.add(pair)
                add_edge(caller_nid, tgt_nid, relation, node.start_point[0] + 1, context=relation)
        else:
            raw_calls.append({
                "caller_nid": caller_nid,
                "callee": simple,
                "relation": relation,
                "source_file": str_path,
                "source_location": f"L{node.start_point[0] + 1}",
            })

    def walk_calls(node, caller_nid: str) -> None:
        for child in node.children:
            # Nested routine/type definitions are scanned with their own caller;
            # skip them here so their calls aren't misattributed to this scope.
            if child.type in _DEF_NODES:
                continue
            emit_call(child, caller_nid)
            emit_table_ref(child, caller_nid)
            walk_calls(child, caller_nid)

    # Each definition's own body, attributed to that routine.
    for caller_nid, body_node in routine_bodies:
        walk_calls(body_node, caller_nid)
    # Top-level program body of a procedural .p/.w (statements outside any
    # definition): attribute RUN/function calls to the file node itself.
    walk_calls(root, file_nid)

    # Drop edges pointing at nodes we never materialised (defensive, matches go.py).
    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports_from", "includes", "runs")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
