"""Sql extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id

# Recovers CREATE FUNCTION/PROCEDURE statements the grammar could not parse
# structurally. Used by BOTH recovery sites — the walk-time ERROR-node scan and
# the whole-file has_error fallback (#2180). They MUST share one pattern: when
# they disagreed, the same statement produced two nodes with different names
# (the ERROR scan captured `dbo.[usp_Mixed]`, the fallback stopped at `dbo`,
# and _add_node's id-dedupe never fired because the ids differed).
#
# Each name part is a bare identifier, a double-quoted (delimited) one, or a
# T-SQL bracket-delimited one, so CREATE OR REPLACE FUNCTION "public"."fn"(...)
# and CREATE PROCEDURE [dbo].[usp_Load] ... are both recovered. A bare [\w$.]+
# stops dead at the leading delimiter, which silently dropped every quoted
# PL/pgSQL routine (#2180) and every bracket-named T-SQL procedure. T-SQL's
# AS BEGIN...END body idiom always lands in recovery — the grammar has no
# create_procedure parse for it — and T-SQL spells re-creation CREATE OR ALTER
# (it has no OR REPLACE), so accept that form too, mirroring fb_proc_or_trigger.
# Inside a bracket-delimited part, a literal ] is escaped by doubling
# ([a]]b] names the identifier a]b), so consume ]] before treating a
# lone ] as the closing delimiter — stopping at the first ] truncated
# the name and minted a phantom that could collide with a real [a].
# PROC is T-SQL's official shorthand for PROCEDURE and equally common in the
# wild; the optional (?:EDURE)? still requires trailing whitespace, so a word
# that merely starts with PROC cannot match.
# \bCREATE: without the boundary, CREATE matched inside a bare word, so
# 'SELECT AUTOCREATE PROCEDURE x FROM t;' in an error-bearing file minted a
# phantom routine x() (delimited identifiers are span-skipped at the scan
# site, but a bare word has no span).
_ROUTINE_RECOVERY_RX = re.compile(
    r"\bCREATE\s+(?:OR\s+(?:REPLACE|ALTER)\s+)?(?:FUNCTION|PROC(?:EDURE)?)\s+"
    r"(?:IF\s+NOT\s+EXISTS\s+)?"
    r"((?:\"(?:[^\"\n]|\"\")+\"|\[(?:[^\]\n]|\]\])+\]|[\w$]+)"
    r"(?:\s*\.\s*(?:\"(?:[^\"\n]|\"\")+\"|\[(?:[^\]\n]|\]\])+\]|[\w$]+))*)",
    re.IGNORECASE,
)

# _mask_sql_comments is a linear character scanner, not a regex: the four
# span kinds interact in ways a single pattern cannot express safely —
# comment-opener parity inside strings, nested block comments, and
# end-of-line abandonment of unclosed literals. Span handling:
#
# - single-quoted strings are BLANKED like comments: routine names never
#   live in single quotes, and dynamic SQL (EXEC(N'CREATE PROC [dbo].[Fake]
#   ...')) would otherwise fabricate a routine node whenever an unrelated
#   parse error arms the whole-file scan. (Dialects where other quoting
#   carries strings — MySQL double quotes, PostgreSQL dollar-quoting — are
#   NOT modelled; DDL inside those still reaches the scan.)
# - double-quoted and bracket-delimited identifiers are PRESERVED verbatim —
#   they are exactly the delimited names the recovery regex must see ("" and
#   ]] escapes consumed, mirroring _ROUTINE_RECOVERY_RX).
# - line comments blank to end-of-line; block comments blank to their
#   matching */ with NESTING tracked (SQL Server and PostgreSQL both nest
#   /* */, and a lazy first-*/ match let commented-out DDL inside a nested
#   comment fabricate nodes). MySQL and Oracle do NOT nest — there the
#   depth tracking over-blanks, losing (never fabricating) a routine after
#   an inner */; the primary T-SQL/PostgreSQL targets win that trade. An
#   UNCLOSED block comment blanks to end-of-file, matching SQL semantics.
#
# Literals are deliberately line-scoped: this mask only runs on files that
# already failed to parse, where an unclosed delimiter is likely, and a
# multi-line literal span would let one unclosed quote swallow real DDL
# below it. The cost is asymmetric by kind. A single-quoted string that
# continues past its line is blanked only up to the newline, so a comment
# opener inside it cannot fire on that line — but its CONTINUATION lines are
# scanned as code, and DDL there fabricates: multi-line dynamic SQL
# (SET @sql = N\'\n CREATE PROC ...\') is a KNOWN HOLE, alongside the
# unmodelled quoting dialects above; only same-line dynamic SQL is blanked.
# Closing it would need a real string heuristic (e.g. an end-of-line opening
# quote), judged not worth the swallow risk in a recovery-only path.


def _scan_sql(text: str) -> tuple[str, list[tuple[int, int]]]:
    """Blank comment and string-literal spans, preserving every offset.

    One output character per input character: non-newline characters inside
    a blanked span become spaces and newlines are kept, so positions and
    line numbers computed against the masked text are valid against the
    original. Double-quoted and bracket-delimited identifiers are preserved
    verbatim (they carry recoverable routine names); single-quoted strings,
    line comments, and (nesting-aware) block comments are blanked. Used by
    the routine-recovery scan so CREATE PROCEDURE/FUNCTION DDL reachable
    only through a comment or a single-quoted string cannot fabricate a
    routine node when an unrelated parse error arms recovery.

    Returns (masked_text, ident_spans) where ident_spans holds the [start,
    end) of every PRESERVED delimited identifier: preserved spans keep their
    text verbatim, so DDL keywords inside one are still visible in the
    masked text, and the recovery scan must skip a match that starts there
    (identifier data, not DDL — 'SELECT 1 AS [CREATE PROCEDURE x pending]'
    must not mint a routine).
    """
    ident_spans: list[tuple[int, int]] = []
    out: list[str] = []
    i, n = 0, len(text)

    def _blank(upto: int) -> int:
        """Blank [i, upto), keeping newlines; return upto."""
        for c in text[i:upto]:
            out.append("\n" if c == "\n" else " ")
        return upto

    def _blank_tail_and_carry(start: int) -> int:
        """Blank from start to end-of-line, carrying comment state forward.

        The union-of-readings blank for an ambiguous stretch: the rest of the
        line is blanked outright; if the raw text of that stretch leaves a /*
        unclosed on its own line (the maximum comment depth any reading could
        be left holding), blanking continues, nesting-aware, to the closing
        */ or EOF. Where a carry closes MID-line the same rule applies to the
        remainder of that line — under the reading where the carry never
        opened, that whole line may be a comment or a string, so emitting the
        post-*/ text verbatim exposed it (found by differential fuzzing).
        Repeats until a line ends with no carry pending. Appends one output
        character per input character; returns the resume index.
        """
        k = start
        while True:
            eol = text.find("\n", k)
            eol = n if eol == -1 else eol
            depth = 0
            m2 = k
            while m2 < eol:
                if text.startswith("/*", m2):
                    depth += 1
                    m2 += 2
                elif text.startswith("*/", m2):
                    if depth:
                        depth -= 1
                    m2 += 2
                else:
                    m2 += 1
            for ch in text[k:eol]:
                out.append("\n" if ch == "\n" else " ")
            k = eol
            if not depth:
                return k
            j2 = k
            while j2 < n and depth:
                if text.startswith("/*", j2):
                    depth += 1
                    j2 += 2
                elif text.startswith("*/", j2):
                    depth -= 1
                    j2 += 2
                else:
                    j2 += 1
            for ch in text[k:j2]:
                out.append("\n" if ch == "\n" else " ")
            k = j2
            if k >= n:
                return k
            # the carry closed mid-line: the remainder of THIS line is the
            # same ambiguous stretch — loop and blank it too

    while i < n:
        c = text[i]
        if c == "'":
            # Single-quoted string: blank it. '' is an escaped quote; a
            # newline abandons the literal (see the comment above).
            j = i + 1
            while j < n and text[j] != "\n":
                if text[j] == "'":
                    if j + 1 < n and text[j + 1] == "'":
                        j += 2
                        continue
                    j += 1
                    break
                j += 1
            i = _blank(j)
        elif c == '"' or c == "[":
            # Delimited identifier: preserve verbatim. Doubled closers are
            # escapes. A span is DISTRUSTED when it is unterminated (no
            # closer before the newline) or would swallow a comment opener
            # on its way to the closer ('SELECT [Col FROM t -- CREATE PROC
            # [dbo]' closes on [dbo]'s bracket) — a stray delimiter is
            # ordinary in exactly the broken files this mask runs on.
            #
            # A distrusted span is irreducibly ambiguous (identifier data vs
            # stray delimiter before real comments/strings), and any attempt
            # to pick one reading exposed text the other reading blanks —
            # re-emitting the delimiter and rescanning even re-paired later
            # single quotes and uncovered dynamic SQL. So blank the UNION of
            # every reading: the rest of the line is blanked outright, and
            # any raw /* on it with no later */ on the same line carries
            # forward as (nesting-aware) comment state, since some reading
            # may have left it open — and where that carry closes mid-line,
            # the remainder of THAT line gets the same treatment, repeated
            # until a line ends carry-free (under the no-carry reading the
            # close line may itself be all comment or string, so emitting its
            # post-*/ tail verbatim was an exposure). Over-blanking loses at
            # most routines on lines already entangled with the broken one (a
            # conservative false negative; a routine named like [a--b] is
            # inside that loss); under-blanking is what fabricates, and every
            # reading's blank set stays a subset of this one — except where a
            # */ + * versus * + /* token split makes two readings consume the
            # same /, an irreducible divergence whose only closure would be
            # blanking to EOF on every */* sequence (accepted, documented
            # limitation; the token sequence appears in no dialect's idiom).
            closer = '"' if c == '"' else "]"
            j = i + 1
            closed = False
            while j < n and text[j] != "\n":
                if text[j] == closer:
                    if j + 1 < n and text[j + 1] == closer:
                        j += 2
                        continue
                    j += 1
                    closed = True
                    break
                j += 1
            span = text[i:j]
            if closed and "--" not in span and "/*" not in span:
                ident_spans.append((i, j))
                out.append(span)
                i = j
            else:
                i = _blank_tail_and_carry(i)
        elif c == "-" and i + 1 < n and text[i + 1] == "-":
            j = i
            while j < n and text[j] != "\n":
                j += 1
            i = _blank(j)
        elif c == "/" and i + 1 < n and text[i + 1] == "*":
            depth, j = 1, i + 2
            while j < n and depth:
                if text[j] == "/" and j + 1 < n and text[j + 1] == "*":
                    depth += 1
                    j += 2
                elif text[j] == "*" and j + 1 < n and text[j + 1] == "/":
                    depth -= 1
                    j += 2
                else:
                    j += 1
            i = _blank(j)  # unclosed comment: j == n, blanks to end-of-file
        else:
            out.append(c)
            i += 1
    return "".join(out), ident_spans


def _mask_sql_comments(text: str) -> str:
    """Masked text only — see _scan_sql for the span-reporting form."""
    return _scan_sql(text)[0]


def _norm_ident(name: str) -> str:
    """Normalize a SQL identifier for name-based reference resolution.

    Splits on `.`, strips one pair of surrounding delimiters from each part
    (double quotes for Postgres/ANSI, backticks for MySQL, brackets for
    T-SQL), lowercases, and rejoins. So `"public"."users"`, `public.users`,
    and `PUBLIC.USERS` all normalize to `public.users`. Used ONLY for
    `table_nids` keys and lookups — node ids and display labels keep the
    original text.
    """
    parts = []
    for part in name.split("."):
        p = part.strip()
        if len(p) >= 2 and ((p[0] == p[-1] and p[0] in ('"', "`"))
                            or (p[0] == "[" and p[-1] == "]")):
            p = p[1:-1]
        parts.append(p.lower())
    return ".".join(parts)


def extract_sql(path: Path, content: str | bytes | None = None) -> dict:
    """Extract tables, views, functions, and relationships from .sql files via tree-sitter."""
    try:
        import tree_sitter_sql as tssql
        from tree_sitter import Language, Parser
    except ImportError as e:
        import importlib.util
        # An installed-but-broken grammar (e.g. a C extension built for a
        # different Python ABI, #2602) raises ImportError here too. Reporting
        # that as "not installed" sends the user to a no-op `pip install`, so
        # distinguish a genuinely-absent module from one that failed to load
        # and surface the real exception in the latter case.
        if importlib.util.find_spec("tree_sitter_sql") is None:
            return {"nodes": [], "edges": [],
                    "error": "tree_sitter_sql not installed. Run: pip install tree-sitter-sql"}
        return {"nodes": [], "edges": [],
                "error": f"tree_sitter_sql is installed but failed to load: {e}"}

    try:
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

    def _ref_stub(name: str) -> str:
        """Sourceless bare-name stub for a table referenced but not defined here.

        SQL references are NAME-based, so a table defined in another file (e.g.
        prisma migration m2 referencing a table created in m1) can only resolve
        at the corpus level. Minting `_make_id(stem, name)` under THIS file's
        stem fabricated a node-less compound id — an absolute-path slug when the
        input path was absolute — that could never match the real definition
        (#2324). Instead emit a SOURCELESS stub, mirroring the Go extractor's
        cross-file pattern (#1402): `_rewire_unique_stub_nodes` collapses it
        onto the unique real table definition, and an unresolvable name survives
        as a portable name-only node instead of dangling. No contains edge: a
        sourced/contained stub would get the referencing file's path baked into
        its id by disambiguation, blocking the rewire.
        """
        nid = _make_id(name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": name, "file_type": "code",
                           "source_file": "", "source_location": "",
                           "origin_file": str_path})
        return nid

    def walk(node) -> None:
        t = node.type
        line = node.start_point[0] + 1

        if t == "create_table":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[_norm_ident(name)] = nid
                # Foreign key REFERENCES
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
                                    ref_nid = table_nids.get(_norm_ident(ref_name)) or _ref_stub(ref_name)
                                    _add_edge(nid, ref_nid, "references", line)
                                    seen_refs.add(_norm_ident(ref_name))
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
                                        ref_nid = table_nids.get(_norm_ident(ref_name)) or _ref_stub(ref_name)
                                        _add_edge(nid, ref_nid, "references", line)
                                        seen_refs.add(_norm_ident(ref_name))
                        if has_error:
                            # Dialect-specific syntax (e.g. Firebird COMPUTED BY) causes ERROR
                            # nodes that make the parser drop the trailing constraints block.
                            # Regex-scan the raw column_definitions text as fallback.
                            col_text = _read(col)
                            for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", col_text, re.IGNORECASE):
                                ref_name = rm.group(1)
                                if _norm_ident(ref_name) not in seen_refs:
                                    ref_nid = table_nids.get(_norm_ident(ref_name)) or _ref_stub(ref_name)
                                    _add_edge(nid, ref_nid, "references", line)
                                    seen_refs.add(_norm_ident(ref_name))

        elif t == "create_view":
            name = _obj_name(node)
            if name:
                nid = _make_id(stem, name)
                _add_node(nid, name, line)
                table_nids[_norm_ident(name)] = nid
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
                src_nid = table_nids.get(_norm_ident(name))
                if not src_nid:
                    # Subject table not defined in this file: sourceless stub,
                    # not a sourced wrong-stem node (#2324).
                    src_nid = _ref_stub(name)
                    table_nids[_norm_ident(name)] = src_nid
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
                                ref_nid = (table_nids.get(_norm_ident(ref_name))
                                           or _ref_stub(ref_name))
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
                    tbl_nid = table_nids.get(_norm_ident(tbl_name)) or _ref_stub(tbl_name)
                    _add_edge(trig_nid, tbl_nid, "triggers", line)

        # NOTE: there is deliberately NO recovery scan on individual ERROR
        # nodes. Any ERROR node anywhere makes root.has_error true, so the
        # whole-file masked scan below this walk already recovers everything
        # a per-node scan could — from the SAME shared _ROUTINE_RECOVERY_RX,
        # with _add_node deduping by id. A per-node scan is not just
        # redundant, it is unsound: _mask_sql_comments needs file-level
        # context, and an ERROR fragment can begin MID-comment (tree-sitter's
        # lexer does not nest /* */, so the text after an inner */ parses as
        # code and lands in an ERROR blob with no comment opener in sight),
        # which let commented-out DDL fabricate routine nodes.

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
                        tbl_nid = table_nids.get(_norm_ident(tbl)) or _ref_stub(tbl)
                        _add_edge(obj_nid, tbl_nid, "triggers", line)
                _NON_TABLES = {
                    "select", "where", "set", "dual", "null", "true", "false",
                    "first", "skip", "rows", "next", "only", "lateral",
                }
                # Same CTE-blindness as the AST path (#2577): a `WITH <name> AS (`
                # binding is statement-local, not a table, so its name must not
                # become a reads_from stub. The regex has no scope tree, so the
                # skip is body-wide — the right trade for a recovery path.
                for cm in re.finditer(
                    r"(?:\bWITH\s+(?:RECURSIVE\s+)?|,\s*)([\w$]+)\s*(?:\([^()]*\))?\s+AS\s*\(",
                    text, re.IGNORECASE,
                ):
                    _NON_TABLES.add(_norm_ident(cm.group(1)))
                seen_tbls: set[str] = set()
                for rm in re.finditer(r"\b(?:FROM|JOIN|INTO)\s+([\w$]+)", text, re.IGNORECASE):
                    tbl = rm.group(1)
                    if _norm_ident(tbl) not in _NON_TABLES and _norm_ident(tbl) not in seen_tbls:
                        seen_tbls.add(_norm_ident(tbl))
                        tbl_nid = table_nids.get(_norm_ident(tbl)) or _ref_stub(tbl)
                        _add_edge(obj_nid, tbl_nid, "reads_from", line)
                for rm in re.finditer(r"\bUPDATE\s+([\w$]+)", text, re.IGNORECASE):
                    tbl = rm.group(1)
                    if _norm_ident(tbl) not in _NON_TABLES and _norm_ident(tbl) not in seen_tbls:
                        seen_tbls.add(_norm_ident(tbl))
                        tbl_nid = table_nids.get(_norm_ident(tbl)) or _ref_stub(tbl)
                        _add_edge(obj_nid, tbl_nid, "reads_from", line)

        for child in node.children:
            walk(child)

    def _walk_from_refs(node, caller_nid: str, line: int,
                        cte_names: frozenset[str] = frozenset()) -> None:
        """Recursively find FROM/JOIN table references inside a node, skipping CTEs.

        A name bound by `WITH <name> AS (...)` is not a table: emitting it as a
        `reads_from` target minted a bare `_ref_stub`, and because that stub is
        intentionally sourceless (see `_ref_stub`) it carried no schema, file, or
        language namespace, so a CTE named `levels` or `slug` collided with any
        same-named node from another language during the build (#2577).

        Scoping matters: a CTE is visible only inside the query that declares it,
        and a `WITH` inside a subquery is scoped to that subquery alone. So the
        active set is extended PER SUBTREE — each node's directly-owned `cte`
        children (`create_query` for a statement-level WITH, `subquery` for a
        nested one) join the set passed down into that node's recursion only. A
        single statement-wide pre-collect would also suppress an OUTER reference
        to a real table that merely shares a subquery-CTE's name
        (`... FROM t2 JOIN (WITH t2 AS (...) SELECT ...) sub`), dropping the
        real `-> t2` edge.
        """
        own: set[str] = set()
        for c in node.children:
            if c.type != "cte":
                continue
            # First identifier is the CTE's name; later ones are its column
            # list (`WITH levels(a, b) AS (...)`), which must not be skipped.
            for cc in c.children:
                if cc.type in ("identifier", "object_reference"):
                    own.add(_norm_ident(_read(cc)))
                    break
        if own:
            cte_names = frozenset(cte_names | own)
        if node.type in ("from", "join"):
            for c in node.children:
                if c.type == "relation":
                    for cc in c.children:
                        if cc.type == "object_reference":
                            tbl = _read(cc)
                            if _norm_ident(tbl) in cte_names:
                                continue
                            tbl_nid = table_nids.get(_norm_ident(tbl)) or _ref_stub(tbl)
                            _add_edge(caller_nid, tbl_nid, "reads_from",
                                      c.start_point[0] + 1)
        for child in node.children:
            _walk_from_refs(child, caller_nid, line, cte_names)

    # Pre-pass: register every table/view DEFINED in this file before walking,
    # so forward references (a FK to a table created later in the same file)
    # still resolve to the real sourced node instead of falling back to a stub.
    def _collect_defined_names(node) -> None:
        if node.type in ("create_table", "create_view"):
            name = _obj_name(node)
            if name:
                table_nids[_norm_ident(name)] = _make_id(stem, name)
        for child in node.children:
            _collect_defined_names(child)

    _collect_defined_names(root)

    # Secondary bare-name aliases: a reference written without a schema
    # (`REFERENCES users`) should resolve to a schema-qualified definition
    # (`public.users`) when that is unambiguous. Never shadow an explicit
    # definition, and skip bare names defined under more than one schema.
    bare_candidates: dict[str, str | None] = {}
    for key, alias_nid in table_nids.items():
        if "." in key:
            bare = key.rsplit(".", 1)[1]
            bare_candidates[bare] = (
                alias_nid if bare_candidates.get(bare, alias_nid) == alias_nid else None
            )
    for bare, alias_nid in bare_candidates.items():
        if alias_nid is not None and bare not in table_nids:
            table_nids[bare] = alias_nid

    for stmt in root.children:
        if stmt.type == "statement":
            for child in stmt.children:
                walk(child)
        elif stmt.type == "transaction":
            # BEGIN; ... COMMIT; wraps DDL in a transaction node whose children
            # are statement nodes, not direct create_table nodes (#2953).
            walk(stmt)
        elif stmt.type in ("fb_proc_or_trigger", "set_term", "declare_external_function", "ERROR"):
            walk(stmt)

    # Global regex fallback: catch any REFERENCES missed due to ERROR nodes in the parse tree
    # (e.g. Firebird COMPUTED BY columns push constraints out of the tree entirely).
    # Snapshot after tree walk so we don't re-emit edges already captured above.
    emitted = {(e["source"], e["target"]) for e in edges if e["relation"] == "references"}
    src_text = source.decode("utf-8", errors="replace")
    for m in re.finditer(r"CREATE\s+TABLE\s+([\w$]+)\s*\(", src_text, re.IGNORECASE):
        tbl_name = m.group(1)
        tbl_nid = table_nids.get(_norm_ident(tbl_name))
        if tbl_nid is None:
            continue
        tbl_line = src_text[: m.start()].count("\n") + 1
        tail = src_text[m.start():]
        end = re.search(r"(?:^|\n)(?:CREATE|SET\s+TERM|ALTER)\s", tail[1:], re.IGNORECASE)
        block = tail[: end.start() + 1] if end else tail
        for rm in re.finditer(r"\bREFERENCES\s+([\w$]+)", block, re.IGNORECASE):
            ref_name = rm.group(1)
            ref_nid = table_nids.get(_norm_ident(ref_name)) or _ref_stub(ref_name)
            if (tbl_nid, ref_nid) not in emitted:
                _add_edge(tbl_nid, ref_nid, "references", tbl_line)
                emitted.add((tbl_nid, ref_nid))

    # Global regex fallback for routines (#2180). PL/pgSQL bodies break the parse
    # in more than one shape, and only the first was recovered before:
    #   1. the whole CREATE lands in one ERROR node          -> handled in walk()
    #   2. the statement is shredded into loose top-level tokens
    #      (keyword_create/keyword_function/object_reference/... ) and the ERROR
    #      node holds only the offending body line, e.g. `PERFORM x();` or
    #      `x := 1;` -- so no CREATE text is inside any ERROR node at all
    #   3. the name is a delimited identifier — quoted ("public"."fn") or
    #      T-SQL-bracketed ([dbo].[usp_Load]) — which a bare [\w$.]+ pattern
    #      cannot match
    # Shapes 2 and 3 silently dropped the routine: no node, no warning, exit 0.
    # Scanning the raw source catches all three, and _add_node dedupes by id so
    # routines already recovered from the tree are not emitted twice.
    #
    # Gate on a failed parse: a cleanly-parsing file must NOT have routines
    # fabricated from MySQL `CREATE FUNCTION IF NOT EXISTS` (which would
    # capture `IF`) or other shapes the mask does not model (double-quoted
    # strings in MySQL's default mode, PostgreSQL dollar-quoted bodies). Every
    # observed drop shape leaves an ERROR node in the tree, so has_error loses
    # nothing while protecting clean corpora (#2180 follow-up).
    if root.has_error:
        # The mask blanks comments (nesting-aware) and single-quoted strings
        # (offset-preserving), so commented-out DDL and single-quoted dynamic
        # SQL cannot fabricate a routine when an unrelated error arms this
        # scan; string shapes the mask does not model rely on the has_error
        # gate alone. Preserved delimited identifiers keep their text
        # verbatim (they carry the recoverable names), so a match whose
        # CREATE keyword STARTS inside one is identifier data, not DDL
        # ('SELECT 1 AS [CREATE PROCEDURE x pending]') and is skipped — the
        # name a genuine statement captures is allowed to be a delimited
        # identifier; its CREATE never is.
        masked_src, ident_spans = _scan_sql(src_text)
        for m in _ROUTINE_RECOVERY_RX.finditer(masked_src):
            if any(s <= m.start() < e for s, e in ident_spans):
                continue
            fn_name = m.group(1)
            fn_line = src_text[: m.start()].count("\n") + 1
            _add_node(_make_id(stem, fn_name), f"{fn_name}()", fn_line)

    return {"nodes": nodes, "edges": edges}
