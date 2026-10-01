"""Structural extraction for InterSystems ObjectScript (.cls UDL classes and
.mac/.rtn/.inc routines). See graphify/extractors/MIGRATION.md."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterator

from tree_sitter import Node

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.engine import _first_parse_error_line, _has_multiline_error

_LANG = "objectscript"
_UDL_SUFFIXES = frozenset({".cls"})
_INCLUDE_SUFFIXES = frozenset({".inc"})
_UDL_MEMBER_KINDS = {
    "method", "classmethod", "clientmethod", "property", "parameter",
    "relationship", "foreignkey", "query", "index", "trigger", "xdata",
    "projection", "storage",
}
_UDL_NAME_NODE = {
    "method": "method_name", "classmethod": "method_name", "clientmethod": "method_name",
    "property": "property_name", "parameter": "parameter_name",
    "relationship": "relationship_name", "foreignkey": "foreignkey_name",
    "query": "query_name", "index": "index_name", "trigger": "trigger_name",
    "xdata": "xdata_name", "projection": "projection_name", "storage": "storage_name",
}
_METHOD_KINDS = {"method", "classmethod", "clientmethod"}
_IDENT_TYPES = {"identifier", "objectscript_identifier", "objectscript_identifier_special"}
_COMMENT_TYPES = {
    "documatic_line", "line_comment_1", "line_comment_2", "line_comment_3",
    "line_comment_4", "block_comment", "inline_comment", "argumentless_inline_comment",
}
_POUND_CONDITIONALS = {"pound_if", "pound_ifdef", "pound_ifndef", "pound_else", "pound_elseif"}
# `#if <expr>` (and its `#elseif`/`#else`-adjacent first clause) is parsed by
# tree-sitter-objectscript 1.9.22 as one of these *leaf* nodes -- raw,
# unparsed body text with no `statement` children at all -- unlike
# `#ifdef`/`#ifndef`, whose identifier-only condition does yield a real
# nested `statement` tree. See `_scan_pound_if_leaf`.
_POUND_IF_LEAF_TYPES = {
    "pound_if_special_case", "pound_if_special_case_else", "pound_if_special_case_else_if",
}
_INSTANTIATING_METHODS = {"%New"}
_DOLLAR_CLASS_FUNCS = {"$classmethod"}
_CLASS_TOKEN_FULL_RE = re.compile(r"^[%A-Za-z][A-Za-z0-9]*(?:\.[%A-Za-z][A-Za-z0-9]*)+$")
_XDATA_CLASS_ATTRS = {
    "targetClass", "sourceClass", "class", "ClassName", "classname", "request",
    "response", "type", "context", "production", "transform", "Forward",
    "messageClass", "requestClass", "responseClass", "returnType",
    "targetObjClass", "sourceObjClass",
}
_XDATA_ATTR_RE = re.compile(r"""\b([A-Za-z][A-Za-z0-9]*)\s*=\s*(['"])([^'"]*)\2""")
_XDATA_CLASS_CALL_RE = re.compile(r"##class\(([%A-Za-z][A-Za-z0-9.]*)\)\.([%A-Za-z][A-Za-z0-9]*)\(", re.I)
_XDATA_REST_CALL_RE = re.compile(
    r"""\bCall\s*=\s*['"]([%A-Za-z][A-Za-z0-9.]*):([%A-Za-z][A-Za-z0-9]*)['"]"""
)
# Bare same-class production `Call="MethodName"` (no `ClassName:` prefix) --
# routes to on_self_call rather than on_class_call. The value must be a plain
# identifier with no colon/dot, so this never overlaps _XDATA_REST_CALL_RE.
_XDATA_SELF_CALL_RE = re.compile(r"""\bCall\s*=\s*['"]([%A-Za-z][A-Za-z0-9]*)['"]""")
# Fallback text scan for the unparsed body of a `_POUND_IF_LEAF_TYPES` leaf
# (see there): `Do`/`Goto L^R`, `Do`/`Goto ^R`, `Do`/`Goto L`.
_POUND_IF_LINE_CALL_RE = re.compile(
    r"""\b(?:Do|Goto)\s+(?:
            (?P<label1>[%A-Za-z][A-Za-z0-9]*)\^(?P<routine1>[%A-Za-z][A-Za-z0-9.]*)
          | \^(?P<routine2>[%A-Za-z][A-Za-z0-9.]*)
          | (?P<label2>[%A-Za-z][A-Za-z0-9]*)
        )""",
    re.X,
)
_POUND_IF_MACRO_RE = re.compile(r"\$\$\$([%A-Za-z][A-Za-z0-9]*)")
_POUND_IF_SELF_CALL_RE = re.compile(r"\.\.([%A-Za-z][A-Za-z0-9]*)\s*\(")
_COMPILED_HEADER_NAME_RE = re.compile(rb"^([%A-Za-z][A-Za-z0-9.]*)\^(?:MAC|INT|INC)\^", re.M)
_XDATA_MAX_SCAN_BYTES = 1_000_000

# Sniffs (grammar-free, byte-level).
_OS_CLASS_HEADER_RE = re.compile(
    rb"^[ \t]*Class[ \t]+([%A-Za-z][A-Za-z0-9]*(?:\.[%A-Za-z0-9]+)*)[ \t]*(?:Extends\b|\[|\{|\r?$)",
    re.M,
)
_OS_CLASS_MARKERS = (
    b"##class(", b"ClassMethod ", b" As %", b"XData ", b"$$$", b"Extends %",
    b"\nInclude ", b"\nImport ", b"\nMethod ",
)
_OS_INC_HEADER_RE = re.compile(
    rb"^ROUTINE[ \t]+[%A-Za-z][A-Za-z0-9.]*[ \t]*\[[ \t]*Type[ \t]*=[ \t]*INC\b", re.M | re.I
)
_OS_INC_DIRECTIVE_RE = re.compile(
    rb"^[ \t]*#(?:define|def1arg|dim|include|import|if|ifdef|ifndef|elseif|else|endif)\b",
    re.M | re.I,
)
_OS_INC_STRONG_MARKERS = (b"#def1arg", b"#dim ", b"$$$", b"##class(", b"##continue", b"##Continue", b"##;")
# ObjectScript-only syntax that a C header or Pascal include never contains:
# `$Get(`/`$ZDateTime(`-style intrinsic and `$$label(` extrinsic function calls
# (`$` is not an identifier character in C; Pascal only uses it for hex
# literals, never before `(`), and `#define NAME(%arg)` macro parameters, which
# ObjectScript requires to start with `%`.
_OS_INC_STRONG_RE = re.compile(
    rb"\$\$?[%A-Za-z][A-Za-z0-9]*\(|^[ \t]*#define[ \t]+[%A-Za-z][A-Za-z0-9]*\([ \t]*%",
    re.M | re.I,
)
# Legacy `%RO` export container (Studio / "Save for Source Control"): a
# `^INC^...` banner line, then a `%RO` line, then `Name^INC` — no directive
# needs to follow, so this is checked before the directive gate.
_OS_RO_EXPORT_RE = re.compile(rb"^%RO\r?\n[%A-Za-z][A-Za-z0-9.]*\^(?:INC|MAC|INT)\b", re.M)
_PASCAL_INC_MARKERS = (b"{$", b":=", b"begin", b"end;", b"procedure ", b"function ", b"unit ", b"uses ")

_HEAD_SCAN_BYTES = 256 * 1024


# --------------------------------------------------------------------------
# Module-level helpers (grammar-shape aware, but not extraction-state aware).
# --------------------------------------------------------------------------


def _ident_text(node: Node | None, source: bytes) -> str:
    if node is None:
        return ""
    child = _child(node, *_IDENT_TYPES)
    if child is not None:
        return _read_text(child, source)
    text = _read_text(node, source)
    if len(text) >= 2 and text[0] == text[-1] == '"':
        return text[1:-1]
    return text


def _child(node: Node | None, *types: str) -> Node | None:
    if node is None:
        return None
    for c in node.children:
        if c.type in types:
            return c
    return None


def _children(node: Node | None, *types: str) -> list[Node]:
    if node is None:
        return []
    return [c for c in node.children if c.type in types]


def _find_descendant(node: Node, type_name: str, max_depth: int = 3) -> Node | None:
    if node.type == type_name:
        return node
    if max_depth <= 0:
        return None
    for c in node.children:
        found = _find_descendant(c, type_name, max_depth - 1)
        if found is not None:
            return found
    return None


def _has_indirection(node: Node, max_depth: int = 4) -> bool:
    if node.type == "indirection":
        return True
    if max_depth <= 0:
        return False
    return any(_has_indirection(c, max_depth - 1) for c in node.children)


def _keyword_text(node: Node, source: bytes) -> str:
    parts = [
        _read_text(c, source)
        for c in node.children
        if c.type.endswith("_keyword") or c.type.endswith("_keywords")
    ]
    return " ".join(parts)


def _canonical_class(name: str) -> str:
    if name.startswith("%") and "." not in name:
        return f"%Library.{name[1:]}"
    return name


def _short_name(full: str) -> str:
    return full.rsplit(".", 1)[-1]


def _package(full: str) -> str:
    if "." in full:
        return full.rsplit(".", 1)[0]
    return ""


def _qualify_candidates(name: str, own_pkg: str, imports: list[str]) -> list[str]:
    if "." in name or name.startswith("%"):
        return [_canonical_class(name)]
    cands: list[str] = []
    if own_pkg:
        cands.append(f"{own_pkg}.{name}")
    for pkg in imports:
        cands.append(f"{pkg}.{name}")
    cands.append(f"User.{name}")
    return cands


def _typename_class(typename: Node | None, source: bytes) -> tuple[str | None, str | None]:
    if typename is None:
        return None, None
    ident_children = [c for c in typename.children if c.type in _IDENT_TYPES]
    if not ident_children:
        return None, None
    of_node = _child(typename, "keyword_of")
    if of_node is not None:
        after = [c for c in ident_children if c.start_byte > of_node.start_byte]
        if after:
            element = _read_text(after[0], source)
            collection = _read_text(ident_children[0], source).lower()
            return element, collection
    return _read_text(ident_children[0], source), None


def _iter_statements(node: Node) -> Iterator[Node]:
    for child in node.children:
        if child.type == "statement":
            yield child
        elif child.type in _POUND_CONDITIONALS:
            yield from _iter_statements(child)
        elif child.type == "ERROR":
            for gc in child.children:
                if gc.type == "statement":
                    yield gc
                elif gc.type in _POUND_CONDITIONALS:
                    yield from _iter_statements(gc)


def _line(node: Node) -> str:
    return f"L{node.start_point[0] + 1}"


def _is_objectscript_class(path: Path) -> bool:
    try:
        head = path.read_bytes()[:_HEAD_SCAN_BYTES]
    except OSError:
        return False
    m = _OS_CLASS_HEADER_RE.search(head)
    if m is None:
        return False
    return b"." in m.group(1) or any(marker in head for marker in _OS_CLASS_MARKERS)


def _is_objectscript_include(path: Path) -> bool:
    try:
        head = path.read_bytes()[:_HEAD_SCAN_BYTES]
    except OSError:
        return False
    if _OS_INC_HEADER_RE.search(head) or (head.startswith(b"^INC^") and _OS_RO_EXPORT_RE.search(head)):
        return True
    if not _OS_INC_DIRECTIVE_RE.search(head):
        return False
    if any(marker in head for marker in _PASCAL_INC_MARKERS):
        return False
    # `#define`/`#include`/`#ifndef`/`#endif` alone are also plain C preprocessor
    # syntax (a C-style header guard parses identically). Require a positive,
    # InterSystems-specific signal rather than defaulting to ObjectScript for
    # anything that merely fails to look like Pascal — same posture as
    # `_is_objectscript_class` requiring a dotted name or a positive marker.
    return any(marker in head for marker in _OS_INC_STRONG_MARKERS) or bool(_OS_INC_STRONG_RE.search(head))


# --------------------------------------------------------------------------
# Extraction
# --------------------------------------------------------------------------


def extract_objectscript(path: Path) -> dict:
    suffix = path.suffix.lower()
    is_udl = suffix in _UDL_SUFFIXES
    is_include = suffix in _INCLUDE_SUFFIXES
    try:
        from tree_sitter import Language, Parser
        if is_udl:
            import tree_sitter_objectscript_udl as _ts
            lang_fn = _ts.language_objectscript_udl
        else:
            import tree_sitter_objectscript_routine as _ts
            lang_fn = _ts.language_objectscript_routine
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-objectscript not installed"}
    try:
        source = path.read_bytes()
        root = Parser(Language(lang_fn())).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"ObjectScript grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()
    self_methods: dict[str, str] = {}
    self_members: dict[str, str] = {}
    self_params: dict[str, str] = {}
    self_labels: dict[str, str] = {}
    self_macros: dict[str, str] = {}
    bodies: list[tuple[list[Node], str, str, str]] = []
    pending: list[tuple[Node, str]] = []
    includes: list[str] = []
    imports: list[str] = []
    own_pkg = ""
    class_full: str | None = None
    class_nid = ""
    rname: str | None = None

    # ---- base closures -----------------------------------------------

    def add_node(
        nid: str,
        label: str,
        node: Node,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            details: dict[str, Any] = {"language": _LANG, "kind": kind}
            if metadata:
                details.update(metadata)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": _line(node),
                "metadata": details,
            }
            # Stubs (source_backed=False) carry an EMPTY source_file rather than
            # no key: graphify's validator requires the field on every node, and
            # `_rewire_unique_stub_nodes` / the resolver test for truthiness.
            item["source_file"] = source_file if source_backed else ""
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(
        src: str,
        tgt: str,
        relation: str,
        node: Node,
        *,
        confidence: str = "EXTRACTED",
        context: str | None = None,
        metadata: dict[str, Any] | None = None,
        score: float | None = None,
    ) -> None:
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": score if score is not None else (1.0 if confidence == "EXTRACTED" else 0.85),
            "source_file": source_file,
            "source_location": _line(node),
            "weight": 1.0,
        }
        if context is not None:
            edge["context"] = context
        if metadata:
            edge["metadata"] = metadata
        edges.append(edge)

    def add_raw_call(**fields: Any) -> None:
        # Every ObjectScript raw call names its own target scope: a class for
        # `##class(X).M()` / `..M()`, a routine for `$$L^R`, an include for
        # `$$$MACRO`. A bare-name match on `M`/`L` would bind to any same-named
        # symbol in the corpus, so `is_qualified_call` tells the shared
        # cross-file pass in extract.py to leave them to
        # resolve_objectscript_calls. `is_member_call` keeps its usual meaning
        # (a call on a class or on self) and is set only for those kinds.
        fields["language"] = _LANG
        fields["is_qualified_call"] = True
        fields["is_member_call"] = fields.get("kind") in ("class_call", "self_call")
        fields.setdefault("source_file", source_file)
        raw_calls.append(fields)

    def class_ref(name: str, node: Node) -> str:
        if "." in name or name.startswith("%"):
            full = _canonical_class(name)
        else:
            full = f"{own_pkg}.{name}" if own_pkg else name
        if class_full is not None and full.casefold() == class_full.casefold():
            return class_nid
        cands = _qualify_candidates(name, own_pkg, imports)
        full = cands[0]
        nid = _make_id("objectscript", "class", full)
        return add_node(
            nid, full, node, kind="external_class", source_backed=False,
            metadata={"full_name": full, "package": _package(full), "alternatives": cands[1:]},
        )

    def include_stub(name: str, node: Node) -> str:
        return add_node(
            _make_id("objectscript", "include", name), name, node,
            kind="external_include", source_backed=False, metadata={"routine": name},
        )

    # ---- call-resolution handlers (used from both UDL and routine bodies) --

    def on_self_call(caller_nid: str, name: str, node: Node, *, confidence: str = "EXTRACTED",
                      context: str | None = None) -> None:
        if class_full is None:
            return
        if name in self_methods:
            add_edge(caller_nid, self_methods[name], "calls", node, confidence=confidence, context=context)
        else:
            add_raw_call(
                caller_nid=caller_nid, callee=name, owner=class_full, kind="self_call",
                source_location=_line(node),
            )

    def on_class_call(caller_nid: str, cls_name: str, method_name: str, node: Node, *,
                       confidence: str = "EXTRACTED", context: str | None = None) -> None:
        cands = _qualify_candidates(cls_name, own_pkg, imports)
        is_self = class_full is not None and (
            _canonical_class(cls_name).casefold() == class_full.casefold()
            or ("." not in cls_name and cls_name.casefold() == _short_name(class_full).casefold())
        )
        if is_self:
            on_self_call(caller_nid, method_name, node, confidence=confidence, context=context)
            return
        cls_nid = class_ref(cls_name, node)
        if method_name in _INSTANTIATING_METHODS:
            add_edge(caller_nid, cls_nid, "instantiates", node, confidence=confidence)
            return
        ref_context = "type" if confidence == "EXTRACTED" else "value"
        add_edge(caller_nid, cls_nid, "references", node, confidence=confidence, context=ref_context)
        add_raw_call(
            caller_nid=caller_nid, callee=method_name, target_class=cands[0],
            alternatives=cands[1:], kind="class_call", confidence=confidence,
            context=context or "class_method_call", source_location=_line(node),
        )

    def on_line_ref(caller_nid: str, node: Node) -> None:
        if _has_indirection(node):
            return
        lr = _child(node, "line_ref")
        rr = _child(lr, "routine_ref") if lr is not None else _child(node, "routine_ref")
        label_node_ = _child(lr, "method_name") if lr is not None else _child(node, "method_name")
        label = _ident_text(label_node_, source) if label_node_ is not None else None
        routine: str | None = None
        if rr is not None:
            rn = _child(rr, "routine_name")
            if rn is None:
                return
            routine = _ident_text(rn, source)
        if routine is None:
            if label is not None and label in self_labels:
                add_edge(caller_nid, self_labels[label], "calls", node)
            return
        if rname is not None and routine.casefold() == rname.casefold() and label is not None \
                and label in self_labels:
            add_edge(caller_nid, self_labels[label], "calls", node, context="routine_call")
            return
        add_raw_call(
            caller_nid=caller_nid, routine=routine, label=label, callee=label or routine,
            kind="routine_call", source_location=_line(node),
        )

    def on_macro_use(caller_nid: str, name: str, node: Node) -> None:
        if name in self_macros:
            add_edge(caller_nid, self_macros[name], "uses", node)
        else:
            add_raw_call(
                caller_nid=caller_nid, callee=name, includes=list(includes), kind="macro_use",
                source_location=_line(node),
            )

    def scan_pound_if_leaf(caller_nid: str, node: Node) -> None:
        # `node` is a _POUND_IF_LEAF_TYPES leaf: raw, unparsed text for a
        # `#if <expr>` body that the grammar never breaks into a `statement`
        # tree (see the type comment). Text-scan it the same way XData bodies
        # are scanned so `Do`/`Goto`, `##class(...)` and `$$$MACRO` inside it
        # are not silently lost. `node` still belongs to the real tree (only
        # its *children* are missing), so its line number is accurate and it
        # can stand in wherever a call/reference handler needs a `Node` for
        # `_line()`/`add_node()`/`add_edge()`.
        text = _read_text(node, source)
        if len(text) > _XDATA_MAX_SCAN_BYTES:
            return
        for m in _XDATA_CLASS_CALL_RE.finditer(text):
            on_class_call(
                caller_nid, m.group(1), m.group(2), node, confidence="INFERRED",
                context="conditional_call",
            )
        for m in _POUND_IF_LINE_CALL_RE.finditer(text):
            label = m.group("label1") or m.group("label2")
            routine = m.group("routine1") or m.group("routine2")
            if routine:
                add_raw_call(
                    caller_nid=caller_nid, routine=routine, label=label, callee=label or routine,
                    kind="routine_call", source_location=_line(node),
                )
            elif label and label in self_labels:
                add_edge(
                    caller_nid, self_labels[label], "calls", node, confidence="INFERRED",
                    context="conditional_call",
                )
        for m in _POUND_IF_MACRO_RE.finditer(text):
            on_macro_use(caller_nid, m.group(1), node)
        for m in _POUND_IF_SELF_CALL_RE.finditer(text):
            on_self_call(caller_nid, m.group(1), node, confidence="INFERRED", context="conditional_call")

    def scan_xdata(xdata_nid: str, body: Node | None) -> None:
        if body is None:
            return
        text = _read_text(body, source)
        if len(text) > _XDATA_MAX_SCAN_BYTES:
            return
        for m in _XDATA_ATTR_RE.finditer(text):
            attr, value = m.group(1), m.group(3)
            if attr not in _XDATA_CLASS_ATTRS:
                continue
            if not _CLASS_TOKEN_FULL_RE.match(value):
                continue
            target = class_ref(value, body)
            add_edge(
                xdata_nid, target, "references", body, confidence="INFERRED", context="value",
                metadata={"xdata": True, "attribute": attr},
            )
        for m in _XDATA_CLASS_CALL_RE.finditer(text):
            on_class_call(
                xdata_nid, m.group(1), m.group(2), body, confidence="INFERRED", context="dynamic_call"
            )
        for m in _XDATA_REST_CALL_RE.finditer(text):
            on_class_call(
                xdata_nid, m.group(1), m.group(2), body, confidence="INFERRED", context="dynamic_call"
            )
        for m in _XDATA_SELF_CALL_RE.finditer(text):
            on_self_call(xdata_nid, m.group(1), body, confidence="INFERRED", context="dynamic_call")

    # ---- UDL walk -------------------------------------------------------

    def process_member(member: Node, kind: str) -> None:
        nonlocal class_full
        if kind == "storage":
            return
        if kind in _METHOD_KINDS:
            _member_method(member, kind)
        elif kind in ("property", "relationship"):
            _member_property_or_relationship(member, kind)
        elif kind == "parameter":
            _member_parameter(member)
        elif kind == "xdata":
            _member_xdata(member)
        elif kind == "index":
            _member_index(member)
        elif kind == "foreignkey":
            _member_foreignkey(member)
        elif kind == "query":
            _member_query(member)
        elif kind == "trigger":
            _member_trigger(member)
        elif kind == "projection":
            _member_projection(member)

    def _member_method(member: Node, kind: str) -> None:
        container = _child(member, "method_definition") or member
        name_node = _child(container, _UDL_NAME_NODE[kind])
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        arguments = _child(container, "arguments")
        arg_nodes = _children(arguments, "argument") if arguments is not None else []
        arity = len(arg_nodes)

        body_language: str | None = None
        body_stmts: list[Node] = []
        ext_lang_node = _find_descendant(container, "keyword_external_language", max_depth=3)
        if ext_lang_node is not None:
            tn = _child(ext_lang_node, "typename")
            if tn is not None:
                body_language = _read_text(tn, source)
        else:
            call_kw = _find_descendant(container, "call_method_keyword", max_depth=3)
            codemode_expr_node = _find_descendant(
                container, "method_keyword_codemode_expression", max_depth=3
            )
            if call_kw is not None:
                rtc = _child(container, "routine_tag_call")
                if rtc is not None:
                    body_stmts = [rtc]
            elif codemode_expr_node is not None:
                # `[ CodeMode = expression ]` bodies are a single `expression`
                # node directly under the container, never `statement` children.
                body_stmts = _children(container, "expression")
            else:
                body_stmts = _children(container, "statement")
                for err in (c for c in container.children if c.type == "ERROR"):
                    body_stmts.extend(_children(err, "statement"))

        kw_text = _keyword_text(container, source)
        codemode_match = re.search(r"CodeMode\s*=\s*(\w+)", kw_text)
        codemode = codemode_match.group(1) if codemode_match else None

        method_nid = add_node(
            _make_id(class_nid, name), f".{name}()", member, kind=kind, callable_node=True,
            metadata={
                "owner": class_full, "name": name, "arity": arity,
                "is_classmethod": kind != "method", "body_language": body_language,
                "codemode": codemode,
            },
        )
        add_edge(class_nid, method_nid, "method", member)
        self_methods[name] = method_nid

        for arg in arg_nodes:
            rt = _child(arg, "return_type")
            tn = _child(rt, "typename") if rt is not None else None
            if tn is not None:
                element, _coll = _typename_class(tn, source)
                if element and not element.startswith("%"):
                    add_edge(method_nid, class_ref(element, arg), "references", arg, context="parameter_type")
        ret = _child(container, "return_type")
        if ret is not None:
            tn = _child(ret, "typename")
            if tn is not None:
                element, _coll = _typename_class(tn, source)
                if element and not element.startswith("%"):
                    add_edge(method_nid, class_ref(element, ret), "references", ret, context="return_type")

        if body_stmts:
            bodies.append((body_stmts, method_nid, kind, name))

    def _member_property_or_relationship(member: Node, kind: str) -> None:
        name_node = _child(member, _UDL_NAME_NODE[kind])
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        return_type = _child(member, "return_type")
        typename = _child(return_type, "typename") if return_type is not None else None
        element, collection = _typename_class(typename, source)
        metadata: dict[str, Any] = {
            "owner": class_full, "name": name, "type": element, "collection": collection,
        }
        if kind == "relationship":
            kw_text = _keyword_text(member, source)
            m = re.search(r"Cardinality\s*=\s*(\w+)", kw_text)
            if m:
                metadata["cardinality"] = m.group(1)
            m = re.search(r"Inverse\s*=\s*(\w+)", kw_text)
            if m:
                metadata["inverse"] = m.group(1)
        member_nid = add_node(
            _make_id(class_nid, kind, name), name, member, kind=kind, metadata=metadata,
        )
        add_edge(class_nid, member_nid, "contains", member)
        self_members[name] = member_nid
        if element and not element.startswith("%"):
            add_edge(member_nid, class_ref(element, member), "references", member, context="field")

    def _member_parameter(member: Node) -> None:
        name_node = _child(member, "parameter_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        value_node = _child(member, "default_argument_value")
        raw = _read_text(value_node, source).strip() if value_node is not None else ""
        if raw.startswith("="):
            raw = raw[1:].strip()
        if len(raw) >= 2 and raw[0] == raw[-1] == '"':
            raw = raw[1:-1]
        param_nid = add_node(
            _make_id(class_nid, "parameter", name), name, member, kind="parameter",
            metadata={"owner": class_full, "name": name, "value": raw[:200]},
        )
        add_edge(class_nid, param_nid, "contains", member)
        self_params[name] = param_nid
        if _CLASS_TOKEN_FULL_RE.match(raw):
            add_edge(
                param_nid, class_ref(raw, member), "references", member, confidence="INFERRED",
                context="value",
            )

    def _member_xdata(member: Node) -> None:
        name_node = _child(member, "xdata_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        mimetype = None
        kw_container = _child(member, "xdata_keywords")
        if kw_container is not None:
            mt_node = _find_descendant(kw_container, "xdata_keyword_mimetype", max_depth=2)
            if mt_node is not None:
                tn = _child(mt_node, "typename")
                if tn is not None:
                    mimetype = _read_text(tn, source)
        xdata_nid = add_node(
            _make_id(class_nid, "xdata", name), name, member, kind="xdata",
            metadata={"owner": class_full, "name": name, "mimetype": mimetype},
        )
        add_edge(class_nid, xdata_nid, "contains", member)
        body = _child(member, "external_method_body_content")
        scan_xdata(xdata_nid, body)

    def _member_index(member: Node) -> None:
        name_node = _child(member, "index_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        properties = []
        for ipv in _children(member, "index_property_value"):
            pn = _child(ipv, "property_name")
            if pn is not None:
                properties.append(_ident_text(pn, source))
        index_nid = add_node(
            _make_id(class_nid, "index", name), name, member, kind="index",
            metadata={"owner": class_full, "name": name, "properties": properties},
        )
        add_edge(class_nid, index_nid, "contains", member)

    def _member_foreignkey(member: Node) -> None:
        name_node = _child(member, "foreignkey_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        properties = [_ident_text(pn, source) for pn in _children(member, "property_name")]
        target_cn = _child(member, "class_name")
        idx_node = _child(member, "index_name")
        metadata: dict[str, Any] = {"owner": class_full, "name": name, "properties": properties}
        if idx_node is not None:
            metadata["index"] = _ident_text(idx_node, source)
        fk_nid = add_node(
            _make_id(class_nid, "foreignkey", name), name, member, kind="foreignkey", metadata=metadata,
        )
        add_edge(class_nid, fk_nid, "contains", member)
        if target_cn is not None:
            target_full = _canonical_class(_ident_text(target_cn, source))
            metadata["references"] = target_full
            add_edge(fk_nid, class_ref(target_full, target_cn), "references", member, context="field")

    def _member_query(member: Node) -> None:
        name_node = _child(member, "query_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        arguments = _child(member, "arguments")
        arity = len(_children(arguments, "argument")) if arguments is not None else 0
        kw_text = _keyword_text(member, source)
        m = re.search(r"\b(SqlProc|Sql|Class)\b", kw_text, re.I)
        query_type = m.group(1) if m else None
        query_nid = add_node(
            _make_id(class_nid, "query", name), name, member, kind="query",
            metadata={"owner": class_full, "name": name, "arity": arity, "query_type": query_type},
        )
        add_edge(class_nid, query_nid, "contains", member)

    def _member_trigger(member: Node) -> None:
        name_node = _child(member, "trigger_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        trigger_nid = add_node(
            _make_id(class_nid, "trigger", name), name, member, kind="trigger",
            callable_node=True, metadata={"owner": class_full, "name": name},
        )
        add_edge(class_nid, trigger_nid, "contains", member)
        container = _child(member, "method_definition") or member
        body_stmts = _children(container, "statement")
        for err in (c for c in container.children if c.type == "ERROR"):
            body_stmts.extend(_children(err, "statement"))
        if body_stmts:
            bodies.append((body_stmts, trigger_nid, "trigger", name))

    def _member_projection(member: Node) -> None:
        name_node = _child(member, "projection_name")
        if name_node is None:
            return
        name = _ident_text(name_node, source)
        return_type = _child(member, "return_type")
        typename = _child(return_type, "typename") if return_type is not None else None
        element, _coll = _typename_class(typename, source)
        proj_nid = add_node(
            _make_id(class_nid, "projection", name), name, member, kind="projection",
            metadata={"owner": class_full, "name": name},
        )
        add_edge(class_nid, proj_nid, "contains", member)
        if element and not element.startswith("%"):
            add_edge(proj_nid, class_ref(element, member), "references", member, context="type")

    def dispatch_class_statement(cs: Node) -> None:
        member = next((c for c in cs.children if c.type in _UDL_MEMBER_KINDS), None)
        if member is not None:
            process_member(member, member.type)

    def collect_class_statements(node: Node, depth: int = 0) -> list[Node]:
        # A single malformed member can make the parser fold the WHOLE class
        # body (and any valid members before/after it) into an ERROR node that
        # is a direct child of `class_definition` rather than of `class_body`
        # (garbage after the closing brace is the common trigger). Recurse
        # into `class_body`/ERROR at any depth (bounded) so real members
        # never go missing just because a sibling was broken.
        stmts: list[Node] = []
        if depth > 6:
            return stmts
        for c in node.children:
            if c.type == "class_statement":
                stmts.append(c)
            elif c.type in ("class_body", "ERROR"):
                stmts.extend(collect_class_statements(c, depth + 1))
        return stmts

    def process_class(cdef: Node) -> None:
        nonlocal class_full, own_pkg, class_nid
        name_node = _child(cdef, "class_name")
        if name_node is None:
            return
        name_text = _ident_text(name_node, source)
        # tree-sitter-objectscript 1.9.22 cannot parse a delimited class-name
        # segment (`Class Demo."My Class"`): it emits only the unquoted
        # prefix as `class_name` and folds the rest into a sibling ERROR
        # node immediately following it. Fold that raw text back in so the
        # class is at least identified by its real name instead of a
        # silently truncated/wrong one.
        siblings = cdef.children
        name_idx = next((i for i, c in enumerate(siblings) if c is name_node), None)
        if name_idx is not None and name_idx + 1 < len(siblings):
            nxt = siblings[name_idx + 1]
            if nxt.type == "ERROR" and nxt.start_byte == name_node.end_byte:
                name_text = source[name_node.start_byte:nxt.end_byte].decode("utf-8", "replace")
        full = _canonical_class(name_text)
        class_full = full
        own_pkg = _package(full)
        extends_list: list[str] = []
        keywords: dict[str, Any] = {}
        class_nid = add_node(
            _make_id(stem, full), _short_name(full), cdef, kind="class",
            metadata={
                "full_name": full, "name": _short_name(full), "package": own_pkg,
                "extends": extends_list, "includes": includes, "imports": imports,
                "keywords": keywords,
            },
        )
        add_edge(file_id, class_nid, "contains", cdef)

        ext = _child(cdef, "class_extends")
        if ext is not None:
            for cn in _children(ext, "class_name"):
                parent_full = _canonical_class(_ident_text(cn, source))
                add_edge(class_nid, class_ref(parent_full, cn), "inherits", ext)
                extends_list.append(parent_full)

        for kw in cdef.children:
            if kw.type != "class_keyword":
                continue
            kw_text = _read_text(kw, source)
            kw_name = kw_text.split("=", 1)[0].strip()
            if kw_name:
                keywords[kw_name] = True
            # A keyword value can be a parenthesized list (e.g.
            # `DependsOn = (Demo.A, Demo.B)`), which parses as multiple
            # `class_name` children of the same `class_keyword` node -- emit a
            # reference for every one of them, not just the first.
            for kw_class_name in _children(kw, "class_name"):
                target_full = _canonical_class(_ident_text(kw_class_name, source))
                add_edge(
                    class_nid, class_ref(target_full, kw_class_name), "references", kw,
                    context="attribute", metadata={"keyword": kw_name},
                )

        for cs in collect_class_statements(cdef):
            dispatch_class_statement(cs)

    def process_top_level(child: Node) -> None:
        if child.type in ("include_code", "include_generator"):
            for cn in _children(child, "class_name"):
                name = _ident_text(cn, source)
                add_edge(file_id, include_stub(name, child), "includes", child)
                includes.append(name)
        elif child.type == "import_code":
            for cn in _children(child, "class_name"):
                imports.append(_ident_text(cn, source))
        elif child.type == "class_definition":
            process_class(child)

    def walk_udl() -> None:
        for child in root.children:
            if child.type == "ERROR":
                for gc in child.children:
                    process_top_level(gc)
            else:
                process_top_level(child)

    # ---- Routine/include walk --------------------------------------------

    def label_node(
        tag: str, node: Node, container_nid: str, *, kind_: str, arity: int, has_params: bool,
        visibility: str, methodimpl: bool,
    ) -> str:
        nid = _make_id(stem, "label", tag)
        if nid in seen_ids:
            existing = next((n for n in nodes if n["id"] == nid), None)
            if existing is not None and existing["label"] != f"{tag}()":
                nid = _make_id(stem, "label", tag, _line(node))
        add_node(
            nid, f"{tag}()", node, kind=kind_, callable_node=True,
            metadata={
                "routine": rname, "name": tag, "arity": arity, "has_params": has_params,
                "visibility": visibility, "methodimpl": methodimpl,
            },
        )
        add_edge(container_nid, nid, "contains", node)
        self_labels.setdefault(tag, nid)
        return nid

    def walk_routine(is_include: bool) -> None:
        nonlocal rname
        first = next((c for c in root.children if c.type not in _COMMENT_TYPES), None)
        if first is not None and first.type == "routine_definition":
            rn = _child(first, "routine_name")
            resolved_name = _ident_text(rn, source) if rn is not None else path.stem
        elif first is not None and first.type == "compiled_header":
            # The `Name^INC^^^0` line is the third line of a `%RO` export (after
            # the `^INC^...` banner and the `%RO` line), so search the head
            # rather than anchoring at byte 0.
            m = _COMPILED_HEADER_NAME_RE.search(source[:2048])
            resolved_name = m.group(1).decode("utf-8", "replace") if m else path.stem
        else:
            resolved_name = path.stem
        rname = resolved_name

        kind = "include" if is_include else "routine"
        rnid = add_node(
            _make_id(stem, kind, resolved_name), resolved_name, root, kind=kind,
            metadata={"routine": rname, "includes": includes, "imports": imports, "generated": False},
        )
        add_edge(file_id, rnid, "contains", root)
        current = rnid

        for st in _iter_statements(root):
            inner = next((c for c in st.children if c.type not in _COMMENT_TYPES), None)
            if inner is None:
                continue
            if inner.type == "tag_statement":
                tag_node = _child(inner, "tag")
                if tag_node is None:
                    continue
                tag = _read_text(tag_node, source)
                params = _child(inner, "parameter_list")
                arity = len(_children(params, "tag_parameter")) if params is not None else 0
                visibility = "private" if _find_descendant(inner, "keyword_private", 2) else "public"
                current = label_node(
                    tag, inner, rnid, kind_="label", arity=arity, has_params=arity > 0,
                    visibility=visibility, methodimpl=False,
                )
            elif inner.type == "procedure":
                tag_node = _child(inner, "tag")
                if tag_node is None:
                    continue
                tag = _read_text(tag_node, source)
                params = _child(inner, "parameter_list")
                arity = len(_children(params, "tag_parameter")) if params is not None else 0
                visibility = "public" if _find_descendant(inner, "keyword_public", 2) else "private"
                proc_nid = label_node(
                    tag, inner, rnid, kind_="procedure", arity=arity, has_params=arity > 0,
                    visibility=visibility, methodimpl=False,
                )
                for pst in _iter_statements(inner):
                    pinner = next((c for c in pst.children if c.type not in _COMMENT_TYPES), None)
                    if pinner is None:
                        continue
                    if pinner.type == "tag_statement":
                        ptag_node = _child(pinner, "tag")
                        if ptag_node is None:
                            continue
                        ptag = _read_text(ptag_node, source)
                        label_node(
                            ptag, pinner, proc_nid, kind_="label", arity=0, has_params=False,
                            visibility="public", methodimpl=False,
                        )
                    else:
                        pending.append((pinner, proc_nid))
                current = rnid
            elif inner.type == "pound_include":
                cn = _child(inner, "class_name")
                if cn is not None:
                    name = _ident_text(cn, source)
                    add_edge(file_id, include_stub(name, inner), "includes", inner)
                    includes.append(name)
            elif inner.type == "pound_import":
                cn = _child(inner, "class_name")
                if cn is not None:
                    imports.append(_ident_text(cn, source))
            elif inner.type == "pound_define":
                name_node = _child(inner, "macro_def")
                if name_node is None:
                    continue
                name = _ident_text(name_node, source)
                has_args = _child(inner, "pound_define_variable_args") is not None
                macro_nid = add_node(
                    _make_id(stem, "macro", name), f"$$${name}", inner, kind="macro",
                    metadata={"routine": rname, "name": name, "has_args": has_args},
                )
                add_edge(rnid, macro_nid, "contains", inner)
                self_macros[name] = macro_nid
                value_node = _child(inner, "macro_value")
                if value_node is not None:
                    pending.append((value_node, rnid))
            else:
                pending.append((inner, current))

    # ---- Pass 2: body walk -------------------------------------------------

    def dispatch_call_node(n: Node, caller_nid: str, method_names_by_nid: dict[str, str]) -> None:
        if n.type == "class_method_call":
            class_ref_node = _child(n, "class_ref")
            class_name_node = _child(class_ref_node, "class_name") if class_ref_node is not None else None
            method_name_node = _child(n, "method_name")
            if class_name_node is None or method_name_node is None:
                return
            on_class_call(
                caller_nid, _ident_text(class_name_node, source), _ident_text(method_name_node, source), n
            )
        elif n.type == "oref_chain_expr":
            head = n.children[0] if n.children else None
            if head is None or head.type != "class_ref":
                return
            class_name_node = _child(head, "class_name")
            if class_name_node is None:
                return
            cls_name = _ident_text(class_name_node, source)
            segment = _child(n, "oref_chain_segment")
            if segment is None:
                return
            seg_inner = next(
                (c for c in segment.children if c.type in ("oref_method", "oref_parameter")), None
            )
            if seg_inner is None:
                return
            if seg_inner.type == "oref_method":
                method_name_node = _child(seg_inner, "method_name")
                if method_name_node is None:
                    return
                on_class_call(caller_nid, cls_name, _ident_text(method_name_node, source), n)
            else:
                add_edge(
                    caller_nid, class_ref(cls_name, n), "references", n, confidence="EXTRACTED",
                    context="type",
                )
        elif n.type == "relative_dot_method":
            oref_method = _child(n, "oref_method")
            method_name_node = _child(oref_method, "method_name") if oref_method is not None else None
            if method_name_node is not None:
                on_self_call(caller_nid, _ident_text(method_name_node, source), n)
        elif n.type == "relative_dot_property":
            oref_property = _child(n, "oref_property")
            name_node = _child(oref_property, "property_name") if oref_property is not None else None
            if name_node is not None:
                name = _ident_text(name_node, source)
                if name in self_members:
                    add_edge(caller_nid, self_members[name], "uses", n)
        elif n.type == "relative_dot_parameter":
            oref_parameter = _child(n, "oref_parameter")
            name_node = _child(oref_parameter, "parameter_name") if oref_parameter is not None else None
            if name_node is not None:
                name = _ident_text(name_node, source)
                if name in self_params:
                    add_edge(caller_nid, self_params[name], "uses", n)
        elif n.type == "superclass_method_call":
            name = method_names_by_nid.get(caller_nid)
            if name is not None:
                add_raw_call(
                    caller_nid=caller_nid, callee=name, owner=class_full, via_super=True,
                    kind="self_call", source_location=_line(n),
                )
        elif n.type in ("extrinsic_function", "routine_tag_call", "goto_argument"):
            on_line_ref(caller_nid, n)
        elif n.type == "system_defined_function":
            head_text = _read_text(n, source).split("(", 1)[0].strip().lower()
            if head_text in _DOLLAR_CLASS_FUNCS:
                arg_nodes = _children(n, "method_arg")
                strings: list[str] = []
                for arg in arg_nodes:
                    sl = _find_descendant(arg, "string_literal", max_depth=3)
                    if sl is not None:
                        strings.append(_ident_text(sl, source))
                if len(strings) >= 2:
                    on_class_call(
                        caller_nid, strings[0], strings[1], n, confidence="INFERRED",
                        context="dynamic_call",
                    )
        elif n.type in ("macro_constant", "macro_function", "command_macro"):
            text = _read_text(n, source)
            if text.startswith("$$$"):
                text = text[3:]
            name = text.split("(", 1)[0]
            on_macro_use(caller_nid, name, n)
        elif n.type in _POUND_IF_LEAF_TYPES:
            scan_pound_if_leaf(caller_nid, n)

    def walk_bodies() -> None:
        method_names_by_nid = {nid: name for name, nid in self_methods.items()}
        entries: list[tuple[list[Node], str]] = []
        for body, caller_nid, *_rest in bodies:
            entries.append((body, caller_nid))
        for stmt, caller_nid in pending:
            entries.append(([stmt], caller_nid))
        for roots, caller_nid in entries:
            stack = list(reversed(roots))
            while stack:
                n = stack.pop()
                dispatch_call_node(n, caller_nid, method_names_by_nid)
                stack.extend(reversed(n.children))

    # ---- main ---------------------------------------------------------

    add_node(file_id, path.name, root, kind="file")
    if is_udl:
        walk_udl()
    else:
        walk_routine(is_include)
    walk_bodies()

    clean_edges = [e for e in edges if e["source"] in seen_ids and e["target"] in seen_ids]
    result: dict[str, Any] = {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
    if root.has_error:
        result["parse_errors"] = {
            "first_error_line": _first_parse_error_line(root),
            "multiline_error": _has_multiline_error(root),
        }
    return result


# --------------------------------------------------------------------------
# Cross-file resolution
# --------------------------------------------------------------------------


def resolve_objectscript_calls(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    classes: dict[str, list[str]] = {}
    class_meta: dict[str, tuple[str, list[str], str]] = {}
    methods: dict[tuple[str, str], list[str]] = {}
    routines: dict[str, list[str]] = {}
    labels: dict[tuple[str, str], list[str]] = {}
    macros: dict[str, list[tuple[str, str]]] = {}
    class_stubs: list[dict] = []
    include_stubs: list[dict] = []

    for node in all_nodes:
        metadata = node.get("metadata")
        if not isinstance(metadata, dict) or metadata.get("language") != _LANG:
            continue
        kind = metadata.get("kind")
        has_source = bool(node.get("source_file"))
        if kind == "class":
            full = metadata.get("full_name")
            if isinstance(full, str):
                classes.setdefault(full, []).append(node["id"])
                class_meta[node["id"]] = (
                    full, list(metadata.get("extends") or []), metadata.get("package", "")
                )
        elif kind == "external_class" and not has_source:
            class_stubs.append(node)
        elif kind in ("include", "routine"):
            rname_ = metadata.get("routine")
            if isinstance(rname_, str):
                routines.setdefault(rname_, []).append(node["id"])
        elif kind == "external_include" and not has_source:
            include_stubs.append(node)
        elif kind in _METHOD_KINDS:
            owner = metadata.get("owner")
            name = metadata.get("name")
            if isinstance(owner, str) and isinstance(name, str):
                methods.setdefault((owner, name), []).append(node["id"])
        elif kind in ("label", "procedure"):
            rname_ = metadata.get("routine")
            name = metadata.get("name")
            if isinstance(rname_, str) and isinstance(name, str):
                labels.setdefault((rname_, name), []).append(node["id"])
        elif kind == "macro":
            rname_ = metadata.get("routine")
            name = metadata.get("name")
            if isinstance(rname_, str) and isinstance(name, str):
                macros.setdefault(name, []).append((rname_, node["id"]))

    existing: set[tuple[Any, Any, Any]] = {
        (e.get("source"), e.get("target"), e.get("relation")) for e in all_edges
    }

    def ancestors(full: str) -> list[str]:
        defs = classes.get(full, [])
        if len(defs) != 1:
            return []
        result: list[str] = []
        visited: set[str] = {full}
        queue = list(class_meta.get(defs[0], (full, [], ""))[1])
        while queue and len(visited) < 64:
            parent = queue.pop(0)
            if parent in visited:
                continue
            visited.add(parent)
            result.append(parent)
            parent_defs = classes.get(parent, [])
            if len(parent_defs) == 1:
                queue.extend(class_meta.get(parent_defs[0], (parent, [], ""))[1])
        return result

    # Step 1: stub retargeting.
    remap: dict[str, str] = {}
    for stub in class_stubs:
        full = stub["metadata"].get("full_name")
        alts = stub["metadata"].get("alternatives", [])
        target = None
        for candidate_full in [full, *alts]:
            defs = classes.get(candidate_full, [])
            if len(defs) == 1:
                target = defs[0]
                break
        if target is not None:
            remap[stub["id"]] = target
    for stub in include_stubs:
        name = stub["metadata"].get("routine")
        defs = routines.get(name, [])
        if len(defs) == 1:
            remap[stub["id"]] = defs[0]

    if remap:
        for e in all_edges:
            if e.get("source") in remap:
                e["source"] = remap[e["source"]]
            if e.get("target") in remap:
                e["target"] = remap[e["target"]]
        seen: set[tuple[Any, Any, Any]] = set()
        deduped: list[dict] = []
        for e in all_edges:
            src, tgt, rel = e.get("source"), e.get("target"), e.get("relation")
            if not src or not tgt or src == tgt:
                continue
            key = (src, tgt, rel)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(e)
        all_edges[:] = deduped
        all_nodes[:] = [n for n in all_nodes if n["id"] not in remap]
        existing = {(e.get("source"), e.get("target"), e.get("relation")) for e in all_edges}

    # (src, tgt, rel) -> the edge dict `emit()` appended for it, so a later,
    # stronger-confidence duplicate for the same key (e.g. an inherited
    # `..M()` self_call resolved at INFERRED and a qualified `##class(X).M()`
    # class_call resolved at EXTRACTED for the identical caller/callee pair)
    # can upgrade it in place instead of being silently dropped by whichever
    # raw call happened to be processed first. Only edges *we* emitted here
    # are tracked -- an edge already present from pass-1 extraction is never
    # touched.
    emitted_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}

    def emit(
        src: str | None, tgt: str | None, rel: str, conf: str, ctx: str | None,
        source_file: str, source_location: Any,
    ) -> None:
        if not src or not tgt or src == tgt:
            return
        key = (src, tgt, rel)
        if key in existing:
            prior = emitted_by_key.get(key)
            if prior is not None and conf == "EXTRACTED" and prior["confidence"] != "EXTRACTED":
                prior["confidence"] = conf
                prior["confidence_score"] = 1.0
                prior["context"] = ctx
                prior["source_file"] = source_file
                prior["source_location"] = source_location
            return
        existing.add(key)
        edge: dict[str, Any] = {
            "source": src, "target": tgt, "relation": rel, "context": ctx,
            "confidence": conf, "confidence_score": 1.0 if conf == "EXTRACTED" else 0.85,
            "source_file": source_file, "source_location": source_location, "weight": 1.0,
        }
        all_edges.append(edge)
        emitted_by_key[key] = edge

    def _s(value: Any) -> str:
        return value if isinstance(value, str) else ""

    # Step 2: raw call resolution.
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for call in result.get("raw_calls", []):
            if not isinstance(call, dict) or call.get("language") != _LANG:
                continue
            kind = call.get("kind")
            caller: Any = call.get("caller_nid")
            caller = remap.get(caller, caller)
            source_file = call.get("source_file", "")
            source_location = call.get("source_location")
            if kind == "class_call":
                cands = [_s(call.get("target_class")), *[_s(a) for a in call.get("alternatives", [])]]
                target_class = None
                for c in cands:
                    if c and len(classes.get(c, [])) == 1:
                        target_class = c
                        break
                callee = _s(call.get("callee"))
                conf = call.get("confidence", "EXTRACTED")
                ctx = call.get("context", "class_method_call")
                if target_class is not None:
                    direct = methods.get((target_class, callee), [])
                    if len(direct) == 1:
                        emit(caller, direct[0], "calls", conf, ctx, source_file, source_location)
                        continue
                    for anc in ancestors(target_class):
                        anc_methods = methods.get((anc, callee), [])
                        if len(anc_methods) == 1:
                            emit(
                                caller, anc_methods[0], "calls", "INFERRED", "inherited_call",
                                source_file, source_location,
                            )
                            break
            elif kind == "self_call":
                owner = _s(call.get("owner"))
                callee = _s(call.get("callee"))
                if not owner or not callee:
                    continue
                ctx = "super_call" if call.get("via_super") else "inherited_call"
                for anc in ancestors(owner):
                    anc_methods = methods.get((anc, callee), [])
                    if len(anc_methods) == 1:
                        emit(caller, anc_methods[0], "calls", "INFERRED", ctx, source_file, source_location)
                        break
            elif kind == "routine_call":
                routine = _s(call.get("routine"))
                label_val = call.get("label")
                if label_val is not None:
                    targets = labels.get((routine, _s(label_val)), [])
                else:
                    targets = routines.get(routine, [])
                if len(targets) == 1:
                    emit(
                        caller, targets[0], "calls", "EXTRACTED", "routine_call", source_file,
                        source_location,
                    )
            elif kind == "macro_use":
                name = _s(call.get("callee"))
                caller_includes = call.get("includes") or []
                scoped = [nid for rname_, nid in macros.get(name, []) if rname_ in caller_includes]
                target = None
                if len(scoped) == 1:
                    target = scoped[0]
                else:
                    global_defs = macros.get(name, [])
                    if len(global_defs) == 1:
                        target = global_defs[0][1]
                if target is not None:
                    emit(caller, target, "uses", "INFERRED", "macro", source_file, source_location)
