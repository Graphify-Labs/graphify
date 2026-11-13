"""Return the text of a Markdown section straight from its source file.

A heading node records the line its heading sits on. The section it opens is
found at read time from the current file: it runs to the line before the next
heading of the same or a shallower level, so it includes its subsections. The
boundary is never stored, so an edit inside a section cannot make it stale, and
graphs built before this module existed work unchanged.

Heading detection reuses the Markdown extractor's own rules (ATX headings,
CommonMark fences, leading frontmatter), so what counts as a heading here is
exactly what the extractor turned into a node.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from graphify.extractors.base import _read_source_text
from graphify.extractors.markdown import (
    _MD_ATX_CLOSING_RE,
    _MD_ATX_HEADING_RE,
    _fence_closes,
    _fence_open,
    _split_frontmatter,
)
from graphify.security import redact_secrets, sanitize_label

DEFAULT_MAX_CHARS = 8000

# The suffixes the extractor dispatches to extract_markdown.
_MARKDOWN_SUFFIXES = frozenset({".md", ".mdx", ".qmd", ".skill"})
_LINE_RE = re.compile(r"^L(\d+)$")
# Control characters other than tab, so a section keeps its line layout while a
# document cannot push terminal escapes or fake log lines into a model's context.
_BODY_CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


@dataclass(frozen=True)
class Section:
    source_file: str
    start: int
    end: int
    text: str
    truncated: bool
    moved: bool


def _headings(lines: list[str]) -> list[tuple[int, int, str]]:
    """``(line, level, title)`` for every heading the extractor would emit."""
    _, body_start = _split_frontmatter(lines)
    out: list[tuple[int, int, str]] = []
    fence = None
    # Like the extractor, track fences from the first line, frontmatter included.
    for i, text in enumerate(lines):
        if fence is not None:
            if _fence_closes(text, fence):
                fence = None
            continue
        opened = _fence_open(text)
        if opened is not None:
            fence = opened
            continue
        if i < body_start:
            continue
        m = _MD_ATX_HEADING_RE.match(text)
        title = _MD_ATX_CLOSING_RE.sub("", m.group(2).strip()) if m else ""
        if m and title:
            out.append((i + 1, len(m.group(1)), title))
    return out


def _resolve_inside(source_file: str, root: Path) -> "Path | None":
    """The file ``source_file`` names, or None when it falls outside ``root``."""
    candidate = Path(source_file)
    if not candidate.is_absolute():
        candidate = root / candidate
    try:
        resolved = candidate.resolve()
        resolved.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    return resolved


def section_root(gp: Path) -> Path:
    """The project root section reads are confined to, for the graph at ``gp``.

    For a graph in ``<project>/graphify-out`` a ``.graphify_root`` marker may
    only narrow the root to a folder inside the project, never widen it, so a
    committed marker cannot open the rest of the disk to reads.
    """
    from graphify.paths import GRAPHIFY_OUT, graph_root_for

    root = graph_root_for(gp)
    out = Path(GRAPHIFY_OUT).parts
    if out and not Path(GRAPHIFY_OUT).is_absolute() and gp.parent.parts[-len(out):] == out:
        project = gp.parent.parents[len(out) - 1]
        try:
            root.resolve().relative_to(project.resolve())
        except (OSError, RuntimeError, ValueError):
            return project
    return root


def is_section_node(node: dict) -> bool:
    kind = node.get("node_kind")
    suffix = Path(str(node.get("source_file") or "")).suffix.lower()
    return kind in ("heading", "page") and suffix in _MARKDOWN_SUFFIXES


def read_section(node: dict, root: Path,
                 max_chars: int = DEFAULT_MAX_CHARS) -> "tuple[Section | None, str]":
    """Read the section a heading (or page) node opens. ``(section, "")`` or ``(None, reason)``."""
    label = str(node.get("label") or "")
    source_file = str(node.get("source_file") or "")
    if not is_section_node(node):
        return None, (f"'{label}' is not a Markdown heading or page. "
                      "get_section reads Markdown sections only.")
    if node.get("repo"):
        return None, (f"'{label}' comes from a merged multi-repo graph. "
                      "Read it from that repo's own graph.")
    path = _resolve_inside(source_file, root)
    if path is None:
        return None, f"Refusing to read '{source_file}': it is outside the project."
    try:
        lines = _read_source_text(path, warn=False).splitlines()
    except (OSError, UnicodeError) as exc:
        return None, f"Could not read {source_file}: {exc}"

    moved = False
    if node.get("node_kind") == "page":
        _, body_start = _split_frontmatter(lines)
        start, end = body_start + 1, len(lines)
    else:
        m = _LINE_RE.match(str(node.get("source_location") or "").strip())
        recorded = int(m.group(1)) if m else 0
        heads = _headings(lines)
        same = [h for h in heads
                if h[2] == label or sanitize_label(h[2]) == sanitize_label(label)]
        exact = [h for h in same if h[0] == recorded]
        # The recorded line wins. A heading that moved is followed only when its
        # title is unique in the file; with several, guessing could return the
        # wrong one.
        hit = exact[0] if exact else same[0] if len(same) == 1 else None
        if hit is None:
            return None, (f"'{label}' is no longer at line {recorded} of {source_file}. "
                          "Run `graphify update .` to refresh the graph.")
        moved = hit[0] != recorded
        start, level = hit[0], hit[1]
        end = next((ln - 1 for ln, lv, _ in heads if ln > start and lv <= level), len(lines))
    while end > start and not lines[end - 1].strip():
        end -= 1
    if end < start:
        return None, f"{source_file} has no text for '{label}'."
    body = "\n".join(_BODY_CONTROL_RE.sub("", ln) for ln in lines[start - 1:end])
    body = redact_secrets(body)
    truncated = len(body) > max_chars
    if truncated:
        body = body[:max_chars]
    return Section(sanitize_label(source_file), start, end, body, truncated, moved), ""


def format_section(section: Section, label: str) -> str:
    header = f"Section: {label}  [{section.source_file}:L{section.start}-L{section.end}]"
    notes = []
    if section.moved:
        notes.append("The heading moved since indexing; run `graphify update .` "
                     "to refresh the graph.")
    if section.truncated:
        notes.append(f"Truncated; read {section.source_file} lines "
                     f"{section.start}-{section.end} for the rest.")
    return "\n".join([header, *(f"Note: {n}" for n in notes), "", section.text])


def resolve_section_query(G, query: str) -> "tuple[str | None, str]":
    """Resolve a heading label, node id or ``path::Heading`` to one section node.

    A code symbol that shares a heading's name must not shadow it, so a query
    that is ambiguous or lands on a non-section node is retried against the
    section nodes alone.
    """
    from graphify.serve import _resolve_single_node

    nid, err = _resolve_single_node(G, query)
    if nid is not None and is_section_node(G.nodes[nid]):
        return nid, ""
    sections = G.subgraph([n for n, d in G.nodes(data=True) if is_section_node(d)])
    sec_nid, _ = _resolve_single_node(sections, query)
    if sec_nid is not None:
        return sec_nid, ""
    return nid, err or ""
