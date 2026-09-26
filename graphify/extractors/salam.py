"""Salam (.salam) extractor: token scanner, no third-party parser needed.

Salam blocks open with ``:`` and close with ``end`` (Persian ``پایان``), and
every keyword has an English and a Persian spelling. The scanner tokenizes the
source, tracks the block stack, and emits packages, imports, functions, structs
(with methods), enums, interfaces, ``impl`` blocks, type aliases, constants,
extern C functions, layout blocks and components, plus ``calls`` and
``references`` edges. ``@en`` / ``@fa`` annotations are kept as node aliases so
a Persian call site can resolve to the English definition and back.
"""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id

_ID, _NUM, _STR, _OP, _META, _NL = "id", "num", "str", "op", "meta", "nl"

_ZWNJ = "‌"


def _fold(text: str) -> str:
    return text.replace("ي", "ی").replace("ك", "ک")


def _norm(text: str) -> str:
    """Canonical spelling of an identifier: Arabic yeh/kaf folded, ZWNJ -> space."""
    return " ".join(_fold(text).replace(_ZWNJ, " ").split())


def _kw_key(text: str) -> str:
    return _fold(text).replace(_ZWNJ, "")


_KEYWORD_SPELLINGS: dict[str, tuple[str, ...]] = {
    "func": ("func", "روال"),
    "struct": ("struct", "ساختار"),
    "enum": ("enum", "جداشمار"),
    "interface": ("interface", "میانجی"),
    "impl": ("impl", "کاربست"),
    "type": ("type", "گونه"),
    "const": ("const", "پایا"),
    "import": ("import", "واردسازی"),
    "package": ("package", "بسته"),
    "extern": ("extern", "فراخوانه"),
    "layout": ("layout", "چیدمان"),
    "component": ("component", "بخش"),
    "end": ("end", "پایان"),
    "if": ("if", "اگر"),
    "else": ("else", "وگرنه"),
    "loop": ("until", "repeat", "each", "تکرار", "هر"),
    "match": ("match", "همخوان"),
    "switch": ("switch", "ترابرد"),
    "on": ("on", "بر"),
    "mut": ("mut", "ناپایا"),
    "pub": ("pub", "همگانی"),
    "modifier": ("deprecated", "inline", "noinline", "pure", "noret",
                 "بی‌کاره", "درخط", "نادرخط", "ناب", "نابرگشت"),
    "until_or_to": ("تا",),
    "other": ("ret", "as", "true", "false", "null", "this", "break", "continue",
              "print", "println", "printerr", "printerrln", "input", "defer",
              "operator", "to", "by", "in", "with",
              "برگشت", "برگردان", "درست", "نادرست", "پوچ", "این", "بشکن", "گذر",
              "چاپ", "سرچاپ", "نادرست‌چاپ", "نادرست‌سرچاپ", "ورودی", "دیرکن",
              "کارور", "از", "و", "یا", "برابر", "نابرابر"),
}
_KW: dict[str, str] = {}
for _canon, _spellings in _KEYWORD_SPELLINGS.items():
    for _spelling in _spellings:
        _KW[_kw_key(_spelling)] = _canon

_DECL_KEYWORDS = frozenset({
    "func", "struct", "enum", "interface", "impl", "type", "const", "import",
    "package", "extern", "layout", "component",
})
_BODY_DECLS = frozenset({
    "func", "struct", "enum", "interface", "impl", "extern", "layout", "component",
})
_LINK_WORDS = frozenset({"link", "پیوند"})
_LINK_KINDS = frozenset({"static", "dynamic", "framework", "ایستا", "پویا", "چارچوب"})
_THIS_WORDS = frozenset({"this", "این"})
_REPEAT_WORDS = frozenset({"repeat", "تکرار"})
_OPERATOR_WORDS = frozenset({"operator", "کارور"})
_VARIADIC_ARITY = 1000
_RETURN_WORDS = frozenset({"ret", "برگشت"})
_AS_WORDS = frozenset({"as", "برگردان"})
_BUILTIN_CALLS = frozenset({"len", "cap", "spawn", "join"})

_BUILTIN_TYPES = frozenset(_norm(name) for name in (
    "i8 i16 i32 i64 u8 u16 u32 u64 f32 f64 int uint float bool char str void "
    "size uchar auto Vector HashMap MapIter Variant File "
    "صحیح صحیح۸ صحیح۱۶ صحیح۳۲ صحیح۶۴ صحیح8 صحیح16 صحیح32 صحیح64 "
    "طبیعی طبیعی۸ طبیعی۱۶ طبیعی۳۲ طبیعی۶۴ طبیعی8 طبیعی16 طبیعی32 طبیعی64 "
    "اعشار اعشار۳۲ اعشار۶۴ اعشار32 اعشار64 منطقی نویسه یونیکد رشته تهی اندازه "
    "وکتور نگاشت پیمایشگرنگاشت گوناگون پرونده"
).split())

_TYPE_KINDS = frozenset({"struct", "enum", "interface", "type_alias", "component"})

_NUMBER = re.compile(
    r"0[xX][0-9a-fA-F_]+|0[bB][01_]+|0[oO][0-7_]+"
    r"|\d[\d_]*(?:\.\d[\d_]*)?(?:[eE][+-]?\d+)?f?"
)
_IDENT = re.compile(r"[^\W\d][\w‌‍ً-ٰٟۖ-ۭـ]*")
_TRIPLE = re.compile(r'"""(?:\\.|[^\\])*?"""', re.S)
_STRING = re.compile(r'u?"(?:\\.|[^"\\\n])*"')
_CHAR = re.compile(r"u?'(?:\\[^\n']*|[^'\\\n])'")
_GUILLEMET = re.compile(r"\u00ab(?:\\.|[^\u00bb\\\n])*\u00bb")
_OPERATOR = re.compile(
    r"\.\.\.|:=|=>|&:|==|!=|<=|>=|&&|\|\||\^\^=?|\+\+|--"
    r"|[+\-*/%&|^]=|[-+*/%<>=!&|^~?:,.;()\[\]{}]"
)

Token = tuple[str, str, int, int]


def _tokenize(text: str) -> list[Token]:
    toks: list[Token] = []
    pos, n, line, line_start = 0, len(text), 1, 0
    while pos < n:
        ch = text[pos]
        if ch == "\n":
            toks.append((_NL, "\n", line, pos - line_start))
            pos += 1
            line += 1
            line_start = pos
            continue
        if ch in " \t\r\f\v﻿":
            pos += 1
            continue
        if ch == "/" and text.startswith("//", pos):
            end = text.find("\n", pos)
            pos = n if end < 0 else end
            continue
        if ch == "/" and text.startswith("/*", pos):
            depth, p = 1, pos + 2
            while p < n and depth:
                opener = text.find("/*", p)
                closer = text.find("*/", p)
                if closer < 0:
                    p = n
                    break
                if 0 <= opener < closer:
                    depth += 1
                    p = opener + 2
                else:
                    depth -= 1
                    p = closer + 2
            segment = text[pos:p]
            newlines = segment.count("\n")
            if newlines:
                line += newlines
                line_start = pos + segment.rfind("\n") + 1
            pos = p
            continue
        col = pos - line_start
        if ch == "\u00ab":
            match = _GUILLEMET.match(text, pos)
            if match is not None:
                segment = match.group()
                toks.append((_STR, segment[1:-1], line, col))
                pos = match.end()
                continue
        if ch == "`":
            end = text.find("`", pos + 1)
            end = n if end < 0 else end + 1
            segment = text[pos:end]
            toks.append((_STR, segment[1:-1], line, col))
            newlines = segment.count("\n")
            if newlines:
                line += newlines
                line_start = pos + segment.rfind("\n") + 1
            pos = end
            continue
        if ch == '"' or (ch == "u" and text.startswith(('u"', "u'"), pos)):
            match = _TRIPLE.match(text, pos) if text.startswith('"""', pos) else None
            if match is None:
                match = _STRING.match(text, pos) or _CHAR.match(text, pos)
            if match is not None:
                segment = match.group()
                toks.append((_STR, segment.lstrip("u").strip("\"'"), line, col))
                newlines = segment.count("\n")
                if newlines:
                    line += newlines
                    line_start = pos + segment.rfind("\n") + 1
                pos = match.end()
                continue
            if ch == '"':
                end = text.find("\n", pos)
                end = n if end < 0 else end
                toks.append((_STR, text[pos + 1:end], line, col))
                pos = end
                continue
        if ch == "'":
            match = _CHAR.match(text, pos)
            if match is not None:
                toks.append((_STR, match.group()[1:-1], line, col))
                pos = match.end()
                continue
        if ch in "\u060c\u061f":
            toks.append((_OP, "," if ch == "\u060c" else "?", line, col))
            pos += 1
            continue
        if ch == "@":
            match = _IDENT.match(text, pos + 1)
            if match is not None:
                toks.append((_META, _fold(match.group()), line, col))
                pos = match.end()
                continue
        if ch.isdigit():
            match = _NUMBER.match(text, pos)
            if match is not None:
                toks.append((_NUM, match.group(), line, col))
                pos = match.end()
                continue
        match = _IDENT.match(text, pos)
        if match is not None:
            toks.append((_ID, match.group(), line, col))
            pos = match.end()
            continue
        match = _OPERATOR.match(text, pos)
        if match is not None:
            toks.append((_OP, match.group(), line, col))
            pos = match.end()
            continue
        toks.append((_OP, ch, line, col))
        pos += 1
    return toks


class _Frame:
    __slots__ = (
        "kind", "nid", "name", "brace_mode", "braces", "decl_ok", "layout_mode",
        "fields", "locals", "locals_via_call", "typarams", "owner",
    )

    def __init__(
        self,
        kind: str,
        nid: str,
        name: str = "",
        *,
        brace_mode: bool = False,
        decl_ok: bool = False,
        layout_mode: bool = False,
        typarams: frozenset[str] = frozenset(),
        owner: str = "",
    ) -> None:
        self.kind = kind
        self.nid = nid
        self.name = name
        self.brace_mode = brace_mode
        self.braces = 1 if brace_mode else 0
        self.decl_ok = decl_ok
        self.layout_mode = layout_mode
        self.fields: dict[str, str] = {}
        self.locals: dict[str, str] = {}
        self.locals_via_call: dict[str, int] = {}
        self.typarams = typarams
        self.owner = owner


class _SalamExtractor:
    def __init__(self, path: Path, source: str) -> None:
        self.path = path
        self.source_file = str(path)
        self.stem = _file_stem(path)
        self.file_id = _make_id(self.source_file)
        self.toks = _tokenize(source)
        self.n = len(self.toks)
        self.nodes: list[dict[str, Any]] = []
        self.edges: list[dict[str, Any]] = []
        self.raw_calls: list[dict[str, Any]] = []
        self.seen_ids: set[str] = set()
        self.seen_edges: set[tuple[str, str, str]] = set()
        self.package = "main"
        self.frames = [_Frame("file", self.file_id, decl_ok=True)]
        self.pending_meta: dict[str, list[str]] = {}
        self.meta: dict[str, list[str]] = {}
        self.aliases: dict[str, str] = {}
        self.funcs: dict[str, list[tuple[str, int, int]]] = {}
        self.methods: dict[tuple[str, str], list[tuple[str, int, int]]] = {}
        self.type_nodes: dict[str, str] = {}
        self.components: dict[str, str] = {}
        self.calls: list[dict[str, Any]] = []
        self.indirect_refs: list[tuple[str, str, str, int]] = []
        self.import_aliases: set[str] = set()
        self.owner_local_names: dict[str, set[str]] = {}
        self._call_by_close: dict[int, dict[str, Any]] = {}
        self.type_refs: list[dict[str, Any]] = []
        self.paren_stack: list[int] = []
        self.ternary = 0
        self.stray_ends = 0
        self.resyncs = 0

    def tok(self, i: int) -> Token | None:
        return self.toks[i] if 0 <= i < self.n else None

    def is_op(self, i: int, text: str) -> bool:
        t = self.tok(i)
        return t is not None and t[0] == _OP and t[1] == text

    def kw_at(self, i: int) -> str | None:
        t = self.tok(i)
        if t is None or t[0] != _ID or self.is_op(i - 1, "."):
            return None
        return _KW.get(_kw_key(t[1]))

    def add_node(
        self,
        nid: str,
        label: str,
        line: int,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if nid in self.seen_ids:
            return nid
        self.seen_ids.add(nid)
        details: dict[str, Any] = {"language": "salam", "kind": kind}
        if metadata:
            details.update(metadata)
        item: dict[str, Any] = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_location": f"L{line}",
            "metadata": details,
        }
        item["source_file"] = self.source_file if source_backed else ""
        if source_backed:
            details.setdefault("package", self.package)
        if callable_node:
            item["_callable"] = True
        self.nodes.append(item)
        return nid

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        line: int,
        *,
        context: str | None = None,
        confidence: str = "EXTRACTED",
        target_file: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        key = (source_id, target_id, relation if context is None else f"{relation}:{context}")
        if not source_id or not target_id or source_id == target_id or key in self.seen_edges:
            return
        self.seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": confidence,
            "source_file": self.source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if confidence == "INFERRED":
            edge["confidence_score"] = 0.8
        if context:
            edge["context"] = context
        if target_file:
            edge["target_file"] = target_file
        if metadata:
            edge["metadata"] = metadata
        self.edges.append(edge)

    def unique_id(self, *parts: str, arity: int | None = None) -> str:
        nid = _make_id(*parts)
        if nid not in self.seen_ids:
            return nid
        if arity is not None:
            with_arity = _make_id(*parts, f"{arity}p")
            if with_arity not in self.seen_ids:
                return with_arity
            nid = with_arity
        count = 2
        while f"{nid}_{count}" in self.seen_ids:
            count += 1
        return f"{nid}_{count}"

    def take_aliases(self) -> dict[str, str]:
        aliases: dict[str, str] = {}
        for lang in ("en", "fa"):
            values = self.meta.get(lang)
            if values:
                aliases[lang] = _norm(values[0])
        return aliases

    def name_run(self, i: int) -> tuple[list[str], int]:
        t = self.tok(i)
        if t is None:
            return [], i
        line, parts, j = t[2], [], i
        while True:
            t = self.tok(j)
            if t is None or t[0] != _ID or t[2] != line or self.kw_at(j) is not None:
                break
            parts.append(t[1])
            j += 1
        return parts, j

    def owner_frame(self) -> _Frame:
        for frame in reversed(self.frames):
            if frame.kind in ("func", "component", "layout", "struct", "interface", "impl"):
                return frame
        return self.frames[0]

    def fn_frame(self) -> _Frame | None:
        for frame in reversed(self.frames):
            if frame.kind in ("func", "component", "layout"):
                return frame
        return None

    def owner_type_frame(self) -> _Frame | None:
        for frame in reversed(self.frames):
            if frame.kind in ("struct", "impl"):
                return frame
        return None

    def typarams_in_scope(self) -> frozenset[str]:
        names: set[str] = set()
        for frame in self.frames:
            names |= frame.typarams
        return frozenset(names)

    def parse_type(self, j: int, refs: list[tuple[str, str]], tparams: frozenset[str]) -> int:
        t = self.tok(j)
        if t is None or t[0] != _ID:
            return -1
        kw = self.kw_at(j)
        if kw is not None and not (kw == "func" and not self.is_op(j - 1, ".")):
            return -1
        if kw == "func":
            j += 1
            if self.is_op(j, "("):
                j = self.skip_type_list(j + 1, ")", refs, tparams)
                if j < 0:
                    return -1
            end = self.parse_type(j, refs, tparams)
            return j if end < 0 else end
        parts, run_end = self.name_run(j)
        if not parts:
            return -1
        if _norm(parts[0]) == "dyn" and len(parts) > 1:
            parts = parts[1:]
            j += 1
        qualifier = ""
        while run_end < self.n and self.is_op(run_end, ".") and self.tok(run_end + 1) is not None:
            nxt_parts, nxt_end = self.name_run(run_end + 1)
            if not nxt_parts:
                break
            qualifier = _norm(" ".join(parts)) if not qualifier else qualifier + "." + _norm(" ".join(parts))
            parts, run_end = nxt_parts, nxt_end
        if qualifier:
            name = _norm(parts[0])
            end = run_end - len(parts) + 1
        else:
            name = _norm(parts[0])
            end = j + 1
        if name and name not in _BUILTIN_TYPES and name not in tparams and name != "dyn":
            refs.append((qualifier, name))
        j = end
        if self.is_op(j, "<"):
            j = self.skip_type_list(j + 1, ">", refs, tparams)
            if j < 0:
                return -1
        while True:
            if self.is_op(j, "*"):
                j += 1
            elif self.is_op(j, "["):
                depth = 1
                j += 1
                while j < self.n and depth:
                    if self.toks[j][0] == _NL:
                        return -1
                    if self.is_op(j, "["):
                        depth += 1
                    elif self.is_op(j, "]"):
                        depth -= 1
                    j += 1
            else:
                break
        return j

    def skip_type_list(
        self, j: int, close: str, refs: list[tuple[str, str]], tparams: frozenset[str]
    ) -> int:
        if self.is_op(j, close):
            return j + 1
        while True:
            j = self.parse_type(j, refs, tparams)
            if j < 0:
                return -1
            if self.is_op(j, ","):
                j += 1
                continue
            if self.is_op(j, close):
                return j + 1
            return -1

    def skip_balanced(self, j: int, open_op: str, close_op: str) -> int:
        depth = 0
        while j < self.n:
            if self.is_op(j, open_op):
                depth += 1
            elif self.is_op(j, close_op):
                depth -= 1
                if depth == 0:
                    return j + 1
            j += 1
        return j

    def parse_typarams(self, j: int, refs: list[tuple[str, str]]) -> tuple[int, frozenset[str]]:
        names: list[str] = []
        bounds: list[tuple[str, str]] = []
        j += 1
        while j < self.n and not self.is_op(j, ">"):
            t = self.toks[j]
            if t[0] == _NL:
                break
            if t[0] == _ID:
                names.append(_norm(t[1]))
                j += 1
                if self.is_op(j, ":"):
                    end = self.parse_type(j + 1, bounds, frozenset())
                    j = end if end >= 0 else j + 1
                continue
            j += 1
        refs.extend(bounds)
        return j + 1, frozenset(names)

    def parse_params(
        self, j: int, tparams: frozenset[str], refs: list[tuple[str, str]]
    ) -> tuple[int, list[tuple[str, str, bool]]]:
        params: list[tuple[str, str, bool]] = []
        j += 1
        while j < self.n and not self.is_op(j, ")"):
            if self.is_op(j, ","):
                j += 1
                continue
            if self.is_op(j, "..."):
                params.append(("...", "", True))
                j += 1
                continue
            parts, k = self.name_run(j)
            if not parts:
                if self.toks[j][0] == _NL:
                    j += 1
                    continue
                j += 1
                continue
            pname = _norm(" ".join(parts))
            has_default = False
            ptype = ""
            j = k
            if self.is_op(j, "&:") or self.is_op(j, ":"):
                pt_refs: list[tuple[str, str]] = []
                end = self.parse_type(j + 1, pt_refs, tparams)
                if end >= 0:
                    j = end
                    if pt_refs:
                        ptype = pt_refs[0][1]
                        refs.extend(pt_refs)
                else:
                    j += 1
            if self.is_op(j, "="):
                has_default = True
                depth = 0
                while j < self.n:
                    if self.is_op(j, "(") or self.is_op(j, "[") or self.is_op(j, "{"):
                        depth += 1
                    elif self.is_op(j, ")") or self.is_op(j, "]") or self.is_op(j, "}"):
                        if depth == 0:
                            break
                        depth -= 1
                    elif self.is_op(j, ",") and depth == 0:
                        break
                    j += 1
            params.append((pname, ptype, has_default))
        return j + 1, params

    def header_tail(
        self, j: int, tparams: frozenset[str], *, signature_ok: bool = False
    ) -> tuple[int, bool, list[tuple[str, str]], bool]:
        """After the parameter list: optional ``: return_type`` then ``:`` or ``{``.

        Returns ``(next_index, brace_mode, return_type_refs, has_body)``. Inside an
        ``extern:`` or ``interface`` block a header may be a bare signature.
        """
        ret_refs: list[tuple[str, str]] = []
        if self.is_op(j, ":"):
            trial: list[tuple[str, str]] = []
            end = self.parse_type(j + 1, trial, tparams)
            if end >= 0 and (self.is_op(end, ":") or self.is_op(end, "{")):
                ret_refs = trial
                j = end
            elif signature_ok and end >= 0 and (
                end >= self.n or self.toks[end][0] == _NL or self.kw_at(end) == "end"
            ):
                return end, False, trial, False
        elif signature_ok:
            return j, False, ret_refs, False
        if self.is_op(j, "{"):
            return j + 1, True, ret_refs, True
        if self.is_op(j, ":"):
            return j + 1, False, ret_refs, True
        return j, False, ret_refs, not signature_ok

    def push_type_refs(
        self, source_nid: str, refs: list[tuple[str, str]], context: str, line: int
    ) -> None:
        for qualifier, name in refs:
            self.type_refs.append({
                "source": source_nid, "name": name, "qualifier": qualifier,
                "context": context, "line": line,
            })

    def handle_package(self, i: int) -> int:
        parts, j = self.name_run(i + 1)
        if not parts:
            return i + 1
        name = _norm(" ".join(parts))
        line = self.toks[i][2]
        self.package = name
        self.nodes[0]["metadata"]["package"] = name
        if name == "main":
            return j
        aliases = self.take_aliases()
        pkg_id = self.add_node(
            _make_id("salam", "package", name), f"{name} (package)", line, kind="package",
            source_backed=False,
            metadata={"name": name, "declared": True, "aliases": aliases},
        )
        self.add_edge(pkg_id, self.file_id, "contains", line)
        return j

    def handle_import(self, i: int) -> int:
        line = self.toks[i][2]
        j = i + 1
        entries: list[tuple[str, str, bool]] = []
        while j < self.n and self.toks[j][2] == line:
            t = self.toks[j]
            if t[0] == _STR:
                entries.append(("", t[1], True))
                j += 1
                continue
            parts, k = self.name_run(j)
            if not parts:
                break
            if self.tok(k) is not None and self.toks[k][0] == _STR and self.toks[k][2] == line:
                entries.append((_norm(" ".join(parts)), self.toks[k][1], True))
                j = k + 1
                continue
            segments = [_norm(" ".join(parts))]
            j = k
            while self.is_op(j, ".") and self.toks[j][2] == line:
                more, k = self.name_run(j + 1)
                if not more:
                    break
                segments.append(_norm(" ".join(more)))
                j = k
            entries.append(("", ".".join(segments), False))
            break
        for alias, value, is_string in entries:
            self.add_import(alias, value, is_string, line)
        return max(j, i + 1)

    def add_import(self, alias: str, value: str, is_string: bool, line: int) -> None:
        if is_string and value.endswith(".salam") and "://" not in value:
            target = Path(os.path.normpath(self.path.parent / value))
            resolved_alias = alias or _norm(target.stem)
            self.import_aliases.add(resolved_alias)
            self.add_edge(
                self.file_id, _make_id(str(target)), "imports_from", line,
                target_file=str(target),
                metadata={"alias": resolved_alias, "salam_import": True},
            )
            return
        dotted = value.strip("/").replace("/", ".") if is_string else value
        leaf = _norm(dotted.split(".")[-1])
        if not leaf:
            return
        self.import_aliases.add(alias or leaf)
        self.add_edge(
            self.file_id, _make_id("salam", "import", leaf), "imports_from", line,
            metadata={"alias": alias or leaf, "path": dotted, "salam_import": True},
        )

    def handle_link(self, i: int) -> int:
        j = i + 1
        line = self.toks[i][2]
        kind = ""
        t = self.tok(j)
        if t is not None and t[0] == _ID and _norm(t[1]) in _LINK_KINDS:
            kind = _norm(t[1])
            j += 1
        t = self.tok(j)
        if t is not None and t[0] == _STR:
            lib = t[1]
            stub = self.add_node(
                _make_id(self.stem, "library", lib), f"{lib} (native library)", line,
                kind="native_library", metadata={"name": lib, "link_kind": kind},
            )
            self.add_edge(self.file_id, stub, "links", line)
            j += 1
        return j

    def handle_meta(self, i: int) -> int:
        name = self.toks[i][1]
        j = i + 1
        values: list[str] = []
        while self.tok(j) is not None and self.toks[j][0] == _STR and self.toks[j][2] == self.toks[i][2]:
            values.append(self.toks[j][1])
            j += 1
        if name in ("en", "fa") and values:
            self.pending_meta[name] = values
        return j

    def skip_modifiers(self, i: int) -> tuple[int, bool]:
        is_pub = False
        while self.kw_at(i) in ("pub", "modifier"):
            if self.kw_at(i) == "pub":
                is_pub = True
            i += 1
        return i, is_pub

    def stmt_start(self, i: int) -> bool:
        j = i - 1
        while j >= 0 and self.kw_at(j) in ("pub", "modifier"):
            j -= 1
        if j < 0:
            return True
        prev = self.toks[j]
        if prev[0] == _NL:
            return True
        return prev[0] == _OP and prev[1] in (":", ";", "{", "}")

    def stmt_first_col(self, i: int) -> int:
        j = i
        while j - 1 >= 0 and self.toks[j - 1][0] != _NL:
            j -= 1
        return self.toks[j][3]

    def operator_name(self, j: int) -> tuple[str, int]:
        """``func operator + (o: T)`` names the operator symbol itself."""
        t = self.tok(j)
        if t is None or t[0] != _ID or _kw_key(t[1]) not in _OPERATOR_WORDS:
            return "", j
        symbols: list[str] = []
        k = j + 1
        while k < self.n and self.toks[k][0] == _OP and self.toks[k][2] == t[2]:
            if self.toks[k][1] == "(" and symbols:
                break
            symbols.append(self.toks[k][1])
            k += 1
        return ("operator" + "".join(symbols), k) if symbols else ("", j)

    def handle_func(self, i: int, is_pub: bool, mods_start: int) -> int:
        frame = self.frames[-1]
        line = self.toks[i][2]
        operator_name, j = self.operator_name(i + 1)
        if operator_name:
            name = operator_name
        else:
            parts, j = self.name_run(i + 1)
            if not parts:
                return i + 1
            name = _norm(" ".join(parts))
        refs: list[tuple[str, str]] = []
        param_refs: list[tuple[str, str]] = []
        tparams: frozenset[str] = frozenset()
        if self.is_op(j, "<"):
            j, tparams = self.parse_typarams(j, refs)
        scope_tparams = self.typarams_in_scope() | tparams
        params: list[tuple[str, str, bool]] = []
        if self.is_op(j, "("):
            j, params = self.parse_params(j, scope_tparams, param_refs)
        j, brace_mode, ret_refs, has_body = self.header_tail(
            j, scope_tparams, signature_ok=frame.kind in ("interface", "extern")
        )
        signature_only = not has_body
        aliases = self.take_aliases()
        variadic = any(p[0] == "..." for p in params)
        params = [p for p in params if p[0] != "..."]
        min_arity = sum(1 for p in params if not p[2])
        max_arity = _VARIADIC_ARITY if variadic else len(params)
        in_type = frame.kind in ("struct", "interface", "impl")
        # Bare name only, package ignored - `methods` is keyed the same way
        # every other receiver-typing path here already is (this/declared/field).
        return_type = ret_refs[0][1] if len(ret_refs) == 1 else ""
        metadata: dict[str, Any] = {
            "name": name, "pub": is_pub, "arity": len(params), "aliases": aliases,
        }
        if return_type and return_type not in _BUILTIN_TYPES:
            metadata["return_type"] = return_type
        if in_type:
            owner = frame.owner or frame.name
            metadata["owner"] = owner
            nid = self.unique_id(frame.nid, name, arity=max_arity)
            kind = "method_signature" if frame.kind == "interface" else "method"
            self.add_node(
                nid, f".{name}()", line, kind=kind,
                callable_node=frame.kind != "interface", metadata=metadata,
            )
            self.add_edge(frame.nid, nid, "method", line)
            self.methods.setdefault((owner, name), []).append((nid, min_arity, max_arity))
            for alias in aliases.values():
                self.methods.setdefault((owner, alias), []).append((nid, min_arity, max_arity))
        else:
            nid = self.unique_id(self.stem, name, arity=max_arity)
            kind = "extern_function" if signature_only and frame.kind == "extern" else "function"
            self.add_node(nid, f"{name}()", line, kind=kind, callable_node=True, metadata=metadata)
            self.add_edge(self.file_id, nid, "contains", line)
            self.funcs.setdefault(name, []).append((nid, min_arity, max_arity))
            for alias in aliases.values():
                self.funcs.setdefault(alias, []).append((nid, min_arity, max_arity))
        self.push_type_refs(nid, refs, "type_bound", line)
        self.push_type_refs(nid, ret_refs, "return_type", line)
        self.push_type_refs(nid, param_refs, "param_type", line)
        if signature_only:
            return j
        fn = _Frame(
            "func", nid, name, brace_mode=brace_mode, typarams=tparams,
            owner=(frame.owner or frame.name) if in_type else "",
        )
        local_names = self.owner_local_names.setdefault(nid, set())
        for pname, ptype, _default in params:
            local_names.add(pname)
            if ptype:
                fn.locals[pname] = ptype
        self.frames.append(fn)
        return j

    def handle_struct_like(self, i: int, kw: str, is_pub: bool) -> int:
        line = self.toks[i][2]
        parts, j = self.name_run(i + 1)
        if not parts:
            return i + 1
        name = _norm(" ".join(parts))
        refs: list[tuple[str, str]] = []
        tparams: frozenset[str] = frozenset()
        if self.is_op(j, "<"):
            j, tparams = self.parse_typarams(j, refs)
        brace_mode = False
        if self.is_op(j, "{"):
            brace_mode = True
            j += 1
        elif self.is_op(j, ":"):
            j += 1
        aliases = self.take_aliases()
        nid = self.unique_id(self.stem, name)
        self.add_node(
            nid, name, line, kind=kw, metadata={"name": name, "pub": is_pub, "aliases": aliases},
        )
        self.add_edge(self.file_id, nid, "contains", line)
        self.type_nodes[name] = nid
        for alias in aliases.values():
            self.type_nodes.setdefault(alias, nid)
        self.push_type_refs(nid, refs, "type_bound", line)
        if kw == "enum":
            return self.handle_enum_body(j, nid, brace_mode)
        frame = _Frame(kw, nid, name, brace_mode=brace_mode, typarams=tparams, owner=name)
        self.frames.append(frame)
        return j

    def handle_enum_body(self, j: int, nid: str, brace_mode: bool) -> int:
        members: list[str] = []
        expect_member = True
        depth = 0
        while j < self.n:
            t = self.toks[j]
            if brace_mode:
                if self.is_op(j, "{"):
                    depth += 1
                elif self.is_op(j, "}"):
                    if depth == 0:
                        j += 1
                        break
                    depth -= 1
            elif self.kw_at(j) == "end" and depth == 0:
                j += 1
                break
            if t[0] == _NL or self.is_op(j, ","):
                expect_member = True
            elif t[0] == _ID and expect_member and depth == 0:
                members.append(_norm(t[1]))
                expect_member = False
            elif self.is_op(j, "("):
                depth += 1
            elif self.is_op(j, ")"):
                depth = max(0, depth - 1)
            j += 1
        for node in self.nodes:
            if node["id"] == nid:
                node["metadata"]["members"] = members[:64]
                break
        return j

    def handle_impl(self, i: int) -> int:
        line = self.toks[i][2]
        parts, j = self.name_run(i + 1)
        if not parts:
            return i + 1
        iface_qualifier = ""
        iface = _norm(" ".join(parts))
        while self.is_op(j, "."):
            more, k = self.name_run(j + 1)
            if not more:
                break
            iface_qualifier = iface if not iface_qualifier else iface_qualifier + "." + iface
            iface = _norm(" ".join(more))
            j = k
        if self.kw_at(j) != "on":
            return j
        refs: list[tuple[str, str]] = []
        end = self.parse_type(j + 1, refs, frozenset())
        if end < 0:
            return j + 1
        target = refs[0][1] if refs else _norm(self.toks[j + 1][1])
        j = end
        brace_mode = False
        if self.is_op(j, "{"):
            brace_mode, j = True, j + 1
        elif self.is_op(j, ":"):
            j += 1
        nid = self.unique_id(self.stem, "impl", iface, "on", target)
        label = f"impl {iface} on {target}"
        self.add_node(
            nid, label, line, kind="impl",
            metadata={"name": label, "interface": iface, "target": target},
        )
        self.add_edge(self.file_id, nid, "contains", line)
        self.type_refs.append({
            "source": nid, "name": iface, "qualifier": iface_qualifier,
            "context": "implements", "line": line, "relation": "implements",
        })
        if target not in _BUILTIN_TYPES:
            self.type_refs.append({
                "source": nid, "name": target, "qualifier": "",
                "context": "impl_target", "line": line,
            })
        self.frames.append(_Frame("impl", nid, label, brace_mode=brace_mode, owner=target))
        return j

    def handle_alias(self, i: int, is_pub: bool) -> int:
        line = self.toks[i][2]
        parts, j = self.name_run(i + 1)
        if not parts or not self.is_op(j, "="):
            return i + 1
        name = _norm(" ".join(parts))
        refs: list[tuple[str, str]] = []
        end = self.parse_type(j + 1, refs, frozenset())
        aliases = self.take_aliases()
        nid = self.unique_id(self.stem, name)
        self.add_node(
            nid, name, line, kind="type_alias",
            metadata={"name": name, "pub": is_pub, "aliases": aliases},
        )
        self.add_edge(self.file_id, nid, "contains", line)
        self.type_nodes[name] = nid
        self.push_type_refs(nid, refs, "alias_of", line)
        return end if end >= 0 else j + 1

    def handle_const(self, i: int, is_pub: bool) -> int:
        line = self.toks[i][2]
        parts, j = self.name_run(i + 1)
        if not parts:
            return i + 1
        name = _norm(" ".join(parts))
        aliases = self.take_aliases()
        nid = self.unique_id(self.stem, name)
        self.add_node(
            nid, name, line, kind="constant",
            metadata={"name": name, "pub": is_pub, "aliases": aliases},
        )
        self.add_edge(self.file_id, nid, "contains", line)
        return j

    def handle_layout(self, i: int) -> int:
        line = self.toks[i][2]
        j = i + 1
        if not self.is_op(j, ":"):
            return i + 1
        nid = self.unique_id(self.stem, "layout")
        self.add_node(nid, "layout", line, kind="layout", callable_node=False,
                      metadata={"name": "layout"})
        self.add_edge(self.file_id, nid, "contains", line)
        self.frames.append(_Frame("layout", nid, "layout", layout_mode=True))
        return j + 1

    def handle_component(self, i: int, is_pub: bool) -> int:
        line = self.toks[i][2]
        parts, j = self.name_run(i + 1)
        if not parts:
            return i + 1
        name = _norm(" ".join(parts))
        refs: list[tuple[str, str]] = []
        params: list[tuple[str, str, bool]] = []
        if self.is_op(j, "("):
            j, params = self.parse_params(j, frozenset(), refs)
        if self.is_op(j, ":"):
            j += 1
        aliases = self.take_aliases()
        nid = self.unique_id(self.stem, name)
        self.add_node(
            nid, name, line, kind="component",
            metadata={"name": name, "arity": len(params), "aliases": aliases},
        )
        self.add_edge(self.file_id, nid, "contains", line)
        self.type_nodes[name] = nid
        self.components[name] = nid
        self.frames.append(_Frame("component", nid, name, layout_mode=True))
        return j

    def handle_extern(self, i: int) -> int:
        j = i + 1
        while j < self.n and self.toks[j][0] == _STR:
            j += 1
        if self.is_op(j, ":"):
            self.frames.append(_Frame("extern", self.file_id, "extern"))
            return j + 1
        return i + 1

    def handle_field(self, i: int, frame: _Frame, is_pub: bool) -> int | None:
        parts, j = self.name_run(i)
        if not parts and self.tok(i)[0] == _ID and self.is_op(i + 1, ":"):
            parts, j = [self.toks[i][1]], i + 1
        if not parts or not self.is_op(j, ":"):
            return None
        refs: list[tuple[str, str]] = []
        end = self.parse_type(j + 1, refs, frame.typarams)
        if end < 0:
            return None
        name = _norm(" ".join(parts))
        if refs:
            frame.fields[name] = refs[0][1]
        self.push_type_refs(frame.nid, refs, "field_type", self.toks[i][2])
        for node in self.nodes:
            if node["id"] == frame.nid:
                fields = node["metadata"].setdefault("fields", [])
                if len(fields) < 64:
                    fields.append(name)
                break
        return end

    def pop_frame(self) -> None:
        if len(self.frames) > 1:
            self.frames.pop()
        else:
            self.stray_ends += 1

    def maybe_lambda_block(self, close_index: int, open_index: int) -> bool:
        """``(params): ... end`` opens a block; ``(params) => expr`` does not."""
        if not self.is_op(close_index + 1, ":"):
            return False
        k = open_index - 1
        while k >= 0 and self.toks[k][0] == _NL:
            k -= 1
        before = self.tok(k)
        if before is None:
            return False
        if before[0] == _OP:
            if before[1] not in (":=", "=", ",", "(", "[", "=>"):
                return False
        elif before[0] != _ID or _kw_key(before[1]) not in _RETURN_WORDS:
            return False
        trial: list[tuple[str, str]] = []
        end = self.parse_type(close_index + 2, trial, frozenset())
        return not (end >= 0 and self.is_op(end, "=>"))

    def arg_count(self, open_index: int) -> int:
        depth, commas, seen = 0, 0, False
        j = open_index
        while j < self.n:
            if self.is_op(j, "(") or self.is_op(j, "[") or self.is_op(j, "{"):
                depth += 1
                if depth > 1:
                    seen = True
            elif self.is_op(j, ")") or self.is_op(j, "]") or self.is_op(j, "}"):
                depth -= 1
                if depth == 0:
                    break
            elif self.is_op(j, ",") and depth == 1:
                commas += 1
            elif depth >= 1 and self.toks[j][0] != _NL:
                seen = True
            j += 1
        return commas + 1 if seen else 0

    def matching_close(self, open_index: int) -> int:
        """Index of the ``)`` matching the ``(`` at *open_index*."""
        depth, j = 0, open_index
        while j < self.n:
            if self.is_op(j, "("):
                depth += 1
            elif self.is_op(j, ")"):
                depth -= 1
                if depth == 0:
                    return j
            j += 1
        return self.n - 1

    def call_open_after(self, j: int) -> int:
        """``(`` of the call whose result a ``name :=`` binds, or -1.

        Matches ``name(...)`` and ``qualifier.name(...)``; bails on a deeper
        chain (``f().g()``) rather than guess which call's return type wins.
        """
        parts, k = self.name_run(j)
        if not parts:
            return -1
        while self.is_op(k, "."):
            more, k2 = self.name_run(k + 1)
            if not more:
                return -1
            k = k2
        if not self.is_op(k, "("):
            return -1
        close = self.matching_close(k)
        if self.is_op(close + 1, "."):
            return -1
        return k

    def receiver_chain(self, dot_index: int) -> list[str]:
        """Segments of ``a.b.c`` ending at the dot before the callee, left to right."""
        segments: list[str] = []
        j = dot_index
        while self.is_op(j, "."):
            k = j - 1
            run: list[str] = []
            line = self.toks[j][2]
            while k >= 0 and self.toks[k][0] == _ID and self.toks[k][2] == line:
                is_this = _norm(self.toks[k][1]) in _THIS_WORDS
                if self.kw_at(k) is not None and not is_this:
                    break
                run.append(self.toks[k][1])
                if is_this:
                    # "this"/"این" is a keyword but always the chain's root -
                    # include it, then stop (nothing legitimately precedes it).
                    break
                k -= 1
                if self.is_op(k, "."):
                    break
            if not run:
                return []
            segments.append(_norm(" ".join(reversed(run))))
            j = k
        segments.reverse()
        return segments

    def mark_local(self, name: str) -> None:
        """Record *name* as a param/local of the enclosing function, regardless
        of whether a type was inferred - shadowing (`func Escape(db: Database)`
        alongside a same-file `import db`) must still hide the import alias
        from the qualified-argument-reference check, unrelated to typing."""
        owner = self.fn_frame()
        if owner is not None:
            self.owner_local_names.setdefault(owner.nid, set()).add(name)

    def lookup_local_type(self, name: str) -> str:
        for frame in reversed(self.frames):
            if name in frame.locals:
                return frame.locals[name]
            if frame.kind == "func" or frame.kind == "component":
                break
        return ""

    def lookup_local_via_call(self, name: str) -> int | None:
        """Close-paren index of the call a local's value came from (``x := f()``)."""
        for frame in reversed(self.frames):
            if name in frame.locals_via_call:
                return frame.locals_via_call[name]
            if frame.kind == "func" or frame.kind == "component":
                break
        return None

    def construction_type_before(self, close_brace: int) -> str:
        """Type name of the ``Type { ... }`` / ``Type<Args> { ... }`` ending here."""
        if not self.is_op(close_brace, "}"):
            return ""
        depth, k = 1, close_brace - 1
        while k >= 0 and depth:
            if self.is_op(k, "}"):
                depth += 1
            elif self.is_op(k, "{"):
                depth -= 1
                if depth == 0:
                    break
            k -= 1
        if depth != 0:
            return ""
        j = k - 1
        if self.is_op(j, ">"):
            angle_depth, m = 1, j - 1
            while m >= 0 and angle_depth:
                if self.is_op(m, ">"):
                    angle_depth += 1
                elif self.is_op(m, "<"):
                    angle_depth -= 1
                m -= 1
            if angle_depth != 0:
                return ""
            j = m
        t = self.tok(j)
        if t is None or t[0] != _ID or self.kw_at(j) is not None:
            return ""
        return _norm(t[1])

    def _via_call_of(self, close_index: int) -> dict[str, Any] | None:
        inner = self._call_by_close.get(close_index)
        if inner is None:
            return None
        via: dict[str, Any] = {"callee": inner["callee"], "argc": inner["argc"]}
        if inner["member"]:
            via["is_member_call"] = True
        for key in ("receiver_type", "qualifier", "typed_by"):
            if inner.get(key):
                via[key] = inner[key]
        return via

    def note_call(self, i: int, open_index: int) -> None:
        t = self.toks[i]
        line = t[2]
        # Multi-word names are real (`func is weekend(...)`, `dog.is weekend()`):
        # merge backward across plain identifiers first, THEN look at whatever
        # precedes the whole run to decide member vs. bare - a `.` right before
        # "weekend" alone would otherwise cut a member call's name to one word.
        k = i
        callee_parts = [t[1]]
        while (
            k - 1 >= 0 and self.toks[k - 1][0] == _ID and self.toks[k - 1][2] == line
            and self.kw_at(k - 1) is None
        ):
            k -= 1
            callee_parts.insert(0, self.toks[k][1])
        run_end = k
        member = self.is_op(run_end - 1, ".")
        callee = _norm(" ".join(callee_parts))
        if not callee or (not member and callee in _BUILTIN_CALLS):
            return
        owner = self.owner_frame()
        call: dict[str, Any] = {
            "caller": owner.nid, "callee": callee, "line": line,
            "argc": self.arg_count(open_index), "member": member,
        }
        if member:
            chain = self.receiver_chain(run_end - 1)
            call["receiver"] = ".".join(chain)
            if chain:
                root = chain[0]
                owner_type = self.owner_type_frame()
                if root in _THIS_WORDS and owner_type is not None:
                    if len(chain) == 1:
                        call["receiver_type"] = owner_type.owner or owner_type.name
                        call["typed_by"] = "this"
                    elif len(chain) == 2 and chain[1] in owner_type.fields:
                        call["receiver_type"] = owner_type.fields[chain[1]]
                        call["typed_by"] = "field"
                elif len(chain) == 1:
                    declared = self.lookup_local_type(root)
                    if declared:
                        call["receiver_type"] = declared
                        call["typed_by"] = "declared"
                    else:
                        via_close = self.lookup_local_via_call(root)
                        via = self._via_call_of(via_close) if via_close is not None else None
                        if via is not None:
                            call["via_call"] = via
                        else:
                            call["qualifier"] = root
                else:
                    call["qualifier"] = ".".join(chain)
            elif self.is_op(run_end - 2, "}"):
                # `Type { ... }.method()` / `Type<Args> { ... }.method()`: the type
                # is spelled right here, no cross-file inference needed.
                type_name = self.construction_type_before(run_end - 2)
                if type_name and type_name not in _BUILTIN_TYPES:
                    call["receiver_type"] = type_name
                    call["typed_by"] = "literal"
            elif self.is_op(run_end - 2, ")"):
                # `f(x).method()` / `pkg.Make(x).method()`: the receiver is
                # whatever that call returns - resolved cross-file, if at all,
                # from the callee's own declared return type.
                via = self._via_call_of(run_end - 2)
                if via is not None:
                    call["via_call"] = via
        close_index = self.matching_close(open_index)
        self._call_by_close[close_index] = call
        self.calls.append(call)
        self.note_arg_references(open_index, close_index)

    def note_arg_references(self, open_index: int, close_index: int) -> None:
        """A bare identifier that is a WHOLE call argument (``h(r, "/", home)``)
        names a function value, not a call: "a bare named function decays to its
        address" (SKILL.md §2). Record it as a candidate indirect reference,
        resolved in ``finish()`` once every definition in this file is known.
        Scoped to call-argument position only (not assignments or literal
        fields) to keep this a precise, low-noise signal.
        """
        depth = 0
        span: list[int] = []
        j = open_index + 1
        while j <= close_index:
            if self.is_op(j, "(") or self.is_op(j, "[") or self.is_op(j, "{"):
                depth += 1
            elif self.is_op(j, ")") or self.is_op(j, "]") or self.is_op(j, "}"):
                depth -= 1
            at_boundary = j == close_index or (depth == 0 and self.is_op(j, ","))
            if not at_boundary and self.toks[j][0] != _NL:
                span.append(j)
            if at_boundary:
                self.note_one_arg_reference(span)
                span = []
            j += 1

    def note_one_arg_reference(self, span: list[int]) -> None:
        caller = self.owner_frame().nid
        if len(span) == 1 and self.toks[span[0]][0] == _ID and self.kw_at(span[0]) is None:
            name = _norm(self.toks[span[0]][1])
            if name:
                self.indirect_refs.append((caller, name, "", self.toks[span[0]][2]))
            return
        # `pkg.Name` as a whole argument: same value-reference shape, package-qualified.
        if (
            len(span) == 3 and self.toks[span[0]][0] == _ID and self.kw_at(span[0]) is None
            and self.is_op(span[1], ".") and self.toks[span[2]][0] == _ID
            and self.kw_at(span[2]) is None
        ):
            qualifier = _norm(self.toks[span[0]][1])
            name = _norm(self.toks[span[2]][1])
            if qualifier and name:
                self.indirect_refs.append((caller, name, qualifier, self.toks[span[2]][2]))

    def note_construction(self, i: int) -> None:
        t = self.toks[i]
        name = _norm(t[1])
        if not name[:1].isupper() or name in _BUILTIN_TYPES:
            return
        self.type_refs.append({
            "source": self.owner_frame().nid, "name": name, "qualifier": "",
            "context": "construct", "line": t[2],
        })

    def rhs_cast_type_after(self, start: int) -> str:
        """Type of the rightmost top-level ``... as Type`` before end of statement.

        Skips a cast to a builtin (``as int``, ``as Variant<...>``) and keeps
        scanning a chain (``x as int as u8``), so only a genuine user-type cast
        wins. Used to type a `:=` binding directly from its cast instead of
        guessing at the uncast expression's shape.
        """
        depth, j, result = 0, start, ""
        while j < self.n:
            t = self.toks[j]
            if t[0] == _NL:
                break
            if t[0] == _OP:
                if t[1] in ("(", "[", "{"):
                    depth += 1
                elif t[1] in (")", "]", "}"):
                    if depth == 0:
                        break
                    depth -= 1
                elif depth == 0 and t[1] in (",", ";"):
                    break
            if depth == 0 and t[0] == _ID and _kw_key(t[1]) in _AS_WORDS:
                refs: list[tuple[str, str]] = []
                end = self.parse_type(j + 1, refs, self.typarams_in_scope())
                if end < 0:
                    break
                if len(refs) == 1 and not refs[0][0]:
                    result = refs[0][1]
                j = end
                continue
            j += 1
        return result

    def note_local_binding(self, i: int) -> int:
        """Track ``name := Type {``, ``name := f()`` and ``name: Type`` so member
        calls on the bound name can be typed."""
        fn = self.fn_frame()
        if fn is None:
            return i + 1
        parts, j = self.name_run(i)
        if not parts:
            return i + 1
        name = _norm(" ".join(parts))
        self.mark_local(name)
        if self.is_op(j, ":="):
            cast_type = self.rhs_cast_type_after(j + 1)
            if cast_type and cast_type not in _BUILTIN_TYPES:
                fn.locals[name] = cast_type
                return j
            t = self.tok(j + 1)
            if t is not None and t[0] == _ID and self.kw_at(j + 1) is None and self.is_op(j + 2, "{"):
                tname = _norm(t[1])
                if tname not in _BUILTIN_TYPES:
                    fn.locals[name] = tname
            else:
                open_idx = self.call_open_after(j + 1)
                if open_idx >= 0:
                    fn.locals_via_call[name] = self.matching_close(open_idx)
        elif self.is_op(j, ":") and not self.is_op(j, ":="):
            refs: list[tuple[str, str]] = []
            end = self.parse_type(j + 1, refs, self.typarams_in_scope())
            if end >= 0 and refs:
                fn.locals[name] = refs[0][1]
        return j

    def try_layout_element(self, i: int, frame: _Frame) -> int | None:
        t = self.toks[i]
        if t[0] != _ID or not self.is_op(i + 1, ":"):
            return None
        if self.ternary:
            self.ternary -= 1
            return None
        name = _norm(t[1])
        if name in self.components:
            self.type_refs.append({
                "source": self.owner_frame().nid, "name": name, "qualifier": "",
                "context": "component_use", "line": t[2],
            })
        self.frames.append(_Frame("element", frame.nid, name, layout_mode=True))
        return i + 2

    def run(self) -> dict:
        self.add_node(self.file_id, self.path.name, 1, kind="file", metadata={"package": "main"})
        i = 0
        while i < self.n:
            if self.toks[i][0] == _NL:
                self.ternary = 0
                i += 1
                continue
            if self.toks[i][0] == _META:
                i = self.handle_meta(i)
                continue
            self.meta, self.pending_meta = self.pending_meta, {}
            frame = self.frames[-1]
            i = self.step_layout(i, frame) if frame.layout_mode else self.step_code(i, frame)
        self.finish()
        return {"nodes": self.nodes, "edges": self.edges, "raw_calls": self.raw_calls}

    def step_layout(self, i: int, frame: _Frame) -> int:
        kind, text, line, col = self.toks[i]
        if kind == _ID and self.kw_at(i) == "end" and not self.is_op(i + 1, "="):
            self.pop_frame()
            return i + 1
        if kind == _OP and text == "?":
            self.ternary += 1
        element = self.try_layout_element(i, frame)
        if element is not None:
            return element
        if kind == _ID and self.is_op(i + 1, "(") and self.toks[i + 1][2] == line:
            self.note_call(i, i + 1)
        return i + 1

    def step_code(self, i: int, frame: _Frame) -> int:
        kind, text, line, col = self.toks[i]
        if frame.kind in ("match", "switch") and self.is_arm_block(i):
            self.frames.append(_Frame("block", frame.nid, "arm"))
            return self.arm_colon(i) + 1
        if (
            frame.kind == "struct" and kind == _ID and self.is_op(i + 1, ":")
            and self.kw_at(i) not in ("end", "pub", "modifier", "func") and self.stmt_start(i)
        ):
            end = self.handle_field(i, frame, False)
            if end is not None:
                return end
        if kind == _OP:
            if text == "{":
                frame.braces += 1
            elif text == "}":
                frame.braces -= 1
                if frame.brace_mode and frame.braces <= 0:
                    self.pop_frame()
            elif text == "(":
                self.paren_stack.append(i)
            elif text == ")" and self.paren_stack:
                open_index = self.paren_stack.pop()
                if self.maybe_lambda_block(i, open_index):
                    self.frames.append(_Frame("lambda", frame.nid, "lambda"))
                    return i + 2
            return i + 1
        if kind != _ID:
            return i + 1
        if self.is_op(i - 1, "."):
            if self.is_op(i + 1, "(") and self.toks[i + 1][2] == line:
                self.note_call(i, i + 1)
            return i + 1
        kw = self.kw_at(i)
        if kw is None:
            return self.step_word(i, frame)
        return self.step_keyword(i, frame, kw)

    def arm_colon(self, i: int) -> int:
        depth, j = 0, i
        while j < self.n and self.toks[j][0] != _NL:
            if self.toks[j][0] == _OP:
                text = self.toks[j][1]
                if text in ("(", "[", "{"):
                    depth += 1
                elif text in (")", "]", "}"):
                    depth -= 1
                elif depth == 0 and text in (":", "=>"):
                    return j if text == ":" else -1
            j += 1
        return -1

    def is_arm_block(self, i: int) -> bool:
        """A ``match`` arm written ``pattern: statements end`` owns its own ``end``."""
        prev = self.tok(i - 1)
        if prev is not None and prev[0] != _NL:
            return False
        if self.kw_at(i) == "end":
            return False
        return self.arm_colon(i) >= 0

    def step_word(self, i: int, frame: _Frame) -> int:
        kind, text, line, col = self.toks[i]
        if _norm(text) in _LINK_WORDS and frame.decl_ok and self.stmt_start(i):
            nxt = self.tok(i + 1)
            if nxt is not None and (
                nxt[0] == _STR or (nxt[0] == _ID and _norm(nxt[1]) in _LINK_KINDS)
            ):
                return self.handle_link(i)
        if frame.kind == "struct" and self.stmt_start(i):
            end = self.handle_field(i, frame, False)
            if end is not None:
                return end
        if frame.decl_ok and frame.kind in ("file", "cond") and self.stmt_start(i):
            end = self.handle_top_variable(i)
            if end is not None:
                return end
        if self.is_op(i + 1, "(") and self.toks[i + 1][2] == line:
            self.note_call(i, i + 1)
            return i + 1
        if self.is_op(i + 1, "<") and self.generic_call_open(i + 1) >= 0:
            self.note_call(i, self.generic_call_open(i + 1))
            return i + 1
        if self.is_op(i + 1, "{") and self.toks[i + 1][2] == line:
            self.note_construction(i)
            return i + 1
        if frame.kind in ("func", "block", "lambda") and self.stmt_start_word(i):
            return max(self.note_local_binding(i), i + 1)
        return i + 1

    def stmt_start_word(self, i: int) -> bool:
        prev = self.tok(i - 1)
        if prev is None or prev[0] == _NL:
            return True
        if prev[0] == _OP and prev[1] in (":", ";", "{"):
            return True
        return self.kw_at(i - 1) == "mut"

    def generic_call_open(self, lt_index: int) -> int:
        refs: list[tuple[str, str]] = []
        end = self.skip_type_list(lt_index + 1, ">", refs, self.typarams_in_scope())
        if end >= 0 and self.is_op(end, "("):
            return end
        return -1

    def handle_top_variable(self, i: int) -> int | None:
        parts, j = self.name_run(i)
        if not parts or not (self.is_op(j, ":=") or self.is_op(j, ":")):
            return None
        if self.is_op(j, ":"):
            refs: list[tuple[str, str]] = []
            if self.parse_type(j + 1, refs, frozenset()) < 0:
                return None
        name = _norm(" ".join(parts))
        line = self.toks[i][2]
        nid = self.unique_id(self.stem, name)
        self.add_node(
            nid, name, line, kind="variable",
            metadata={"name": name, "aliases": self.take_aliases()},
        )
        self.add_edge(self.file_id, nid, "contains", line)
        return j

    def step_keyword(self, i: int, frame: _Frame, kw: str) -> int:
        kind, text, line, col = self.toks[i]
        if kw == "end":
            self.pop_frame()
            return i + 1
        if kw in ("if", "loop", "match", "switch"):
            if self.is_op(i + 1, "="):
                # `Type { if = true }` / `f(if = 1)`: a keyword reused as a field
                # or parameter name in a literal/call, never the real statement -
                # a genuine `if`/`match`/`switch`/loop is never followed by '='.
                return i + 1
            if kw == "loop" and self.is_repeat_step(i):
                return i + 1
            if not (kw == "if" and self.kw_at(i - 1) == "else"):
                opened = self.block_frame(frame)
                if kw in ("match", "switch"):
                    opened = _Frame(kw, frame.nid, kw)
                self.frames.append(opened)
            return i + 1
        if kw == "until_or_to":
            if self.stmt_start_word(i):
                self.frames.append(self.block_frame(frame))
            return i + 1
        if kw == "mut":
            after = i + 1
            if frame.decl_ok and frame.kind in ("file", "cond") and self.stmt_start(i):
                end = self.handle_top_variable(after)
                if end is not None:
                    return end
            if frame.kind in ("func", "block", "lambda"):
                return max(self.note_local_binding(after), i + 1)
            return i + 1
        if kw in ("pub", "modifier") or kw in _DECL_KEYWORDS:
            return self.step_declaration(i, frame)
        return i + 1

    def is_repeat_step(self, i: int) -> bool:
        """Inside a ``repeat`` header ``each``/``هر`` is the step, not a loop opener."""
        if _kw_key(self.toks[i][1]) not in ("each", "هر"):
            return False
        j = i - 1
        while j >= 0 and self.toks[j][0] != _NL:
            if self.toks[j][0] == _ID and _kw_key(self.toks[j][1]) in _REPEAT_WORDS:
                return not self.is_op(j - 1, ".")
            j -= 1
        return False

    def block_frame(self, frame: _Frame) -> _Frame:
        if frame.decl_ok:
            return _Frame("cond", frame.nid, "if", decl_ok=True)
        return _Frame("block", frame.nid, "block")

    def step_declaration(self, i: int, frame: _Frame) -> int:
        j, is_pub = self.skip_modifiers(i)
        kw = self.kw_at(j)
        if kw not in _DECL_KEYWORDS:
            return i + 1
        if not self.stmt_start(j) and kw != "const":
            return j + 1
        in_body = frame.kind in ("func", "block", "lambda")
        if frame.kind != "cond" and self.stmt_first_col(j) == 0 and (
            kw != "func" or in_body or frame.layout_mode
        ):
            base = 1
            while base < len(self.frames) and self.frames[base].kind == "cond":
                base += 1
            if len(self.frames) > base:
                self.frames[:] = self.frames[:base]
                self.paren_stack.clear()
                self.resyncs += 1
            frame, in_body = self.frames[-1], False
        if in_body and kw != "const":
            return j + 1
        if kw == "package":
            return self.handle_package(j)
        if kw == "import":
            return self.handle_import(j)
        if kw == "func":
            return self.handle_func(j, is_pub, i)
        if kw in ("struct", "enum", "interface"):
            return self.handle_struct_like(j, kw, is_pub)
        if kw == "impl":
            return self.handle_impl(j)
        if kw == "type":
            return self.handle_alias(j, is_pub)
        if kw == "const":
            return j + 1 if in_body else self.handle_const(j, is_pub)
        if kw == "extern":
            return self.handle_extern(j)
        if kw == "layout":
            return self.handle_layout(j)
        return self.handle_component(j, is_pub)

    def finish(self) -> None:
        for call in self.calls:
            self.resolve_call(call)
        for ref in self.type_refs:
            self.resolve_type_ref(ref)
        for caller, name, qualifier, line in self.indirect_refs:
            self.resolve_indirect_ref(caller, name, qualifier, line)

    def resolve_indirect_ref(self, caller: str, name: str, qualifier: str, line: int) -> None:
        if not qualifier:
            # Same-file only: Salam bans a variable/param reusing a function's
            # name (E090), but only within the scope that sees both - a plain
            # local elsewhere in a 2600-file corpus can coincidentally share a
            # name with some unrelated function, and unlike a real call there is
            # no argc to disambiguate a value reference with. Deferring this to
            # the cross-file generic indirect_call pass turned nearly every
            # bare-identifier argument in the corpus into a same-named-anywhere
            # guess; same-file resolution has no such collision risk.
            candidates = self.funcs.get(name)
            if not candidates or len(candidates) != 1 or candidates[0][0] == caller:
                return
            self.add_edge(
                caller, candidates[0][0], "indirect_call", line,
                context="argument", confidence="INFERRED",
            )
            return
        # `qualifier.Name` as a whole argument is ambiguous at the token level -
        # `c.query` (a field read) looks identical to `pkg.Func` (a reference) -
        # so only proceed when `qualifier` is an actual import alias declared
        # SOMEWHERE in this file (checked here, in finish(), so it doesn't
        # matter whether the call site precedes the import in the token
        # stream), AND not shadowed by a param/local of THIS SPECIFIC function
        # (`func Escape(db: Database)` alongside a same-file `import db` is
        # real code here - the param wins inside its own function).
        if qualifier not in self.import_aliases:
            return
        if qualifier in self.owner_local_names.get(caller, ()):
            return
        self.raw_calls.append({
            "caller_nid": caller, "callee": name, "language": "salam",
            "source_file": self.source_file, "source_location": f"L{line}",
            "indirect": True, "context": "argument", "qualifier": qualifier,
        })

    def pick_overload(
        self, candidates: list[tuple[str, int, int]], argc: int
    ) -> list[str]:
        fitting = [c for c in candidates if c[1] <= argc <= c[2]]
        chosen = fitting or candidates
        return sorted({c[0] for c in chosen})

    def resolve_call(self, call: dict[str, Any]) -> None:
        caller, callee, line, argc = call["caller"], call["callee"], call["line"], call["argc"]
        if not call["member"]:
            candidates = self.funcs.get(callee)
            if candidates:
                for target in self.pick_overload(candidates, argc):
                    self.add_edge(caller, target, "calls", line, context="call")
                return
            self.raw_calls.append({
                "caller_nid": caller, "callee": callee, "language": "salam",
                "source_file": self.source_file, "source_location": f"L{line}",
                "argc": argc,
            })
            return
        receiver_type = call.get("receiver_type")
        if receiver_type:
            candidates = self.methods.get((receiver_type, callee))
            if candidates:
                confidence = "EXTRACTED" if call.get("typed_by") == "this" else "INFERRED"
                for target in self.pick_overload(candidates, argc):
                    self.add_edge(caller, target, "calls", line, context="call", confidence=confidence)
                return
        raw: dict[str, Any] = {
            "caller_nid": caller, "callee": callee, "language": "salam",
            "source_file": self.source_file, "source_location": f"L{line}",
            "is_member_call": True, "receiver": call.get("receiver", ""), "argc": argc,
        }
        for key in ("receiver_type", "typed_by", "qualifier", "via_call"):
            if call.get(key):
                raw[key] = call[key]
        self.raw_calls.append(raw)

    def resolve_type_ref(self, ref: dict[str, Any]) -> None:
        name, qualifier, line = ref["name"], ref["qualifier"], ref["line"]
        relation = ref.get("relation", "references")
        local = self.type_nodes.get(name) if not qualifier else None
        if local is not None:
            self.add_edge(ref["source"], local, relation, line, context=ref["context"])
            return
        target = _make_id("salam", "type", qualifier, name) if qualifier else _make_id("salam", "type", name)
        self.add_edge(
            ref["source"], target, relation, line, context=ref["context"],
            metadata={"salam_ref": {"name": name, "qualifier": qualifier}},
        )


def extract_salam(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}
    return _SalamExtractor(path, source).run()


def _package_of(node: dict[str, Any] | None) -> str:
    metadata = (node or {}).get("metadata")
    return str(metadata.get("package", "")) if isinstance(metadata, dict) else ""


def resolve_salam_references(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Bind package aliases, type references and package/receiver-qualified calls.

    Runs after every file is extracted, so a Persian import path resolves to the
    English package it names (via ``@fa``), a type named in one file finds its
    struct in another, and ``pkg.Func()`` / ``value.method()`` land on the exact
    definition when exactly one candidate exists.
    """
    def meta(node: dict) -> dict:
        value = node.get("metadata")
        return value if isinstance(value, dict) else {}

    salam_nodes = [n for n in all_nodes if meta(n).get("language") == "salam"]
    by_id: dict[str, dict] = {}
    for node in all_nodes:
        by_id.setdefault(node.get("id"), node)

    package_id: dict[str, str] = {}
    package_by_alias: dict[str, str] = {}
    for node in salam_nodes:
        details = meta(node)
        if details.get("kind") != "package" or not details.get("declared"):
            continue
        name = str(details.get("name", ""))
        package_id[name] = node["id"]
        package_by_alias[name] = name
        for alias in (details.get("aliases") or {}).values():
            if alias:
                package_by_alias[str(alias)] = name

    file_imports: dict[str, dict[str, str]] = {}
    file_import_targets: dict[str, dict[str, str]] = {}
    for edge in all_edges:
        edge_meta = edge.get("metadata")
        if edge.get("relation") != "imports_from" or not isinstance(edge_meta, dict):
            continue
        if not edge_meta.get("salam_import"):
            continue
        source_file = str(edge.get("source_file", ""))
        alias = str(edge_meta.get("alias", ""))
        if "path" not in edge_meta:
            file_import_targets.setdefault(source_file, {})[alias] = str(edge.get("target"))
            continue
        leaf = str(edge_meta.get("path", "")).split(".")[-1]
        canonical = package_by_alias.get(_norm(leaf), _norm(leaf))
        file_imports.setdefault(source_file, {})[alias] = canonical
        if canonical in package_id and edge.get("target") != package_id[canonical]:
            edge["target"] = package_id[canonical]

    type_defs: dict[str, list[dict]] = {}
    for node in salam_nodes:
        details = meta(node)
        if details.get("kind") in _TYPE_KINDS and node.get("source_file"):
            keys = {str(details.get("name", ""))}
            keys.update(str(a) for a in (details.get("aliases") or {}).values() if a)
            for key in keys:
                if key:
                    type_defs.setdefault(key, []).append(node)

    for edge in all_edges:
        edge_meta = edge.get("metadata")
        ref = edge_meta.get("salam_ref") if isinstance(edge_meta, dict) else None
        if not isinstance(ref, dict):
            continue
        name, qualifier = str(ref.get("name", "")), str(ref.get("qualifier", ""))
        candidates = type_defs.get(name, [])
        if qualifier:
            source_file = str(edge.get("source_file", ""))
            head = qualifier.split(".")[-1]
            package = file_imports.get(source_file, {}).get(head) or package_by_alias.get(head, head)
            candidates = [c for c in candidates if _package_of(c) == package]
        else:
            source_package = _package_of(by_id.get(edge.get("source")))
            same_package = [c for c in candidates if _package_of(c) == source_package]
            candidates = same_package if len(same_package) == 1 else candidates
        if len(candidates) == 1:
            edge["target"] = candidates[0]["id"]
            edge_meta.pop("salam_ref", None)

    file_node_id = {
        n.get("source_file"): n["id"] for n in salam_nodes if meta(n).get("kind") == "file"
    }
    functions: dict[tuple[str, str], list[dict]] = {}
    methods: dict[tuple[str, str], list[dict]] = {}
    functions_by_file: dict[tuple[str, str], list[dict]] = {}
    for node in salam_nodes:
        details = meta(node)
        kind = details.get("kind")
        keys = {str(details.get("name", ""))}
        keys.update(str(a) for a in (details.get("aliases") or {}).values() if a)
        for key in keys:
            if not key:
                continue
            if kind in ("function", "extern_function"):
                functions.setdefault((str(details.get("package", "")), key), []).append(node)
                functions_by_file.setdefault(
                    (str(file_node_id.get(node.get("source_file"), "")), key), []
                ).append(node)
            elif kind == "method":
                methods.setdefault((str(details.get("owner", "")), key), []).append(node)

    existing = {
        (e.get("source"), e.get("target")) for e in all_edges if e.get("relation") == "calls"
    }
    existing_indirect = {
        (e.get("source"), e.get("target"))
        for e in all_edges if e.get("relation") == "indirect_call"
    }

    def fits(nodes: list[dict], argc: int) -> list[dict]:
        matching = [n for n in nodes if meta(n).get("arity", argc) >= argc]
        return matching or nodes

    def targets_for(call_like: dict, source_file: str, caller: str | None) -> tuple[list[dict], str, str]:
        """Candidate target nodes for a call (or a chained call's own inner call),
        as (candidates, context, confidence); ``context`` is "" when the call's
        shape (a bare member call with no known receiver) can't be looked up at
        all - the signal the caller uses to try a ``via_call`` chain instead."""
        callee = _norm(str(call_like.get("callee", "")))
        qualifier = call_like.get("qualifier")
        receiver_type = call_like.get("receiver_type")
        if qualifier and "." not in str(qualifier):
            alias = str(qualifier)
            target_file = file_import_targets.get(source_file, {}).get(alias)
            if target_file:
                return functions_by_file.get((target_file, callee), []), "package_call", "EXTRACTED"
            package = file_imports.get(source_file, {}).get(alias)
            if package is not None:
                candidates = [
                    n for n in functions.get((package, callee), []) if meta(n).get("pub", True)
                ]
                return candidates, "package_call", "EXTRACTED"
            return [], "package_call", "EXTRACTED"
        if receiver_type:
            confidence = "EXTRACTED" if call_like.get("typed_by") == "this" else "INFERRED"
            return methods.get((str(receiver_type), callee), []), "method_call", confidence
        if not call_like.get("is_member_call"):
            package = _package_of(by_id.get(caller))
            return functions.get((package, callee), []), "call", "INFERRED"
        return [], "", ""

    for result in per_file:
        for call in result.get("raw_calls", []) or []:
            if call.get("language") != "salam":
                continue
            if call.get("indirect"):
                # A bare `pkg.Name` argument (a function reference, not a call):
                # package-qualified, so resolved here the same way a qualified
                # call is, rather than by extract.py's own generic same-label
                # indirect_call pass, which knows nothing of Salam packages. An
                # unqualified bare name is left to that shared pass.
                qualifier = call.get("qualifier")
                if not qualifier:
                    continue
                caller = call.get("caller_nid")
                source_file = str(call.get("source_file", ""))
                candidates, context, _confidence = targets_for(call, source_file, caller)
                if context:
                    candidates = fits(candidates, 0)
                if len(candidates) == 1:
                    target = candidates[0]["id"]
                    pair = (caller, target)
                    if caller and target != caller and pair not in existing and pair not in existing_indirect:
                        existing_indirect.add(pair)
                        all_edges.append({
                            "source": caller,
                            "target": target,
                            "relation": "indirect_call",
                            "context": "argument",
                            "confidence": "INFERRED",
                            "confidence_score": 0.8,
                            "source_file": source_file,
                            "source_location": call.get("source_location"),
                            "weight": 1.0,
                        })
                continue
            caller, callee = call.get("caller_nid"), _norm(str(call.get("callee", "")))
            source_file = str(call.get("source_file", ""))
            argc = int(call.get("argc", 0) or 0)
            candidates, context, confidence = targets_for(call, source_file, caller)
            if not context:
                # A plain member call with no locally-typed receiver: try the type
                # the receiver's OWN call (`f(x)` in `f(x).method()`, or the call
                # a local variable was bound from) declares as its return type.
                via = call.get("via_call")
                if isinstance(via, dict):
                    via_argc = int(via.get("argc", 0) or 0)
                    via_candidates, via_context, _via_confidence = targets_for(via, source_file, caller)
                    if via_context:
                        via_candidates = fits(via_candidates, via_argc)
                        if len(via_candidates) == 1:
                            return_type = meta(via_candidates[0]).get("return_type")
                            if return_type:
                                candidates = methods.get((str(return_type), callee), [])
                                context, confidence = "chained_call", "INFERRED"
            candidates = fits(candidates, argc)
            if len(candidates) != 1:
                continue
            target = candidates[0]["id"]
            if not caller or target == caller or (caller, target) in existing:
                continue
            existing.add((caller, target))
            edge: dict[str, Any] = {
                "source": caller,
                "target": target,
                "relation": "calls",
                "context": context,
                "confidence": confidence,
                "source_file": source_file,
                "source_location": call.get("source_location"),
                "weight": 1.0,
            }
            if confidence == "INFERRED":
                edge["confidence_score"] = 0.8
            else:
                edge["confidence_score"] = 1.0
            all_edges.append(edge)
