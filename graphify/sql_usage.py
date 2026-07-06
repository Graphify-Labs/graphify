"""SQL-usage mining: how application code touches database objects.

Scans the source files behind a code graph for SQL statements and emits
cross-namespace links from the graph's FILE nodes to MaluDb data-model
nodes ("<datamodel_ns>/<schema>.<table>"). Pushed with the server's
resolve_external option, targets that exist in the tenant's data-model
graph resolve into real edges; unknown targets are reported in the
import's skipped list, not fatal.

Deliberately regex-based (no SQL parse): the goal is INFERRED-confidence
"this file reads/writes that table" edges, not query understanding.
"""
from __future__ import annotations
import re
from pathlib import Path

# Table reference sites. Group 1..3: write forms; group 4: read forms.
_WRITE_RE = re.compile(
    r"\bINSERT\s+INTO\s+([A-Za-z_\"][\w$.\"]*)"
    r"|\bUPDATE\s+([A-Za-z_\"][\w$.\"]*)\s+SET\b"
    r"|\bDELETE\s+FROM\s+([A-Za-z_\"][\w$.\"]*)",
    re.IGNORECASE,
)
_READ_RE = re.compile(r"\b(?:FROM|JOIN)\s+([A-Za-z_\"][\w$.\"]*)", re.IGNORECASE)

# Identifiers that follow FROM/JOIN in SQL or SQL-ish prose but are not tables.
_NOISE = {
    "select", "the", "a", "an", "this", "that", "these", "each", "one",
    "unnest", "generate_series", "jsonb_array_elements", "jsonb_array_elements_text",
    "jsonb_each", "json_array_elements", "regexp_split_to_table", "lateral",
    "dual", "information_schema", "pg_catalog", "now", "coalesce", "string_to_table",
}

_MAX_FILE_BYTES = 2_000_000
_MAX_REFS_PER_FILE = 200

_CODE_SUFFIXES = {
    ".py", ".php", ".ts", ".tsx", ".js", ".jsx", ".rs", ".go", ".rb",
    ".java", ".kt", ".cs", ".sql", ".c", ".h", ".cpp", ".pl",
}


def _clean_ident(raw: str) -> str | None:
    """Normalize a captured identifier; None if it is noise."""
    name = raw.strip().strip('"').rstrip("(,;")
    if not name or name.lower() in _NOISE:
        return None
    # placeholders / interpolations / pseudo-tables
    if any(ch in name for ch in "%{}()"):
        return None
    bare = name.split(".")[-1]
    if len(bare) < 3 or bare.lower() in _NOISE:
        return None
    # information_schema.x / pg_catalog.x / pg_* system relations
    head = name.split(".")[0].lower()
    if head in ("information_schema", "pg_catalog") or bare.lower().startswith("pg_"):
        return None
    return name


def _qualify(name: str, default_schema: str) -> str:
    return name if "." in name else f"{default_schema}.{name}"


def scan_file(text: str) -> dict[str, set[str]]:
    """Return {'reads': {names}, 'writes': {names}} found in one file's text."""
    writes: set[str] = set()
    reads: set[str] = set()
    for m in _WRITE_RE.finditer(text):
        name = _clean_ident(next(g for g in m.groups() if g))
        if name:
            writes.add(name)
        if len(writes) >= _MAX_REFS_PER_FILE:
            break
    for m in _READ_RE.finditer(text):
        name = _clean_ident(m.group(1))
        if name and name not in writes:
            reads.add(name)
        if len(reads) >= _MAX_REFS_PER_FILE:
            break
    return {"reads": reads, "writes": writes}


def file_nodes(G) -> dict[str, str]:
    """Map source_file -> the file-level node id (shortest id per file)."""
    best: dict[str, str] = {}
    for node_id, data in G.nodes(data=True):
        source = data.get("source_file")
        if not source:
            continue
        if source not in best or len(node_id) < len(best[source]):
            best[source] = node_id
    return best


def mine_sql_usage(
    G,
    source_root: str,
    datamodel_ns: str = "datamodel",
    default_schema: str = "public",
) -> list[dict]:
    """Build cross-namespace links: file node -> datamodel/<schema>.<table>.

    Only files that actually appear in the graph are scanned, so the link
    sources always resolve; targets resolve server-side via the import's
    resolve_external option (unknown tables are reported, not fatal).
    """
    root = Path(source_root)
    links: list[dict] = []
    for source_file, node_id in sorted(file_nodes(G).items()):
        path = root / source_file
        if not path.is_file() and Path(source_file).is_absolute():
            path = Path(source_file)
        if not path.is_file() or path.suffix.lower() not in _CODE_SUFFIXES:
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        found = scan_file(text)
        for rel, names in (("writes", found["writes"]), ("reads", found["reads"])):
            for name in sorted(names):
                links.append({
                    "source": node_id,
                    "target": f"{datamodel_ns}/{_qualify(name, default_schema)}",
                    "relation": rel,
                    "confidence": "INFERRED",
                })
    return links
