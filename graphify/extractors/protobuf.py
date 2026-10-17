"""Protocol Buffers extractor for .proto files.

There is no maintained tree-sitter grammar for protobuf on PyPI, and the
pure-Python parsers that exist drop line numbers, so this module carries a
small tokenizer and recursive-descent walker over the parts of the language
that declare structure: ``package``, ``import`` (``public`` / ``weak`` /
``option``), ``message`` (nested, with ``oneof`` / ``map`` / proto2 ``group``),
``enum`` and its values, ``service`` / ``rpc``, ``extend`` and the extension
fields it declares, and edition 2024 ``export`` / ``local`` modifiers. Options
are read where they carry meaning for the graph: code-generation file options,
``deprecated``, ``google.api.http`` bindings on an rpc, and every custom
``(option)`` usage. Reserved ranges, field numbers and other options are
skipped. The walker never raises on malformed input; it skips the statement it
does not understand and keeps going.

Doc comments follow protoc's attachment rule (``SourceCodeInfo``): a comment
block directly above a declaration, with no blank line between, is its leading
comment and becomes a ``rationale`` node.

Type and option names are resolved with protobuf's own scoping rule (innermost
scope first, ``.pkg.Type`` absolute). A name declared in the same file is bound
here; anything else is left on a placeholder target and bound by
:func:`resolve_protobuf_references` once every file in the corpus is extracted.
"""
from __future__ import annotations

import hashlib
import posixpath
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import (
    _file_stem,
    _make_id,
    _read_source_text,
    _shorten_rationale_label,
)

_SCALARS = frozenset({
    "double", "float", "int32", "int64", "uint32", "uint64", "sint32", "sint64",
    "fixed32", "fixed64", "sfixed32", "sfixed64", "bool", "string", "bytes",
})
_LABELS = frozenset({"optional", "required", "repeated"})
# Edition 2024 symbol-visibility modifiers in front of `message` / `enum`.
_VISIBILITY = frozenset({"export", "local"})
# File options that decide how each protoc plugin names the generated code, kept on
# the file node so a consumer-language pass can map generated names back to the
# declarations. ScalaPB's live in an aggregate custom option.
_CODEGEN_OPTIONS = frozenset({
    "java_package", "java_outer_classname", "java_multiple_files", "go_package",
    "csharp_namespace", "objc_class_prefix", "php_namespace", "php_metadata_namespace",
    "ruby_package", "swift_prefix",
})
_SCALAPB_OPTIONS = frozenset({"package_name", "flat_package"})
_HTTP_OPTION = "google.api.http"
_HTTP_METHODS = ("get", "put", "post", "delete", "patch")
_TYPE_KINDS = frozenset({"message", "enum", "group"})

# Edge context prefixes. A reference bound inside the file carries the bare
# context; an unbound one carries "<context>:<scope>:<name>" until the corpus
# resolver binds it. Imports carry "<import context>:<import path>".
_TYPE_CONTEXT = "protobuf_type"
_OPTION_CONTEXT = "protobuf_option"
_IMPORT_CONTEXT = "protobuf_import"
# `import public` re-exports the imported file's declarations to importers.
_PUBLIC_IMPORT_CONTEXT = "protobuf_import_public"

_TOKEN_RE = re.compile(
    r"""
    (?P<ws>[ \t\r\f\v]+)
    | (?P<nl>\n)
    | (?P<line_comment>//[^\n]*)
    | (?P<block_comment>/\*.*?\*/)
    | (?P<string>"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*')
    | (?P<ident>[A-Za-z_][A-Za-z0-9_]*)
    | (?P<number>[0-9][0-9A-Za-z_.+-]*)
    | (?P<punct>.)
    """,
    re.VERBOSE | re.DOTALL,
)

Token = tuple[str, str, int]


class _Comment:
    __slots__ = ("start", "end", "text", "owns_line", "is_block")

    def __init__(self, start: int, end: int, text: str, owns_line: bool, is_block: bool):
        self.start = start
        self.end = end
        self.text = text
        # True when no code precedes the comment on its first line.
        self.owns_line = owns_line
        self.is_block = is_block


def _comment_text(raw: str) -> str:
    if raw.startswith("//"):
        return raw[2:]
    body = raw[2:-2]
    lines = [re.sub(r"^\s*\*?", "", ln) for ln in body.split("\n")]
    return "\n".join(lines)


def _tokenize(text: str) -> tuple[list[Token], list[_Comment]]:
    """Return (kind, value, line) code tokens, and the comments with their lines."""
    tokens: list[Token] = []
    comments: list[_Comment] = []
    line = 1
    last_code_line = 0
    for m in _TOKEN_RE.finditer(text):
        kind = m.lastgroup or "punct"
        value = m.group()
        if kind == "nl":
            line += 1
            continue
        if kind == "ws":
            continue
        if kind in ("line_comment", "block_comment"):
            end = line + value.count("\n")
            comments.append(_Comment(line, end, _comment_text(value), last_code_line != line,
                                     kind == "block_comment"))
            line = end
            continue
        tokens.append((kind, value, line))
        last_code_line = line + value.count("\n")
        line = last_code_line
    return tokens, comments


def _unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return re.sub(r"\\(.)", r"\1", value[1:-1])
    return value


def _parse_int(text: str) -> int | None:
    try:
        sign = -1 if text.startswith("-") else 1
        body = text.lstrip("+-").lower()
        if body.startswith("0x"):
            return sign * int(body, 16)
        if len(body) > 1 and body.startswith("0") and body.isdigit():
            return sign * int(body, 8)
        return sign * int(body)
    except ValueError:
        return None


def _scope_chain(scope: str) -> list[str]:
    """``a.b.C`` -> ``["a.b.C", "a.b", "a", ""]`` (innermost first)."""
    chain = []
    while scope:
        chain.append(scope)
        scope = scope.rpartition(".")[0]
    chain.append("")
    return chain


def _qualify(scope: str, name: str) -> str:
    return f"{scope}.{name}" if scope else name


def _candidate_fqns(name: str, scope: str) -> list[str]:
    if name.startswith("."):
        return [name[1:]]
    return [_qualify(s, name) for s in _scope_chain(scope)]


class _Walker:
    def __init__(self, tokens: list[Token]):
        self.toks = tokens
        self.i = 0

    def peek(self, offset: int = 0) -> Token | None:
        j = self.i + offset
        return self.toks[j] if 0 <= j < len(self.toks) else None

    def value(self, offset: int = 0) -> str | None:
        tok = self.peek(offset)
        return tok[1] if tok else None

    def prev_line(self) -> int:
        """Line of the token just consumed (a declaration's keyword, as protoc reports it)."""
        return self.toks[self.i - 1][2] if 0 < self.i <= len(self.toks) else self.line()

    def line(self) -> int:
        tok = self.peek() or (self.toks[-1] if self.toks else None)
        return tok[2] if tok else 1

    def next(self) -> Token | None:
        tok = self.peek()
        if tok is not None:
            self.i += 1
        return tok

    def accept(self, value: str) -> bool:
        if self.value() == value:
            self.i += 1
            return True
        return False

    def full_ident(self) -> str | None:
        """Read ``.a.b.C`` / ``a.b.C``; returns None (consuming nothing) if absent."""
        start = self.i
        parts = []
        if self.value() == ".":
            parts.append(".")
            self.i += 1
        while True:
            tok = self.peek()
            if tok is None or tok[0] != "ident":
                self.i = start
                return None
            parts.append(tok[1])
            self.i += 1
            if self.value() == "." and (nxt := self.peek(1)) is not None and nxt[0] == "ident":
                parts.append(".")
                self.i += 1
                continue
            return "".join(parts)

    def option_name(self) -> tuple[str, str | None] | None:
        """Read an option name: ``a.b``, ``(x.y)``, ``(x.y).a.b`` or ``a.(x.y)``.

        Returns (written name, custom extension name or None).
        """
        start = self.i
        parts: list[str] = []
        custom: str | None = None
        while True:
            if self.accept("("):
                ext = self.full_ident()
                if ext is None or not self.accept(")"):
                    self.i = start
                    return None
                custom = custom or ext
                parts.append(f"({ext})")
            else:
                ident = self.full_ident()
                if ident is None:
                    self.i = start
                    return None
                parts.append(ident)
            if self.value() == ".":
                self.i += 1
                continue
            return ".".join(parts), custom

    def constant(self) -> Any:
        """Read a scalar option value: adjacent strings, a signed number, true/false or an identifier."""
        tok = self.peek()
        if tok is None:
            return None
        if tok[0] == "string":
            parts = []
            while (t := self.peek()) is not None and t[0] == "string":
                parts.append(_unquote(t[1]))
                self.i += 1
            return "".join(parts)
        if tok[1] in ("-", "+") and (nxt := self.peek(1)) is not None and nxt[0] in ("number", "ident"):
            self.i += 2
            return tok[1] + nxt[1]
        if tok[0] == "number":
            self.i += 1
            return tok[1]
        if tok[0] == "ident":
            self.i += 1
            return {"true": True, "false": False}.get(tok[1], tok[1])
        return None

    def aggregate(self) -> dict[str, Any]:
        """Read a text-format message literal ``{ key: value key2 { ... } }`` into a dict.

        A key that repeats collects its values into a list. The opening '{' or '<'
        is the next token.
        """
        result: dict[str, Any] = {}
        close = {"{": "}", "<": ">"}.get(self.value() or "")
        if close is None:
            return result
        self.i += 1
        while (v := self.value()) is not None and v != close:
            if v in (",", ";"):
                self.i += 1
                continue
            if v == "[":
                # Extension / Any field name: [pkg.ext] or [type.googleapis.com/x.Y]
                depth_start = self.i
                while self.value() not in ("]", None):
                    self.i += 1
                key = "".join(t[1] for t in self.toks[depth_start:self.i + 1])
                self.accept("]")
            else:
                tok = self.next()
                if tok is None or tok[0] != "ident":
                    continue
                key = tok[1]
            self.accept(":")
            if self.value() in ("{", "<"):
                value: Any = self.aggregate()
            elif self.value() == "[":
                self.i += 1
                items = []
                while (iv := self.value()) is not None and iv != "]":
                    if iv == ",":
                        self.i += 1
                    elif iv in ("{", "<"):
                        items.append(self.aggregate())
                    else:
                        c = self.constant()
                        if c is None:
                            self.i += 1
                        else:
                            items.append(c)
                self.accept("]")
                value = items
            else:
                value = self.constant()
                if value is None:
                    self.i += 1
                    continue
            if key in result:
                prev = result[key]
                result[key] = (prev if isinstance(prev, list) else [prev]) + (value if isinstance(value, list) else [value])
            else:
                result[key] = value
        self.accept(close)
        return result

    def skip_statement(self) -> None:
        """Skip to the end of the current statement: a ';' or a balanced {...} block."""
        depth = 0
        while (tok := self.next()) is not None:
            v = tok[1]
            if v in "{[(" and tok[0] == "punct":
                depth += 1
            elif v in "}])" and tok[0] == "punct":
                if depth == 0:
                    # Belongs to the enclosing block; leave it for the caller.
                    self.i -= 1
                    return
                depth -= 1
                if depth == 0 and v == "}":
                    return
            elif v == ";" and depth == 0:
                return


def _http_bindings(rule: Any) -> list[dict[str, str]]:
    """Flatten a google.api.HttpRule literal (with additional_bindings) into bindings."""
    bindings: list[dict[str, str]] = []
    rules = rule if isinstance(rule, list) else [rule]
    for r in rules:
        if not isinstance(r, dict):
            continue
        binding: dict[str, str] = {}
        for method in _HTTP_METHODS:
            if isinstance(r.get(method), str):
                binding = {"method": method.upper(), "path": r[method]}
                break
        else:
            custom = r.get("custom")
            if isinstance(custom, dict) and isinstance(custom.get("path"), str):
                binding = {"method": str(custom.get("kind", "")).upper(), "path": custom["path"]}
        if binding:
            for key in ("body", "response_body"):
                if isinstance(r.get(key), str):
                    binding[key] = r[key]
            bindings.append(binding)
        bindings.extend(_http_bindings(r.get("additional_bindings", [])))
    return bindings


def extract_protobuf(path: Path) -> dict:
    """Extract the declarations of a .proto file and the references between them.

    Nodes: the file; every message (nested included), proto2 group, enum, enum
    value, service, rpc and extension field; and a ``rationale`` node for each
    declaration's leading doc comment. Node metadata carries ``language`` =
    ``"protobuf"``, ``kind`` and the fully qualified protobuf name (``fqn``),
    plus ``deprecated`` when set, the enum value ``number``, rpc streaming
    flags and ``http`` bindings, and on the file node ``package``, ``syntax`` /
    ``edition`` and the code-generation ``options``.

    Edges: ``contains`` (file or enclosing message / enum -> declaration),
    ``method`` (service -> rpc), ``references`` (message -> field / map / oneof /
    group type, rpc -> request and response types, extension field -> the
    message it extends and its own type; context ``protobuf_type``),
    ``references`` with context ``protobuf_option`` (a declaration -> the
    extension field behind each custom ``(option)`` it sets), ``imports`` (file
    -> imported .proto file) and ``rationale_for`` (doc comment -> declaration).
    Scalar field types produce no edge.
    """
    text = _read_source_text(path)
    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    node_by_id: dict[str, dict[str, Any]] = {}
    seen_edges: set[tuple[str, str, str]] = set()
    package = ""
    file_options: dict[str, Any] = {}
    # fqn -> node id for declarations in this file, used for in-file binding.
    local_types: dict[str, str] = {}
    local_extensions: dict[str, str] = {}
    http_rules: dict[str, dict[str, Any]] = {}  # rpc node id -> google.api.HttpRule literal
    # (source id, scope, written name, line, context) bound after the walk, so a
    # field may refer to a message declared further down the file.
    pending: list[tuple[str, str, str, int, str]] = []

    tokens, comments = _tokenize(text)
    comment_by_end: dict[int, _Comment] = {}
    for c in comments:
        if c.owns_line:
            comment_by_end[c.end] = c
    trailing_by_line: dict[int, _Comment] = {c.start: c for c in comments if not c.owns_line}

    def add_node(nid: str, label: str, line: int, kind: str, fqn: str | None = None,
                 **extra: Any) -> dict[str, Any]:
        if nid in node_by_id:
            return node_by_id[nid]
        metadata: dict[str, Any] = {"language": "protobuf", "kind": kind}
        if fqn is not None:
            metadata["fqn"] = fqn
        metadata.update(extra)
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": str_path,
            "source_location": f"L{line}",
            "metadata": metadata,
        }
        nodes.append(node)
        node_by_id[nid] = node
        return node

    def add_edge(src: str, tgt: str, relation: str, line: int, context: str | None = None) -> None:
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
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def attach_doc(nid: str, line: int, trailing: bool = False) -> None:
        """Leading comment block ending on the line above ``line`` (no blank line between)."""
        # Consecutive `//` lines form one block; a /* */ comment is a block on its own
        # (protoc's rule), so an earlier comment above it is detached.
        block: list[_Comment] = []
        c = comment_by_end.get(line - 1)
        while c is not None:
            block.append(c)
            if c.is_block:
                break
            c = comment_by_end.get(c.start - 1)
            if c is not None and c.is_block:
                break
        doc_line = block[-1].start if block else line
        doc = "\n".join(c.text for c in reversed(block)).strip()
        if not doc and trailing and line in trailing_by_line:
            doc = trailing_by_line[line].text.strip()
            doc_line = line
        if not doc:
            return
        rid = _make_id(stem, "rationale", str(doc_line))
        if rid not in node_by_id:
            node = {
                "id": rid,
                "label": _shorten_rationale_label(doc),
                "file_type": "rationale",
                "source_file": str_path,
                "source_location": f"L{doc_line}",
            }
            nodes.append(node)
            node_by_id[rid] = node
        add_edge(rid, nid, "rationale_for", doc_line)

    def ref(src: str, scope: str, name: str | None, line: int, context: str = _TYPE_CONTEXT) -> None:
        if not name or (context == _TYPE_CONTEXT and name in _SCALARS):
            return
        pending.append((src, scope, name, line, context))

    claimed: dict[str, str] = {}  # node id -> fqn that owns it

    def decl_id(local_name: str, fqn: str) -> str:
        """Node id for a declaration, kept distinct from names that differ only in case.

        ``make_id`` lowercases, but protobuf names are case-sensitive: ``minimal`` and
        ``MINIMAL`` enum aliases, or an extension ``foo_bar`` beside a message
        ``Foo_bar``, are different symbols. The first keeps the plain id; a later
        declaration whose id is taken by another full name gets one salted with a
        digest of its own full name.
        """
        nid = _make_id(stem, local_name)
        owner = claimed.setdefault(nid, fqn)
        if owner != fqn:
            nid = _make_id(stem, local_name, hashlib.sha1(fqn.encode("utf-8")).hexdigest()[:8])
            claimed.setdefault(nid, fqn)
        return nid

    w = _Walker(tokens)
    add_node(file_nid, path.name, 1, "file")

    def is_visibility_modifier() -> bool:
        # `export message Foo {` / `local enum Bar {`, not a field typed `export`.
        return w.value(1) in ("message", "enum") and w.value(3) == "{"

    def apply_option(owner: str, scope: str, name: str, custom: str | None, line: int,
                     value_start: int, describes_owner: bool = True) -> None:
        """Record what an option assignment means for ``owner``; the value is at ``value_start``.

        ``describes_owner`` is False for a field's ``[...]`` options: the field has no
        node, so its options are attributed to the enclosing message as usages only.
        """
        if custom is not None:
            ref(owner, scope, custom, line, _OPTION_CONTEXT)
        if not describes_owner:
            return
        meta = node_by_id[owner]["metadata"]
        w.i = value_start
        if name == "deprecated":
            if w.constant() is True:
                meta["deprecated"] = True
        elif custom == _HTTP_OPTION and meta["kind"] == "rpc":
            rule = http_rules.setdefault(owner, {})
            if name == f"({_HTTP_OPTION})" and w.value() in ("{", "<"):
                rule.update(w.aggregate())
            else:
                # Dotted form, possibly split over statements:
                #   option (google.api.http).post = "/v1/x";
                #   option (google.api.http).body = "*";
                sub = name[len(f"({_HTTP_OPTION})."):]
                value = w.aggregate() if w.value() in ("{", "<") else w.constant()
                if sub and value is not None:
                    rule[sub] = value
        elif owner == file_nid:
            if name in _CODEGEN_OPTIONS:
                value = w.constant()
                if value is not None:
                    file_options[name] = value
            elif name == "(scalapb.options)" and w.value() in ("{", "<"):
                agg = w.aggregate()
                for key in sorted(_SCALAPB_OPTIONS & agg.keys()):
                    if not isinstance(agg[key], (dict, list)):
                        file_options[f"(scalapb.options).{key}"] = agg[key]
            elif name.startswith("(scalapb.options).") and name.rsplit(".", 1)[-1] in _SCALAPB_OPTIONS:
                value = w.constant()
                if value is not None:
                    file_options[name] = value

    def parse_option_statement(owner: str, scope: str) -> None:
        """``option NAME = VALUE;`` with the ``option`` keyword already consumed."""
        line = w.prev_line()
        start = w.i
        parsed = w.option_name()
        if parsed is None or not w.accept("="):
            w.i = start
            w.skip_statement()
            return
        apply_option(owner, scope, parsed[0], parsed[1], line, w.i)
        w.i = start
        w.skip_statement()

    def parse_bracket_options(owner: str, scope: str, describes_owner: bool = True) -> None:
        """``[a = 1, (x.y) = 2]`` after a field or enum value; '[' is the next token."""
        if not w.accept("["):
            return
        while (v := w.value()) is not None and v not in ("]", ";", "}"):
            if v == ",":
                w.next()
                continue
            line = w.line()
            parsed = w.option_name()
            if parsed is None or not w.accept("="):
                w.next()
                continue
            apply_option(owner, scope, parsed[0], parsed[1], line, w.i, describes_owner)
            # Skip the value (it may be an aggregate) up to the next ',' or ']'.
            depth = 0
            while (t := w.peek()) is not None:
                if t[0] == "punct" and t[1] in "{[(<":
                    depth += 1
                elif t[0] == "punct" and t[1] in "}])>":
                    if depth == 0:
                        break
                    depth -= 1
                elif t[1] == "," and depth == 0:
                    break
                w.next()
        w.accept("]")

    def parse_field(owner: str, scope: str, extension_scope: tuple[str, str] | None = None,
                    extendee: str | None = None) -> None:
        """One field statement (label already consumed). In an ``extend`` block the
        field is an extension and gets a node of its own (``extension_scope`` is the
        enclosing (scope, local scope))."""
        line = w.line()
        types: list[str | None] = []
        if w.value() == "map" and w.value(1) == "<":
            w.next()
            w.next()
            types.append(w.full_ident())
            w.accept(",")
            types.append(w.full_ident())
            w.accept(">")
        else:
            types.append(w.full_ident())
        name_tok = w.peek()
        source = owner
        if extension_scope is not None and name_tok is not None and name_tok[0] == "ident":
            ext_scope, ext_local = extension_scope
            fqn = _qualify(ext_scope, name_tok[1])
            source = decl_id(_qualify(ext_local, name_tok[1]), fqn)
            add_node(source, name_tok[1], line, "extension", fqn,
                     **({"extendee": extendee} if extendee else {}))
            local_extensions[fqn] = source
            add_edge(owner, source, "contains", line)
            ref(source, scope, extendee, line)
            attach_doc(source, line)
        for type_name in types:
            ref(source, scope, type_name, line)
        while (v := w.value()) is not None and v not in (";", "[", "}"):
            w.next()
        if w.value() == "[":
            # An extension field is a node and owns its options; a plain field does not.
            parse_bracket_options(source, scope, describes_owner=source != owner)
        w.skip_statement()

    def parse_message(container_nid: str, scope: str, local_scope: str, kind: str = "message") -> None:
        # The 'message' / 'group' keyword has been consumed; next token is the name.
        line = w.prev_line()
        tok = w.next()
        if tok is None or tok[0] != "ident":
            w.skip_statement()
            return
        name = tok[1]
        fqn = _qualify(scope, name)
        local_name = _qualify(local_scope, name)
        nid = decl_id(local_name, fqn)
        add_node(nid, name, line, kind, fqn)
        local_types[fqn] = nid
        add_edge(container_nid, nid, "contains", line)
        attach_doc(nid, line)
        if kind == "group":
            # proto2 group: `group Name = N [opts] { ... }` declares a type and a
            # field of that type in one statement.
            add_edge(container_nid, nid, "references", line, context=_TYPE_CONTEXT)
            while w.value() not in ("{", ";", "[", None):
                w.next()
            if w.value() == "[":
                parse_bracket_options(container_nid, scope, describes_owner=False)
        parse_message_body(nid, fqn, local_name)

    def parse_enum(container_nid: str, scope: str, local_scope: str) -> None:
        line = w.prev_line()
        tok = w.next()
        if tok is None or tok[0] != "ident":
            w.skip_statement()
            return
        name = tok[1]
        fqn = _qualify(scope, name)
        local_name = _qualify(local_scope, name)
        nid = decl_id(local_name, fqn)
        add_node(nid, name, line, "enum", fqn)
        local_types[fqn] = nid
        add_edge(container_nid, nid, "contains", line)
        attach_doc(nid, line)
        if not w.accept("{"):
            w.skip_statement()
            return
        while (v := w.value()) is not None and v != "}":
            if v == ";":
                w.next()
            elif v == "option":
                w.next()
                parse_option_statement(nid, scope)
            elif v == "reserved":
                w.skip_statement()
            elif (tok := w.peek()) is not None and tok[0] == "ident" and w.value(1) == "=":
                value_line = tok[2]
                w.i += 2
                number = w.constant()
                # Enum values are siblings of their enum in protobuf's scoping.
                value_fqn = _qualify(scope, tok[1])
                vid = decl_id(_qualify(local_name, tok[1]), value_fqn)
                extra: dict[str, Any] = {}
                parsed = _parse_int(number) if isinstance(number, str) else None
                if parsed is not None:
                    extra["number"] = parsed
                add_node(vid, tok[1], value_line, "enum_value", value_fqn, **extra)
                add_edge(nid, vid, "contains", value_line)
                attach_doc(vid, value_line, trailing=True)
                if w.value() == "[":
                    parse_bracket_options(vid, scope)
                w.skip_statement()
            else:
                w.skip_statement()
        w.accept("}")

    def parse_extend(owner: str, scope: str, local_scope: str) -> None:
        line = w.line()
        target = w.full_ident()
        if not w.accept("{"):
            ref(owner, scope, target, line)
            w.skip_statement()
            return
        while (v := w.value()) is not None and v != "}":
            if v == ";":
                w.next()
            elif v == "option":
                w.skip_statement()
            else:
                if v in _LABELS and w.value(1) is not None:
                    w.next()
                if w.value() == "group" and (nxt := w.peek(1)) is not None and nxt[0] == "ident":
                    # `extend X { optional group Foo = N {...} }` declares a type Foo and
                    # an extension field foo (the lowercased name), both in the scope
                    # enclosing the extend.
                    field = nxt[1].lower()
                    ext_fqn = _qualify(scope, field)
                    ext_nid = decl_id(_qualify(local_scope, field), ext_fqn)
                    add_node(ext_nid, field, nxt[2], "extension", ext_fqn,
                             **({"extendee": target} if target else {}))
                    local_extensions[ext_fqn] = ext_nid
                    add_edge(owner, ext_nid, "contains", nxt[2])
                    ref(ext_nid, scope, target, nxt[2])
                    ref(ext_nid, scope, nxt[1], nxt[2])
                    w.next()
                    parse_message(owner, scope, local_scope, kind="group")
                else:
                    parse_field(owner, scope, (scope, local_scope), target)
        w.accept("}")

    def parse_oneof(owner: str, scope: str, local_scope: str) -> None:
        w.next()  # oneof name
        if not w.accept("{"):
            w.skip_statement()
            return
        while (v := w.value()) is not None and v != "}":
            if v == ";":
                w.next()
            elif v == "option":
                w.next()
                parse_option_statement(owner, scope)
            elif v == "group" and (nxt := w.peek(1)) is not None and nxt[0] == "ident":
                w.next()
                parse_message(owner, scope, local_scope, kind="group")
            else:
                if v in _LABELS:
                    w.next()
                parse_field(owner, scope)
        w.accept("}")

    def parse_message_body(nid: str, fqn: str, local_name: str) -> None:
        if not w.accept("{"):
            w.skip_statement()
            return
        while (v := w.value()) is not None and v != "}":
            if v == ";":
                w.next()
            elif v in _VISIBILITY and is_visibility_modifier():
                w.next()
            elif v == "message":
                w.next()
                parse_message(nid, fqn, local_name)
            elif v == "enum":
                w.next()
                parse_enum(nid, fqn, local_name)
            elif v == "oneof":
                w.next()
                parse_oneof(nid, fqn, local_name)
            elif v == "extend":
                w.next()
                parse_extend(nid, fqn, local_name)
            elif v == "option":
                w.next()
                parse_option_statement(nid, fqn)
            elif v in ("reserved", "extensions"):
                w.skip_statement()
            elif v in _LABELS and w.value(1) == "group":
                w.next()
                w.next()
                parse_message(nid, fqn, local_name, kind="group")
            elif v == "group" and (nxt := w.peek(1)) is not None and nxt[0] == "ident" and w.value(2) == "=":
                w.next()
                parse_message(nid, fqn, local_name, kind="group")
            else:
                if v in _LABELS:
                    w.next()
                parse_field(nid, fqn)
        w.accept("}")

    def parse_service() -> None:
        line = w.prev_line()
        tok = w.next()
        if tok is None or tok[0] != "ident":
            w.skip_statement()
            return
        name = tok[1]
        fqn = _qualify(package, name)
        nid = decl_id(name, fqn)
        add_node(nid, name, line, "service", fqn)
        add_edge(file_nid, nid, "contains", line)
        attach_doc(nid, line)
        if not w.accept("{"):
            w.skip_statement()
            return
        while (v := w.value()) is not None and v != "}":
            if v == "option":
                w.next()
                parse_option_statement(nid, fqn)
                continue
            if v != "rpc":
                w.skip_statement()
                continue
            rpc_line = w.line()
            w.next()
            rtok = w.next()
            if rtok is None or rtok[0] != "ident":
                w.skip_statement()
                continue
            rpc_fqn = _qualify(fqn, rtok[1])
            rpc_nid = decl_id(_qualify(name, rtok[1]), rpc_fqn)
            types: list[tuple[str | None, bool]] = []
            for keyword in (None, "returns"):
                if keyword is not None and not w.accept(keyword):
                    break
                if not w.accept("("):
                    break
                streaming = w.accept("stream")
                types.append((w.full_ident(), streaming))
                w.accept(")")
            add_node(rpc_nid, f".{rtok[1]}()", rpc_line, "rpc", rpc_fqn,
                     client_streaming=bool(types and types[0][1]),
                     server_streaming=bool(len(types) > 1 and types[1][1]))
            add_edge(nid, rpc_nid, "method", rpc_line)
            attach_doc(rpc_nid, rpc_line, trailing=True)
            for type_name, _streaming in types:
                ref(rpc_nid, fqn, type_name, rpc_line)
            if w.accept("{"):
                while (rv := w.value()) is not None and rv != "}":
                    if rv == "option":
                        w.next()
                        parse_option_statement(rpc_nid, fqn)
                    else:
                        w.skip_statement()
                w.accept("}")
            else:
                w.accept(";")
        w.accept("}")

    while (tok := w.peek()) is not None:
        v = tok[1]
        if v in ("syntax", "edition") and w.value(1) == "=":
            w.next()
            w.next()
            declared = w.constant()
            if isinstance(declared, str):
                nodes[0]["metadata"][v] = declared
            w.skip_statement()
        elif v == "package":
            w.next()
            package = (w.full_ident() or "").lstrip(".")
            nodes[0]["metadata"]["package"] = package
            w.skip_statement()
        elif v == "option":
            w.next()
            parse_option_statement(file_nid, package)
        elif v in _VISIBILITY and is_visibility_modifier():
            w.next()
        elif v == "import":
            line = tok[2]
            w.next()
            modifier = w.value() if w.value() in ("public", "weak", "option") else None
            if modifier is not None:
                w.next()
            s = w.peek()
            if s is not None and s[0] == "string":
                import_path = _unquote(s[1])
                if import_path:
                    prefix = _PUBLIC_IMPORT_CONTEXT if modifier == "public" else _IMPORT_CONTEXT
                    add_edge(file_nid, _make_id(import_path), "imports", line,
                             context=f"{prefix}:{import_path}")
            w.skip_statement()
        elif v == "message":
            w.next()
            parse_message(file_nid, package, "")
        elif v == "enum":
            w.next()
            parse_enum(file_nid, package, "")
        elif v == "service":
            w.next()
            parse_service()
        elif v == "extend":
            w.next()
            parse_extend(file_nid, package, "")
        elif v == "}":
            w.next()  # stray closer from malformed input
        else:
            w.skip_statement()

    if file_options:
        nodes[0]["metadata"]["options"] = dict(sorted(file_options.items()))
    for rpc_nid, rule in http_rules.items():
        bindings = _http_bindings(rule)
        if bindings:
            node_by_id[rpc_nid]["metadata"]["http"] = bindings

    for src, scope, name, line, context in pending:
        if src == file_nid:
            # File options are interpreted in the file's package wherever the
            # `option` statement sits, even above the `package` line.
            scope = package
        table = local_types if context == _TYPE_CONTEXT else local_extensions
        # Only the scopes from the reference outwards to the file's own package can
        # hold a same-file declaration, and protobuf forbids a second definition of
        # the same full name in that package, so a local hit cannot be shadowed.
        local = next((table[f] for f in _candidate_fqns(name, scope) if f in table), None)
        if local is not None:
            add_edge(src, local, "references", line, context=context)
        else:
            add_edge(src, _make_id(context, scope, name), "references", line,
                     context=f"{context}:{scope}:{name}")

    return {"nodes": nodes, "edges": edges}


def _common_dir_depth(a: str, b: str) -> int:
    pa = posixpath.dirname(a).split("/")
    pb = posixpath.dirname(b).split("/")
    depth = 0
    for x, y in zip(pa, pb):
        if x != y:
            break
        depth += 1
    return depth


def resolve_protobuf_references(
    _per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Bind cross-file protobuf imports, type references and option usages across the corpus.

    Imports: ``import "a/b.proto"`` binds to the corpus .proto file whose path is
    ``a/b.proto`` or ends with ``/a/b.proto`` (the include root is not known). If
    several match, the one under the include root that unambiguous imports in the
    corpus resolve through most often wins, then the one sharing the longest
    directory prefix with the importing file, marked INFERRED; a tie stays
    unbound and the graph builder turns it into an external stub, as for any
    unresolved import.

    Type references and custom option usages: only declarations in files the
    referencing file can see count, as for protoc: its imports, plus what they
    re-export through ``import public`` (same-file names were bound during
    extraction). Candidate full names follow protobuf scoping (innermost scope
    first, or the absolute ``.pkg.Name`` form) and the first one with a visible
    declaration (a type, or an extension field for an option) is the binding,
    marked INFERRED when it was picked among several copies of that full name.
    A reference to a file that is not imported, or whose import did not
    resolve, stays unbound and is dropped by the builder rather than guessed,
    as are two visible declarations of the same full name.
    """
    node_by_id = {n.get("id"): n for n in all_nodes}
    proto_files: dict[str, str] = {}  # normalized source path -> file node id
    declared_by_fqn: dict[str, dict[str, list[dict]]] = {_TYPE_CONTEXT: {}, _OPTION_CONTEXT: {}}
    for node in all_nodes:
        meta = node.get("metadata")
        if not isinstance(meta, dict) or meta.get("language") != "protobuf":
            continue
        source = str(node.get("source_file") or "").replace("\\", "/")
        kind = meta.get("kind")
        if kind == "file" and source:
            proto_files[source] = node["id"]
        elif meta.get("fqn"):
            if kind in _TYPE_KINDS:
                declared_by_fqn[_TYPE_CONTEXT].setdefault(meta["fqn"], []).append(node)
            elif kind == "extension":
                declared_by_fqn[_OPTION_CONTEXT].setdefault(meta["fqn"], []).append(node)
    if not proto_files:
        return
    source_by_file_id = {nid: src for src, nid in proto_files.items()}

    by_suffix: dict[str, list[str]] = {}
    for src in proto_files:
        parts = src.split("/")
        for i in range(len(parts)):
            by_suffix.setdefault("/".join(parts[i:]), []).append(src)

    pending: list[tuple[dict, str, str, list[str], bool]] = []
    for edge in all_edges:
        context = edge.get("context")
        if not isinstance(context, str):
            continue
        is_public = context.startswith(_PUBLIC_IMPORT_CONTEXT + ":")
        if not is_public and not context.startswith(_IMPORT_CONTEXT + ":"):
            continue
        import_path = posixpath.normpath(context.split(":", 1)[1].replace("\\", "/"))
        matches = sorted(by_suffix.get(import_path, ()))
        if matches:
            importer = source_by_file_id.get(str(edge.get("source")), "")
            pending.append((edge, importer, import_path, matches, is_public))

    def root_of(src: str, import_path: str) -> str:
        return src[: len(src) - len(import_path)]

    # Include roots that unambiguous imports already resolve through. An import
    # that matches several files prefers the root the rest of the corpus uses
    # (googleapis/ over a vendored googleapis/preview/ copy), then the one closest
    # to the importing file; anything still tied stays unbound.
    root_use: dict[str, int] = {}
    for _edge, _importer, import_path, matches, _public in pending:
        if len(matches) == 1:
            root = root_of(matches[0], import_path)
            root_use[root] = root_use.get(root, 0) + 1

    imported: dict[str, set[str]] = {}
    public_imports: dict[str, set[str]] = {}
    for edge, importer, import_path, matches, is_public in pending:
        if len(matches) > 1:
            for score in (
                lambda m: root_use.get(root_of(m, import_path), 0),
                lambda m: _common_dir_depth(importer, m),
            ):
                scores = {m: score(m) for m in matches}
                best = max(scores.values())
                matches = [m for m in matches if scores[m] == best]
                if len(matches) == 1:
                    break
            if len(matches) != 1:
                continue
            edge["confidence"] = "INFERRED"
        edge["target"] = proto_files[matches[0]]
        imported.setdefault(importer, set()).add(matches[0])
        if is_public:
            public_imports.setdefault(importer, set()).add(matches[0])

    visible_cache: dict[str, set[str]] = {}

    def visible_files(source: str) -> set[str]:
        """Direct imports plus whatever they re-export through `import public`."""
        if source not in visible_cache:
            seen: set[str] = set()
            stack = list(imported.get(source, ()))
            while stack:
                f = stack.pop()
                if f not in seen:
                    seen.add(f)
                    stack.extend(public_imports.get(f, ()))
            visible_cache[source] = seen
        return visible_cache[source]

    for edge in all_edges:
        context = edge.get("context")
        if not isinstance(context, str):
            continue
        kind, sep, rest = context.partition(":")
        if not sep or kind not in declared_by_fqn:
            continue
        scope, _, name = rest.partition(":")
        declared_index = declared_by_fqn[kind]
        referrer = str((node_by_id.get(edge.get("source")) or {}).get("source_file") or "").replace("\\", "/")
        files = visible_files(referrer)
        for fqn in _candidate_fqns(name, scope):
            # Only declarations in files the referrer imports are in scope (protoc
            # never sees the rest), so an invisible declaration neither binds nor
            # shadows a visible one further out.
            visible = [n for n in declared_index.get(fqn, ())
                       if str(n.get("source_file") or "").replace("\\", "/") in files]
            if not visible:
                continue
            if len(visible) == 1:
                edge["target"] = visible[0]["id"]
                edge["context"] = kind
                if len(declared_index[fqn]) > 1:
                    # Picked among vendored copies through the import graph.
                    edge["confidence"] = "INFERRED"
            break
