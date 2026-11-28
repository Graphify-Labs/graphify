"""Shopify theme Liquid extractor (regex only, deterministic).

Extracts the references a `.liquid` file of a Shopify theme makes to the rest of
the theme, so `graphify affected` answers "who uses this snippet / section /
block":

* ``render`` / ``include 'x'``          -> ``snippets/x.liquid``      (``imports``)
* ``section 'x'``                       -> ``sections/x.liquid``      (``imports``)
* ``sections 'x'``                      -> ``sections/x.json``        (``imports``)
* ``content_for 'block', type: 'x'``    -> ``blocks/x.liquid``        (``imports``)
* ``{% schema %}`` ``blocks[]`` entries -> ``blocks/<type>.liquid``   (``imports``)
* ``content_for 'blocks'`` in a file whose schema lists ``@theme`` -> every public
  ``blocks/*.liquid`` (no ``_`` prefix) not linked otherwise (``imports``, ``INFERRED``)
* ``{% schema %}`` ``presets[].blocks`` (nested, list or dict form) -> ``blocks/<type>.liquid``
  when that file exists (``imports``; section-local types get nothing)
* ``{% schema %}`` ``enabled_on`` / ``disabled_on`` ``templates`` and ``groups``
  -> ``templates/<x>.json`` (or ``.liquid``) and ``sections/<g>-group.json`` (or ``<g>.json``)
  (``references``; ``"*"`` gets nothing)
* ``'x' | asset_url`` / ``asset_img_url`` / ``inline_asset_content`` -> ``assets/x[.liquid]`` (``references``)
* ``'a.b' | t`` / ``| translate``       -> key ``a.b`` of the default locale (``references``)

Gates and limits, all fail-closed:

* A file is only analysed inside a theme root: the nearest ancestor (at most
  three levels up) holding ``layout/theme.liquid``. Jekyll and Eleventy also use
  ``.liquid`` with different ``include`` semantics, so elsewhere only the file
  node is emitted.
* Statically named targets that exist inside the theme root get an ``EXTRACTED``
  edge. A static name whose file (or locale key) does not exist becomes an
  ``AMBIGUOUS`` edge to a node flagged ``unresolved`` (id ``ref_liquid_<kind>_...``,
  kinds snippet, section, section_group, block, asset, t). List them with
  ``[e for e in links if e["confidence"] == "AMBIGUOUS" and e["target"].startswith("ref_liquid_")]``
  over graph.json. A full rebuild clears one once the file exists.
  Dynamic names (``render some_var``), names containing ``/``, ``\\`` or ``..``,
  and absolute asset names get nothing.
* Text inside ``comment``, ``doc``, ``raw``, ``stylesheet``, ``javascript`` and
  inline ``{% # %}`` regions is ignored; line numbers still count it.
* ``| t`` edges need exactly one ``locales/*.default.json``; keys under
  ``shopify.`` are provided by Shopify and get no edge.

Not covered: the ``{% block %}`` / ``{% partial %}`` preview tags, CSS and app
references, ``@app`` blocks, and schemas that accept only named block types
(``content_for 'blocks'`` then links nothing beyond the schema's own ``blocks[]``).
"""
from __future__ import annotations

import bisect
import json
import os
import re
from pathlib import Path

from graphify.extractors.base import _make_id, _read_source_text

_THEME_ROOT_LEVELS = 3
_MAX_LOCALE_BYTES = 8 * 1024 * 1024

_STMT_NAME = re.compile(r"\s*([A-Za-z_]\w*)")
_NAME_ARG = re.compile(r"""\s*(['"])([^'"\n]*)\1""")
_BLOCK_TYPE = re.compile(r"""\btype\s*:\s*(['"])([^'"\n]*)\1""")
# A quoted literal directly piped into asset_url or into the t / translate filter.
_FILTER = re.compile(r"""(['"])([^'"\n]+)\1\s*\|\s*(asset_url|asset_img_url|inline_asset_content|t|translate)(?![\w])""")
_ASSET_FILTERS = frozenset({"asset_url", "asset_img_url", "inline_asset_content"})
_ASSET_SUFFIX = re.compile(r"[?#]")
_JSON_COMMENT = re.compile(r'"(?:[^"\\\n]|\\.)*"|//[^\n]*|/\*.*?\*/', re.DOTALL)

_SKIP_UNTIL = {
    "raw": "endraw",
    "doc": "enddoc",
    "stylesheet": "endstylesheet",
    "javascript": "endjavascript",
}
_COMPOSITION = {
    "render": "snippets",
    "include": "snippets",
    "section": "sections",
}

# (theme root, locale path) -> (mtime_ns, parsed locale or None)
_LOCALE_CACHE: dict[tuple[str, str], tuple[int, dict | None]] = {}
# (theme root, settings_schema.json path) -> (mtime_ns, {setting id: line} or None)
_SETTINGS_CACHE: dict[tuple[str, str], tuple[int, dict[str, int] | None]] = {}
_ID_PROP = re.compile(r'"id"\s*:\s*"([^"\\\n]+)"')
# ``settings.x``, ``section.settings.x``, ``block.settings.x`` and their ``['x']`` forms.
_SETTING_USE = re.compile(
    r"""(?<![\w.])(?<!t:)(section\.settings|block\.settings|settings)(?:\.([A-Za-z_]\w*)|\[\s*(['"])([\w-]+)\3\s*\])"""
)


# Names the HTML Standard ("valid custom element name") lists as hyphenated but never custom elements.
_RESERVED_ELEMENTS = frozenset({
    "annotation-xml", "color-profile", "font-face", "font-face-src", "font-face-uri",
    "font-face-format", "font-face-name", "missing-glyph",
})
# Separators are never part of a segment (``[a-z0-9_.]`` has no ``-``), so these stay linear on hostile input.
_CE_NAME = r"[a-z][a-z0-9_.]*(?:-[a-z0-9_.]+)+(?![\w.-])"
_CE_USE = re.compile(rf"<({_CE_NAME})|(?<![\w-])is\s*=\s*([\"'])({_CE_NAME})\2")
_CE_DEFINE = re.compile(r"""customElements\s*\.\s*define\s*\(\s*(['"])([a-z][\w.]*(?:-[\w.]*)+)\1""")
_JAVASCRIPT_OPEN = re.compile(r"\{%-?\s*javascript\s*-?%\}")
_THEME_LIQUID_DIRS = ("layout", "sections", "blocks", "snippets", "templates")
# root -> (signature, {element name: (file, line)})
_CE_CACHE: dict[str, tuple[tuple, dict[str, tuple[Path, int]]]] = {}


def _find_theme_root(path: Path) -> Path | None:
    """Nearest ancestor within three levels that holds ``layout/theme.liquid``."""
    for parent in list(path.parents)[:_THEME_ROOT_LEVELS]:
        if (parent / "layout" / "theme.liquid").is_file():
            return parent
    return None


def _safe_component(name: str) -> bool:
    """True for a bare file-name component: no separators, no ``..``, not empty."""
    return bool(name) and "/" not in name and "\\" not in name and ".." not in name and "\0" not in name


def _safe_asset(name: str) -> bool:
    """True for a relative asset name that cannot leave ``assets/``."""
    return bool(name) and not name.startswith(("/", "\\")) and "\\" not in name and ".." not in name and "\0" not in name


def _inside(root: Path, target: Path) -> bool:
    try:
        Path(os.path.realpath(target)).relative_to(os.path.realpath(root))
    except ValueError:
        return False
    return True


def _strip_json_comments(text: str) -> str:
    """Blank ``//`` and ``/* */`` comments outside strings, keeping newlines so line numbers survive."""
    return _JSON_COMMENT.sub(
        lambda m: m.group(0) if m.group(0).startswith('"') else re.sub(r"[^\n]", " ", m.group(0)), text,
    )


def _read_theme_json(path: Path) -> object | None:
    """Parsed JSON (comments allowed) when the file is small enough and valid, else None."""
    try:
        if path.stat().st_size > _MAX_LOCALE_BYTES:
            return None
        return json.loads(_strip_json_comments(_read_source_text(path)))
    except (OSError, ValueError, RecursionError):
        return None


def _settings_schema(root: Path) -> dict[str, int] | None:
    """Global setting id -> line of its ``"id"`` in ``config/settings_schema.json``; None if absent or hostile."""
    path = root / "config" / "settings_schema.json"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    key = (str(root), str(path))
    cached = _SETTINGS_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    ids: dict[str, int] | None = None
    data = _read_theme_json(path)
    if data is not None:
        found: set[str] = set()
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                sid = node.get("id")
                if isinstance(sid, str) and "type" in node:
                    found.add(sid)
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
        text = _strip_json_comments(_read_source_text(path))
        ids = {}
        for m in _ID_PROP.finditer(text):
            if m.group(1) in found and m.group(1) not in ids:
                ids[m.group(1)] = text.count("\n", 0, m.start()) + 1
        for sid in found:
            ids.setdefault(sid, 1)
    _SETTINGS_CACHE[key] = (mtime, ids)
    return ids


def _default_locale(root: Path, pattern: str = "*.default.json") -> tuple[Path, dict] | None:
    """The parsed ``locales/<pattern>`` file when exactly one exists, else None."""
    candidates = sorted((root / "locales").glob(pattern)) if (root / "locales").is_dir() else []
    if len(candidates) != 1:
        return None
    locale_path = candidates[0]
    try:
        stat = locale_path.stat()
    except OSError:
        return None
    key = (str(root), str(locale_path))
    cached = _LOCALE_CACHE.get(key)
    if cached is not None and cached[0] == stat.st_mtime_ns:
        data = cached[1]
    else:
        data = None
        if stat.st_size <= _MAX_LOCALE_BYTES:
            try:
                text = _read_source_text(locale_path)
                parsed = json.loads(_strip_json_comments(text))
                data = parsed if isinstance(parsed, dict) else None
            except (OSError, ValueError):
                data = None
        _LOCALE_CACHE[key] = (stat.st_mtime_ns, data)
    return (locale_path, data) if data is not None else None


def _has_key(locale: dict, key: str) -> bool:
    node: object = locale
    for part in key.split("."):
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, (str, dict))


_METAFIELD_OWNERS = frozenset({
    "product", "variant", "collection", "shop", "article", "page", "blog", "order", "customer", "company",
    "location", "market", "company_location",
})
# ``<var>.metafields.<ns>.<key>`` and ``[<var>.]metafields['<ns>']['<key>']``.
_METAFIELD_USE = re.compile(
    r"""\b(\w+)\.metafields\.(\w+)\.(\w+)|(?:\b(\w+)\.)?metafields\[['"]([\w-]+)['"]\]\[['"]([\w-]+)['"]\]"""
)
# (theme root, metafields.json path) -> (mtime_ns, {(owner, ns, key): {name, type, line}} or None)
_METAFIELD_CACHE: dict[tuple[str, str], tuple[int, dict | None]] = {}
_KEY_PROP = re.compile(r'"key"\s*:\s*"((?:[^"\\\n]|\\.)*)"')


def _metafield_defs(root: Path) -> dict[tuple[str, str, str], dict] | None:
    """Definitions of ``.shopify/metafields.json`` keyed ``(owner, namespace, key)``; None if absent or hostile."""
    path = root / ".shopify" / "metafields.json"
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        return None
    cache_key = (str(root), str(path))
    cached = _METAFIELD_CACHE.get(cache_key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    defs: dict[tuple[str, str, str], dict] | None = None
    data = _read_theme_json(path)
    if isinstance(data, dict):
        try:
            text = _strip_json_comments(_read_source_text(path))
        except OSError:
            text = ""
        lines = [(m.group(1), text.count("\n", 0, m.start()) + 1) for m in _KEY_PROP.finditer(text)]
        defs = {}
        index = 0
        for owner, entries in data.items():
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if not isinstance(entry, dict) or not isinstance(entry.get("key"), str) \
                        or not isinstance(entry.get("namespace"), str):
                    continue
                at = lines[index][1] if index < len(lines) and lines[index][0] == entry["key"] else 1
                index += 1
                kind = entry.get("type")
                defs.setdefault((owner, entry["namespace"], entry["key"]), {
                    "name": str(entry.get("name") or ""),
                    "type": str(kind.get("name")) if isinstance(kind, dict) and kind.get("name") else "",
                    "line": at,
                })
    _METAFIELD_CACHE[cache_key] = (mtime, defs)
    return defs


def setting_node(root: Path, sid: str, line: int) -> dict:
    """The node of global setting ``sid``; shared by the Liquid and the settings-schema extractors."""
    return {
        "id": _make_id("liquid_setting", str(root), sid), "label": f"settings.{sid}", "file_type": "concept",
        "source_file": str(root / "config" / "settings_schema.json"), "source_location": f"L{line}",
    }


_MAX_SCHEMA_DEPTH = 32


def _schema_setting_ids(data: dict, body: str, first_line: int) -> tuple[dict[str, int], list[dict[str, int]]]:
    """Setting ids of a ``{% schema %}``: ``settings[]`` and, per ``blocks[]`` entry, its ``settings[]``; id -> line.

    Walks ``data`` in source order alongside the ``"id"`` occurrences of ``body`` so each id gets its own line.
    """
    matches: list[tuple[str, int]] = []
    pos = line = 0
    for m in _ID_PROP.finditer(body):
        line += body.count("\n", pos, m.start())
        pos = m.start()
        matches.append((m.group(1), first_line + line))
    first_of: dict[str, int] = {}
    for sid, at in matches:
        first_of.setdefault(sid, at)
    own: dict[str, int] = {}
    blocks_raw = data.get("blocks")
    per_block: list[dict[str, int]] = [{} for _ in blocks_raw] if isinstance(blocks_raw, list) else []
    counter = 0

    def walk(node: object, path: tuple, depth: int) -> None:
        nonlocal counter
        if depth > _MAX_SCHEMA_DEPTH:
            return
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "id" and isinstance(value, str):
                    index, counter = counter, counter + 1
                    at = matches[index][1] if index < len(matches) and matches[index][0] == value else first_of.get(value, first_line)
                    if "type" not in node:
                        continue
                    if len(path) == 2 and path[0] == "settings":
                        own.setdefault(value, at)
                    elif len(path) == 4 and path[0] == "blocks" and path[2] == "settings" and path[1] < len(per_block):
                        per_block[path[1]].setdefault(value, at)
                else:
                    walk(value, path + (key,), depth + 1)
        elif isinstance(node, list):
            for i, value in enumerate(node):
                walk(value, path + (i,), depth + 1)

    walk(data, (), 0)
    return own, per_block


# theme root -> (signature of sections/blocks/snippets, _ThemeIndex)
_THEME_INDEX: dict[str, tuple[tuple, "_ThemeIndex"]] = {}
_INDEXED_AREAS = ("sections", "blocks", "snippets")
_MAX_INDEXED_FILES = 4000


class _FileInfo:
    """What the settings resolver needs from one theme file: its schema ids and what it places or renders."""

    __slots__ = ("path", "own", "block_ids", "static_blocks")

    def __init__(self, path: Path, own: dict[str, int], block_ids: list[dict[str, int]], static_blocks: set[str]) -> None:
        self.path = path
        self.own = own
        self.block_ids = block_ids
        self.static_blocks = static_blocks


class _ThemeIndex:
    """Settings and call graph of a theme's sections, blocks and snippets, built once per root."""

    def __init__(self) -> None:
        self.files: dict[str, _FileInfo] = {}
        self.callers: dict[str, set[str]] = {}   # "snippets/x.liquid" -> files that render it

    def parents_of_block(self, name: str) -> list[_FileInfo]:
        """Sections that place theme block ``name`` statically."""
        return [i for r, i in self.files.items() if r.startswith("sections/") and name in i.static_blocks]

    def callers_closure(self, rel: str) -> list[str]:
        """Every file that renders ``rel``, directly or through other snippets, in sorted order."""
        seen: set[str] = set()
        todo = [rel]
        while todo:
            for caller in self.callers.get(todo.pop(), ()):
                if caller not in seen:
                    seen.add(caller)
                    todo.append(caller)
        return sorted(seen)


def _theme_index(root: Path) -> _ThemeIndex:
    """Index of ``sections/``, ``blocks/`` and ``snippets/`` Liquid files, cached per root until one changes."""
    files: list[Path] = []
    for area in _INDEXED_AREAS:
        folder = root / area
        if folder.is_dir() and _inside(root, folder):
            files.extend(sorted(folder.glob("*.liquid"))[:_MAX_INDEXED_FILES])
    signature: list[tuple[str, int, int]] = []
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        signature.append((f.name, st.st_mtime_ns, st.st_size))
    cached = _THEME_INDEX.get(str(root))
    if cached is not None and cached[0] == tuple(signature):
        return cached[1]
    index = _ThemeIndex()
    for f in files:
        if not f.is_file():
            continue
        try:
            collector = _Collector(f, root)
            collector.want_html = False
            _scan(_read_source_text(f), collector)
        except (OSError, RecursionError):
            continue
        rel = f.relative_to(root).as_posix()
        index.files[rel] = _FileInfo(f, collector.own_settings, collector.block_settings, collector.static_blocks)
        for edge in collector.edges:
            target = edge.get("target_file")
            if target and edge["relation"] == "imports" and edge["confidence"] == "EXTRACTED" \
                    and Path(target).parent.name == "snippets":
                index.callers.setdefault(f"snippets/{Path(target).name}", set()).add(rel)
    _THEME_INDEX[str(root)] = (tuple(signature), index)
    return index


def _snippet_hits(index: _ThemeIndex, callers: list[str], scope: str, sid: str) -> list[tuple[Path, tuple[str, ...], int]]:
    """Schema declarations of ``sid`` reachable from the files that render a snippet (directly or transitively)."""
    hits: list[tuple[Path, tuple[str, ...], int]] = []
    sections: dict[str, _FileInfo] = {}
    for rel in callers:
        info = index.files.get(rel)
        if info is None:
            continue
        if rel.startswith("sections/"):
            sections[rel] = info
        elif rel.startswith("blocks/"):
            if scope == "block":
                if sid in info.own:
                    hits.append((info.path, ("block",), info.own[sid]))
            else:
                for parent in index.parents_of_block(Path(rel).stem):
                    sections.setdefault(parent.path.relative_to(parent.path.parents[1]).as_posix(), parent)
    for info in sections.values():
        if scope == "section":
            if sid in info.own:
                hits.append((info.path, ("section",), info.own[sid]))
        else:
            hits.extend((info.path, ("block", str(i)), d[sid]) for i, d in enumerate(info.block_ids) if sid in d)
    return hits


class _Collector:
    """Accumulates nodes and de-duplicated edges for one file, in source order."""

    def __init__(self, path: Path, root: Path) -> None:
        self.path = path
        self.root = root
        self.file_id = _make_id(str(path))
        self.nodes: list[dict] = [{
            "id": self.file_id, "label": path.name, "file_type": "code",
            "source_file": str(path), "source_location": None,
        }]
        self.edges: list[dict] = []
        self._node_ids = {self.file_id}
        self._probe: dict[Path, str] = {}
        self._seen: set[tuple[str, str, int]] = set()
        self._locale: tuple[Path, dict] | None | _Unset = _UNSET
        self._schema_locale: tuple[Path, dict] | None | _Unset = _UNSET
        self._settings: dict[str, int] | None | _Unset = _UNSET
        self._metafields: dict[tuple[str, str, str], dict] | None | _Unset = _UNSET
        self.pending: list[tuple[str, str, int]] = []   # (section|block, setting id, line) resolved after the schema
        self.own_settings: dict[str, int] = {}          # schema ``settings[]`` ids -> line
        self.block_settings: list[dict[str, int]] = []  # schema ``blocks[].settings`` ids -> line, one dict per block entry
        self.static_blocks: set[str] = set()            # theme block names placed by ``content_for 'block'`` or ``blocks[]``
        self.blocks_line: int | None = None   # first static ``content_for 'blocks'``
        self.accepts_theme = False            # schema ``blocks`` lists ``@theme``
        self._defines: dict[str, tuple[Path, int]] | None = None
        self.want_html = True                # the settings index scans many files and has no use for HTML uses

    def inferred_theme_blocks(self) -> None:
        """INFERRED ``imports`` to every public ``blocks/*.liquid`` when ``content_for 'blocks'``
        meets a schema that accepts ``@theme``. Blocks already linked get nothing extra."""
        if self.blocks_line is None or not self.accepts_theme:
            return
        folder = self.root / "blocks"
        if not folder.is_dir() or not _inside(self.root, folder):
            return
        linked = {e["target_file"] for e in self.edges if e.get("target_file")}
        for block in sorted(folder.glob("*.liquid")):
            if block.name.startswith("_") or str(block) in linked or block == self.path or not block.is_file():
                continue
            target_id = _make_id(str(block))
            if not self._first(target_id, "imports", self.blocks_line):
                continue
            self.edges.append({
                "source": self.file_id, "target": target_id, "target_file": str(block),
                "relation": "imports", "confidence": "INFERRED", "confidence_score": 0.55,
                "source_file": str(self.path), "source_location": f"L{self.blocks_line}", "weight": 1.0,
            })

    def add_selectors(self, nodes_edges: tuple[list[dict], list[dict]]) -> None:
        """Merge CSS selector nodes and their ``contains`` edges from this file."""
        nodes, edges = nodes_edges
        for node in nodes:
            self._declare(node)
        self.edges.extend(edges)

    def stylesheet(self, body: str, first_line: int) -> None:
        """Selectors of a ``{% stylesheet %}`` body, with absolute lines (``first_line`` is where the body starts)."""
        from graphify.extractors.css import css_selectors, selector_nodes_edges

        self.add_selectors(selector_nodes_edges(self.path, self.file_id, css_selectors(body), first_line - 1))

    def html(self, text: str, line: int) -> None:
        """Custom-element uses (``<x-y`` and ``is="x-y"``) in an HTML segment of rendered output starting at ``line``."""
        if not self.want_html or ("-" not in text):
            return
        last_offset, current = 0, line
        for m in _CE_USE.finditer(text):
            current += text.count("\n", last_offset, m.start())
            last_offset = m.start()
            self.custom_element_edge(m.group(1) or m.group(3), current)

    def custom_element_edge(self, name: str, line: int) -> None:
        """``references`` edge to the ``<name>`` node placed at its ``customElements.define``, else an unresolved one.

        The node also hangs from the JS file by ``contains``, so ``affected`` on that file reaches its users.
        """
        if name in _RESERVED_ELEMENTS:
            return
        if self._defines is None:
            self._defines = _custom_element_defines(self.root)   # once per file: the signature check stats the theme
        hit = self._defines.get(name)
        if hit is None:
            self._unresolved("references", "custom_element", name, f"<{name}>", line)
            return
        js_path, js_line = hit
        node_id = _make_id("liquid_ce", str(self.root), name)
        if not self._first(node_id, "references", line):
            return
        if node_id not in self._node_ids:
            js_id = _make_id(str(js_path))
            if js_path != self.path:
                self._declare({
                    "id": js_id, "label": js_path.name, "file_type": "code",
                    "source_file": str(js_path), "source_location": None,
                })
            self._declare({
                "id": node_id, "label": f"<{name}>", "file_type": "code",
                "source_file": str(js_path), "source_location": f"L{js_line}",
            })
            self.edges.append({
                "source": js_id, "target": node_id, "relation": "contains", "confidence": "EXTRACTED",
                "confidence_score": 1.0, "source_file": str(js_path), "source_location": f"L{js_line}", "weight": 1.0,
            })
        self.edges.append({
            "source": self.file_id, "target": node_id, "relation": "references",
            "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def classes(self, view: str) -> None:
        """INFERRED ``references`` from each ``class`` token to every theme selector of that name.

        ``view`` is the file with Liquid and inactive regions blanked to spaces (newlines kept). WHY: a ``"`` inside
        ``{% if x != "" %}`` would end the attribute value early; blanked, the value runs to its real closing quote.
        A token with no selector in the theme is not a component use and gets no edge.
        """
        if "class" not in view:
            return
        index = _css_class_index(self.root)
        if not index:
            return
        last_offset, current = 0, 1
        for am in _CLASS_ATTR.finditer(view):
            group = 1 if am.group(1) is not None else 2
            base = am.start(group)
            for tm in _CLASS_TOKEN.finditer(am.group(group)):
                token = tm.group(0)
                targets = index.get(token) if _CLASS_NAME.fullmatch(token) else None
                if not targets:
                    continue
                offset = base + tm.start()
                current += view.count("\n", last_offset, offset)
                last_offset = offset
                for node_id, selector_file, selector_line in targets:
                    if not self._first(node_id, "references", current):
                        continue
                    self._declare({
                        "id": node_id, "label": "." + token, "file_type": "code",
                        "source_file": str(selector_file), "source_location": f"L{selector_line}",
                    })
                    self.edges.append({
                        "source": self.file_id, "target": node_id, "relation": "references",
                        "confidence": "INFERRED", "confidence_score": 0.55,
                        "source_file": str(self.path), "source_location": f"L{current}", "weight": 1.0,
                    })

    def _declare(self, node: dict) -> None:
        if node["id"] not in self._node_ids:
            self._node_ids.add(node["id"])
            self.nodes.append(node)

    def file_edge(self, relation: str, kind: str, name: str, target: Path, line: int) -> None:
        """Edge to an existing file inside the theme, else an unresolved reference.

        Non-Liquid targets get a declared file node so the edge never dangles.
        """
        state = self._probe.get(target)
        if state is None:
            state = "out" if not _inside(self.root, target) else ("file" if target.is_file() else "missing")
            self._probe[target] = state
        if state == "out":
            return
        if state == "missing":
            self._unresolved(relation, kind, name, target.relative_to(self.root).as_posix(), line)
            return
        target_id = _make_id(str(target))
        if not self._first(target_id, relation, line):
            return
        if target.suffix != ".liquid":
            self._declare({
                "id": target_id, "label": target.name, "file_type": "code",
                "source_file": str(target), "source_location": None,
            })
        self.edges.append({
            "source": self.file_id, "target": target_id, "target_file": str(target),
            "relation": relation, "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def metafield_edge(self, var: str, ns: str, key: str, line: int) -> None:
        """Usage node ``metafields.<ns>.<key>`` linked to its definition(s) in ``.shopify/metafields.json``.

        EXTRACTED when ``var`` names the owner type that defines it; INFERRED to every definition of ``(ns, key)``
        otherwise; no definition leaves an unresolved node carrying a ``warning``.
        """
        if self._metafields is _UNSET:
            self._metafields = _metafield_defs(self.root)
        defs = self._metafields
        label = f"metafields.{ns}.{key}"
        if not isinstance(defs, dict):
            self._unresolved("references", "metafield", f"{ns}.{key}", label, line, "no .shopify/metafields.json")
            return
        owner = var if var in _METAFIELD_OWNERS else None
        exact = (owner, ns, key) if owner is not None and (owner, ns, key) in defs else None
        found = [exact] if exact else sorted(k for k in defs if k[1] == ns and k[2] == key)
        if not found:
            self._unresolved("references", "metafield", f"{ns}.{key}", label, line, "not defined in .shopify/metafields.json")
            return
        use_id = _make_id("liquid_metafield", str(self.root), ns, key)
        if self._first(use_id, "references", line):
            self._declare({
                "id": use_id, "label": label, "file_type": "concept",
                "source_file": str(self.path), "source_location": f"L{line}",
            })
            self.edges.append({
                "source": self.file_id, "target": use_id, "relation": "references",
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
            })
        for definition in found:
            info = defs[definition]
            def_id = _make_id("liquid_metafield_def", str(self.root), *definition)
            self._declare({
                "id": def_id, "label": f"{label}@{definition[0]}", "file_type": "concept",
                "source_file": str(self.root / ".shopify" / "metafields.json"), "source_location": f"L{info['line']}",
                "owner": definition[0], "metafield_type": info["type"], "name": info["name"],
            })
            if self._first(f"{use_id}>{def_id}", "references", line):
                self.edges.append({
                    "source": use_id, "target": def_id, "relation": "references",
                    "confidence": "EXTRACTED" if exact else "INFERRED", "confidence_score": 1.0 if exact else 0.55,
                    "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
                })

    def _unresolved(self, relation: str, kind: str, name: str, label: str, line: int, warning: str | None = None) -> None:
        """AMBIGUOUS edge to a declared ``unresolved`` node for a missing target."""
        target_id = _make_id("ref", "liquid", kind, name)
        if not self._first(target_id, relation, line):
            return
        node = {
            "id": target_id, "label": label, "file_type": "concept",
            "source_file": str(self.path), "source_location": f"L{line}",
            "unresolved": True, "ref_kind": kind,
        }
        if warning:
            node["warning"] = warning
        self._declare(node)
        self.edges.append({
            "source": self.file_id, "target": target_id, "relation": relation,
            "confidence": "AMBIGUOUS", "confidence_score": 0.2,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def key_edge(self, key: str, line: int) -> None:
        """``references`` edge to a translation key found in the default locale."""
        if key.startswith("shopify."):
            return
        if self._locale is _UNSET:
            self._locale = _default_locale(self.root)
        if self._locale is None or isinstance(self._locale, _Unset):
            return
        locale_path, data = self._locale
        if not _has_key(data, key):
            self._unresolved("references", "t", key, key, line)
            return
        target_id = _make_id("liquid_t", key)
        if not self._first(target_id, "references", line):
            return
        self._declare({
            "id": target_id, "label": key, "file_type": "concept",
            "source_file": str(locale_path), "source_location": None,
        })
        self.edges.append({
            "source": self.file_id, "target": target_id, "relation": "references",
            "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def schema_key_edge(self, key: str, line: int) -> None:
        """``references`` edge to a ``t:`` key found in the default ``*.schema.json`` locale."""
        if self._schema_locale is _UNSET:
            self._schema_locale = _default_locale(self.root, "*.default.schema.json")
        if self._schema_locale is None or isinstance(self._schema_locale, _Unset):
            return
        locale_path, data = self._schema_locale
        if not _has_key(data, key):
            self._unresolved("references", "schema_t", key, f"t:{key}", line)
            return
        target_id = _make_id("liquid_t_schema", key)
        if not self._first(target_id, "references", line):
            return
        self._declare({
            "id": target_id, "label": f"t:{key}", "file_type": "concept",
            "source_file": str(locale_path), "source_location": None,
        })
        self.edges.append({
            "source": self.file_id, "target": target_id, "relation": "references",
            "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def schema_keys(self, data: object, text: str, first_line: int) -> None:
        """Link every ``t:<key>`` string inside a parsed schema to the schema locale.

        ``text`` is the source the object was parsed from; each quoted occurrence
        in it gets its own line so the edge points at the setting that uses it.
        """
        keys: set[str] = set()
        stack = [data]
        while stack:
            node = stack.pop()
            if isinstance(node, dict):
                stack.extend(node.values())
            elif isinstance(node, list):
                stack.extend(node)
            elif isinstance(node, str) and node.startswith("t:") and len(node) > 2:
                keys.add(node[2:])
        for key in sorted(keys):
            needle = json.dumps(f"t:{key}", ensure_ascii=False)
            pos = text.find(needle)
            if pos == -1:
                self.schema_key_edge(key, first_line)
            while pos != -1:
                self.schema_key_edge(key, first_line + text.count("\n", 0, pos))
                pos = text.find(needle, pos + 1)

    def _first(self, target_id: str, relation: str, line: int) -> bool:
        key = (target_id, relation, line)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    # -- statement level -------------------------------------------------

    def setting_edge(self, sid: str, line: int) -> None:
        """``references`` edge to a global setting of ``config/settings_schema.json`` (or an unresolved one)."""
        if self._settings is _UNSET:
            self._settings = _settings_schema(self.root)
        ids = self._settings
        label = f"settings.{sid}"
        if not isinstance(ids, dict) or sid not in ids:
            self._unresolved("references", "setting", label, label, line)
            return
        node = setting_node(self.root, sid, ids[sid])
        if not self._first(node["id"], "references", line):
            return
        self._declare(node)
        self.edges.append({
            "source": self.file_id, "target": node["id"], "relation": "references",
            "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def _schema_setting_edge(
        self, scope: str, file: Path, parts: tuple[str, ...], sid: str, at: int, line: int, inferred: bool,
    ) -> None:
        """Edge to the ``<scope>.settings.<sid>`` declared at line ``at`` of the ``{% schema %}`` of ``file``."""
        label = f"{scope}.settings.{sid}"
        target_id = _make_id("liquid_schema_setting", str(file), *parts, sid)
        if not self._first(target_id, "references", line):
            return
        self._declare({
            "id": target_id, "label": label, "file_type": "concept",
            "source_file": str(file), "source_location": f"L{at}",
        })
        self.edges.append({
            "source": self.file_id, "target": target_id, "relation": "references",
            "confidence": "INFERRED" if inferred else "EXTRACTED", "confidence_score": 0.55 if inferred else 1.0,
            "source_file": str(self.path), "source_location": f"L{line}", "weight": 1.0,
        })

    def resolve_settings(self) -> None:
        """Resolve the pending ``section.settings.x`` / ``block.settings.x`` once the file's schema is known.

        A section reads its own ``settings`` and the ``blocks[].settings`` of its blocks; a theme block reads its own
        ``settings`` and the ``settings`` of the sections that place it statically. Anything else, or an id nobody
        defines, is an AMBIGUOUS unresolved reference.
        """
        if not self.pending:
            return
        try:
            area = self.path.relative_to(self.root).parts[0]
        except (ValueError, IndexError):
            area = ""
        index: _ThemeIndex | None = None
        parents: list[_FileInfo] = []
        callers: list[str] = []
        for scope, sid, line in self.pending:
            if index is None and (area == "snippets" or (scope == "section" and area == "blocks")):
                index = _theme_index(self.root)
                parents = index.parents_of_block(self.path.stem)
                callers = index.callers_closure(f"snippets/{self.path.stem}.liquid") if area == "snippets" else []
            label = f"{scope}.settings.{sid}"
            if scope == "section" and area == "sections":
                hits = [(self.path, ("section",), self.own_settings[sid])] if sid in self.own_settings else []
                inferred = False
            elif scope == "block" and area == "blocks":
                hits = [(self.path, ("block",), self.own_settings[sid])] if sid in self.own_settings else []
                inferred = False
            elif scope == "block" and area == "sections":
                hits = [(self.path, ("block", str(i)), d[sid]) for i, d in enumerate(self.block_settings) if sid in d]
                inferred = len(hits) > 1
            elif scope == "section" and area == "blocks":
                hits = [(s.path, ("section",), s.own[sid]) for s in parents if sid in s.own]
                inferred = len(parents) > 1 or len(hits) > 1
            elif area == "snippets" and index is not None:
                # A snippet has no schema: the sections that render it (transitively) are the only candidates.
                hits = _snippet_hits(index, callers, scope, sid)
                inferred = True
            else:
                hits, inferred = [], False
            if not hits:
                self._unresolved("references", "setting", label, label, line)
                continue
            for file, parts, at in hits:
                self._schema_setting_edge(scope, file, parts, sid, at, line, inferred)

    def statement(self, text: str, line: int) -> None:
        """Handle one tag body or one line of a ``{% liquid %}`` block."""
        self.html(text, line)   # markup echoed from a tag or an output, e.g. ``echo '<x-y>'``
        if "metafields" in text:
            for m in _METAFIELD_USE.finditer(text):
                at = line + text.count("\n", 0, m.start())
                if m.group(2) is not None:
                    self.metafield_edge(m.group(1), m.group(2), m.group(3), at)
                else:
                    self.metafield_edge(m.group(4) or "", m.group(5), m.group(6), at)
        if "settings" in text:
            for m in _SETTING_USE.finditer(text):
                scope, sid = m.group(1), m.group(2) or m.group(4)
                at = line + text.count("\n", 0, m.start())   # a tag body can span lines
                if scope == "settings":
                    self.setting_edge(sid, at)
                else:
                    self.pending.append((scope.split(".", 1)[0], sid, at))
        for m in _FILTER.finditer(text):
            name, kind = m.group(2), m.group(3)
            if kind in _ASSET_FILTERS:
                self._asset(name, line)
            else:
                self.key_edge(name, line)
        head = _STMT_NAME.match(text)
        if head is None:
            return
        tag = head.group(1)
        rest = text[head.end():]
        if tag in _COMPOSITION:
            arg = _NAME_ARG.match(rest)
            if arg and _safe_component(arg.group(2)):
                folder = _COMPOSITION[tag]
                kind = "snippet" if folder == "snippets" else "section"
                self.file_edge("imports", kind, arg.group(2), self.root / folder / f"{arg.group(2)}.liquid", line)
        elif tag == "sections":
            arg = _NAME_ARG.match(rest)
            if arg and _safe_component(arg.group(2)):
                name = arg.group(2)
                self.file_edge("imports", "section_group", name, self.root / "sections" / f"{name}.json", line)
        elif tag == "content_for":
            arg = _NAME_ARG.match(rest)
            if arg and arg.group(2) == "blocks" and self.blocks_line is None:
                self.blocks_line = line
            if arg and arg.group(2) == "block":
                m = _BLOCK_TYPE.search(rest[arg.end():])
                if m and _safe_component(m.group(2)):
                    block = m.group(2)
                    self.static_blocks.add(block)
                    self.file_edge("imports", "block", block, self.root / "blocks" / f"{block}.liquid", line)

    def _asset(self, name: str, line: int) -> None:
        # Old font stacks write 'x.eot?#iefix' | asset_url: the file is the part before ? or #.
        name = _ASSET_SUFFIX.split(name, maxsplit=1)[0]
        if not _safe_asset(name):
            return
        direct = self.root / "assets" / name
        if direct.is_file():
            self.file_edge("references", "asset", name, direct, line)
        elif (self.root / "assets" / f"{name}.liquid").is_file():
            self.file_edge("references", "asset", name, self.root / "assets" / f"{name}.liquid", line)
        else:
            self.file_edge("references", "asset", name, direct, line)

    def _availability(self, data: dict, body: str, line: int) -> None:
        """``references`` for ``enabled_on`` / ``disabled_on`` templates and section groups."""
        for key in ("enabled_on", "disabled_on"):
            spec = data.get(key)
            if not isinstance(spec, dict):
                continue
            key_at = max(body.find(f'"{key}"'), 0)
            for field, kind in (("templates", "template"), ("groups", "section_group")):
                names = spec.get(field)
                if not isinstance(names, list):
                    continue
                for name in names:
                    if not isinstance(name, str) or name == "*" or not name or name.startswith("/") \
                            or "\\" in name or ".." in name or "\0" in name:
                        continue
                    if kind == "template":
                        candidates = [self.root / "templates" / f"{name}.json", self.root / "templates" / f"{name}.liquid"]
                    else:
                        candidates = [self.root / "sections" / f"{name}-group.json", self.root / "sections" / f"{name}.json"]
                    target = next((c for c in candidates if c.is_file()), candidates[0])
                    m = re.compile(r'"' + re.escape(name) + '"').search(body, key_at)
                    entry_line = line + body.count("\n", 0, m.start()) if m else line
                    self.file_edge("references", kind, name, target, entry_line)

    def _preset_blocks(self, data: dict, body: str, line: int) -> None:
        """``imports`` for each ``presets[].blocks`` type (nested too) that has a ``blocks/`` file."""
        presets = data.get("presets")
        if not isinstance(presets, list):
            return
        start = max(body.find('"presets"'), 0)
        seen: set[str] = set()
        stack: list[tuple[object, int]] = [(p, 0) for p in reversed(presets)]
        while stack:
            node, depth = stack.pop()
            if depth > 32 or not isinstance(node, dict):
                continue
            children = node.get("blocks")
            if isinstance(children, dict):
                children = list(children.values())
            if isinstance(children, list):
                stack.extend((c, depth + 1) for c in reversed(children))
            if depth == 0:
                continue
            block_type = node.get("type")
            if not isinstance(block_type, str) or block_type.startswith(("@", "shopify://")) or block_type in seen:
                continue
            seen.add(block_type)
            target = self.root / "blocks" / f"{block_type}.liquid"
            if not _safe_component(block_type) or not target.is_file():
                continue
            m = re.compile(r'"type"\s*:\s*"' + re.escape(block_type) + '"').search(body, start)
            entry_line = line + body.count("\n", 0, m.start()) if m else line
            self.file_edge("imports", "block", block_type, target, entry_line)

    def schema(self, body: str, line: int) -> None:
        """``blocks[]`` entries of a section/block schema that name a theme block file."""
        try:
            data = json.loads(body)
        except (ValueError, RecursionError):
            return
        self.schema_keys(data, body, line)
        if not isinstance(data, dict):
            return
        self.own_settings, self.block_settings = _schema_setting_ids(data, body, line)
        self._preset_blocks(data, body, line)
        self._availability(data, body, line)
        blocks = data.get("blocks")
        if not isinstance(blocks, list):
            return
        if any(isinstance(b, dict) and b.get("type") == "@theme" for b in blocks):
            self.accepts_theme = True
        search_from = body.find('"blocks"')
        for entry in blocks:
            if not isinstance(entry, dict):
                continue
            block_type = entry.get("type")
            if not isinstance(block_type, str) or "name" in entry or block_type.startswith("@"):
                continue
            if not _safe_component(block_type):
                continue
            self.static_blocks.add(block_type)
            entry_line = line
            if search_from >= 0:
                m = re.compile(r'"type"\s*:\s*"' + re.escape(block_type) + '"').search(body, search_from)
                if m:
                    entry_line = line + body.count("\n", 0, m.start())
            self.file_edge("imports", "block", block_type, self.root / "blocks" / f"{block_type}.liquid", entry_line)


def _theme_sources(root: Path, asset_patterns: tuple[str, ...], liquid: bool) -> list[Path]:
    """Sorted theme files: ``assets/`` matches of ``asset_patterns`` plus, when ``liquid``, the Liquid directories."""
    files: list[Path] = []
    assets = root / "assets"
    if assets.is_dir() and _inside(root, assets):
        for pattern in asset_patterns:
            files.extend(sorted(assets.glob(pattern)))
    if liquid:
        for area in _THEME_LIQUID_DIRS:
            folder = root / area
            if folder.is_dir() and _inside(root, folder):
                files.extend(sorted(folder.glob("*.liquid"))[:_MAX_INDEXED_FILES])
    return [f for f in files if f.is_file()]


def _signature(files: list[Path]) -> tuple[tuple[str, int, int], ...]:
    """``(path, mtime_ns, size)`` of every file: the change test for a per-root index, blind to no add, remove or swap."""
    out: list[tuple[str, int, int]] = []
    for f in files:
        try:
            st = f.stat()
        except OSError:
            continue
        out.append((str(f), st.st_mtime_ns, st.st_size))
    return tuple(sorted(out))


def _line_numbers(text: str, offsets: list[int], first_line: int = 1) -> list[int]:
    """Line of each ascending offset in ``text``, the first line being ``first_line``."""
    lines: list[int] = []
    line, last = first_line, 0
    for offset in offsets:
        line += text.count("\n", last, offset)
        last = offset
        lines.append(line)
    return lines


_JS_NOISE = re.compile(r"""//[^\n]*|/\*.*?\*/|"(?:\\.|[^"\\\n])*"|'(?:\\.|[^'\\\n])*'|`(?:\\.|[^`\\])*`""", re.S)


def _blank_js_comments(text: str) -> str:
    """Blank ``//`` and ``/* */`` comments, keeping offsets and newlines; strings and template literals are untouched."""
    def repl(m: re.Match) -> str:
        chunk = m.group(0)
        return chunk if chunk[0] in "\"'`" else re.sub(r"[^\n]", " ", chunk)

    return _JS_NOISE.sub(repl, text)


def _blank_spans(text: str, spans: list[tuple[int, int]]) -> str:
    """``text`` with JS comments blanked inside each ``(begin, stop)`` span only."""
    out, pos = [], 0
    for begin, stop in spans:
        out.append(text[pos:begin])
        out.append(_blank_js_comments(text[begin:stop]))
        pos = stop
    out.append(text[pos:])
    return "".join(out)


def _custom_element_defines(root: Path) -> dict[str, tuple[Path, int]]:
    """``{name: (file, line)}`` of every ``customElements.define('x-y', …)`` in the theme's JS.

    Looks in ``assets/*.js``, ``assets/*.js.liquid`` and ``{% javascript %}`` bodies; the first one in sorted
    order wins. Cached per root until a scanned file is added or touched.
    """
    files = _theme_sources(root, ("*.js", "*.js.liquid"), True)
    signature = _signature(files)
    cached = _CE_CACHE.get(str(root))
    if cached is not None and cached[0] == signature:
        return cached[1]
    found: dict[str, tuple[Path, int]] = {}
    for f in files:
        try:
            text = _read_source_text(f)
        except OSError:
            continue
        if "customElements" not in text:
            continue
        if f.suffix == ".liquid" and f.parent.name != "assets":
            spans = []
            for opener in _JAVASCRIPT_OPEN.finditer(text):
                end = _find_end_tag(text, opener.end(), "endjavascript")
                spans.append((opener.end(), end[0] if end else len(text)))
            text = _blank_spans(text, spans)
        else:
            text = _blank_js_comments(text)
            spans = [(0, len(text))]
        for begin, stop in spans:
            matches = list(_CE_DEFINE.finditer(text, begin, stop))
            for m, line in zip(matches, _line_numbers(text, [m.start() for m in matches])):
                found.setdefault(m.group(2), (f, line))
    _CE_CACHE[str(root)] = (signature, found)
    return found


_STYLESHEET_OPEN = re.compile(r"\{%-?\s*stylesheet\s*-?%\}")
# ``class="…"`` / ``class='…'``; a ``-`` before the name excludes ``data-class``.
_CLASS_ATTR = re.compile(r"""(?<![\w-])class\s*=\s*(?:"([^"]*)"|'([^']*)')""")
_CLASS_TOKEN = re.compile(r"\S+")
_CLASS_NAME = re.compile(r"[A-Za-z_-][\w:/.%-]*")
# root -> (signature, {class name: [(selector node id, file, line)]})
_CSS_CACHE: dict[str, tuple[tuple, dict[str, list[tuple[str, Path, int]]]]] = {}


def _css_class_index(root: Path) -> dict[str, list[tuple[str, Path, int]]]:
    """``{class name: [(selector node id, file, line)]}`` for every ``.name`` selector the theme defines.

    Sources: ``assets/*.css``, ``assets/*.css.liquid`` (Liquid stripped) and ``{% stylesheet %}`` bodies. Ids come
    from ``css_selector_id``, so they equal the nodes the CSS extraction creates. Cached like the defines index.
    """
    from graphify.extractors.css import css_selector_id, css_selectors

    files = _theme_sources(root, ("*.css", "*.css.liquid"), True)
    signature = _signature(files)
    cached = _CSS_CACHE.get(str(root))
    if cached is not None and cached[0] == signature:
        return cached[1]
    index: dict[str, list[tuple[str, Path, int]]] = {}

    def add(path: Path, selectors: list[tuple[str, int]], line_offset: int = 0) -> None:
        first: dict[str, int] = {}
        for selector, line in selectors:
            if selector.startswith("."):
                first.setdefault(selector[1:], line + line_offset)
        for name, line in first.items():
            index.setdefault(name, []).append((css_selector_id(str(path), "." + name), path, line))

    for f in files:
        try:
            text = _read_source_text(f)
        except OSError:
            continue
        if f.parent.name == "assets":
            add(f, css_selectors(_strip_liquid(text) if f.name.endswith(".liquid") else text))
            continue
        if "stylesheet" not in text:
            continue
        for opener in _STYLESHEET_OPEN.finditer(text):
            end = _find_end_tag(text, opener.end(), "endstylesheet")
            body = text[opener.end():end[0] if end else len(text)]
            add(f, css_selectors(body), text.count("\n", 0, opener.end()))
    _CSS_CACHE[str(root)] = (signature, index)
    return index


class _Unset:
    """Sentinel: the locale has not been looked up yet."""


_UNSET = _Unset()


def _scan(src: str, out: _Collector) -> None:
    """Walk ``{% %}`` / ``{{ }}`` tokens in order, honouring masked regions."""
    line_starts = [0]
    pos = src.find("\n")
    while pos != -1:
        line_starts.append(pos + 1)
        pos = src.find("\n", pos + 1)

    def line_of(offset: int) -> int:
        return bisect.bisect_right(line_starts, offset)

    i = 0
    n = len(src)
    tag_close = 0   # cached position of the next "%}" at or after i (-2 = none left)
    out_close = 0
    comment_depth = 0
    skip_until: str | None = None
    seg = 0   # start of the HTML text not yet handed to ``out.html``
    next_t = next_o = -2  # cached next opener offsets (-1 = none left)
    while i < n:
        if next_t != -1 and next_t < i:
            next_t = src.find("{%", i)
        if next_o != -1 and next_o < i:
            next_o = src.find("{{", i)
        t, o = next_t, next_o
        if t == -1 and o == -1:
            break
        is_tag = t != -1 and (o == -1 or t < o)
        start = t if is_tag else o
        if is_tag:
            if tag_close != -2 and tag_close < start + 2:
                tag_close = src.find("%}", start + 2)
                if tag_close == -1:
                    tag_close = -2
            close = tag_close
        else:
            if out_close != -2 and out_close < start + 2:
                out_close = src.find("}}", start + 2)
                if out_close == -1:
                    out_close = -2
            close = out_close
        if close == -2:
            # No closer left for this opener kind: it is plain text.
            i = start + 2
            if is_tag and o == -1:
                break
            continue
        body_start = start + 2
        body_end = close
        if body_start < body_end and src[body_start] == "-":
            body_start += 1
        if body_end > body_start and src[body_end - 1] == "-":
            body_end -= 1
        body = src[body_start:body_end]
        if start > seg and comment_depth == 0 and skip_until is None:
            out.html(src[seg:start], line_of(seg))
        i = seg = close + 2
        if not is_tag:
            if comment_depth == 0 and skip_until is None:
                out.statement(body, line_of(start))
            continue
        head = _STMT_NAME.match(body)
        name = head.group(1) if head else ""
        if skip_until is not None:
            if name == skip_until:
                skip_until = None
            continue
        if comment_depth:
            if name == "comment":
                comment_depth += 1
            elif name == "endcomment":
                comment_depth -= 1
            continue
        if name == "comment":
            comment_depth = 1
        elif name == "stylesheet" and (end := _find_end_tag(src, i, "endstylesheet")) is not None:
            out.stylesheet(src[i:end[0]], line_of(i))
            i = seg = end[1]
        elif name in _SKIP_UNTIL:
            skip_until = _SKIP_UNTIL[name]
        elif name == "schema":
            end = _find_end_tag(src, i, "endschema")
            if end is not None:
                out.schema(src[i:end[0]], line_of(i))
                i = seg = end[1]
        elif name == "liquid":
            _liquid_block(body, head.end() if head else 0, line_of(body_start), out)
        elif body.lstrip().startswith("#"):
            continue
        else:
            out.statement(body, line_of(start))
    if seg < n and comment_depth == 0 and skip_until is None:
        out.html(src[seg:], line_of(seg))


_END_TAG = re.compile(r"\{%-?\s*(\w+)")


def _find_end_tag(src: str, start: int, name: str) -> tuple[int, int] | None:
    """Offsets (start of the closing tag, just after it) of the next ``{% name %}``."""
    for m in _END_TAG.finditer(src, start):
        if m.group(1) != name:
            continue
        close = src.find("%}", m.end())
        if close == -1:
            return None
        return m.start(), close + 2
    return None


def _liquid_block(body: str, skip: int, body_line: int, out: _Collector) -> None:
    """Handle the lines of a ``{% liquid %}`` tag as individual statements."""
    first_line = body_line + body.count("\n", 0, skip)
    comment_depth = 0
    for index, raw in enumerate(body[skip:].split("\n")):
        line = first_line + index
        stmt = raw.strip()
        if not stmt or stmt.startswith("#"):
            continue
        head = _STMT_NAME.match(stmt)
        word = head.group(1) if head else ""
        if comment_depth:
            if word == "comment":
                comment_depth += 1
            elif word == "endcomment":
                comment_depth -= 1
            continue
        if word == "comment":
            comment_depth = 1
            continue
        out.statement(stmt, line)


def extract_liquid(path: Path) -> dict:
    """Extract theme-composition edges from a Shopify theme `.liquid` file.

    Returns only the file node when the file is not inside a theme root.
    """
    try:
        src = _read_source_text(path)
    except OSError:
        return {"error": f"cannot read {path}"}
    path = Path(os.path.abspath(path))
    root = _find_theme_root(path)
    out = _Collector(path, root if root is not None else path.parent)
    if root is not None:
        _scan(src, out)
        if not path.name.endswith((".css.liquid", ".js.liquid")):
            out.classes(_strip_liquid(src, drop_schema=True))
        out.inferred_theme_blocks()
        out.resolve_settings()
        if path.name.endswith(".css.liquid"):
            from graphify.extractors.css import css_selectors, selector_nodes_edges

            out.add_selectors(selector_nodes_edges(path, out.file_id, css_selectors(_strip_liquid(src))))
        elif path.name.endswith(".js.liquid"):
            _add_js_symbols(path, src, out)
    return {"nodes": out.nodes, "edges": out.edges}


def _add_js_symbols(path: Path, src: str, out: _Collector) -> None:
    """Run the Liquid-stripped source of a ``.js.liquid`` asset through the JS extractor, in memory.

    Line numbers match the Liquid file; a JS extraction error leaves the Liquid result untouched.
    """
    # Local imports: graphify.extract imports this module at load time.
    from graphify.extract import _JS_CONFIG
    from graphify.extractors.engine import _extract_generic

    result = _extract_generic(path, _JS_CONFIG, source_override=_strip_liquid(src, "0").encode("utf-8"))
    if "error" in result:
        return
    for node in result.get("nodes", []):
        out._declare(node)
    out.edges.extend(result.get("edges", []))


_BLANK_NON_NEWLINE = re.compile(r"[^\n]")


def _strip_liquid(src: str, output_fill: str = "", drop_schema: bool = False) -> str:
    """``src`` with every Liquid tag, output and ``comment``/``doc`` body replaced by spaces, newlines kept.

    Tokenizes like ``_scan`` (nested ``comment``, an opener without closer is text); ``raw`` bodies stay,
    since Liquid emits them verbatim. Line and column of everything that survives are unchanged.
    ``output_fill`` replaces the first character of each ``{{ }}`` (``"0"`` keeps JS expressions parseable);
    ``drop_schema`` blanks ``{% schema %}`` bodies too (JSON, never rendered).
    """
    n = len(src)
    pieces: list[str] = []
    pos = 0          # start of the text not yet emitted
    i = 0
    depth = 0        # open {% comment %} blocks
    next_t = next_o = -2
    tag_close = out_close = 0

    def emit(upto: int, keep: bool) -> None:
        nonlocal pos
        chunk = src[pos:upto]
        pieces.append(chunk if keep else _BLANK_NON_NEWLINE.sub(" ", chunk))
        pos = upto

    while i < n:
        if next_t != -1 and next_t < i:
            next_t = src.find("{%", i)
        if next_o != -1 and next_o < i:
            next_o = src.find("{{", i)
        if next_t == -1 and next_o == -1:
            break
        is_tag = next_t != -1 and (next_o == -1 or next_t < next_o)
        start = next_t if is_tag else next_o
        if is_tag:
            if tag_close != -2 and tag_close < start + 2:
                tag_close = src.find("%}", start + 2)
                if tag_close == -1:
                    tag_close = -2
            close = tag_close
        else:
            if out_close != -2 and out_close < start + 2:
                out_close = src.find("}}", start + 2)
                if out_close == -1:
                    out_close = -2
            close = out_close
        if close == -2:
            i = start + 2
            if is_tag and next_o == -1:
                break
            continue
        end = close + 2
        i = end
        emit(start, depth == 0)
        if not is_tag and output_fill and depth == 0:
            pieces.append(output_fill + _BLANK_NON_NEWLINE.sub(" ", src[start:end])[len(output_fill):])
            pos = end
        else:
            emit(end, False)
        if not is_tag:
            continue
        body_start = start + 3 if src[start + 2:start + 3] == "-" else start + 2
        head = _STMT_NAME.match(src, body_start, close)
        name = head.group(1) if head else ""
        if depth:
            depth += (name == "comment") - (name == "endcomment")
        elif name == "comment":
            depth = 1
        elif name in ("raw", "doc") or (drop_schema and name == "schema"):
            span = _find_end_tag(src, end, "end" + name)
            if span is not None:
                emit(span[0], name == "raw")
                emit(span[1], False)
                i = span[1]
    emit(n, depth == 0)
    return "".join(pieces)
