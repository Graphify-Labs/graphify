"""Detect and parse SQL statements embedded in application-code string literals.

Pure helpers with no graphify.extract dependency (import direction is one-way:
extract.py -> sql_evidence.py). Host-language extractors flatten a string
expression (replacing interpolations with :data:`PARAM_PLACEHOLDER`), then:

    looks_like_sql(text)  ->  cheap gate, no parsing
    sanitize_sql(text)    ->  placeholder/backtick normalization
    parse_sql_statement() ->  {"op", "tables_read", "tables_written", "joins"}

``joins`` are equality predicates between qualified columns of two different
tables (JOIN ON or WHERE), with aliases resolved — the raw evidence from which
a later corpus-wide pass infers undeclared foreign keys. Precision beats
recall throughout: a parse tree containing ERROR nodes is discarded rather
than guessed at, and any name touched by an interpolation placeholder is
dropped.

Known v1 limitation: quoted mixed-case identifiers (``"Users"`` vs ``users``)
are conflated by the casefolding in :func:`normalize_table_key`.
"""
from __future__ import annotations

import re

# Placeholder spliced in for interpolated/concatenated fragments and bind
# parameters. Parses as a plain identifier in both expression and relation
# position, so surrounding structure survives.
PARAM_PLACEHOLDER = "__gfx_param__"

_SQL_HEAD = re.compile(r"\s*(SELECT|INSERT|UPDATE|DELETE|REPLACE|WITH)\b", re.IGNORECASE)
_SQL_BODY = re.compile(r"\b(FROM|INTO|SET|JOIN|WHERE)\b", re.IGNORECASE)
# Punctuation that essentially never appears in prose that merely starts with
# "Select ... from ...": placeholders, comparisons, wildcards, quoting, calls.
_SQL_SIGNAL = re.compile(r"[*=?;()'\"`%]|:\w")

_NAMED_PARAM = re.compile(r"(?<!:):[A-Za-z_]\w*")  # :id but not ::int casts
_FORMAT_PARAM = re.compile(r"%[sdif]\b")
_GLUED_PREFIX = re.compile(rf"(?<!\w){PARAM_PLACEHOLDER}(?=[A-Za-z_])")

_MIN_SQL_LEN = 12


def looks_like_sql(text: str) -> bool:
    """Cheap gate: does this string plausibly contain a SQL statement?

    Requires a leading DML keyword plus a second structural keyword after it.
    Because prose like "Select an option from the menu" satisfies both (and
    even parses as valid SQL), additionally require either SQL-ish punctuation
    or upper-cased keywords as written.
    """
    if len(text) < _MIN_SQL_LEN:
        return False
    head = _SQL_HEAD.match(text)
    if not head:
        return False
    body = _SQL_BODY.search(text, head.end())
    if not body:
        return False
    if _SQL_SIGNAL.search(text):
        return True
    return head.group(1).isupper() and body.group(1).isupper()


def sanitize_sql(text: str) -> str:
    """Normalize app-code SQL so tree-sitter-sql can parse it.

    Strips MySQL backticks and replaces bind-parameter syntax (``?``, ``:name``,
    ``%s``) with :data:`PARAM_PLACEHOLDER`. A placeholder glued to the front of
    an identifier (WordPress-style ``{$wpdb->prefix}posts``) collapses onto the
    identifier; an identifier glued to the front of a placeholder stays tainted
    (the real name is unknowable).
    """
    text = text.replace("`", "")
    text = text.replace("?", PARAM_PLACEHOLDER)
    text = _NAMED_PARAM.sub(PARAM_PLACEHOLDER, text)
    text = _FORMAT_PARAM.sub(PARAM_PLACEHOLDER, text)
    text = _GLUED_PREFIX.sub("", text)
    return text


def normalize_table_key(name: str) -> str:
    """Canonical matching key for a table name across evidence sources.

    Strips quoting, drops a leading ``public.`` schema qualifier, casefolds.
    """
    parts = [p.strip('"').strip("`") for p in name.split(".") if p]
    if len(parts) > 1 and parts[0].casefold() == "public":
        parts = parts[1:]
    return ".".join(parts).casefold()


_parser = None
_parser_failed = False


def _get_parser():
    global _parser, _parser_failed
    if _parser is None and not _parser_failed:
        try:
            import tree_sitter_sql as tssql
            from tree_sitter import Language, Parser
            _parser = Parser(Language(tssql.language()))
        except Exception:
            _parser_failed = True
    return _parser


def _tainted(name: str) -> bool:
    return PARAM_PLACEHOLDER in name


def parse_sql_statement(text: str) -> dict | None:
    """Parse one sanitized SQL string into table/join facts.

    Returns ``{"op", "tables_read", "tables_written", "joins"}`` or ``None``
    when the text does not parse cleanly (any ERROR node) or yields no table
    references. ``joins`` entries are ``{"left": [table, column], "right":
    [table, column]}`` with the two sides ordered lexically so that
    ``a.x = b.y`` and ``b.y = a.x`` produce identical records.
    """
    parser = _get_parser()
    if parser is None:
        return None
    try:
        tree = parser.parse(text.encode("utf-8"))
    except Exception:
        return None
    root = tree.root_node
    if root.has_error:
        return None

    src = text.encode("utf-8")

    def _read(n) -> str:
        return src[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

    op: str | None = None
    reads: dict[str, str] = {}   # key -> display name
    writes: dict[str, str] = {}
    alias_map: dict[str, str] = {}  # casefolded alias/name -> display name
    joins: list[dict] = []
    seen_joins: set[tuple] = set()

    def _relation_parts(rel) -> tuple[str | None, str | None]:
        """(table, alias) from a ``relation`` node."""
        table = alias = None
        for c in rel.children:
            if c.type == "object_reference" and table is None:
                table = _read(c)
            elif c.type == "identifier":
                alias = _read(c)
        return table, alias

    def _register(table: str | None, alias: str | None, bucket: dict[str, str]) -> None:
        if not table or _tainted(table):
            return
        key = normalize_table_key(table)
        if not key:
            return
        bucket.setdefault(key, table)
        alias_map.setdefault(table.casefold(), table)
        alias_map.setdefault(key, table)
        if alias and not _tainted(alias):
            alias_map.setdefault(alias.casefold(), table)

    def _qualified_field(n) -> tuple[str, str] | None:
        """(table-or-alias, column) from a ``field`` node, or None if unqualified."""
        if n.type != "field":
            return None
        ref = col = None
        for c in n.children:
            if c.type == "object_reference":
                ref = _read(c)
            elif c.type == "identifier":
                col = _read(c)
        if ref and col:
            return ref, col
        return None

    def _collect_joins(n) -> None:
        if n.type == "binary_expression" and len(n.children) == 3 and n.children[1].type == "=":
            left = _qualified_field(n.children[0])
            right = _qualified_field(n.children[2])
            if left and right:
                lt = alias_map.get(left[0].casefold(), left[0])
                rt = alias_map.get(right[0].casefold(), right[0])
                lc, rc = left[1], right[1]
                if (not any(_tainted(x) for x in (lt, rt, lc, rc))
                        and normalize_table_key(lt) != normalize_table_key(rt)):
                    a, b = sorted([(lt, lc), (rt, rc)])
                    dedup = (normalize_table_key(a[0]), a[1].casefold(),
                             normalize_table_key(b[0]), b[1].casefold())
                    if dedup not in seen_joins:
                        seen_joins.add(dedup)
                        joins.append({"left": [a[0], a[1]], "right": [b[0], b[1]]})
        for c in n.children:
            _collect_joins(c)

    def _walk_statement(stmt) -> None:
        nonlocal op
        stmt_op: str | None = None
        is_delete = False
        for child in stmt.children:
            if child.type in ("select", "insert", "update", "delete"):
                stmt_op = child.type
                is_delete = is_delete or child.type == "delete"
        if op is None:
            op = stmt_op

        def _walk(n, in_write_target: bool = False) -> None:
            t = n.type
            if t == "insert":
                for c in n.children:
                    if c.type == "object_reference":
                        _register(_read(c), None, writes)
                    else:
                        _walk(c)
                return
            if t == "update":
                # The relation directly under UPDATE is the write target;
                # anything nested deeper (FROM/JOIN) is a read.
                for c in n.children:
                    if c.type == "relation":
                        table, alias = _relation_parts(c)
                        _register(table, alias, writes)
                    else:
                        _walk(c)
                return
            if t == "from" and is_delete:
                # DELETE FROM x: the from node holds the target directly.
                for c in n.children:
                    if c.type == "object_reference":
                        _register(_read(c), None, writes)
                    elif c.type == "relation":
                        table, alias = _relation_parts(c)
                        _register(table, alias, writes)
                    else:
                        _walk(c)
                return
            if t == "relation":
                table, alias = _relation_parts(n)
                _register(table, alias, reads)
                for c in n.children:
                    _walk(c)  # subquery relations
                return
            for c in n.children:
                _walk(c)

        _walk(stmt)

    for stmt in root.children:
        if stmt.type == "statement":
            _walk_statement(stmt)

    if op is None or (not reads and not writes):
        return None

    for stmt in root.children:
        if stmt.type == "statement":
            _collect_joins(stmt)

    return {
        "op": op,
        "tables_read": sorted(reads.values(), key=str.casefold),
        "tables_written": sorted(writes.values(), key=str.casefold),
        "joins": joins,
    }
