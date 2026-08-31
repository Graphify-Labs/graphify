"""Haxe extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import (
    _LANGUAGE_BUILTIN_GLOBALS,
    _file_stem,
    _make_id,
    _read_text,
)


def _extract_haxe_vantreeseba(path: Path) -> dict:
    """Extract from a .hx file parsed by the vantreeseba-derived grammar.

    Node names here (``class_declaration``, ``call_expression``,
    ``member_expression``) are those of ``masquepublishing/tree-sitter-haxe``.
    See :func:`extract_haxe` for how the grammar in use is chosen."""
    try:
        import tree_sitter_haxe as _tshaxe
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-haxe not installed"}

    try:
        language = Language(_tshaxe.language())
        parser = Parser(language)
        source = path.read_bytes()
        # Normalize CR-only and CRLF line endings to LF so that the tree-sitter
        # comment rule `seq('//', /.*/)`  doesn't consume the rest of the file
        # on old-Mac \r-only files (where .* matches \r and runs to EOF).
        if b"\r" in source:
            source = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, Any]] = []

    def add_node(nid: str, label: str, line: int) -> None:
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED") -> None:
        if src and tgt and src != tgt:
            edges.append({
                "source": src,
                "target": tgt,
                "relation": relation,
                "confidence": confidence,
                "source_file": str_path,
                "source_location": f"L{line}",
                "weight": 1.0,
            })

    def ensure_type_node(name: str, line: int) -> str:
        nid = _make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
            })
            seen_ids.add(nid)
        return nid

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _haxe_call_name(call_node) -> str:
        """Return the bare function/method name from a call_expression node."""
        obj = call_node.child_by_field_name("object")
        ctor = call_node.child_by_field_name("constructor")
        if ctor is not None:
            return _read_text(ctor, source)
        if obj is None:
            return ""
        if obj.type == "identifier":
            return _read_text(obj, source)
        if obj.type == "member_expression":
            # Last entry in the `member` field list is the method name
            members = obj.children_by_field_name("member")
            if members:
                last = members[-1]
                if last.type == "identifier":
                    return _read_text(last, source)
                # nested member_expression — recurse one level
                if last.type == "member_expression":
                    sub = last.children_by_field_name("member")
                    if sub:
                        return _read_text(sub[-1], source)
        return ""

    def walk_calls(node, owner_nid: str, class_name: "str | None") -> None:
        """Walk a function body collecting call edges; stops at nested function boundaries."""
        if node.type == "function_declaration":
            return
        if node.type == "call_expression":
            call_name = _haxe_call_name(node)
            if call_name and call_name not in _LANGUAGE_BUILTIN_GLOBALS:
                # Only resolve within the same file. Every other language's
                # extractor in this codebase deliberately stops here too when
                # it can't otherwise disambiguate (see the generic call-walk's
                # per-file label_to_nid lookup and the #543/#1219 god-node
                # comments in _resolve_cross_file_*): a bare, language-unscoped
                # name lookup collides across the whole depot and produces
                # wrong edges (e.g. a Haxe `textSprite()` call resolving to an
                # unrelated `Dev/Poker/Client/GraphObjs.h` by name coincidence)
                # far more often than it produces a real one. No cross-file
                # resolver exists for Haxe, so an unresolved call here is
                # simply dropped rather than guessed at.
                #
                # `_haxe_call_name` doesn't distinguish a bare call, a
                # `this.foo()` call, and an `other.foo()` call — all three
                # come back as just "foo" — so a same-class sibling-method
                # call (the idiomatic case, since methods are stored under a
                # class-qualified id) has to be tried explicitly here rather
                # than falling out of a single file-scoped lookup.
                tgt_nid = None
                if class_name is not None:
                    candidate = _make_id(stem, class_name, call_name)
                    if candidate in seen_ids:
                        tgt_nid = candidate
                if tgt_nid is None:
                    candidate = _make_id(stem, call_name)
                    if candidate in seen_ids:
                        tgt_nid = candidate
                if tgt_nid is not None:
                    line = node.start_point[0] + 1
                    add_edge(owner_nid, tgt_nid, "calls", line)
        for child in node.children:
            walk_calls(child, owner_nid, class_name)

    def _haxe_dotted_path(node) -> str:
        """Reconstruct dotted package path from an import/using statement."""
        parts = [
            _read_text(c, source)
            for c in node.children
            if c.type in ("package_name", "type_name")
        ]
        return ".".join(parts)

    def walk(node, parent_class_nid: "str | None" = None,
             parent_class_name: "str | None" = None) -> None:
        t = node.type

        if t in ("import_statement", "using_statement"):
            dotted = _haxe_dotted_path(node)
            if dotted:
                tgt_nid = _make_id(dotted.replace(".", "_"))
                add_edge(file_nid, tgt_nid, "imports", node.start_point[0] + 1)
            return

        if t in ("class_declaration", "interface_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for child in node.children:
                    walk(child, parent_class_nid, parent_class_name)
                return
            class_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            class_nid = _make_id(stem, class_name)
            add_node(class_nid, class_name, line)
            add_edge(file_nid, class_nid, "contains", line)

            # extends
            for super_node in node.children_by_field_name("super_class_name"):
                base = _read_text(super_node, source).strip()
                if base:
                    add_edge(class_nid, ensure_type_node(base, line), "inherits", line)

            # implements / interface extends
            for iface_node in node.children_by_field_name("interface_name"):
                iface = _read_text(iface_node, source).strip()
                if iface:
                    rel = "inherits" if t == "interface_declaration" else "implements"
                    add_edge(class_nid, ensure_type_node(iface, line), rel, line)

            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    walk(child, class_nid, class_name)
            return

        if t in ("enum_declaration", "enum_abstract_declaration"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            enum_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            enum_nid = _make_id(stem, enum_name)
            add_node(enum_nid, enum_name, line)
            add_edge(file_nid, enum_nid, "contains", line)
            # Walk body for nested function declarations (uncommon but possible)
            body = node.child_by_field_name("body")
            if body is not None:
                for child in body.children:
                    walk(child, enum_nid, enum_name)
            return

        if t == "typedef_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            typedef_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            typedef_nid = _make_id(stem, typedef_name)
            add_node(typedef_nid, typedef_name, line)
            add_edge(file_nid, typedef_nid, "contains", line)
            return

        if t == "function_declaration":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            func_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            if parent_class_nid is not None and parent_class_name is not None:
                func_nid = _make_id(stem, parent_class_name, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(parent_class_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
            fn_body = node.child_by_field_name("body")
            if fn_body is not None:
                function_bodies.append((func_nid, fn_body, parent_class_name))
            return

        for child in node.children:
            walk(child, parent_class_nid, parent_class_name)

    walk(root)

    # Fallback: recover class/enum names from scattered module-level tokens.
    # When the grammar can't form a proper declaration node (e.g. minified files
    # where everything is on one line, or unsupported preprocessor patterns), the
    # parser emits bare 'class'/'enum' keyword tokens followed by an identifier.
    # Walk the top-level children looking for that pattern and create nodes for
    # any names that weren't already extracted.
    if len(nodes) <= 1:
        _haxe_recover_scattered(root, source, stem, file_nid,
                                add_node, add_edge, seen_ids, function_bodies)

    for func_nid, body, class_name in function_bodies:
        walk_calls(body, func_nid, class_name)

    return {"nodes": nodes, "edges": edges}


def _haxe_recover_scattered(
    root: Any,
    source: bytes,
    stem: str,
    file_nid: str,
    add_node: Any,
    add_edge: Any,
    seen_ids: set,
    function_bodies: list,
) -> None:
    """Extract class/enum names from module-level scattered tokens.

    When the grammar fails to form a declaration node (minified code, unsupported
    preprocessor patterns), the parser emits 'class'/'enum' as bare keyword tokens
    followed by an identifier. This pass recovers at least the type name so the
    file has a meaningful node rather than just a file-level stub.
    """
    children = list(root.children)
    i = 0
    while i < len(children):
        node = children[i]
        t = node.type
        raw = source[node.start_byte:node.end_byte].decode("utf-8", "replace").strip()

        # Pattern: 'class' token followed by identifier token
        if raw == "class" and i + 1 < len(children):
            next_node = children[i + 1]
            if next_node.type == "identifier":
                class_name = source[next_node.start_byte:next_node.end_byte].decode("utf-8", "replace").strip()
                line = node.start_point[0] + 1
                class_nid = _make_id(stem, class_name)
                add_node(class_nid, class_name, line)
                add_edge(file_nid, class_nid, "contains", line)
                # Collect any function_declaration siblings that follow before
                # we hit another keyword or end of file
                j = i + 2
                while j < len(children):
                    sib = children[j]
                    if sib.type == "function_declaration":
                        fn_name_node = sib.child_by_field_name("name")
                        if fn_name_node is not None:
                            fn_name = source[fn_name_node.start_byte:fn_name_node.end_byte].decode("utf-8", "replace")
                            fn_line = sib.start_point[0] + 1
                            fn_nid = _make_id(stem, class_name, fn_name)
                            add_node(fn_nid, f"{fn_name}()", fn_line)
                            add_edge(class_nid, fn_nid, "method", fn_line)
                            fn_body = sib.child_by_field_name("body")
                            if fn_body is not None:
                                function_bodies.append((fn_nid, fn_body, class_name))
                    elif sib.type in ("class_declaration", "interface_declaration",
                                       "enum_declaration", "enum_abstract_declaration"):
                        break
                    elif source[sib.start_byte:sib.end_byte].decode("utf-8", "replace").strip() == "class":
                        break
                    j += 1
                i = j
                continue

        # Pattern: 'enum' keyword token (ERROR node contains the rest)
        if raw == "enum" and i + 1 < len(children):
            # Try to pull the name out of the following ERROR node's text
            next_node = children[i + 1]
            err_text = source[next_node.start_byte:next_node.end_byte].decode("utf-8", "replace")
            import re as _re
            # Matches: [abstract] Name[(...)][from...][to...] — grab Name
            m = _re.match(r"\s*(?:abstract\s+)?([A-Za-z_][A-Za-z0-9_]*)", err_text)
            if m:
                enum_name = m.group(1)
                line = node.start_point[0] + 1
                enum_nid = _make_id(stem, enum_name)
                add_node(enum_nid, enum_name, line)
                add_edge(file_nid, enum_nid, "contains", line)

        # Pattern: bare 'typedef' token followed by identifier — handles struct
        # typedefs with optional fields (?field:T) that the grammar can't parse.
        if raw == "typedef" and i + 1 < len(children):
            next_node = children[i + 1]
            if next_node.type == "identifier":
                td_name = source[next_node.start_byte:next_node.end_byte].decode("utf-8", "replace").strip()
                line = node.start_point[0] + 1
                td_nid = _make_id(stem, td_name)
                add_node(td_nid, td_name, line)
                add_edge(file_nid, td_nid, "contains", line)

        # Pattern: ERROR node whose text contains a class/interface/enum declaration.
        # Use re.search (not match) to skip leading metadata like @deprecated that
        # precede the actual keyword and would otherwise block recognition.
        if node.type == "ERROR":
            import re as _re
            err_text = source[node.start_byte:node.end_byte].decode("utf-8", "replace")
            m = _re.search(
                r"\b(class|interface|enum)\s+"
                r"(?:abstract\s+)?"
                r"([A-Za-z_][A-Za-z0-9_]*)",
                err_text,
            )
            if m:
                decl_name = m.group(2)
                line = node.start_point[0] + 1
                decl_nid = _make_id(stem, decl_name)
                add_node(decl_nid, decl_name, line)
                add_edge(file_nid, decl_nid, "contains", line)
                # Extract function names from the ERROR text with a simple regex
                for fn_m in _re.finditer(r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)\s*[\(<]", err_text):
                    fn_name = fn_m.group(1)
                    fn_line = line + err_text[:fn_m.start()].count("\n")
                    fn_nid = _make_id(stem, decl_name, fn_name)
                    add_node(fn_nid, f"{fn_name}()", fn_line)
                    add_edge(decl_nid, fn_nid, "method", fn_line)

        i += 1


# Two different tree-sitter grammars for Haxe are in use across this project's
# history, and they share no node names:
#
#   masquepublishing/tree-sitter-haxe       class_declaration, call_expression, ...
#   masquepublishing/tree-sitter-haxe-tong  ClassType,         ECall,           ...
#
# They also cannot share a Python environment: tong's parser is ABI 15, which a
# tree-sitter 0.23.x core rejects outright. So exactly one is importable at a
# time, and which one it is fully determines the node names in the tree. Rather
# than pin either, probe once and dispatch, so a checkout keeps working with
# whichever grammar happens to be installed.
_HAXE_FLAVOUR: "str | None" = None


def _detect_haxe_flavour() -> str:
    """Return 'tong', 'vantreeseba' or 'none'. Probed once, then cached."""
    global _HAXE_FLAVOUR
    if _HAXE_FLAVOUR is not None:
        return _HAXE_FLAVOUR
    try:
        import tree_sitter_haxe as _tshaxe
        from tree_sitter import Language, Parser
        root = Parser(Language(_tshaxe.language())).parse(b"class A {}").root_node
        kinds = {c.type for c in root.children}
        _HAXE_FLAVOUR = "tong" if "ClassType" in kinds else "vantreeseba"
    except Exception:
        _HAXE_FLAVOUR = "none"
    return _HAXE_FLAVOUR


def _extract_haxe_tong(path: Path) -> dict:
    """Extract from a .hx file parsed by the tong-derived grammar.

    Mirrors :func:`_extract_haxe_vantreeseba`'s contract exactly -- same node
    ids, same edge relations -- so the two are directly comparable on the same
    input. tong's tree differs in three ways that matter here: ``ClassType``
    covers both classes and interfaces (told apart by its ``kind`` field), it
    has no ``body`` field so members are direct children, and ``extends``/
    ``implements`` are explicit fields rather than named child rules."""
    try:
        import tree_sitter_haxe as _tshaxe
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-haxe not installed"}
    try:
        language = Language(_tshaxe.language())
        parser = Parser(language)
        source = path.read_bytes()
        if b"\r" in source:
            source = source.replace(b"\r\n", b"\n").replace(b"\r", b"\n")
        root = parser.parse(source).root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple] = []

    def add_node(nid, label, line):
        if nid and nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src, tgt, relation, line, confidence="EXTRACTED"):
        if src and tgt and src != tgt:
            edges.append({"source": src, "target": tgt, "relation": relation,
                          "confidence": confidence, "source_file": str_path,
                          "source_location": f"L{line}", "weight": 1.0})

    def ensure_type_node(name, line):
        nid = _make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            nodes.append({"id": nid, "label": name, "file_type": "code",
                          "source_file": "", "source_location": ""})
            seen_ids.add(nid)
        return nid

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _dotted_path(node) -> str:
        # `import`/`using` expose their segments as package_name/type_name
        # children, as the vantreeseba grammar did -- plus, for an import that
        # reaches a sub-type, one `sub` field per extra segment, emitted as a
        # bare identifier:
        #
        #   import com.masque.tools.MiscUtil.ArrayOrItem.ArrayOrItemArrayInt;
        #     path: com, masque, tools | module: MiscUtil
        #     sub: ArrayOrItem | sub: ArrayOrItemArrayInt
        #
        # Collecting only package_name/type_name truncates that at `MiscUtil`
        # and points the edge at the wrong target -- 2,264 import edges across
        # 1,139 files in one 5,372-file corpus. An `as` alias is skipped: it
        # renames the import rather than extending its path.
        parts = []
        for i, c in enumerate(node.children):
            if c.type not in ("package_name", "type_name", "identifier"):
                continue
            if node.field_name_for_child(i) == "alias":
                continue
            parts.append(_read_text(c, source))
        return ".".join(parts)

    def _call_name(node) -> str:
        """Bare function/method name from an ECall or ENew."""
        if node.type == "ENew":
            tp = next((c for c in node.children if c.type == "TypePath"), None)
            if tp is None:
                return ""
            nm = tp.child_by_field_name("name")
            return _read_text(nm, source) if nm is not None else ""
        callee = node.child_by_field_name("callee")
        if callee is None:
            return ""
        if callee.type == "identifier":
            return _read_text(callee, source)
        if callee.type == "EField":
            nm = callee.child_by_field_name("name")
            if nm is not None:
                return _read_text(nm, source)
        return ""

    def walk_calls(node, owner_nid, class_name):
        # Resolution policy is deliberately identical to
        # _extract_haxe_vantreeseba's: resolve within the same file only, and
        # DROP an unresolved call rather than inventing a node for it. A bare,
        # language-unscoped name collides across the whole depot far more often
        # than it lands (a Haxe `textSprite()` resolving to an unrelated C++
        # `GraphObjs.h`), and no cross-file resolver exists for Haxe.
        #
        # This matters far more here than it did before: tong parses function
        # bodies that previously failed, so it sees ~5x the call sites, and the
        # overwhelming majority are calls OUT of the file (`addEventListener`,
        # `Std.isOfType`). Creating a node per unresolved name buries the graph
        # in placeholders -- measured on a 5,372-file corpus it left 92% of
        # Haxe call edges pointing at fabricated nodes and cut community count
        # by 41%, the largest community going 620 -> 3,799 nodes.
        #
        # `_call_name` doesn't distinguish `foo()`, `this.foo()` and
        # `other.foo()` -- all come back as "foo" -- so the same-class sibling
        # method (the idiomatic case, stored under a class-qualified id) is
        # tried explicitly before the file-scoped name.
        if node.type in ("ECall", "ENew"):
            name = _call_name(node)
            if name and name not in _LANGUAGE_BUILTIN_GLOBALS:
                tgt_nid = None
                if class_name is not None:
                    candidate = _make_id(stem, class_name, name)
                    if candidate in seen_ids:
                        tgt_nid = candidate
                if tgt_nid is None:
                    candidate = _make_id(stem, name)
                    if candidate in seen_ids:
                        tgt_nid = candidate
                if tgt_nid is not None:
                    add_edge(owner_nid, tgt_nid, "calls", node.start_point[0] + 1)
        for c in node.children:
            walk_calls(c, owner_nid, class_name)

    def walk(node, parent_nid=None, parent_name=None):
        t = node.type

        if t in ("import", "using"):
            dotted = _dotted_path(node)
            if dotted:
                add_edge(file_nid, _make_id(dotted.replace(".", "_")),
                         "imports", node.start_point[0] + 1)
            return

        if t == "ClassType":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                for c in node.children:
                    walk(c, parent_nid, parent_name)
                return
            class_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            class_nid = _make_id(stem, class_name)
            add_node(class_nid, class_name, line)
            add_edge(file_nid, class_nid, "contains", line)

            kind_node = node.child_by_field_name("kind")
            is_iface = kind_node is not None and _read_text(kind_node, source) == "interface"

            for sup in node.children_by_field_name("extends"):
                base = _read_text(sup, source).strip()
                if base:
                    add_edge(class_nid, ensure_type_node(base, line), "inherits", line)
            for iface in node.children_by_field_name("implements"):
                nm = _read_text(iface, source).strip()
                if nm:
                    add_edge(class_nid, ensure_type_node(nm, line),
                             "inherits" if is_iface else "implements", line)

            # tong has no `body` field: members are direct children.
            for c in node.children:
                walk(c, class_nid, class_name)
            return

        if t in ("EnumType", "AbstractType"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            enum_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            enum_nid = _make_id(stem, enum_name)
            add_node(enum_nid, enum_name, line)
            add_edge(file_nid, enum_nid, "contains", line)
            for c in node.children:
                walk(c, enum_nid, enum_name)
            return

        if t == "DefType":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            td = _read_text(name_node, source)
            line = node.start_point[0] + 1
            td_nid = _make_id(stem, td)
            add_node(td_nid, td, line)
            add_edge(file_nid, td_nid, "contains", line)
            return

        if t in ("ClassMethod", "EFunction"):
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            func_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            if parent_nid is not None and parent_name is not None:
                func_nid = _make_id(stem, parent_name, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(parent_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
            body = node.child_by_field_name("body")
            if body is not None:
                function_bodies.append((func_nid, body, parent_name))
            return

        for c in node.children:
            walk(c, parent_nid, parent_name)

    walk(root)
    for func_nid, body, class_name in function_bodies:
        walk_calls(body, func_nid, class_name)
    return {"nodes": nodes, "edges": edges}


def extract_haxe(path: Path) -> dict:
    """Extract from a .hx file, using whichever Haxe grammar is installed."""
    flavour = _detect_haxe_flavour()
    if flavour == "tong":
        return _extract_haxe_tong(path)
    if flavour == "vantreeseba":
        return _extract_haxe_vantreeseba(path)
    return {"nodes": [], "edges": [], "error": "tree-sitter-haxe not installed"}
