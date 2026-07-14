"""Solidity extractor.

Structural extraction over the tree-sitter-solidity grammar: contracts,
interfaces, libraries, their functions/constructors/modifiers, structs, enums,
and events, plus inheritance (`is A, B`), imports, and same-file call edges
(including modifier invocations, which are Solidity-specific call sites with
no explicit call syntax).

Scope note (be honest about the boundary, matching the smaller extractors in
this package rather than the full cross-file typed-receiver resolution the
larger OOP-language blocks in extract.py do): call resolution here is by
same-file method-NAME matching, not receiver-type checking — `x.foo()`
resolves to whichever `foo` this file defines if the name is unambiguous,
regardless of what `x` actually is (same tradeoff rust.py's label_to_nid
makes). This gets common cases right (calling through a storage variable
typed as a locally-defined interface, `Library.staticMethod()`,
`InterfaceName.method()` casts) but can mismatch if two unrelated types in
the same file happen to share a method name, and never resolves a call whose
callee name isn't defined anywhere in this file (an imported library/contract
whose body lives elsewhere) — those are still emitted via `raw_calls` for a
possible future cross-file pass. Modifier invocations (Solidity-specific call
sites with no explicit call syntax) resolve the same way.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text

_SOL_CONTAINER_TYPES = ("contract_declaration", "interface_declaration", "library_declaration")
_SOL_MEMBER_FUNCTION_TYPES = ("function_definition", "constructor_definition", "modifier_definition")


def _sol_name(node, source: bytes) -> str | None:
    """First direct `identifier` child of a declaration node."""
    for child in node.children:
        if child.type == "identifier":
            return _read_text(child, source)
    return None


def _sol_resolve_import_path(raw: str, str_path: str) -> str:
    """Resolve a Solidity import string to a node id.

    Relative paths (`./x.sol`, `../lib/y.sol`) resolve against the importing
    file's directory, matching the file-node ids emitted for every other
    `.sol` file in the corpus, so imports link up to the real file node.
    Bare/package-style paths (`@openzeppelin/...`, `hardhat/...`) still often
    point at a real vendored path inside the repo (node_modules-alike lib
    dirs), so try that same relative-to-file-dir resolution first; only fall
    back to a bare global id (an external/unindexed reference stub) if the
    resolved path doesn't look like a `.sol` file at all.
    """
    raw = raw.strip()
    base = Path(str_path).parent
    if raw.startswith(("./", "../")) or not raw.startswith(("@", "http")):
        candidate = (base / raw).as_posix()
        # Collapse ../ segments the same way the rest of the corpus's file
        # node ids are built (plain path string, no filesystem access needed
        # here — resolution against real files happens at the corpus-level id
        # rewire, same mechanism the stub nodes below rely on).
        parts: list[str] = []
        for seg in candidate.split("/"):
            if seg == "..":
                if parts:
                    parts.pop()
            elif seg not in (".", ""):
                parts.append(seg)
        return _make_id("/" + "/".join(parts) if candidate.startswith("/") else "/".join(parts))
    return _make_id(raw)


def extract_solidity(path: Path) -> dict:
    """Extract contracts, interfaces, libraries, functions, modifiers, structs,
    enums, events, inheritance, imports, and same-file calls from a .sol file."""
    try:
        import tree_sitter_solidity as tssol
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-solidity not installed"}

    try:
        language = Language(tssol.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, object]] = []

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

    def ensure_named_node(name: str, line: int) -> str:
        """Same sourceless-stub pattern as the other extractors (rust.py etc):
        prefer an in-file id if the name is locally defined, else a bare
        global id the corpus-level rewire can collapse onto the real
        cross-file definition."""
        nid = _make_id(stem, name)
        if nid in seen_ids:
            return nid
        nid = _make_id(name)
        if nid not in seen_ids:
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

    def collect_inheritance(container_node, container_nid: str, line: int) -> None:
        for child in container_node.children:
            if child.type != "inheritance_specifier":
                continue
            type_node = child.child_by_field_name("type") or next(
                (c for c in child.children if c.type == "user_defined_type"), None
            )
            if type_node is None:
                continue
            name_node = next((c for c in type_node.children if c.type == "identifier"), type_node)
            base_name = _read_text(name_node, source)
            if base_name:
                tgt = ensure_named_node(base_name, line)
                if tgt != container_nid:
                    add_edge(container_nid, tgt, "inherits", line)

    def walk_member(node, parent_nid: str | None) -> None:
        """Handle one member of a contract/interface/library body, or a
        top-level (free) declaration when parent_nid is None."""
        t = node.type

        if t in _SOL_CONTAINER_TYPES:
            walk(node)
            return

        if t in _SOL_MEMBER_FUNCTION_TYPES:
            line = node.start_point[0] + 1
            if t == "constructor_definition":
                name = "constructor"
            else:
                name = _sol_name(node, source) or "anonymous"
            label = f".{name}()" if parent_nid else f"{name}()"
            if parent_nid:
                func_nid = _make_id(parent_nid, name)
                add_node(func_nid, label, line)
                add_edge(parent_nid, func_nid, "method", line)
            else:
                func_nid = _make_id(stem, name)
                add_node(func_nid, label, line)
                add_edge(file_nid, func_nid, "contains", line)

            for child in node.children:
                if child.type == "modifier_invocation":
                    mod_name = next((c for c in child.children if c.type == "identifier"), None)
                    if mod_name is not None:
                        mtxt = _read_text(mod_name, source)
                        if mtxt:
                            tgt = ensure_named_node(mtxt, line)
                            if tgt != func_nid:
                                add_edge(func_nid, tgt, "calls", line, context="modifier_invocation")

            body = node.child_by_field_name("body") or next(
                (c for c in node.children if c.type in ("function_body",)), None
            )
            if body:
                function_bodies.append((func_nid, body))
            return

        if t in ("struct_declaration", "enum_declaration", "event_definition"):
            line = node.start_point[0] + 1
            name = _sol_name(node, source)
            if not name:
                return
            item_nid = _make_id(parent_nid, name) if parent_nid else _make_id(stem, name)
            add_node(item_nid, name, line)
            add_edge(parent_nid or file_nid, item_nid, "contains", line)
            return

    def walk(node) -> None:
        t = node.type

        if t in _SOL_CONTAINER_TYPES:
            line = node.start_point[0] + 1
            name = _sol_name(node, source)
            if not name:
                return
            container_nid = _make_id(stem, name)
            add_node(container_nid, name, line)
            add_edge(file_nid, container_nid, "contains", line)
            collect_inheritance(node, container_nid, line)
            body = next((c for c in node.children if c.type in ("contract_body", "interface_body", "library_body")), None)
            if body:
                for member in body.children:
                    walk_member(member, container_nid)
            return

        if t == "import_directive":
            line = node.start_point[0] + 1
            string_node = next((c for c in node.children if c.type == "string"), None)
            if string_node is None:
                return
            raw = _read_text(string_node, source).strip("\"' ")
            if not raw:
                return
            tgt_nid = _sol_resolve_import_path(raw, str_path)
            add_edge(file_nid, tgt_nid, "imports_from", line, context="import")
            for child in node.children:
                if child.type == "identifier" and child != string_node:
                    # Named import binding (`import {A, B as C} from ...`) —
                    # emit a same-named stub too, so a same-file reference to
                    # `A`/`C` resolves without needing the module-level
                    # target's internal structure.
                    imported_name = _read_text(child, source)
                    if imported_name:
                        ensure_named_node(imported_name, line)
            return

        # Free (top-level, outside any contract) function/struct/enum/event —
        # Solidity permits these since 0.7.
        if t in _SOL_MEMBER_FUNCTION_TYPES or t in ("struct_declaration", "enum_declaration", "event_definition"):
            walk_member(node, None)
            return

        for child in node.children:
            walk(child)

    walk(root)

    # Same-file "calls" resolution, matching rust.py's label_to_nid pattern:
    # only resolve calls whose callee name is something this file itself
    # defines (a function, contract, interface, or library visible here).
    # Anything else becomes a raw_call for a possible cross-file pass.
    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw_label = n["label"]
        normalised = raw_label.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in _SOL_MEMBER_FUNCTION_TYPES:
            return
        if node.type == "call_expression":
            expr = node.child_by_field_name("function") or (node.children[0] if node.children else None)
            # `call_expression`'s first named child is an `expression` wrapper
            # around either a bare `identifier` or a `member_expression`.
            inner = expr
            if inner is not None and inner.type == "expression" and inner.children:
                inner = inner.children[0]
            callee_name: str | None = None
            is_member_call = False
            receiver: str | None = None
            if inner is not None:
                if inner.type == "identifier":
                    callee_name = _read_text(inner, source)
                elif inner.type == "member_expression":
                    is_member_call = True
                    obj_node = inner.children[0] if inner.children else None
                    method_node = next((c for c in inner.children if c.type == "identifier"), None)
                    # Last identifier child is the method name; first is the receiver.
                    idents = [c for c in inner.children if c.type == "identifier"]
                    if len(idents) >= 2:
                        obj_node, method_node = idents[0], idents[-1]
                    if obj_node is not None:
                        receiver = _read_text(obj_node, source)
                    if method_node is not None:
                        callee_name = _read_text(method_node, source)
            if callee_name:
                tgt_nid = label_to_nid.get(callee_name)
                if tgt_nid and tgt_nid != caller_nid:
                    pair = (caller_nid, tgt_nid)
                    if pair not in seen_call_pairs:
                        seen_call_pairs.add(pair)
                        line = node.start_point[0] + 1
                        add_edge(caller_nid, tgt_nid, "calls", line, context="call")
                elif is_member_call:
                    raw_calls.append({
                        "caller_nid": caller_nid,
                        "callee": callee_name,
                        "receiver": receiver,
                        "is_member_call": True,
                        "source_file": str_path,
                        "source_location": f"L{node.start_point[0] + 1}",
                    })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    valid_ids = seen_ids
    clean_edges = []
    for edge in edges:
        src, tgt = edge["source"], edge["target"]
        if src in valid_ids and (tgt in valid_ids or edge["relation"] == "imports_from"):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
