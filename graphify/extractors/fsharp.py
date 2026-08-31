"""F# extractor (own module, optional tree-sitter-fsharp dependency).

Handles implementation files (.fs) and scripts (.fsx) via ionide's
tree-sitter-fsharp ``language()`` grammar, which covers both. Signature files
(.fsi, ``language_signature()``) are deliberately not wired yet.

F# is ML-family, so this module follows graphify/extractors/ocaml.py closely:
the same sourceless ref-stub discipline for cross-file targets (#1402), the
same local-definition table with ambiguity tracking, and the same two-pass
call resolution so forward references (``let rec ... and ...`` — every
``and``-joined head is minted, not just the first) resolve.

.NET-family conventions (so F# joins the same corpus passes as C#):

* **Namespaces are canonical.** ``namespace Grasp.Core`` emits the same
  ``csharp_namespace:<sha1>`` node id from every file (via
  engine._csharp_namespace_id) with ``type: "namespace"``, so
  _canonicalize_csharp_namespace_nodes merges them and the unique-stub rewire
  skips them. Namespace segments are NOT treated as local qualifiers: files
  across the corpus share them, so a call rooted at one must stay a stub.
* **Members are type-scoped and method-labelled.** A member's node id carries
  its owning type (two same-file ``Dispose``s stay distinct) and its label is
  ``.Name()``, matching the C# method convention the rewire indexes key on.

F#-specific handling, grounded in live AST probes of the grammar:

* **Names are nested, not a field.** A type's name sits at
  ``type_definition > *_type_defn > type_name``; a function's at
  ``function_declaration_left > identifier``; a value's at
  ``value_declaration_left > identifier_pattern > long_identifier_or_op``
  (an annotated ``let f ... : T =`` hides T in the same subtree — never take
  the last identifier of the whole head); a destructuring
  ``let (a, b) = ...`` binds via ``paren_pattern > identifier_pattern``, one
  definition per bound name; a member's at
  ``method_or_prop_defn > property_or_ident`` (last identifier — ``this.Run``
  carries two, a static member one).
* **Callees may be dotted.** ``f x`` puts a ``long_identifier_or_op`` head on
  the application; ``Grasp.Telemetry.init args`` and method-on-expression
  calls wrap it in a ``dot_expression``. Both are accepted.
* **Pipelines carry the calls.** ``x |> f`` is an ``infix_expression`` whose
  callee is the *right* operand (``f <| x`` mirrors it on the left); comment
  nodes interleave as named children and are filtered before operand counting.
* **Enums are not unions.** DU cases live under ``union_type_cases``; enum
  members under ``enum_type_cases``. Both are emitted, type-scoped.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.engine import _csharp_namespace_id

# *_type_defn wrappers under type_definition, per the grammar (fsharp/grammar.js).
_TYPE_DEFN_KINDS = frozenset({
    "record_type_defn", "union_type_defn", "interface_type_defn",
    "enum_type_defn", "type_abbrev_defn", "type_extension",
    "type_declaration", "delegate_type_defn", "anon_type_defn",
})

# Pipe operators whose non-function operand is data, not a callee.
_PIPE_RIGHT = frozenset({"|>", "||>", "|||>"})   # callee on the right
_PIPE_LEFT = frozenset({"<|", "<||", "<|||"})    # callee on the left

_COMMENT_TYPES = frozenset({"line_comment", "block_comment", "xml_doc"})

# Node types that can carry a callee name in an application/pipe position.
_CALLEE_TYPES = frozenset({"long_identifier_or_op", "dot_expression"})


def extract_fsharp(path: Path) -> dict:
    """Extract modules, namespaces, types, union/enum cases, members, let-bound
    functions/values, ``open`` imports, and calls (application + pipeline)
    from an F# source file."""
    try:
        import tree_sitter_fsharp as tsfsharp
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-fsharp not installed"}

    try:
        source = path.read_bytes()
    except OSError as e:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}: {e}"}

    try:
        parser = Parser(Language(tsfsharp.language()))
        root = parser.parse(source).root_node
    except Exception as e:  # pragma: no cover - grammar load failure
        return {"nodes": [], "edges": [], "error": f"failed to load: {e}"}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    node_labels: dict[str, str] = {}

    local_defs: dict[str, str] = {}
    ambiguous: set[str] = set()
    # Names a qualified call `M.f` may resolve THROUGH to a local `f`: modules
    # and types DEFINED here. Deliberately NOT namespace segments — the whole
    # corpus shares those, so `Sidecar.validate` under `namespace Grasp.Sidecar`
    # must stay a stub the corpus rewire can redirect, never bind locally.
    local_containers: set[str] = set()
    # (caller_nid, callee_name, qualifier_root_or_None, full_path_text, line)
    call_sites: list[tuple[str, str, str | None, str, int]] = []

    def add_node(nid: str, label: str, line: int, **extra) -> None:
        node_labels.setdefault(nid, label)
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
                **extra,
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
        """All `identifier` leaf texts under an identifier-ish node, in source
        order. `Grasp.Sidecar.Demo` -> ["Grasp", "Sidecar", "Demo"]. Works for
        long_identifier_or_op and dot_expression alike."""
        out: list[str] = []

        def rec(n) -> None:
            if n.type == "identifier":
                out.append(_read_text(n, source))
                return
            for c in n.children:
                rec(c)

        rec(node)
        return out

    def first_child(node, *types):
        for c in node.children:
            if c.type in types:
                return c
        return None

    def find_all(node, node_type: str) -> list:
        found: list = []

        def rec(n) -> None:
            if n.type == node_type:
                found.append(n)
                return
            for c in n.children:
                rec(c)

        rec(node)
        return found

    def type_name_of(defn) -> tuple[str | None, int]:
        tn = first_child(defn, "type_name")
        if tn is None:
            return None, line_of(defn)
        parts = identifiers_of(tn)
        return (parts[-1] if parts else None), line_of(tn)

    def emit_cases(defn, type_nid: str, type_name: str) -> None:
        """DU cases (union_type_cases) and enum members (enum_type_cases).
        Case ids are TYPE-scoped: two same-file DUs with an `Ok` case stay
        distinct, and the single-case wrapper `type Email = Email of string`
        gets a case node distinct from its type instead of a self-loop."""
        for wrapper in ("union_type_cases", "enum_type_cases"):
            cases = first_child(defn, wrapper)
            if cases is None:
                continue
            for case in cases.children:
                if case.type not in ("union_type_case", "enum_type_case"):
                    continue
                ident = first_child(case, "identifier")
                if ident is None:
                    continue
                cname = _read_text(ident, source)
                cnid = _make_id(stem, type_name, cname)
                add_node(cnid, cname, line_of(case))
                add_edge(type_nid, cnid, "contains", line_of(case))
                register_def(cname, cnid)

    def emit_member(member_defn, type_nid: str, owner_label: str = "") -> str | None:
        """member this.Run() / static member Default — name is the LAST
        identifier of property_or_ident (the first is the self-identifier when
        present). Returns the member nid for call attribution in its body.

        Ids are qualified by the OWNING TYPE (F# repeats member names
        constantly — every IDisposable impl has a Dispose) and labels use the
        dotnet-family `.Name()` method convention so the corpus rewire treats
        them as methods, not type-like unique-stub targets."""
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
        add_node(mnid, f".{mname}()", line)
        add_edge(type_nid, mnid, "contains", line)
        register_def(mname, mnid)
        return mnid

    def bound_value_names(head) -> list[tuple[str, int]]:
        """Names bound by a value_declaration_left, with their lines.

        - `let x = ...` / `let f (a: A) : T = ...`: the FIRST
          long_identifier_or_op under the direct identifier_pattern (never the
          subtree's last identifier — that is a type annotation).
        - `let (a, b) = ...`: one name per identifier_pattern inside the
          paren_pattern.
        """
        ip = first_child(head, "identifier_pattern")
        if ip is not None:
            lio = first_child(ip, "long_identifier_or_op")
            if lio is not None:
                parts = identifiers_of(lio)
                if parts:
                    return [(parts[-1], line_of(ip))]
            return []
        pp = first_child(head, "paren_pattern")
        if pp is not None:
            out: list[tuple[str, int]] = []
            for sub in find_all(pp, "identifier_pattern"):
                lio = first_child(sub, "long_identifier_or_op")
                if lio is not None:
                    parts = identifiers_of(lio)
                    if parts:
                        out.append((parts[-1], line_of(sub)))
            return out
        return []

    def mint_binding_head(head, container_nid: str) -> str | None:
        """Mint definition node(s) for one binding head; returns the nid to
        attribute the following body's calls to (the last minted)."""
        minted: str | None = None
        if head.type == "function_declaration_left":
            ident = first_child(head, "identifier")
            if ident is not None:
                name = _read_text(ident, source)
                line = line_of(head)
                nid = _make_id(stem, name)
                add_node(nid, name, line)
                add_edge(container_nid, nid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(name, nid)
                minted = nid
        else:  # value_declaration_left
            for name, line in bound_value_names(head):
                nid = _make_id(stem, name)
                add_node(nid, name, line)
                add_edge(container_nid, nid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(name, nid)
                minted = nid
        return minted

    def record_call(callee_node, caller: str) -> None:
        """Register a call site from a long_identifier_or_op or dot_expression
        callee node."""
        parts = identifiers_of(callee_node)
        if not parts:
            return
        callee = parts[-1]
        qualifier = parts[0] if len(parts) > 1 else None
        call_sites.append((caller, callee, qualifier,
                           ".".join(parts), line_of(callee_node)))

    def walk(node, container_nid: str, enclosing_value: str) -> None:
        t = node.type

        if t == "import_decl":  # open X.Y
            li = first_child(node, "long_identifier")
            if li is not None:
                parts = identifiers_of(li)
                if parts:
                    add_edge(container_nid, ref_stub(parts[-1]),
                             "imports_from", line_of(node), confidence="INFERRED")
            return

        if t == "namespace":
            name_node = first_child(node, "long_identifier", "identifier")
            parts = identifiers_of(name_node) if name_node is not None else []
            if parts:
                ns_label = ".".join(parts)
                line = line_of(node)
                # Canonical id shared with the C# path: every file declaring
                # this namespace emits the SAME node, which
                # _canonicalize_csharp_namespace_nodes then merges, and
                # _is_type_like_definition excludes from unique-stub rewire.
                ns_nid = _csharp_namespace_id(ns_label)
                add_node(ns_nid, ns_label, line, type="namespace",
                         metadata={"kind": "csharp_namespace"})
                add_edge(file_nid, ns_nid, "contains", line)
                for child in node.children:
                    walk(child, ns_nid, enclosing_value)
                return

        if t in ("named_module", "module_defn"):
            name_node = first_child(node, "long_identifier", "identifier")
            parts = identifiers_of(name_node) if name_node is not None else []
            if parts:
                mname = parts[-1]
                line = line_of(node)
                mnid = _make_id(stem, mname)
                add_node(mnid, mname, line)
                add_edge(container_nid, mnid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(mname, mnid)
                # Only the module actually DEFINED here may qualify a local
                # binding; leading path segments are shared namespace roots.
                local_containers.add(mname)
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
                emit_cases(defn, tnid, tname)
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
                    elif child.type not in ("type_name", "union_type_cases",
                                            "enum_type_cases"):
                        walk(child, tnid, enclosing_value)
            return

        if t == "exception_definition":
            li = first_child(node, "long_identifier", "identifier")
            parts = identifiers_of(li) if li is not None else []
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
            mnid = emit_member(node, container_nid,
                              node_labels.get(container_nid, ""))
            for child in node.children:
                walk(child, container_nid, mnid or enclosing_value)
            return

        if t == "function_or_value_defn":
            # `let rec f ... and g ...` packs EVERY and-joined head into this
            # one node, heads and bodies interleaved in source order. Walk the
            # children sequentially: each head (re)binds the attribution scope
            # for the body expressions that follow it, so g's calls attribute
            # to g, not f. Nested `let x = e` inside a value body keeps the
            # outer scope and mints nothing (mirrors ocaml.py's rule).
            current_scope = enclosing_value
            for child in node.children:
                if child.type in ("function_declaration_left",
                                  "value_declaration_left"):
                    if not enclosing_value:
                        minted = mint_binding_head(child, container_nid)
                        if minted:
                            current_scope = minted
                    continue  # argument patterns carry no call sites
                walk(child, container_nid, current_scope)
            return

        if t == "application_expression":
            fn = node.named_children[0] if node.named_children else None
            if fn is not None and fn.type in _CALLEE_TYPES:
                record_call(fn, enclosing_value or container_nid)
            # Fall through: arguments may contain further applications.

        if t == "infix_expression":
            op = first_child(node, "infix_op")
            operands = [c for c in node.named_children
                        if c.type != "infix_op" and c.type not in _COMMENT_TYPES]
            if op is not None and len(operands) == 2:
                op_text = _read_text(op, source)
                target = None
                if op_text in _PIPE_RIGHT and operands[1].type in _CALLEE_TYPES:
                    target = operands[1]
                elif op_text in _PIPE_LEFT and operands[0].type in _CALLEE_TYPES:
                    target = operands[0]
                if target is not None:
                    record_call(target, enclosing_value or container_nid)
            # Fall through: both operands need walking (nested pipes, args).

        for child in node.children:
            walk(child, container_nid, enclosing_value)

    walk(root, file_nid, "")

    for caller, callee, qualifier, full_path, line in call_sites:
        # Qualified call whose root is not defined here (`StringBuilder`
        # methods, `List.map`, namespace-rooted paths): keep it distinct so
        # the rewire can't bind it to a same-named local (ocaml.py's rule).
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
