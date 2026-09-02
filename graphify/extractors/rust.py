"""Rust extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
from pathlib import Path
from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id, _read_text


def _rust_collect_type_refs(node, source: bytes, generic: bool, out: list[tuple[str, str]]) -> None:
    """Walk a Rust type expression; append (name, role) tuples."""
    if node is None:
        return
    t = node.type
    if t == "primitive_type":
        return
    if t == "type_identifier":
        text = _read_text(node, source)
        if text:
            out.append((text, "generic_arg" if generic else "type"))
        return
    if t == "scoped_type_identifier":
        text = _read_text(node, source).rsplit("::", 1)[-1]
        if text:
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
            if text:
                out.append((text, "generic_arg" if generic else "type"))
        for c in node.children:
            if c.type == "type_arguments":
                for arg in c.children:
                    if arg.is_named:
                        _rust_collect_type_refs(arg, source, True, out)
        return
    if t in ("reference_type", "pointer_type", "array_type", "tuple_type", "slice_type"):
        for c in node.children:
            if c.is_named:
                _rust_collect_type_refs(c, source, generic, out)
        return
    if node.is_named:
        for c in node.children:
            if c.is_named:
                _rust_collect_type_refs(c, source, generic, out)

_RUST_TRAIT_METHOD_BLOCKLIST: frozenset[str] = frozenset({
    "new", "default", "parse", "from_str", "now", "clone", "into", "from",
    "to_string", "to_owned", "len", "is_empty", "iter", "next", "build",
    "start", "run", "init", "app", "get", "set", "push", "pop", "insert",
    "remove", "contains", "collect", "map", "filter", "unwrap", "expect",
    "ok", "err", "some", "none", "send", "recv", "lock", "read", "write",
})

# Rust module roots: a file that IS its module (rather than a child of one).
_RUST_MODULE_ROOT_FILES = ("mod.rs", "lib.rs", "main.rs")

# `pub(self)` restricts to the current module, which is what a bare `use`
# already does — it publishes nothing and so is not a re-export.
_RUST_PUB_SELF_RE = re.compile(r"^pub\s*\(\s*self\s*\)$")


def _rust_path_segments(node, source: bytes) -> list[str]:
    """Flatten a use-path node into its segments.

    ``crate::models::prelude`` parses as nested ``scoped_identifier``s; the
    leading ``crate``/``super``/``self`` keywords are their own node types, not
    ``identifier``, so read text rather than filtering on type.
    """
    if node is None:
        return []
    if node.type == "scoped_identifier":
        segments: list[str] = []
        for child in node.children:
            if child.type == "::":
                continue
            segments.extend(_rust_path_segments(child, source))
        return segments
    text = _read_text(node, source).strip()
    return [text] if text else []


def _rust_use_leaves(node, source: bytes, prefix: tuple[str, ...] = ()) -> list[tuple[tuple[str, ...], str | None, bool]]:
    """Flatten a ``use`` tree into ``(path_segments, alias, is_wildcard)`` leaves.

    One declaration can bind many names —  ``use crate::x::{a, b::C, d as D}``
    is three leaves, and lists nest arbitrarily. The previous string-splitting
    approach took everything before the first ``{`` and kept the last ``::``
    segment, so a braced list collapsed to a single edge naming the shared
    prefix and every name inside it was lost. ``use_as_clause`` was not parsed
    at all, leaving the alias glued to the symbol (``Entity as Risk``).
    """
    if node is None:
        return []
    t = node.type
    if t == "use_as_clause":
        path_node = node.child_by_field_name("path")
        alias_node = node.child_by_field_name("alias")
        if path_node is None or alias_node is None:
            named = [c for c in node.named_children]
            path_node = path_node or (named[0] if named else None)
            alias_node = alias_node or (named[1] if len(named) > 1 else None)
        if path_node is not None and path_node.type == "self" and prefix:
            # `use foo::bar::{self as bar_mod, Baz}` aliases the MODULE the
            # prefix spells, exactly as the unaliased `self` does.
            segments = tuple(prefix)
        else:
            segments = tuple(prefix) + tuple(_rust_path_segments(path_node, source))
        alias = _read_text(alias_node, source).strip() if alias_node is not None else None
        return [(segments, alias or None, False)] if segments else []
    if t == "use_wildcard":
        segments: tuple[str, ...] = tuple(prefix)
        for child in node.children:
            if child.type in ("::", "*"):
                continue
            segments = segments + tuple(_rust_path_segments(child, source))
        return [(segments, None, True)] if segments else []
    if t == "use_list":
        leaves: list[tuple[tuple[str, ...], str | None, bool]] = []
        for child in node.named_children:
            leaves.extend(_rust_use_leaves(child, source, prefix))
        return leaves
    if t == "scoped_use_list":
        inner_prefix = tuple(prefix)
        list_node = None
        for child in node.children:
            if child.type == "::":
                continue
            if child.type == "use_list":
                list_node = child
            else:
                inner_prefix = inner_prefix + tuple(_rust_path_segments(child, source))
        return _rust_use_leaves(list_node, source, inner_prefix) if list_node else []
    if t == "self" and prefix:
        # Inside a use list, `self` names the MODULE the prefix already spells:
        # `use foo::bar::{self, Baz}` binds `foo::bar`, not a symbol called
        # `self`. Appending the segment would resolve nothing and mint a node
        # labelled `self`. A leading `self::` path has an empty prefix and
        # falls through below, where `_resolve_rust_use_path` anchors it.
        return [(tuple(prefix), None, False)]
    if t in ("scoped_identifier", "identifier", "crate", "super", "self", "metavariable"):
        segments = tuple(prefix) + tuple(_rust_path_segments(node, source))
        return [(segments, None, False)] if segments else []
    return []


# Cargo's conventional auto-discovered target directories. A .rs file sitting
# directly in one of these IS a crate root of its own, so `crate::` inside it
# refers to that file's module tree, not to the library's `src/`.
# `bin` is only auto-discovered under `src`; the others sit at the package
# root. A top-level `bin/` is just a directory and holds no crate roots.
_RUST_PACKAGE_TARGET_DIRS = ("examples", "tests", "benches")
_RUST_SRC_TARGET_DIRS = ("bin",)


def _rust_crate_src_root(path: Path) -> Path | None:
    """The root directory ``crate::`` resolves against for ``path``.

    Usually the owning package's ``src``. But a file directly inside one of
    Cargo's auto-discovered target directories — ``src/bin/tool.rs``,
    ``examples/demo.rs``, ``tests/it.rs``, ``benches/bench.rs`` — is its OWN
    crate root, so ``crate::helper`` there means ``src/bin/tool/helper.rs``,
    not ``src/helper.rs``. A directory form (``src/bin/tool/main.rs``) is
    already handled by the plain ``src`` answer plus the module walk.

    Returns ``None`` when no ``Cargo.toml`` is above ``path`` — there is no
    crate to resolve against, and callers must not walk the filesystem.
    """
    probe = path.parent
    while True:
        if (probe / "Cargo.toml").is_file():
            src = probe / "src"
            base = src if src.is_dir() else probe
            own = _rust_auto_target_crate_dir(path, base, probe)
            return own if own is not None else base
        if probe.parent == probe:
            return None
        probe = probe.parent


def _rust_is_auto_target_dir(directory: Path, src: Path, package: Path) -> bool:
    """True when ``directory`` is one of Cargo's auto-discovered target dirs.

    ``bin`` lives under ``src``; ``examples``/``tests``/``benches`` sit at the
    package root.
    """
    if directory.name in _RUST_SRC_TARGET_DIRS:
        # Only under `src`, and only when `src` is a real directory — with no
        # `src/` the package root stands in for it, and a top-level `bin/`
        # there is not an auto-target.
        return src.name == "src" and directory.parent == src
    return directory.name in _RUST_PACKAGE_TARGET_DIRS and directory.parent == package


def _rust_auto_target_crate_dir(path: Path, src: Path, package: Path) -> Path | None:
    """The crate-root directory when ``path`` belongs to an auto-target crate.

    Two shapes reach the same answer. ``src/bin/tool.rs`` IS the crate, so its
    module tree is the sibling ``src/bin/tool/``; a module of that crate
    (``src/bin/tool/helper.rs``, or deeper) resolves ``crate::`` against the
    same directory. Returns ``None`` for an ordinary module of the library
    crate, which anchors at ``src``.
    """
    if path.name not in _RUST_MODULE_ROOT_FILES and _rust_is_auto_target_dir(
        path.parent, src, package
    ):
        # The crate root file itself. The sibling directory holds its children;
        # if it does not exist the crate simply has none, which the module walk
        # discovers — better than falling back to `src` and edging a namesake
        # module of the library.
        return path.parent / path.stem
    # A module nested inside an auto-target crate: the crate root is the
    # directory whose own parent is the auto-target directory.
    probe = path.parent
    while probe != package and probe.parent != probe:
        if _rust_is_auto_target_dir(probe.parent, src, package):
            return probe
        probe = probe.parent
    return None


def _rust_module_file(directory: Path, name: str) -> Path | None:
    """Resolve one module segment inside ``directory``: ``name.rs`` or ``name/mod.rs``."""
    candidate = directory / f"{name}.rs"
    if candidate.is_file():
        return candidate
    candidate = directory / name / "mod.rs"
    if candidate.is_file():
        return candidate
    return None


def _rust_module_dirs(path: Path) -> tuple[Path, Path]:
    """Return ``(search_dir, super_dir)`` for the module ``path`` defines.

    ``mod.rs``/``lib.rs``/``main.rs`` ARE their module, so their own directory
    holds their children and the parent directory is ``super``. Any other file
    ``foo.rs`` is a module whose children live in a sibling ``foo/`` directory,
    and whose ``super`` is the directory it sits in.

    ``search_dir`` falls back to the containing directory when a plain
    ``foo.rs`` has no sibling ``foo/``, which is what the 2018-edition
    crate-relative *heuristic* wants to probe. It is NOT the module's ``self``
    — use :func:`_rust_self_module_dir` for a path anchored on the ``self``
    keyword, which must not reach the module's siblings.
    """
    if path.name in _RUST_MODULE_ROOT_FILES:
        return path.parent, path.parent.parent
    sibling = path.parent / path.stem
    return (sibling if sibling.is_dir() else path.parent), path.parent


def _rust_self_module_dir(path: Path) -> Path | None:
    """The directory holding ``path``'s CHILD modules, or ``None`` if it has none.

    ``self::x`` names a child of this module, so it resolves inside the
    module's own directory. A plain ``foo.rs`` with no sibling ``foo/`` has no
    children at all, and falling back to its containing directory would
    silently make ``self::`` behave like ``super::`` — resolving a sibling
    module the ``self`` path cannot legally reach.
    """
    if path.name in _RUST_MODULE_ROOT_FILES:
        return path.parent
    sibling = path.parent / path.stem
    return sibling if sibling.is_dir() else None


def _resolve_rust_use_path(
    segments: tuple[str, ...], path: Path
) -> "tuple[Path, str | None] | None":
    """Resolve a ``use`` path to ``(module_file, symbol_name)`` on disk.

    Walks ``crate``/``super``/``self``-anchored paths through the crate's module
    tree. The trailing segment of a ``use`` is usually a SYMBOL rather than a
    module (``crate::models::prelude::Risk``), so when the full path does not
    name a file the last segment is retried as a symbol inside the module the
    rest resolves to. Returns ``None`` for anything not on disk — an external
    crate (``std``, ``sea_orm``) or a path this resolver cannot follow.
    """
    if not segments:
        return None
    search_dir, super_dir = _rust_module_dirs(path)
    src_root = _rust_crate_src_root(path)

    index = 0
    anchor: Path | None = None
    first = segments[0]
    if first == "crate":
        anchor, index = src_root, 1
    elif first == "self":
        anchor, index = _rust_self_module_dir(path), 1
    elif first == "super":
        # `super` walks one module up per keyword, but the crate root has no
        # `super`. Every step and the final anchor are checked against the
        # crate floor, so the walk can never leave the crate and resolve an
        # unrelated file higher up the filesystem. With no `Cargo.toml` above
        # the file there is no floor, and no `super` is honoured at all.
        if src_root is None:
            return None
        anchor, index = super_dir, 1
        while index < len(segments) and segments[index] == "super":
            if anchor is None or anchor == src_root:
                return None
            anchor = anchor.parent
            index += 1
        if anchor is None or src_root not in (anchor, *anchor.parents):
            return None
    if anchor is None and first not in ("crate", "self", "super"):
        # 2018-edition paths may be crate-relative without the `crate` prefix;
        # try the crate root, then the current module. An external crate simply
        # resolves to nothing at either.
        for candidate_anchor in (src_root, search_dir):
            if candidate_anchor is None:
                continue
            # No anchor_file here: a bare path is only a GUESS at being
            # crate-relative, and seeding the anchor's own file would make
            # every external crate (`use anyhow::Result`) resolve to a symbol
            # named `anyhow` inside `lib.rs`.
            resolved = _walk_rust_segments(candidate_anchor, segments)
            if resolved is not None:
                return resolved
        return None
    if anchor is None:
        if first == "self" and len(segments) >= 2:
            # `use self::Config;` names an item of THIS module, which needs no
            # child directory to live in. A longer path names something inside
            # that item (`self::Status::Active`), so the item is attributed and
            # the rest dropped — the same rule `_walk_rust_segments` applies.
            return path, segments[1]
        if first == "self":
            # `use self::{self};` names this module, children or not.
            return path, None
        return None
    if first == "self":
        anchor_file = path
    elif path.parent == anchor and path.name in _RUST_MODULE_ROOT_FILES:
        # A crate with both `src/lib.rs` and `src/main.rs` has two roots in one
        # directory. `crate::` inside `main.rs` is `main.rs`, so prefer the
        # file doing the importing over the first name that happens to exist.
        anchor_file = path
    else:
        anchor_file = _rust_module_root_file(anchor)
    remainder = segments[index:]
    if not remainder:
        # A keyword-only path: `use super::{self};` / `use crate::{self};`
        # name the anchor's module itself, with nothing left to walk. Without
        # this the leaf resolved to nothing and the import was dropped.
        return (anchor_file, None) if anchor_file is not None else None
    return _walk_rust_segments(anchor, remainder, anchor_file=anchor_file)


def _rust_module_root_file(directory: Path) -> Path | None:
    """The file that IS the module owning ``directory``, if one is present.

    A symbol imported straight off an anchor (``use crate::Config``) is defined
    in that module's own file rather than in a child module, so the anchor
    needs a file to attribute it to.
    """
    for name in _RUST_MODULE_ROOT_FILES:
        candidate = directory / name
        if candidate.is_file():
            return candidate
    # A module can equally be backed by a sibling FILE: `src/models.rs` owns
    # `src/models/`. Without this, `use super::Config` from a child resolved
    # only when the parent happened to be a `mod.rs`.
    sibling = directory.parent / f"{directory.name}.rs"
    return sibling if sibling.is_file() else None


def _walk_rust_segments(
    anchor: Path, segments: tuple[str, ...], anchor_file: Path | None = None
) -> "tuple[Path, str | None] | None":
    """Walk module segments from ``anchor``; the tail may name a symbol.

    ``anchor_file`` is the file backing ``anchor``'s own module, so a symbol
    that is not inside any child module (``use crate::Config``, defined in
    ``lib.rs``) still resolves instead of dropping its edge.
    """
    if not segments:
        return None
    directory = anchor
    resolved: Path | None = None
    for position, segment in enumerate(segments):
        found = _rust_module_file(directory, segment)
        if found is None:
            if (
                resolved is None
                and anchor_file is not None
                and position == len(segments) - 1
            ):
                # `use crate::Config` — the only segment is not a module, so it
                # is an item of the anchor's own module file. Restricted to a
                # LAST segment: an unresolved segment with more behind it was
                # meant to be a module (`crate::models::risk::X` where
                # `models` does not exist), and attributing that module name as
                # an item of `lib.rs` invents a symbol nothing defines.
                return anchor_file, segment
            # Not a module, so the remainder is a symbol path inside the module
            # that resolved (`…::prelude::Risk` -> `Risk`). The FIRST unresolved
            # segment is the item the module defines; anything after it names
            # something inside that item (`…::Status::Active` -> `Status`), so
            # attribute the item and drop the rest rather than the whole edge.
            if resolved is not None:
                return resolved, segment
            return None
        resolved = found
        directory = found.parent if found.name == "mod.rs" else found.parent / found.stem
    return (resolved, None) if resolved is not None else None


def extract_rust(path: Path) -> dict:
    """Extract functions, structs, enums, traits, impl methods, and use declarations from a .rs file."""
    try:
        import tree_sitter_rust as tsrust
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-rust not installed"}

    try:
        language = Language(tsrust.language())
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
        nid = _make_id(stem, name)
        if nid in seen_ids:
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
                _rust_collect_type_refs(type_node, source, False, refs)
                for ref_name, role in refs:
                    ctx = "generic_arg" if role == "generic_arg" else "parameter_type"
                    tgt = ensure_named_node(ref_name, line)
                    if tgt != func_nid:
                        add_edge(func_nid, tgt, "references", line, context=ctx)
        return_type = func_node.child_by_field_name("return_type")
        if return_type is not None:
            refs = []
            _rust_collect_type_refs(return_type, source, False, refs)
            for ref_name, role in refs:
                ctx = "generic_arg" if role == "generic_arg" else "return_type"
                tgt = ensure_named_node(ref_name, line)
                if tgt != func_nid:
                    add_edge(func_nid, tgt, "references", line, context=ctx)

    def emit_use_leaf(segments, alias, is_wildcard: bool, is_reexport: bool, line: int) -> None:
        """Emit the edges for one resolved leaf of a ``use`` declaration.

        Two edges where the path resolves on disk: a file-level ``imports_from``
        so the module graph connects, and a symbol-level edge stamped with
        ``target_file`` so the shared canonicalization repoints it at the real
        definition. Unresolved paths (external crates) get a sourceless stub
        rather than a bare-name target — the old code emitted an id no node ever
        carried, so the edge dangled and was dropped at build time, which is why
        a prelude showed inbound edges and no outbound ones.
        """
        if not segments:
            return
        resolution = _resolve_rust_use_path(tuple(segments), path)
        if resolution is None:
            # External crate or unresolvable path. Mint a sourceless stub for the
            # leaf name so the edge has a real endpoint and the corpus-level
            # rewire can still collapse it onto a definition if one shows up.
            name = alias or segments[-1]
            if not is_wildcard and name:
                stub_nid = ensure_named_node(name, line)
                add_edge(file_nid, stub_nid, "imports_from", line, context="import")
                if is_reexport:
                    # `pub use anyhow::Result;` republishes an external name.
                    # Without the symbol-level `re_exports` the barrel collapse
                    # cannot follow a consumer through this module, which is the
                    # whole point of resolving preludes.
                    add_edge(file_nid, stub_nid, "re_exports", line)
            return
        module_file, symbol = resolution
        module_nid = _make_id(str(module_file))
        file_edge = {
            "source": file_nid, "target": module_nid, "relation": "imports_from",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0, "context": "import",
            "target_file": str(module_file),
        }
        if symbol is None and alias and alias != segments[-1]:
            # `use crate::models::risk as risk_model;` aliases the MODULE, so
            # the alias belongs on the file-level edge. Compared against the
            # last PATH segment, which is the module's name as written: a
            # `mod.rs` file's stem is `mod`, not the module it defines.
            file_edge["local_alias"] = alias
        edges.append(file_edge)
        if symbol is None or is_wildcard:
            # `use super::risk;` names the module itself, and a glob re-export
            # (`pub use super::risk::*;`) publishes an unknown set of names —
            # neither identifies one symbol to point at.
            return
        # Build the id the DEFINING file gives its own symbols (`_make_id(stem,
        # name)`), so this edge lands on that node rather than a look-alike the
        # corpus rewire has to guess at.
        symbol_nid = _make_id(_file_stem(module_file), symbol)
        symbol_edge = {
            "source": file_nid, "target": symbol_nid,
            "relation": "re_exports" if is_reexport else "imports",
            "confidence": "EXTRACTED", "source_file": str_path,
            "source_location": f"L{line}", "weight": 1.0,
            "target_file": str(module_file),
        }
        if alias and alias != symbol:
            # `use …::Entity as Risk;` — this file spells the symbol `Risk`.
            # `local_alias` is the field the corpus-level receiver resolution
            # already reads (#2082), so the alias resolves like the bare name
            # instead of being parsed and then dropped.
            symbol_edge["local_alias"] = alias
        edges.append(symbol_edge)

    def walk(node, parent_impl_nid: str | None = None) -> None:
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
                else:
                    func_nid = _make_id(stem, func_name)
                    add_node(func_nid, f"{func_name}()", line)
                    add_edge(file_nid, func_nid, "contains", line)
                emit_param_return_refs(node, func_nid, line)
                body = node.child_by_field_name("body")
                if body:
                    function_bodies.append((func_nid, body))
            return

        if t in ("struct_item", "enum_item", "trait_item"):
            name_node = node.child_by_field_name("name")
            if name_node:
                item_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                item_nid = _make_id(stem, item_name)
                add_node(item_nid, item_name, line)
                add_edge(file_nid, item_nid, "contains", line)
                if t == "trait_item":
                    for c in node.children:
                        if c.type != "trait_bounds":
                            continue
                        for sub in c.children:
                            if not sub.is_named:
                                continue
                            refs: list[tuple[str, str]] = []
                            _rust_collect_type_refs(sub, source, False, refs)
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
                            _rust_collect_type_refs(type_node, source, False, refs)
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
                            _rust_collect_type_refs(tc, source, False, refs)
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
                        _rust_collect_type_refs(type_node, source, False, refs2)
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
            return

        if t == "impl_item":
            type_node = node.child_by_field_name("type")
            trait_node = node.child_by_field_name("trait")
            impl_nid: str | None = None
            if type_node:
                type_name = _read_text(type_node, source).strip()
                impl_nid = _make_id(stem, type_name)
                add_node(impl_nid, type_name, node.start_point[0] + 1)
            if trait_node is not None and impl_nid is not None:
                refs: list[tuple[str, str]] = []
                _rust_collect_type_refs(trait_node, source, False, refs)
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
                for child in body.children:
                    walk(child, parent_impl_nid=impl_nid)
            return

        if t == "use_declaration":
            arg = node.child_by_field_name("argument")
            if arg:
                line = node.start_point[0] + 1
                # `pub use` is a RE-EXPORT: the module publishes someone else's
                # symbol under its own path. The corpus-level barrel collapse
                # keys on this relation to follow consumers through to the
                # defining file, so a prelude stops being a dead end.
                # `pub(self)` is exactly as private as a bare `use`, so it is
                # NOT a re-export. `pub(crate)`/`pub(super)`/`pub(in path)`
                # genuinely republish within a scope and still count.
                is_reexport = any(
                    child.type == "visibility_modifier"
                    and not _RUST_PUB_SELF_RE.match(_read_text(child, source))
                    for child in node.children
                )
                for segments, alias, is_wildcard in _rust_use_leaves(arg, source):
                    emit_use_leaf(segments, alias, is_wildcard, is_reexport, line)
            return

        for child in node.children:
            walk(child, parent_impl_nid=None)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        raw = n["label"]
        normalised = raw.strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type == "function_item":
            return
        if node.type == "call_expression":
            func_node = node.child_by_field_name("function")
            callee_name: str | None = None
            is_member_call: bool = False
            is_scoped_call: bool = False
            if func_node:
                if func_node.type == "identifier":
                    callee_name = _read_text(func_node, source)
                elif func_node.type == "field_expression":
                    is_member_call = True
                    field = func_node.child_by_field_name("field")
                    if field:
                        callee_name = _read_text(field, source)
                elif func_node.type == "scoped_identifier":
                    # Type::method() — still allow in-file EXTRACTED match, but
                    # skip cross-file resolution: bare last-segment lookup ignores
                    # crate boundaries and produces spurious INFERRED edges (#908).
                    is_scoped_call = True
                    name = func_node.child_by_field_name("name")
                    if name:
                        callee_name = _read_text(name, source)
            if callee_name and callee_name not in _LANGUAGE_BUILTIN_GLOBALS:
                tgt_nid = label_to_nid.get(callee_name)
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
                elif not is_scoped_call and callee_name.lower() not in _RUST_TRAIT_METHOD_BLOCKLIST:
                    raw_calls.append({
                        "caller_nid": caller_nid,
                        "callee": callee_name,
                        "is_member_call": is_member_call,
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
        # A cross-file import target is not a node this file owns, so these
        # relations are allowed to point outside `valid_ids` and are resolved
        # corpus-wide later. `re_exports` belongs with them — a barrel names a
        # symbol it does not define — and matches the shared engine filter.
        if src in valid_ids and (tgt in valid_ids or edge["relation"] in ("imports", "imports_from", "re_exports")):
            clean_edges.append(edge)

    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
