"""Shopify theme Liquid extractor (regex only, deterministic).

Extracts the references a `.liquid` file of a Shopify theme makes to the rest of
the theme, so `graphify affected` answers "who uses this snippet / section /
block":

* ``render`` / ``include 'x'``          -> ``snippets/x.liquid``      (``imports``)
* ``section 'x'``                       -> ``sections/x.liquid``      (``imports``)
* ``sections 'x'``                      -> ``sections/x.json``        (``imports``)
* ``content_for 'block', type: 'x'``    -> ``blocks/x.liquid``        (``imports``)
* ``{% schema %}`` ``blocks[]`` entries -> ``blocks/<type>.liquid``   (``imports``)
* ``{% schema %}`` ``presets[].blocks`` (nested, list or dict form) -> ``blocks/<type>.liquid``
  when that file exists (``imports``; section-local types get nothing)
* ``'x' | asset_url`` / ``inline_asset_content`` -> ``assets/x[.liquid]`` (``references``)
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
references, dynamic ``content_for 'blocks'`` expansion.
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
_FILTER = re.compile(r"""(['"])([^'"\n]+)\1\s*\|\s*(asset_url|inline_asset_content|t|translate)(?![\w])""")
_ASSET_FILTERS = frozenset({"asset_url", "inline_asset_content"})
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
    """Drop ``//`` and ``/* */`` comments outside strings (Shopify locale files carry them)."""
    return _JSON_COMMENT.sub(lambda m: m.group(0) if m.group(0).startswith('"') else " ", text)


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

    def _unresolved(self, relation: str, kind: str, name: str, label: str, line: int) -> None:
        """AMBIGUOUS edge to a declared ``unresolved`` node for a missing target."""
        target_id = _make_id("ref", "liquid", kind, name)
        if not self._first(target_id, relation, line):
            return
        self._declare({
            "id": target_id, "label": label, "file_type": "concept",
            "source_file": str(self.path), "source_location": f"L{line}",
            "unresolved": True, "ref_kind": kind,
        })
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

    def statement(self, text: str, line: int) -> None:
        """Handle one tag body or one line of a ``{% liquid %}`` block."""
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
            if arg and arg.group(2) == "block":
                m = _BLOCK_TYPE.search(rest[arg.end():])
                if m and _safe_component(m.group(2)):
                    block = m.group(2)
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
        except ValueError:
            return
        self.schema_keys(data, body, line)
        if not isinstance(data, dict):
            return
        self._preset_blocks(data, body, line)
        blocks = data.get("blocks")
        if not isinstance(blocks, list):
            return
        search_from = body.find('"blocks"')
        for entry in blocks:
            if not isinstance(entry, dict):
                continue
            block_type = entry.get("type")
            if not isinstance(block_type, str) or "name" in entry or block_type.startswith("@"):
                continue
            if not _safe_component(block_type):
                continue
            entry_line = line
            if search_from >= 0:
                m = re.compile(r'"type"\s*:\s*"' + re.escape(block_type) + '"').search(body, search_from)
                if m:
                    entry_line = line + body.count("\n", 0, m.start())
            self.file_edge("imports", "block", block_type, self.root / "blocks" / f"{block_type}.liquid", entry_line)


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
        i = close + 2
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
        elif name in _SKIP_UNTIL:
            skip_until = _SKIP_UNTIL[name]
        elif name == "schema":
            end = _find_end_tag(src, i, "endschema")
            if end is not None:
                out.schema(src[i:end[0]], line_of(i))
                i = end[1]
        elif name == "liquid":
            _liquid_block(body, head.end() if head else 0, line_of(body_start), out)
        elif body.lstrip().startswith("#"):
            continue
        else:
            out.statement(body, line_of(start))


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
    return {"nodes": out.nodes, "edges": out.edges}
