"""Link SQL tables to the application code that queries them (#2884).

``tree-sitter-sql`` extracts table declarations correctly and the host-language
grammars extract the application code correctly, but nothing connected the two:
a table declared in ``db/schema.sql`` had no edge to the ``.ts`` file whose query
reads ``SELECT … FROM that_table``. Every table landed connected only to the file
that declares it (``contains``, degree 1), so the data layer floated free of the
application and the graph could not answer "what breaks if I change this table?".

This is a text-embedding problem rather than an AST one — the table name lives
inside a template literal that the TypeScript grammar sees only as a string — so
the pass is lexical: after per-file extraction, scan every non-SQL source for
each declared table name and emit a ``references`` edge from the referencing file
to the table.

Precision is the whole difficulty. Table names like ``users``, ``events``,
``sales`` and ``notifications`` are extremely common ordinary identifiers, and a
matcher that asks "does this file contain SQL anywhere, and does this table name
appear anywhere in it" produces mostly phantoms — on the reporting corpus, 1,489
edges of which the 130 for ``events`` were all JavaScript variables named
``events``. The table must therefore sit in a real SQL keyword position **in the
same match**, which brings that corpus to 921 edges that hand-checked clean.

Set ``GRAPHIFY_NO_SQL_LINKS=1`` to skip the pass (a repo that reaches its
database through an ORM gets little from it, since ORMs name tables via model
classes rather than in SQL text).
"""

from __future__ import annotations

import os
import re
from pathlib import PurePath

# A table name only counts when it directly follows one of these. Run over the
# whole file text rather than line by line, so a table named on the second line
# of a multi-line template literal still matches.
_SQL_KEYWORDS = r"(?:FROM|JOIN|INTO|UPDATE|REFERENCES|TABLE(?:\s+IF\s+NOT\s+EXISTS)?)"
# Identifier quoting differs by dialect: MySQL backticks, standard SQL double
# quotes, T-SQL brackets (cf. #2712). Unquoted is the common case.
_OPEN_QUOTE = r"[`\"\[]?"
_CLOSE_QUOTE = r"[`\"\]]?"

# Files larger than this are not scanned: a multi-megabyte bundle or generated
# artifact costs more to read than the edges it could plausibly contribute.
_MAX_SCAN_BYTES = 2 * 1024 * 1024


def _table_pattern(name: str) -> "re.Pattern[str]":
    return re.compile(
        _SQL_KEYWORDS + r"\s+" + _OPEN_QUOTE + re.escape(name) + _CLOSE_QUOTE + r"\b",
        re.IGNORECASE,
    )


def _declared_tables(all_nodes: list[dict], all_edges: list[dict]) -> dict[str, list[str]]:
    """Map table name -> node ids of every ``.sql`` file that declares it.

    A declaration is the target of a ``contains`` edge from a ``.sql`` file, which
    is exactly how the SQL extractor anchors tables and views it defines. The
    sourceless reference stubs it mints for tables defined in another file carry
    no ``contains`` edge, so they are excluded — a stub is not a declaration site.
    """
    sql_files = {
        n["id"] for n in all_nodes
        if isinstance(n, dict) and str(n.get("source_file", "")).lower().endswith(".sql")
        and n.get("source_location") in (None, "", "L1")
        and str(n.get("label", "")).lower().endswith(".sql")
    }
    if not sql_files:
        return {}
    labels = {
        n["id"]: str(n.get("label", ""))
        for n in all_nodes
        if isinstance(n, dict) and n.get("id")
    }
    declared: dict[str, list[str]] = {}
    for e in all_edges:
        if not isinstance(e, dict) or e.get("relation") != "contains":
            continue
        if e.get("source") not in sql_files:
            continue
        target = e.get("target")
        label = labels.get(target, "")
        # Bare identifiers only: anything punctuated is a column, a member or a
        # file node, none of which is addressable as `FROM <name>`.
        if not label or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_$]*", label):
            continue
        ids = declared.setdefault(label, [])
        if target not in ids:
            ids.append(target)
    return declared


def _scannable_sources(all_nodes: list[dict]) -> list[tuple[str, str]]:
    """(source_file, file node id) for every non-SQL source, in stable order.

    The file node is the one labelled with the file's basename. Its id cannot be
    recomputed from the path here: by the time resolvers run, ids have already
    been made portable, so ``make_id(source_file)`` no longer matches. Extractors
    emit the file node before anything else in the file, so the first match wins
    if a symbol happens to share the basename.
    """
    seen: set[str] = set()
    out: list[tuple[str, str]] = []
    for n in all_nodes:
        if not isinstance(n, dict) or not n.get("id"):
            continue
        sf = str(n.get("source_file") or "")
        if not sf or sf in seen or sf.lower().endswith(".sql"):
            continue
        if str(n.get("label", "")) != PurePath(sf).name:
            continue
        seen.add(sf)
        out.append((sf, n["id"]))
    return out


def resolve_sql_table_references(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Emit ``references`` edges from application files to the tables they query."""
    if os.environ.get("GRAPHIFY_NO_SQL_LINKS", "").strip().lower() in ("1", "true", "yes"):
        return

    declared = _declared_tables(all_nodes, all_edges)
    if not declared:
        return

    patterns = {name: _table_pattern(name) for name in declared}

    for sf, file_nid in _scannable_sources(all_nodes):
        try:
            with open(sf, "rb") as fh:
                blob = fh.read(_MAX_SCAN_BYTES + 1)
        except OSError:
            continue
        if len(blob) > _MAX_SCAN_BYTES:
            continue
        text = blob.decode("utf-8", errors="replace")
        # Cheap pre-filter: no SQL keyword at all means no possible match, which
        # skips the per-table scan for the overwhelming majority of files.
        if not re.search(_SQL_KEYWORDS + r"\s", text, re.IGNORECASE):
            continue
        for name, table_nids in declared.items():
            m = patterns[name].search(text)
            if m is None:
                continue
            line = text.count("\n", 0, m.start()) + 1
            for table_nid in table_nids:
                if table_nid == file_nid:
                    continue
                all_edges.append({
                    "source": file_nid,
                    "target": table_nid,
                    "relation": "references",
                    # The table name is written verbatim in a SQL keyword
                    # position in this file — a checkable claim, not an
                    # inference. `calls` edges must stay within one language
                    # (see references/extraction-spec.md); `references` is a
                    # different relation and this is what it is for.
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": sf,
                    "source_location": f"L{line}",
                    "weight": 1.0,
                    "context": "sql_table",
                })
