"""SCSS/Sass extractor: module graph, mixin graph, and design-token graph.

Regex-based by design, mirroring ``extractors/blade.py``. The three relationships
worth graphing in a stylesheet are all lexical, so a parser buys nothing here:

* ``@use`` / ``@forward`` / ``@import`` -- the module graph, resolved through
  Sass's partial (``_name.scss``) and index (``name/_index.scss``) conventions so
  edges land on real files.
* ``@mixin`` / ``@include`` -- the mixin graph. Both sides key off a shared,
  file-independent node, so the file defining a mixin and every file using it
  connect through it. A namespaced use (``@include mx.button-reset``) is keyed on
  the bare name, since that is what the definition is called.
* ``--custom-property`` declarations and ``var(--custom-property)`` references --
  the design-token graph, likewise sharing one node per token so token-defining
  stylesheets connect to every consumer.

Plain ``.css`` is deliberately not routed here: in a Sass project the CSS files
are compiled output of the very ``.scss`` sources already indexed, so indexing
both would duplicate the whole stylesheet layer.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _blank_spans, _corpus_relative_path, _make_id

# Comments, stripped before extraction so a commented-out or illustrative
# `@use`/`@include` is not read as a real dependency. The `//` form is guarded
# against `:` so a `https://` inside `url(...)` is not mistaken for one.
_SCSS_BLOCK_COMMENT = re.compile(r"/\*.*?\*/", re.DOTALL)
_SCSS_LINE_COMMENT = re.compile(r"(?<![:/])//[^\n]*")

# `@use 'x' as y`, `@forward 'x'`, `@import 'a', 'b'`. The tail is captured whole
# and scanned for quoted strings, because `@import` accepts a comma-separated
# list. `\b` keeps `@import` from matching the `@include` rule below.
_SCSS_AT_RULE = re.compile(r"@(use|forward|import)\b([^;{]*)")
_SCSS_QUOTED = re.compile(r"(['\"])([^'\"]+)\1")

# `@mixin button-reset` / `@mixin button-reset($size)`.
_SCSS_MIXIN_DEF = re.compile(r"@mixin\s+([A-Za-z_][\w-]*)")

# `@include button-reset` and the namespaced `@include mx.button-reset`.
_SCSS_MIXIN_USE = re.compile(r"@include\s+([A-Za-z_][\w-]*(?:\.[A-Za-z_][\w-]*)?)")

# A custom-property declaration: `--spacing-05: 16px;`. Anchored on the start of
# a line, a `{`, or a preceding `;` so a single-line block (`:root { --a: 1px; }`)
# is caught too. A *reference* is always preceded by `(` or `,` inside `var()`,
# so none of these delimiters can match one.
_SCSS_TOKEN_DEF = re.compile(r"(?:^|[{;])\s*(--[A-Za-z0-9_-]+)\s*:", re.MULTILINE)

# A custom-property reference: `var(--spacing-05, 16px)`.
_SCSS_TOKEN_USE = re.compile(r"var\(\s*(--[A-Za-z0-9_-]+)")

# Sass's own module namespace (`@use 'sass:math'`) and anything fetched or
# resolved through a package manager: real dependencies, but not files in the
# corpus, so they stay stubs rather than failed resolutions.
_SCSS_NON_FILE_PREFIXES = ("sass:", "http:", "https:", "//", "~")

_SCSS_SOURCE_EXTS = (".scss", ".sass", ".css")

_MAX_WALK_UP = 12


def _resolve_scss_import(raw: str, path: Path) -> "Path | None":
    """Resolve a Sass module reference through the partial/index conventions."""
    if not raw or raw.startswith(_SCSS_NON_FILE_PREFIXES):
        return None
    ref = Path(raw)
    if ref.is_absolute():
        return None
    directory = path.parent / ref.parent
    stem = ref.name
    if not stem:
        return None
    candidates: list[Path] = []
    if ref.suffix in _SCSS_SOURCE_EXTS:
        bare = stem[: -len(ref.suffix)]
        candidates += [directory / stem, directory / f"_{bare}{ref.suffix}"]
    else:
        # Sass prefers the partial spelling, so `_name.scss` is tried first.
        for name in (f"_{stem}", stem):
            candidates += [directory / f"{name}{ext}" for ext in _SCSS_SOURCE_EXTS]
        for index in ("_index", "index"):
            candidates += [
                directory / stem / f"{index}{ext}" for ext in _SCSS_SOURCE_EXTS
            ]
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def extract_scss(path: Path) -> dict:
    """Extract module imports, mixin definitions/uses, and design-token usage."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}
    src = _blank_spans(_blank_spans(src, _SCSS_BLOCK_COMMENT), _SCSS_LINE_COMMENT)

    str_path = str(path)
    file_nid = _make_id(str_path)
    nodes = [{"id": file_nid, "label": path.name, "file_type": "code",
              "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_nodes = {file_nid}
    seen_edges: set[tuple[str, str]] = set()

    def line_of(offset: int) -> str:
        return f"L{src.count(chr(10), 0, offset) + 1}"

    def add(target_id: str, label: str, relation: str, location: str,
            target_file: "str | None" = None) -> None:
        # A reference that resolved to another stylesheet gets NO node here:
        # that file mints its own file node when extracted, and a second one
        # with the same id makes _disambiguate_colliding_node_ids rename the
        # pair apart, severing the very link being drawn. The edge's
        # target_file stamp canonicalizes it onto the real node instead —
        # the pattern extract_markdown uses for doc-to-doc links.
        if target_file is None and target_id not in seen_nodes:
            seen_nodes.add(target_id)
            nodes.append({"id": target_id, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": None})
        # One edge per (target, relation). A stylesheet referencing the same
        # token in 150 declarations is one dependency on it, and duplicate
        # parallel edges trip graphify's same-endpoint-collapse diagnostic.
        key = (target_id, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {"source": file_nid, "target": target_id, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str_path, "source_location": location,
                "weight": 1.0}
        # Stamp the resolved path so the target canonicalizes to the imported
        # stylesheet's real node id; without it the target keeps an
        # absolute-path derived id that matches no node in the merged graph and
        # the import edge silently drops (#2211). Only set when the reference
        # resolved — an unresolvable import must stay dangling.
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

    for rule in _SCSS_AT_RULE.finditer(src):
        for quoted in _SCSS_QUOTED.finditer(rule.group(2)):
            raw = quoted.group(2).strip()
            if not raw:
                continue
            resolved = _resolve_scss_import(raw, path)
            if resolved is not None:
                target_file = _corpus_relative_path(resolved, path)
                add(_make_id(target_file), resolved.name, "imports",
                    line_of(rule.start()), target_file=target_file)
            else:
                add(_make_id(raw), raw, "imports", line_of(rule.start()))

    for m in _SCSS_MIXIN_DEF.finditer(src):
        name = m.group(1)
        add(_make_id("scss-mixin", name), name, "defines_mixin", line_of(m.start()))

    for m in _SCSS_MIXIN_USE.finditer(src):
        # `mx.button-reset` -> `button-reset`: the namespace is the importing
        # file's local alias, while the definition carries the bare name.
        name = m.group(1).rsplit(".", 1)[-1]
        add(_make_id("scss-mixin", name), name, "uses_mixin", line_of(m.start()))

    for m in _SCSS_TOKEN_DEF.finditer(src):
        name = m.group(1)
        add(_make_id(name), name, "defines_token", line_of(m.start()))

    for m in _SCSS_TOKEN_USE.finditer(src):
        name = m.group(1)
        add(_make_id(name), name, "uses_token", line_of(m.start()))

    return {"nodes": nodes, "edges": edges}
