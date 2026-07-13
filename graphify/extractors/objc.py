"""objc — moved verbatim from graphify/extract.py."""
from __future__ import annotations

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.engine import _cpp_declarator_name, _semantic_reference_edge
from graphify.extractors.resolution import _resolve_c_include_path
from pathlib import Path
from typing import Any


def _objc_local_var_types(body_node, source: bytes, table: dict[str, str]) -> None:
    """Collect ``var -> ClassName`` from ObjC local declarations (``Foo *f = ...;``)
    in a method body, for receiver typing in the cross-file message-send pass
    (#1556). Only a capitalized ``type_identifier`` with a single named declarator
    is recorded; a built-in/lower-cased type or an un-nameable declarator is skipped
    (precision over recall). Reuses the C++ declarator unwrapper (identical grammar).
    """
    stack = [body_node]
    while stack:
        n = stack.pop()
        if n.type == "method_definition" and n is not body_node:
            continue
        if n.type == "declaration":
            type_node = n.child_by_field_name("type")
            if type_node is None:
                for c in n.children:
                    if c.type == "type_identifier":
                        type_node = c
                        break
            if type_node is not None and type_node.type == "type_identifier":
                type_name = _read_text(type_node, source).strip()
                declarators = [
                    c for c in n.children
                    if c.type in ("identifier", "pointer_declarator", "init_declarator")
                ]
                if type_name and type_name[:1].isupper() and len(declarators) == 1:
                    var = _cpp_declarator_name(declarators[0], source)
                    if var and var not in table:
                        table[var] = type_name
        for c in n.children:
            stack.append(c)

def extract_objc(path: Path) -> dict:
    """Extract interfaces, implementations, protocols, methods, and imports from .m/.mm/.h files."""
    try:
        import tree_sitter_objc as tsobjc
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_objc not installed"}

    try:
        language = Language(tsobjc.language())
        parser = Parser(language)
        source = path.read_bytes()
        # tree-sitter-objc cannot expand these argument-less annotation macros (no
        # trailing ';'), and their presence before @interface makes the parser fail to
        # emit a class_interface node (#1475). Blank them to equal-length spaces so byte
        # offsets / line numbers are preserved and the interface parses.
        _OBJC_BLANK_MACROS = (b"NS_ASSUME_NONNULL_BEGIN", b"NS_ASSUME_NONNULL_END")
        for _m in _OBJC_BLANK_MACROS:
            source = source.replace(_m, b" " * len(_m))
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    method_bodies: list[tuple[str, Any, str]] = []
    # #1556: unresolved message sends saved for the cross-file ObjC resolver, plus a
    # per-file `var -> ClassName` table from `Foo *f = ...;` local declarations.
    raw_calls: list[dict] = []
    objc_type_table: dict[str, str] = {}

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _read(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def _get_name(node, field: str) -> str | None:
        n = node.child_by_field_name(field)
        return _read(n) if n else None

    def _type_identifiers(node):
        """Yield every type_identifier under a property's type node, descending
        through generic_specifier/type_name so NSArray<Product *> yields both
        NSArray and the element type Product (the generic case was invisible
        because the type was wrapped in a generic_specifier, not a bare
        type_identifier child) (#1475)."""
        if node.type == "type_identifier":
            yield node
            return
        for c in node.children:
            yield from _type_identifiers(c)

    def ensure_named_node(name: str, line: int) -> str:
        nid = _make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
            # The name isn't defined in this file, so this is a cross-file reference
            # (e.g. a `Thing` type annotation imported from another module). Emit a
            # SOURCELESS stub — like the inheritance-base path below — so the
            # corpus-level rewire can collapse it onto the real definition. A sourced
            # stub here makes _disambiguate_colliding_node_ids bake the referencing
            # file's path (with extension) into the id and blocks the rewire, which is
            # the phantom-duplicate-node bug (#1402).
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            })
        return nid

    def walk(node, parent_nid: str | None = None) -> None:
        t = node.type
        line = node.start_point[0] + 1

        if t == "preproc_include":
            # #import <Foundation/Foundation.h> or #import "MyClass.h"
            for child in node.children:
                if child.type == "system_lib_string":
                    raw = _read(child).strip("<>")
                    module = raw.split("/")[-1].replace(".h", "")
                    if module:
                        tgt_nid = _make_id(module)
                        add_edge(file_nid, tgt_nid, "imports", line, context="import")
                elif child.type == "string_literal":
                    # recurse into string_literal to find string_content
                    for sub in child.children:
                        if sub.type == "string_content":
                            raw = _read(sub)
                            # Resolve the quoted include to a real file so the target id
                            # matches the (possibly disambiguated) node id _make_id gives
                            # that file; the bare-stem id never survives
                            # _disambiguate_colliding_node_ids when a .h/.m pair exists,
                            # so the edge dangled and was dropped (#1475).
                            resolved = _resolve_c_include_path(raw, str_path)
                            if resolved is not None:
                                add_edge(file_nid, _make_id(str(resolved)), "imports", line, context="import")
                            else:
                                module = raw.split("/")[-1].replace(".h", "")
                                if module:
                                    add_edge(file_nid, _make_id(module), "imports", line, context="import")
            return

        if t == "module_import":
            # @import Foundation;  /  @import Foundation.NSString;
            path_node = node.child_by_field_name("path")
            if path_node is not None:
                module = _read(path_node).split(".")[0].strip()
                if module:
                    add_edge(file_nid, _make_id(module), "imports", line, context="import")
            return

        if t == "class_interface":
            # @interface ClassName : SuperClass <Protocols>
            # children: @interface, identifier(name), ':', identifier(super), parameterized_arguments, ...
            identifiers = [c for c in node.children if c.type == "identifier"]
            if not identifiers:
                for child in node.children:
                    walk(child, parent_nid)
                return
            name = _read(identifiers[0])
            cls_nid = _make_id(stem, name)
            add_node(cls_nid, name, line)
            add_edge(file_nid, cls_nid, "contains", line)
            # superclass is second identifier after ':'
            colon_seen = False
            for child in node.children:
                if child.type == ":":
                    colon_seen = True
                elif colon_seen and child.type == "identifier":
                    super_nid = ensure_named_node(_read(child), line)
                    add_edge(cls_nid, super_nid, "inherits", line)
                    colon_seen = False
                elif child.type == "parameterized_arguments":
                    # protocols adopted: @interface Foo : Bar <Proto1, Proto2>
                    for sub in child.children:
                        if sub.type == "type_name":
                            for s in sub.children:
                                if s.type == "type_identifier":
                                    proto_nid = ensure_named_node(_read(s), line)
                                    add_edge(cls_nid, proto_nid, "implements", line)
                elif child.type == "property_declaration":
                    prop_line = child.start_point[0] + 1
                    for sub in child.children:
                        if sub.type == "struct_declaration":
                            # The type is either a direct type_identifier
                            # (NSString *x) or wrapped in a generic_specifier
                            # (NSArray<Product *> *xs). Walk every type name in the
                            # type portion, skipping the declarator (the *field
                            # name), so generic collections are no longer invisible.
                            seen_types: set[str] = set()
                            for s in sub.children:
                                if s.type in ("struct_declarator", ";"):
                                    continue
                                for ti in _type_identifiers(s):
                                    tname = _read(ti)
                                    if tname in seen_types:
                                        continue
                                    seen_types.add(tname)
                                    type_nid = ensure_named_node(tname, prop_line)
                                    edges.append(_semantic_reference_edge(
                                        cls_nid, type_nid, "field", str_path, prop_line))
                elif child.type == "method_declaration":
                    walk(child, cls_nid)
            return

        if t == "class_implementation":
            # @implementation ClassName
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = _read(child)
                    break
            if not name:
                for child in node.children:
                    walk(child, parent_nid)
                return
            impl_nid = _make_id(stem, name)
            if impl_nid not in seen_ids:
                add_node(impl_nid, name, line)
                add_edge(file_nid, impl_nid, "contains", line)
            for child in node.children:
                if child.type == "implementation_definition":
                    for sub in child.children:
                        walk(sub, impl_nid)
            return

        if t == "protocol_declaration":
            name = None
            for child in node.children:
                if child.type == "identifier":
                    name = _read(child)
                    break
            if name:
                proto_nid = _make_id(stem, name)
                add_node(proto_nid, f"<{name}>", line)
                add_edge(file_nid, proto_nid, "contains", line)
                # Adopted protocols: `@protocol Derived <Base, Other>`. These
                # nest under a protocol_reference_list node (distinct from the
                # parameterized_arguments node used by @interface adoption), so
                # they were never emitted. Emit an `implements` edge for each,
                # matching how @interface protocol adoption is handled.
                for child in node.children:
                    if child.type == "protocol_reference_list":
                        for sub in child.children:
                            if sub.type == "identifier":
                                base_nid = ensure_named_node(_read(sub), line)
                                if base_nid != proto_nid:
                                    add_edge(proto_nid, base_nid, "implements", line)
                for child in node.children:
                    walk(child, proto_nid)
            return

        if t in ("method_declaration", "method_definition"):
            container = parent_nid or file_nid
            # Class methods start with '+', instance methods with '-' (the grammar
            # emits the sigil as the first child). The selector is the concatenation
            # of the direct identifier children: one for a simple selector (-go),
            # several for a compound one (-tableView:numberOfRowsInSection: ->
            # "tableViewnumberOfRowsInSection"); method_parameter holds the arg
            # types/names, not selector keywords, so it is correctly skipped.
            prefix = "-"
            for child in node.children:
                if child.type in ("+", "-"):
                    prefix = child.type
                    break
            parts = [_read(c) for c in node.children if c.type == "identifier"]
            method_name = "".join(parts) if parts else None
            if method_name:
                method_nid = _make_id(container, method_name)
                add_node(method_nid, f"{prefix}{method_name}", line)
                add_edge(container, method_nid, "method", line)
                if t == "method_definition":
                    method_bodies.append((method_nid, node, container))
            return

        for child in node.children:
            walk(child, parent_nid)

    walk(root)

    # Second pass: resolve calls inside method bodies
    all_method_nids = {n["id"] for n in nodes if n["id"] != file_nid}
    class_method_nids: dict[str, set[str]] = {}
    for m_nid, _, container_nid in method_bodies:
        class_method_nids.setdefault(container_nid, set()).add(m_nid)
    seen_calls: set[tuple[str, str]] = set()
    # #1556: per-file `var -> ClassName` table from local declarations in every
    # method body, so the cross-file resolver can type a `[f doThing]` receiver.
    for _m_nid, body_node, _container in method_bodies:
        _objc_local_var_types(body_node, source, objc_type_table)

    for caller_nid, body_node, container_nid in method_bodies:
        sibling_nids = class_method_nids.get(container_nid, set())

        def walk_calls(n) -> None:
            if n.type == "message_expression":
                # `[[Foo alloc] init]` is a message_expression whose method is the
                # identifier `alloc` and whose receiver is the bare class identifier
                # `Foo`; resolve that class name and emit a `references` edge so the
                # allocating method links to the allocated type. ensure_named_node
                # emits a sourceless stub for unknown names, which the corpus rewire
                # collapses ONLY when exactly one real class of that name exists, so an
                # unknown/ambiguous class produces no false resolved edge (#1475).
                meth = n.child_by_field_name("method")
                recv = n.child_by_field_name("receiver")
                if (meth is not None and meth.type == "identifier" and _read(meth) == "alloc"
                        and recv is not None and recv.type == "identifier"):
                    tname = _read(recv)
                    ref_line = n.start_point[0] + 1
                    type_nid = ensure_named_node(tname, ref_line)
                    if type_nid != caller_nid:
                        edges.append(_semantic_reference_edge(
                            caller_nid, type_nid, "type", str_path, ref_line))
                # [receiver sel] and [receiver kw1:a kw2:b] both parse to a
                # message_expression whose selector parts carry the field name
                # "method" (one for a simple selector, several for a compound one);
                # the receiver carries field name "receiver". Reconstruct the
                # selector from every "method" child so self/super/ClassName
                # receivers are never mistaken for a selector, and compound sends
                # resolve too (the whole second pass was previously dead code for
                # ObjC because the grammar emits these as `identifier`, not
                # `selector`/`keyword_argument_list`) (#1475).
                sel_parts = [
                    _read(child)
                    for i, child in enumerate(n.children)
                    if n.field_name_for_child(i) == "method" and child.type == "identifier"
                ]
                method_name = "".join(sel_parts)
                if method_name:
                    needle = _make_id("", method_name).lstrip("_")
                    for candidate in all_method_nids:
                        if candidate.endswith(needle):
                            pair = (caller_nid, candidate)
                            if pair not in seen_calls and caller_nid != candidate:
                                seen_calls.add(pair)
                                add_edge(caller_nid, candidate, "calls", n.start_point[0] + 1,
                                         confidence="EXTRACTED", weight=1.0, context="call")
                    # #1556: also emit a raw_call so the cross-file resolver can type
                    # the receiver and link to a method in ANOTHER file. A bare
                    # identifier receiver (`f`, `self`, `Foo`) is captured; a nested
                    # message send (`[[Foo alloc] init]`) has no simple receiver name
                    # to type, so it is left to the alloc/init `references` edge above.
                    if recv is not None and recv.type == "identifier":
                        raw_calls.append({
                            "caller_nid": caller_nid,
                            "callee": method_name,
                            "is_member_call": True,
                            "source_file": str_path,
                            "source_location": f"L{n.start_point[0] + 1}",
                            "receiver": _read(recv),
                            "lang": "objc",
                        })
            elif n.type == "field_expression":
                # self.name / self.product.name — dot-syntax sugar for [self name].
                # Resolve to a sibling method of the SAME class, matched by EXACT
                # node id (a method id is _make_id(container, name)). A suffix
                # substring match would mis-resolve self.name -> -surname and would
                # let a substring-colliding sibling (-surname) suppress the real
                # -name edge, so it must be an exact match (#1475).
                for child in n.children:
                    if child.type == "field_identifier":
                        field_name = _read(child)
                        target = _make_id(container_nid, field_name)
                        if target in sibling_nids and target != caller_nid:
                            pair = (caller_nid, target)
                            if pair not in seen_calls:
                                seen_calls.add(pair)
                                add_edge(caller_nid, target, "accesses",
                                         n.start_point[0] + 1,
                                         confidence="EXTRACTED", weight=1.0)
            elif n.type == "selector_expression":
                # @selector(doSomething:withParam:) — compile-time method ref.
                # Match the selector name EXACTLY (a method id is
                # _make_id(container, name)) against every class's methods, and emit
                # only when exactly one method matches, to avoid ambiguous fan-out.
                # Exact match (not a suffix) keeps -doThing distinct from
                # -reallyDoThing (#1475).
                sel_parts = [_read(c) for c in n.children if c.type == "identifier"]
                sel_name = "".join(sel_parts)
                if sel_name:
                    matches = sorted({
                        m for m, _, cont in method_bodies
                        if m == _make_id(cont, sel_name) and m != caller_nid
                    })
                    if len(matches) == 1:
                        pair = (caller_nid, matches[0])
                        if pair not in seen_calls:
                            seen_calls.add(pair)
                            add_edge(caller_nid, matches[0], "calls",
                                     n.start_point[0] + 1,
                                     confidence="EXTRACTED", weight=1.0,
                                     context="call")
            for child in n.children:
                walk_calls(child)
        walk_calls(body_node)

    result = {"nodes": nodes, "edges": edges, "raw_calls": raw_calls,
              "input_tokens": 0, "output_tokens": 0}
    if objc_type_table:
        result["objc_type_table"] = {"path": str_path, "table": objc_type_table}
    return result
