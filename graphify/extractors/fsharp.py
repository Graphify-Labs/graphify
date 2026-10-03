"""F# extractor (own module, optional tree-sitter-fsharp dependency).

Handles implementation files (.fs) and scripts (.fsx) via ionide's
tree-sitter-fsharp ``language()`` grammar, which covers both. Signature files
(.fsi, ``language_signature()``) are deliberately not wired yet.

F# is ML-family, so this module follows graphify/extractors/ocaml.py for the
resolution discipline: sourceless ref stubs for cross-file targets (#1402), a
local-definition table with ambiguity tracking, and two-pass call resolution
so forward references (``let rec ... and ...`` — every ``and``-joined head is
minted) resolve.

Call resolution models F#'s lexical environment. Every scope (the file, a
namespace, a module, a type) records the names it declares and the ``open``s
it contains, in source order:

* A name is looked up from the innermost scope outward. Within a scope the
  LATEST visible declaration or preceding ``open`` wins, so a later ``open``
  shadows an earlier module and an inner ``open`` outranks an outer one. An
  ``open``'s target is itself resolved through the environment at the
  ``open`` (``open A`` then ``open Lib`` opens ``A.Lib``; an ``open`` never
  reaches a module declared after it).
* A declaration is visible only after it (F# is declaration-ordered), inside
  its own body only under ``let rec`` (types are recursive), and everywhere in
  a ``module rec``. Members are reached only through their type or receiver.
* Local bindings shadow: parameters (including those of return-annotated
  function and member heads, ``let f (g: int -> int) : int = ...``, and of
  property accessors), local ``let``/``use``, ``let!``/``and!`` groups (for
  their continuation), lambda, match, ``for`` and ``as`` binders, and member
  receivers. A call to a local binding is not recorded.
* An unqualified call binds EXTRACTED only to a visible definition of this
  file. A qualified call ``Q.f`` resolves ``Q``'s first segment the same way:
  a value there makes it a receiver call (``let Lib = C() ... Lib.Map``); a
  module or type there must own ``f`` along the rest of ``Q``; ``this.M``
  binds to the enclosing type's ``M`` when ``this`` is the member's receiver.
* When the answer is in another file, or an ``open`` of another file is
  nearer than any local match, the call gets a scoped stub: labelled with the
  name as written, carrying ``{"qualifier", "name", "scopes"}`` (scopes
  nearest first, part of the stub's id). With a local answer behind those
  ``open``s, only the ``open``s are listed and the stub is ``exhaustive``,
  with the local answer as its ``fallback`` ([container path, exact name]);
  a local VALUE there has no fallback: the call is a receiver call. An
  ``open type T`` among those opens also removes the fallback: whether T has
  a static member of that name is unknown, so the stub stays unbound. The corpus rewire binds it only to a
  unique definition, with that exact name, in the container the name
  reaches from the FIRST scope that has any, and never to a definition in the
  referring file (which already decided): ``Lib.map`` reaches module
  ``Lib``'s ``map``, ``List.map`` reaches nothing in the corpus, and an
  unqualified ``map`` only a ``map`` in a module the caller opens or is
  inside. A scope that supplies a qualifier's first segment as anything
  but an owning container (a value imported through an ``open``, say) ends
  the search. Definitions carry ``container_path`` metadata for that check.
* Receiver calls, and qualifiers that name a container of this file which
  does not own the name, get a metadata-free stub that never binds.
* Definition ids keep the exact spelling: ``run``/``Run``, ``f``/``f'`` and
  ````a-b````/``a_b`` are distinct nodes.
* Destructuring binds names, not constructors: ``let (Some v) = ...`` defines
  ``v``; list, record and ``as`` patterns bind their variables, not field
  labels.

Where tree-sitter-fsharp's tree disagrees with F# semantics, the call rules
correct for it:

* ``a :: f x`` (any infix operator but ``&&``/``||``) parses as
  ``(a :: f) x``; application binds tighter, so the call is to ``f``.
* ``xs[i]`` (F# 6 index syntax, no space) parses as an application of ``xs``
  to ``[i]``; it is an element read, not a call. ``f [i]`` (with a space)
  still is one.
* ``g &v 1`` parses ``&`` as a binary operator; it is address-of, and the
  call is to ``g``. ``g &&v`` (native address-of, no space before ``v``) is
  handled the same way; ``a && b`` stays boolean.
* ``f[1; 2]`` compiles as a call when ``f`` is a function, so an adjacent
  ``[`` resolves as a call only to a same-file ``let f x = ...`` function
  declaration (a function VALUE such as ``let f = List.sum`` is not
  recognised); ``f[|1; 2|]`` (an array) is an ordinary application.

tree-sitter-fsharp's parse of a return-annotated head is context-dependent:
the last binding in a file parses as a value head, others as function heads.
Both are treated as functions.

This is a lexical model, not the F# compiler's name resolution: it has no
type inference, and what another file declares is known only as graph nodes.
Known gaps:

* An ``open`` of another file is not resolved through earlier ``open``s
  across files (``open A`` then ``open Lib``, with ``A.Lib`` defined in
  another file, may bind to a root-level ``Lib`` elsewhere); within a file
  it is.
* Accessibility is not modelled: a ``private`` definition in an opened
  module of another file can be chosen over a public one further out.

Not handled:

* ``.fsi`` signature files.
* ``[<AutoOpen>]`` modules: unqualified calls into one bind only if the module
  is opened explicitly.
* A nullary union case used as a ``let`` pattern (``let (None) = ...``) is
  read as a binder.
* ``#r`` / ``#load`` script directives (no edges).
* Static members of C# classes (``Widget.Create()``): C# member labels
  (``.Name()``) are not rewire targets. A C# constructor call resolves only
  when its type is reached from the caller's scopes, and never a nested type.
"""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.engine import _csharp_namespace_id
from graphify.security import sanitize_metadata

# *_type_defn wrappers under type_definition, per the grammar. type_extension
# is handled by its own branch (it augments an existing type) and is therefore
# not in this set.
_TYPE_DEFN_KINDS = frozenset({
    "record_type_defn", "union_type_defn", "interface_type_defn",
    "enum_type_defn", "type_abbrev_defn",
    "type_declaration", "delegate_type_defn", "anon_type_defn",
})

# Pipe operators whose non-function operand is data, not a callee.
_PIPE_RIGHT = frozenset({"|>", "||>", "|||>"})   # callee on the right
_PIPE_LEFT = frozenset({"<|", "<||", "<|||"})    # callee on the left
# Composition: BOTH operands are callees (direction only swaps application
# order). Deliberately not generalized to custom operators — Kleisli (>=>)
# happens to compose functions but bind (>>=) has a data operand; there is no
# sound generic rule.
_COMPOSE = frozenset({">>", "<<"})
# Address-of: `g &v 1` passes a byref, but the grammar reads `&` as a binary
# operator, `(g & v) 1`. Binary `&` is obsolete F# (superseded by &&), so the
# callee is the LEFT operand.
_ADDRESS_OF = "&"

_COMMENT_TYPES = frozenset({"line_comment", "block_comment", "xml_doc"})

# Node types that can carry a callee name in an application/pipe position.
_CALLEE_TYPES = frozenset({"long_identifier_or_op", "dot_expression"})

# Nodes whose body a binding head scopes, for the lexical-shadowing check.
_BINDING_HEADS = frozenset({"function_declaration_left", "value_declaration_left"})
_MODULE_LEVEL = frozenset({"file", "named_module", "module_defn", "namespace"})


def _case_parts(name: str) -> tuple[str, ...]:
    """Id parts for a definition name. `_make_id` folds case and drops
    punctuation, but F# names are exact: `run`/`Run`, `f`/`f'` and
    ``a-b``/`a_b` are distinct definitions. A name that normalization would
    alter carries a tag of its exact spelling."""
    if re.fullmatch(r"[a-z0-9_]+", name):
        return (name,)
    return (name, "c" + hashlib.sha1(name.encode("utf-8")).hexdigest()[:8])


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

    # The lexical environment used for name resolution. Every scope (the file,
    # a namespace, a module, a type) lists the names it declares and the
    # `open`s it contains, with source positions; `lookup` walks it the way F#
    # does (see its docstring).
    env_defs: dict[str, list[tuple[str, str, int, int, int, bool]]] = {}
    env_opens: dict[str, list[tuple[int, str]]] = {}
    scope_parent: dict[str, str] = {}
    rec_scopes: set[str] = set()  # `module rec` / `namespace rec`
    # `open type T` (scope, path): it brings T's static members into scope,
    # which this file cannot enumerate for a type defined elsewhere.
    type_opens: set[tuple[str, str]] = set()
    # Modules and types defined here: container nid -> {member name -> nid};
    # full dotted path -> modules/types, and -> openable scopes.
    container_members: dict[str, dict[str, str]] = {}
    containers_at: dict[str, set[str]] = {}
    scopes_at: dict[str, set[str]] = {}
    path_of: dict[str, str] = {}  # scope nid -> full dotted path
    # (caller_nid, callee_name, qualifier_or_None, full_path_text, line,
    #  index_like, receiver_is_local, self_type_nid_or_None, scope_nid, position)
    call_sites: list[tuple[str, str, str | None, str, int, bool, bool, str | None,
                           str, int]] = []
    # member_defn span -> owning type nid, so `this.M` can resolve to the
    # enclosing type's own member M.
    member_owner: dict[tuple[int, int], str] = {}

    def add_node(nid: str, label: str, line: int, container: str | None = None,
                 **extra) -> None:
        node_labels.setdefault(nid, label)
        if nid not in seen_ids:
            seen_ids.add(nid)
            node = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_file": str_path,
                "source_location": f"L{line}",
                **extra,
            }
            if container is not None and path_of.get(container):
                # What the corpus rewire checks a qualified stub against: a
                # stub for `Lib.map` may bind only to a definition whose
                # container path is `Lib` as seen from one of the caller's
                # scopes (see _rewire_unique_stub_nodes).
                node.setdefault("metadata", {})["container_path"] = path_of[container]
            nodes.append(node)

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

    def ref_stub(name: str, qualifier: str | None = None, member: str | None = None,
                 scopes: list[str] | None = None, fallback: list[str] | None = None,
                 exhaustive: bool = False) -> str:
        """Sourceless stub for a cross-file target; the corpus rewire collapses
        it onto the unique real definition (#1402).

        A dotted `name` never matches a definition label, so on its own it
        fails closed. Passing `qualifier`, `member` and the caller's `scopes`
        makes it a qualified stub: the rewire may then bind it to a unique
        `member` definition whose container path is `qualifier` as seen from
        one of those scopes — `Lib.map` reaches module Lib's map, and
        `List.map` never reaches an unrelated `map`. The scopes are part of the
        stub's identity, so a stub never lends its binding permission to a
        same-spelled reference from another scope (or to a fail-closed one)."""
        if scopes is not None:
            # Per referring file too: the rewire never binds a scoped stub to
            # a definition in the file it came from (that file already decided).
            scope_tag = hashlib.sha1("\n".join(
                [str_path, *scopes, *(fallback or []), str(exhaustive)]).encode("utf-8")).hexdigest()[:8]
            nid = _make_id(*_case_parts(name), "q" + scope_tag)
        else:
            nid = _make_id(*_case_parts(name))
        if nid not in seen_ids:
            seen_ids.add(nid)
            stub: dict[str, object] = {
                "id": nid,
                "label": name,
                "file_type": "code",
                "source_file": "",
                "source_location": "",
                "origin_file": str_path,
            }
            if qualifier is not None and member is not None and scopes is not None:
                meta: dict[str, object] = {"qualifier": qualifier, "name": member,
                                           "scopes": list(scopes)}
                if exhaustive:
                    # A local binding answers behind the listed scopes: nothing
                    # further out may be tried, and `fallback` (if any) names
                    # that local answer by [container path, exact name] — ids are
                    # renormalized after extraction, meanings are not — used
                    # when no listed scope supplies the name.
                    meta["exhaustive"] = True
                    if fallback is not None:
                        meta["fallback"] = fallback
                stub["metadata"] = meta
            nodes.append(stub)
        return nid

    def line_of(node) -> int:
        return node.start_point[0] + 1

    def register_path(nid: str, parent_nid: str, dotted: str) -> str:
        parent = path_of.get(parent_nid, "")
        path_of[nid] = f"{parent}.{dotted}" if parent else dotted
        scope_parent[nid] = parent_nid
        return path_of[nid]

    def register_container(nid: str, parent_nid: str, dotted: str,
                           openable: bool = False) -> None:
        path = register_path(nid, parent_nid, dotted)
        containers_at.setdefault(path, set()).add(nid)
        if openable:
            scopes_at.setdefault(path, set()).add(nid)
        container_members.setdefault(nid, {})

    def register_member(container_nid: str, name: str, nid: str) -> None:
        if container_nid in container_members:
            container_members[container_nid].setdefault(name, nid)

    def declare(scope: str, name: str, nid: str, defn, is_rec: bool) -> None:
        """Record that `scope` declares `name` (as `nid`) at `defn`'s position.
        `is_rec` makes the name visible inside its own definition (`let rec`,
        and types, whose members may name the type)."""
        env_defs.setdefault(scope, []).append(
            (name, nid, defn.start_byte, defn.start_byte, defn.end_byte, is_rec))

    def visible(entry, scope: str, at: int) -> bool:
        """F# is declaration-ordered: a name is visible after its definition,
        inside it only when recursive, and everywhere in a `module rec`."""
        _, _, pos, start_b, end_b, is_rec = entry
        if scope in rec_scopes:
            return True
        if start_b <= at < end_b:
            return is_rec
        return pos < at

    module_nids: set[str] = set()  # openable modules of this file
    _open_cache: dict[tuple[str, str, int], str | None] = {}

    def open_target(path: str, scope: str, at: int) -> str | None:
        """The scope (of this file) that `open path`, written at byte `at` in
        `scope`, opens. Its first segment is resolved through the environment
        AT THE OPEN, so earlier opens count (`open A` then `open Lib` opens
        A.Lib) and later declarations do not; the rest is followed through
        that module's own path. A namespace is found by its full path. None
        when it opens something defined elsewhere."""
        key = (path, scope, at)
        if key in _open_cache:
            return _open_cache[key]
        _open_cache[key] = None  # guards against a pathological self-reference
        segs = path.split(".")
        target = None
        foreign, local = resolve(segs[0], scope, at)
        if not foreign and local is not None:
            for m in sorted(n for n in local if n in module_nids):
                hit = scopes_at.get(".".join([path_of[m], *segs[1:]]))
                if hit:
                    target = sorted(hit)[0]
                    break
        if target is None and not foreign:
            s: str | None = scope
            while s is not None and target is None:  # namespaces, relative then absolute
                base = path_of.get(s, "")
                hit = scopes_at.get(f"{base}.{path}" if base else path)
                if hit and not any(n in module_nids for n in hit):
                    target = sorted(hit)[0]
                s = scope_parent.get(s)
        _open_cache[key] = target
        return target

    def resolve(name: str, scope: str, at: int):
        """How F# would resolve `name` at byte `at` in `scope`, as far as this
        file can tell. Scopes are searched from the innermost outward; within
        a scope the LATEST visible declaration or preceding `open` wins (a
        later `open` shadows an earlier declaration and vice versa).

        Returns (foreign, local): `foreign` lists, nearest first, the
        (scope, path) of `open`s of other files that come BEFORE any local
        answer (each may or may not supply `name`); `local` is the nids this
        file declares under that name in the scope that answers, or None."""
        foreign: list[tuple[str, str]] = []
        s: str | None = scope
        while s is not None:
            # (position, open path) — the path is "" for a declaration
            entries: list[tuple[int, str]] = []
            for entry in env_defs.get(s, ()):
                if entry[0] == name and visible(entry, s, at):
                    entries.append((entry[2], ""))
            for opos, opath in env_opens.get(s, ()):
                if opos < at:
                    entries.append((opos, opath))
            for pos, opath in sorted(entries, key=lambda e: e[0], reverse=True):
                if not opath:
                    return foreign, [e[1] for e in env_defs[s]
                                     if e[0] == name and visible(e, s, at) and e[2] == pos]
                target = open_target(opath, s, pos)
                if target is None:
                    foreign.append((s, opath))
                    continue
                hits = [e[1] for e in env_defs.get(target, ()) if e[0] == name]
                if hits:
                    return foreign, hits
            s = scope_parent.get(s)
        return foreign, None

    def foreign_scopes(foreign: list[tuple[str, str]]) -> list[str]:
        """Prefixes for `open`s of other files, nearest first: each relative
        to the enclosing paths of the scope it appears in, then as written."""
        out: list[str] = []
        for s, opath in foreign:
            chain_s: str | None = s
            while chain_s is not None:
                if path_of.get(chain_s):
                    out.append(f"{path_of[chain_s]}.{opath}")
                chain_s = scope_parent.get(chain_s)
            out.append(opath)
        seen: set[str] = set()
        return [x for x in out if not (x in seen or seen.add(x))]

    def stub_scopes(scope: str, at: int, qualified: bool) -> list[str]:
        """The prefixes, nearest first, from which the corpus rewire may
        resolve a name this file could not: for each scope from the innermost
        outward, its preceding `open`s latest first (relative to each
        enclosing path, then as written), then the scope's own path; the
        parent namespaces of the outermost declaration; and for a qualified
        name the root ("")."""
        chain: list[str] = []
        s: str | None = scope
        while s is not None:
            chain.append(s)
            s = scope_parent.get(s)
        out: list[str] = []
        for i, s in enumerate(chain):
            for opos, opath in sorted(env_opens.get(s, ()), reverse=True):
                if opos < at:
                    out += [f"{path_of[a]}.{opath}" for a in chain[i:] if path_of.get(a)]
                    out.append(opath)
            if path_of.get(s):
                out.append(path_of[s])
        outer = [path_of[s] for s in chain if path_of.get(s)]
        if outer:
            segs = outer[-1].split(".")
            out += [".".join(segs[:k]) for k in range(len(segs) - 1, 0, -1)]
        if qualified:
            out.append("")
        seen: set[str] = set()
        return [x for x in out if not (x in seen or seen.add(x))]

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

    def pattern_binders(pat) -> list[tuple[str, int]]:
        """Names a pattern BINDS, with their lines. A constructor pattern
        (`Some v`, `Box (a, b)`: an identifier_pattern with more than one named
        child) names a union case in its first child and binds only inside
        its arguments; a record pattern's field labels are not binders; type
        annotations bind nothing. A lone name is a binder."""
        out: list[tuple[str, int]] = []

        def rec(p) -> None:
            t = p.type
            if t == "identifier_pattern":
                named = [c for c in p.named_children if c.type not in _COMMENT_TYPES]
                if len(named) == 1 and named[0].type == "long_identifier_or_op":
                    parts = identifiers_of(named[0])
                    if len(parts) == 1:  # a dotted name is a qualified case
                        out.append((parts[0], line_of(p)))
                    return
                # A constructor pattern: the case name (the first child, a
                # long_identifier_or_op) binds nothing; its arguments may.
                for c in named:
                    rec(c)
                return
            if t == "long_identifier":
                # A bare parameter (`let f x`) is a long_identifier directly
                # under argument_patterns; elsewhere it is a record field label
                # (`{ X = a }`) or part of a type, and binds nothing.
                if p.parent is not None and p.parent.type == "argument_patterns":
                    parts = identifiers_of(p)
                    if len(parts) == 1:
                        out.append((parts[0], line_of(p)))
                return
            if t == "identifier" and p.parent is not None and p.parent.type == "as_pattern":
                out.append((_read_text(p, source), line_of(p)))  # `pat as alias`
                return
            if t.endswith("_type") or t in ("const", "type_arguments"):
                return
            for c in p.named_children:
                rec(c)

        rec(pat)
        return out

    def type_ref_parts(node) -> list[str]:
        """Dotted name of a type REFERENCE (heritage clause, interface impl,
        object expression). `Base<'T>` wraps in generic_type whose subtree also
        holds the type parameters — read only the long_identifier child, the
        same rule type_name_parts applies to definitions."""
        if node is None:
            return []
        if node.type in ("generic_type", "simple_type", "long_identifier_or_op"):
            inner = first_child(node, "long_identifier", "identifier")
            if inner is not None:
                return identifiers_of(inner)
        return identifiers_of(node)

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
                cnid = _make_id(type_nid, *_case_parts(cname))
                add_node(cnid, cname, line_of(case), container=type_nid)
                add_edge(type_nid, cnid, "contains", line_of(case))
                # A case is usable unqualified wherever its type is visible.
                if type_nid in scope_parent:
                    declare(scope_parent[type_nid], cname, cnid, defn, True)
                register_member(type_nid, cname, cnid)

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
        member_owner[(member_defn.start_byte, member_defn.end_byte)] = type_nid
        mnid = _make_id(type_nid, "mem", *_case_parts(mname))
        add_node(mnid, f".{mname}()", line, container=type_nid)
        add_edge(type_nid, mnid, "contains", line)
        # Not declared in any scope: a member is reached only through its type
        # or receiver (`T.M`, `this.M`), never unqualified.
        register_member(type_nid, mname, mnid)
        return mnid

    def emit_heritage(defn, type_nid: str) -> None:
        """`inherit Base(...)` → inherits; `interface I with` → implements.
        INFERRED edges to sourceless stubs: the target is defined elsewhere,
        and the stub is what lets the corpus rewire (and its supertype guard)
        bind it to the real definition."""
        for decl in defn.children:
            if decl.type == "class_inherits_decl":
                st = first_child(decl, "simple_type", "generic_type",
                                 "long_identifier")
                parts = type_ref_parts(st)
                if parts:
                    add_edge(type_nid, ref_stub(parts[-1]), "inherits",
                             line_of(decl), confidence="INFERRED")

    def bound_value_names(head) -> list[tuple[str, int]]:
        """Names bound by a value_declaration_left, with their lines.

        - `let x = ...` / `let f (a: A) : T = ...`: an identifier_pattern
          directly under the head names the binding in its FIRST
          long_identifier_or_op (never the subtree's last identifier — that is
          a type annotation; the rest are parameters).
        - Anything else (`let (a, b)`, `let (Some v)`, `let [a; b]`,
          `let { X = a }`) is a destructuring pattern: its binders.
        """
        ip = first_child(head, "identifier_pattern")
        if ip is not None:
            lio = first_child(ip, "long_identifier_or_op")
            if lio is not None:
                parts = identifiers_of(lio)
                if parts:
                    return [(parts[-1], line_of(ip))]
            return []
        out: list[tuple[str, int]] = []
        for pat in head.named_children:
            out.extend(pattern_binders(pat))
        return out

    def head_params(head) -> list:
        """Parameter patterns of a binding head. `let f x = ...` keeps them in
        argument_patterns; a head with a return-type annotation
        (`let f (g: int -> int) : int = ...`) parses as a value head whose
        identifier_pattern holds the name first, then the parameters."""
        if head.type == "function_declaration_left":
            ap = first_child(head, "argument_patterns")
            return [ap] if ap is not None else []
        ip = first_child(head, "identifier_pattern")
        if ip is not None:
            named = [c for c in ip.named_children if c.type not in _COMMENT_TYPES]
            if len(named) > 1 and named[0].type == "long_identifier_or_op":
                return named[1:]
        return []

    def binding_names(defn) -> set[str]:
        """Names a local `let` (a function_or_value_defn) introduces."""
        names: set[str] = set()
        for head in defn.children:
            if head.type == "function_declaration_left":
                ident = first_child(head, "identifier")
                if ident is not None:
                    names.add(_read_text(ident, source))
            elif head.type == "value_declaration_left":
                names.update(n for n, _ in bound_value_names(head))
        return names

    def binder_of(node, name: str):
        """The nearest binding of `name` in scope at `node`, if it is LOCAL:
        the enclosing method_or_prop_defn node when that binding is the
        member's own receiver (`this` in `member this.X`), "local" for any
        other local binding (a parameter, a local `let`/`use`, a lambda or
        match binder, a `for` variable, member arguments, a primary-constructor
        argument), or None when no local binding intervenes. A call through a
        local binding targets a value, not a definition, so it must bind
        neither to a same-named definition here nor to one elsewhere."""
        def binds(pat) -> bool:
            return any(n == name for n, _ in pattern_binders(pat))

        child, p = node, node.parent
        while p is not None:
            t = p.type
            if t == "function_or_value_defn":
                head = None
                for c in p.children:
                    if c == child:
                        break
                    if c.type in _BINDING_HEADS:
                        head = c
                if head is not None and child.type not in _BINDING_HEADS:
                    if any(binds(pat) for pat in head_params(head)):
                        return "local"
                    # Only a nested `let rec` names itself inside its own
                    # right-hand side; `let f = f 42` calls the OUTER f.
                    if (any(c.type == "rec" for c in p.children)
                            and p.parent is not None and p.parent.type == "declaration_expression"
                            and p.parent.parent is not None
                            and p.parent.parent.type not in _MODULE_LEVEL
                            and name in binding_names(p)):
                        return "local"
            elif t == "declaration_expression":
                kids = [c for c in p.named_children if c.type not in _COMMENT_TYPES]
                if kids and kids[0].type == "function_or_value_defn":
                    # `let! x = a` `and! y = b`: the and_bang siblings belong to
                    # the group; its names scope the continuation, not the
                    # group's own initializers.
                    group = [k for k in kids[1:] if k.type == "and_bang"]
                    if child != kids[0] and child not in group:
                        names = binding_names(kids[0])
                        for g in group:
                            pats = [c for c in g.named_children if c.type not in _COMMENT_TYPES][:1]
                            names |= {n for pat in pats for n, _ in pattern_binders(pat)}
                        if name in names:
                            return "local"
                elif (len(kids) >= 3 and kids[0].type == "identifier"
                      and child not in kids[:2]
                      and _read_text(kids[0], source) == name):  # `use f = e` body
                    return "local"
            elif t == "property_accessor":  # `with set (value) = ...`
                ap = first_child(p, "argument_patterns")
                if ap is not None and child != ap and binds(ap):
                    return "local"
            elif t == "fun_expression":
                ap = first_child(p, "argument_patterns")
                if ap is not None and child != ap and binds(ap):
                    return "local"
            elif t == "rule":
                kids = p.named_children
                if kids and child != kids[0] and binds(kids[0]):
                    return "local"
            elif t == "for_expression":
                kids = p.named_children
                if len(kids) >= 3 and child not in kids[:2] and binds(kids[0]):
                    return "local"
            elif t == "method_or_prop_defn":
                poi = first_child(p, "property_or_ident")
                if poi is not None and child != poi:
                    for c in p.named_children:
                        # `member _.H (f: T) : R = ...` wraps the parameters in a
                        # typed_pattern with the return type; pattern_binders
                        # skips the type.
                        if c.type in ("identifier_pattern", "paren_pattern", "argument_patterns",
                                      "typed_pattern") \
                                and c != child and binds(c):
                            return "local"
                    receiver = identifiers_of(poi)
                    if len(receiver) > 1 and receiver[0] == name:
                        return p
            elif t == "anon_type_defn":
                args = first_child(p, "primary_constr_args")
                if args is not None and binds(args):
                    return "local"
            child, p = p, p.parent
        return None

    def locally_bound(node, name: str) -> bool:
        return binder_of(node, name) is not None

    def is_rec(defn) -> bool:
        return any(c.type == "rec" for c in defn.children)

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
                nid = _make_id(container_nid, *_case_parts(name))
                add_node(nid, f"{name}()", line, container=container_nid)
                add_edge(container_nid, nid,
                         "defines" if container_nid == file_nid else "contains", line)
                declare(container_nid, name, nid, head.parent, is_rec(head.parent))
                register_member(container_nid, name, nid)
                return nid
            # Active pattern `(|Even|Odd|)`: mint one node labelled with the
            # full delimited spelling; each case name resolves to it.
            ap = first_child(head, "active_pattern")
            if ap is not None:
                case_names = [_read_text(c, source) for c in ap.children
                              if c.type == "active_pattern_op_name"]
                if case_names:
                    label = _read_text(ap, source)  # keeps `|_|` in partials
                    line = line_of(head)
                    nid = _make_id(container_nid, "ap", *case_names)
                    add_node(nid, label, line, container=container_nid)
                    add_edge(container_nid, nid,
                             "defines" if container_nid == file_nid else "contains",
                             line)
                    for cn in case_names:
                        declare(container_nid, cn, nid, head.parent, is_rec(head.parent))
                    return nid
            # Operator `(+.)`: label is the delimited spelling (ends in `)`,
            # so it is excluded from the type-like rewire by construction).
            op = first_child(head, "op_identifier")
            if op is not None:
                op_text = _read_text(op, source)
                line = line_of(head)
                nid = _make_id(container_nid, "op", op_text)
                add_node(nid, op_text, line, container=container_nid)
                add_edge(container_nid, nid,
                         "defines" if container_nid == file_nid else "contains", line)
                # no register_def: nothing resolves calls by operator spelling
                # (non-pipe operator invocations are deliberately unrecorded)
                return nid
            return None
        # value_declaration_left. With parameters (a return-annotated function
        # head, `let f (x: int) : int = ...`) it is a function: `name()`.
        is_function_head = bool(head_params(head))
        for name, line in bound_value_names(head):
            nid = _make_id(container_nid, *_case_parts(name))
            add_node(nid, f"{name}()" if is_function_head else name, line,
                     container=container_nid)
            add_edge(container_nid, nid,
                     "defines" if container_nid == file_nid else "contains", line)
            declare(container_nid, name, nid, head.parent, is_rec(head.parent))
            register_member(container_nid, name, nid)
            minted = nid
        return minted

    # Infix nodes (by span) whose right operand the grammar attached to an
    # index read: `x |> fs[0]` parses as `(x |> fs)[0]`.
    indexed_infixes: set[tuple[int, int]] = set()

    def infix_operator_and_operands(node):
        """(operator text, operator node, [left, right]) of an infix_expression,
        comments filtered; (None, None, []) when it is not a binary infix."""
        op = first_child(node, "infix_op")
        operands = [c for c in node.named_children
                    if c.type != "infix_op" and c.type not in _COMMENT_TYPES]
        if op is None or len(operands) != 2:
            return None, None, []
        return _read_text(op, source), op, operands

    def is_address_of(op_text, op, operands) -> bool:
        """`g &v` and `g &&v` pass an address; the grammar reads both `&` and
        `&&` as binary operators. Binary `&` is obsolete F#, so `&` is always
        address-of; `&&` is address-of (of a native pointer) only when it
        touches its right operand and not its left (`g &&v`, not `a && b`)."""
        if op_text == _ADDRESS_OF:
            return True
        return (op_text == "&&" and operands[1].start_byte == op.end_byte
                and op.start_byte > operands[0].end_byte)

    def infix_applied_operand(node):
        """For an application whose head the grammar parsed as an infix
        expression, the operand that is really being applied: the right one.
        Operator chains nest to the LEFT (`a + b * f x` is `((a + b) * f) x`),
        so the right operand is never itself an infix. None when the
        pipe-right, composition or address-of rule already records the
        callee, so one call site never yields two edges."""
        op_text, op, operands = infix_operator_and_operands(node)
        if (op_text is None or op_text in _PIPE_RIGHT or op_text in _COMPOSE
                or is_address_of(op_text, op, operands)):
            return None
        return operands[1]

    def record_call(callee_node, caller: str, scope: str, index_like: bool = False) -> None:
        """Record a call site. `index_like` marks `name[...]`, which the
        grammar cannot tell from application to a list; it resolves only to a
        local FUNCTION (see the resolution loop)."""
        parts = identifiers_of(callee_node)
        if not parts:
            return
        callee = parts[-1]
        if len(parts) == 1:
            if locally_bound(callee_node, callee):
                return  # a parameter or local binding: not a definition
            call_sites.append((caller, callee, None, callee, line_of(callee_node),
                               index_like, False, None, scope, callee_node.start_byte))
            return
        # `x.Method` on a local value is a receiver call, not module access;
        # `this.M` through the member's own receiver is the enclosing type's M.
        binder = binder_of(callee_node, parts[0])
        self_nid = None
        if binder is not None and binder != "local" and len(parts) == 2 \
                and binder.parent is not None:
            self_nid = member_owner.get((binder.parent.start_byte, binder.parent.end_byte))
        call_sites.append((caller, callee, ".".join(parts[:-1]), ".".join(parts),
                           line_of(callee_node), index_like, binder is not None,
                           self_nid, scope, callee_node.start_byte))

    def walk(node, container_nid: str, enclosing_value: str) -> None:
        t = node.type

        if t == "import_decl":  # open X.Y — mirror C#'s `using`:
            # an EXTRACTED `imports` edge from the FILE node to the full-FQN
            # id, no minted node. A last-segment stub would let `open
            # System.Text` rewire onto any unrelated class named `Text`.
            li = first_child(node, "long_identifier")
            if li is not None:
                parts = identifiers_of(li)
                if parts:
                    fqn = ".".join(parts)
                    env_opens.setdefault(container_nid, []).append((node.start_byte, fqn))
                    if any(c.type == "type" for c in node.children):
                        type_opens.add((container_nid, fqn))
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
                register_path(ns_nid, file_nid, ns_label)
                scopes_at.setdefault(ns_label, set()).add(ns_nid)
                if is_rec(node):
                    rec_scopes.add(ns_nid)
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
                mnid = _make_id(container_nid, "m", *_case_parts(mname))
                add_node(mnid, mname, line, container=container_nid)
                add_edge(container_nid, mnid,
                         "defines" if container_nid == file_nid else "contains", line)
                declare(container_nid, mname, mnid, node, False)
                register_container(mnid, container_nid, ".".join(parts), openable=True)
                module_nids.add(mnid)
                if is_rec(node):
                    rec_scopes.add(mnid)
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
                tnid = _make_id(container_nid, "t", *_case_parts(tname))
                add_node(tnid, tname, line, container=container_nid)
                add_edge(container_nid, tnid,
                         "defines" if container_nid == file_nid else "contains", line)
                declare(container_nid, tname, tnid, node, True)
                register_container(tnid, container_nid, tname)
                emit_cases(defn, tnid)
                emit_heritage(defn, tnid)
                for child in defn.children:
                    if child.type == "type_extension_elements":
                        for el in child.children:
                            if el.type == "member_defn":
                                vd = first_child(el, "value_declaration")
                                if vd is not None:
                                    # `static let build x = ...`: a binding in
                                    # member clothing; mint it under the type
                                    # (empty scope lets mint_binding_head run).
                                    for sub in vd.children:
                                        walk(sub, tnid, "")
                                    continue
                                mnid = emit_member(el, tnid)
                                for sub in el.children:
                                    walk(sub, tnid, mnid or tnid)
                            elif el.type == "interface_implementation":
                                st = first_child(el, "simple_type", "generic_type",
                                                 "long_identifier")
                                iparts = type_ref_parts(st)
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
                    elif child.type == "class_inherits_decl":
                        # heritage edge came from emit_heritage; the ctor
                        # arguments still carry calls (`inherit Base(mkArg ())`)
                        for sub in child.children:
                            if sub.type not in ("simple_type", "generic_type",
                                                "long_identifier"):
                                walk(sub, tnid, enclosing_value)
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
                enid = _make_id(container_nid, "e", *_case_parts(ename))
                add_node(enid, ename, line, container=container_nid)
                add_edge(container_nid, enid,
                         "defines" if container_nid == file_nid else "contains", line)
                declare(container_nid, ename, enid, node, False)
            return

        if t == "object_expression":
            # `{ new IFoo with member ... }` is ANONYMOUS: minting its members
            # as container members fabricates ownership, merges same-named
            # implementations, and poisons local_defs (a later real `Go`
            # binding turns ambiguous). Attribute member-body calls to the
            # enclosing binding; reference the interface as a stub.
            st = first_child(node, "long_identifier_or_op", "generic_type",
                             "simple_type", "long_identifier")
            iparts = type_ref_parts(st)
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
            vd = first_child(node, "value_declaration")
            if vd is not None:
                for sub in vd.children:
                    walk(sub, container_nid, "")
                return
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
            arg = node.named_children[1] if len(node.named_children) > 1 else None
            # F# 6 index syntax: `xs[i]` (no space) reads an element, while
            # `f [i]` applies f to a list; the grammar parses both as
            # application. An adjacent `[` (but not an array `[|`) makes the
            # site index-like: it stays a call only if the name is a local
            # function (`f[1; 2]` compiles as a call to f).
            index_like = (fn is not None and arg is not None
                          and arg.start_byte == fn.end_byte
                          and source[arg.start_byte:arg.start_byte + 1] == b"["
                          and source[arg.start_byte:arg.start_byte + 2] != b"[|")
            if fn is not None and fn.type == "infix_expression":
                if index_like:
                    indexed_infixes.add((fn.start_byte, fn.end_byte))
                # tree-sitter-fsharp parses `a :: f x` (and `+`, `=`, `@`, ...
                # — every infix operator but && and ||) as `(a :: f) x`,
                # although application binds tighter than any infix operator.
                # The function actually applied is the infix's rightmost
                # operand; without this, `head :: loop rest` loses its call.
                fn = infix_applied_operand(fn)
            if fn is not None and fn.type in _CALLEE_TYPES:
                record_call(fn, enclosing_value or container_nid, container_nid, index_like)
            # Fall through: arguments may contain further applications.

        if t == "infix_expression":
            op_text, op, operands = infix_operator_and_operands(node)
            if op_text is not None:
                caller = enclosing_value or container_nid
                right_indexed = (node.start_byte, node.end_byte) in indexed_infixes
                if op_text in _PIPE_RIGHT and operands[1].type in _CALLEE_TYPES:
                    record_call(operands[1], caller, container_nid, right_indexed)
                elif op_text in _PIPE_LEFT and operands[0].type in _CALLEE_TYPES:
                    record_call(operands[0], caller, container_nid)
                elif is_address_of(op_text, op, operands):
                    # `g &v`: g is called. In `1 + g &v` the grammar puts the
                    # function inside the left operand: `(1 + g) & v`.
                    left = operands[0]
                    if left.type == "infix_expression":
                        left = infix_applied_operand(left)
                    if left is not None and left.type in _CALLEE_TYPES:
                        record_call(left, caller, container_nid)
                elif op_text in _COMPOSE:
                    if operands[0].type in _CALLEE_TYPES:
                        record_call(operands[0], caller, container_nid)
                    if operands[1].type in _CALLEE_TYPES:
                        record_call(operands[1], caller, container_nid, right_indexed)
            # Fall through: both operands need walking (nested pipes, args).

        for child in node.children:
            walk(child, container_nid, enclosing_value)

    walk(root, file_nid, "")

    def is_function(nid: str) -> bool:
        return node_labels.get(nid, "").endswith("()")

    node_by_id = {n["id"]: n for n in nodes}

    def safe_fallback(foreign: list[tuple[str, str]], nid: str | None) -> list[str] | None:
        """The local fallback for a stub, unless an `open type` is among the
        nearer foreign opens: whether that type has a static member of this
        name is unknown, so restoring the shadowed local answer could be
        wrong. The stub then stays unbound instead."""
        if any(f in type_opens for f in foreign):
            return None
        return fallback_ref(nid)

    def fallback_ref(nid: str | None) -> list[str] | None:
        """[container path, exact name] of a local definition, for a stub's
        fallback; None when it has no container path to name it by."""
        node = node_by_id.get(nid) if nid else None
        meta = (node or {}).get("metadata") or {}
        path = meta.get("container_path")
        if not node or not path:
            return None
        label = node["label"][:-2] if node["label"].endswith("()") else node["label"]
        return [path, label[1:] if label.startswith(".") else label]

    def emit_call(caller: str, target: str, line: int, index_like: bool) -> None:
        if not index_like or is_function(target):
            add_edge(caller, target, "calls", line)

    def emit_scoped_stub(caller, label, qualifier, callee, scope, at, line) -> None:
        add_edge(caller, ref_stub(label, qualifier, callee,
                                  stub_scopes(scope, at, qualified=bool(qualifier))),
                 "calls", line, confidence="INFERRED")

    for (caller, callee, qualifier, full_path, line, index_like, receiver_local,
         self_nid, scope, at) in call_sites:
        if self_nid is not None and callee in container_members.get(self_nid, {}):
            emit_call(caller, container_members[self_nid][callee], line, index_like)
            continue
        if receiver_local:
            # A method on a local value: its target is unknown and must never
            # be rewired onto a same-named module function elsewhere.
            if not index_like:
                add_edge(caller, ref_stub(full_path), "calls", line, confidence="INFERRED")
            continue
        foreign, local = resolve(callee if qualifier is None else full_path.split(".")[0], scope, at)
        if qualifier is None:
            if not foreign and local is not None:
                emit_call(caller, local[-1], line, index_like)
            elif not index_like:
                # Possibly supplied by an `open` of another file: a scoped stub.
                # With a local answer behind those opens, only the opens are
                # listed and the local answer is the fallback.
                if local is not None:
                    add_edge(caller, ref_stub(callee, "", callee, foreign_scopes(foreign),
                                              fallback=safe_fallback(foreign, local[-1]),
                                              exhaustive=True),
                             "calls", line, confidence="INFERRED")
                else:
                    emit_scoped_stub(caller, callee, "", callee, scope, at, line)
            continue
        if local is None:
            if not index_like:
                emit_scoped_stub(caller, full_path, qualifier, callee, scope, at, line)
            continue
        heads = [n for n in local if n in container_members]
        rest = qualifier.split(".")[1:]
        owners = sorted({
            n for h in heads
            for n in containers_at.get(".".join([path_of[h], *rest]), set())
            if callee in container_members.get(n, {})})
        target = container_members[owners[0]][callee] if len(owners) == 1 else None
        if foreign:
            # An `open` of another file is nearer than the local answer: list
            # only those opens; the local answer is the fallback when none of
            # them supplies the qualifier (a VALUE answer has no fallback —
            # it is a receiver call, never a module function).
            if not index_like:
                add_edge(caller, ref_stub(full_path, qualifier, callee, foreign_scopes(foreign),
                                          fallback=safe_fallback(foreign, target), exhaustive=True),
                         "calls", line, confidence="INFERRED")
            continue
        if not heads:
            # The first segment is a VALUE (`let Lib = C()`): a receiver call.
            if not index_like:
                add_edge(caller, ref_stub(full_path), "calls", line, confidence="INFERRED")
            continue
        if target is not None:
            emit_call(caller, target, line, index_like)
        elif not index_like:
            # A container of this file that does not own the name, or two that
            # do: nothing anywhere can be the target, so the stub fails closed.
            add_edge(caller, ref_stub(full_path), "calls", line, confidence="INFERRED")

    return {"nodes": nodes, "edges": edges}
