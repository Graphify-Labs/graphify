"""JavaServer Pages extractor (.jsp, .jspf, .jspx).

A JSP is markup carrying directives, standard actions and Java scriptlets, so no
single grammar reads it. This extractor is regex-based, like the Razor and Blade
template extractors, and recovers only the structure a JSP states explicitly:

- ``<%@ page import="a.b.C, d.e.F" %>`` / ``<jsp:directive.page import=.../>``
  -> ``imports`` edges to the imported class (wildcards produce no edge).
- ``<%@ include file=... %>`` / ``<jsp:directive.include file=.../>`` (static)
  and ``<jsp:include page=.../>`` (dynamic) -> ``includes`` edges.
- ``<jsp:forward page=.../>`` -> ``references`` edge.
- ``<%@ taglib prefix=... uri=|tagdir=... %>`` -> ``imports`` edge to a stub.
- ``<jsp:useBean class=|type=|beanName=.../>`` -> ``references`` edges.
- Java methods declared in ``<%! ... %>`` / ``<jsp:declaration>`` -> ``contains``.

JSP comments (``<%-- --%>``, and XML comments in a ``.jspx`` document) are
blanked before anything is matched, so commented-out directives produce nothing.
Blanking is length- and newline-preserving, so every match offset maps to its
real line.

Not read (no edge rather than a guessed one): scriptlet/expression bodies and EL,
custom-tag usages, ``xmlns:`` taglib declarations in a JSP document, any
attribute value computed at request time (``<%= %>``, ``${}``, ``#{}``), and
wildcard imports.
"""
from __future__ import annotations

import os
import posixpath
import re
from bisect import bisect_right
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_source_text
from graphify.security import sanitize_metadata

_JSP_COMMENT_RE = re.compile(r"<%--.*?--%>", re.DOTALL)
# In a JSP document (XML syntax) an XML comment is discarded by the container,
# so an action inside it never runs. In classic syntax `<!-- -->` is template
# text sent to the client and the JSP elements inside it still execute, so it is
# only blanked for `.jspx`.
_XML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
# Scripting elements: `<% %>`, `<%= %>`, `<%! %>` (never a `<%@` directive) and
# their XML spellings. Their bodies are Java, so a `<jsp:include ...>` written in
# a Java string is not an action; the bodies are blanked before directives and
# actions are matched, keeping the delimiters so a request-time attribute value
# (`page="<%= x %>"`) is still recognised as one.
_SCRIPTING_RE = re.compile(r"(<%(?!@)[=!]?)(.*?)(%>)", re.DOTALL)
_XML_SCRIPTING_RE = re.compile(
    r"(<jsp:(scriptlet|expression|declaration)\s*>)(.*?)(</jsp:\2\s*>)", re.DOTALL
)

# `<%@ name attr="v" ... %>`; quoted values may contain `%>` or newlines.
_DIRECTIVE_RE = re.compile(
    r"""<%@\s*([A-Za-z]+)((?:[^%"']|%(?!>)|"[^"]*"|'[^']*')*)%>"""
)
# XML-syntax directives and the standard actions this extractor reads. The body
# skips over quoted values so a `>` inside one does not end the tag. (A JSP
# document has no taglib directive element; it declares tag libraries with
# `xmlns:prefix="uri"`, which is not read, see the module docstring.)
_JSP_TAG_RE = re.compile(
    r"""<jsp:(directive\.page|directive\.include|include|forward|useBean)"""
    r"""(?=[\s/>])((?:[^>"']|"[^"]*"|'[^']*')*)>"""
)
_ATTR_RE = re.compile(r"""([A-Za-z_][\w:.-]*)\s*=\s*(?:"([^"]*)"|'([^']*)')""")

_DECL_CLASSIC_RE = re.compile(r"<%!(.*?)%>", re.DOTALL)
_DECL_XML_RE = re.compile(r"<jsp:declaration\s*>(.*?)</jsp:declaration\s*>", re.DOTALL)
_CDATA_MARK_RE = re.compile(r"<!\[CDATA\[|\]\]>")
_XML_ENTITY_RE = re.compile(r"&(lt|gt|amp|quot|apos);")
_XML_ENTITY_CHARS = {"lt": "<", "gt": ">", "amp": "&", "quot": '"', "apos": "'"}

_JAVA_QUALIFIED_NAME_RE = re.compile(r"[A-Za-z_$][\w$]*(?:\.[A-Za-z_$][\w$]*)*")

# A member method header at brace depth 0 of a declaration block: optional
# annotations and modifiers, optional type parameters, a return type, the name,
# the parameter list, an optional throws clause, then the opening brace.
_METHOD_RE = re.compile(
    r"(?:^|(?<=[;{}]))\s*"
    r"(?:@[\w$.]+(?:\s*\([^)]*\))?\s*)*"
    r"(?:(?:public|protected|private|static|final|synchronized|abstract|native|strictfp)\s+)*"
    r"(?:<[^;{}()]*>\s*)?"
    r"([\w$.]+(?:\s*<[^;{}()]*>)?(?:\s*\[\s*\])*)\s+"
    r"([A-Za-z_$][\w$]*)\s*\((?:[^()]|\([^()]*\))*\)\s*"
    r"(?:throws\s+[\w$.,\s]+)?\{"
)
_JAVA_KEYWORDS = frozenset({
    "abstract", "assert", "boolean", "break", "byte", "case", "catch", "char",
    "class", "const", "continue", "default", "do", "double", "else", "enum",
    "extends", "final", "finally", "float", "for", "goto", "if", "implements",
    "import", "instanceof", "int", "interface", "long", "native", "new",
    "package", "private", "protected", "public", "return", "short", "static",
    "strictfp", "super", "switch", "synchronized", "this", "throw", "throws",
    "transient", "try", "void", "volatile", "while",
})
_NON_TYPE_KEYWORDS = _JAVA_KEYWORDS - {
    "boolean", "byte", "char", "double", "float", "int", "long", "short", "void",
}

# Runtime-expression markers: a value carrying one is computed per request, so
# the target is unknowable statically and no edge is emitted (fail-closed).
_EXPRESSION_MARKERS = ("<%=", "${", "#{")


def _blank(text: str) -> str:
    """Spaces for every character except line breaks (offset/line preserving)."""
    return re.sub(r"[^\n]", " ", text)


def _blank_matches(src: str, pattern: re.Pattern[str]) -> str:
    return pattern.sub(lambda m: _blank(m.group(0)), src)


def _unescape_xml_preserving(text: str) -> str:
    """Decode the five predefined XML entities, padding to keep every offset."""
    def _sub(m: re.Match[str]) -> str:
        return _XML_ENTITY_CHARS[m.group(1)] + " " * (len(m.group(0)) - 1)
    return _XML_ENTITY_RE.sub(_sub, text)


def _java_member_level(code: str) -> str:
    """Blank everything except brace-depth-0 Java code (offset preserving).

    String/char literals and comments are blanked at every depth, and the body
    of each top-level brace block is blanked while its own ``{``/``}`` are kept,
    so a member-header regex can only match class-member declarations, never an
    ``if (...) {`` inside a method body.
    """
    out = list(code)
    n = len(code)
    depth = 0
    i = 0
    while i < n:
        c = code[i]
        nxt = code[i + 1] if i + 1 < n else ""
        if c == "/" and nxt == "/":
            j = code.find("\n", i)
            j = n if j < 0 else j
            for p in range(i, j):
                out[p] = " "
            i = j
            continue
        if c == "/" and nxt == "*":
            j = code.find("*/", i + 2)
            j = n if j < 0 else j + 2
            for p in range(i, j):
                if code[p] != "\n":
                    out[p] = " "
            i = j
            continue
        if c in ('"', "'"):
            j = i + 1
            while j < n and code[j] != c and code[j] != "\n":
                j += 2 if code[j] == "\\" else 1
            j = min(j + 1, n)
            for p in range(i, j):
                if code[p] != "\n":
                    out[p] = " "
            i = j
            continue
        if c == "{":
            if depth > 0:
                out[i] = " "
            depth += 1
        elif c == "}":
            depth = max(depth - 1, 0)
            if depth > 0:
                out[i] = " "
        elif depth > 0 and c != "\n":
            out[i] = " "
        i += 1
    return "".join(out)


def _context_root(directory: Path) -> Path | None:
    """Nearest ancestor (inclusive) that holds a ``WEB-INF`` directory."""
    for candidate in (directory, *directory.parents):
        try:
            if (candidate / "WEB-INF").is_dir():
                return candidate
        except OSError:
            continue
    return None


def _resolve_page_path(path: Path, raw: str) -> Path | None:
    """Resolve an include/forward path the way a servlet container would.

    A relative path resolves against the including page's directory. A path
    starting with ``/`` is relative to the web-application context root: the
    nearest ancestor that holds ``WEB-INF`` (the servlet-spec marker) when there
    is one, otherwise the nearest ancestor ``D`` where ``D/<path>`` is a file.
    A query string or fragment is not part of the file name. Returns ``None``
    when nothing on disk matches, or when a context-relative path climbs out of
    its root.
    """
    clean = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not clean:
        return None
    if not clean.startswith("/"):
        candidate = Path(os.path.normpath(path.parent / clean))
        try:
            return candidate if candidate.is_file() else None
        except OSError:
            return None
    rel = posixpath.normpath(clean.lstrip("/"))
    if rel in (".", "") or rel == ".." or rel.startswith("../"):
        return None
    root = _context_root(path.parent)
    search = (root,) if root is not None else (path.parent, *path.parent.parents)
    for directory in search:
        candidate = Path(os.path.normpath(directory / rel))
        try:
            if candidate.is_file():
                return candidate
        except OSError:
            continue
    return None


def _is_expression(value: str) -> bool:
    # `%= expr %` is the JSP-document (XML syntax) spelling of a request-time
    # attribute value, the counterpart of `<%= expr %>` in classic syntax.
    return value.strip().startswith("%=") or any(m in value for m in _EXPRESSION_MARKERS)


def extract_jsp(path: Path) -> dict:
    """Extract imports, includes, forwards, taglibs, beans and declared methods from a JSP."""
    try:
        raw_src = _read_source_text(path)
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    is_xml_document = path.suffix.lower() == ".jspx"
    # `src`: comments blanked (declarations are read from it).
    # `markup`: scripting bodies blanked too (directives and actions are read
    # from it). Every blanking keeps offsets, so both map to the same lines.
    src = _blank_matches(raw_src, _JSP_COMMENT_RE)
    if is_xml_document:
        src = _blank_matches(src, _XML_COMMENT_RE)
    markup = _SCRIPTING_RE.sub(lambda m: m.group(1) + _blank(m.group(2)) + m.group(3), src)
    markup = _XML_SCRIPTING_RE.sub(
        lambda m: m.group(1) + _blank(m.group(3)) + m.group(4), markup
    )

    line_starts = [0] + [m.end() for m in re.finditer("\n", src)]

    def _line(offset: int) -> int:
        return bisect_right(line_starts, offset)

    str_path = str(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()

    def _add_edge(target: str, relation: str, line: int, *, context: str | None = None,
                  metadata: dict | None = None, target_file: str | None = None) -> None:
        loc = f"L{line}"
        key = (relation, target, loc)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict = {"source": file_nid, "target": target, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": loc, "weight": 1.0}
        if context:
            edge["context"] = context
        if metadata:
            edge["metadata"] = sanitize_metadata(metadata)
        if target_file:
            # Transient stamp read by the #2169 canonicalization pass in
            # extract(), which repoints the edge at the real file node.
            edge["target_file"] = target_file
        edges.append(edge)

    def _sourceless_stub(label: str, *, file_scoped: bool) -> str:
        """A stub for something defined elsewhere (a class, a tag library).

        ``source_file`` stays empty so the stub never claims to be defined in
        this JSP and a real source-backed node always wins. A file-scoped stub
        (the razor ``@inject`` convention) carries ``origin_file``, which keeps
        it apart from another file's same-named stub. A fully-qualified class
        name or a taglib URI names one global thing, so it carries none and
        every importer shares one node, like the FQN stub
        ``_resolve_java_type_references`` parks external Java imports on.
        """
        nid = _make_id(label)
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            node = {"id": nid, "label": label, "file_type": "code",
                    "source_file": "", "source_location": ""}
            if file_scoped:
                node["origin_file"] = str_path
            nodes.append(node)
        return nid

    def _emit_class_ref(fqn: str, offset: int, relation: str, *, context: str | None,
                        extra: dict) -> None:
        if fqn.endswith(".*") or not _JAVA_QUALIFIED_NAME_RE.fullmatch(fqn):
            return
        prefix, _, simple = fqn.rpartition(".")
        if not simple:
            return
        # The stub is labelled with the FQN, not the simple name. Java's
        # type-reference pass resolves a dotted sourceless stub by exact FQN
        # against the corpus's own classes, and the bare-label rewire never
        # matches a dotted label, so an external `org.acme.Component` cannot
        # collapse onto an unrelated internal `com.example.ui.Component`
        # (#2504). A simple-name stub would be resolved by label alone.
        nid = _sourceless_stub(fqn, file_scoped=not prefix)
        if not nid:
            return
        metadata: dict = {"target_fqn": fqn, **extra}
        if relation == "references":
            metadata["ref_token"] = simple
            if prefix:
                metadata["qualified"] = True
                metadata["ref_qualifier"] = prefix
        _add_edge(nid, relation, _line(offset), context=context, metadata=metadata)

    def _emit_imports(value: str, value_offset: int) -> None:
        for item in re.finditer(r"[^,]+", value):
            fqn = item.group(0).strip()
            if not fqn:
                continue
            # A static import names a member, not a class; skip it rather than
            # guess which segment is the class.
            if fqn.startswith("static ") or fqn.startswith("static\t"):
                continue
            lead = len(item.group(0)) - len(item.group(0).lstrip())
            _emit_class_ref(fqn, value_offset + item.start() + lead, "imports",
                            context="import", extra={})

    def _emit_page_link(raw: str, offset: int, relation: str, metadata: dict) -> None:
        raw = raw.strip()
        if not raw or _is_expression(raw):
            return
        line = _line(offset)
        resolved = _resolve_page_path(path, raw)
        metadata = {**metadata, "raw_path": raw}
        if resolved is not None:
            _add_edge(_make_id(str(resolved)), relation, line, metadata=metadata,
                      target_file=str(resolved))
            return
        # Unresolved: keep the edge on a stub labelled with the raw path, the
        # same shape `_emit_ejs_include` leaves for a template it cannot find.
        nid = _make_id(raw)
        if not nid:
            return
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": raw, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}",
                          "confidence": "EXTRACTED"})
        _add_edge(nid, relation, line, metadata=metadata)

    def _emit_taglib(attrs: dict[str, tuple[str, int]]) -> None:
        prefix = attrs.get("prefix", ("", 0))[0].strip()
        if "uri" in attrs:
            kind, (value, value_offset) = "uri", attrs["uri"]
        elif "tagdir" in attrs:
            kind, (value, value_offset) = "tagdir", attrs["tagdir"]
        else:
            return
        value = value.strip()
        if not value or _is_expression(value):
            return
        # A taglib URI is a global identifier, so every page that names it
        # shares one node. A tagdir is a path inside one web application (two
        # webapps in a corpus can each have /WEB-INF/tags), so its stub is
        # file-scoped. graphify has no directory nodes, so even a tagdir that
        # exists on disk stays a stub rather than a resolved target.
        nid = _sourceless_stub(value, file_scoped=kind == "tagdir")
        if not nid:
            return
        metadata = {"taglib_kind": kind, kind: value}
        if prefix:
            metadata["prefix"] = prefix
        _add_edge(nid, "imports", _line(value_offset), context="import", metadata=metadata)

    def _emit_use_bean(attrs: dict[str, tuple[str, int]]) -> None:
        bean_id = attrs.get("id", ("", 0))[0].strip()
        for attr in ("class", "type", "beanName"):
            if attr not in attrs:
                continue
            value, value_offset = attrs[attr]
            value = value.strip()
            if not value or _is_expression(value):
                continue
            extra: dict = {"bean_attribute": attr}
            if bean_id:
                extra["bean_id"] = bean_id
            _emit_class_ref(value, value_offset, "references", context="field", extra=extra)

    def _attributes(body: str, body_offset: int) -> tuple[dict[str, tuple[str, int]], list[tuple[str, int]]]:
        """(first value per attribute, every ``import`` value) of a tag body.

        ``import`` is the one page-directive attribute the JSP spec lets a page
        repeat, so all of its values are kept. For any other attribute the first
        occurrence wins: a duplicate is a translation error, and picking one
        deterministically is enough.
        """
        attrs: dict[str, tuple[str, int]] = {}
        imports: list[tuple[str, int]] = []
        for am in _ATTR_RE.finditer(body):
            group = 2 if am.group(2) is not None else 3
            value = (am.group(group), body_offset + am.start(group))
            attrs.setdefault(am.group(1), value)
            if am.group(1) == "import":
                imports.append(value)
        return attrs, imports

    # Collect every directive/action first, then emit in source order so edge
    # order does not depend on which syntax a construct was written in.
    occurrences: list[tuple[int, str, dict[str, tuple[str, int]], list[tuple[str, int]]]] = []
    for m in _DIRECTIVE_RE.finditer(markup):
        occurrences.append((m.start(), m.group(1), *_attributes(m.group(2), m.start(2))))
    for m in _JSP_TAG_RE.finditer(markup):
        name = m.group(1)
        kind = name.split(".", 1)[1] if name.startswith("directive.") else "jsp:" + name
        occurrences.append((m.start(), kind, *_attributes(m.group(2), m.start(2))))
    occurrences.sort(key=lambda item: item[0])

    for _offset, kind, attrs, import_values in occurrences:
        if kind == "page":
            for value, value_offset in import_values:
                _emit_imports(value, value_offset)
        elif kind == "include":
            if "file" in attrs:
                value, value_offset = attrs["file"]
                _emit_page_link(value, value_offset, "includes", {"include_kind": "static"})
        elif kind == "taglib":
            _emit_taglib(attrs)
        elif kind == "jsp:include":
            if "page" in attrs:
                value, value_offset = attrs["page"]
                _emit_page_link(value, value_offset, "includes", {"include_kind": "dynamic"})
        elif kind == "jsp:forward":
            if "page" in attrs:
                value, value_offset = attrs["page"]
                _emit_page_link(value, value_offset, "references", {"jsp_action": "forward"})
        elif kind == "jsp:useBean":
            _emit_use_bean(attrs)

    # Declarations compile to members of the generated servlet class.
    blocks: list[tuple[int, str]] = [(m.start(1), m.group(1)) for m in _DECL_CLASSIC_RE.finditer(src)]
    for m in _DECL_XML_RE.finditer(src):
        body = _blank_matches(m.group(1), _CDATA_MARK_RE)
        blocks.append((m.start(1), _unescape_xml_preserving(body)))
    blocks.sort(key=lambda item: item[0])
    stem = _file_stem(path)
    for block_offset, code in blocks:
        flat = _java_member_level(code)
        for mm in _METHOD_RE.finditer(flat):
            return_type = mm.group(1).split("<", 1)[0].strip()
            name = mm.group(2)
            if return_type in _NON_TYPE_KEYWORDS or name in _JAVA_KEYWORDS:
                continue
            method_nid = _make_id(stem, name)
            if not method_nid or method_nid in seen_ids:
                continue
            seen_ids.add(method_nid)
            line = _line(block_offset + mm.start(2))
            nodes.append({"id": method_nid, "label": f".{name}()", "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})
            _add_edge(method_nid, "contains", line)

    return {"nodes": nodes, "edges": edges}
