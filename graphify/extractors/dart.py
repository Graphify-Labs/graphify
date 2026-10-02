"""Dart extractor — tree-sitter AST walk with Flutter heuristic edges."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id, _read_text

_DART_BUILTIN_TYPES = frozenset({
    "String", "int", "double", "bool", "num", "dynamic", "Object", "void",
    "List", "Map", "Set", "Future", "Stream", "Iterable", "Iterator",
    "Null", "Never", "Function", "Record", "Symbol", "Type",
})

_ANNOTATION_SKIP = frozenset({
    "override", "deprecated", "required", "protected", "mustCallSuper",
    "visibleForTesting", "immutable", "nonVirtual", "mustBeOverridden",
})

_METHOD_NAME_SKIP = frozenset({
    "if", "for", "while", "switch", "catch", "return", "void", "dynamic",
    "final", "const", "get", "set", "var", "late", "typedef", "factory",
})


def _line_of(node) -> int:
    return node.start_point[0] + 1


def _strip_quotes(text: str) -> str:
    text = text.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in "'\"":
        return text[1:-1]
    return text


def _type_blacklist_ok(name: str) -> bool:
    return bool(name) and name not in _DART_BUILTIN_TYPES


def _collect_top_type_names(node, source: bytes) -> list[str]:
    """Collect top-level type names from a type node, preserving foo.Bar quals.

    Does not flatten nested type_arguments (Bloc<Pair<A,B>, C> → Pair, C only).
    """
    if node is None:
        return []
    names: list[str] = []

    def walk_type(n) -> None:
        if n is None:
            return
        if n.type == "type_arguments":
            # Only direct type children of this argument list.
            i = 0
            children = [c for c in n.children if c.is_named or c.type == "."]
            while i < len(children):
                c = children[i]
                if c.type == "type_identifier":
                    parts = [_read_text(c, source)]
                    j = i + 1
                    while j + 1 < len(children) and children[j].type == "." and children[j + 1].type == "type_identifier":
                        parts.append(_read_text(children[j + 1], source))
                        j += 2
                    names.append(".".join(parts))
                    # Skip nested type_arguments belonging to this type.
                    if j < len(children) and children[j].type == "type_arguments":
                        j += 1
                    i = j
                    continue
                if c.type == "type_arguments":
                    i += 1
                    continue
                if c.is_named:
                    walk_type(c)
                i += 1
            return
        if n.type == "type_identifier":
            # Lone identifier (no args) — handled by callers joining quals.
            return
        for c in n.children:
            if c.is_named or c.type == ".":
                if c.type == "type_arguments":
                    walk_type(c)
                elif c.type not in ("type_identifier", "."):
                    walk_type(c)

    if node.type == "type_arguments":
        walk_type(node)
        return names

    # Qualified / simple type: join type_identifier(.type_identifier)* then args.
    children = list(node.children)
    i = 0
    while i < len(children):
        c = children[i]
        if c.type == "type_identifier":
            parts = [_read_text(c, source)]
            j = i + 1
            while j + 1 < len(children) and children[j].type == "." and children[j + 1].type == "type_identifier":
                parts.append(_read_text(children[j + 1], source))
                j += 2
            names.append(".".join(parts))
            if j < len(children) and children[j].type == "type_arguments":
                walk_type(children[j])
                j += 1
            i = j
            continue
        if c.type == "type_arguments":
            walk_type(c)
        elif c.is_named:
            walk_type(c)
        i += 1
    return names


def _first_identifier(node, source: bytes) -> str | None:
    if node is None:
        return None
    if node.type == "identifier":
        return _read_text(node, source)
    for c in node.children:
        if c.type == "identifier":
            return _read_text(c, source)
        if c.is_named:
            found = _first_identifier(c, source)
            if found:
                return found
    return None


def _qualified_type_before(node, source: bytes) -> str | None:
    """Rebuild auth.AuthService from sibling type_identifier / . nodes before node."""
    parent = node.parent
    if parent is None:
        return None
    siblings = list(parent.children)
    try:
        idx = siblings.index(node)
    except ValueError:
        return None
    parts: list[str] = []
    i = idx - 1
    # Walk left over type_identifier and '.' 
    buf: list[str] = []
    while i >= 0:
        s = siblings[i]
        if s.type == "type_identifier":
            buf.append(_read_text(s, source))
            i -= 1
            continue
        if s.type == ".":
            i -= 1
            continue
        if s.type in ("type_arguments",):
            i -= 1
            continue
        break
    if not buf:
        return None
    buf.reverse()
    return ".".join(buf)


def _apply_flutter_heuristics(
    body_text: str,
    body_start_line: int,
    owner_nid: str,
    add_node,
    add_edge,
    *,
    attribute_generic_lookups_to: str | None = None,
) -> None:
    """Bloc / Riverpod / navigation edges from body source text."""
    if not body_text:
        return

    def _line_at(offset: int) -> int:
        return body_start_line + body_text[:offset].count("\n")

    for em in re.finditer(r"\bon<(\w+)>\s*\(", body_text):
        event_name = em.group(1)
        event_nid = _make_id(event_name)
        add_node(event_nid, event_name, source_file=None, line=None)
        add_edge(owner_nid, event_nid, "calls", line=_line_at(em.start(1)), context="bloc_event")

    for sm in re.finditer(r"\b(?:emit|yield)\s*\(?\s*(?:const\s+)?([A-Z]\w*)\b", body_text):
        state_name = sm.group(1)
        if state_name not in _DART_BUILTIN_TYPES:
            state_nid = _make_id(state_name)
            add_node(state_nid, state_name, source_file=None, line=None)
            add_edge(owner_nid, state_nid, "calls", line=_line_at(sm.start(1)), context="emit_state")

    for am in re.finditer(
        r"\b(?:\w*[Bb]loc\w*|context\.read<\w+>\(\))\.add\(\s*(?:const\s+)?([A-Z]\w*)\b",
        body_text,
    ):
        event_name = am.group(1)
        if event_name not in _DART_BUILTIN_TYPES:
            event_nid = _make_id(event_name)
            add_node(event_nid, event_name, source_file=None, line=None)
            add_edge(owner_nid, event_nid, "calls", line=_line_at(am.start(1)), context="bloc_add_event")

    for rm in re.finditer(r"\bref\.(?:watch|read|listen)\s*\(\s*(\w+)\b", body_text):
        provider_name = rm.group(1)
        provider_nid = _make_id(provider_name)
        add_node(provider_nid, provider_name, source_file=None, line=None)
        add_edge(
            owner_nid, provider_nid, "references",
            line=_line_at(rm.start(1)), context="riverpod_reference",
        )

    for bm in re.finditer(
        r"\bBloc(?:Builder|Listener|Consumer|Provider|Selector)\s*<\s*([a-zA-Z0-9_]+)\b",
        body_text,
    ):
        bloc_name = bm.group(1)
        if _type_blacklist_ok(bloc_name):
            bloc_nid = _make_id(bloc_name)
            add_node(bloc_nid, bloc_name, source_file=None, line=None)
            add_edge(
                owner_nid, bloc_nid, "references",
                line=_line_at(bm.start(1)), context="bloc_widget_binding",
            )

    for lm in re.finditer(r"\b(?:read|watch|select|of)\s*<([a-zA-Z0-9_]+)>", body_text):
        bloc_name = lm.group(1)
        if _type_blacklist_ok(bloc_name):
            bloc_nid = _make_id(bloc_name)
            add_node(bloc_nid, bloc_name, source_file=None, line=None)
            add_edge(
                owner_nid, bloc_nid, "references",
                line=_line_at(lm.start(1)), context="bloc_lookup",
            )

    for nm in re.finditer(
        r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?['\"]([a-zA-Z0-9_/?=&%-]+)['\"]",
        body_text,
    ):
        route_path = nm.group(1)
        route_nid = _make_id(
            "route",
            route_path.replace("/", "_").replace("?", "_").replace("=", "_").replace("&", "_"),
        )
        add_node(route_nid, f"Route {route_path}", ftype="concept", source_file=None, line=None)
        add_edge(owner_nid, route_nid, "navigates", line=_line_at(nm.start(1)), context="route_path")

    for cm in re.finditer(
        r"\b(?:go|push|goNamed|pushNamed|replace|replaceNamed)\s*\(\s*(?:context\s*,\s*)?([A-Z][a-zA-Z0-9_]*\.[a-zA-Z0-9_]+)",
        body_text,
    ):
        route_const = cm.group(1)
        route_nid = _make_id("route", route_const.replace(".", "_"))
        add_node(route_nid, route_const, ftype="concept", source_file=None, line=None)
        add_edge(owner_nid, route_nid, "navigates", line=_line_at(cm.start(1)), context="route_const")

    for om in re.finditer(
        r"\b(?:push|replace)\s*\(\s*(?:context\s*,\s*)?.*?\b([A-Z]\w*(?:Route|Screen|Page))\b",
        body_text,
    ):
        route_class = om.group(1)
        route_nid = _make_id(route_class)
        add_node(route_nid, route_class, source_file=None, line=None)
        add_edge(owner_nid, route_nid, "navigates", line=_line_at(om.start(1)), context="route_object")

    # Universal generic invocations → file-level type lookups (legacy contract).
    if attribute_generic_lookups_to is not None:
        generic_call_pattern = r"\b\w+<([a-zA-Z0-9_.]+(?:<[a-zA-Z0-9_.,\s<>]+>)?)\s*>\s*\("
        for m in re.finditer(generic_call_pattern, body_text):
            type_name = m.group(1).split(".")[-1].strip()
            clean_name = type_name.split("<")[0].strip()
            if _type_blacklist_ok(clean_name):
                target_nid = _make_id(clean_name)
                add_node(target_nid, clean_name, source_file=None, line=None)
                add_edge(
                    attribute_generic_lookups_to, target_nid, "references",
                    line=_line_at(m.start(1)), context="type_lookup",
                )


def extract_dart(path: Path) -> dict:
    """Extract Dart/Flutter symbols via tree-sitter AST (+ Flutter body heuristics)."""
    try:
        import tree_sitter_dart as tsdart
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-dart not installed"}

    try:
        source = path.read_bytes()
        language = Language(tsdart.language())
        parser = Parser(language)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object, bool]] = []  # nid, body_node, is_top_level

    def add_node(
        nid: str,
        label: str,
        *,
        ftype: str = "code",
        source_file: str | None = str_path,
        line: int | None = None,
    ) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        nodes.append({
            "id": nid,
            "label": label,
            "file_type": ftype,
            "source_file": source_file,
            "source_location": f"L{line}" if line is not None else None,
        })

    def add_edge(
        src: str,
        tgt: str,
        relation: str,
        *,
        line: int | None = None,
        confidence: str = "EXTRACTED",
        weight: float = 1.0,
        context: str | None = None,
    ) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "confidence_score": 1.0 if confidence == "EXTRACTED" else 0.5,
            "source_file": str_path,
            "source_location": f"L{line}" if line is not None else None,
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    def ensure_external(name: str) -> str:
        nid = _make_id(name)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": None,
                "source_location": None,
            })
        return nid

    # --- part of redirect ---
    is_part = False
    file_nid = _make_id(str(path))

    def _find_part_of(node) -> str | None:
        if node.type == "part_of_directive":
            for c in node.children:
                if c.type == "uri":
                    return _strip_quotes(_read_text(c, source))
        for c in node.children:
            found = _find_part_of(c)
            if found:
                return found
        return None

    part_ref = _find_part_of(root)
    if part_ref and part_ref.endswith(".dart"):
        try:
            parent_path = (path.parent / part_ref).resolve()
            if parent_path.exists():
                stem = _file_stem(parent_path)
                file_nid = _make_id(str(parent_path))
                is_part = True
        except Exception:
            pass

    if not is_part:
        add_node(file_nid, path.name, source_file=str_path, line=None)

    def emit_annotation_edges(ann_node, target_nid: str, target_name: str, target_kind: str) -> None:
        name = None
        for c in ann_node.children:
            if c.type == "identifier":
                name = _read_text(c, source)
                break
        if not name or name in _ANNOTATION_SKIP:
            return
        line = _line_of(ann_node)
        annotation_nid = _make_id("annotation", name.lower())
        add_node(annotation_nid, f"@{name}", ftype="concept", source_file=None, line=None)
        add_edge(target_nid, annotation_nid, "configures", line=line)
        if name.lower() == "riverpod":
            if target_kind == "class":
                provider_name = (
                    target_name[0].lower() + target_name[1:] + "Provider"
                    if len(target_name) > 1
                    else target_name.lower() + "Provider"
                )
            else:
                provider_name = target_name + "Provider"
            provider_nid = _make_id(provider_name)
            add_node(provider_nid, provider_name, ftype="concept", source_file=str_path, line=line)
            add_edge(target_nid, provider_nid, "defines", line=line, context="riverpod_provider")

    def emit_heritage(type_nid: str, type_node, line: int) -> None:
        """Process superclass / mixins / interfaces children of a type decl."""
        for child in type_node.children:
            if child.type == "superclass":
                # extends or on
                relation = "inherits"
                # Prefer joining leading type_identifiers.
                parts: list[str] = []
                saw_args = False
                generic_names: list[str] = []
                kids = list(child.children)
                i = 0
                while i < len(kids):
                    c = kids[i]
                    if c.type in ("extends", "on"):
                        i += 1
                        continue
                    if c.type == "type_identifier" and not saw_args:
                        parts.append(_read_text(c, source))
                        i += 1
                        continue
                    if c.type == "." and not saw_args:
                        i += 1
                        continue
                    if c.type == "type_arguments":
                        saw_args = True
                        generic_names = _collect_top_type_names(c, source)
                        i += 1
                        continue
                    if c.type == "mixins":
                        break
                    i += 1
                if parts:
                    base = ".".join(parts)
                    base_nid = ensure_external(base)
                    add_edge(type_nid, base_nid, relation, line=line)
                    for gen in generic_names:
                        gen_clean = gen.split("<")[0].strip()
                        if _type_blacklist_ok(gen_clean.split(".")[-1]):
                            # Use full gen for id if dotted, else simple.
                            gen_nid = ensure_external(gen_clean)
                            add_edge(type_nid, gen_nid, "references", line=line)
                # mixins nested under superclass
                for c in child.children:
                    if c.type == "mixins":
                        for mname in _collect_top_type_names(c, source):
                            if _type_blacklist_ok(mname.split(".")[-1]):
                                mnid = ensure_external(mname)
                                add_edge(type_nid, mnid, "mixes_in", line=line)
            elif child.type == "mixins":
                for mname in _collect_top_type_names(child, source):
                    if _type_blacklist_ok(mname.split(".")[-1]):
                        mnid = ensure_external(mname)
                        add_edge(type_nid, mnid, "mixes_in", line=line)
            elif child.type == "interfaces":
                for iname in _collect_top_type_names(child, source):
                    if _type_blacklist_ok(iname.split(".")[-1]) or iname == "Object":
                        # Object is allowed for extension type implements Object
                        inid = ensure_external(iname)
                        add_edge(type_nid, inid, "implements", line=line)

        # mixin_declaration uses bare `on Type` as siblings, not superclass wrapper
        if type_node.type == "mixin_declaration":
            kids = list(type_node.children)
            for i, c in enumerate(kids):
                if c.type == "on" and i + 1 < len(kids) and kids[i + 1].type == "type_identifier":
                    # may be qualified
                    parts = [_read_text(kids[i + 1], source)]
                    j = i + 2
                    while j + 1 < len(kids) and kids[j].type == "." and kids[j + 1].type == "type_identifier":
                        parts.append(_read_text(kids[j + 1], source))
                        j += 2
                    base = ".".join(parts)
                    base_nid = ensure_external(base)
                    add_edge(type_nid, base_nid, "inherits", line=line)

    def handle_class_body(body_node, class_nid: str, class_name: str) -> None:
        if body_node is None:
            return
        children = list(body_node.children)
        i = 0
        pending_annotations: list = []
        while i < len(children):
            child = children[i]
            if child.type == "annotation":
                pending_annotations.append(child)
                i += 1
                continue

            if child.type == "declaration":
                # field or constructor
                ctor = None
                for c in child.children:
                    if c.type in (
                        "constructor_signature",
                        "constant_constructor_signature",
                        "factory_constructor_signature",
                        "redirecting_factory_constructor_signature",
                    ):
                        ctor = c
                        break
                if ctor is not None:
                    # Skip primary constructors named after the class; keep factories.
                    if ctor.type in ("factory_constructor_signature", "redirecting_factory_constructor_signature"):
                        idents = [c for c in ctor.children if c.type == "identifier"]
                        # factory MyService.fromJson → last identifier is fromJson
                        if len(idents) >= 2:
                            fname = _read_text(idents[-1], source)
                        elif len(idents) == 1:
                            fname = _read_text(idents[0], source)
                        else:
                            fname = None
                        if fname and fname not in _METHOD_NAME_SKIP and not re.match(r"^[A-Z]", fname):
                            line = _line_of(ctor)
                            mnid = _make_id(stem, class_name, fname)
                            add_node(mnid, fname, line=line)
                            add_edge(class_nid, mnid, "defines", line=line)
                            for ann in pending_annotations:
                                emit_annotation_edges(ann, mnid, fname, "function")
                    pending_annotations = []
                    i += 1
                    continue

                # Field declaration
                # Prefer last qualified type before identifier list
                id_list = None
                for c in child.children:
                    if c.type in ("initialized_identifier_list",):
                        id_list = c
                if id_list is not None:
                    # Collect type: type_identifiers before the list
                    parts: list[str] = []
                    for c in child.children:
                        if c is id_list:
                            break
                        if c.type == "type_identifier":
                            parts.append(_read_text(c, source))
                        elif c.type == ".":
                            continue
                        elif c.type == "type_arguments":
                            continue
                    var_type = ".".join(parts) if parts else None
                    for ini in id_list.children:
                        if ini.type != "initialized_identifier":
                            continue
                        ident = next((x for x in ini.children if x.type == "identifier"), None)
                        if not ident:
                            continue
                        vname = _read_text(ident, source)
                        if not vname or vname in _METHOD_NAME_SKIP:
                            continue
                        line = _line_of(ident)
                        vnid = _make_id(stem, class_name, vname)
                        add_node(vnid, vname, line=line)
                        add_edge(class_nid, vnid, "defines", line=line)
                        # Also file-level define edge for legacy field discovery
                        add_edge(file_nid, vnid, "defines", line=line)
                        if var_type:
                            clean = var_type.split("<")[0].split(".")[-1].strip()
                            if _type_blacklist_ok(clean):
                                tid = ensure_external(clean)
                                add_edge(
                                    file_nid, tid, "references",
                                    line=line, context="variable_type",
                                )
                pending_annotations = []
                i += 1
                continue

            if child.type == "method_signature":
                body = children[i + 1] if i + 1 < len(children) and children[i + 1].type == "function_body" else None
                sig = child
                fname = None
                for c in sig.children:
                    if c.type == "factory_constructor_signature":
                        idents = [x for x in c.children if x.type == "identifier"]
                        if len(idents) >= 2:
                            fname = _read_text(idents[-1], source)
                        elif idents:
                            fname = _read_text(idents[0], source)
                    elif c.type in ("function_signature", "getter_signature", "setter_signature", "method_signature"):
                        # nested
                        for x in c.children:
                            if x.type == "identifier":
                                # last identifier before params tends to be the name
                                pass
                        idents = [x for x in c.children if x.type == "identifier"]
                        if idents:
                            fname = _read_text(idents[-1], source)
                    elif c.type == "identifier":
                        fname = _read_text(c, source)

                # function_signature directly under method_signature
                fs = next((c for c in sig.children if c.type == "function_signature"), None)
                if fs is not None:
                    idents = [x for x in fs.children if x.type == "identifier"]
                    if idents:
                        fname = _read_text(idents[-1], source)
                gs = next((c for c in sig.children if c.type == "getter_signature"), None)
                if gs is not None:
                    idents = [x for x in gs.children if x.type == "identifier"]
                    if idents:
                        fname = _read_text(idents[-1], source)

                if fname and fname not in _METHOD_NAME_SKIP and not re.match(r"^[A-Z]", fname):
                    line = _line_of(sig)
                    mnid = _make_id(stem, class_name, fname)
                    add_node(mnid, fname, line=line)
                    add_edge(class_nid, mnid, "defines", line=line)
                    # Legacy: also file→defines so label-based tools still see membership weakly
                    add_edge(file_nid, mnid, "defines", line=line)
                    for ann in pending_annotations:
                        emit_annotation_edges(ann, mnid, fname, "function")
                    if body is not None:
                        function_bodies.append((mnid, body, False))
                        body_text = _read_text(body, source)
                        _apply_flutter_heuristics(
                            body_text, _line_of(body), mnid, add_node, add_edge,
                            attribute_generic_lookups_to=file_nid,
                        )
                pending_annotations = []
                if body is not None:
                    i += 2
                else:
                    i += 1
                continue

            pending_annotations = []
            i += 1

        # Whole-class body heuristics (Bloc ctor registrations live in constructors)
        body_text = _read_text(body_node, source)
        _apply_flutter_heuristics(
            body_text, _line_of(body_node), class_nid, add_node, add_edge,
            attribute_generic_lookups_to=file_nid,
        )

    def handle_type_decl(node) -> None:
        name = None
        name_node = None
        for c in node.children:
            if c.type == "identifier":
                name = _read_text(c, source)
                name_node = c
                break
            if c.type == "type_identifier" and node.type == "type_alias":
                name = _read_text(c, source)
                name_node = c
                break
        if not name:
            return
        line = _line_of(name_node or node)
        type_nid = _make_id(stem, name)
        add_node(type_nid, name, line=line)
        add_edge(file_nid, type_nid, "defines", line=line)

        for c in node.children:
            if c.type == "annotation":
                emit_annotation_edges(c, type_nid, name, "class")

        emit_heritage(type_nid, node, line)

        if node.type == "type_alias":
            # typedef JsonMap = Map<...>;
            type_ids = [c for c in node.children if c.type == "type_identifier"]
            if len(type_ids) >= 2:
                target = _read_text(type_ids[1], source)
                if _type_blacklist_ok(target):
                    tid = ensure_external(target)
                    add_edge(type_nid, tid, "references", line=line, context="typedef")

        body = None
        for c in node.children:
            if c.type in ("class_body", "enum_body", "extension_body"):
                body = c
                break
        if body is not None and node.type != "enum_declaration":
            handle_class_body(body, type_nid, name)

        if node.type == "extension_declaration":
            # extension X on Target
            kids = list(node.children)
            for i, c in enumerate(kids):
                if c.type == "on" and i + 1 < len(kids):
                    parts = []
                    j = i + 1
                    while j < len(kids) and kids[j].type in ("type_identifier", "."):
                        if kids[j].type == "type_identifier":
                            parts.append(_read_text(kids[j], source))
                        j += 1
                        if j < len(kids) and kids[j].type == "type_arguments":
                            break
                    if parts:
                        target = ".".join(parts)
                        tid = ensure_external(target)
                        add_edge(type_nid, tid, "extends", line=line)
                    break

    def handle_top_function(sig_node, body_node, pending_annotations: list) -> None:
        idents = [c for c in sig_node.children if c.type == "identifier"]
        if not idents:
            return
        fname = _read_text(idents[-1], source)
        if not fname or fname in _METHOD_NAME_SKIP or re.match(r"^[A-Z]", fname):
            return
        line = _line_of(idents[-1])
        fnid = _make_id(stem, fname)
        add_node(fnid, fname, line=line)
        add_edge(file_nid, fnid, "defines", line=line)
        for ann in pending_annotations:
            emit_annotation_edges(ann, fnid, fname, "function")
        if body_node is not None:
            function_bodies.append((fnid, body_node, True))
            body_text = _read_text(body_node, source)
            _apply_flutter_heuristics(
                body_text, _line_of(body_node), fnid, add_node, add_edge,
                attribute_generic_lookups_to=file_nid,
            )

    def handle_import_export(node) -> None:
        is_export = any(c.type == "library_export" for c in node.children)
        uri = None

        def find_uri(n) -> str | None:
            if n.type == "uri" or n.type == "configurable_uri":
                text = _strip_quotes(_read_text(n, source))
                # configurable_uri wraps uri
                if n.type == "configurable_uri":
                    for c in n.children:
                        if c.type == "uri":
                            return _strip_quotes(_read_text(c, source))
                return text
            for c in n.children:
                found = find_uri(c)
                if found:
                    return found
            return None

        uri = find_uri(node)
        if not uri:
            return
        line = _line_of(node)
        tgt = ensure_external(uri)
        # ensure label is full uri
        for n in nodes:
            if n["id"] == tgt:
                n["label"] = uri
                break
        add_edge(file_nid, tgt, "exports" if is_export else "imports", line=line)

    def handle_top_level_vars(program) -> None:
        """Scan program children for top-level variable declarations."""
        children = list(program.children)
        i = 0
        while i < len(children):
            c = children[i]

            # static_final_declaration_list after final/const/late/type
            if c.type == "static_final_declaration_list":
                for decl in c.children:
                    if decl.type != "static_final_declaration":
                        continue
                    ident = next((x for x in decl.children if x.type == "identifier"), None)
                    if not ident:
                        continue
                    vname = _read_text(ident, source)
                    if not vname or vname in _METHOD_NAME_SKIP:
                        continue
                    line = _line_of(ident)
                    vnid = _make_id(stem, vname)
                    add_node(vnid, vname, line=line)
                    add_edge(file_nid, vnid, "defines", line=line)
                i += 1
                continue

            if c.type == "initialized_identifier_list":
                # late final Type name; or pattern leftovers
                for ini in c.children:
                    if ini.type != "initialized_identifier":
                        continue
                    ident = next((x for x in ini.children if x.type == "identifier"), None)
                    if not ident:
                        continue
                    vname = _read_text(ident, source)
                    if not vname or vname in _METHOD_NAME_SKIP:
                        continue
                    # Skip PascalCase type names mistaken as vars
                    if re.match(r"^[A-Z]", vname):
                        continue
                    line = _line_of(ident)
                    vnid = _make_id(stem, vname)
                    add_node(vnid, vname, line=line)
                    add_edge(file_nid, vnid, "defines", line=line)
                    # variable type from preceding siblings
                    var_type = _qualified_type_before(c, source)
                    if var_type:
                        clean = var_type.split(".")[-1]
                        if _type_blacklist_ok(clean):
                            tid = ensure_external(clean)
                            add_edge(
                                file_nid, tid, "references",
                                line=line, context="variable_type",
                            )
                i += 1
                continue

            # Pattern: ERROR(var) + record_type (recA, recB) 
            if c.type == "ERROR" or (c.type == "inferred_type"):
                # look ahead for record_type with lowercase field names
                j = i + 1
                while j < len(children) and children[j].type in ("ERROR", "inferred_type"):
                    j += 1
                if j < len(children) and children[j].type == "record_type":
                    rt = children[j]
                    for field in rt.children:
                        if field.type != "record_type_field":
                            continue
                        # Prefer identifier children (pattern binds); else type_identifier if lowercase
                        idents = [x for x in field.children if x.type == "identifier"]
                        if idents:
                            for ident in idents:
                                vname = _read_text(ident, source)
                                if vname and re.match(r"^[a-z_]\w*$", vname):
                                    line = _line_of(ident)
                                    vnid = _make_id(stem, vname)
                                    add_node(vnid, vname, line=line)
                                    add_edge(file_nid, vnid, "defines", line=line)
                        else:
                            for ti in field.children:
                                if ti.type == "type_identifier":
                                    vname = _read_text(ti, source)
                                    if vname and re.match(r"^[a-z_]\w*$", vname):
                                        line = _line_of(ti)
                                        vnid = _make_id(stem, vname)
                                        add_node(vnid, vname, line=line)
                                        add_edge(file_nid, vnid, "defines", line=line)
                i += 1
                continue

            if c.type == "record_type":
                # Standalone record_type after var ERROR already handled; also
                # `final (int, String) typedRecord` has record_type then static_final list.
                i += 1
                continue

            i += 1

        # Regex supplement for object-pattern destructuring the grammar mishandles:
        # var User(name: myVar, age: myAge) = user;
        src_text = source.decode("utf-8", errors="replace")
        for m in re.finditer(
            r"^\s*(?:var|final|const)\s+[A-Z]\w*\(([^)]+)\)\s*=",
            src_text,
            re.MULTILINE,
        ):
            inner = m.group(1)
            for part in inner.split(","):
                part = part.strip()
                if ":" in part:
                    name = part.split(":")[-1].strip()
                else:
                    name = part
                if re.match(r"^[a-z_]\w*$", name):
                    line = src_text[: m.start()].count("\n") + 1
                    vnid = _make_id(stem, name)
                    add_node(vnid, name, line=line)
                    add_edge(file_nid, vnid, "defines", line=line)

    # --- walk program ---
    pending_annotations: list = []
    children = list(root.children)
    i = 0
    while i < len(children):
        child = children[i]

        if child.type == "annotation":
            # May belong to next class/function; peek ahead
            pending_annotations.append(child)
            i += 1
            continue

        if child.type in (
            "class_definition",
            "mixin_declaration",
            "enum_declaration",
            "extension_declaration",
            "extension_type_declaration",
            "type_alias",
        ):
            # Attach pending annotations into the node walk (also on the node itself)
            handle_type_decl(child)
            # If annotations were siblings before the decl, emit them now
            name = None
            for c in child.children:
                if c.type == "identifier":
                    name = _read_text(c, source)
                    break
                if c.type == "type_identifier" and child.type == "type_alias":
                    name = _read_text(c, source)
                    break
            if name and pending_annotations:
                type_nid = _make_id(stem, name)
                for ann in pending_annotations:
                    # Avoid double-emit if already child of class_definition
                    if ann.parent is child:
                        continue
                    emit_annotation_edges(ann, type_nid, name, "class")
            pending_annotations = []
            i += 1
            continue

        if child.type == "function_signature":
            body = children[i + 1] if i + 1 < len(children) and children[i + 1].type == "function_body" else None
            handle_top_function(child, body, pending_annotations)
            pending_annotations = []
            i += 2 if body is not None else 1
            continue

        if child.type == "import_or_export":
            handle_import_export(child)
            pending_annotations = []
            i += 1
            continue

        if child.type in ("library_import", "library_export"):
            # sometimes not wrapped
            pending_annotations = []
            i += 1
            continue

        # Don't clear annotations on trivia
        if child.type in (";", "comment", "documentation_comment"):
            i += 1
            continue

        if child.is_named and child.type not in (
            "final_builtin", "const_builtin", "late", "type_identifier",
            "type_arguments", "static_final_declaration_list",
            "initialized_identifier_list", "record_type", "inferred_type",
            "ERROR", "part_of_directive", "part_directive", "library_name",
        ):
            pending_annotations = []

        i += 1

    handle_top_level_vars(root)

    # File-level generic type lookups across whole source (matches regex contract)
    src_text = source.decode("utf-8", errors="replace")
    # Skip comments roughly for lookups? Regex used cleaned source; for type_lookup
    # false positives in comments are rare. Use full text for parity with tests.
    generic_call_pattern = r"\b\w+<([a-zA-Z0-9_.]+(?:<[a-zA-Z0-9_.,\s<>]+>)?)\s*>\s*\("
    for m in re.finditer(generic_call_pattern, src_text):
        type_name = m.group(1).split(".")[-1].strip()
        clean_name = type_name.split("<")[0].strip()
        if _type_blacklist_ok(clean_name):
            target_nid = _make_id(clean_name)
            ensure_external(clean_name)
            # Fix label to clean_name
            for n in nodes:
                if n["id"] == target_nid:
                    n["label"] = clean_name
                    break
            line = src_text[: m.start(1)].count("\n") + 1
            add_edge(file_nid, target_nid, "references", line=line, context="type_lookup")

    # Call-graph second pass
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        if n.get("source_file") is None:
            continue
        label_to_nid[n["label"]] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def _has_argument_part(n) -> bool:
        if n.type == "argument_part":
            return True
        return any(_has_argument_part(c) for c in n.children)

    def _emit_call(callee: str, call_node, caller_nid: str) -> None:
        if not callee or callee in _LANGUAGE_BUILTIN_GLOBALS or callee in _METHOD_NAME_SKIP:
            return
        tgt = label_to_nid.get(callee)
        if tgt and tgt != caller_nid:
            pair = (caller_nid, tgt)
            if pair not in seen_call_pairs:
                seen_call_pairs.add(pair)
                line = _line_of(call_node)
                edges.append({
                    "source": caller_nid,
                    "target": tgt,
                    "relation": "calls",
                    "context": "call",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": str_path,
                    "source_location": f"L{line}",
                    "weight": 1.0,
                })
        elif callee:
            raw_calls.append({
                "caller_nid": caller_nid,
                "callee": callee,
                "is_member_call": True,
                "language": "dart",
                "source_file": str_path,
                "source_location": f"L{_line_of(call_node)}",
            })

    def walk_calls(node, caller_nid: str) -> None:
        # Dart calls are identifier/selector chains ending in argument_part,
        # appearing under expression_statement, return_statement, etc.
        if node.type in ("expression_statement", "return_statement"):
            selectors = [c for c in node.children if c.type == "selector"]
            idents = [c for c in node.children if c.type == "identifier"]
            if selectors and _has_argument_part(selectors[-1]):
                callee = None
                if len(selectors) >= 2:
                    prev = selectors[-2]
                    mid = next((c for c in prev.children if c.type == "identifier"), None)
                    if mid is not None:
                        callee = _read_text(mid, source)
                    else:
                        for c in prev.children:
                            found = _first_identifier(c, source)
                            if found:
                                callee = found
                                break
                elif idents:
                    callee = _read_text(idents[0], source)
                _emit_call(callee, node, caller_nid)

        for child in node.children:
            if child.type in ("function_signature", "function_expression", "class_definition"):
                continue
            walk_calls(child, caller_nid)

    for caller_nid, body_node, _top in function_bodies:
        walk_calls(body_node, caller_nid)

    return {"nodes": nodes, "edges": edges, "raw_calls": raw_calls}
