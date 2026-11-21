"""One short, deterministic summary per file-level node, kept in a sidecar file.

`graphify summarize` writes ``node-summaries.json`` next to ``graph.json``. The
graph itself is never modified, and nothing is written unless the command is
run. Every summary is built by fixed rules from facts Graphify already
extracted, with no model call, so the same graph and files always give the same
bytes.

A code file is summarized from the graph alone: its module docstring, the
symbols it defines and what it imports. A Markdown document (which includes a
Word file, converted to Markdown at detection time) is summarized from its
title page when it has one: the text before the first top-level heading, read
with the same confinement to the project root that `graphify section` uses.
That gives a title plus its labelled fields: ``Label: value`` lines and the rows
of a two-column table. When room is left, the short unlabelled lines above the
first field are included too. A document that starts with its top-level heading
is summarized from its heading outline in the graph.

The rules identify a file; they do not describe what a long document says.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import networkx as nx

from graphify.build import _is_file_node_label, edge_datas
from graphify.paths import write_text_atomic
from graphify.security import redact_secrets, sanitize_label

# graphify.sections and graphify.extractors are imported inside the functions
# that read a document, never at module level: `graphify explain` loads this
# module for load_summaries, and read commands must not pay for importing every
# language extractor (tests/test_read_path_imports.py).

SUMMARY_SIDECAR_NAME = "node-summaries.json"
# The default length of a summary, and the range `--max-chars` may set it to.
# A reader never trusts a sidecar beyond the upper bound. A document gets more
# room than a code file by default: its title alone can take 150 characters,
# and what identifies it (a number, a phase, a product) comes after that.
SUMMARY_MAX_CHARS = 250
SUMMARY_DOCUMENT_MAX_CHARS = 500
SUMMARY_MIN_MAX_CHARS = 50
SUMMARY_HARD_MAX_CHARS = 1000
SUMMARY_SCHEMA_VERSION = 1
SUMMARY_GENERATOR = "deterministic"

_MAX_LEAD_CHARS = 120
_MAX_SYMBOLS = 5
_MAX_IMPORTS = 4
_MAX_SECTIONS = 5
# One listed name (a symbol, an import, a heading) never takes more than this.
_MAX_ITEM_CHARS = 60
_MAX_TITLE_CHARS = 150
# An unlabelled title is looked for among this many opening lines of the page.
_TITLE_CANDIDATE_LINES = 3
_MAX_FIELD_VALUE_CHARS = 80
_MAX_FIELD_LABEL_WORDS = 5
# How far into a document the title page is looked for.
_TITLE_PAGE_SCAN_LINES = 400

_LINE_RE = re.compile(r"^L(\d+)$")
# "Label: value" on one line. The label starts with a letter and is short; the
# colon must be followed by a space, so URLs and times do not match.
_FIELD_RE = re.compile(r"^([^\W\d_][\w /#&().'’-]{1,38}):[ \t]+(\S.*)$")
# "Table 7.1: ...", "Figure 2: ...": a label that ends in a number is a caption
# or a numbered option, not a field.
_NUMBERED_LABEL_RE = re.compile(r"\d\s*$")
# Cells of a Markdown table row; a pipe inside a cell is written "\|".
_CELL_SPLIT_RE = re.compile(r"(?<!\\)\|")
_TABLE_RULE_RE = re.compile(r"^:?-+:?$")
# A title-page line shorter than this is a stray mark, not a title.
_MIN_TITLE_CHARS = 3
# Short unlabelled lines above the first field of a title page ("CLINICAL STUDY
# REPORT", a study number) are used when room is left: at most this many, and
# none longer than this, since a longer line is prose.
_MAX_COVER_LINES = 6
_MAX_COVER_LINE_CHARS = 80
# The table that lays out a title page opens it: it starts within this many
# text lines. A two-column table further down is a glossary or a revision list.
_TITLE_TABLE_START_LINES = 15
# A table-of-contents entry copied from a Word file: text, a tab, a page number.
# Only the end of the line is looked at: matched against a whole line, this
# pattern takes quadratic time on a long run of tabs, and a document is
# untrusted input.
_TOC_TAIL_RE = re.compile(r"\t\s*\d+$")
_TOC_TAIL_CHARS = 24
# Nothing the rules keep is longer than a title, so a title-page line is cut
# to this before it is cleaned: the cost of a hostile megabyte-long line stays
# bounded.
_MAX_LINE_CHARS = 2000
_SENTENCE_END = (".", "!", "?", "…")
_UNNAMED_COMMUNITY_RE = re.compile(r"^Community \d+$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")
_NO_LINE = 10**9


def _clean(text: Any) -> str:
    """Graph labels and file text are untrusted: one line, no control
    characters, no credential-shaped tokens."""
    flat = " ".join(str(text or "").split())
    # Redact on both sides of the control-character strip, so a token cannot
    # hide behind an embedded control character.
    return redact_secrets(sanitize_label(redact_secrets(flat))).strip()


def _clean_summary(text: Any) -> str:
    """As ``_clean`` for a whole summary read back from a sidecar, which may be
    longer than the cap ``sanitize_label`` puts on a label."""
    flat = " ".join(str(text or "").split())
    return redact_secrets(_CONTROL_RE.sub("", redact_secrets(flat))).strip()


def _limit(max_chars: int) -> int:
    """``max_chars`` held inside the range a summary may have."""
    return max(SUMMARY_MIN_MAX_CHARS, min(int(max_chars), SUMMARY_HARD_MAX_CHARS))


def _shorten(text: str, limit: int) -> str:
    """``text`` cut to ``limit`` characters on a word boundary, ending in an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[: limit - 1]
    head = cut.rsplit(" ", 1)[0] if " " in cut else cut
    return head.rstrip(" ,;:.") + "…"


def _sentence(text: str) -> str:
    return text if text.endswith(_SENTENCE_END) else text + "."


def _whole_sentences(text: str) -> str:
    """A docstring label is cut at a fixed width, which can leave the start of
    a second sentence. Keep the complete sentences when there is at least one."""
    if not text.endswith("…"):
        return text
    whole = text[:-1].rstrip()
    # Cut exactly at the end of a sentence: only the ellipsis is surplus.
    if whole.endswith((".", "!", "?")):
        return whole
    end = max(whole.rfind(mark) for mark in (". ", "! ", "? "))
    return whole[: end + 1] if end > 0 else text


def _line(data: dict) -> int:
    m = _LINE_RE.match(str(data.get("source_location") or "").strip())
    return int(m.group(1)) if m else _NO_LINE


def _neighbors(G: nx.Graph, nid: str, relations: tuple[str, ...], *, outgoing: bool) -> list[str]:
    """Nodes joined to ``nid`` by one of ``relations``, in the edge's true direction.

    A link stored with flipped endpoints carries its real tail in ``_src``. An
    undirected graph without that marker has no direction to check, so both
    ends are accepted there; `graphify summarize` always loads a directed graph.
    """
    found: set[str] = set()
    arcs: list[tuple[str, str, "str | None"]]
    if isinstance(G, nx.DiGraph):
        arcs = [(nid, nb, nid) for nb in G.successors(nid)]
        arcs += [(nb, nid, nb) for nb in G.predecessors(nid)]
    else:
        arcs = [(nid, nb, None) for nb in G.neighbors(nid)]
    for u, v, tail in arcs:
        other = v if u == nid else u
        for data in edge_datas(G, u, v):
            if data.get("relation") not in relations:
                continue
            true_tail = data.get("_src", tail)
            if true_tail is None or (true_tail == nid) == outgoing:
                found.add(other)
    found.discard(nid)
    return sorted(found, key=str)


def _children(G: nx.Graph, nid: str) -> list[str]:
    """What ``nid`` contains, in source order."""
    kids = _neighbors(G, nid, ("contains",), outgoing=True)
    return sorted(kids, key=lambda k: (_line(G.nodes[k]), str(G.nodes[k].get("label") or ""), str(k)))


def _labels(G: nx.Graph, ids: list[str]) -> list[str]:
    """Cleaned, shortened, de-duplicated labels of ``ids``, keeping their order."""
    out: list[str] = []
    for i in ids:
        label = _shorten(_clean(G.nodes[i].get("label")), _MAX_ITEM_CHARS)
        if label and label not in out:
            out.append(label)
    return out


def _listing(prefix: str, items: list[str], max_items: int, budget: int) -> str:
    """``prefix`` plus as many ``items`` as fit in ``budget``, the rest counted
    as ``(+N more)``. Empty when not even one item fits."""
    for k in range(min(max_items, len(items)), 0, -1):
        rest = len(items) - k
        text = prefix + ", ".join(items[:k]) + (f" (+{rest} more)" if rest else "")
        if len(text) <= budget:
            return text
    return ""


def _assemble(lead: str, clauses: list[str]) -> str:
    """``lead`` then the clauses as one sentence; either part may be empty."""
    body = "; ".join(c for c in clauses if c)
    if body:
        # No second full stop after a value that already ends its sentence, or
        # after the ellipsis of a shortened name.
        body = _sentence(body[0].upper() + body[1:])
    return " ".join(p for p in (lead, body) if p)


def _room(lead: str, clauses: list[str], limit: int) -> int:
    """How many characters one more clause may take before ``limit`` is passed."""
    return limit - len(_assemble(lead, [c for c in clauses if c] + ["x"])) + 1


def is_file_node(data: dict) -> bool:
    """Whether a node's attributes describe a whole file: the nodes that get a summary."""
    if data.get("node_kind") == "heading" or data.get("file_type") == "rationale":
        return False
    return _is_file_node_label(data.get("label"), data.get("source_file"))


def file_node_ids(G: nx.Graph) -> list[str]:
    """Ids of the file-level nodes, sorted, so every run walks them in one order."""
    return sorted((n for n, d in G.nodes(data=True) if is_file_node(d)), key=str)


@dataclass(frozen=True)
class _Index:
    """Facts that take one pass over the whole graph, shared by every node
    summarized from it."""

    # ``source_file -> label`` of its file node, to name the file an imported symbol lives in.
    file_labels: dict[str, str]
    # Every node's name, the way an unnamed community borrows it (see _code_summary).
    node_names: frozenset[str]


def _index(G: nx.Graph) -> _Index:
    file_labels: dict[str, str] = {}
    names: set[str] = set()
    for nid in sorted(G.nodes, key=str):
        data = G.nodes[nid]
        name = str(data.get("label") or nid).strip()
        names.add(name[:-2] if name.endswith("()") else name)
        if is_file_node(data):
            file_labels.setdefault(str(data.get("source_file")), str(data.get("label")))
    return _Index(file_labels, frozenset(names))


# --------------------------------------------------------------------------- code


def _imports(G: nx.Graph, nid: str, data: dict, file_labels: dict[str, str]) -> list[str]:
    """What the file imports, as file and module names.

    An import of a symbol is listed as the file it lives in. Files of this
    project come first: they say more about a file's role than the standard
    library does.
    """
    own = str(data.get("source_file") or "")
    local: set[str] = set()
    external: set[str] = set()
    for target in _neighbors(G, nid, ("imports", "imports_from"), outgoing=True):
        tdata = G.nodes[target]
        source = str(tdata.get("source_file") or "")
        if not source:
            external.add(str(tdata.get("label") or ""))
        # A package's __init__.py is where `from package import x` resolves; it names nothing.
        elif source != own and Path(source).name != "__init__.py":
            local.add(file_labels.get(source) or Path(source).name)
    names: list[str] = []
    for group in (local, external):
        for raw in sorted(group, key=lambda s: (s.lower(), s)):
            name = _shorten(_clean(raw), _MAX_ITEM_CHARS)
            if name and name not in names:
                names.append(name)
    return names


def _code_summary(G: nx.Graph, nid: str, data: dict, index: _Index, limit: int) -> str:
    # The module docstring is a rationale node pointing at the file; a comment
    # further down the file can be one too, so the earliest line wins.
    docs = [G.nodes[r] for r in _neighbors(G, nid, ("rationale_for",), outgoing=False)
            if G.nodes[r].get("file_type") == "rationale"]
    docs.sort(key=lambda r: (_line(r), str(r.get("label") or "")))
    # The extractor already caps a docstring label; the cap here keeps room for
    # the symbols when a graph from another source carries a longer one.
    text = _shorten(_whole_sentences(_clean(docs[0].get("label"))), _MAX_LEAD_CHARS) if docs else ""
    lead = _sentence(text) if text else ""

    kids = [k for k in _children(G, nid) if not is_file_node(G.nodes[k])]
    # Public names first: a leading underscore marks an internal helper.
    kids.sort(key=lambda k: str(G.nodes[k].get("label") or "").lstrip(".").startswith("_"))
    symbols = _labels(G, kids)
    imports = _imports(G, nid, data, index.file_labels)

    clauses: list[str] = []
    clauses.append(_listing("defines ", symbols, _MAX_SYMBOLS, _room(lead, clauses, limit)))
    clauses.append(_listing("imports ", imports, _MAX_IMPORTS, _room(lead, clauses, limit)))
    if not lead:
        name = str(data.get("community_name") or "").strip()
        # Only a name someone gave the community. Without one it is called after
        # its busiest node (cluster.label_communities_by_hub) or "Community N",
        # which says nothing about this file.
        curated = name not in index.node_names and not _UNNAMED_COMMUNITY_RE.match(name)
        community = _shorten(_clean(name), _MAX_ITEM_CHARS) if curated else ""
        if community:
            clause = f'community "{community}"'
            # A community name alone says nothing about the file.
            if any(clauses) and len(clause) <= _room(lead, clauses, limit):
                clauses.append(clause)
    return _assemble(lead, clauses)


# ---------------------------------------------------------------------- documents


def _outline_summary(G: nx.Graph, nid: str, limit: int) -> str:
    """Title and sections from the heading nodes: no file is read."""
    tops = _children(G, nid)
    names = _labels(G, tops)
    if not names:
        return ""
    if len(tops) == 1:
        # A document's title gets the room a title-page title gets, not the
        # shorter cap of a listed name.
        full = _shorten(_clean(G.nodes[tops[0]].get("label")), _MAX_TITLE_CHARS)
        title = f'"{full}"'
        sections = _labels(G, _children(G, tops[0]))
        listing = _listing(": sections ", sections, _MAX_SECTIONS,
                           limit - len(title) - 1)
        return _sentence(title + listing)
    listing = _listing("Sections: ", names, _MAX_SECTIONS, limit - 1)
    return _sentence(listing) if listing else ""


def _plain_lines(lines: list[str], start: int, end: int, headings: set[int]) -> list[str]:
    """The non-blank text lines in ``lines[start:end]``, raw: no headings, HTML
    comments or fenced code. Fences are tracked from the first line, as the
    Markdown extractor does."""
    from graphify.extractors.markdown import _fence_closes, _fence_open

    out: list[str] = []
    fence = None
    for i, text in enumerate(lines[:end]):
        if fence is not None:
            if _fence_closes(text, fence):
                fence = None
            continue
        opened = _fence_open(text)
        if opened is not None:
            fence = opened
            continue
        if i < start or i in headings:
            continue
        if text.strip() and not text.lstrip().startswith("<!--"):
            out.append(text[:_MAX_LINE_CHARS])
    return out


def _is_toc_line(raw: str) -> bool:
    return bool(_TOC_TAIL_RE.search(raw.rstrip()[-_TOC_TAIL_CHARS:]))


def _is_title_label(label: str) -> bool:
    return label.lower().split()[-1] == "title"


def _table_cells(raw: str) -> "list[str] | None":
    """The cells of a Markdown table row, or None when ``raw`` is not one."""
    text = raw.strip()
    if not text.startswith("|"):
        return None
    inner = text[1:-1] if text.endswith("|") and not text.endswith("\\|") else text[1:]
    return [cell.replace("\\|", "|").strip() for cell in _CELL_SPLIT_RE.split(inner)]


def _is_table_rule(cells: list[str]) -> bool:
    """The ``| --- | --- |`` row under a table's first row."""
    return bool(cells) and all(_TABLE_RULE_RE.match(cell) for cell in cells)


def _fields(raw_lines: list[str]) -> list[tuple[str, str]]:
    """The labelled fields among ``raw_lines``, first occurrence of each label.

    A field is a ``Label: value`` line, or a row of a two-column table, which
    is how a title page is usually laid out in a Word document. Table fields
    come from one table only: the first that has any, and only one that starts
    near the top of ``raw_lines``. A two-column table further down (a glossary,
    a revision history) holds data, not the document's identity.
    """
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    table = 0
    table_start = 0
    form_table: "int | None" = None
    for i, raw in enumerate(raw_lines):
        cells = _table_cells(raw)
        if cells is not None:
            # A table's first row follows a line that is not a row, or is the
            # row above a rule row when two tables sit back to back.
            following = _table_cells(raw_lines[i + 1]) if i + 1 < len(raw_lines) else None
            after_row = i > 0 and _table_cells(raw_lines[i - 1]) is not None
            if not after_row or (following is not None and _is_table_rule(following)):
                table += 1
                table_start = i
            if (len(cells) != 2 or _is_table_rule(cells) or form_table not in (None, table)
                    or table_start >= _TITLE_TABLE_START_LINES):
                continue
            text = f"{_clean(cells[0]).rstrip(':').rstrip()}: {_clean(cells[1])}"
        elif _is_toc_line(raw):
            continue
        else:
            text = _clean(raw)
        m = _FIELD_RE.match(text)
        if not m:
            continue
        label, value = m.group(1).strip(), m.group(2).strip()
        key = label.lower()
        if key in seen or len(label.split()) > _MAX_FIELD_LABEL_WORDS:
            continue
        if _NUMBERED_LABEL_RE.search(label):
            continue
        # A value that is itself a label ("Signed: Date:") is an empty form line.
        if value.endswith(":"):
            continue
        value = value.rstrip(" ,;")
        # A long value is a sentence that happens to contain a colon. A title is
        # the exception: it is often long, and it is shortened when used.
        if not value or (len(value) > _MAX_FIELD_VALUE_CHARS and not _is_title_label(label)):
            continue
        seen.add(key)
        out.append((label, value))
        if cells is not None:
            form_table = table
    return out


def _cover_lines(raw_lines: list[str], title: str) -> list[str]:
    """The short unlabelled lines that open a title page, above its first
    labelled line or table: a document type, a product name, a study number.
    The line already used as the title is left out."""
    out: list[str] = []
    seen = {title.casefold()}
    for raw in raw_lines:
        if _table_cells(raw) is not None:
            break
        text = _clean(raw)
        if _FIELD_RE.match(text) and not text.endswith(":"):
            break
        if (not text or not text[0].isalnum() or text.endswith(":")
                or not _MIN_TITLE_CHARS <= len(text) <= _MAX_COVER_LINE_CHARS
                or _is_toc_line(raw) or text.casefold() in seen):
            continue
        seen.add(text.casefold())
        out.append(text)
        if len(out) == _MAX_COVER_LINES:
            break
    return out


def _title_page(lines: list[str]) -> "tuple[str, list[tuple[str, str]], list[str]] | None":
    """``(title, fields, cover lines)`` from a document's title page, or None
    when it has none.

    The title page is the text before the first top-level heading, where the
    top level is the shallowest heading level the document uses. It is
    recognised by its labelled fields (see ``_fields``): an introduction in
    plain prose is not a title page, and such a document is left to the
    outline, as is one that opens with its top-level heading.
    """
    from graphify.extractors.markdown import _split_frontmatter
    from graphify.sections import _headings

    _, body_start = _split_frontmatter(lines)
    heads = _headings(lines)
    heading_lines = {ln - 1 for ln, _, _ in heads}
    top_level = min((level for _, level, _ in heads), default=1)
    top = [ln - 1 for ln, level, _ in heads if level == top_level]
    first = top[0] if top else len(lines)

    preamble = _plain_lines(lines, body_start,
                            min(first, body_start + _TITLE_PAGE_SCAN_LINES), heading_lines)
    text_lines = [c for c in (_clean(raw) for raw in preamble) if c and c[0].isalnum()]
    if not text_lines and not any(_table_cells(raw) is not None for raw in preamble):
        return None

    fields = _fields(preamble)
    if not fields and top:
        # A title page that is itself the first top-level section.
        end = top[1] if len(top) > 1 else len(lines)
        fields = _fields(_plain_lines(lines, first + 1,
                                      min(end, first + 1 + _TITLE_PAGE_SCAN_LINES),
                                      heading_lines))

    if not fields:
        return None

    title = ""
    for label, value in fields:
        if _is_title_label(label):
            title = value
            # A second title field ("Short Title") repeats the first.
            fields = [f for f in fields if not _is_title_label(f[0])]
            break
    if not title:
        # An unlabelled title is one of the first lines of the page.
        for line in text_lines[:_TITLE_CANDIDATE_LINES]:
            if (len(line) >= _MIN_TITLE_CHARS and not line.endswith(":")
                    and not _FIELD_RE.match(line)):
                title = line
                break
    return title, fields, _cover_lines(preamble, title)


def _read_lines(data: dict, root: Path) -> "list[str] | None":
    """The Markdown source of a page node, or None when it must not or cannot be read."""
    from graphify.extractors.base import _read_source_text
    from graphify.sections import _resolve_inside, is_section_node

    if data.get("node_kind") != "page" or not is_section_node(data) or data.get("repo"):
        return None
    path = _resolve_inside(str(data.get("source_file") or ""), root)
    # The reader can hand back bytes an earlier build in this process read for
    # the same path (paths.take_preread_bytes), so a file that has since been
    # deleted is checked for here rather than left to raise.
    if path is None or not path.is_file():
        return None
    try:
        return _read_source_text(path, warn=False).splitlines()
    except (OSError, UnicodeError):
        return None


def _document_summary(G: nx.Graph, nid: str, data: dict, root: "Path | None",
                      limit: int) -> str:
    lines = _read_lines(data, root) if root is not None else None
    page = _title_page(lines) if lines else None
    if page is None:
        return _outline_summary(G, nid, limit)

    title, fields, cover = page
    lead = _sentence(_shorten(title, _MAX_TITLE_CHARS)) if title else ""
    parts: list[str] = []
    for label, value in fields:
        field = f"{label}: {value}"
        if len(field) > _room(lead, parts, limit):
            break
        parts.append(field)
    if not parts:
        # A title alone is thin; say what the document contains when there is room.
        names = _labels(G, _children(G, nid))
        parts.append(_listing("sections: ", names, _MAX_SECTIONS, _room(lead, parts, limit)))
    # The title and the fields come first. Only the room they leave goes to
    # the cover lines, which then read in page order, right after the title.
    for line in cover:
        longer = " ".join(p for p in (lead, _sentence(line)) if p)
        if len(_assemble(longer, parts)) > limit:
            break
        lead = longer
    return _assemble(lead, parts)


# ------------------------------------------------------------------------ public


def summarize_node(G: nx.Graph, nid: str, root: "Path | None" = None, *,
                   index: "_Index | None" = None,
                   max_chars: "int | None" = None) -> "str | None":
    """The summary of file-level node ``nid``, or None when it is not a file
    node or there is nothing to say about it.

    ``root`` is the project root documents may be read from. Without it no file
    is opened and a document is summarized from its heading outline.
    ``index`` is the result of one pass over the graph, passed in by callers
    that summarize many nodes; it is computed here when left out.
    ``max_chars`` is the longest the summary may be, held inside
    ``SUMMARY_MIN_MAX_CHARS``..``SUMMARY_HARD_MAX_CHARS``. Left out, it is
    ``SUMMARY_MAX_CHARS`` for a code file and ``SUMMARY_DOCUMENT_MAX_CHARS``
    for a document.
    """
    if nid not in G:
        return None
    data = G.nodes[nid]
    if not is_file_node(data):
        return None
    is_document = data.get("node_kind") == "page" or data.get("file_type") == "document"
    default = SUMMARY_DOCUMENT_MAX_CHARS if is_document else SUMMARY_MAX_CHARS
    limit = _limit(default if max_chars is None else max_chars)
    if is_document:
        text = _document_summary(G, nid, data, root, limit)
    else:
        text = _code_summary(G, nid, data, _index(G) if index is None else index, limit)
    text = _shorten(text, limit)
    return text or None


def build_summaries(G: nx.Graph, root: "Path | None" = None,
                    max_chars: "int | None" = None) -> dict[str, Any]:
    """The sidecar document for ``G``: one entry per file node that has a summary."""
    nodes: dict[str, dict[str, str]] = {}
    index = _index(G)
    for nid in file_node_ids(G):
        summary = summarize_node(G, nid, root, index=index, max_chars=max_chars)
        if not summary:
            continue
        data = G.nodes[nid]
        nodes[str(nid)] = {
            "label": _clean(data.get("label")),
            "source_file": _clean(data.get("source_file")),
            "summary": summary,
            "generated_by": SUMMARY_GENERATOR,
        }
    return {
        "version": SUMMARY_SCHEMA_VERSION,
        "generator": SUMMARY_GENERATOR,
        "nodes": nodes,
    }


def write_summaries(G: nx.Graph, out_path: Path, root: "Path | None" = None,
                    max_chars: "int | None" = None) -> tuple[Path, int, int]:
    """Write the sidecar for ``G`` to ``out_path``.

    Returns ``(path, summarized, file_nodes)``. When no file node has a summary
    no file is created. A sidecar that is already there is replaced by an empty
    one: left alone, its entries would go on being shown as current.
    """
    out_path = Path(out_path)
    data = build_summaries(G, root, max_chars)
    summarized = len(data["nodes"])
    if summarized or out_path.is_file():
        out_path.parent.mkdir(parents=True, exist_ok=True)
        # No timestamp, and entries in node-id order: the same input gives the same bytes.
        write_text_atomic(out_path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return out_path, summarized, len(file_node_ids(G))


def load_summaries(graph_path: Path) -> dict[str, dict[str, Any]]:
    """``{node_id: entry}`` from the sidecar next to ``graph_path``.

    A missing, unreadable or malformed sidecar gives ``{}``; a malformed entry
    is skipped on its own. Summaries are cleaned and held to the longest
    length `--max-chars` allows, since the file can be edited by hand or
    written by another tool.
    """
    sidecar = Path(graph_path).parent / SUMMARY_SIDECAR_NAME
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    nodes = data.get("nodes") if isinstance(data, dict) else None
    if not isinstance(nodes, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for nid, entry in nodes.items():
        if not isinstance(entry, dict):
            continue
        summary = entry.get("summary")
        source = entry.get("source_file")
        if not isinstance(summary, str) or not summary.strip():
            continue
        if source is not None and not isinstance(source, str):
            continue
        out[str(nid)] = {**entry,
                         "summary": _shorten(_clean_summary(summary), SUMMARY_HARD_MAX_CHARS)}
    return out
