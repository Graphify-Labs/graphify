"""GDScript (Godot ``.gd``) extraction and cross-file resolution.

A script is a class. Its members (``func``, ``signal``, ``const``, ``enum``,
inner ``class``) hang off the file node, or off a class node when the script
declares ``class_name``, so the global name is what owns them.

The per-file pass only reads the file it is given. What it can settle there it
emits as edges: same-file calls, ``self.f()``, local signal ``connect``/``emit``,
``preload``/``load`` of another script or scene, and ``extends "res://…"``.
Everything that needs another file (a ``class_name``, an autoload, an inherited
method or signal, a ``preload`` alias's members) is left as a ``raw_calls``
entry with ``language: "gdscript"`` and resolved by
``resolve_gdscript_references`` against the whole corpus. That keeps a cached
per-file result valid when some other script changes, and lets an incremental
rebuild resolve against the unchanged scripts it receives as context.

A bare call is only ever matched to the script's own methods or to a method of
a script it inherits from: that is all GDScript itself allows. Engine methods
and builtins (``add_child``, ``print``) find no script and stay unresolved. All
entries are flagged ``is_member_call`` so the shared name-matching pass never
binds them to an unrelated script that happens to define the same name.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from graphify.extractors.base import _file_stem, _make_id, _read_source_bytes, _read_text

_LANGUAGE = "gdscript"
_SIGNAL_METHODS = frozenset({"connect", "disconnect", "emit", "is_connected"})
_LOADABLE_SUFFIXES = frozenset({".gd", ".tscn", ".tres"})


def godot_project_root(path: Path) -> Path | None:
    """The directory holding ``project.godot`` above ``path``, or None."""
    for parent in path.parents:
        if (parent / "project.godot").is_file():
            return parent
    return None


def resolve_res_path(ref: str, path: Path, project_root: Path | None) -> Path | None:
    """The file a ``res://`` or relative resource path names, or None.

    ``uid://`` and ``user://`` are left alone: neither names a file in the
    source tree that this pass can see.
    """
    if ref.startswith("res://"):
        if project_root is None:
            return None
        target = project_root / ref[len("res://"):]
    elif "://" in ref or not ref:
        return None
    else:
        target = path.parent / ref
    # Lexical, not resolved: the id must match the one the target's own
    # extraction mints from the same path form, even through a symlink.
    return Path(os.path.normpath(target))


def extract_gdscript(path: Path) -> dict:
    try:
        from tree_sitter import Parser
        from tree_sitter_language_pack import get_language
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-language-pack not installed"}

    try:
        source = _read_source_bytes(path)
        root = Parser(get_language("gdscript")).parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": f"GDScript grammar failed to load: {exc}"}

    source_file = str(path)
    stem = _file_stem(path)
    file_id = _make_id(source_file)
    project_root = godot_project_root(path)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def text(node) -> str:
        return _read_text(node, source)

    def line_of(node) -> int:
        return node.start_point[0] + 1

    def add_node(nid: str, label: str, line: int, kind: str, name: str | None = None,
                 *, callable_node: bool = False) -> None:
        if nid in seen_ids:
            return
        seen_ids.add(nid)
        metadata = {"language": _LANGUAGE, "kind": kind}
        if name is not None:
            metadata["name"] = name
        item: dict[str, Any] = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": f"L{line}",
            "metadata": metadata,
        }
        if callable_node:
            item["_callable"] = True
        nodes.append(item)

    def add_edge(src: str, tgt: str, relation: str, line: int, *,
                 context: str | None = None, **extra: Any) -> None:
        key = (src, tgt, relation)
        if src == tgt or key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": src,
            "target": tgt,
            "relation": relation,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if context:
            edge["context"] = context
        edge.update(extra)
        edges.append(edge)

    def add_ref(caller: str, line: int, kind: str, **fields: Any) -> None:
        raw_calls.append({
            "caller_nid": caller,
            "callee": fields.pop("callee", fields.get("name", "")),
            "is_member_call": True,
            "language": _LANGUAGE,
            "gd_kind": kind,
            "source_file": source_file,
            "source_location": f"L{line}",
            **fields,
        })

    def string_value(node) -> str | None:
        if node is None or node.type != "string":
            return None
        return text(node)[1:-1]

    def plain_type(node) -> str | None:
        """``Foo`` from a ``type`` node that is a single identifier, else None."""
        if node is None:
            return None
        named = node.named_children
        if len(named) == 1 and named[0].type == "identifier":
            return text(named[0])
        return None

    add_node(file_id, path.name, 1, "file")

    owner_id = file_id
    for child in root.named_children:
        if child.type == "class_name_statement":
            name_node = child.child_by_field_name("name")
            if name_node is not None:
                name = text(name_node)
                owner_id = _make_id(stem, "class", name)
                add_node(owner_id, name, line_of(child), "class", name)
                add_edge(file_id, owner_id, "contains", line_of(child))
            break

    # One scope per class body: the script itself and each inner class.
    # members maps (kind, name) -> node id inside that scope.
    scopes: dict[str, dict[tuple[str, str], str]] = {owner_id: {}}
    bodies: list[tuple[str, Any, str, str]] = []   # (caller, body, scope, func name)
    member_values: list[tuple[Any, str]] = []      # top-level var/const initialisers
    type_refs: list[tuple[str, str, int]] = []     # (scope, `var x: Name` type, line)
    aliases: dict[str, Path] = {}                  # const Alias := preload("x.gd")

    def emit_extends(node, owner: str) -> None:
        spec = node.named_children[0] if node.named_children else None
        if spec is None:
            return
        ref = string_value(spec)
        if ref is not None:
            target = resolve_res_path(ref, path, project_root)
            if target is not None and target.suffix == ".gd":
                add_edge(owner, _make_id(str(target)), "inherits", line_of(node),
                         target_file=str(target))
            return
        name = plain_type(spec) if spec.type == "type" else None
        if name is not None:
            add_ref(owner, line_of(node), "extends", name=name)

    def load_target(call) -> Path | None:
        """The script or scene a ``preload("…")`` / ``load("…")`` names."""
        kids = call.named_children
        if len(kids) < 2 or kids[0].type != "identifier" or text(kids[0]) not in ("preload", "load"):
            return None
        args = kids[1].named_children
        ref = string_value(args[0]) if args else None
        target = resolve_res_path(ref, path, project_root) if ref else None
        if target is None or target.suffix not in _LOADABLE_SUFFIXES:
            return None
        return target

    def declare(node, scope: str, scope_stem: str, top: bool) -> None:
        t = node.type
        name_node = node.child_by_field_name("name")
        name = text(name_node) if name_node is not None else None
        line = line_of(node)
        members = scopes[scope]
        if t == "extends_statement":
            emit_extends(node, scope)
            return
        if name is None:
            return
        if t == "function_definition":
            nid = _make_id(scope_stem, name)
            add_node(nid, f".{name}()", line, "function", name, callable_node=True)
            add_edge(scope, nid, "method", line)
            members[("function", name)] = nid
            body = node.child_by_field_name("body")
            if body is not None:
                bodies.append((nid, body, scope, name))
        elif t == "signal_statement":
            nid = _make_id(scope_stem, "signal", name)
            add_node(nid, f"signal {name}", line, "signal", name)
            add_edge(scope, nid, "contains", line)
            members[("signal", name)] = nid
        elif t == "enum_definition":
            nid = _make_id(scope_stem, "enum", name)
            add_node(nid, name, line, "enum", name)
            add_edge(scope, nid, "contains", line)
        elif t in ("const_statement", "variable_statement"):
            if t == "const_statement":
                nid = _make_id(scope_stem, "const", name)
                add_node(nid, name, line, "constant", name)
                add_edge(scope, nid, "contains", line)
            type_name = plain_type(node.child_by_field_name("type"))
            if type_name is not None:
                type_refs.append((scope, type_name, line))
            value = node.child_by_field_name("value")
            if value is not None:
                if top:
                    member_values.append((value, scope))
                if t == "const_statement" and value.type == "call":
                    target = load_target(value)
                    if target is not None:
                        aliases[name] = target
        elif t == "class_definition":
            nid = _make_id(scope_stem, "class", name)
            add_node(nid, name, line, "inner_class", name)
            add_edge(scope, nid, "contains", line)
            members[("class", name)] = nid
            scopes[nid] = {}
            ext = node.child_by_field_name("extends")
            if ext is not None:
                emit_extends(ext, nid)
            body = node.child_by_field_name("body")
            for member in body.named_children if body is not None else ():
                declare(member, nid, f"{scope_stem}/{name}", False)

    for child in root.named_children:
        if child.type != "class_name_statement":
            declare(child, owner_id, stem, True)

    # Member type annotations (`var weapon: Weapon`): an inner class of this
    # script, or another script's class_name for the resolver.
    for scope, type_name, line in type_refs:
        inner = scopes[owner_id].get(("class", type_name))
        if inner is not None:
            add_edge(scope, inner, "references", line, context="type")
        elif scope == owner_id:
            add_ref(owner_id, line, "type", name=type_name)

    # preload/load anywhere in the file: an import of that script or scene.
    # A const alias is tagged so the resolver can follow `Alias.method()`.
    alias_of = {target: name for name, target in aliases.items()}

    def walk_loads(node) -> None:
        if node.type == "call":
            target = load_target(node)
            if target is not None:
                extra: dict[str, Any] = {"target_file": str(target)}
                if target in alias_of:
                    extra["_gd_alias"] = alias_of[target]
                add_edge(file_id, _make_id(str(target)), "imports_from", line_of(node),
                         context="preload", **extra)
        for c in node.named_children:
            walk_loads(c)

    walk_loads(root)

    def local_signal(scope: str, name: str, caller: str, line: int, top: bool, context: str) -> None:
        nid = scopes[scope].get(("signal", name))
        if nid is not None:
            add_edge(caller, nid, "uses", line, context=context)
        elif top:
            add_ref(caller, line, "signal", name=name, context=context)

    def callback(args, scope: str, caller: str, line: int) -> None:
        first = args.named_children[0] if args is not None and args.named_children else None
        if first is None:
            return
        if first.type == "attribute":
            parts = first.named_children
            if len(parts) == 2 and all(p.type == "identifier" for p in parts) and text(parts[0]) == "self":
                first = parts[1]
        if first.type != "identifier":
            return
        nid = scopes[scope].get(("function", text(first)))
        if nid is not None:
            add_edge(caller, nid, "references", line, context="connect")

    def handle_call(node, caller: str, scope: str, func_name: str, top: bool) -> None:
        kids = node.named_children
        if not kids or kids[0].type != "identifier":
            return
        fn = text(kids[0])
        line = line_of(node)
        if fn in ("preload", "load"):
            return
        if fn == "emit_signal":
            args_node = node.child_by_field_name("arguments")
            args = args_node.named_children if args_node is not None else []
            name = string_value(args[0]) if args else None
            if name:
                local_signal(scope, name, caller, line, top, "emit")
            return
        if fn == "super":
            if top:
                add_ref(caller, line, "call", callee=func_name, super=True)
            return
        nid = scopes[scope].get(("function", fn))
        if nid is not None:
            add_edge(caller, nid, "calls", line, context="call")
        elif top:
            add_ref(caller, line, "call", callee=fn)

    def handle_attribute(node, caller: str, scope: str, top: bool) -> None:
        kids = node.named_children
        call_at = next((i for i, c in enumerate(kids) if c.type == "attribute_call"), None)
        if call_at is None:
            return
        chain = kids[:call_at]
        if not chain or not all(c.type == "identifier" for c in chain):
            return   # `$Node.f()`, `get_node(...).f()`, `foo().f()`: receiver unknown here
        call = kids[call_at]
        method_node = next((c for c in call.named_children if c.type == "identifier"), None)
        if method_node is None:
            return
        method = text(method_node)
        args = call.child_by_field_name("arguments")
        names = [text(c) for c in chain]
        line = line_of(node)
        head = names[0]
        if head == "self":
            names = names[1:]

        if head == "super":
            if len(names) == 1 and top:
                add_ref(caller, line, "call", callee=method, super=True)
            return

        if method in _SIGNAL_METHODS and names:
            if len(names) == 1:
                local_signal(scope, names[0], caller, line, top, method)
            elif len(names) == 2 and head != "self" and top:
                add_ref(caller, line, "receiver_signal", receiver=names[0], name=names[1],
                        context=method)
            if method == "connect":
                callback(args, scope, caller, line)
            return

        if head == "self":
            if not names:
                nid = scopes[scope].get(("function", method))
                if nid is not None:
                    add_edge(caller, nid, "calls", line, context="call")
                elif top:
                    add_ref(caller, line, "call", callee=method)
            return

        if len(names) == 1:
            inner = scopes[owner_id].get(("class", head))
            if inner is not None:
                if method == "new":
                    add_edge(caller, inner, "references", line, context="instantiates")
                else:
                    nid = scopes.get(inner, {}).get(("function", method))
                    if nid is not None:
                        add_edge(caller, nid, "calls", line, context="call")
                return
            if top:
                add_ref(caller, line, "receiver_call", receiver=head, callee=method)

    def walk_calls(node, caller: str, scope: str, func_name: str, top: bool) -> None:
        if node.type == "call":
            handle_call(node, caller, scope, func_name, top)
        elif node.type == "attribute":
            handle_attribute(node, caller, scope, top)
        for c in node.named_children:
            walk_calls(c, caller, scope, func_name, top)

    for caller, body, scope, func_name in bodies:
        walk_calls(body, caller, scope, func_name, scope == owner_id)
    for value, scope in member_values:
        walk_calls(value, scope, scope, "", True)

    return {"nodes": nodes, "edges": edges, "raw_calls": raw_calls}


def resolve_gdscript_references(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Resolve the cross-file GDScript references the per-file pass left behind.

    A name binds only when exactly one candidate exists: one script with that
    ``class_name``, one autoload with that name. Every edge it adds is sourced by
    a re-extracted file; unchanged files only serve as targets.
    """
    def meta(node: dict) -> dict:
        m = node.get("metadata")
        return m if isinstance(m, dict) and m.get("language") == _LANGUAGE else {}

    gd = {n["id"]: meta(n) for n in all_nodes if n.get("id") and meta(n)}
    classes: dict[str, list[str]] = {}
    autoloads: dict[str, list[str]] = {}
    for nid, m in gd.items():
        if m.get("kind") == "class":
            classes.setdefault(str(m.get("name")), []).append(nid)
        elif m.get("kind") == "autoload":
            autoloads.setdefault(str(m.get("name")), []).append(nid)

    members: dict[str, dict[tuple[str, str], str]] = {}
    owner_of: dict[str, str] = {}
    class_of_file: dict[str, str] = {}
    autoload_target: dict[str, str] = {}
    aliases: dict[tuple[str, str], str] = {}
    for e in all_edges:
        rel, src, tgt = e.get("relation"), e.get("source"), e.get("target")
        if rel in ("method", "contains") and tgt in gd and src in gd:
            kind = gd[tgt].get("kind")
            if kind in ("function", "signal"):
                members.setdefault(src, {})[(kind, str(gd[tgt].get("name")))] = tgt
                owner_of[tgt] = src
            elif kind == "class":
                class_of_file[src] = tgt
        elif rel == "imports_from" and src in gd:
            if gd[src].get("kind") == "autoload":
                autoload_target[src] = tgt
            alias = e.pop("_gd_alias", None)
            if alias:
                aliases[(str(e.get("source_file")), alias)] = tgt

    def owner(nid: str) -> str:
        return class_of_file.get(nid, nid)

    def unique(table: dict[str, list[str]], name: str) -> str | None:
        hits = table.get(name, [])
        return hits[0] if len(hits) == 1 else None

    existing = {(e.get("source"), e.get("target"), e.get("relation")) for e in all_edges}

    def add(rc: dict, src: str, tgt: str, relation: str, context: str) -> None:
        if src == tgt or (src, tgt, relation) in existing:
            return
        existing.add((src, tgt, relation))
        all_edges.append({
            "source": src,
            "target": tgt,
            "relation": relation,
            "context": context,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": rc.get("source_file", ""),
            "source_location": rc.get("source_location"),
            "weight": 1.0,
        })

    refs = [
        rc for result in per_file for rc in result.get("raw_calls", [])
        if rc.get("language") == _LANGUAGE and rc.get("gd_kind")
    ]

    # Inheritance first: the member lookups below walk it.
    for rc in refs:
        if rc["gd_kind"] == "extends":
            target = unique(classes, str(rc.get("name")))
            if target is not None:
                add(rc, rc["caller_nid"], target, "inherits", "extends")

    parent: dict[str, str] = {}
    for e in all_edges:
        if e.get("relation") == "inherits" and e.get("source") in gd and e.get("target") in gd:
            parent[owner(e["source"])] = owner(e["target"])

    def lineage(start: str, include_self: bool) -> list[str]:
        out = [start] if include_self else []
        seen = {start}
        current = start
        while current in parent and parent[current] not in seen:
            current = parent[current]
            seen.add(current)
            out.append(current)
        return out

    def lookup(start: str, kind: str, name: str, include_self: bool = True) -> str | None:
        for scope in lineage(owner(start), include_self):
            hit = members.get(scope, {}).get((kind, name))
            if hit is not None:
                return hit
        return None

    def receiver(rc: dict) -> str | None:
        name = str(rc.get("receiver"))
        target = aliases.get((str(rc.get("source_file")), name))
        if target is None:
            auto = unique(autoloads, name)
            target = autoload_target.get(auto) if auto is not None else None
        if target is None:
            target = unique(classes, name)
        return owner(target) if target is not None else None

    for rc in refs:
        kind = rc["gd_kind"]
        caller = rc["caller_nid"]
        scope = owner_of.get(caller, caller)
        if kind == "type":
            target = unique(classes, str(rc.get("name")))
            if target is not None:
                add(rc, caller, target, "references", "type")
        elif kind == "call":
            target = lookup(scope, "function", str(rc.get("callee")),
                            include_self=not rc.get("super"))
            if target is not None:
                add(rc, caller, target, "calls", "call")
        elif kind == "signal":
            target = lookup(scope, "signal", str(rc.get("name")))
            if target is not None:
                add(rc, caller, target, "uses", str(rc.get("context")))
        elif kind in ("receiver_call", "receiver_signal"):
            target_owner = receiver(rc)
            if target_owner is None:
                continue
            if kind == "receiver_signal":
                target = lookup(target_owner, "signal", str(rc.get("name")))
                if target is not None:
                    add(rc, caller, target, "uses", str(rc.get("context")))
            elif rc.get("callee") == "new":
                add(rc, caller, target_owner, "references", "instantiates")
            else:
                target = lookup(target_owner, "function", str(rc.get("callee")))
                if target is not None:
                    add(rc, caller, target, "calls", "call")
