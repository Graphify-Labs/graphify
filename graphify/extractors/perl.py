"""Perl extractor: packages, subs, imports (use/require), inheritance (@ISA/parent/base).

Deliberately untyped, consistent with the other language extractors. Calls are
handed to the shared cross-file second pass as ``raw_calls`` (INFERRED by
name-matching); method calls (``$obj->meth()``) are marked ``is_member_call`` so
that pass drops them — without receiver types they are unresolvable and naive
name-matching would wire spurious edges to same-named subs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id

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
    "wantarray",
    # string ops
    "index", "rindex", "substr", "length", "uc", "lc", "ucfirst", "lcfirst",
    "chomp", "chop", "chr", "ord", "hex", "oct", "sprintf", "pack", "unpack",
    "quotemeta",
    # math
    "abs", "int", "sqrt", "sin", "cos", "atan2", "exp", "log", "rand", "srand",
    # scalars / refs / types
    "defined", "ref", "scalar", "bless", "return", "eval", "local", "my",
    "our", "sub", "do", "require", "use", "no", "wantarray",
})


def extract_perl(path: Path) -> dict:
    """Extract packages, subs, imports and inheritance from a .pl/.pm/.t file."""
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

        def visit(n) -> None:
            if n.type in ("string_literal", "interpolated_string_literal", "quoted_word_list"):
                for c in n.children:
                    if c.type == "string_content":
                        out.extend(_text(c).split())
                return
            for c in n.children:
                visit(c)

        visit(node)
        return out

    def add_inherits(pkg_nid: str, parent_name: str, line: int) -> None:
        parent_nid = _make_id(parent_name)
        add_stub_node(parent_nid, parent_name)
        add_edge(pkg_nid, parent_nid, "inherits", line, context="inherit")

    current_pkg_nid: str | None = None
    current_pkg_name: str | None = None

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

    def walk_statements(node) -> None:
        nonlocal current_pkg_nid, current_pkg_name
        for child in node.children:
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
                        # Block-form `package Foo { ... }` scopes Foo to the block
                        # only. Walk the block under Foo, then restore the prior
                        # package so following top-level statements are not
                        # mis-attributed to Foo (and the block's subs are not lost).
                        prev_nid, prev_name = current_pkg_nid, current_pkg_name
                        current_pkg_nid, current_pkg_name = pkg_nid, name
                        walk_statements(pkg_block)
                        current_pkg_nid, current_pkg_name = prev_nid, prev_name
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
                    container = current_pkg_nid or file_nid
                    sub_nid = _make_id(container, name)
                    add_node(sub_nid, f"{name}()", line)
                    add_edge(container, sub_nid, "contains", line)
                    if block is not None:
                        sub_bodies.append((sub_nid, block, current_pkg_name))
            elif child.type == "expression_statement":
                for c in child.children:
                    if c.type == "require_expression":
                        handle_require(c, line)
                    elif c.type == "assignment_expression":
                        handle_isa(c, line)

    walk_statements(root)

    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str, caller_package: str | None) -> None:
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
                            "source_file": str_path,
                            "source_location": f"L{node.start_point[0] + 1}",
                        })
                    break
        for child in node.children:
            walk_calls(child, caller_nid, caller_package)

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
    def _is_perl_source(src: str) -> bool:
        if perl_source_files is not None:
            return src in perl_source_files
        return src.endswith((".pl", ".pm"))

    # module-label id -> list of package node ids carrying that fully-qualified
    # label. A bare `use Foo` cannot disambiguate a package re-opened under the
    # same label across files (Foswiki-real: `package Assert;` in AssertOn.pm AND
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
