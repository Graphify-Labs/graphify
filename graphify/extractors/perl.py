"""Perl extractor: packages and subs.

Deliberately untyped, consistent with the other language extractors. This slice
covers package declarations (statement, block, and mid-file switch forms plus
Perl's implicit ``main``) and sub definitions (including qualified
``sub Bar::baz`` declarations). Imports, inheritance, and call resolution are
follow-up slices; calls are intentionally not collected here.
"""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id

_LOG = logging.getLogger(__name__)

# A valid Perl package/class name: a bareword component (`Foo`, `_priv`) optionally
# joined by `::`. Package names flow raw into node labels and on into graph.json /
# the Obsidian export, so a crafted or malformed name (control chars, markdown,
# newlines, an over-long blob) must be discarded rather than labeled (zero-node
# over a bogus label).
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
# (iterative) tree walks run away; on exhaustion the file keeps whatever was
# already extracted (file node + partial graph) instead of nothing.
_MAX_PERL_TRAVERSAL_NODES = 2_000_000


def _is_valid_perl_package_name(name: str) -> bool:
    return (
        bool(name)
        and len(name) <= _MAX_PERL_PKG_NAME_LEN
        and _PERL_PKG_NAME_RE.fullmatch(name) is not None
    )


def extract_perl(path: Path) -> dict:
    """Extract packages and subs from a .pl/.pm file."""
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

    def _text(node) -> str:
        return source[node.start_byte:node.end_byte].decode("utf-8", errors="replace")

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0})

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def _package_name(node) -> str | None:
        """`package Foo::Bar;` -> the second `package`-typed child is the name."""
        names = [c for c in node.children if c.type == "package"]
        name = _text(names[1]) if len(names) >= 2 else None
        # Root-qualified spelling `::Outer` is the same package as `Outer`
        # (::Name == main::Name in Perl); canonicalize so both spellings key to
        # one package node instead of diverging on an empty qualifier.
        if name and name.startswith("::"):
            name = name[2:]
        # The name comes from arbitrary source text; validate before it becomes a
        # label (zero-node over a malformed or crafted package statement).
        return name if _is_valid_perl_package_name(name or "") else None

    current_pkg_nid: str | None = None
    current_pkg_name: str | None = None
    main_pkg_nid: str | None = None

    def _ensure_main_pkg() -> str:
        """Perl's implicit default package. Code with no ``package`` statement lives
        in ``main``; modeling it explicitly (instead of hanging package-less subs off
        the file node) means a qualified ``main::helper()`` can bind once call
        resolution lands, and a bare call from a package-less file has an honest
        scope. Created lazily so a file with no package-less subs gets no empty
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
                elif child.type == "block_statement":
                    # A bare `{ ... }` scope may itself contain package/sub
                    # declarations (`{ package Inner; sub f {...} }` is valid
                    # Perl); descend without changing scope — the frame restores
                    # whatever the enclosing package was once the block ends.
                    stack.append((iter(child.children), current_pkg_nid, current_pkg_name))
                    descended = True
                    break
                elif child.type == "phaser_statement":
                    # BEGIN/CHECK/INIT/END/UNITCHECK blocks compile their bodies
                    # at the surrounding scope, so declarations inside define real
                    # symbols; descend into the phaser's block like any scope.
                    blk = next((c for c in child.children if c.type == "block"), None)
                    if blk is not None:
                        stack.append((iter(blk.children), current_pkg_nid, current_pkg_name))
                        descended = True
                        break
                elif child.type == "subroutine_declaration_statement":
                    name = None
                    for c in child.children:
                        if c.type == "bareword" and name is None:
                            name = _text(c)
                    if name:
                        if "::" in name:
                            # Qualified declaration `sub Pkg::sub {...}` defines the
                            # sub IN the named package, not the current one. Container
                            # = that package (created if it has no `package` statement
                            # of its own).
                            pkg_qual, _, sub_name = name.rpartition("::")
                            if pkg_qual:
                                container = _make_id(stem, pkg_qual)
                                add_node(container, pkg_qual, line)
                                add_edge(file_nid, container, "contains", line)
                            else:
                                # Root-qualified `sub ::foo {...}` declares
                                # main::foo (::Name == main::Name).
                                container = _ensure_main_pkg()
                        else:
                            # Package-less sub → Perl's `main` (not the file node).
                            container = current_pkg_nid or _ensure_main_pkg()
                            sub_name = name
                        sub_nid = _make_id(container, sub_name)
                        add_node(sub_nid, f"{sub_name}()", line)
                        add_edge(container, sub_nid, "contains", line)
            if descended:
                continue
            stack.pop()
            current_pkg_nid, current_pkg_name = restore_nid, restore_name

    walk_statements(root)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   e["target"] in seen_ids]
    return {"nodes": nodes, "edges": clean_edges,
            "input_tokens": 0, "output_tokens": 0}
