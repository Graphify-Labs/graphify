"""Dart extractor.

Tree-sitter is the primary path: declarations, imports/exports, part-of
redirection, annotations, and functions come from the AST with real
``source_location`` line anchors (``L{n}``), matching the other
tree-sitter-backed languages. The Flutter-framework heuristics
(Bloc/Riverpod/navigation) and variable extraction — where the community
grammar is still weaker than the battle-tested regexes (Dart 3 destructuring
patterns parse with ERROR nodes) — keep running as regex sweeps over the same
source, line-anchored via match offsets.

When ``tree-sitter-dart`` isn't installed (it's the optional ``[dart]``
extra), extraction falls back to ``_extract_dart_regex`` — the pre-tree-sitter
implementation, preserved verbatim — so Dart extraction keeps working out of
the box without an extra pip install. This mirrors ``extract_pascal`` (#781).
"""
from __future__ import annotations

import re

from bisect import bisect_right
from pathlib import Path
from typing import Any, Callable

from graphify.extractors.base import _file_stem, _make_id

# Strips // and /* */ comments while leaving string literals untouched
# (so URLs/paths inside strings survive). Shared by both extraction paths.
_DART_COMMENT_STRING_RE = re.compile(
    r'"""(?:\\.|[\s\S])*?"""'
    r"|'''(?:\\.|[\s\S])*?'''"
    r'|"(?:\\.|[^"\\])*"'
    r"|'(?:\\.|[^'\\])*'"
    r"|/\*[\s\S]*?\*/"
    r"|//[^\n]*"
)

# Blacklists preserved exactly from the regex extractor (each sweep filters a
# slightly different builtin set).
_DART_PRIMITIVE_TYPES = frozenset({
    "String", "int", "double", "bool", "num", "dynamic", "Object", "void",
})
_DART_VAR_TYPE_BLACKLIST = _DART_PRIMITIVE_TYPES | {"List", "Map", "Set"}
_DART_TYPEDEF_BLACKLIST = _DART_VAR_TYPE_BLACKLIST | {"Function"}
_DART_GENERIC_CALL_BLACKLIST = _DART_VAR_TYPE_BLACKLIST | {"Future", "Stream"}
_DART_EMIT_BLACKLIST = frozenset({
    "String", "List", "Map", "Set", "Future", "Stream", "Object",
})
_DART_STMT_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return",
})

# --- Flutter-framework body sweeps (class-body scope) ---
_DART_BLOC_ON_RE = re.compile(r"\bon<(\w+)>\s*\(")
_DART_EMIT_RE = re.compile(r"\b(?:emit|yield)\s*\(?\s*(?:const\s+)?([A-Z]\w*)\b")
_DART_BLOC_ADD_RE = re.compile(
    r"\b(?:\w*[Bb]loc\w*|context\.read<\w+>\(\))\.add\(\s*(?:const\s+)?([A-Z]\w*)\b"
)
_DART_RIVERPOD_REF_RE = re.compile(r"\bref\.(?:watch|read|listen)\s*\(\s*(\w+)\b")
_DART_BLOC_WIDGET_RE = re.compile(
    r"\bBloc(?:Builder|Listener|Consumer|Provider|Selector)\s*<\s*([a-zA-Z0-9_]+)\b"
)
_DART_TYPED_LOOKUP_RE = re.compile(r"\b(?:read|watch|select|of)\s*<([a-zA-Z0-9_]+)>")

# --- Navigation sweeps (function-body scope) ---
_DART_NAV_PATH_RE = re.compile(
    r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?['\"]([a-zA-Z0-9_/?=&%-]+)['\"]"
)
_DART_NAV_CONST_RE = re.compile(
    r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?([A-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9_]+)"
)
_DART_NAV_OBJECT_RE = re.compile(
    r"\b(?:push|replace)\s*\(\s*(?:context\s*,\s*)?.*?\b([A-Z]\w*(?:Route|Screen|Page))\b"
)

# --- Whole-file sweeps ---
# Top-level and class-level variables (generic, record, late, destructuring);
# 0-2 space indent keeps locals inside functions/switch expressions out.
_DART_VAR_RE = re.compile(
    r"^\s{0,2}(?:late\s+)?(?:(?:final|const|var)\s+)?(?:\([^)]+\)\s+|([a-zA-Z0-9_<>,.?]+(?:\s+[a-zA-Z0-9_<>,.?]+){0,3})\s+)?(?:(\w+)|(?:\w+\s*)?\(([^)]+)\))\s*(?:=|$|;)",
    re.MULTILINE,
)
# Any method call with type parameters: methodName<Type>() — catches GetIt,
# Injectable, Riverpod, Provider, BlocProvider, and InheritedWidget lookups.
_DART_GENERIC_CALL_RE = re.compile(
    r"\b\w+<([a-zA-Z0-9_.]+(?:<[a-zA-Z0-9_.,\s<>]+>)?)\s*>\s*\("
)

_DART_CLASS_EXTENDS_RE = re.compile(r"^\s*(?:extends|on)\s+([a-zA-Z0-9_.]+)")
_DART_CLASS_WITH_RE = re.compile(r"^\s*with\s+")
_DART_CLASS_IMPLEMENTS_RE = re.compile(r"^\s*implements\s+")

_DART_ANNOTATION_SKIP = frozenset({
    "override", "deprecated", "required", "protected", "mustCallSuper",
})

# Class-family AST node types that produce a class node.
_DART_CLASS_NODE_TYPES = frozenset({
    "class_definition", "mixin_declaration", "enum_declaration",
    "extension_type_declaration",
})


def _dart_strip_comments(src: str) -> str:
    """Remove comments, preserving newline counts so offsets map to lines."""
    def _sub(match: re.Match) -> str:
        token = match.group(0)
        if token.startswith("/"):
            return "\n" * token.count("\n")
        return token
    return _DART_COMMENT_STRING_RE.sub(_sub, src)


def _dart_split_types(text: str) -> list[str]:
    """Split a comma-separated type list, respecting nested generics."""
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in text:
        if char == "<":
            depth += 1
            current.append(char)
        elif char == ">":
            depth -= 1
            current.append(char)
        elif char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
        else:
            current.append(char)
    if current:
        parts.append("".join(current).strip())
    return [p for p in parts if p]


def _dart_parse_class_header(header: str) -> dict:
    """Parse ``extends/on X<...> with A, B implements C, D`` clause text.

    Same semantics as the regex extractor's inline header parsing: returns the
    base class, its balanced generic arguments, mixins, and interfaces.
    """
    base_class = None
    generics = None
    mixins_list: list[str] = []
    interfaces_list: list[str] = []

    extends_m = _DART_CLASS_EXTENDS_RE.search(header)
    if extends_m:
        base_class = extends_m.group(1)
        rest_header = header[extends_m.end():]
        if rest_header.strip().startswith("<"):
            start_idx = rest_header.find("<")
            depth = 1
            i = start_idx + 1
            while i < len(rest_header) and depth > 0:
                if rest_header[i] == "<":
                    depth += 1
                elif rest_header[i] == ">":
                    depth -= 1
                    if depth == 0:
                        generics = rest_header[start_idx + 1 : i]
                        break
                i += 1
            header = rest_header[i + 1:] if generics is not None else rest_header
        else:
            header = rest_header

    with_m = _DART_CLASS_WITH_RE.search(header)
    if with_m:
        rest_header = header[with_m.end():]
        impl_idx = rest_header.find("implements")
        if impl_idx != -1:
            mixins_str = rest_header[:impl_idx]
            header = rest_header[impl_idx:]
        else:
            mixins_str = rest_header
            header = ""
        mixins_list = _dart_split_types(mixins_str)

    impl_m = _DART_CLASS_IMPLEMENTS_RE.search(header)
    if impl_m:
        interfaces_list = _dart_split_types(header[impl_m.end():])

    return {
        "base": base_class, "generics": generics,
        "mixins": mixins_list, "interfaces": interfaces_list,
    }


def extract_dart(path: Path) -> dict:
    """Extract classes, mixins, functions, imports, generic calls, and annotations from a .dart file.

    Uses tree-sitter-dart when available (AST-accurate declarations with
    ``source_location`` line anchors); falls back to the regex extractor
    (``_extract_dart_regex``) when it isn't installed or fails, so Dart
    extraction works out of the box without an extra pip install.
    """
    try:
        import tree_sitter_dart as tsdart
        from tree_sitter import Language, Parser
    except ImportError:
        return _extract_dart_regex(path)

    try:
        language = Language(tsdart.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception:
        return _extract_dart_regex(path)

    try:
        return _extract_dart_tree(path, source, root)
    except Exception:
        # tree-sitter-dart is young (0.1.x); never let a walker bug on an
        # unusual tree cost the whole file — the regex path always works.
        return _extract_dart_regex(path)


def _extract_dart_tree(path: Path, source: bytes, root: Any) -> dict:
    stem = _file_stem(path)
    str_path = str(path)
    decoded = source.decode("utf-8", errors="replace")
    src_clean = _dart_strip_comments(decoded)
    newline_offsets = [i for i, ch in enumerate(src_clean) if ch == "\n"]

    def _line_of(offset: int) -> int:
        return bisect_right(newline_offsets, offset - 1) + 1

    def _read(node: Any) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _node_line(node: Any) -> int:
        return node.start_point[0] + 1

    # part-of redirect: attribute this file's symbols to the parent library file
    file_nid = _make_id(str(path))
    is_part = False
    for child in root.children:
        if child.type == "part_of_directive":
            uri_node = next((c for c in child.children if c.type == "uri"), None)
            if uri_node is None:
                continue
            parent_ref = _read(uri_node).strip("'\"")
            if parent_ref.endswith(".dart"):
                try:
                    parent_path = (path.parent / parent_ref).resolve()
                    if parent_path.exists():
                        stem = _file_stem(parent_path)
                        file_nid = _make_id(str(parent_path))
                        is_part = True
                except Exception:
                    pass
            break

    nodes: list[dict] = []
    edges: list[dict] = []
    defined: set[str] = set()

    def add_node(
        nid: str, label: str, line: int | None = None,
        ftype: str = "code", source_file: str | None = str_path,
    ) -> None:
        if nid not in defined:
            nodes.append({
                "id": nid, "label": label, "file_type": ftype,
                "source_file": source_file,
                "source_location": f"L{line}" if line else None,
            })
            defined.add(nid)

    def add_edge(
        src_id: str, tgt_id: str, relation: str, line: int | None = None,
        weight: float = 1.0, context: str | None = None,
    ) -> None:
        edge: dict[str, Any] = {
            "source": src_id, "target": tgt_id, "relation": relation,
            "confidence": "EXTRACTED", "confidence_score": 1.0,
            "source_file": str_path,
            "source_location": f"L{line}" if line else None, "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    if not is_part:
        add_node(file_nid, path.name, 1)

    def _first_child(node: Any, *types: str) -> Any | None:
        return next((c for c in node.children if c.type in types), None)

    def _sweep(
        text: str, base_line: int, owner_nid: str,
        patterns: list[tuple[re.Pattern, Callable[[re.Match, int], None]]],
    ) -> None:
        clean = _dart_strip_comments(text)
        for pattern, handle in patterns:
            for m in pattern.finditer(clean):
                handle(m, base_line + clean.count("\n", 0, m.start()))

    def _riverpod_handler(owner_nid: str) -> Callable[[re.Match, int], None]:
        def handle(m: re.Match, line: int) -> None:
            provider_name = m.group(1)
            provider_nid = _make_id(provider_name)
            add_node(provider_nid, provider_name, source_file=None)
            add_edge(owner_nid, provider_nid, "references", line, context="riverpod_reference")
        return handle

    def _bloc_add_handler(owner_nid: str) -> Callable[[re.Match, int], None]:
        def handle(m: re.Match, line: int) -> None:
            event_name = m.group(1)
            if event_name not in _DART_EMIT_BLACKLIST:
                event_nid = _make_id(event_name)
                add_node(event_nid, event_name, source_file=None)
                add_edge(owner_nid, event_nid, "calls", line, context="bloc_add_event")
        return handle

    def _typed_lookup_handler(owner_nid: str) -> Callable[[re.Match, int], None]:
        def handle(m: re.Match, line: int) -> None:
            bloc_name = m.group(1)
            if bloc_name not in _DART_PRIMITIVE_TYPES:
                bloc_nid = _make_id(bloc_name)
                add_node(bloc_nid, bloc_name, source_file=None)
                add_edge(owner_nid, bloc_nid, "references", line, context="bloc_lookup")
        return handle

    def _sweep_class_body(body_node: Any, class_nid: str) -> None:
        """Bloc/Riverpod patterns attributed to the class (regex-path parity)."""
        def on_event(m: re.Match, line: int) -> None:
            event_nid = _make_id(m.group(1))
            add_node(event_nid, m.group(1), source_file=None)
            add_edge(class_nid, event_nid, "calls", line, context="bloc_event")

        def on_emit(m: re.Match, line: int) -> None:
            state_name = m.group(1)
            if state_name not in _DART_EMIT_BLACKLIST:
                state_nid = _make_id(state_name)
                add_node(state_nid, state_name, source_file=None)
                add_edge(class_nid, state_nid, "calls", line, context="emit_state")

        def on_bloc_widget(m: re.Match, line: int) -> None:
            bloc_name = m.group(1)
            if bloc_name not in _DART_PRIMITIVE_TYPES:
                bloc_nid = _make_id(bloc_name)
                add_node(bloc_nid, bloc_name, source_file=None)
                add_edge(class_nid, bloc_nid, "references", line, context="bloc_widget_binding")

        _sweep(_read(body_node), _node_line(body_node), class_nid, [
            (_DART_BLOC_ON_RE, on_event),
            (_DART_EMIT_RE, on_emit),
            (_DART_BLOC_ADD_RE, _bloc_add_handler(class_nid)),
            (_DART_RIVERPOD_REF_RE, _riverpod_handler(class_nid)),
            (_DART_BLOC_WIDGET_RE, on_bloc_widget),
            (_DART_TYPED_LOOKUP_RE, _typed_lookup_handler(class_nid)),
        ])

    def _sweep_function_body(body_node: Any, fn_nid: str) -> None:
        """Riverpod/Bloc/navigation patterns attributed to the function."""
        def on_nav_path(m: re.Match, line: int) -> None:
            route_path = m.group(1)
            route_nid = _make_id(
                "route",
                route_path.replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_"),
            )
            add_node(route_nid, f"Route {route_path}", line=None, ftype="concept", source_file=None)
            add_edge(fn_nid, route_nid, "navigates", line, context="route_path")

        def on_nav_const(m: re.Match, line: int) -> None:
            route_const = m.group(1)
            route_nid = _make_id("route", route_const.replace(".", "_"))
            add_node(route_nid, route_const, line=None, ftype="concept", source_file=None)
            add_edge(fn_nid, route_nid, "navigates", line, context="route_const")

        def on_nav_object(m: re.Match, line: int) -> None:
            route_class = m.group(1)
            route_nid = _make_id(route_class)
            add_node(route_nid, route_class, source_file=None)
            add_edge(fn_nid, route_nid, "navigates", line, context="route_object")

        _sweep(_read(body_node), _node_line(body_node), fn_nid, [
            (_DART_RIVERPOD_REF_RE, _riverpod_handler(fn_nid)),
            (_DART_BLOC_ADD_RE, _bloc_add_handler(fn_nid)),
            (_DART_TYPED_LOOKUP_RE, _typed_lookup_handler(fn_nid)),
            (_DART_NAV_PATH_RE, on_nav_path),
            (_DART_NAV_CONST_RE, on_nav_const),
            (_DART_NAV_OBJECT_RE, on_nav_object),
        ])

    def _apply_annotations(target_nid: str, target_name: str, is_class: bool, annotations: list[Any]) -> None:
        for ann in annotations:
            ident = _first_child(ann, "identifier")
            if ident is None:
                continue
            annotation_name = _read(ident)
            if annotation_name in _DART_ANNOTATION_SKIP:
                continue
            line = _node_line(ann)
            annotation_nid = _make_id("annotation", annotation_name.lower())
            add_node(annotation_nid, f"@{annotation_name}", line=None, ftype="concept", source_file=None)
            add_edge(target_nid, annotation_nid, "configures", line)

            # Riverpod codegen: @riverpod Foo -> fooProvider (class) / fnProvider (function)
            if annotation_name.lower() == "riverpod":
                if is_class:
                    provider_name = (
                        target_name[0].lower() + target_name[1:] + "Provider"
                        if len(target_name) > 1 else target_name.lower() + "Provider"
                    )
                else:
                    provider_name = target_name + "Provider"
                provider_nid = _make_id(provider_name)
                add_node(provider_nid, provider_name, line=None, ftype="concept", source_file=str_path)
                add_edge(target_nid, provider_nid, "defines", line, context="riverpod_provider")

    def _function_name(sig_node: Any, class_name: str | None) -> tuple[str | None, int]:
        """Resolve a function/method name, skipping constructors (regex parity)."""
        if sig_node.type == "factory_constructor_signature":
            idents = [c for c in sig_node.children if c.type == "identifier"]
            if not idents:
                return None, 0
            name = _read(idents[-1])
            # `factory MyService()` (single identifier == class) is a plain
            # constructor; `factory MyService.fromJson()` keeps `fromJson`.
            if len(idents) == 1 or name == class_name:
                return None, 0
        elif sig_node.type == "function_signature":
            ident = _first_child(sig_node, "identifier")
            if ident is None:
                return None, 0
            name = _read(ident)
        else:
            return None, 0
        if name in _DART_STMT_KEYWORDS or name in {"void", "dynamic", "final", "const", "get", "set"}:
            return None, 0
        if name[:1].isupper():
            return None, 0
        return name, _node_line(sig_node)

    def _handle_function(sig_node: Any, body_node: Any | None, annotations: list[Any], class_name: str | None) -> None:
        name, line = _function_name(sig_node, class_name)
        if name is None:
            return
        fn_nid = _make_id(stem, name)
        add_node(fn_nid, name, line)
        add_edge(file_nid, fn_nid, "defines", line)
        _apply_annotations(fn_nid, name, is_class=False, annotations=annotations)
        if body_node is not None and _first_child(body_node, "block") is not None:
            _sweep_function_body(body_node, fn_nid)

    def _handle_members(body_node: Any, class_name: str | None) -> None:
        """Walk a class/extension body for methods and factory constructors."""
        pending_annotations: list[Any] = []
        children = body_node.children
        for i, member in enumerate(children):
            if member.type == "annotation":
                pending_annotations.append(member)
                continue
            sig = None
            if member.type in ("method_signature", "function_signature"):
                sig = member if member.type == "function_signature" else _first_child(
                    member, "function_signature", "factory_constructor_signature"
                )
            elif member.type == "declaration":
                # fields and constructor_signatures: fields are handled by the
                # variable sweep; constructors are skipped (regex parity)
                pending_annotations = []
                continue
            if sig is not None:
                body = children[i + 1] if i + 1 < len(children) and children[i + 1].type == "function_body" else None
                _handle_function(sig, body, pending_annotations, class_name)
            if member.type != "annotation":
                pending_annotations = []

    def _handle_class_family(node: Any, annotations: list[Any]) -> None:
        ident = _first_child(node, "identifier")
        if ident is None:
            return
        class_name = _read(ident)
        line = _node_line(ident)
        class_nid = _make_id(stem, class_name)
        add_node(class_nid, class_name, line)
        add_edge(file_nid, class_nid, "defines", line)
        _apply_annotations(class_nid, class_name, is_class=True,
                           annotations=annotations + [c for c in node.children if c.type == "annotation"])

        # Header clause text between the name (or its generics/representation)
        # and the body — parsed with the same balanced-generics logic as the
        # regex path, since the grammar flattens dotted names and comma lists.
        hdr_start = ident.end_byte
        for skip_type in ("type_parameters", "representation_declaration"):
            skip_node = _first_child(node, skip_type)
            if skip_node is not None:
                hdr_start = max(hdr_start, skip_node.end_byte)
        body_node = _first_child(node, "class_body", "enum_body", "extension_body")
        hdr_end = body_node.start_byte if body_node is not None else node.end_byte
        header = _dart_parse_class_header(
            source[hdr_start:hdr_end].decode("utf-8", errors="replace")
        )

        if header["base"]:
            base_nid = _make_id(header["base"])
            add_node(base_nid, header["base"], source_file=None)
            add_edge(class_nid, base_nid, "inherits", line)
            if header["generics"]:
                for gen in _dart_split_types(header["generics"]):
                    gen_clean = gen.split("<")[0].strip()
                    if gen_clean not in _DART_PRIMITIVE_TYPES:
                        gen_nid = _make_id(gen_clean)
                        add_node(gen_nid, gen_clean, source_file=None)
                        add_edge(class_nid, gen_nid, "references", line)
        for mixin in header["mixins"]:
            mixin_clean = mixin.split("<")[0].strip()
            mixin_nid = _make_id(mixin_clean)
            add_node(mixin_nid, mixin_clean, source_file=None)
            add_edge(class_nid, mixin_nid, "mixes_in", line)
        for interface in header["interfaces"]:
            interface_clean = interface.split("<")[0].strip()
            interface_nid = _make_id(interface_clean)
            add_node(interface_nid, interface_clean, source_file=None)
            add_edge(class_nid, interface_nid, "implements", line)

        if body_node is not None and body_node.type != "enum_body":
            _sweep_class_body(body_node, class_nid)
            _handle_members(body_node, class_name)

    def _handle_extension(node: Any, annotations: list[Any]) -> None:
        ident = _first_child(node, "identifier")
        target_node = None
        seen_on = False
        for c in node.children:
            if c.type == "on":
                seen_on = True
            elif seen_on and c.type == "type_identifier":
                target_node = c
                break
        if target_node is None:
            return
        target_class = _read(target_node).split("<")[0]
        ext_name = _read(ident) if ident is not None else f"{stem}_anonymous_extension"
        label = _read(ident) if ident is not None else f"Extension on {target_class}"
        line = _node_line(ident if ident is not None else node)
        ext_nid = _make_id(stem, ext_name)
        add_node(ext_nid, label, line)
        add_edge(file_nid, ext_nid, "defines", line)
        target_nid = _make_id(target_class)
        add_node(target_nid, target_class, source_file=None)
        add_edge(ext_nid, target_nid, "extends", line)
        _apply_annotations(ext_nid, label, is_class=True, annotations=annotations)
        body_node = _first_child(node, "extension_body")
        if body_node is not None:
            _handle_members(body_node, None)

    def _handle_import_export(node: Any) -> None:
        is_export = _first_child(node, "library_export") is not None
        # Breadth-first for the uri: imports nest it under
        # library_import > import_specification > configurable_uri, exports
        # under library_export > configurable_uri.
        queue = list(node.children)
        uri = None
        while queue:
            n = queue.pop(0)
            if n.type == "uri":
                uri = n
                break
            if n.type == "configurable_uri" and uri is None:
                uri = n  # keep scanning; prefer the inner plain uri
            queue.extend(n.children)
        if uri is None:
            return
        pkg = _read(uri).strip("'\"")
        tgt_nid = _make_id(pkg)
        add_node(tgt_nid, pkg, source_file=None)
        add_edge(file_nid, tgt_nid, "exports" if is_export else "imports", _node_line(node))

    def _handle_type_alias(node: Any, annotations: list[Any]) -> None:
        name_node = _first_child(node, "type_identifier")
        if name_node is None:
            return
        typedef_name = _read(name_node)
        line = _node_line(name_node)
        # RHS target: first type after `=` (regex parity: builtins skipped
        # entirely, including `Map<...>`/`Function` aliases)
        rhs = _read(node)
        eq_idx = rhs.find("=")
        target_type = None
        if eq_idx != -1:
            m = re.match(r"\s*([a-zA-Z0-9_.]+)", rhs[eq_idx + 1:])
            if m:
                target_type = m.group(1).split(".")[-1]
        if target_type is None or target_type in _DART_TYPEDEF_BLACKLIST:
            return
        typedef_nid = _make_id(stem, typedef_name)
        add_node(typedef_nid, typedef_name, line)
        add_edge(file_nid, typedef_nid, "defines", line)
        target_nid = _make_id(target_type)
        add_node(target_nid, target_type, source_file=None)
        add_edge(typedef_nid, target_nid, "references", line, context="typedef")
        _apply_annotations(typedef_nid, typedef_name, is_class=False, annotations=annotations)

    # --- Program-level walk. Annotations can appear either as children of a
    # declaration or as loose siblings before it (grammar quirk), so track
    # pending loose annotations and hand them to the next declaration.
    pending: list[Any] = []
    program_children = root.children
    for i, child in enumerate(program_children):
        t = child.type
        if t == "annotation":
            pending.append(child)
            continue
        if t in _DART_CLASS_NODE_TYPES:
            _handle_class_family(child, pending)
        elif t == "extension_declaration":
            _handle_extension(child, pending)
        elif t == "import_or_export":
            _handle_import_export(child)
        elif t == "type_alias":
            _handle_type_alias(child, pending)
        elif t == "function_signature":
            body = (
                program_children[i + 1]
                if i + 1 < len(program_children) and program_children[i + 1].type == "function_body"
                else None
            )
            _handle_function(child, body, pending, None)
        pending = []

    # --- Regex supplements over the comment-stripped source (line-anchored).
    # Variables (incl. Dart 3 destructuring, which the grammar still parses
    # with ERROR nodes) and generic DI invocations stay on the proven regexes.
    #
    # Named/optional parameters are a Dart-specific trap for the variable
    # regex: a multi-line parameter list puts `required String id,` at the
    # 0-2-space indent the pattern treats as a declaration. The AST knows
    # where every parameter list is, so matches on those lines are skipped.
    # Only parameter lists of declaration signatures count — a lambda's
    # `(ref) =>` shares its line with a real variable declaration.
    param_lines: set[int] = set()
    stack = [root]
    while stack:
        n = stack.pop()
        if (
            n.type == "formal_parameter_list"
            and n.parent is not None
            and n.parent.type.endswith("_signature")
        ):
            # A real signature names the function *before* its parameters;
            # error recovery can misparse a record-typed variable
            # (`final (int, String) x`) as a signature whose "parameters"
            # are the record type, with the identifier trailing them.
            # (error recovery can also name a phantom signature with a
            # keyword — `final (int, String) x` after an unparsable line)
            ident = next((c for c in n.parent.children if c.type == "identifier"), None)
            if (
                ident is not None
                and ident.end_byte <= n.start_byte
                and _read(ident) not in {"final", "const", "var", "late"}
            ):
                param_lines.update(range(n.start_point[0] + 1, n.end_point[0] + 2))
        stack.extend(n.children)

    for m in _DART_VAR_RE.finditer(src_clean):
        var_type = m.group(1)
        single_name = m.group(2)
        destructured_names = m.group(3)
        # Anchor on the matched name itself — the pattern's ^\s{0,2} can
        # consume a leading newline, and a match can span lines.
        line = _line_of(m.start(2) if single_name else m.start(3) if destructured_names else m.start())
        if line in param_lines:
            continue

        if not re.match(r"^\s*(?:late|final|const|var)\b", m.group(0)) and not var_type:
            continue

        if single_name:
            if single_name not in _DART_STMT_KEYWORDS:
                var_nid = _make_id(stem, single_name)
                add_node(var_nid, single_name, line)
                add_edge(file_nid, var_nid, "defines", line)

                if var_type and var_type not in _DART_VAR_TYPE_BLACKLIST:
                    clean_type = var_type.split("<")[0].split(".")[-1].strip()
                    type_nid = _make_id(clean_type)
                    add_node(type_nid, clean_type, source_file=None)
                    add_edge(file_nid, type_nid, "references", line, context="variable_type")
        elif destructured_names:
            for name in [n.strip() for n in destructured_names.split(",") if n.strip()]:
                if ":" in name:
                    name = name.split(":")[-1].strip()
                if re.match(r"^[a-zA-Z_]\w*$", name) and not re.match(r"^[A-Z]", name):
                    if name not in _DART_STMT_KEYWORDS:
                        var_nid = _make_id(stem, name)
                        add_node(var_nid, name, line)
                        add_edge(file_nid, var_nid, "defines", line)

    for m in _DART_GENERIC_CALL_RE.finditer(src_clean):
        type_name = m.group(1).split(".")[-1].strip()
        clean_name = type_name.split("<")[0].strip()
        if clean_name not in _DART_GENERIC_CALL_BLACKLIST:
            target_nid = _make_id(clean_name)
            add_node(target_nid, clean_name, source_file=None)
            add_edge(file_nid, target_nid, "references", _line_of(m.start()), context="type_lookup")

    return {"nodes": nodes, "edges": edges}


def _extract_dart_regex(path: Path) -> dict:
    """Regex fallback: classes, mixins, functions, imports, generic calls, and annotations from a .dart file.

    The pre-tree-sitter implementation, preserved verbatim (no line anchors);
    used when tree-sitter-dart is not installed or fails to parse.
    """
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    # Remove inline and multi-line comments while leaving string literals untouched to prevent stripping URLs/paths inside strings
    comment_string_pattern = re.compile(
        r'"""(?:\\.|[\s\S])*?"""'
        r"|'''(?:\\.|[\s\S])*?'''"
        r'|"(?:\\.|[^"\\])*"'
        r"|'(?:\\.|[^'\\])*'"
        r"|/\*[\s\S]*?\*/"
        r"|//[^\n]*"
    )
    def _comment_replace(match: re.Match) -> str:
        token = match.group(0)
        if token.startswith("/"):
            return ""
        return token
    src_clean = comment_string_pattern.sub(_comment_replace, src)

    stem = _file_stem(path)
    file_nid = _make_id(str(path))

    # Check if this is a part-of file and redirect to parent
    part_of_match = re.search(r"^\s*part\s+of\s+['\"]([^'\"]+)['\"]", src_clean, re.MULTILINE)
    is_part = False
    if part_of_match:
        parent_ref = part_of_match.group(1)
        if parent_ref.endswith(".dart"):
            try:
                parent_path = (path.parent / parent_ref).resolve()
                if parent_path.exists():
                    stem = _file_stem(parent_path)
                    file_nid = _make_id(str(parent_path))
                    is_part = True
            except Exception:
                pass

    nodes = []
    if not is_part:
        nodes.append({"id": file_nid, "label": path.name, "file_type": "code",
                      "source_file": str(path), "source_location": None})
    edges = []
    defined: set[str] = set()

    def add_node(nid: str, label: str, ftype: str = "code", source_file: str | None = str(path)) -> None:
        if nid not in defined:
            nodes.append({"id": nid, "label": label, "file_type": ftype,
                          "source_file": source_file, "source_location": None})
            defined.add(nid)

    def add_edge(src_id: str, tgt_id: str, relation: str, weight: float = 1.0, context: str | None = None) -> None:
        edge = {"source": src_id, "target": tgt_id, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str(path), "source_location": None, "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    def _split_types(text: str) -> list[str]:
        parts = []
        current = []
        depth = 0
        for char in text:
            if char == "<":
                depth += 1
                current.append(char)
            elif char == ">":
                depth -= 1
                current.append(char)
            elif char == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        if current:
            parts.append("".join(current).strip())
        return [p for p in parts if p]

    def _find_matching_brace(text: str, start_pos: int) -> int:
        brace_count = 0
        in_double_quote = False
        in_single_quote = False
        escape = False

        first_brace = text.find("{", start_pos)
        if first_brace == -1:
            return len(text)

        brace_count = 1
        i = first_brace + 1
        n = len(text)
        while i < n:
            char = text[i]
            if escape:
                escape = False
                i += 1
                continue
            if char == "\\":
                escape = True
                i += 1
                continue
            if text[i:i+3] == '"""' and not in_single_quote:
                i += 3
                end = text.find('"""', i)
                i = end + 3 if end != -1 else n
                continue
            if text[i:i+3] == "'''" and not in_double_quote:
                i += 3
                end = text.find("'''", i)
                i = end + 3 if end != -1 else n
                continue
            if char == '"' and not in_single_quote:
                in_double_quote = not in_double_quote
            elif char == "'" and not in_double_quote:
                in_single_quote = not in_single_quote
            elif not in_double_quote and not in_single_quote:
                if char == "{":
                    brace_count += 1
                elif char == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        return i + 1
            i += 1
        return len(text)

    # 1. Classes, mixins, and enums declarations (with inheritance, mixins, interfaces, and generics)
    # Supports multiple combined modifiers (e.g., abstract base class, mixin class) without capturing "class" as a name
    class_pattern = r"^\s*(?:(?:abstract|sealed|base|interface|final|mixin)\s+)*(?:class|mixin|enum|extension\s+type)\s+(\w+)"
    for m in re.finditer(class_pattern, src_clean, re.MULTILINE):
        class_name = m.group(1)
        class_nid = _make_id(stem, class_name)
        add_node(class_nid, class_name)
        add_edge(file_nid, class_nid, "defines")

        # Manually parse extends/on, with, and implements in header to handle nested generics brackets balanced
        start_idx = m.end()
        rest = src_clean[start_idx : start_idx + 500]

        # Skip class generic parameters
        if rest.lstrip().startswith("<"):
            offset = rest.find("<")
            depth = 1
            i = offset + 1
            while i < len(rest) and depth > 0:
                if rest[i] == "<": depth += 1
                elif rest[i] == ">": depth -= 1
                i += 1
            rest = rest[i:]

        # Skip primary constructor (e.g. extension type MyExt(int id))
        if rest.lstrip().startswith("("):
            offset = rest.find("(")
            depth = 1
            i = offset + 1
            while i < len(rest) and depth > 0:
                if rest[i] == "(": depth += 1
                elif rest[i] == ")": depth -= 1
                i += 1
            rest = rest[i:]

        header_end = rest.find("{")
        if header_end == -1:
            header_end = rest.find(";")
        if header_end == -1:
            header_end = len(rest)
        header = rest[:header_end]

        base_class = None
        generics = None
        mixins_list = []
        interfaces_list = []

        # Parse extends or on
        extends_m = re.search(r"^\s*(?:extends|on)\s+([a-zA-Z0-9_.]+)", header)
        if extends_m:
            base_class = extends_m.group(1)
            rest_header = header[extends_m.end():]
            if rest_header.strip().startswith("<"):
                start_idx = rest_header.find("<")
                depth = 1
                i = start_idx + 1
                while i < len(rest_header) and depth > 0:
                    if rest_header[i] == "<":
                        depth += 1
                    elif rest_header[i] == ">":
                        depth -= 1
                        if depth == 0:
                            generics = rest_header[start_idx + 1 : i]
                            break
                    i += 1
                if generics is not None:
                    header = rest_header[i + 1:]
                else:
                    header = rest_header
            else:
                header = rest_header

        # Parse with
        with_m = re.search(r"^\s*with\s+", header)
        if with_m:
            rest_header = header[with_m.end():]
            impl_idx = rest_header.find("implements")
            if impl_idx != -1:
                mixins_str = rest_header[:impl_idx]
                header = rest_header[impl_idx:]
            else:
                mixins_str = rest_header
                header = ""
            mixins_list = _split_types(mixins_str)

        # Parse implements
        impl_m = re.search(r"^\s*implements\s+", header)
        if impl_m:
            interfaces_list = _split_types(header[impl_m.end():])

        # Map extends inheritance relation
        if base_class:
            base_nid = _make_id(base_class)
            add_node(base_nid, base_class, source_file=None)
            add_edge(class_nid, base_nid, "inherits")

            # Map generic type arguments (e.g. MyBloc extends Bloc<MyEvent, MyState>)
            if generics:
                for gen in _split_types(generics):
                    gen_clean = gen.split("<")[0].strip()
                    if gen_clean not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                        gen_nid = _make_id(gen_clean)
                        add_node(gen_nid, gen_clean, source_file=None)
                        add_edge(class_nid, gen_nid, "references")

        # Map mixins
        for mixin in mixins_list:
            mixin_clean = mixin.split("<")[0].strip()
            mixin_nid = _make_id(mixin_clean)
            add_node(mixin_nid, mixin_clean, source_file=None)
            add_edge(class_nid, mixin_nid, "mixes_in")

        # Map interfaces
        for interface in interfaces_list:
            interface_clean = interface.split("<")[0].strip()
            interface_nid = _make_id(interface_clean)
            add_node(interface_nid, interface_clean, source_file=None)
            add_edge(class_nid, interface_nid, "implements")

        # Extract class body for precise framework dependencies and event handling
        start_idx = m.start()
        brace_pos = src_clean.find("{", start_idx)
        semi_pos = src_clean.find(";", start_idx)

        has_body = brace_pos != -1
        if has_body and semi_pos != -1 and semi_pos < brace_pos:
            has_body = False

        if has_body:
            end_pos = _find_matching_brace(src_clean, start_idx)
            class_body = src_clean[brace_pos:end_pos]

            # Bloc event registration: on<MyEvent>()
            for em in re.finditer(r"\bon<(\w+)>\s*\(", class_body):
                event_name = em.group(1)
                event_nid = _make_id(event_name)
                add_node(event_nid, event_name, source_file=None)
                add_edge(class_nid, event_nid, "calls", context="bloc_event")

            # Bloc state emissions: emit(MyState) or yield MyState
            for sm in re.finditer(r"\b(?:emit|yield)\s*\(?\s*(?:const\s+)?([A-Z]\w*)\b", class_body):
                state_name = sm.group(1)
                if state_name not in {"String", "List", "Map", "Set", "Future", "Stream", "Object"}:
                    state_nid = _make_id(state_name)
                    add_node(state_nid, state_name, source_file=None)
                    add_edge(class_nid, state_nid, "calls", context="emit_state")

            # Bloc event additions: widget.add(MyEvent()) or bloc.add(MyEvent())
            for am in re.finditer(r"\b(?:\w*[Bb]loc\w*|context\.read<\w+>\(\))\.add\(\s*(?:const\s+)?([A-Z]\w*)\b", class_body):
                event_name = am.group(1)
                if event_name not in {"String", "List", "Map", "Set", "Future", "Stream", "Object"}:
                    event_nid = _make_id(event_name)
                    add_node(event_nid, event_name, source_file=None)
                    add_edge(class_nid, event_nid, "calls", context="bloc_add_event")

            # Riverpod provider references: ref.watch(provider)
            for rm in re.finditer(r"\bref\.(?:watch|read|listen)\s*\(\s*(\w+)\b", class_body):
                provider_name = rm.group(1)
                provider_nid = _make_id(provider_name)
                add_node(provider_nid, provider_name, source_file=None)
                add_edge(class_nid, provider_nid, "references", context="riverpod_reference")

            # Widget to Bloc references: BlocBuilder<MyBloc, ...>
            for bm in re.finditer(r"\bBloc(?:Builder|Listener|Consumer|Provider|Selector)\s*<\s*([a-zA-Z0-9_]+)\b", class_body):
                bloc_name = bm.group(1)
                if bloc_name not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                    bloc_nid = _make_id(bloc_name)
                    add_node(bloc_nid, bloc_name, source_file=None)
                    add_edge(class_nid, bloc_nid, "references", context="bloc_widget_binding")

            # context.read<MyBloc>() or BlocProvider.of<MyBloc>(context)
            for lm in re.finditer(r"\b(?:read|watch|select|of)\s*<([a-zA-Z0-9_]+)>", class_body):
                bloc_name = lm.group(1)
                if bloc_name not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                    bloc_nid = _make_id(bloc_name)
                    add_node(bloc_nid, bloc_name, source_file=None)
                    add_edge(class_nid, bloc_nid, "references", context="bloc_lookup")

    # 2. Annotations mapping (class, mixin, enum, or function level annotations)
    # Support: @riverpod, @Riverpod(...), @injectable, @singleton, @RoutePage(), @HiveType(typeId: 0), @RestApi()
    # Matches `@annotation` and links it to the next class/mixin/enum/function declaration in the file
    annotation_pattern = r"@(\w+)(?:\([^)]*\))?"
    for am in re.finditer(annotation_pattern, src_clean):
        annotation_name = am.group(1)
        if annotation_name in {"override", "deprecated", "required", "protected", "mustCallSuper"}:
            continue
        annotation_pos = am.end()
        intervening_text = src_clean[annotation_pos : annotation_pos + 300]

        class_m = re.search(r"^\s*(?:(?:abstract|sealed|base|interface|final|mixin)\s+)*(?:class|mixin|enum|extension\s+type)\s+(\w+)", intervening_text, re.MULTILINE)
        func_m = re.search(r"^\s*(?:factory\s+|static\s+|async\s+|external\s+|abstract\s+)?(?:\([^)]+\)|[a-zA-Z0-9_<>,.?]+)(?:\s+[a-zA-Z0-9_<>,.?]+){0,3}\s+(\w+)\s*\(", intervening_text, re.MULTILINE)

        target_nid = None
        target_name = None
        target_type = None

        if class_m and func_m:
            if class_m.start() < func_m.start():
                target_name = class_m.group(1)
                target_type = "class"
                target_nid = _make_id(stem, target_name)
            else:
                target_name = func_m.group(1)
                target_type = "function"
                target_nid = _make_id(stem, target_name)
        elif class_m:
            target_name = class_m.group(1)
            target_type = "class"
            target_nid = _make_id(stem, target_name)
        elif func_m:
            target_name = func_m.group(1)
            target_type = "function"
            target_nid = _make_id(stem, target_name)

        if target_nid and target_name:
            actual_intervening = intervening_text[:min(class_m.start() if class_m else 300, func_m.start() if func_m else 300)]
            if ";" not in actual_intervening and "}" not in actual_intervening and "{" not in actual_intervening:
                annotation_nid = _make_id("annotation", annotation_name.lower())
                add_node(annotation_nid, f"@{annotation_name}", ftype="concept", source_file=None)
                add_edge(target_nid, annotation_nid, "configures")

                # Riverpod specific provider generation mapping (supports camelCase class and functional providers)
                if annotation_name.lower() == "riverpod":
                     if target_type == "class":
                         provider_name = target_name[0].lower() + target_name[1:] + "Provider" if len(target_name) > 1 else target_name.lower() + "Provider"
                     else:
                         provider_name = target_name + "Provider"
                     provider_nid = _make_id(provider_name)
                     add_node(provider_nid, provider_name, ftype="concept", source_file=str(path))
                     add_edge(target_nid, provider_nid, "defines", context="riverpod_provider")

    # 2.5 Typedefs (Type Aliases)
    typedef_pattern = r"^\s*typedef\s+(\w+)\s*(?:<[^>]+>)?\s*=\s*([a-zA-Z0-9_<>,.?\s]+);"
    for m in re.finditer(typedef_pattern, src_clean, re.MULTILINE):
        typedef_name = m.group(1)
        target_type = m.group(2).split("<")[0].split(".")[-1].strip()
        if target_type not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "List", "Map", "Set", "void", "Function"}:
            typedef_nid = _make_id(stem, typedef_name)
            add_node(typedef_nid, typedef_name)
            add_edge(file_nid, typedef_nid, "defines")
            target_nid = _make_id(target_type)
            add_node(target_nid, target_type, source_file=None)
            add_edge(typedef_nid, target_nid, "references", context="typedef")

    # 3. Extensions (extension MyExt on MyClass)
    ext_pattern = r"^\s{0,4}extension\s+(\w+)?(?:<[^>]+>)?\s+on\s+(\w+)"
    for m in re.finditer(ext_pattern, src_clean, re.MULTILINE):
        ext_name = m.group(1) or f"{stem}_anonymous_extension"
        target_class = m.group(2)

        ext_nid = _make_id(stem, ext_name)
        label = m.group(1) or f"Extension on {target_class}"
        add_node(ext_nid, label)
        add_edge(file_nid, ext_nid, "defines")

        target_nid = _make_id(target_class)
        add_node(target_nid, target_class, source_file=None)
        add_edge(ext_nid, target_nid, "extends")

    # 4. Top-level and class-level variable declarations (generic variables, records, late, and destructuring)
    # Restrict indentation to 0-2 spaces to avoid matching local variables inside functions or switch expressions
    var_pattern = r"^\s{0,2}(?:late\s+)?(?:(?:final|const|var)\s+)?(?:\([^)]+\)\s+|([a-zA-Z0-9_<>,.?]+(?:\s+[a-zA-Z0-9_<>,.?]+){0,3})\s+)?(?:(\w+)|(?:\w+\s*)?\(([^)]+)\))\s*(?:=|$|;)"
    for m in re.finditer(var_pattern, src_clean, re.MULTILINE):
        var_type = m.group(1)
        single_name = m.group(2)
        destructured_names = m.group(3)

        if not re.match(r"^\s*(?:late|final|const|var)\b", m.group(0)) and not var_type:
            continue

        if single_name:
            if single_name not in {"if", "for", "while", "switch", "catch", "return"}:
                var_nid = _make_id(stem, single_name)
                add_node(var_nid, single_name)
                add_edge(file_nid, var_nid, "defines")

                if var_type and var_type not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "List", "Map", "Set", "void"}:
                    clean_type = var_type.split("<")[0].split(".")[-1].strip()
                    type_nid = _make_id(clean_type)
                    add_node(type_nid, clean_type, source_file=None)
                    add_edge(file_nid, type_nid, "references", context="variable_type")
        elif destructured_names:
            for name in [n.strip() for n in destructured_names.split(",") if n.strip()]:
                if ":" in name:
                    name = name.split(":")[-1].strip()
                if re.match(r"^[a-zA-Z_]\w*$", name) and not re.match(r"^[A-Z]", name):
                    if name not in {"if", "for", "while", "switch", "catch", "return"}:
                        var_nid = _make_id(stem, name)
                        add_node(var_nid, name)
                        add_edge(file_nid, var_nid, "defines")

    # 5. Top-level and member functions/methods (supports typed/generic/record return types and Riverpod/Bloc references)
    # Restrict indentation to 0-2 spaces to avoid matching nested local functions or methods inside multiline switch statements
    method_pattern = r"^\s{0,2}(?:factory\s+|static\s+|async\s+|external\s+|abstract\s+)?(?:\([^)]+\)|[a-zA-Z0-9_<>,.?]+)(?:\s+[a-zA-Z0-9_<>,.?]+){0,3}\s+(\w+(?:\.\w+)?)\s*\("
    for m in re.finditer(method_pattern, src_clean, re.MULTILINE):
        raw_name = m.group(1)
        name = raw_name.split(".")[-1]
        if name in {"if", "for", "while", "switch", "catch", "return", "void", "dynamic", "final", "const", "get", "set"}:
            continue
        if re.match(r"^[A-Z]", name):
            continue
        nid = _make_id(stem, name)
        add_node(nid, name)
        add_edge(file_nid, nid, "defines")

        # Get function body using matching brace to extract Riverpod reference patterns
        start_idx = m.start()
        brace_pos = src_clean.find("{", start_idx)
        semi_pos = src_clean.find(";", start_idx)
        arrow_pos = src_clean.find("=>", start_idx)

        has_body = brace_pos != -1
        if has_body and semi_pos != -1 and semi_pos < brace_pos:
            has_body = False
        if has_body and arrow_pos != -1 and arrow_pos < brace_pos:
            has_body = False

        if has_body:
            end_pos = _find_matching_brace(src_clean, start_idx)
            func_body = src_clean[brace_pos:end_pos]

            # Extract Riverpod provider references: ref.watch(provider)
            for rm in re.finditer(r"\bref\.(?:watch|read|listen)\s*\(\s*(\w+)\b", func_body):
                provider_name = rm.group(1)
                provider_nid = _make_id(provider_name)
                add_node(provider_nid, provider_name, source_file=None)
                add_edge(nid, provider_nid, "references", context="riverpod_reference")

            # Extract Bloc event additions: widget.add(MyEvent()) or bloc.add(MyEvent())
            for am in re.finditer(r"\b(?:\w*[Bb]loc\w*|context\.read<\w+>\(\))\.add\(\s*(?:const\s+)?([A-Z]\w*)\b", func_body):
                event_name = am.group(1)
                if event_name not in {"String", "List", "Map", "Set", "Future", "Stream", "Object"}:
                    event_nid = _make_id(event_name)
                    add_node(event_nid, event_name, source_file=None)
                    add_edge(nid, event_nid, "calls", context="bloc_add_event")

            # context.read<MyBloc>() or BlocProvider.of<MyBloc>(context)
            for lm in re.finditer(r"\b(?:read|watch|select|of)\s*<([a-zA-Z0-9_]+)>", func_body):
                bloc_name = lm.group(1)
                if bloc_name not in {"String", "int", "double", "bool", "num", "dynamic", "Object", "void"}:
                    bloc_nid = _make_id(bloc_name)
                    add_node(bloc_nid, bloc_name, source_file=None)
                    add_edge(nid, bloc_nid, "references", context="bloc_lookup")

            # Universal Navigation Patters (GoRouter, AutoRoute, Navigator)
            for nm in re.finditer(r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?['\"]([a-zA-Z0-9_/?=&%-]+)['\"]", func_body):
                route_path = nm.group(1)
                route_nid = _make_id("route", route_path.replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_"))
                add_node(route_nid, f"Route {route_path}", ftype="concept", source_file=None)
                add_edge(nid, route_nid, "navigates", context="route_path")

            for cm in re.finditer(r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?([A-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9_]+)", func_body):
                route_const = cm.group(1)
                route_nid = _make_id("route", route_const.replace(".", "_"))
                add_node(route_nid, route_const, ftype="concept", source_file=None)
                add_edge(nid, route_nid, "navigates", context="route_const")

            for om in re.finditer(r"\b(?:push|replace)\s*\(\s*(?:context\s*,\s*)?.*?\b([A-Z]\w*(?:Route|Screen|Page))\b", func_body):
                route_class = om.group(1)
                route_nid = _make_id(route_class)
                add_node(route_nid, route_class, source_file=None)
                add_edge(nid, route_nid, "navigates", context="route_object")

    # 6. Imports and Exports
    for m in re.finditer(r"""^\s*import\s+['"]([^'"]+)['"]""", src_clean, re.MULTILINE):
        pkg = m.group(1)
        tgt_nid = _make_id(pkg)
        add_node(tgt_nid, pkg, source_file=None)
        add_edge(file_nid, tgt_nid, "imports")

    for m in re.finditer(r"""^\s*export\s+['"]([^'"]+)['"]""", src_clean, re.MULTILINE):
        pkg = m.group(1)
        tgt_nid = _make_id(pkg)
        add_node(tgt_nid, pkg, source_file=None)
        add_edge(file_nid, tgt_nid, "exports")

    # 7. Generic Invocations / Type Lookups (Universal Dependency Lookup)
    # Matches any method call with type parameters: methodName<Type>() or object.methodName<Type>()
    # Automatically extracts GetIt, Injectable, Riverpod, Provider, BlocProvider, and InheritedWidget type lookups!
    generic_call_pattern = r"\b\w+<([a-zA-Z0-9_.]+(?:<[a-zA-Z0-9_.,\s<>]+>)?)\s*>\s*\("
    type_blacklist = {"String", "int", "double", "bool", "num", "dynamic", "Object", "List", "Map", "Set", "Future", "Stream", "void"}
    for m in re.finditer(generic_call_pattern, src_clean):
        type_name = m.group(1).split(".")[-1].strip()
        clean_name = type_name.split("<")[0].strip()
        if clean_name not in type_blacklist:
            target_nid = _make_id(clean_name)
            add_node(target_nid, clean_name, source_file=None)
            add_edge(file_nid, target_nid, "references", context="type_lookup")

    return {"nodes": nodes, "edges": edges}
