"""AsciiDoc extractor (#2938).

``.adoc`` was in no extension set, so a project whose documentation is
AsciiDoc had none of it in the graph — only the PNGs beside it. This mirrors
:mod:`graphify.extractors.markdown`: the file is a ``page`` node, each
section title a ``heading`` node nested by level, and every local document
the file pulls in or points at becomes a ``references`` edge whose target
id is minted from the resolved path so it merges into that document's own
node. The semantic pass then digests the prose exactly as it does markdown.

Links covered: ``include::other.adoc[]``, ``xref:other.adoc[text]`` /
``xref:other#anchor[]`` (an extension-less xref names a sibling ``.adoc``),
``link:guide.adoc[text]`` (a local path — ``link:https://...`` is external and
skipped), and the cross-document form of ``<<other.adoc#anchor,text>>``.
Targets that still carry an unresolved attribute (``{docdir}/x.adoc``) are
skipped rather than guessed.

Delimited blocks (listing ``----``, literal ``....``, comment ``////``,
passthrough ``++++``, example ``====``, sidebar ``****``, quote ``____``)
are skipped so their contents are neither headings nor links.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id
from graphify.security import sanitize_metadata

ASCIIDOC_EXTENSIONS: frozenset[str] = frozenset({".adoc", ".asciidoc"})

# Documents an AsciiDoc file may reference; kept in step with markdown's set.
_LINKABLE_EXTS: frozenset[str] = frozenset({
    ".adoc", ".asciidoc", ".md", ".mdx", ".qmd", ".markdown", ".rst", ".txt",
})

_TITLE_RE = re.compile(r"^(=+)\s+(\S.*?)\s*=*\s*$")
_INCLUDE_RE = re.compile(r"^include::([^\[\]]+)\[[^\]]*\]")
_XREF_RE = re.compile(r"xref:([^\[\]\s]+)\[[^\]]*\]")
_LINK_RE = re.compile(r"link:([^\[\]\s]+)\[[^\]]*\]")
_ANGLE_XREF_RE = re.compile(r"<<([^>,\s]+)(?:,[^>]*)?>>")
_ATTR_LINE_RE = re.compile(r"^:([A-Za-z0-9_][A-Za-z0-9_-]*):\s*(.*)$")

# Delimiter lines that open/close a block whose body must be skipped. A block
# closes on the SAME delimiter that opened it - same character AND same
# length, which is how AsciiDoc nests an example block inside an example
# block (`====` ... `======` ... `======` ... `====`).
_BLOCK_DELIM_CHARS = frozenset("-./+=*_")


def _block_delim(stripped: str) -> str | None:
    if len(stripped) >= 4 and stripped[0] in _BLOCK_DELIM_CHARS and stripped == stripped[0] * len(stripped):
        return stripped
    return None


def _resolve_doc_link(raw: str, source_dir: Path) -> Path | None:
    """Resolve a local document target to an absolute (normalised) path, or
    None for external URLs, in-page anchors, attribute-bearing paths, and
    non-document targets."""
    target = raw.strip()
    if not target:
        return None
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target:
        return None
    low = target.lower()
    if "://" in target or low.startswith(("mailto:", "tel:", "//", "data:")):
        return None
    if "{" in target or "}" in target:
        return None  # an unresolved AsciiDoc attribute; do not guess
    suffix = Path(target).suffix.lower()
    if suffix == "":
        target += ".adoc"
        suffix = ".adoc"
    if suffix not in _LINKABLE_EXTS:
        return None
    candidate = Path(target)
    if not candidate.is_absolute():
        candidate = source_dir / candidate
    return Path(os.path.normpath(str(candidate)))


def extract_asciidoc(path: Path) -> dict:
    """Extract page, section and document-reference structure from AsciiDoc."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, node_kind: str = "heading",
                 extra: dict | None = None) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        node = {"id": nid, "label": label, "file_type": "document",
                "node_kind": node_kind, "source_file": str_path,
                "source_location": f"L{line}"}
        if extra:
            node.update(extra)
        nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 target_file: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

    file_nid = _make_id(str_path)
    source_dir = path.parent
    linked: set[str] = set()

    def add_link(raw: str, line: int) -> None:
        resolved = _resolve_doc_link(raw, source_dir)
        if resolved is None:
            return
        # Same recipe as the target's own file node (see markdown.py): the
        # absolute path, canonicalised by extract()'s post-pass, so the edge
        # merges into the real document node instead of spawning a ghost.
        tgt_nid = _make_id(str(resolved))
        if tgt_nid == file_nid or tgt_nid in linked:
            return
        linked.add(tgt_nid)
        target_file = None
        try:
            if resolved.is_file():
                target_file = str(resolved)
        except OSError:
            pass
        add_edge(file_nid, tgt_nid, "references", line, target_file=target_file)

    lines = source.splitlines()
    # Header attributes (`:author: ...`) between the document title and the
    # first blank line play the role markdown frontmatter does.
    attributes: dict[str, str] = {}
    in_header = True
    heading_stack: list[tuple[int, str]] = []
    block_delim: str | None = None
    doc_title: str | None = None

    for idx, line_text in enumerate(lines):
        line_num = idx + 1
        stripped = line_text.strip()
        delim = _block_delim(stripped)
        if block_delim is not None:
            if delim == block_delim:
                block_delim = None
            continue
        if delim is not None:
            block_delim = delim
            continue
        if stripped.startswith("//"):
            continue  # line comment

        if in_header:
            if not stripped and doc_title is not None:
                in_header = False
            attr = _ATTR_LINE_RE.match(stripped) if stripped else None
            if attr:
                attributes[attr.group(1)] = attr.group(2).strip()
                continue

        m = _INCLUDE_RE.match(stripped)
        if m:
            add_link(m.group(1), line_num)
            continue
        for m in _XREF_RE.finditer(line_text):
            add_link(m.group(1), line_num)
        for m in _LINK_RE.finditer(line_text):
            add_link(m.group(1), line_num)
        for m in _ANGLE_XREF_RE.finditer(line_text):
            ref = m.group(1)
            if "#" in ref and Path(ref.split("#", 1)[0]).suffix:
                add_link(ref, line_num)  # cross-document form only

        title = _TITLE_RE.match(line_text)
        if not title:
            continue
        level = len(title.group(1))  # `=` is the document title (level 1)
        text = title.group(2).strip()
        if level == 1 and doc_title is None:
            doc_title = text
            continue  # the page node carries the document title
        h_nid = _make_id(stem, text)
        if h_nid in seen_ids:
            h_nid = _make_id(stem, text, str(line_num))
        add_node(h_nid, text, line_num)
        while heading_stack and heading_stack[-1][0] >= level:
            heading_stack.pop()
        parent = heading_stack[-1][1] if heading_stack else file_nid
        add_edge(parent, h_nid, "contains", line_num)
        heading_stack.append((level, h_nid))

    extra: dict = {}
    if doc_title:
        extra["title"] = doc_title
    if attributes:
        extra["frontmatter"] = sanitize_metadata(attributes)
    # The page node goes first, as in markdown, regardless of when the title
    # was seen.
    nodes.insert(0, {"id": file_nid, "label": path.name, "file_type": "document",
                     "node_kind": "page", "source_file": str_path,
                     "source_location": "L1", **extra})
    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}
