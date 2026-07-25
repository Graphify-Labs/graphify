"""Sql extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id


def extract_sql(path: Path, content: str | bytes | None = None) -> dict:
    """Extract tables, views, functions, and relationships from .sql/.pkb/.pks files via tree-sitter.

    Supports both tree-sitter-sql (standard SQL) and tree-sitter-plsql (Oracle PL/SQL).
    PL/SQL grammar is tried first, falling back to standard SQL.
    """
    try:
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter not installed. Run: pip install tree-sitter"}

    try:
        import tree_sitter_plsql as tsplsql
        HAS_PLSQL = True
    except ImportError:
        HAS_PLSQL = False
        try:
            import tree_sitter_sql as tssql
        except ImportError:
            return {"nodes": [], "edges": [],
                    "error": "neither tree_sitter_plsql nor tree_sitter_sql installed"}

    try:
        if HAS_PLSQL:
            language = Language(tsplsql.language())
        else:
            language = Language(tssql.language())
        parser = Parser(language)
        source = (
            content.encode("utf-8") if isinstance(content, str)
            else content if content is not None
            else path.read_bytes()
        )
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}


    stem = _file_stem(path)
    str_path = str(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                           "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    table_nids: dict[str, str] = {}  # name → nid for reference resolution

    def _read(n) -> str:
        return source[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

    def _obj_name(n) -> str | None:
        if HAS_PLSQL:
            # PL/SQL grammar uses identifier (not object_reference) for names
            for c in n.children:
                if c.type == "identifier":
                    return _read(c)
        for c in n.children:
            if c.type == "object_reference":
                return _read(c)
        return None

    def _add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                           "source_file": str_path, "source_location": f"L{line}"})
            edges.append({"source": file_nid, "target": nid, "relation": "contains",
                           "confidence": "EXTRACTED", "source_file": str_path,
                           "source_location": f"L{line}", "weight": 1.0})

    def _add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                       "confidence": "EXTRACTED", "source_file": str_path,
                       "source_location": f"L{line}", "weight": 1.0})

    def _walk_from_refs(node, caller_nid: str, line: int) -> None:
        """Recursively find FROM/JOIN table references inside a node."""
        if node.type in ("from", "join"):
            for c in node.children:
                if c.type == "relation":
                    for cc in c.children:
                        if cc.type == "object_reference":
                            tbl = _read(cc)
                            tbl_nid = _make_id(stem, tbl)
                            _add_edge(caller_nid, tbl_nid, "reads_from",
                                      c.start_point[0] + 1)

        # PL/SQL: walk into sql_statement_* nodes for table references
        if HAS_PLSQL and node.type.startswith("sql_statement_"):
            _walk_plsql_sql_stmt(node, caller_nid, line)

        for child in node.children:
            _walk_from_refs(child, caller_nid, line)

    def _walk_plsql_sql_stmt(node, caller_nid: str, line: int) -> None:
        """Extract table references from PL/SQL SQL statement nodes.

        PL/SQL wraps SQL statements in sql_statement_select/insert/update/delete/merge
        nodes. Table references are inside table_list > table_list_element > referenced_element > identifier.
        Also handles INTO clause (INSERT target table) and UPDATE target table.
        """
        t = node.type

        if t == "sql_statement_select":
            for child in node.children:
                if child.type == "kw_from":
                    # Walk for table_list
                    for sibling in node.children:
                        if sibling.type == "table_list":
                            for tbl_elem in sibling.children:
                                if tbl_elem.type == "table_list_element":
                                    for ref in tbl_elem.children:
                                        if ref.type == "referenced_element":
                                            for id_node in ref.children:
                                                if id_node.type == "identifier":
                                                    tbl = _read(id_node)
                                                    tbl_nid = _make_id(stem, tbl)
                                                    _add_edge(caller_nid, tbl_nid, "reads_from",
                                                              id_node.start_point[0] + 1)

        elif t in ("sql_statement_insert", "sql_statement_update", "sql_statement_delete"):
            # INSERT/UPDATE/DELETE — extract target table and FROM references
            for child in node.children:
                if child.type == "single_table_insert":
                    for sub in child.children:
                        if sub.type == "referenced_element":
                            for id_node in sub.children:
                                if id_node.type == "identifier":
                                    tbl = _read(id_node)
                                    tbl_nid = _make_id(stem, tbl)
                                    _add_edge(caller_nid, tbl_nid, "reads_from",
                                              id_node.start_point[0] + 1)
                        elif sub.type == "kw_from":
                            # Subquery FROM inside INSERT ... SELECT
                            for sibling in child.children:
                                if sibling.type == "table_list":
                                    _walk_plsql_table_list(sibling, caller_nid)
                elif child.type == "referenced_element":
                    for id_node in child.children:
                        if id_node.type == "identifier":
                            tbl = _read(id_node)
                            tbl_nid = _make_id(stem, tbl)
                            _add_edge(caller_nid, tbl_nid, "reads_from",
                                      id_node.start_point[0] + 1)

    def _walk_plsql_table_list(node, caller_nid: str) -> None:
        """Walk a table_list node for table references."""
        for tbl_elem in node.children:
            if tbl_elem.type == "table_list_element":
                for ref in tbl_elem.children:
                    if ref.type == "referenced_element":
                        for id_node in ref.children:
                            if id_node.type == "identifier":
                                tbl = _read(id_node)
                                tbl_nid = _make_id(stem, tbl)
                                _add_edge(caller_nid, tbl_nid, "reads_from",
                                          id_node.start_point[0] + 1)

    def _plsql_create_table_name(node) -> str | None:
        """Get table name from PL/SQL CREATE TABLE (uses identifier child)."""
        for c in node.children:
            if c.type == "identifier":
                return _read(c)
        return None

    def _plsql_extract_references(node, tbl_nid: str, line: int) -> None:
        """Extract REFERENCES edges from PL/SQL CREATE TABLE columns/constraints."""
        seen_refs: set[str] = set()

        for child in node.children:
            if child.type == "table_element":
                for sub in child.children:
                    if sub.type == "table_column_definition":
                        # Inline REFERENCES — PL/SQL grammar may produce ERROR here,
                        # fall back to regex.
                        ref_text = _read(sub)
                        for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", ref_text, re.IGNORECASE):
                            ref_name = rm.group(1)
                            if ref_name.lower() not in seen_refs:
                                seen_refs.add(ref_name.lower())
                                ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                _add_edge(tbl_nid, ref_nid, "references", line)

                    elif sub.type == "table_constraint":
                        for constraint in sub.children:
                            if constraint.type == "table_constraint_foreign_key":
                                ref_name = None
                                found_ref = False
                                for cc in constraint.children:
                                    if cc.type == "kw_references":
                                        found_ref = True
                                    elif found_ref and cc.type == "referenced_element":
                                        for id_node in cc.children:
                                            if id_node.type == "identifier":
                                                ref_name = _read(id_node)
                                                break
                                        if ref_name:
                                            break
                                if ref_name and ref_name.lower() not in seen_refs:
                                    seen_refs.add(ref_name.lower())
                                    ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                    _add_edge(tbl_nid, ref_nid, "references", line)

    def walk(node) -> None:
        t = node.type
        line = node.start_point[0] + 1

        if t == "create_table":
            if HAS_PLSQL:
                name = _plsql_create_table_name(node)
            else:
                name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[name.lower()] = nid

            if HAS_PLSQL:
                # PL/SQL table structure: table_element > table_column_definition / table_constraint
                _plsql_extract_references(node, nid, line)
            else:
                # Standard SQL structure
                for col in node.children:
                    if col.type == "column_definitions":
                        has_error = any(cd.type == "ERROR" for cd in col.children)
                        seen_refs: set[str] = set()
                        for cd in col.children:
                            if cd.type == "column_definition":
                                # Inline column-level REFERENCES
                                ref_name: str | None = None
                                found_ref = False
                                for cc in cd.children:
                                    if cc.type == "keyword_references":
                                        found_ref = True
                                    elif found_ref and cc.type == "object_reference":
                                        ref_name = _read(cc)
                                        break
                                if ref_name:
                                    ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                    _add_edge(nid, ref_nid, "references", line)
                                    seen_refs.add(ref_name.lower())
                            elif cd.type == "constraints":
                                # Table-level FOREIGN KEY ... REFERENCES ... constraints
                                for constraint in cd.children:
                                    if constraint.type != "constraint":
                                        continue
                                    ref_name = None
                                    found_ref = False
                                    for cc in constraint.children:
                                        if cc.type == "keyword_references":
                                            found_ref = True
                                        elif found_ref and cc.type == "object_reference":
                                            ref_name = _read(cc)
                                            break
                                    if ref_name:
                                        ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                        _add_edge(nid, ref_nid, "references", line)
                                        seen_refs.add(ref_name.lower())
                        if has_error:
                            # Dialect-specific syntax (e.g. Firebird COMPUTED BY) causes ERROR
                            # nodes that make the parser drop the trailing constraints block.
                            # Regex-scan the raw column_definitions text as fallback.
                            col_text = _read(col)
                            for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", col_text, re.IGNORECASE):
                                ref_name = rm.group(1)
                                if ref_name.lower() not in seen_refs:
                                    ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
                                    _add_edge(nid, ref_nid, "references", line)
                                    seen_refs.add(ref_name.lower())

        elif t == "create_view":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[name.lower()] = nid
                # FROM/JOIN table references inside view body
                _walk_from_refs(node, nid, line)

        elif t == "create_function":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", line)
                _walk_from_refs(node, nid, line)

        elif t == "create_procedure":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", line)
                _walk_from_refs(node, nid, line)

        elif t == "alter_table":
            name = _obj_name(node)
            if name:
                src_nid = table_nids.get(name.lower())
                if not src_nid:
                    src_nid = _make_id(stem, name)
                    _add_node(src_nid, name, line)
                    table_nids[name.lower()] = src_nid
                for child in node.children:
                    if child.type == "add_constraint":
                        for cc in child.children:
                            if cc.type != "constraint":
                                continue
                            found_ref = False
                            ref_name: str | None = None
                            for ccc in cc.children:
                                if ccc.type == "keyword_references":
                                    found_ref = True
                                elif found_ref and ccc.type == "object_reference":
                                    ref_name = _read(ccc)
                                    break
                            if ref_name:
                                ref_nid = table_nids.get(ref_name.lower())
                                if not ref_nid:
                                    ref_nid = _make_id(stem, ref_name)
                                _add_edge(src_nid, ref_nid, "references", line)

        elif t == "create_trigger":
            trig_name: str | None = None
            tbl_name: str | None = None
            after_trigger = False
            after_for = False
            for c in node.children:
                if c.type == "keyword_trigger":
                    after_trigger = True
                elif after_trigger and not trig_name and c.type == "object_reference":
                    trig_name = _read(c)
                elif c.type == "keyword_for":
                    after_for = True
                elif after_for and not tbl_name and c.type == "object_reference":
                    tbl_name = _read(c)
            if trig_name:
                trig_nid = _make_id(stem, trig_name)
                _add_node(trig_nid, trig_name, line)
                if tbl_name:
                    tbl_nid = table_nids.get(tbl_name.lower()) or _make_id(stem, tbl_name)
                    _add_edge(trig_nid, tbl_nid, "triggers", line)

        # ── PL/SQL-specific node types ──────────────────────────────────────
        elif HAS_PLSQL and t == "create_package":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[name.lower()] = nid
                # Walk children for function/procedure/type/cursor declarations
                _walk_from_refs(node, nid, line)

        elif HAS_PLSQL and t == "create_package_body":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[name.lower()] = nid
                _walk_from_refs(node, nid, line)

        elif HAS_PLSQL and t in ("function_declaration", "function_definition"):
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", line)
                _walk_from_refs(node, nid, line)

        elif HAS_PLSQL and t in ("procedure_declaration", "procedure_definition"):
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", line)
                _walk_from_refs(node, nid, line)

        elif HAS_PLSQL and t in (
            "cursor_definition",
            "type_definition_ref_cursor",
            "type_definition_record",
            "type_definition_collection",
            "type_definition_sub",
        ):
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)

        # ── End PL/SQL-specific nodes ───────────────────────────────────────

        elif t == "ERROR":
            # tree-sitter-sql cannot parse PL/pgSQL CREATE FUNCTION/PROCEDURE
            # bodies (OUT/INOUT params, tagged dollar quotes, PERFORM, :=) and
            # emits an ERROR node instead, silently dropping the object.
            # Regex-scan the raw text as fallback, mirroring the
            # fb_proc_or_trigger recovery below. One ERROR blob can swallow
            # several statements, so scan for every CREATE in it. We deliberately
            # do not scan the body for FROM/JOIN references: PL/pgSQL loop
            # variables and locals would produce junk reads_from targets.
            text = _read(node)
            for m in re.finditer(
                r"CREATE\s+(?:OR\s+REPLACE\s+)?(?:FUNCTION|PROCEDURE)\s+([\w$.]+)",
                text, re.IGNORECASE,
            ):
                name = m.group(1)
                m_line = line + text[: m.start()].count("\n")
                nid = _make_id(stem, name)
                _add_node(nid, f"{name}()", m_line)

        elif t == "fb_proc_or_trigger":
            text = _read(node)
            m = re.match(
                r"CREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?"
                r"(PROCEDURE|TRIGGER|FUNCTION)\s+([\w$]+)",
                text, re.IGNORECASE,
            )
            if m:
                obj_type = m.group(1).upper()
                obj_name = m.group(2)
                obj_nid = _make_id(stem, obj_name)
                label = obj_name if obj_type == "TRIGGER" else f"{obj_name}()"
                _add_node(obj_nid, label, line)
                if obj_type == "TRIGGER":
                    fm = re.search(r"\bFOR\s+([\w$]+)", text, re.IGNORECASE)
                    if fm:
                        tbl = fm.group(1)
                        tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                        _add_edge(obj_nid, tbl_nid, "triggers", line)
                _NON_TABLES = {
                    "select", "where", "set", "dual", "null", "true", "false",
                    "first", "skip", "rows", "next", "only", "lateral",
                }
                seen_tbls: set[str] = set()
                for rm in re.finditer(r"\b(?:FROM|JOIN|INTO)\s+([\w$]+)", text, re.IGNORECASE):
                    tbl = rm.group(1)
                    if tbl.lower() not in _NON_TABLES and tbl.lower() not in seen_tbls:
                        seen_tbls.add(tbl.lower())
                        tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                        _add_edge(obj_nid, tbl_nid, "reads_from", line)
                for rm in re.finditer(r"\bUPDATE\s+([\w$]+)", text, re.IGNORECASE):
                    tbl = rm.group(1)
                    if tbl.lower() not in _NON_TABLES and tbl.lower() not in seen_tbls:
                        seen_tbls.add(tbl.lower())
                        tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                        _add_edge(obj_nid, tbl_nid, "reads_from", line)

        for child in node.children:
            walk(child)

    for stmt in root.children:
        if stmt.type == "statement":
            for child in stmt.children:
                walk(child)
        elif stmt.type in ("fb_proc_or_trigger", "set_term", "declare_external_function", "ERROR"):
            walk(stmt)
        elif HAS_PLSQL:
            # PL/SQL grammar: top-level nodes have no "statement" wrapper
            walk(stmt)

    # Global regex fallback: catch any REFERENCES missed due to ERROR nodes in the parse tree
    # (e.g. Firebird COMPUTED BY columns push constraints out of the tree entirely).
    # Snapshot after tree walk so we don't re-emit edges already captured above.
    emitted = {(e["source"], e["target"]) for e in edges if e["relation"] == "references"}
    src_text = source.decode("utf-8", errors="replace")
    for m in re.finditer(r"CREATE\s+TABLE\s+([\w$]+)\s*\(", src_text, re.IGNORECASE):
        tbl_name = m.group(1)
        tbl_nid = table_nids.get(tbl_name.lower())
        if tbl_nid is None:
            continue
        tbl_line = src_text[: m.start()].count("\n") + 1
        tail = src_text[m.start():]
        end = re.search(r"(?:^|\n)(?:CREATE|SET\s+TERM|ALTER)\s", tail[1:], re.IGNORECASE)
        block = tail[: end.start() + 1] if end else tail
        for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", block, re.IGNORECASE):
            ref_name = rm.group(1)
            ref_nid = table_nids.get(ref_name.lower()) or _make_id(stem, ref_name)
            if (tbl_nid, ref_nid) not in emitted:
                _add_edge(tbl_nid, ref_nid, "references", tbl_line)
                emitted.add((tbl_nid, ref_nid))

    # ── PL/SQL regex fallback for SQL*Plus extracts ────────────────────────
    # These files start with PACKAGE BODY name (no CREATE OR REPLACE), which
    # the PL/SQL grammar doesn't recognize as package headers. Use regex to
    # recover package/procedure/function/cursor/type nodes and table references.
    if HAS_PLSQL:
        src_text = source.decode("utf-8", errors="replace")

        # 1. Package / Package Body declarations
        for m in re.finditer(
            r"PACKAGE\s+(?:BODY\s+)?(\w+)\s+(?:IS|AS)",
            src_text, re.IGNORECASE,
        ):
            name = m.group(1)
            nid = _make_id(stem, name)
            pkg_line = src_text[: m.start()].count("\n") + 1
            _add_node(nid, name, pkg_line)

        # 2. Procedure declarations (outside BEGIN/END blocks)
        _NON_TABLES = {
            "select", "where", "null", "true", "false",
            "first", "rows", "next", "only",
        }
        seen_proc_func: set[str] = set()
        for m in re.finditer(
            r"(?:^|\n)\s*(?:PROCEDURE|FUNCTION)\s+(\w+)",
            src_text, re.IGNORECASE,
        ):
            name = m.group(1)
            if name.upper() in _NON_TABLES or name.lower() in seen_proc_func:
                continue
            seen_proc_func.add(name.lower())
            nid = _make_id(stem, name)
            func_line = src_text[: m.start()].count("\n") + 1
            _add_node(nid, f"{name}()", func_line)

        # 3. Cursor definitions
        seen_cursors: set[str] = set()
        for m in re.finditer(
            r"CURSOR\s+(\w+)\s+IS",
            src_text, re.IGNORECASE,
        ):
            name = m.group(1)
            if name.lower() in seen_cursors:
                continue
            seen_cursors.add(name.lower())
            nid = _make_id(stem, name)
            cur_line = src_text[: m.start()].count("\n") + 1
            _add_node(nid, name, cur_line)

        # 4. Type definitions (TYPE name IS REF CURSOR | RECORD | TABLE OF | SUBTYPE)
        seen_types: set[str] = set()
        for m in re.finditer(
            r"(?:TYPE|SUBTYPE)\s+(\w+)\s+IS",
            src_text, re.IGNORECASE,
        ):
            name = m.group(1)
            if name.lower() in seen_types:
                continue
            seen_types.add(name.lower())
            nid = _make_id(stem, name)
            type_line = src_text[: m.start()].count("\n") + 1
            _add_node(nid, name, type_line)

        # 5. FROM/JOIN/INTO table references (heavy regex, only if we found packages)
        em_reade = {(e["source"], e["target"]) for e in edges if e["relation"] == "reads_from"}
        has_pkg = any(n.get("label", "") for n in nodes if n["id"] != file_nid)
        if has_pkg:
            for m in re.finditer(r"\b(?:FROM|JOIN)\s+(\w+)", src_text, re.IGNORECASE):
                # Heuristic: only include if it looks like a table (not a keyword or variable)
                tbl = m.group(1)
                if tbl.upper() in _NON_TABLES or len(tbl) <= 2:
                    continue
                tbl_nid = table_nids.get(tbl.lower()) or _make_id(stem, tbl)
                if tbl_nid not in seen_ids:
                    # Don't create new nodes for table refs — just emit the edge
                    pass
                # Find the nearest package/procedure node as the caller
                tbl_line = src_text[: m.start()].count("\n") + 1
                for node in reversed(nodes):
                    if node["id"] != file_nid:
                        caller_nid = node["id"]
                        if (caller_nid, tbl_nid) not in em_reade:
                            em_reade.add((caller_nid, tbl_nid))
                            _add_edge(caller_nid, tbl_nid, "reads_from", tbl_line)
                        break

    return {"nodes": nodes, "edges": edges}
