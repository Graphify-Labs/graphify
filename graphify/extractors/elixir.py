"""Elixir extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from graphify.extractors.base import _LANGUAGE_BUILTIN_GLOBALS, _file_stem, _make_id


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
    function_bodies: list[tuple[str, Any]] = []
    # Per-file alias bindings (local name -> full module name) collected from
    # `alias`/`use`/`require`/`import` directives. The cross-file Elixir
    # resolver uses them to turn an aliased remote call (`Channels.create()`
    # after `alias ChatServer.Channels`) into a precise edge. Deterministic
    # and cache-safe: recorded at extraction time, consumed only at resolve
    # time (gated there behind GRAPHIFY_ELIXIR_REMOTE_CALLS).
    elixir_aliases: dict[str, str] = {}

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

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

    _IMPORT_KEYWORDS = frozenset({"alias", "import", "require", "use"})

    # ExUnit block macros whose do_block holds test code. Their bodies must be
    # walked for calls just like `def` bodies, or every call inside a test is
    # invisible to the call-graph passes (the caller is the enclosing module).
    _EXUNIT_BLOCK_KEYWORDS = frozenset({"test", "describe", "setup", "setup_all"})

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

    def _get_alias_as_name(node) -> str | None:
        """Local name bound by `alias Foo.Bar, as: Baz` ("Baz"), or None.

        The grammar puts the option in a trailing ``keywords`` child of the
        arguments: ``pair(keyword("as:"), alias)``.
        """
        for child in node.children:
            if child.type != "keywords":
                continue
            for pair in child.children:
                if pair.type != "pair":
                    continue
                key = pair.child_by_field_name("key")
                value = pair.child_by_field_name("value")
                if key is None or value is None:
                    # Fall back to positional children: keyword then alias.
                    kids = [c for c in pair.children if c.type in ("keyword", "alias")]
                    if len(kids) != 2:
                        continue
                    key, value = kids
                key_text = source[key.start_byte:key.end_byte].decode("utf-8", errors="replace")
                if key_text.strip().rstrip(":") == "as":
                    return source[value.start_byte:value.end_byte].decode("utf-8", errors="replace")
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
            add_node(module_nid, module_name, line)
            add_edge(file_nid, module_nid, "contains", line)
            if do_block_node:
                for child in do_block_node.children:
                    walk(child, parent_module_nid=module_nid)
            return

        if keyword in ("def", "defp"):
            func_name = None
            if arguments_node:
                for child in arguments_node.children:
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
            if parent_module_nid:
                add_edge(parent_module_nid, func_nid, "method", line)
            else:
                add_edge(file_nid, func_nid, "contains", line)
            if do_block_node:
                function_bodies.append((func_nid, do_block_node))
            return

        if keyword in _IMPORT_KEYWORDS and arguments_node:
            as_name = _get_alias_as_name(arguments_node) if keyword == "alias" else None
            for module_name in _get_alias_modules(arguments_node):
                tgt_nid = _make_id(module_name)
                add_edge(file_nid, tgt_nid, "imports", line, context="import")
                local = as_name or module_name.split(".")[-1]
                if local:
                    elixir_aliases.setdefault(local, module_name)
            return

        if keyword in _EXUNIT_BLOCK_KEYWORDS and do_block_node is not None:
            # `test`/`describe`/`setup` bodies are not `def`s, but the calls
            # inside them are the spec's link to the code under test. Walk them
            # with the enclosing module as the caller.
            function_bodies.append((parent_module_nid or file_nid, do_block_node))
            for child in node.children:
                walk(child, parent_module_nid)
            return

        for child in node.children:
            walk(child, parent_module_nid)

    walk(root)

    label_to_nid: dict[str, str] = {}
    for n in nodes:
        normalised = n["label"].strip("()").lstrip(".")
        label_to_nid[normalised] = n["id"]

    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []
    _SKIP_KEYWORDS = frozenset({
        "def", "defp", "defmodule", "defmacro", "defmacrop",
        "defstruct", "defprotocol", "defimpl", "defguard",
        "alias", "import", "require", "use",
        "if", "unless", "case", "cond", "with", "for",
    })

    def walk_calls(node, caller_nid: str) -> None:
        if node.type != "call":
            for child in node.children:
                walk_calls(child, caller_nid)
            return
        for child in node.children:
            if child.type == "identifier":
                kw = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                if kw in _SKIP_KEYWORDS:
                    for c in node.children:
                        walk_calls(c, caller_nid)
                    return
                break
        callee_name: str | None = None
        is_member_call: bool = False
        receiver: str | None = None
        for child in node.children:
            if child.type == "dot":
                is_member_call = True
                dot_text = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                parts = dot_text.rstrip(".").split(".")
                if parts:
                    callee_name = parts[-1]
                if len(parts) > 1:
                    recv = ".".join(parts[:-1])
                    # Elixir module names always start uppercase; a lowercase
                    # receiver is a variable (`ch.id`), not a remote module
                    # call, so only module-shaped receivers are recorded.
                    if recv[:1].isupper():
                        receiver = recv
                break
            if child.type == "identifier":
                callee_name = source[child.start_byte:child.end_byte].decode("utf-8", errors="replace")
                break
        if callee_name and callee_name not in _LANGUAGE_BUILTIN_GLOBALS:
            tgt_nid = label_to_nid.get(callee_name)
            if tgt_nid and tgt_nid != caller_nid:
                pair = (caller_nid, tgt_nid)
                if pair not in seen_call_pairs:
                    seen_call_pairs.add(pair)
                    add_edge(caller_nid, tgt_nid, "calls",
                             node.start_point[0] + 1, confidence="EXTRACTED", weight=1.0,
                             context="call")
            else:
                rc = {
                    "caller_nid": caller_nid,
                    "callee": callee_name,
                    "is_member_call": is_member_call,
                    "lang": "elixir",
                    "source_file": str_path,
                    "source_location": f"L{node.start_point[0] + 1}",
                }
                if receiver:
                    rc["receiver"] = receiver
                raw_calls.append(rc)
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body in function_bodies:
        walk_calls(body, caller_nid)

    # Nested ExUnit blocks (describe > test) are walked once per enclosing
    # block, so the same call can be recorded more than once. Dedup on
    # (caller, callee, receiver, location) — the tuple fully determines the
    # edge a resolver would emit.
    seen_rc: set[tuple] = set()
    deduped_raw_calls: list[dict] = []
    for rc in raw_calls:
        key = (rc["caller_nid"], rc["callee"], rc.get("receiver"), rc["source_location"])
        if key in seen_rc:
            continue
        seen_rc.add(key)
        deduped_raw_calls.append(rc)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] == "imports")]
    result = {"nodes": nodes, "edges": clean_edges, "raw_calls": deduped_raw_calls, "input_tokens": 0, "output_tokens": 0}
    if elixir_aliases:
        result["elixir_aliases"] = elixir_aliases
    return result
