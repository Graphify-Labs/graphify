"""Twig template extractor: composition, macro imports, and library attachments.

Regex-based by design, mirroring ``extractors/blade.py``. Twig's tag grammar is
regular enough for composition extraction, and staying dependency-free avoids
pulling a tree-sitter grammar in for a template language.

Two dialects are resolved to real files rather than left as stubs:

* **Drupal Single Directory Components** -- ``{% include 'mytheme:card' %}``.
  The provider (``mytheme``) is a Drupal extension machine name, so its root is
  the nearest ancestor holding ``mytheme.info.yml``, and the component template
  lives at ``<root>/components/**/card/card.twig``.
* **Path references** -- ``{% extends 'layout.html.twig' %}`` and Symfony's
  ``@Namespace/path.html.twig``, resolved against the referring file's own
  directory and any enclosing ``templates/`` root.

A reference that resolves becomes an edge to that file's node, so templates link
to templates. A reference that does not resolve still emits an edge, to a stub
node carrying the raw reference: the include is a fact of the source even when
its target sits outside the scanned corpus.
"""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _blank_spans, _corpus_relative_path, _make_id

# `{# ... #}`. Twig comments do not nest, so a non-greedy span is exact.
# Stripped before extraction: component docblocks carry "Usage:" examples, and
# reading those as real tags gives a component an include edge to itself.
_TWIG_COMMENT = re.compile(r"\{#.*?#\}", re.DOTALL)

# `{% include 'x' %}` and friends. The optional `-` is Twig's whitespace-control
# spelling (`{%- include ... %}`).
_TWIG_TAG_REF = re.compile(
    r"\{%-?\s*(include|embed|extends|import|use)\s+(['\"])([^'\"]+)\2"
)

# `{% from 'x' import macro %}` puts the template before the keyword, so it
# cannot share the pattern above.
_TWIG_FROM_REF = re.compile(r"\{%-?\s*from\s+(['\"])([^'\"]+)\1\s+import\b")

# The function forms, `{{ include('x') }}` and `{{ source('x') }}`.
_TWIG_FN_REF = re.compile(r"\b(include|source)\(\s*(['\"])([^'\"]+)\2")

# `{% block content %}` -- a named extension point this template defines.
_TWIG_BLOCK = re.compile(r"\{%-?\s*block\s+([A-Za-z_]\w*)")

# Drupal's `{{ attach_library('mytheme/component') }}`.
_TWIG_ATTACH_LIBRARY = re.compile(r"\battach_library\(\s*(['\"])([^'\"]+)\1")

_TAG_RELATIONS = {
    "include": "includes",
    "embed": "embeds",
    "extends": "extends",
    "import": "imports_macro",
    "use": "uses_template",
    "from": "imports_macro",
    "source": "includes",
}

# `provider:component-name` -- Drupal SDC. Provider machine names are
# `[a-z0-9_]`; component names additionally allow `-`.
_SDC_REF = re.compile(r"^([a-z][a-z0-9_]*):([a-z0-9][a-z0-9_-]*)$")

# How far up the tree to look for a `<provider>.info.yml` or a `templates/` root.
_MAX_WALK_UP = 12

# Component index per Drupal extension root, keyed by that root's path string.
# Module-level dicts rather than functools.lru_cache, matching the caching
# convention in extractors/resolution.py.
_SDC_INDEX_CACHE: dict[str, dict[str, Path]] = {}

# Resolved extension root per (start dir, provider); None means "not found".
_PROVIDER_ROOT_CACHE: dict[tuple[str, str], "Path | None"] = {}


def _provider_root(start: Path, provider: str) -> "Path | None":
    """Nearest ancestor of *start* that is the Drupal extension named *provider*.

    Identified by `<provider>.info.yml`, the file every Drupal theme and module
    carries at its root.
    """
    key = (str(start), provider)
    if key in _PROVIDER_ROOT_CACHE:
        return _PROVIDER_ROOT_CACHE[key]
    root: "Path | None" = None
    current = start
    for _ in range(_MAX_WALK_UP):
        try:
            if (current / f"{provider}.info.yml").is_file():
                root = current
                break
        except OSError:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    _PROVIDER_ROOT_CACHE[key] = root
    return root


def _sdc_index(root: Path) -> dict[str, Path]:
    """Map SDC component name -> its template, for one extension root.

    An SDC component is a directory whose template shares its name
    (`components/molecules/card/card.twig`), so the stem-equals-parent test
    identifies component templates without reading any YAML.
    """
    key = str(root)
    cached = _SDC_INDEX_CACHE.get(key)
    if cached is not None:
        return cached
    index: dict[str, Path] = {}
    components = root / "components"
    if components.is_dir():
        try:
            for template in components.rglob("*.twig"):
                if template.stem == template.parent.name:
                    index.setdefault(template.stem, template)
        except OSError:
            pass
    _SDC_INDEX_CACHE[key] = index
    return index


def _resolve_path_ref(raw: str, path: Path) -> "Path | None":
    """Resolve a non-SDC reference against the referring file's own tree."""
    # Symfony's `@Namespace/rest`: the namespace maps to a directory configured
    # outside the template, so only the remainder is usable statically.
    relative = raw.split("/", 1)[1] if raw.startswith("@") and "/" in raw else raw
    if not relative or relative.startswith("/") or ".." in Path(relative).parts:
        return None
    candidates = [path.parent / relative]
    current = path.parent
    for _ in range(_MAX_WALK_UP):
        templates = current / "templates"
        try:
            if templates.is_dir():
                candidates.append(templates / relative)
        except OSError:
            break
        parent = current.parent
        if parent == current:
            break
        current = parent
    for candidate in candidates:
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _resolve_twig_ref(raw: str, path: Path) -> "Path | None":
    """Resolve a Twig template reference to a real file, or None."""
    sdc = _SDC_REF.match(raw)
    if sdc:
        provider, name = sdc.groups()
        root = _provider_root(path.parent, provider)
        if root is None:
            return None
        return _sdc_index(root).get(name)
    return _resolve_path_ref(raw, path)


def extract_twig(path: Path) -> dict:
    """Extract include/embed/extends/import composition from a Twig template."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}
    src = _blank_spans(src, _TWIG_COMMENT)

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
        """Emit one edge, and a node for the target only when we own it.

        A reference that resolved to another file in the corpus gets NO node
        here: that file mints its own file node when it is extracted, and
        emitting a second one with the same id makes
        ``_disambiguate_colliding_node_ids`` rename the pair apart, which severs
        exactly the link we were trying to draw. Instead the edge carries a
        ``target_file`` stamp and the target canonicalizes onto the real node
        downstream — the pattern `extract_markdown` uses for doc-to-doc links.
        """
        if target_file is None and target_id not in seen_nodes:
            seen_nodes.add(target_id)
            nodes.append({"id": target_id, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": None})
        # One edge per (target, relation): a template that includes the same
        # component twice is one dependency, and duplicate parallel edges trip
        # graphify's own same-endpoint-collapse diagnostic.
        key = (target_id, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {"source": file_nid, "target": target_id, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str_path, "source_location": location,
                "weight": 1.0}
        if target_file is not None:
            edge["target_file"] = target_file
        edges.append(edge)

    def add_template_ref(raw: str, relation: str, offset: int) -> None:
        raw = raw.strip()
        if not raw:
            return
        resolved = _resolve_twig_ref(raw, path)
        if resolved is not None:
            target_file = _corpus_relative_path(resolved, path)
            add(_make_id(target_file), resolved.name, relation, line_of(offset),
                target_file=target_file)
        else:
            add(_make_id(raw), raw, relation, line_of(offset))

    for m in _TWIG_TAG_REF.finditer(src):
        add_template_ref(m.group(3), _TAG_RELATIONS[m.group(1)], m.start())

    for m in _TWIG_FROM_REF.finditer(src):
        add_template_ref(m.group(2), _TAG_RELATIONS["from"], m.start())

    for m in _TWIG_FN_REF.finditer(src):
        add_template_ref(m.group(3), _TAG_RELATIONS[m.group(1)], m.start())

    for m in _TWIG_BLOCK.finditer(src):
        name = m.group(1)
        add(_make_id(str_path, "block", name), name, "defines_block",
            line_of(m.start()))

    for m in _TWIG_ATTACH_LIBRARY.finditer(src):
        library = m.group(2)
        add(_make_id(library), library, "attaches_library", line_of(m.start()))

    return {"nodes": nodes, "edges": edges}
