"""Rust extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations


import re
from pathlib import Path
from graphify.extractors.base import (
    _LANGUAGE_BUILTIN_GLOBALS,
    _file_stem,
    _make_id,
    _read_source_bytes,
    _read_text,
)


# Rust prelude / std types. Language-local (like _GO_PREDECLARED_FUNCS and
# _RUST_TRAIT_METHOD_BLOCKLIST below) rather than added to the shared
# _LANGUAGE_BUILTIN_GLOBALS: the shared set is consulted with no language gate,
# and `Path`, `Result`, `Error`, `From`, `Into`, `Iterator`, `Default` and
# friends are ordinary user type names in the other languages that read it.
#
# Without this set a Rust codebase resolves every `Option`/`Vec`/`String`/
# `Result` annotation to a few canonical nodes, so the language's own primitives
# become the top god nodes (a ~1,200-file workspace had `String` at #1 with
# ~1,700 edges). Filtering is definition-aware: see _rust_collect_type_refs.
_RUST_BUILTIN_TYPES: frozenset[str] = frozenset({
    # prelude types and aliases
    "String", "str", "Option", "Result", "Vec", "VecDeque", "Box", "Rc",
    "Arc", "Weak", "RefCell", "Cell", "Cow", "Pin",
    # collections
    "HashMap", "HashSet", "BTreeMap", "BTreeSet", "BinaryHeap",
    # paths / OS strings
    "Path", "PathBuf", "OsStr", "OsString", "CStr", "CString",
    # time / ranges / markers
    "Duration", "Instant", "SystemTime", "Ordering", "Range", "RangeInclusive",
    "RangeFrom", "RangeTo", "RangeFull", "PhantomData", "ManuallyDrop",
    "NonZeroU8", "NonZeroU16", "NonZeroU32", "NonZeroU64", "NonZeroUsize",
    # variants and core traits
    "Some", "None", "Ok", "Err", "Self",
    "Default", "Clone", "Copy", "Debug", "Display", "Error", "From", "Into",
    "TryFrom", "TryInto", "AsRef", "AsMut", "Iterator", "IntoIterator",
    "Extend", "PartialEq", "Eq", "PartialOrd", "Ord", "Hash", "Send", "Sync",
    "Sized", "Drop", "Deref", "DerefMut", "Future", "Fn", "FnMut", "FnOnce",
})


def _rust_collect_type_refs(
    node,
    source: bytes,
    generic: bool,
    out: list[tuple[str, str]],
    local_types: frozenset[str] = frozenset(),
) -> None:
    """Walk a Rust type expression; append (name, role) tuples.

    A name in ``_RUST_BUILTIN_TYPES`` is skipped unless ``local_types`` holds it:
    a file that defines its own ``struct Result<T>`` shadows the prelude, and its
    references must survive. Filtering the bare name alone would erase a
    legitimate user type that happens to share a std name.
    """

    def _keep(text: str) -> bool:
        return bool(text) and (text not in _RUST_BUILTIN_TYPES or text in local_types)

    if node is None:
        return
    t = node.type
    if t == "primitive_type":
        return
    if t == "type_identifier":
        text = _read_text(node, source)
        if _keep(text):
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "scoped_type_identifier":
        text = _read_text(node, source).rsplit("::", 1)[-1]
        if _keep(text):
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "generic_type":
        name_node = node.child_by_field_name("type")
        if name_node is None:
            for c in node.children:
                if c.type in ("type_identifier", "scoped_type_identifier"):
                    name_node = c
                    break
        if name_node is not None:
            text = _read_text(name_node, source).rsplit("::", 1)[-1]
            if _keep(text):
                out.append((text, "generic_arg" if generic else "type"))
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _rust_collect_type_refs(arg, source, True, out, local_types)
        return
    if t in ("reference_type", "pointer_type", "array_type", "tuple_type", "slice_type"):
        for c in node.children:
            if c.is_named:
                _rust_collect_type_refs(c, source, generic, out, local_types)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _rust_collect_type_refs(c, source, generic, out, local_types)


def _rust_simple_generic_impl_key(node, source: bytes) -> str | None:
    """Return a stable owner/arity key for a deliberately narrow impl shape."""
    if node.child_by_field_name("trait") is not None:
        return None
    parameters = node.child_by_field_name("type_parameters")
    owner_type = node.child_by_field_name("type")
    if parameters is None or owner_type is None or owner_type.type != "generic_type":
        return None
    if any(child.type == "where_clause" for child in node.named_children):
        return None

    parameter_names: list[str] = []
    for parameter in parameters.named_children:
        if parameter.type != "type_parameter":
            return None
        named = parameter.named_children
        if len(named) != 1 or named[0].type != "type_identifier":
            return None
        name = _read_text(named[0], source)
        if not name or name in parameter_names:
            return None
        parameter_names.append(name)
    if not parameter_names:
        return None

    owner = owner_type.child_by_field_name("type")
    if owner is None or owner.type != "type_identifier":
        return None
    arguments = next(
        (child for child in owner_type.named_children if child.type == "type_arguments"),
        None,
    )
    if arguments is None:
        return None
    argument_names = [
        _read_text(argument, source)
        for argument in arguments.named_children
        if argument.type == "type_identifier"
    ]
    if len(argument_names) != len(arguments.named_children):
        return None
    if argument_names != parameter_names:
        return None

    owner_name = _read_text(owner, source)
    return f"{owner_name}/{len(parameter_names)}" if owner_name else None


_RUST_TRAIT_METHOD_BLOCKLIST: frozenset[str] = frozenset({
    "new", "default", "parse", "from_str", "now", "clone", "into", "from",
    "to_string", "to_owned", "len", "is_empty", "iter", "next", "build",
    "start", "run", "init", "app", "get", "set", "push", "pop", "insert",
    "remove", "contains", "collect", "map", "filter", "unwrap", "expect",
    "ok", "err", "some", "none", "send", "recv", "lock", "read", "write",
})

_RUST_PRIMITIVE_TYPES: frozenset[str] = frozenset({
    "bool", "char", "str", "f32", "f64",
    "i8", "i16", "i32", "i64", "i128", "isize",
    "u8", "u16", "u32", "u64", "u128", "usize",
})


def _rust_qualifier_type(path_node, source: bytes) -> str | None:
    """The type a `Type::f()` call is qualified by, or None for a module path.

    `Foo`, `crate::a::Foo`, `Foo::<T>`, `Vec::<u8>` and `i32` give their last
    segment without generic arguments; `Self` is returned as is for the caller to
    map to the enclosing impl type. Any other lowercase last segment is a module
    (`fs::read`, `self::helper`), and `<T as Trait>` has no segment of its own:
    both give None.
    """
    if path_node is None:
        return None
    last = _rust_type_last_segment(_read_text(path_node, source))
    return last if last[:1].isupper() or last in _RUST_PRIMITIVE_TYPES else None


def _rust_type_last_segment(text: str) -> str:
    """`crate::a::Foo<T>` -> `Foo`: the last path segment, generic arguments dropped.
    A leading `&`, `&'a mut` or `dyn` (`impl Tr for &'a Foo`) is not part of it."""
    text = re.sub(r"^(?:&\s*(?:'\w+\s+)?(?:mut\s+)?|dyn\s+)", "", text.strip())
    depth, kept = 0, []
    for ch in text:
        if ch == "<":
            depth += 1
        elif ch == ">":
            depth = max(depth - 1, 0)
        elif depth == 0:
            kept.append(ch)
    segments = [s.strip() for s in "".join(kept).split("::") if s.strip()]
    return segments[-1] if segments else ""


def extract_rust(path: Path) -> dict:
    """Extract functions, structs, enums, traits, impl methods, statics/consts, and use declarations from a .rs file."""
    try:
        import tree_sitter_rust as tsrust
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-rust not installed"}

    try:
        language = Language(tsrust.language())
        parser = Parser(language)
        source = _read_source_bytes(path)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object, str | None, str | None]] = []
    impl_keys: dict[str, str | None] = {}

    # Names this file defines as a type (struct/enum/trait/union/alias) before it
    # starts referring to them. A local definition shadows the prelude, so its
    # references must not be dropped by the builtin-name filter further down.
    local_types: set[str] = set()

    def _scan_local_types(scan_node) -> None:
        if scan_node.type in ("struct_item", "enum_item", "trait_item", "union_item", "type_item"):
            name_node = scan_node.child_by_field_name("name")
            if name_node is not None:
                name = _read_text(name_node, source)
                if name:
                    local_types.add(name)
        for child in scan_node.children:
            _scan_local_types(child)

    _scan_local_types(root)
    local_type_names = frozenset(local_types)

    # `macro_rules!` macros defined in this file, keyed by bare name. A macro and a
    # function can share a name in Rust (`vec!` vs `vec`), and a macro is invoked
    # as `name!(...)` (a `macro_invocation`, never a `call_expression`), so macros
    # are resolved through their own registry rather than the function/type
    # label_to_nid to avoid cross-binding.
    macro_nids_by_name: dict[str, str] = {}

    # (bare impl type, method name) -> the method nodes this file's `impl` blocks
    # define, so an in-file `Type::f()` / `self.f()` binds to a method of that type.
    impl_methods: dict[tuple[str, str], set[str]] = {}

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
            })

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    # Pre-scan the struct/enum/trait names declared in this file so a type used
    # above its declaration resolves exactly as a use below it already does,
    # rather than to a sourceless stub that the corpus-level rewire only folds
    # back when the name is unique across the corpus (#3782). Only these three
    # items are pre-registered: walk() never makes a node of a `type` alias or a
    # `union`, so registering one would leave its references pointing at no node.
    # The scan never descends further than walk() does, so every id registered
    # here ends up as a node. Ids are casefolded, so `fn handle` and
    # `struct Handle` (or `struct HANDLE` and `struct Handle`) share one and
    # walk() keeps whichever comes first: a type is only pre-registered when
    # every file-level item behind its id is that same type (`#[cfg]` twins count
    # once), and it is matched by its exact name, since a `type HANDLE` alias or
    # an imported `HANDLE` shares the id of a local `struct Handle`. Otherwise the
    # forward reference keeps the sourceless stub v8's extractor gives it. An
    # `impl` block counts as the type it names, because walk() gives it the node
    # of its type text (`impl Tr for HANDLE` collides with `struct Handle`,
    # `impl Tr for &Handle<'_>` does not); methods and impl-scoped items have
    # impl-qualified ids and are not counted.
    items_by_id: dict[str, set[tuple[bool, str]]] = {}
    declared_type_ids: set[str] = set()

    def _scan_type_items(node) -> None:
        t = node.type
        if t in ("struct_item", "enum_item", "trait_item", "function_item",
                 "function_signature_item", "static_item", "const_item"):
            name_node = node.child_by_field_name("name")
            if name_node:
                name = _read_text(name_node, source)
                if t in ("static_item", "const_item") and name == "_":
                    return
                nid = _make_id(stem, name)
                is_type = t in ("struct_item", "enum_item", "trait_item")
                items_by_id.setdefault(nid, set()).add((is_type, name))
                if is_type:
                    declared_type_ids.add(nid)
            return
        if t == "impl_item":
            type_node = node.child_by_field_name("type")
            if type_node is not None:
                type_name = _read_text(type_node, source).strip()
                refs: list[tuple[str, str]] = []
                _rust_collect_type_refs(type_node, source, False, refs)
                bare = next((ref for ref, role in refs if role == "type"), type_name)
                items_by_id.setdefault(_make_id(stem, type_name), set()).add((True, bare))
            return
        if t == "use_declaration":
            return
        for child in node.children:
            _scan_type_items(child)

    _scan_type_items(root)
    local_type_names = {
        next(iter(items))[1] for nid, items in items_by_id.items()
        if nid in declared_type_ids and len(items) == 1
    }

    def ensure_named_node(name: str, line: int) -> str:
        nid = _make_id(stem, name)
        if nid in seen_ids or name in local_type_names:
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

    def emit_param_return_refs(func_node, func_nid: str, line: int) -> None:
        params = func_node.child_by_field_name("parameters")
        if params is not None:
            for p in params.children:
                if p.type != "parameter":
                    continue
                type_node = p.child_by_field_name("type")
                refs: list[tuple[str, str]] = []
                _rust_collect_type_refs(type_node, source, False, refs, local_type_names)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                    tgt = ensure_named_node(ref_name, line)
                    if tgt != func_nid:
                        add_edge(func_nid, tgt, "references", line, context=ctx)
        return_type = func_node.child_by_field_name("return_type")
        if return_type is not None:
            refs = []
            _rust_collect_type_refs(return_type, source, False, refs, local_type_names)
            for ref_name, role in refs:
                ctx = "generic_arg" if role == "generic_arg" else "return_type"
                tgt = ensure_named_node(ref_name, line)
                if tgt != func_nid:
                    add_edge(func_nid, tgt, "references", line, context=ctx)

    def walk(
        node,
        parent_impl_nid: str | None = None,
        parent_impl_type: str | None = None,
        parent_impl_key: str | None = None,
    ) -> None:
        t = node.type

        if t == "function_item":
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if parent_impl_nid:
                    func_nid = _make_id(parent_impl_nid, func_name)
                    add_node(func_nid, f".{func_name}()", line)
                    add_edge(parent_impl_nid, func_nid, "method", line)
                    if parent_impl_type:
                        owner = _rust_type_last_segment(parent_impl_type)
                        impl_methods.setdefault((owner, func_name), set()).add(func_nid)
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(file_nid, func_nid, "contains", line)
                emit_param_return_refs(node, func_nid, line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((
                        func_nid,
                        body,
                        parent_impl_type,
                        parent_impl_key,
                    ))
            return

        if t == "function_signature_item":
            # `fn greet(&self) -> String;` — a trait method with no body. This node type
            # had no branch at all, so a trait's required methods were unreachable: the
            # only method nodes in a graph came from impl blocks, and a trait with no
            # implementor in the corpus contributed none. Mirrors function_item, minus
            # the body walk (there is no body).
            name_node = node.child_by_field_name("name")
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if parent_impl_nid:
                    func_nid = _make_id(parent_impl_nid, func_name)
                    add_node(func_nid, f".{func_name}()", line)
                    add_edge(parent_impl_nid, func_nid, "method", line)
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(file_nid, func_nid, "contains", line)
                emit_param_return_refs(node, func_nid, line)
            return

        if t == "macro_definition":
            # `macro_rules! name { ... }` defines a named, invocable item. This node
            # type had no branch, so the macro was dropped entirely: it was never a
            # node, and a `name!(...)` invocation of it had nothing to resolve to.
            # The id is macro-qualified so it never collides with a same-named fn or
            # type (`vec!` vs `vec`); the `!` suffix in the label marks it a macro.
            name_node = node.child_by_field_name("name")
            if name_node:
                macro_name = _read_text(name_node, source)
                if macro_name:
                    line = node.start_point[0] + 1
                    macro_nid = _make_id(stem, "macro", macro_name)
                    add_node(macro_nid, f"{macro_name}!", line)
                    add_edge(file_nid, macro_nid, "contains", line)
                    macro_nids_by_name.setdefault(macro_name, macro_nid)
            return

        if t in ("struct_item", "enum_item", "trait_item"):
            name_node = node.child_by_field_name("name")
            if name_node:
                item_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                item_nid = _make_id(stem, item_name)
                add_node(item_nid, item_name, line)
                declaration_node = next(n for n in nodes if n["id"] == item_nid)
                declaration_node["_rust_declaration_count"] = (
                    declaration_node.get("_rust_declaration_count", 0) + 1
                )
                add_edge(file_nid, item_nid, "contains", line)
                if t == "trait_item":
                    for c in node.children:
                        if c.type != "trait_bounds":
                            continue
                        for sub in c.children:
                            if not sub.is_named:
                                continue
                            refs: list[tuple[str, str]] = []
                            _rust_collect_type_refs(sub, source, False, refs, local_type_names)
                            for idx, (ref_name, _role) in enumerate(refs):
                                tgt = ensure_named_node(ref_name, line)
                                if tgt == item_nid:
                                    continue
                                rel = "inherits" if idx == 0 else "references"
                                if rel == "inherits":
                                    add_edge(item_nid, tgt, "inherits", line)
                                else:
                                    add_edge(item_nid, tgt, "references", line,
                                             context="generic_arg")
                if t == "struct_item":
                    for c in node.children:
                        if c.type != "field_declaration_list":
                            continue
                        for field in c.children:
                            if field.type != "field_declaration":
                                continue
                            type_node = field.child_by_field_name("type")
                            if type_node is None:
                                for fc in field.children:
                                    if fc.type in ("type_identifier", "generic_type",
                                                    "scoped_type_identifier",
                                                    "reference_type", "primitive_type"):
                                        type_node = fc
                                        break
                            refs = []
                            _rust_collect_type_refs(type_node, source, False, refs, local_type_names)
                            for ref_name, role in refs:
                                ctx = "generic_arg" if role == "generic_arg" else "field"
                                tgt = ensure_named_node(ref_name, field.start_point[0] + 1)
                                if tgt != item_nid:
                                    add_edge(item_nid, tgt, "references",
                                             field.start_point[0] + 1, context=ctx)
                    # Tuple structs (`struct Wrapper(pub Logger, Config);`) nest their
                    # positional field types directly under ordered_field_declaration_list
                    # with no field_declaration wrapper -- the same shape handled for tuple
                    # enum variants below. Without this branch these field type references
                    # are silently dropped.
                    for c in node.children:
                        if c.type != "ordered_field_declaration_list":
                            continue
                        fline = c.start_point[0] + 1
                        for tc in c.children:
                            if tc.type not in ("type_identifier", "generic_type",
                                               "scoped_type_identifier", "reference_type",
                                               "primitive_type", "tuple_type", "array_type"):
                                continue
                            refs = []
                            _rust_collect_type_refs(tc, source, False, refs, local_type_names)
                            for ref_name, role in refs:
                                ctx = "generic_arg" if role == "generic_arg" else "field"
                                tgt = ensure_named_node(ref_name, fline)
                                if tgt != item_nid:
                                    add_edge(item_nid, tgt, "references", fline, context=ctx)
                if t == "enum_item":
                    # Variant payload types nest under enum_variant_list ->
                    # enum_variant -> ordered_field_declaration_list (tuple variant,
                    # `Click(Logger)`) | field_declaration_list (struct variant,
                    # `Resize { size: Dim }`). Neither was traversed, so every
                    # enum-variant type reference was silently dropped.
                    _TYPE_NODES = ("type_identifier", "generic_type",
                                   "scoped_type_identifier", "reference_type",
                                   "primitive_type", "tuple_type", "array_type")

                    def _emit_enum_type(type_node, at_line):
                        if type_node is None:
                            return
                        refs2: list[tuple[str, str]] = []
                        _rust_collect_type_refs(type_node, source, False, refs2, local_type_names)
                        for ref_name, role in refs2:
                            ctx = "generic_arg" if role == "generic_arg" else "field"
                            tgt = ensure_named_node(ref_name, at_line)
                            if tgt != item_nid:
                                add_edge(item_nid, tgt, "references", at_line, context=ctx)

                    for c in node.children:
                        if c.type != "enum_variant_list":
                            continue
                        for variant in c.children:
                            if variant.type != "enum_variant":
                                continue
                            vline = variant.start_point[0] + 1
                            # Emit a node per variant with a case_of edge back to
                            # the enum. Only the variants' payload types were
                            # walked before, so the variants themselves (`Circle`,
                            # `Square`, `Empty`) never became nodes and the enum
                            # was left a memberless leaf. This is the Rust parity
                            # of Java #1719 / Kotlin #1738 / Swift / Scala enums.
                            # The variant name is the enum_variant's `identifier`.
                            vname_node = next(
                                (vc for vc in variant.children
                                 if vc.type == "identifier"),
                                None,
                            )
                            if vname_node is not None:
                                vname = _read_text(vname_node, source)
                                if vname:
                                    variant_nid = _make_id(item_nid, vname)
                                    add_node(variant_nid, vname, vline)
                                    add_edge(item_nid, variant_nid, "case_of", vline)
                            for vc in variant.children:
                                if vc.type == "ordered_field_declaration_list":
                                    for tc in vc.children:
                                        if tc.type in _TYPE_NODES:
                                            _emit_enum_type(tc, vline)
                                elif vc.type == "field_declaration_list":
                                    for field in vc.children:
                                        if field.type != "field_declaration":
                                            continue
                                        type_node = field.child_by_field_name("type")
                                        _emit_enum_type(type_node, field.start_point[0] + 1)
                if t == "trait_item":
                    # The methods a trait declares are its contract, and they were not
                    # reached: this branch returns below, so nothing walked the body.
                    # Descend the same way impl_item does, attributing each method to
                    # the trait node — so `explain <Trait>` can list what an
                    # implementor must provide.
                    body = node.child_by_field_name("body")
                    if body:
                        for child in body.children:
                            walk(child, parent_impl_nid=item_nid)
            return

        if t in ("static_item", "const_item"):
            # `static NAME: T = …;` / `const NAME: T = …;` at module level, or an
            # associated const inside an impl. Neither node type had a branch, so a
            # constant reached the graph only through files that referenced it,
            # never from the Rust that defines it (#3471).
            name_node = node.child_by_field_name("name")
            if name_node:
                item_name = _read_text(name_node, source)
                if item_name == "_":
                    return
                line = node.start_point[0] + 1
                if parent_impl_nid:
                    item_nid = _make_id(parent_impl_nid, item_name)
                    add_node(item_nid, f".{item_name}", line)
                    add_edge(parent_impl_nid, item_nid, "contains", line)
                else:
                    item_nid = _make_id(stem, item_name)
                    add_node(item_nid, item_name, line)
                    add_edge(file_nid, item_nid, "contains", line)
                type_node = node.child_by_field_name("type")
                if type_node is not None:
                    refs: list[tuple[str, str]] = []
                    _rust_collect_type_refs(type_node, source, False, refs, local_type_names)
                    for ref_name, role in refs:
                        tgt = ensure_named_node(ref_name, line)
                        if tgt == item_nid:
                            continue
                        ctx = "generic_arg" if role == "generic_arg" else "field"
                        add_edge(item_nid, tgt, "references", line, context=ctx)
            return

        if t == "impl_item":
            type_node = node.child_by_field_name("type")
            trait_node = node.child_by_field_name("trait")
            impl_nid: str | None = None
            impl_type_bare: str | None = None
            impl_key: str | None = None
            if type_node:
                type_name = _read_text(type_node, source).strip()
                impl_nid = _make_id(stem, type_name)
                add_node(impl_nid, type_name, node.start_point[0] + 1)
                impl_key = _rust_simple_generic_impl_key(node, source)
                # Bare name (generics stripped) for typing a `self.` receiver
                # inside this block's methods (#2234) — `impl Foo<T>` types
                # `self` as `Foo`, not the literal `Foo<T>` text.
                impl_type_bare = type_name.split("<")[0].strip()
            if trait_node is not None and impl_nid is not None:
                refs: list[tuple[str, str]] = []
                _rust_collect_type_refs(trait_node, source, False, refs, local_type_names)
                for idx, (ref_name, _role) in enumerate(refs):
                    tgt = ensure_named_node(ref_name, node.start_point[0] + 1)
                    if tgt == impl_nid:
                        continue
                    if idx == 0:
                        add_edge(impl_nid, tgt, "implements", node.start_point[0] + 1)
                    else:
                        add_edge(impl_nid, tgt, "references", node.start_point[0] + 1,
                                 context="generic_arg")
            body = node.child_by_field_name("body")
            if body:
                has_methods = any(
                    child.type in ("function_item", "function_signature_item")
                    for child in body.children
                )
                if impl_nid is not None and has_methods:
                    if impl_nid not in impl_keys:
                        impl_keys[impl_nid] = impl_key
                    elif impl_keys[impl_nid] != impl_key:
                        impl_keys[impl_nid] = None
                    impl_node = next(n for n in nodes if n["id"] == impl_nid)
                    if impl_keys[impl_nid]:
                        impl_node["_rust_impl_key"] = impl_keys[impl_nid]
                    else:
                        impl_node.pop("_rust_impl_key", None)
                for child in body.children:
                    walk(
                        child,
                        parent_impl_nid=impl_nid,
                        parent_impl_type=impl_type_bare,
                        parent_impl_key=impl_key,
                    )
            return

        if t == "use_declaration":
            arg = node.child_by_field_name("argument")
            if arg:
                raw = _read_text(arg, source)
                clean = raw.split("{")[0].rstrip(":").rstrip("*").rstrip(":")
                module_name = clean.split("::")[-1].strip()
                if module_name:
                    tgt_nid = _make_id(module_name)
                    add_edge(file_nid, tgt_nid, "imports_from", node.start_point[0] + 1, context="import")
            return

        for child in node.children:
            walk(child, parent_impl_nid=None)

    walk(root)

    # A bare `f()` can only reach a free function or a type (a tuple struct or
    # variant constructor), and `x.f()` only a method, so each call shape looks up
    # its own index: one shared name index let `drop(x)` bind to `impl Drop`'s
    # `drop` and `x.len()` to a free `fn len`.
    label_to_nid: dict[str, str] = {}
    method_label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        if raw.startswith("."):
            if raw.endswith(")"):
                method_label_to_nid[normalised] = n["id"]
        else:
            label_to_nid[normalised] = n["id"]

    # Nodes whose label has no `()` suffix are data definitions (structs, enums,
    # traits, statics), not callables. In Rust `Foo(x)` / `Foo { .. }` onto one
    # of them constructs a value rather than invoking a function, so the edge is
    # a `references` (context "constructor"), not a `calls`. Without this a
    # newtype used everywhere (`ClientId(id)`) reads as a top call hub.
    type_nids: set[str] = {n["id"] for n in nodes if not n["label"].endswith(")")}

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(
        node,
        caller_nid: str,
        self_type: str | None = None,
        self_impl_key: str | None = None,
    ) -> None:
        if node.type == "function_item":
            return
        if node.type == "macro_invocation":
            # `name!(...)` invoking a macro_rules! macro defined in this file.
            # Resolve only a bare `identifier` macro against the local registry;
            # a `scoped_identifier` (`log::info!`) is cross-module/crate and stays
            # unresolved (fail-closed), matching how scoped calls are handled above.
            macro_node = node.child_by_field_name("macro")
            if macro_node is not None and macro_node.type == "identifier":
                macro_name = _read_text(macro_node, source)
                tgt_nid = macro_nids_by_name.get(macro_name)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "calls",
                            "context": "call",
                            "confidence": "EXTRACTED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })
            # Fall through to the generic child recursion below rather than
            # returning, preserving the prior traversal of the invocation's
            # subtree (its arguments are a raw token tree, so this neither adds
            # nor drops any nested edges relative to before).
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            is_member_call: bool = False
            is_scoped_call: bool = False
            is_self_call: bool = False
            qualifier_type: str | None = None
            if func_node:
                if func_node.type == "identifier":
                    callee_name = _read_text(func_node, source)
                elif func_node.type == "field_expression":
                    is_member_call = True
                    field = func_node.child_by_field_name("field")
                    if field:
                        callee_name = _read_text(field, source)
                    receiver = func_node.child_by_field_name("value")
                    if receiver is not None and receiver.type == "self":
                        is_self_call = True
                elif func_node.type == "scoped_identifier":
                    # Type::method() — still allow in-file EXTRACTED match, but
                    # skip cross-file resolution: bare last-segment lookup ignores
                    # crate boundaries and produces spurious INFERRED edges (#908).
                    is_scoped_call = True
                    name = func_node.child_by_field_name("name")
                    if name:
                        callee_name = _read_text(name, source)
                    qualifier_type = _rust_qualifier_type(func_node.child_by_field_name("path"), source)
                    if qualifier_type == "Self":
                        # A trait's default method has no impl type: "" matches
                        # no method, so `Self::f()` there binds nothing in-file.
                        qualifier_type = self_type or ""
            if (
                callee_name
                and callee_name not in _LANGUAGE_BUILTIN_GLOBALS
                and (callee_name not in _RUST_BUILTIN_TYPES or callee_name in local_types)
            ):
                if qualifier_type is not None or (is_self_call and self_type):
                    # `Type::f()` / `Self::f()` / `self.f()` name the type whose
                    # method is called: bind only to that type's method in this
                    # file. Matching the bare name instead sent `Arc::new(x)` and
                    # `B::new()` to whichever `fn new` the file happened to define.
                    owner = _rust_type_last_segment(qualifier_type or self_type or "")
                    owned = impl_methods.get((owner, callee_name), set())
                    tgt_nid = next(iter(owned)) if len(owned) == 1 else None
                    if tgt_nid is None and qualifier_type is not None:
                        # `Enum::Variant(x)` constructs a value: the variant node.
                        named = label_to_nid.get(callee_name)
                        tgt_nid = named if named in type_nids else None
                elif is_member_call:
                    tgt_nid = method_label_to_nid.get(callee_name)
                else:
                    tgt_nid = label_to_nid.get(callee_name)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        is_constructor = tgt_nid in type_nids
                        edges.append({
                            "source": caller_nid,
                            "target": tgt_nid,
                            "relation": "references" if is_constructor else "calls",
                            "context": "constructor" if is_constructor else "call",
                            "confidence": "EXTRACTED",
                            "source_file": str_path,
                            "source_location": f"L{line}",
                            "weight": 1.0,
                        })
                elif not is_scoped_call and callee_name.lower() not in _RUST_TRAIT_METHOD_BLOCKLIST:
                    rc_entry = {
                        "caller_nid": caller_nid,
                        "callee": callee_name,
                        "is_member_call": is_member_call,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                    }
                    if is_self_call and self_type:
                        rc_entry["rust_self_type"] = self_type
                        if self_impl_key:
                            rc_entry["rust_self_impl_key"] = self_impl_key
                    raw_calls.append(rc_entry)
        for child in node.children:
            walk_calls(child, caller_nid, self_type, self_impl_key)

    for caller_nid, body_node, impl_type, impl_key in function_bodies:
        walk_calls(body_node, caller_nid, impl_type, impl_key)

    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
