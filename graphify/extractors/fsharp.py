"""F# extractor (own module, optional tree-sitter-fsharp dependency).

Handles implementation files (.fs) and scripts (.fsx) via ionide's
tree-sitter-fsharp ``language()`` grammar, which covers both. Signature files
(.fsi, ``language_signature()``) are deliberately not wired yet.

F# is ML-family, so this module follows graphify/extractors/ocaml.py closely:
the same sourceless ref-stub discipline for cross-file targets (#1402), the
same local-definition table with ambiguity tracking, and the same two-pass
call resolution so forward references (``let rec ... and ...``) resolve.

What is F#-specific:

* **Names are nested, not a field.** A type's name sits at
  ``type_definition > *_type_defn > type_name > identifier``; a function's at
  ``function_declaration_left > identifier``; a value's at
  ``value_declaration_left > identifier_pattern > long_identifier_or_op``;
  a member's at ``method_or_prop_defn > property_or_ident`` (last identifier —
  ``this.Run`` carries two, a static member one).
* **Pipelines carry the calls.** ``x |> f`` is an ``infix_expression`` whose
  callee is the *right* operand (``f <| x`` mirrors it on the left). Plain
  application ``f x`` is an ``application_expression`` whose callee is its
  first named child. Both feed the same call-site table.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text

# *_type_defn wrappers under type_definition, per the grammar (fsharp/grammar.js).
_TYPE_DEFN_KINDS = frozenset({
    "record_type_defn", "union_type_defn", "interface_type_defn",
    "enum_type_defn", "type_abbrev_defn", "type_extension",
    "type_declaration", "delegate_type_defn", "anon_type_defn",
})

# Pipe operators whose non-function operand is data, not a callee.
_PIPE_RIGHT = frozenset({"|>", "||>", "|||>"})   # callee on the right
_PIPE_LEFT = frozenset({"<|", "<||", "<|||"})    # callee on the left


def extract_fsharp(path: Path) -> dict:
    """Extract modules, namespaces, types, union cases, members, let-bound
    functions/values, ``open`` imports, and calls (application + pipeline)
    from an F# source file."""
    try:
        import tree_sitter_fsharp as tsfsharp
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-fsharp not installed"}

    try:
        parser = Parser(Language(tsfsharp.language()))
        source = path.read_bytes()
        root = parser.parse(source).root_node
    except Exception as e:  # pragma: no cover - grammar load failure
        return {"nodes": [], "edges": [], "error": f"failed to load: {e}"}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    local_defs: dict[str, str] = {}
    ambiguous: set[str] = set()
    # Module/namespace/type names DEFINED here: a qualified call `M.f` may only
    # bind to a local `f` when `M` is one of these (mirrors ocaml.py).
    local_containers: set[str] = set()
    # (caller_nid, callee_name, qualifier_root_or_None, full_path_text, line)
    call_sites: list[tuple[str, str, str | None, str, int]] = []

    node_labels: dict[str, str] = {}

    def add_node(nid: str, label: str, line: int) -> None:
        node_labels.setdefault(nid, label)
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
                 confidence: str = "EXTRACTED", weight: float = 1.0) -> None:
        edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        })

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def ref_stub(name: str) -> str:
        """Sourceless stub for a cross-file target; the corpus rewire collapses
        it onto the unique real definition (#1402 — a sourced stub would bake
        this file's path into the id and block the rewire)."""
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

    def line_of(node) -> int:
        return node.start_point[0] + 1

    def register_def(name: str, nid: str) -> None:
        if name in ambiguous:
            return
        if name in local_defs and local_defs[name] != nid:
            ambiguous.add(name)
            local_defs.pop(name, None)
            return
        local_defs[name] = nid

    def identifiers_of(node) -> list[str]:
        """All `identifier` leaf texts under a (long_)identifier-ish node, in
        source order. `Grasp.Sidecar.Demo` -> ["Grasp", "Sidecar", "Demo"]."""
        out: list[str] = []

        def rec(n) -> None:
            if n.type == "identifier":
                out.append(_read_text(n, source))
                return
            for c in n.children:
                rec(c)

        rec(node)
        return out

    def dotted_parts(node) -> list[str]:
        return identifiers_of(node)

    def first_child(node, *types):
        for c in node.children:
            if c.type in types:
                return c
        return None

    def type_name_of(defn) -> tuple[str | None, int]:
        tn = first_child(defn, "type_name")
        if tn is None:
            return None, line_of(defn)
        parts = identifiers_of(tn)
        return (parts[-1] if parts else None), line_of(tn)

    def emit_union_cases(defn, type_nid: str) -> None:
        cases = first_child(defn, "union_type_cases")
        if cases is None:
            return
        for case in cases.children:
            if case.type != "union_type_case":
                continue
            ident = first_child(case, "identifier")
            if ident is None:
                continue
            cname = _read_text(ident, source)
            cnid = _make_id(stem, cname)
            add_node(cnid, cname, line_of(case))
            add_edge(type_nid, cnid, "contains", line_of(case))
            register_def(cname, cnid)

    def emit_member(member_defn, type_nid: str, owner_label: str = "") -> str | None:
        """member this.Run() / static member Default — name is the LAST
        identifier of property_or_ident (the first is the self-identifier when
        present). Returns the member nid for call attribution in its body.

        The node id is qualified by the OWNING TYPE, not just the file: F#
        repeats member names constantly (every IDisposable impl has a Dispose),
        and a file-scoped id would merge same-named members of different types
        in one file into a single node."""
        mp = first_child(member_defn, "method_or_prop_defn", "member_signature")
        if mp is None:
            return None
        poi = first_child(mp, "property_or_ident", "identifier")
        if poi is None:
            return None
        parts = identifiers_of(poi)
        if not parts:
            return None
        mname = parts[-1]
        line = line_of(member_defn)
        mnid = _make_id(stem, owner_label, mname) if owner_label else _make_id(stem, mname)
        add_node(mnid, mname, line)
        add_edge(type_nid, mnid, "contains", line)
        register_def(mname, mnid)
        return mnid

    def record_call(callee_node, caller: str) -> None:
        """Register a call site from a long_identifier_or_op callee node."""
        parts = dotted_parts(callee_node)
        if not parts:
            return
        callee = parts[-1]
        qualifier = parts[0] if len(parts) > 1 else None
        call_sites.append((caller, callee, qualifier,
                           ".".join(parts), line_of(callee_node)))

    def callee_operand(node):
        """The callee node of an expression operand, if it is one: a bare
        long_identifier_or_op (`validate`, `sb.Append`), or the function head
        of a nested application (`makeConfig cfg.Host |> validate` — the LEFT
        operand is itself an application already handled on descent)."""
        if node.type == "long_identifier_or_op":
            return node
        return None

    def walk(node, container_nid: str, enclosing_value: str) -> None:
        t = node.type

        if t == "import_decl":  # open X.Y
            li = first_child(node, "long_identifier")
            if li is not None:
                parts = dotted_parts(li)
                if parts:
                    add_edge(container_nid, ref_stub(parts[-1]),
                             "imports_from", line_of(node), confidence="INFERRED")
            return

        if t in ("named_module", "module_defn", "namespace"):
            name_node = first_child(node, "long_identifier", "identifier")
            parts = dotted_parts(name_node) if name_node is not None else []
            if parts:
                mname = parts[-1]
                line = line_of(node)
                mnid = _make_id(stem, mname)
                add_node(mnid, mname, line)
                add_edge(container_nid, mnid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(mname, mnid)
                local_containers.update(parts)
                for child in node.children:
                    walk(child, mnid, enclosing_value)
                return

        if t == "type_definition":
            for defn in node.children:
                if defn.type not in _TYPE_DEFN_KINDS:
                    continue
                tname, line = type_name_of(defn)
                if not tname:
                    continue
                tnid = _make_id(stem, tname)
                add_node(tnid, tname, line)
                add_edge(container_nid, tnid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(tname, tnid)
                local_containers.add(tname)
                emit_union_cases(defn, tnid)
                # Class bodies (anon_type_defn etc.): members + primary-ctor body.
                for child in defn.children:
                    if child.type == "type_extension_elements":
                        for el in child.children:
                            if el.type == "member_defn":
                                mnid = emit_member(el, tnid, tname)
                                for sub in el.children:
                                    walk(sub, tnid, mnid or tnid)
                            else:
                                walk(el, tnid, enclosing_value)
                    elif child.type not in ("type_name", "union_type_cases"):
                        walk(child, tnid, enclosing_value)
            return

        if t == "exception_definition":
            li = first_child(node, "long_identifier", "identifier")
            parts = dotted_parts(li) if li is not None else []
            if parts:
                ename = parts[-1]
                line = line_of(node)
                enid = _make_id(stem, ename)
                add_node(enid, ename, line)
                add_edge(container_nid, enid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(ename, enid)
            return

        if t == "member_defn":
            # A member outside type_extension_elements (type augmentation).
            mnid = emit_member(node, container_nid, node_labels.get(container_nid, ""))
            for child in node.children:
                walk(child, container_nid, mnid or enclosing_value)
            return

        if t == "function_or_value_defn":
            # Mint a definition only when not already inside a value's body
            # (a nested `let x = e` keeps the outer scope for call attribution
            # and must not steal it — mirrors ocaml.py's is_toplevel rule).
            new_scope = enclosing_value
            if not enclosing_value:
                head = first_child(node, "function_declaration_left",
                                   "value_declaration_left")
                if head is not None:
                    if head.type == "function_declaration_left":
                        ident = first_child(head, "identifier")
                        name = _read_text(ident, source) if ident is not None else None
                    else:
                        # value_declaration_left: the name is the FIRST
                        # long_identifier_or_op under identifier_pattern.
                        # Taking the subtree's last identifier instead grabs a
                        # type annotation — `let subscribe ... : IDisposable =`
                        # minted a sourced `IDisposable` node that the dotnet
                        # family rewire then bound every BCL reference to.
                        name = None
                        ip = first_child(head, "identifier_pattern")
                        if ip is not None:
                            lio = first_child(ip, "long_identifier_or_op")
                            if lio is not None:
                                parts = identifiers_of(lio)
                                name = parts[-1] if parts else None
                    if name:
                        line = line_of(head)
                        nid = _make_id(stem, name)
                        add_node(nid, name, line)
                        add_edge(container_nid, nid,
                                 "defines" if container_nid == file_nid else "contains",
                                 line)
                        register_def(name, nid)
                        new_scope = nid
            for child in node.children:
                walk(child, container_nid, new_scope)
            return

        if t == "application_expression":
            fn = node.named_children[0] if node.named_children else None
            if fn is not None and fn.type == "long_identifier_or_op":
                record_call(fn, enclosing_value or container_nid)
            # Fall through: arguments may contain further applications.

        if t == "infix_expression":
            op = first_child(node, "infix_op")
            operands = [c for c in node.named_children if c.type != "infix_op"]
            if op is not None and len(operands) == 2:
                op_text = _read_text(op, source)
                target = None
                if op_text in _PIPE_RIGHT:
                    target = callee_operand(operands[1])
                elif op_text in _PIPE_LEFT:
                    target = callee_operand(operands[0])
                if target is not None:
                    record_call(target, enclosing_value or container_nid)
            # Fall through: both operands need walking (nested pipes, args).

        for child in node.children:
            walk(child, container_nid, enclosing_value)

    walk(root, file_nid, "")

    for caller, callee, qualifier, full_path, line in call_sites:
        # Qualified call whose root is not defined here (`StringBuilder`
        # methods, `List.map`): keep it distinct so the rewire can't bind it to
        # a same-named local (ocaml.py's rule, verbatim rationale).
        if qualifier is not None and qualifier not in local_containers:
            if callee in local_defs:
                add_edge(caller, ref_stub(full_path), "calls", line,
                         confidence="INFERRED")
            else:
                add_edge(caller, ref_stub(callee), "calls", line,
                         confidence="INFERRED")
        elif callee in local_defs:
            add_edge(caller, local_defs[callee], "calls", line)
        else:
            add_edge(caller, ref_stub(callee), "calls", line, confidence="INFERRED")

    return {"nodes": nodes, "edges": edges}
