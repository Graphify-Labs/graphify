"""CSS selector extraction for Shopify themes.

``css_selectors`` is a pure scanner (class, id and custom-element type selectors in
selector position, with the line of each occurrence); ``extract_css`` turns a theme's
``.css`` assets into one node per ``(file, selector)``. Outside a Shopify theme it
returns no nodes, because ``.css`` is registered for every repository.
"""
from __future__ import annotations

import bisect
import hashlib
import os
import re
from pathlib import Path

from graphify.extractors.base import _make_id, _read_source_text

# Pseudo-classes whose argument is itself a selector list: the argument is scanned.
_SELECTOR_PSEUDOS = frozenset({"is", "where", "not", "has", "matches", "-webkit-any", "-moz-any"})
_NOISE_START = re.compile(r"/\*|\"|'")
_BOUNDARY = re.compile(r"[{};]")
_ATTRIBUTE = re.compile(r"\[[^\]\n]*\]")
_PSEUDO = re.compile(r"(?<!\\)::?([\w-]+)(\()?")
# ``.x`` / ``#x`` anywhere; a type selector only when it is a hyphenated custom element name.
_TOKEN = re.compile(
    r"(?<!\\)[.#](?:[A-Za-z_-]|\\.)(?:[\w-]|\\.)*"
    r"|(?<![\w.#\\-])[A-Za-z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)+(?![\w-])"
)
_ESCAPE = re.compile(r"\\(.)")
_NOT_NEWLINE = re.compile(r"[^\n]")


def _blank(chunk: str) -> str:
    """Replace every character but newlines with a space."""
    return _NOT_NEWLINE.sub(" ", chunk)


def _mask_noise(text: str) -> str:
    """Blank comments and string literals, keeping newlines. An unterminated one runs to the end."""
    pieces: list[str] = []
    pos = 0
    n = len(text)
    while True:
        m = _NOISE_START.search(text, pos)
        if m is None:
            pieces.append(text[pos:])
            break
        start = m.start()
        opener = m.group(0)
        if opener == "/*":
            close = text.find("*/", start + 2)
            end = n if close == -1 else close + 2
        else:
            end = start + 1
            while end < n and text[end] != opener and text[end] != "\n":
                end += 2 if text[end] == "\\" else 1
            end = min(end, n)
            if end < n and text[end] == opener:
                end += 1
        pieces.append(text[pos:start])
        pieces.append(_blank(text[start:end]))
        pos = end
    return "".join(pieces)


def _blank_pseudos(prelude: str) -> str:
    """Blank attribute selectors and pseudo-classes; keep the arguments of ``:is/:not/:where/:has``."""
    view = list(_ATTRIBUTE.sub(lambda m: " " * len(m.group(0)), prelude))
    work = "".join(view)
    pos = 0
    while True:
        m = _PSEUDO.search(work, pos)
        if m is None:
            break
        end = m.end()
        if m.group(2) and m.group(1).lower() not in _SELECTOR_PSEUDOS:
            depth = 1
            while end < len(work) and depth:
                depth += (work[end] == "(") - (work[end] == ")")
                end += 1
        for k in range(m.start(), end):
            if view[k] != "\n":
                view[k] = " "
        pos = end
    return "".join(view)


def css_selectors(text: str) -> list[tuple[str, int]]:
    """Every class, id and custom-element selector in selector position, as ``(selector, line)``.

    Comments, strings, declaration values, at-rule preludes and pseudo-classes yield nothing.
    A selector that appears several times is returned once per appearance.
    """
    clean = _mask_noise(text)
    newlines = [m.start() for m in re.finditer("\n", clean)]
    found: list[tuple[str, int]] = []
    start = 0
    for m in _BOUNDARY.finditer(clean):
        if m.group(0) != "{":
            start = m.end()
            continue
        prelude = clean[start:m.start()]
        if not prelude.lstrip().startswith("@"):
            view = _blank_pseudos(prelude)
            for tm in _TOKEN.finditer(view):
                found.append((_ESCAPE.sub(r"\1", tm.group(0)), bisect.bisect_left(newlines, start + tm.start()) + 1))
        start = m.end()
    return found


def css_selector_id(rel_path: str, selector: str) -> str:
    """Stable node id of ``selector`` in the file keyed by ``rel_path`` (the string used for its file node).

    The hash tells apart selectors that ``_make_id`` would fold together (``.a-b`` / ``.a_b``, ``.x`` / ``#x``).
    """
    digest = hashlib.sha1(selector.encode("utf-8")).hexdigest()[:8]
    return _make_id("css_selector", rel_path, selector, digest)


def selector_nodes_edges(path: Path, file_id: str, selectors: list[tuple[str, int]], line_offset: int = 0) -> tuple[list[dict], list[dict]]:
    """One node per selector (first appearance) and one ``contains`` edge per appearance from ``file_id``."""
    nodes: list[dict] = []
    edges: list[dict] = []
    seen: set[str] = set()
    for selector, line in selectors:
        nid = css_selector_id(str(path), selector)
        absolute = line + line_offset
        if nid not in seen:
            seen.add(nid)
            nodes.append({
                "id": nid, "label": selector, "file_type": "code",
                "source_file": str(path), "source_location": f"L{absolute}",
            })
        edges.append({
            "source": file_id, "target": nid, "relation": "contains", "confidence": "EXTRACTED",
            "source_file": str(path), "source_location": f"L{absolute}", "weight": 1.0,
        })
    return nodes, edges


def css_result(path: Path, text: str) -> dict:
    """Extraction result for CSS ``text`` that lives in ``path``: the file node plus its selectors."""
    file_id = _make_id(str(path))
    nodes, edges = selector_nodes_edges(path, file_id, css_selectors(text))
    file_node = {
        "id": file_id, "label": path.name, "file_type": "code",
        "source_file": str(path), "source_location": None,
    }
    return {"nodes": [file_node, *nodes], "edges": edges}


def extract_css(path: Path) -> dict:
    """Selector nodes of a ``.css`` file inside a Shopify theme; an empty ``skipped`` result elsewhere."""
    from graphify.extractors.liquid import _find_theme_root

    try:
        text = _read_source_text(path)
    except OSError:
        return {"error": f"cannot read {path}"}
    path = Path(os.path.abspath(path))
    if _find_theme_root(path) is None:
        return {"nodes": [], "edges": [], "skipped": "not a shopify theme"}
    return css_result(path, text)
