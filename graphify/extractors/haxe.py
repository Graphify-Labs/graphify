"""Haxe extractor.

Haxe has no single canonical tree-sitter grammar, and the competing forks do
not agree on node names. This module therefore probes the installed grammar
for its node vocabulary and dispatches to an extractor written against that
vocabulary, rather than assuming one.

Only the tong dialect is implemented. To add another grammar: write an
``_extract_haxe_<dialect>`` mirroring :func:`_extract_haxe_tong`'s contract
(same node ids, same edge relations, so the two are comparable on the same
input), give it a marker node type in ``_DIALECT_MARKERS``, and dispatch to it
in :func:`extract_haxe`. Do not widen a dialect's extractor to cover a second
grammar -- the vocabularies collide (both forks even install under the same
package name, ``tree-sitter-haxe``), which is exactly what the probe exists to
disambiguate.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import (
    _LANGUAGE_BUILTIN_GLOBALS,
    _file_stem,
    _make_id,
    _read_text,
)


#: Node type each known grammar emits for `class A {}`, which is enough to
#: tell the dialects apart. `ClassType` is tong's; `class_declaration` is the
#: vantreeseba fork's, listed so an old workspace gets a message naming what it
#: has rather than an anonymous refusal.
_DIALECT_MARKERS = {
    "ClassType": "tong",
    "class_declaration": "vantreeseba",
}

#: Dialects with an extractor in this module.
_SUPPORTED_DIALECTS = frozenset({"tong"})

_HAXE_DIALECT: "str | None" = None


def _detect_haxe_dialect() -> str:
    """Name the installed grammar's node vocabulary. Probed once, then cached.

    Returns a key of ``_DIALECT_MARKERS``, ``"none"`` when no grammar is
    installed, or ``"unknown"`` when a grammar is installed but emits a
    vocabulary this module has never seen.

    ``"unknown"`` is deliberately distinct from ``"none"``. Guessing a dialect
    produces a silently different graph rather than an error -- no exception,
    no empty result, just fewer and differently-shaped nodes -- which is the
    worst failure this module can have, because nothing downstream can detect
    it. So an unrecognised grammar is refused by name instead.
    """
    global _HAXE_DIALECT
    if _HAXE_DIALECT is not None:
        return _HAXE_DIALECT
    try:
        import tree_sitter_haxe as _tshaxe
        from tree_sitter import Language, Parser
        root = Parser(Language(_tshaxe.language())).parse(b"class A {}").root_node
        kinds = {c.type for c in root.children}
    except Exception:
        _HAXE_DIALECT = "none"
        return _HAXE_DIALECT
    for marker, dialect in _DIALECT_MARKERS.items():
        if marker in kinds:
            _HAXE_DIALECT = dialect
            break
    else:
        _HAXE_DIALECT = "unknown"
    return _HAXE_DIALECT


def _extract_haxe_tong(path: Path) -> dict:
    """Extract from a .hx file parsed by the tong-derived grammar.

    tong's tree differs in three ways that matter here: ``ClassType``
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

    def add_edge(src, tgt, relation, line, confidence="EXTRACTED", context=None):
        if src and tgt and src != tgt:
            e = {"source": src, "target": tgt, "relation": relation,
                 "confidence": confidence, "source_file": str_path,
                 "source_location": f"L{line}", "weight": 1.0}
            if context:
                e["context"] = context
            edges.append(e)

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
        # children -- plus, for an import that reaches a sub-type, one `sub`
        # field per extra segment, emitted as a bare identifier:
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
        # Resolution policy: resolve within the same file only, and DROP an
        # unresolved call rather than inventing a node for it. A bare,
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

        # Class fields. Without this the graph held a class's behaviour and
        # none of its data -- `Achievements.hx` contributed 54 nodes, every one
        # a class or a method, and not one of its declared fields. Emitted as
        # `defines` with context "field", matching what the other extractors
        # use, and labelled bare so a field reads differently from a method's
        # `name()`.
        #
        # A property with accessors (`var p(get, never):Bool`) is one field
        # here, not three: the `get`/`set` entries are a property_accessor
        # child, and the accessor methods, where they exist, are separate
        # ClassMethod nodes already.
        if t == "ClassVar":
            name_node = node.child_by_field_name("name")
            if name_node is None:
                return
            field_name = _read_text(name_node, source)
            line = node.start_point[0] + 1
            if parent_nid is not None and parent_name is not None:
                field_nid = _make_id(stem, parent_name, field_name)
                add_node(field_nid, field_name, line)
                add_edge(parent_nid, field_nid, "defines", line, context="field")
            else:
                field_nid = _make_id(stem, field_name)
                add_node(field_nid, field_name, line)
                add_edge(file_nid, field_nid, "contains", line)
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
    """Extract from a .hx file, if the installed grammar is one we can read."""
    dialect = _detect_haxe_dialect()
    if dialect in _SUPPORTED_DIALECTS:
        return _extract_haxe_tong(path)
    if dialect == "none":
        return {"nodes": [], "edges": [],
                "error": "tree-sitter-haxe not installed"}
    which = (
        "an unrecognised Haxe grammar" if dialect == "unknown"
        else f"the '{dialect}' Haxe grammar"
    )
    return {
        "nodes": [], "edges": [],
        "error": (
            f"tree-sitter-haxe is installed but is {which}, which this "
            f"extractor cannot read (supported: "
            f"{', '.join(sorted(_SUPPORTED_DIALECTS))}). Every Haxe grammar "
            f"fork installs under the package name 'tree-sitter-haxe', so the "
            f"package name does not identify which one is present. Install "
            f"the supported one with: pip install git+https://github.com/"
            f"masquepublishing/tree-sitter-haxe-tong.git"
        ),
    }
