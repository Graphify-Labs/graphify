"""F# extractor (own module, optional tree-sitter-fsharp dependency).

Handles implementation files (.fs) and scripts (.fsx) via ionide's
tree-sitter-fsharp ``language()`` grammar, which covers both. Signature files
(.fsi, ``language_signature()``) are deliberately not wired yet.

F# is ML-family, so this module follows graphify/extractors/ocaml.py for the
resolution discipline: sourceless ref stubs for cross-file targets (#1402), a
local-definition table with ambiguity tracking, and two-pass call resolution
so forward references (``let rec ... and ...`` — every ``and``-joined head is
minted) resolve.

.NET-family conventions (so F# joins the same corpus passes as C#):

* **Namespaces are canonical** (``csharp_namespace:<sha1>`` via
  engine._csharp_namespace_id, ``type: "namespace"``): N files declaring one
  namespace merge into one hub, and namespace segments never qualify local
  call binding — the corpus shares them.
* **Ids chain from the container** (C#'s ``_make_id(parent_nid, name)``
  pattern) with a kind tag where kinds can collide: the companion-module idiom
  (``type Config`` + ``module Config``) yields two nodes, sibling modules'
  same-named ``run`` bindings stay distinct, and a member's id hangs off its
  owning type.
* **Labels follow the family's shape conventions**: members ``.Name()``,
  let-bound functions ``name()`` (both excluded from the unique-stub
  type-rewire by `_is_type_like_definition`'s ``)``/leading-``.`` rules —
  ``_node_label_key`` strips punctuation, so cross-file matching still works);
  plain values stay bare.
* **`open` mirrors `using`**: an ``imports`` edge from the FILE node to
  ``_make_id(full_fqn)`` with ``target_fqn`` metadata, EXTRACTED, no minted
  node — not a last-segment stub that could rewire onto an unrelated class.
* **Heritage is emitted**: ``inherit Base()`` → INFERRED ``inherits`` and
  ``interface I with`` → INFERRED ``implements`` edges to sourceless stubs,
  so the supertype guard in the corpus rewire can protect F# base types.

F#-specific handling, grounded in live AST probes of the grammar:

* A generic ``type_name`` carries ``type_arguments`` siblings — the type's
  own name is the ``long_identifier``/``identifier`` child only, never the
  subtree's last identifier (that is the last type parameter, or a constraint
  type such as ``IDisposable``).
* ``type X with`` (type_extension) AUGMENTS a possibly-foreign type: members
  attach to a sourceless stub of X, and no sourced type node is minted — a
  sourced one would let an extension file impersonate the BCL type it extends.
* Object expressions (``{ new IFoo with ... }``) are anonymous: their member
  bodies' calls attribute to the enclosing binding, no member node is minted,
  and an INFERRED ``references`` edge points at the interface stub.
* Active patterns (``let (|Even|Odd|) n``) and operator definitions
  (``let (+.) a b``) mint nodes labelled with their delimited spelling; their
  bodies attribute to them, not to the enclosing module.
* ``member val`` auto-properties put ``property_or_ident`` directly under
  ``member_defn`` (no ``method_or_prop_defn`` wrapper) and are still emitted.
* Callees may be dotted (``dot_expression``); pipes (``|>``/``<|`` families)
  carry callees on the operand side, with comment nodes filtered before
  operand counting; enum members live under ``enum_type_cases``.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.engine import _csharp_namespace_id
from graphify.security import sanitize_metadata

# *_type_defn wrappers under type_definition, per the grammar. type_extension
# is deliberately NOT here: it augments an existing type (see emit path below).
_TYPE_DEFN_KINDS = frozenset({
    "record_type_defn", "union_type_defn", "interface_type_defn",
    "enum_type_defn", "type_abbrev_defn",
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
    functions/values, operators, active patterns, ``open`` imports, heritage
    (inherits/implements), and calls (application + pipeline) from an F# file."""
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
    # and types DEFINED here. Never namespace segments (corpus-shared).
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
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 metadata: dict | None = None) -> None:
        edge = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": confidence,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": weight,
        }
        if metadata:
            edge["metadata"] = sanitize_metadata(metadata)
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def ref_stub(name: str) -> str:
        """Sourceless stub for a cross-file target; the corpus rewire collapses
        it onto the unique real definition (#1402)."""
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
        order. Works for long_identifier_or_op and dot_expression alike."""
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

    def type_name_parts(defn) -> tuple[list[str], int]:
        """The type's OWN dotted name. A generic `type_name` carries
        `type_arguments` (and `when` constraints) as siblings of the name —
        taking the subtree's last identifier yields the last type parameter,
        or a constraint type like IDisposable. Read only the name child."""
        tn = first_child(defn, "type_name")
        if tn is None:
            return [], line_of(defn)
        name_node = first_child(tn, "long_identifier", "identifier")
        if name_node is None:
            return [], line_of(tn)
        return identifiers_of(name_node), line_of(tn)

    def emit_cases(defn, type_nid: str) -> None:
        """DU cases (union_type_cases) and enum members (enum_type_cases),
        id-scoped under their owning type."""
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
                cnid = _make_id(type_nid, cname)
                add_node(cnid, cname, line_of(case))
                add_edge(type_nid, cnid, "contains", line_of(case))
                register_def(cname, cnid)

    def emit_member(member_defn, type_nid: str) -> str | None:
        """member this.Run() / static member Default / member val Name.
        Id hangs off the OWNING TYPE's node id (C#'s convention); label uses
        the dotnet `.Name()` shape so the rewire treats it as a method."""
        mp = first_child(member_defn, "method_or_prop_defn", "member_signature")
        # `member val Name = ...` puts property_or_ident directly under
        # member_defn, with no method_or_prop_defn wrapper.
        poi = (first_child(mp, "property_or_ident", "identifier") if mp is not None
               else first_child(member_defn, "property_or_ident"))
        if poi is None:
            return None
        parts = identifiers_of(poi)
        if not parts:
            return None
        mname = parts[-1]
        line = line_of(member_defn)
        mnid = _make_id(type_nid, mname)
        add_node(mnid, f".{mname}()", line)
        add_edge(type_nid, mnid, "contains", line)
        register_def(mname, mnid)
        return mnid

    def emit_heritage(defn, type_nid: str) -> None:
        """`inherit Base(...)` → inherits; `interface I with` → implements.
        INFERRED edges to sourceless stubs: the target is defined elsewhere,
        and the stub is what lets the corpus rewire (and its supertype guard)
        bind it to the real definition."""
        for decl in defn.children:
            if decl.type == "class_inherits_decl":
                st = first_child(decl, "simple_type", "long_identifier")
                parts = identifiers_of(st) if st is not None else []
                if parts:
                    add_edge(type_nid, ref_stub(parts[-1]), "inherits",
                             line_of(decl), confidence="INFERRED")

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
        attribute the following body's calls to.

        Ids chain from the container (same-named `run` in two sibling modules
        stays two nodes). Functions get `name()` labels — engine languages do
        the same (function_label_parens), and `_is_type_like_definition`
        excludes `)`-labelled nodes from the unique-stub TYPE rewire, so a
        Python `parse()` reference can't bind onto an F# `parse` function.
        Plain values stay bare-labelled."""
        minted: str | None = None
        if head.type == "function_declaration_left":
            ident = first_child(head, "identifier")
            if ident is not None:
                name = _read_text(ident, source)
                line = line_of(head)
                nid = _make_id(container_nid, name)
                add_node(nid, f"{name}()", line)
                add_edge(container_nid, nid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(name, nid)
                return nid
            # Active pattern `(|Even|Odd|)`: mint one node labelled with the
            # full delimited spelling; each case name resolves to it.
            ap = first_child(head, "active_pattern")
            if ap is not None:
                case_names = [_read_text(c, source) for c in ap.children
                              if c.type == "active_pattern_op_name"]
                if case_names:
                    label = "(|" + "|".join(case_names) + "|)"
                    line = line_of(head)
                    nid = _make_id(container_nid, "ap", *case_names)
                    add_node(nid, label, line)
                    add_edge(container_nid, nid,
                             "defines" if container_nid == file_nid else "contains",
                             line)
                    for cn in case_names:
                        register_def(cn, nid)
                    return nid
            # Operator `(+.)`: label is the delimited spelling (ends in `)`,
            # so it is excluded from the type-like rewire by construction).
            op = first_child(head, "op_identifier")
            if op is not None:
                op_text = _read_text(op, source)
                line = line_of(head)
                nid = _make_id(container_nid, "op", op_text)
                add_node(nid, op_text, line)
                add_edge(container_nid, nid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(op_text.strip("()"), nid)
                return nid
            return None
        # value_declaration_left
        for name, line in bound_value_names(head):
            nid = _make_id(container_nid, name)
            add_node(nid, name, line)
            add_edge(container_nid, nid,
                     "defines" if container_nid == file_nid else "contains", line)
            register_def(name, nid)
            minted = nid
        return minted

    def record_call(callee_node, caller: str) -> None:
        parts = identifiers_of(callee_node)
        if not parts:
            return
        callee = parts[-1]
        qualifier = parts[0] if len(parts) > 1 else None
        call_sites.append((caller, callee, qualifier,
                           ".".join(parts), line_of(callee_node)))

    def walk(node, container_nid: str, enclosing_value: str) -> None:
        t = node.type

        if t == "import_decl":  # open X.Y — mirror C#'s `using` (#3221 r3):
            # an EXTRACTED `imports` edge from the FILE node to the full-FQN
            # id, no minted node. A last-segment stub would let `open
            # System.Text` rewire onto any unrelated class named `Text`.
            li = first_child(node, "long_identifier")
            if li is not None:
                parts = identifiers_of(li)
                if parts:
                    fqn = ".".join(parts)
                    add_edge(file_nid, _make_id(fqn), "imports", line_of(node),
                             metadata={"using_kind": "namespace",
                                       "target_fqn": fqn,
                                       "scope_kind": "file"})
            return

        if t == "namespace":
            name_node = first_child(node, "long_identifier", "identifier")
            parts = identifiers_of(name_node) if name_node is not None else []
            if parts:
                ns_label = ".".join(parts)
                line = line_of(node)
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
                mnid = _make_id(container_nid, "m", mname)
                add_node(mnid, mname, line)
                add_edge(container_nid, mnid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(mname, mnid)
                local_containers.add(mname)
                for child in node.children:
                    walk(child, mnid, enclosing_value)
                return

        if t == "type_definition":
            for defn in node.children:
                if defn.type == "type_extension":
                    # `type X with ...` AUGMENTS an existing (often foreign)
                    # type. Minting a sourced X here would let this file
                    # impersonate the real definition in the unique-stub
                    # rewire (verified: a C# `class Foo : Widget` rewired its
                    # inherits edge onto an extension file). Members attach to
                    # a sourceless stub instead.
                    parts, line = type_name_parts(defn)
                    if not parts:
                        continue
                    owner = ref_stub(parts[-1])
                    for child in defn.children:
                        if child.type == "type_extension_elements":
                            for el in child.children:
                                if el.type == "member_defn":
                                    mnid = emit_member(el, owner)
                                    for sub in el.children:
                                        walk(sub, container_nid, mnid or enclosing_value)
                                else:
                                    walk(el, container_nid, enclosing_value)
                    continue
                if defn.type not in _TYPE_DEFN_KINDS:
                    continue
                parts, line = type_name_parts(defn)
                if not parts:
                    continue
                tname = parts[-1]
                tnid = _make_id(container_nid, "t", tname)
                add_node(tnid, tname, line)
                add_edge(container_nid, tnid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(tname, tnid)
                local_containers.add(tname)
                emit_cases(defn, tnid)
                emit_heritage(defn, tnid)
                for child in defn.children:
                    if child.type == "type_extension_elements":
                        for el in child.children:
                            if el.type == "member_defn":
                                mnid = emit_member(el, tnid)
                                for sub in el.children:
                                    walk(sub, tnid, mnid or tnid)
                            elif el.type == "interface_implementation":
                                st = first_child(el, "simple_type", "long_identifier")
                                iparts = identifiers_of(st) if st is not None else []
                                if iparts:
                                    add_edge(tnid, ref_stub(iparts[-1]),
                                             "implements", line_of(el),
                                             confidence="INFERRED")
                                for imember in el.children:
                                    if imember.type == "member_defn":
                                        mnid = emit_member(imember, tnid)
                                        for sub in imember.children:
                                            walk(sub, tnid, mnid or tnid)
                            else:
                                walk(el, tnid, enclosing_value)
                    elif child.type not in ("type_name", "union_type_cases",
                                            "enum_type_cases",
                                            "class_inherits_decl"):
                        walk(child, tnid, enclosing_value)
            return

        if t == "exception_definition":
            li = first_child(node, "long_identifier", "identifier")
            parts = identifiers_of(li) if li is not None else []
            if parts:
                ename = parts[-1]
                line = line_of(node)
                enid = _make_id(container_nid, "e", ename)
                add_node(enid, ename, line)
                add_edge(container_nid, enid,
                         "defines" if container_nid == file_nid else "contains", line)
                register_def(ename, enid)
            return

        if t == "object_expression":
            # `{ new IFoo with member ... }` is ANONYMOUS: minting its members
            # as container members fabricates ownership, merges same-named
            # implementations, and poisons local_defs (a later real `Go`
            # binding turns ambiguous). Attribute member-body calls to the
            # enclosing binding; reference the interface as a stub.
            st = first_child(node, "simple_type", "long_identifier")
            iparts = identifiers_of(st) if st is not None else []
            if iparts:
                add_edge(enclosing_value or container_nid, ref_stub(iparts[-1]),
                         "references", line_of(node), confidence="INFERRED")
            for child in node.children:
                if child.type == "member_defn":
                    for sub in child.children:
                        walk(sub, container_nid, enclosing_value)
                else:
                    walk(child, container_nid, enclosing_value)
            return

        if t == "member_defn":
            # A member outside type_extension_elements (type augmentation).
            mnid = emit_member(node, container_nid)
            for child in node.children:
                walk(child, container_nid, mnid or enclosing_value)
            return

        if t == "function_or_value_defn":
            # `let rec f ... and g ...` packs EVERY and-joined head into this
            # one node, heads and bodies interleaved in source order: each
            # head (re)binds the attribution scope for the body that follows.
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
