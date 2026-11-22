"""HTML structural extractor: literal ``href`` / ``src`` references (#5226).

HTML is classified as a document, so the structural (AST-only) pass used to
skip it entirely: a page linking ``./details.html`` and loading
``../scripts/app.js`` contributed no edges until an LLM read it. This is the
deterministic counterpart. It reads each start tag's ``href`` / ``src``
attribute with the standard-library parser and emits one ``references`` edge
from the page to every target that is

* a literal relative path (no scheme, no ``//host``, no root-relative ``/x``,
  no template or interpolation syntax),
* an existing file inside the scan root, and
* of a kind graphify scans (a source file or a document).

Anything else yields no edge: remote URLs, in-page anchors, framework routes,
dynamic strings, missing targets, assets graphify does not index, and paths
that leave the scan root. A document carrying a ``<base href>`` rewrites every
relative reference, so none of its relative targets are read.

Only the page node and these edges are produced; classification stays
``document`` so semantic extraction of the page's prose is unchanged.
"""
from __future__ import annotations

import os
from html.parser import HTMLParser
from pathlib import Path

from graphify.detect import FileType, _resolves_under_root, classify_file
from graphify.extractors.base import _make_id, _read_source_text, active_scan_root
from graphify.extractors.markdown import _is_external_link, _percent_decoded

# A generated page (graph.html, a coverage report) can be megabytes of inline
# data and carries no authored references; keep it to a page node.
_HTML_MAX_BYTES = 2 * 1024 * 1024

_REFERENCE_ATTRS = ("href", "src")

# A value holding any of these is a template or interpolation expression, not a
# literal path (Jinja/Django/Handlebars `{{ }}` `{% %}`, ERB/EJS/ASP `<% %>`,
# PHP `<? ?>`, JS template `${}`, shell/Angular `$`, Razor `@`).
_DYNAMIC_MARKERS = ("{", "}", "<", ">", "$", "@", "`", "\\")


def _literal_target(raw: str) -> str | None:
    """The file part of a literal relative reference, else None."""
    target = raw.strip()
    # Drop the fragment and query: `./a.html#top` and `./a.html?x=1` name a.html.
    target = target.split("#", 1)[0].split("?", 1)[0].strip()
    if not target or _is_external_link(target):
        return None
    if any(marker in target for marker in _DYNAMIC_MARKERS):
        return None
    if target.startswith("/") or os.path.isabs(target):
        return None  # server-root-relative or absolute: a route, not this tree
    if ":" in target.split("/", 1)[0]:
        return None  # an unrecognised scheme such as `javascript:` or `ftp:`
    return target


class _ReferenceCollector(HTMLParser):
    """Collect ``(line, raw value)`` for every start tag's href/src, in order."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[tuple[int, str]] = []
        self.has_base = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "base" and any(name == "href" for name, _ in attrs):
            self.has_base = True
        line = self.getpos()[0]
        for name, value in attrs:
            if name in _REFERENCE_ATTRS and value:
                self.references.append((line, value))

    handle_startendtag = handle_starttag  # `<script src=... />`, `<link ... />`


def extract_html(path: Path) -> dict:
    """Extract the page node and its literal local ``href``/``src`` references."""
    str_path = str(path)
    file_nid = _make_id(str_path)
    nodes = [{
        "id": file_nid, "label": path.name, "file_type": "document",
        "node_kind": "page", "source_file": str_path, "source_location": "L1",
    }]
    result: dict = {
        "nodes": nodes, "edges": [], "raw_calls": [],
        "input_tokens": 0, "output_tokens": 0,
    }
    try:
        if path.stat().st_size > _HTML_MAX_BYTES:
            return result
        source = _read_source_text(path)
    except Exception as e:  # unreadable or not UTF-8: a page node, no references
        return {"nodes": [], "edges": [], "error": str(e)}

    collector = _ReferenceCollector()
    try:
        collector.feed(source)
        collector.close()
    except Exception:  # the stdlib parser is lenient; never fail the scan on markup
        return result
    if collector.has_base:
        return result  # relative references resolve against <base>, not this file

    scan_root = active_scan_root()
    source_dir = path.parent
    seen: set[str] = set()
    for line, raw in collector.references:
        target = _literal_target(raw)
        if target is None:
            continue
        target = _percent_decoded(target, source_dir)
        if _literal_target(target) is None:
            continue  # decoding revealed a scheme, a host or a dynamic marker
        resolved = Path(os.path.normpath(str(source_dir / target)))
        try:
            if not resolved.is_file():
                continue
            if scan_root is not None and not _resolves_under_root(resolved, scan_root):
                continue
            if classify_file(resolved) not in (FileType.CODE, FileType.DOCUMENT):
                continue
        except OSError:
            continue
        target_nid = _make_id(str(resolved))
        if target_nid == file_nid or target_nid in seen:
            continue
        seen.add(target_nid)
        # `target_file` lets the id-canonicalization pass repoint the edge at the
        # target's real node whether or not that file is in this batch; an edge
        # to a file that is not scanned is dropped there, never a ghost node.
        result["edges"].append({
            "source": file_nid, "target": target_nid, "relation": "references",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0,
            "target_file": str(resolved),
        })
    return result
