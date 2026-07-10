"""Perl extractor: packages, subs, imports (use/require), inheritance (@ISA/parent/base).

Deliberately untyped, consistent with the other language extractors. Calls are
handed to the shared cross-file second pass as ``raw_calls`` (INFERRED by
name-matching); method calls (``$obj->meth()``) are marked ``is_member_call`` so
that pass drops them — without receiver types they are unresolvable and naive
name-matching would wire spurious edges to same-named subs.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id

_LOG = logging.getLogger(__name__)

# A valid Perl package/class name: a bareword component (`Foo`, `_priv`) optionally
# joined by `::`. Inheritance targets come from arbitrary string_literal / qw()
# content (`@ISA`, `use parent`, `use base`), so a crafted or malformed string
# (control chars, markdown, newlines, an over-long blob) could otherwise flow raw
# into a node label and on into graph.json / the Obsidian export. Names that do
# not match are discarded (zero-edge over a bogus stub).
#
# The classes are spelled out as explicit ASCII ranges (not ``\w``): Python's
# ``\w`` is Unicode-default, so accented (``Basé``), fullwidth (``Ｂase``) and
# other non-ASCII barewords would slip through. Every ``::`` component must begin
# with a letter/underscore, which also rejects a digit-start component
# (``Acme::1x``); ``fullmatch`` (below) anchors the whole string, so a trailing
# newline cannot pass on a ``$`` alone.
_PERL_PKG_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(?:::[A-Za-z_][A-Za-z0-9_]*)*")
_MAX_PERL_PKG_NAME_LEN = 256

# Coarse guard so a pathologically large or deeply nested file cannot make the
# (now iterative) tree walks run away; on exhaustion the file keeps whatever was
# already extracted (file node + partial graph) instead of nothing.
_MAX_PERL_TRAVERSAL_NODES = 2_000_000


def _is_valid_perl_package_name(name: str) -> bool:
    return (
        bool(name)
        and len(name) <= _MAX_PERL_PKG_NAME_LEN
        and _PERL_PKG_NAME_RE.fullmatch(name) is not None
    )

# ``use strict`` & friends are compiler pragmas, not module dependencies — they
# must not become imports edges (matches the pragma-exclusion in other langs).
_PERL_PRAGMAS: frozenset[str] = frozenset({
    "strict", "warnings", "utf8", "constant", "vars", "lib", "feature",
    "integer", "bytes", "overload", "mro", "autodie", "diagnostics",
    "sort", "subs", "attributes", "fields", "encoding", "if", "less",
})

# ``use parent`` / ``use base`` declare inheritance, not an import.
_PERL_INHERIT_PRAGMAS: frozenset[str] = frozenset({"parent", "base"})

# Perl builtins that surface as function_call_expression callees; excluding them
# keeps them from accumulating spurious calls edges as god-nodes. Kept to the
# canonical perlfunc core so a user sub that happens to share a name with a
# builtin still resolves against real definitions in the corpus.
_PERL_BUILTINS: frozenset[str] = frozenset({
    # I/O & formatting
    "print", "printf", "say", "sprintf", "open", "close", "read", "write",
    "binmode", "eof", "seek", "tell", "sysread", "syswrite", "readline",
    # process / system
    "system", "exec", "fork", "wait", "waitpid", "kill", "sleep", "time",
    "exit", "die", "warn",
    # filesystem
    "mkdir", "rmdir", "unlink", "rename", "chdir", "chmod", "chown", "stat",
    "lstat", "opendir", "readdir", "closedir", "glob",
    # list / hash ops
    "shift", "unshift", "push", "pop", "splice", "map", "grep", "sort",
    "reverse", "join", "split", "keys", "values", "each", "exists", "delete",
    # string ops
    "index", "rindex", "substr", "length", "uc", "lc", "ucfirst", "lcfirst",
    "chomp", "chop", "chr", "ord", "hex", "oct", "pack", "unpack",
    "quotemeta",
    # math
    "abs", "int", "sqrt", "sin", "cos", "atan2", "exp", "log", "rand", "srand",
    # scalars / refs / types
    "defined", "ref", "scalar", "bless", "return", "eval", "local", "my",
    "our", "sub", "do", "require", "use", "no", "wantarray",
})


def extract_perl(path: Path) -> dict:
    """Extract packages, subs, imports and inheritance from a .pl/.pm file."""
    try:
        import tree_sitter_perl as tsperl
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_perl not installed"}

    try:
        language = Language(tsperl.language())
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
    # Dedup edges on their identity tuple so a repeated construct (e.g. two
    # `use Foo;` in one file) yields a single edge instead of parallel dups.
    seen_edges: set[tuple[str, str, str, str | None]] = set()
    # sub_nid, body block, and the sub's enclosing package name (for the shared
    # second pass's package-aware call resolution).
    sub_bodies: list[tuple[str, Any, str | None]] = []

    def _text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_stub_node(nid: str, label: str) -> None:
        """External inheritance target (base class defined elsewhere / in the RTL).

        Emitted with an empty ``source_file`` so it does not falsely claim this
        child file as the parent's source and so the corpus-level cross-file
        rewire can collapse it onto the real definition; ``origin_file`` keeps
        distinct same-named stubs apart in the colliding-id pass. Mirrors the
        external-stub shape used by go/julia/objc.
        """
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": "", "source_location": "",
                          "origin_file": str_path})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", context: str | None = None) -> None:
        key = (src, tgt, relation, context)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _package_name(node) -> str | None:
        """`package Foo::Bar;` -> the second `package`-typed child is the name."""
        names = [c for c in node.children if c.type == "package"]
        return _text(names[1]) if len(names) >= 2 else None

    def _string_parents(node) -> list[str]:
        """Every string / qw-word parent named under an inheritance construct.

        Reads string_literal (`'Foo'`) and quoted_word_list (`qw(Foo Bar)`)
        content anywhere below ``node``; autoquoted barewords like ``-norequire``
        are a different node type and are intentionally skipped.
        """
        out: list[str] = []
        stack = [node]
        while stack:
            if not _spend():
                break
            n = stack.pop()
            if n.type in ("string_literal", "interpolated_string_literal", "quoted_word_list"):
                for c in n.children:
                    if c.type == "string_content":
                        out.extend(_text(c).split())
                continue  # an inheritance string's own children are not parents
            stack.extend(reversed(n.children))
        return out

    def add_inherits(pkg_nid: str, parent_name: str, line: int) -> None:
        # Inheritance targets are raw string content; discard anything that is not
        # a well-formed package name so a malformed/crafted string never becomes a
        # node label or an edge (zero-edge, matching the untyped-drop discipline).
        if not _is_valid_perl_package_name(parent_name):
            return
        parent_nid = _make_id(parent_name)
        add_stub_node(parent_nid, parent_name)
        add_edge(pkg_nid, parent_nid, "inherits", line, context="inherit")

    current_pkg_nid: str | None = None
    current_pkg_name: str | None = None
    main_pkg_nid: str | None = None

    def _ensure_main_pkg() -> str:
        """Perl's implicit default package. Code with no ``package`` statement lives
        in ``main``; modeling it explicitly (instead of hanging package-less subs off
        the file node) means a qualified ``main::helper()`` call binds, and a bare
        call from a package-less file is scoped to ``main`` — so it cannot be
        mis-bound to a same-named sub in an unrelated package without import
        evidence. Created lazily so a file with no package-less subs gets no empty
        ``main`` node."""
        nonlocal main_pkg_nid
        if main_pkg_nid is None:
            main_pkg_nid = _make_id(stem, "main")
            add_node(main_pkg_nid, "main", 1)
            add_edge(file_nid, main_pkg_nid, "contains", 1)
        return main_pkg_nid

    budget = [_MAX_PERL_TRAVERSAL_NODES]
    budget_warned = [False]

    def _spend() -> bool:
        """Charge one node against the shared traversal budget; False once spent so
        the walkers stop instead of running away. Emits one bounded warning."""
        budget[0] -= 1
        if budget[0] < 0:
            if not budget_warned[0]:
                budget_warned[0] = True
                _LOG.warning(
                    "perl: traversal budget exhausted for %s; graph for this file is partial",
                    str_path,
                )
            return False
        return True

    def handle_use(node, line: int) -> None:
        # In a use_statement the `use` keyword is its own node type, so the
        # module/pragma name is the first (and only) `package`-typed child —
        # unlike package_statement, where `package` is also the keyword's type.
        pkgs = [c for c in node.children if c.type == "package"]
        if not pkgs:
            return
        module = _text(pkgs[0])
        if module in _PERL_INHERIT_PRAGMAS:
            if current_pkg_nid:
                for parent in _string_parents(node):
                    add_inherits(current_pkg_nid, parent, line)
            return
        if module in _PERL_PRAGMAS:
            return
        add_edge(file_nid, _make_id(module), "imports", line, context="import")

    def handle_require(req_node, line: int) -> None:
        for c in req_node.children:
            if c.type == "bareword":
                add_edge(file_nid, _make_id(_text(c)), "imports", line, context="import")
                return

    def handle_isa(assign_node, line: int) -> None:
        """`our @ISA = (...)` -> inherits edges to each named parent."""
        if not current_pkg_nid:
            return
        is_isa = False
        for child in assign_node.children:
            if child.type == "variable_declaration":
                for sub in child.children:
                    if sub.type == "array" and _text(sub) == "@ISA":
                        is_isa = True
        if not is_isa:
            return
        for parent in _string_parents(assign_node):
            add_inherits(current_pkg_nid, parent, line)

    def walk_statements(root_node) -> None:
        nonlocal current_pkg_nid, current_pkg_name
        # Manual call stack in place of recursion: a pathologically deep nest of
        # block-form packages would otherwise blow the Python stack, and the
        # resulting RecursionError makes `_safe_extract` drop the WHOLE file. Each
        # frame is an iterator over one block's statements plus the scope to restore
        # once that block is exhausted; a block-form `package Foo { ... }` pushes a
        # child frame under Foo's scope, so its subs are attributed to Foo and the
        # prior package is restored for statements that follow the block.
        stack: list[tuple[Any, str | None, str | None]] = [
            (iter(root_node.children), current_pkg_nid, current_pkg_name)
        ]
        while stack:
            child_iter, restore_nid, restore_name = stack[-1]
            descended = False
            for child in child_iter:
                # Charge every visited sibling, not once per frame: a broad flat
                # file drains an unbounded number of children under a single frame,
                # so a per-frame charge left them effectively free.
                if not _spend():
                    return  # budget exhausted: keep the partial graph, stop walking
                line = child.start_point[0] + 1
                if child.type == "package_statement":
                    name = _package_name(child)
                    if name:
                        pkg_nid = _make_id(stem, name)
                        add_node(pkg_nid, name, line)
                        add_edge(file_nid, pkg_nid, "contains", line)
                        pkg_block = next(
                            (c for c in child.children if c.type == "block"), None)
                        if pkg_block is not None:
                            # Descend into the block under Foo; the frame remembers
                            # the pre-block scope so it is restored when the block is
                            # fully consumed (statements after the block are not
                            # mis-attributed to Foo).
                            prev_nid, prev_name = current_pkg_nid, current_pkg_name
                            current_pkg_nid, current_pkg_name = pkg_nid, name
                            stack.append((iter(pkg_block.children), prev_nid, prev_name))
                            descended = True
                            break
                        else:
                            current_pkg_nid = pkg_nid
                            current_pkg_name = name
                elif child.type == "use_statement":
                    handle_use(child, line)
                elif child.type == "subroutine_declaration_statement":
                    name = None
                    block = None
                    for c in child.children:
                        if c.type == "bareword" and name is None:
                            name = _text(c)
                        elif c.type == "block":
                            block = c
                    if name:
                        if "::" in name:
                            # Qualified declaration `sub Pkg::sub {...}` defines the
                            # sub IN the named package, not the current one. Container
                            # = that package (created if it has no `package` statement
                            # of its own); the body's caller-package is the qualifier
                            # so its calls resolve against Pkg.
                            pkg_qual, _, sub_name = name.rpartition("::")
                            container = _make_id(stem, pkg_qual)
                            add_node(container, pkg_qual, line)
                            add_edge(file_nid, container, "contains", line)
                            sub_package = pkg_qual
                        else:
                            # Package-less sub → Perl's `main` (not the file node), so
                            # `main::sub()` binds and bare same-file calls resolve.
                            container = current_pkg_nid or _ensure_main_pkg()
                            sub_name = name
                            sub_package = current_pkg_name or "main"
                        sub_nid = _make_id(container, sub_name)
                        add_node(sub_nid, f"{sub_name}()", line)
                        add_edge(container, sub_nid, "contains", line)
                        if block is not None:
                            sub_bodies.append((sub_nid, block, sub_package))
                elif child.type == "expression_statement":
                    for c in child.children:
                        if c.type == "require_expression":
                            handle_require(c, line)
                        elif c.type == "assignment_expression":
                            handle_isa(c, line)
            if descended:
                continue
            stack.pop()
            current_pkg_nid, current_pkg_name = restore_nid, restore_name

    walk_statements(root)

    raw_calls: list[dict] = []

    def walk_calls(root_node, caller_nid: str, caller_package: str | None) -> None:
        # Iterative (see walk_statements): a deeply nested expression / data
        # structure in a sub body would recurse once per level, and RecursionError
        # here would drop the whole file via `_safe_extract`.
        stack = [root_node]
        while stack:
            if not _spend():
                break
            node = stack.pop()
            if node.type == "function_call_expression":
                # Indirect-object constructor `new CLASS(...)` parses as
                # ambiguous_function_call_expression(function 'new', function_call_expression
                # 'CLASS()'); `new CLASS` == CLASS->new, an untyped member dispatch. Mark
                # it a member call (edge-less) so it is not wired to a sub named CLASS.
                parent = node.parent
                indirect_new = (
                    parent is not None
                    and parent.type == "ambiguous_function_call_expression"
                    and bool(parent.children)
                    and parent.children[0].type == "function"
                    and _text(parent.children[0]) == "new"
                )
                for c in node.children:
                    if c.type == "function":
                        # `Acme::Helper::emit` -> callee `emit`, callee_package
                        # `Acme::Helper`; a bare `emit` -> callee `emit`, no package.
                        # The qualifier + caller package let the shared second pass
                        # bind to the right same-named sub instead of any `emit()`.
                        parts = _text(c).split("::")
                        callee = parts[-1]
                        callee_package = "::".join(parts[:-1]) or None
                        if callee and callee not in _PERL_BUILTINS:
                            raw_calls.append({
                                "caller_nid": caller_nid,
                                "callee": callee,
                                "callee_package": callee_package,
                                "caller_package": caller_package,
                                "is_member_call": indirect_new,
                                "lang": "perl",
                                "source_file": str_path,
                                "source_location": f"L{node.start_point[0] + 1}",
                            })
                        break
            elif node.type == "method_call_expression":
                for c in node.children:
                    if c.type == "method":
                        callee = _text(c).split("::")[-1]
                        if callee:
                            raw_calls.append({
                                "caller_nid": caller_nid,
                                "callee": callee,
                                "is_member_call": True,
                                "lang": "perl",
                                "source_file": str_path,
                                "source_location": f"L{node.start_point[0] + 1}",
                            })
                        break
            stack.extend(reversed(node.children))

    for caller_nid, body, caller_package in sub_bodies:
        walk_calls(body, caller_nid, caller_package)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] == "imports")]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls,
            "input_tokens": 0, "output_tokens": 0}


def _resolve_perl_imports(
    all_nodes: list[dict],
    all_edges: list[dict],
    perl_source_files: set[str] | None = None,
) -> None:
    """Re-point dangling in-corpus Perl ``imports`` edges onto the real package node.

    ``use Foo::Bar;`` / ``require Foo::Bar;`` emit an imports edge to a bare
    module-label id (``_make_id('Foo::Bar')``) that matches no node: when Foo::Bar
    is defined in the corpus its package node's id is ``_make_id(stem, 'Foo::Bar')``
    (and a ``package Foo::Bar;`` may live in a file whose stem is unrelated — a
    multi-package file — so we key on the package LABEL, not the file stem). Bridge
    module-label -> real package id so in-corpus imports connect instead of
    dangling. External modules (POSIX, Carp, …) have no in-corpus package node, so
    their edge keeps its bare target — matching the dangling-stub behavior other
    languages leave on unresolved external imports.

    ``perl_source_files`` (absolute-path strings, from ``extract()`` where
    ``_get_extractor(path) is extract_perl``) scopes both the package-node scan and
    the re-pointed edges to Perl provenance. Suffix-based scoping (``.pl``/``.pm``)
    silently skipped extensionless ``#!/usr/bin/perl`` scripts, which are dispatched
    to extract_perl by shebang and whose imports were never re-pointed
    (underreporting). When ``None`` (direct callers), falls back to suffix matching.

    Runs AFTER the shared cross-file call pass: ``_has_package_import_evidence``
    (extract.py) reads imports targets as bare module-label ids to bind a bare call
    to an imported package's sub, so re-pointing before it would break that binding.
    Mutates ``all_edges`` in place; the bare target was never a node, so there is
    nothing to prune.
    """
    # Provenance matching must survive the cache round-trip. A fresh run stamps a
    # node's `source_file` with the raw `str(path)` the extractor was handed, which
    # is exactly what `perl_source_files` holds — so exact membership matches. But a
    # cached fragment is stored relative and re-anchored on load against the RESOLVED
    # cache root, so its `source_file` comes back as an absolute resolved path that
    # no longer equals the raw provenance string — exact membership then misses and
    # the re-pointer silently no-ops on the second (cached) run. Compare on the
    # resolved form so both shapes collapse to the same on-disk identity.
    resolved_perl_sources: set[str] | None = None
    if perl_source_files is not None:
        resolved_perl_sources = set(perl_source_files)
        for s in perl_source_files:
            try:
                resolved_perl_sources.add(str(Path(s).resolve()))
            except OSError:
                pass
    _resolve_memo: dict[str, bool] = {}

    def _is_perl_source(src: str) -> bool:
        if perl_source_files is None:
            return src.endswith((".pl", ".pm"))
        if src in resolved_perl_sources:
            return True
        hit = _resolve_memo.get(src)
        if hit is None:
            try:
                hit = str(Path(src).resolve()) in resolved_perl_sources
            except OSError:
                hit = False
            _resolve_memo[src] = hit
        return hit

    # module-label id -> list of package node ids carrying that fully-qualified
    # label. A bare `use Foo` cannot disambiguate a package re-opened under the
    # same label across files (e.g. `package Assert;` in both AssertOn.pm and
    # AssertOff.pm), so we re-point ONLY when exactly one package node matches;
    # >1 candidate stays dangling (zero-edge over a guessed cross-file binding).
    pkg_ids_by_label_id: dict[str, list[str]] = {}
    for node in all_nodes:
        src = str(node.get("source_file") or "")
        if not _is_perl_source(src):
            continue
        label = node.get("label", "")
        nid = node.get("id", "")
        # package nodes only: skip the file node (label == basename) and subs
        # (label ends in `()`); neither keys an import target.
        if not label or not nid or label.endswith(")") or label == Path(src).name:
            continue
        pkg_ids_by_label_id.setdefault(_make_id(label), []).append(nid)
    if not pkg_ids_by_label_id:
        return
    for edge in all_edges:
        if edge.get("relation") != "imports":
            continue
        # Scope to Perl imports only, so a same-named module-label id in another
        # language's imports edge is never re-pointed onto a Perl package node.
        if not _is_perl_source(str(edge.get("source_file") or "")):
            continue
        candidates = pkg_ids_by_label_id.get(edge.get("target"))
        if candidates and len(candidates) == 1 and candidates[0] != edge["target"]:
            edge["target"] = candidates[0]
