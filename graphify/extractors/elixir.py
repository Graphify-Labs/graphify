"""Elixir extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import (
    _LANGUAGE_BUILTIN_GLOBALS,
    _file_stem,
    _make_id,
    _read_source_bytes,
)


def extract_elixir(path: Path) -> dict:
    """Extract modules, functions, imports, and calls from a .ex/.exs file."""
    try:
        import tree_sitter_elixir as tselixir
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_elixir not installed"}

    try:
        language = Language(tselixir.language())
        parser = Parser(language)
        source = _read_source_bytes(path)
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()
    function_bodies: list[tuple[str, Any]] = []

    def add_node(nid: str, label: str, line: int, **attrs) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            node = {"id": nid, "label": label, "file_type": "code",
                    "source_file": str_path, "source_location": f"L{line}"}
            node.update(attrs)
            nodes.append(node)

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", weight: float = 1.0,
                 context: str | None = None) -> None:
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": confidence, "source_file": str_path,
                "source_location": f"L{line}", "weight": weight}
        if context:
            edge["context"] = context
        edges.append(edge)

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)
    # Elixir scopes `import`/`use` to the module body it appears in and to the
    # modules nested in it, so targets are recorded per enclosing module (None
    # is the file's top level), along with each module's and function's parent.
    call_scope: dict[str | None, list[str]] = {}
    enclosing: dict[str, str | None] = {}
    # For qualified calls (`Mod.fun()`, #4206): each module's full name, each
    # scope's `alias` table (same scoping as call_scope) and each module's defs.
    module_names: dict[str, str] = {}
    aliases: dict[str | None, dict[str, str]] = {}
    module_defs: dict[tuple[str, str], str] = {}

    _IMPORT_KEYWORDS = frozenset({"alias", "import", "require", "use"})

    def _get_alias_text(node) -> str | None:
        for child in node.children:
            if child.type == "alias":
                return source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
        return None

    def _get_alias_modules(node) -> list[str]:
        """Every module named by an alias/import/require/use argument.

        Handles the single form (``alias Foo.Bar`` -> ``["Foo.Bar"]``) and the
        multi-alias brace form (``alias Foo.{Bar, Baz}`` ->
        ``["Foo.Bar", "Foo.Baz"]``), which the grammar represents as a ``dot``
        node holding the base alias and a trailing ``tuple`` of member aliases.
        """
        def _text(n) -> str:
            return source[n.start_byte:n.end_byte].decode("utf-8", errors="replace")

        for child in node.children:
            if child.type == "alias":
                return [_text(child)]
            if child.type == "dot":
                base = None
                tuple_node = None
                for sub in child.children:
                    if sub.type == "alias" and base is None:
                        base = _text(sub)
                    elif sub.type == "tuple":
                        tuple_node = sub
                if base and tuple_node is not None:
                    members = [_text(m) for m in tuple_node.children if m.type == "alias"]
                    if members:
                        return [f"{base}.{m}" for m in members]
                return [_text(child)]
        return []

    def _get_keyword_alias(node, key: str) -> str | None:
        """The module given for keyword ``key`` in an argument list, e.g. the
        `for:` of `defimpl Proto, for: Type` or the `as:` of `alias A.B, as: C`.
        The grammar holds it in a trailing `keywords` node as a `pair` whose
        keyword is `key:` and whose value is an `alias`."""
        for child in node.children:
            if child.type != "keywords":
                continue
            for pair in child.children:
                if pair.type != "pair":
                    continue
                kw = None
                val = None
                for sub in pair.children:
                    if sub.type == "keyword":
                        kw = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                    elif sub.type == "alias":
                        val = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                if kw and kw.rstrip(": ").strip() == key and val:
                    return val
        return None

    def _expand_module(name: str, scope: str | None) -> str:
        """Expand the first segment of a module reference through the `alias`
        tables visible from ``scope`` (or `__MODULE__` to the current module)."""
        first, _, rest = name.partition(".")
        target = None
        if first == "__MODULE__":
            # ``scope`` is a module, or a function directly inside one.
            if scope is not None and scope not in module_names:
                scope = enclosing.get(scope)
            target = (module_names.get(scope) if scope is not None else None) or None
        else:
            seen: set[str | None] = set()
            container = scope
            while container not in seen:
                seen.add(container)
                target = aliases.get(container, {}).get(first)
                if target is not None or container is None:
                    break
                container = enclosing.get(container)
        if target is None:
            return name
        return f"{target}.{rest}" if rest else target

    def _record_aliases(arguments_node, scope: str | None) -> None:
        modules = [_expand_module(m, scope) for m in _get_alias_modules(arguments_node)]
        as_name = _get_keyword_alias(arguments_node, "as")
        table = aliases.setdefault(scope, {})
        if as_name and len(modules) == 1:
            table[as_name] = modules[0]
        elif not as_name:
            for module in modules:
                table[module.rsplit(".", 1)[-1]] = module

    def _register_module(nid: str, name: str, parent: str | None) -> None:
        # A nested `defmodule Inner` is `Outer.Inner`, and `Inner` is
        # auto-aliased inside Outer.
        parent_name = module_names.get(parent) if parent is not None else None
        if parent_name:
            first = name.split(".", 1)[0]
            aliases.setdefault(parent, {})[first] = f"{parent_name}.{first}"
            name = f"{parent_name}.{name}"
        module_names[nid] = name
    def _get_do_keyword_body(node):
        """The body of a keyword-form definition (`def f(x), do: expr`).

        tree-sitter-elixir puts the keyword body in the `arguments` node's
        trailing `keywords` child, as the value of the `pair` whose keyword
        is `do:` (#4207). Returns the value node, or None when the definition
        uses a `do_block` (or has no keyword body at all).
        """
        if node is None:
            return None
        for child in node.children:
            if child.type != "keywords":
                continue
            for pair in child.children:
                if pair.type != "pair":
                    continue
                keyword_text = None
                for sub in pair.children:
                    if sub.type == "keyword":
                        keyword_text = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                    elif keyword_text is not None and keyword_text.rstrip(": ").strip() == "do":
                        return sub
        return None

    def walk(node, parent_module_nid: str | None = None) -> None:
        if node.type != "call":
            for child in node.children:
                walk(child, parent_module_nid)
            return

        identifier_node = None
        arguments_node = None
        do_block_node = None
        for child in node.children:
            if child.type == "identifier":
                identifier_node = child
            elif child.type == "arguments":
                arguments_node = child
            elif child.type == "do_block":
                do_block_node = child

        if identifier_node is None:
            for child in node.children:
                walk(child, parent_module_nid)
            return

        keyword = source[identifier_node.start_byte:identifier_node.end_byte].decode("utf-8", errors="replace")
        line = node.start_point[0] + 1

        if keyword == "defmodule":
            module_name = _get_alias_text(arguments_node) if arguments_node else None
            if not module_name:
                return
            module_nid = _make_id(stem, module_name)
            # Only a top-level module is a safe cross-file resolution target
            # (#3603 follow-up): a nested `defmodule Supervisor` is labeled with
            # its bare inner name and would otherwise capture an unrelated
            # `use Supervisor` from another file. Mark just the top-level ones;
            # the marker rides through incremental rebuilds via the
            # resolution-context allow-list in watch.py / cli.py.
            add_node(module_nid, module_name, line,
                     **({"_elixir_module": True} if parent_module_nid is None else {}))
            add_edge(file_nid, module_nid, "contains", line)
            enclosing[module_nid] = parent_module_nid
            _register_module(module_nid, module_name, parent_module_nid)
            if do_block_node:
                for child in do_block_node.children:
                    walk(child, parent_module_nid=module_nid)
            return

        if keyword == "defprotocol":
            # A protocol is a module-like named container. Without this branch
            # the `defprotocol` call fell through to the generic recursion with
            # parent_module_nid=None, so the protocol node was never minted and
            # its callbacks (`def size(data)`) were attached to the FILE instead
            # of the protocol.
            proto_name = _get_alias_text(arguments_node) if arguments_node else None
            if not proto_name:
                return
            proto_nid = _make_id(stem, proto_name)
            add_node(proto_nid, proto_name, line,
                     **({"_elixir_module": True} if parent_module_nid is None else {}))
            add_edge(parent_module_nid or file_nid, proto_nid, "contains", line)
            enclosing[proto_nid] = parent_module_nid
            _register_module(proto_nid, proto_name, parent_module_nid)
            if do_block_node:
                for child in do_block_node.children:
                    walk(child, parent_module_nid=proto_nid)
            return

        if keyword == "defimpl":
            # `defimpl Proto, for: Type do ... end`. Same orphaning bug as
            # defprotocol: the implementation's functions leaked onto the file.
            proto_name = _get_alias_text(arguments_node) if arguments_node else None
            if not proto_name:
                return
            target = _get_keyword_alias(arguments_node, "for")
            impl_nid = _make_id(stem, "defimpl", proto_name, target or "")
            label = f"{proto_name} (for {target})" if target else proto_name
            add_node(impl_nid, label, line)
            add_edge(parent_module_nid or file_nid, impl_nid, "contains", line)
            enclosing[impl_nid] = parent_module_nid
            module_names[impl_nid] = f"{proto_name}.{target}" if target else ""
            # Link the implementation to the protocol it satisfies. A same-file
            # protocol resolves directly; a cross-file target is filtered out by
            # the dangling-edge guard below rather than left hanging.
            add_edge(impl_nid, _make_id(stem, proto_name), "implements", line)
            if do_block_node:
                for child in do_block_node.children:
                    walk(child, parent_module_nid=impl_nid)
            return

        # `defmacro`/`defmacrop` (macros) and `defguard`/`defguardp` (guard
        # macros) define named, invocable members with the exact same head shape
        # as `def`/`defp` — a `call` head, optionally wrapped in a `when`
        # binary_operator. They were not in this branch, so they fell through to
        # the generic recursion and were dropped entirely: the member was never a
        # node and a call to it (e.g. a macro invoked elsewhere) had nothing to
        # resolve to. Handle them identically to def/defp; they are already in the
        # call-pass _SKIP_KEYWORDS so their own keyword is never mistaken for a call.
        if keyword in ("def", "defp", "defmacro", "defmacrop",
                       "defguard", "defguardp"):
            func_name = None
            if arguments_node:
                for child in arguments_node.children:
                    # tree-sitter-elixir wraps a guarded head
                    # (`def f(x) when guard`) in `binary_operator`;
                    # without unwrapping, a function whose only clause
                    # carries `when` is dropped (#3111).
                    while child.type == "binary_operator":
                        head = None
                        for sub in child.children:
                            if sub.type in ("call", "identifier", "binary_operator"):
                                head = sub
                                break
                        if head is None:
                            break
                        child = head
                    if child.type == "call":
                        for sub in child.children:
                            if sub.type == "identifier":
                                func_name = source[sub.start_byte:sub.end_byte].decode("utf-8", errors="replace")
                                break
                    elif child.type == "identifier":
                        func_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                        break
            if not func_name:
                return
            container = parent_module_nid or file_nid
            func_nid = _make_id(container, func_name)
            add_node(func_nid, f"{func_name}()", line)
            enclosing[func_nid] = parent_module_nid
            if parent_module_nid:
                add_edge(parent_module_nid, func_nid, "method", line)
                module_defs.setdefault((parent_module_nid, func_name), func_nid)
            else:
                add_edge(file_nid, func_nid, "contains", line)
            if do_block_node:
                function_bodies.append((func_nid, do_block_node))
            else:
                # Keyword form (`def f(x), do: expr`) has no `do_block`; its
                # body is the value of the `do:` pair in `arguments` (#4207).
                # Without this the body is never walked and its calls are
                # silently dropped from the graph.
                keyword_body = _get_do_keyword_body(arguments_node)
                if keyword_body is not None:
                    function_bodies.append((func_nid, keyword_body))
            return

        if keyword in _IMPORT_KEYWORDS and arguments_node:
            for module_name in _get_alias_modules(arguments_node):
                tgt_nid = _make_id(module_name)
                add_edge(file_nid, tgt_nid, "imports", line, context="import")
                # Only import/use bring functions into scope for unqualified
                # calls; alias/require do not.
                if keyword in ("import", "use"):
                    call_scope.setdefault(parent_module_nid, []).append(module_name)
            if keyword == "alias":
                _record_aliases(arguments_node, parent_module_nid)
            return

        for child in node.children:
            walk(child, parent_module_nid)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        normalised = n["label"].strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    module_nid_by_name = {name: nid for nid, name in module_names.items()}
    _MODULE_REF = re.compile(r"(__MODULE__|[A-Z]\w*)(\.[A-Z]\w*)*")

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []
    _SKIP_KEYWORDS = frozenset({
        "def", "defp", "defmodule", "defmacro", "defmacrop",
        "defstruct", "defprotocol", "defimpl", "defguard",
        "alias", "import", "require", "use",
        "if", "unless", "case", "cond", "with", "for",
    })

    def _call_scope_for(caller_nid: str) -> list[str]:
        """import/use targets visible to a call inside ``caller_nid``: its own
        module's, each enclosing module's, then the file's top-level ones."""
        scope: list[str] = []
        seen: set[str] = set()  # a module nested in a same-named one shares its nid
        container = enclosing.get(caller_nid)
        while container is not None and container not in seen:
            seen.add(container)
            scope.extend(call_scope.get(container, ()))
            container = enclosing.get(container)
        scope.extend(call_scope.get(None, ()))
        return scope

    def walk_calls(node, caller_nid: str) -> None:
        if node.type != "call":
            for child in node.children:
                walk_calls(child, caller_nid)
            return
        for child in node.children:
            if child.type == "identifier":
                kw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                if kw in _SKIP_KEYWORDS:
                    if kw == "alias":  # a function-local alias
                        for c in node.children:
                            if c.type == "arguments":
                                _record_aliases(c, caller_nid)
                    for c in node.children:
                        walk_calls(c, caller_nid)
                    return
                break
        callee_name: str | None = None
        is_member_call: bool = False
        receiver_module: str | None = None
        for child in node.children:
            if child.type == "dot":
                is_member_call = True
                dot_text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                parts = dot_text.rstrip(".").split(".")
                if parts:
                    callee_name = parts[-1]
                # `Mod.fun()` / `Alias.fun()` / `__MODULE__.fun()`: keep the
                # module. A variable (`mod.fun()`) or atom receiver stays None.
                if child.child_count == 3:
                    receiver = child.children[0]
                    receiver_text = source[receiver.start_byte:receiver.end_byte].decode(
                        "utf-8", errors="replace")
                    if _MODULE_REF.fullmatch(receiver_text):
                        receiver_module = _expand_module(receiver_text, caller_nid)
                break
            if child.type == "identifier":
                callee_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break
        if callee_name and (receiver_module or callee_name not in _LANGUAGE_BUILTIN_GLOBALS):
            # A remote call only ever reaches the named module's own def: never
            # the bare name, which bound `Repo.insert(x)` to a local insert/1.
            if receiver_module is not None:
                mod_nid = module_nid_by_name.get(receiver_module)
                tgt_nid = module_defs.get((mod_nid, callee_name)) if mod_nid else None
            else:
                tgt_nid = None if is_member_call else label_to_nid.get(callee_name)
            if tgt_nid and tgt_nid != caller_nid:
                pair = (caller_nid, tgt_nid)
                if pair not in seen_call_pairs:
                    seen_call_pairs.add(pair)
                    add_edge(caller_nid, tgt_nid, "calls",
                             node.start_point[0] + 1, confidence="EXTRACTED", weight=1.0,
                             context="call")
            else:
                raw_calls.append({
                    "caller_nid": caller_nid,
                    "callee": callee_name,
                    "is_member_call": is_member_call,
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                    "elixir_call_scope": _call_scope_for(caller_nid),
                    **({"elixir_module": receiver_module} if receiver_module else {}),
                })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body in function_bodies:
        walk_calls(body, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] == "imports")]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls, "input_tokens": 0, "output_tokens": 0}
