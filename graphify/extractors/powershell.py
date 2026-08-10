"""Powershell extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from typing import Any
from graphify.extractors.base import _file_stem, _make_id, _read_text


def extract_powershell(path: Path) -> dict:
    """Extract functions, classes, methods, and using statements from a .ps1 file."""
    try:
        import tree_sitter_powershell as tsps
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_powershell not installed"}

    try:
        language = Language(tsps.language())
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

    _PS_SKIP = frozenset({
        "using", "return", "if", "else", "elseif", "foreach", "for",
        "while", "do", "switch", "try", "catch", "finally", "throw",
        "break", "continue", "exit", "param", "begin", "process", "end",
        # Import commands — handled as import edges, not function calls
        "import-module",
    })

    def _find_script_block_body(node):
        for child in node.children:
            if child.type == "script_block":
                for sc in child.children:
                    if sc.type == "script_block_body":
                        return sc
                return child
        return None

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

    def _ps_type_name(type_literal_node) -> str | None:
        """Drill into a type_literal node and return the inner type_identifier text."""
        if type_literal_node is None:
            return None
        for spec in type_literal_node.children:
            if spec.type != "type_spec":
                continue
            for tname in spec.children:
                if tname.type != "type_name":
                    continue
                for tid in tname.children:
                    if tid.type == "type_identifier":
                        return _read_text(tid, source)
        return None

    def walk(node, parent_class_nid: str | None = None) -> None:
        t = node.type

        if t == "function_statement":
            name_node = next((c for c in node.children if c.type == "function_name"), None)
            if name_node:
                func_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                func_nid = _make_id(stem, func_name)
                add_node(func_nid, f"{func_name}()", line)
                add_edge(file_nid, func_nid, "contains", line)
                body = _find_script_block_body(node)
                if body:
                    function_bodies.append((func_nid, body))
                    # Also walk the body during the main pass so that
                    # Import-Module / dot-source inside functions emit
                    # file-level imports_from edges (#1331).
                    walk(body, parent_class_nid)
            return

        if t == "class_statement":
            name_node = next((c for c in node.children if c.type == "simple_name"), None)
            if name_node:
                class_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                class_nid = _make_id(stem, class_name)
                add_node(class_nid, class_name, line)
                add_edge(file_nid, class_nid, "contains", line)
                # Base type(s) after ':'. PowerShell has no syntactic base vs
                # interface split, so (matching the C# convention) treat the
                # first base as the superclass (inherits) and the rest as
                # interfaces (implements). Bases are the simple_name children
                # after the ':' token.
                colon_seen = False
                base_index = 0
                for child in node.children:
                    if child.type == ":":
                        colon_seen = True
                    elif colon_seen and child.type == "simple_name":
                        base_nid = ensure_named_node(_read_text(child, source), line)
                        if base_nid != class_nid:
                            rel = "inherits" if base_index == 0 else "implements"
                            add_edge(class_nid, base_nid, rel, line)
                        base_index += 1
                for child in node.children:
                    walk(child, parent_class_nid=class_nid)
            return

        if t == "class_property_definition" and parent_class_nid:
            type_literal = next((c for c in node.children if c.type == "type_literal"), None)
            type_name = _ps_type_name(type_literal)
            if type_name:
                line = node.start_point[0] + 1
                target_nid = ensure_named_node(type_name, line)
                if target_nid != parent_class_nid:
                    add_edge(parent_class_nid, target_nid, "references",
                             line, context="field")
            return

        if t == "class_method_definition":
            name_node = next((c for c in node.children if c.type == "simple_name"), None)
            if name_node:
                method_name = _read_text(name_node, source)
                line = node.start_point[0] + 1
                if parent_class_nid:
                    method_nid = _make_id(parent_class_nid, method_name)
                    add_node(method_nid, f".{method_name}()", line)
                    add_edge(parent_class_nid, method_nid, "method", line)
                else:
                    method_nid = _make_id(stem, method_name)
                    add_node(method_nid, f"{method_name}()", line)
                    add_edge(file_nid, method_nid, "contains", line)
                # Return type: type_literal sibling of simple_name
                return_type_literal = next(
                    (c for c in node.children if c.type == "type_literal"), None)
                return_type_name = _ps_type_name(return_type_literal)
                if return_type_name:
                    target_nid = ensure_named_node(return_type_name, line)
                    if target_nid != method_nid:
                        add_edge(method_nid, target_nid, "references",
                                 line, context="return_type")
                # Parameter types: class_method_parameter_list
                param_list = next(
                    (c for c in node.children if c.type == "class_method_parameter_list"), None)
                if param_list is not None:
                    for p in param_list.children:
                        if p.type != "class_method_parameter":
                            continue
                        ptype_literal = next(
                            (c for c in p.children if c.type == "type_literal"), None)
                        ptype_name = _ps_type_name(ptype_literal)
                        if not ptype_name:
                            continue
                        p_line = p.start_point[0] + 1
                        target_nid = ensure_named_node(ptype_name, p_line)
                        if target_nid != method_nid:
                            add_edge(method_nid, target_nid, "references",
                                     p_line, context="parameter_type")
                body = _find_script_block_body(node)
                if body:
                    function_bodies.append((method_nid, body))
            return

        if t == "command":
            # Dot-sourcing: `. ./Shared.psm1`
            # Uses command_invokation_operator '.' + command_name_expr (not command_name)
            invoke_op = next(
                (c for c in node.children if c.type == "command_invokation_operator"), None
            )
            if invoke_op is not None and _read_text(invoke_op, source).strip() == ".":
                name_expr = next(
                    (c for c in node.children if c.type == "command_name_expr"), None
                )
                if name_expr is not None:
                    name_node = next(
                        (c for c in name_expr.children if c.type == "command_name"), None
                    )
                    if name_node:
                        raw_path = _read_text(name_node, source)
                        # Strip relative path prefix (./ or .\ or just the dot)
                        module_stem = re.sub(r'^[./\\]+', '', raw_path)
                        # Drop extension to get bare module name
                        module_stem = re.sub(r'\.[^.]+$', '', module_stem).replace('\\', '/')
                        module_name = module_stem.split('/')[-1]
                        if module_name:
                            add_edge(file_nid, _make_id(module_name), "imports_from",
                                     node.start_point[0] + 1)
                return

            cmd_name_node = next((c for c in node.children if c.type == "command_name"), None)
            if cmd_name_node:
                cmd_text = _read_text(cmd_name_node, source).lower()
                if cmd_text == "using":
                    tokens = []
                    for child in node.children:
                        if child.type == "command_elements":
                            for el in child.children:
                                if el.type == "generic_token":
                                    tokens.append(_read_text(el, source))
                    module_tokens = [t for t in tokens
                                     if t.lower() not in ("namespace", "module", "assembly")]
                    if module_tokens:
                        module_name = module_tokens[-1].split(".")[-1]
                        add_edge(file_nid, _make_id(module_name), "imports_from",
                                 node.start_point[0] + 1)
                elif cmd_text == "import-module":
                    # Collect generic_token args; skip command_parameter flags like -Name
                    # The module name is the first generic_token (or the one after -Name)
                    module_name: str | None = None
                    expect_name = False
                    for child in node.children:
                        if child.type != "command_elements":
                            continue
                        for el in child.children:
                            if el.type == "command_parameter":
                                param_text = _read_text(el, source).lstrip("-").lower()
                                expect_name = param_text in ("name", "n")
                            elif el.type == "generic_token":
                                token = _read_text(el, source)
                                if module_name is None or expect_name:
                                    module_name = token
                                    expect_name = False
                    if module_name:
                        # Strip extension; keep only the stem for the node ID
                        bare = re.sub(r'\.[^.]+$', '', module_name).split('/')[-1].split('\\')[-1]
                        if bare:
                            add_edge(file_nid, _make_id(bare), "imports_from",
                                     node.start_point[0] + 1)
            return

        for child in node.children:
            walk(child, parent_class_nid)

    walk(root)

    label_to_nid = {n["label"].strip("()").lstrip(".").lower(): n["id"] for n in nodes}
    seen_call_pairs: set[tuple[str, str]] = set()
    raw_calls: list[dict] = []

    def walk_calls(node, caller_nid: str) -> None:
        if node.type in ("function_statement", "class_statement"):
            return
        if node.type == "command":
            cmd_name_node = next((c for c in node.children if c.type == "command_name"), None)
            if cmd_name_node:
                cmd_text = _read_text(cmd_name_node, source)
                if cmd_text.lower() not in _PS_SKIP:
                    tgt_nid = label_to_nid.get(cmd_text.lower())
                    if tgt_nid and tgt_nid != caller_nid:
                        pair = (caller_nid, tgt_nid)
                        if pair not in seen_call_pairs:
                            seen_call_pairs.add(pair)
                            add_edge(caller_nid, tgt_nid, "calls",
                                     node.start_point[0] + 1,
                                     confidence="EXTRACTED", weight=1.0)
                    elif cmd_text:
                        raw_calls.append({
                            "caller_nid": caller_nid,
                            "callee": cmd_text,
                            "is_member_call": False,
                            "source_file": str_path,
                            "source_location": f"L{node.start_point[0] + 1}",
                        })
        for child in node.children:
            walk_calls(child, caller_nid)

    for caller_nid, body_node in function_bodies:
        walk_calls(body_node, caller_nid)

    clean_edges = [e for e in edges if e["source"] in seen_ids and
                   (e["target"] in seen_ids or e["relation"] in ("imports_from", "imports"))]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}

_PSD1_IMPORT_KEYS = frozenset({"RootModule", "NestedModules", "RequiredModules"})

def _psd1_collect_string_literals(node, source: bytes) -> list[str]:
    """Recursively collect all string_literal text values under *node*."""
    results: list[str] = []

    def _walk(n) -> None:
        if n.type == "string_literal":
            raw = source[n.start_byte:n.end_byte].decode(errors="replace")
            # Strip surrounding quote chars (' or ")
            results.append(raw.strip("'\""))
            return
        for child in n.children:
            _walk(child)

    _walk(node)
    return results

def _psd1_module_name(raw: str) -> str:
    """Derive a bare module name from a raw string value.

    e.g. 'MyModule.psm1' → 'MyModule', './sub/Util.psm1' → 'Util', 'PSReadLine' → 'PSReadLine'
    """
    # Strip path prefix and extension
    name = raw.replace("\\", "/").split("/")[-1]
    name = re.sub(r"\.[^.]+$", "", name)  # remove last extension
    return name.strip()

def extract_powershell_manifest(path: Path) -> dict:
    """Extract module dependency edges from a PowerShell .psd1 manifest file.

    .psd1 files are PowerShell data hashtables, not scripts. tree-sitter-powershell
    parses them correctly (they are syntactically valid PS). We walk the AST looking
    for RootModule, NestedModules, and RequiredModules keys and emit imports_from
    edges for every referenced module.

    RequiredModules supports two forms:
      - Simple string: 'PSReadLine'
      - Module specification: @{ ModuleName = 'Pester'; ModuleVersion = '5.0' }
    For the hashtable form we only follow the ModuleName key.
    """
    try:
        import tree_sitter_powershell as tsps
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_powershell not installed"}

    try:
        language = Language(tsps.language())
        parser = Parser(language)
        source = path.read_bytes()
        tree = parser.parse(source)
        root = tree.root_node
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_import_edge(src: str, module_raw: str, line: int) -> None:
        name = _psd1_module_name(module_raw)
        if not name:
            return
        tgt_nid = _make_id(name)
        edges.append({
            "source": src,
            "target": tgt_nid,
            "relation": "imports_from",
            "confidence": "EXTRACTED",
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
            "context": "import",
        })

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk_manifest(node) -> None:
        """Walk the AST and emit edges for import-relevant hash_entry nodes."""
        if node.type != "hash_entry":
            for child in node.children:
                walk_manifest(child)
            return

        # Identify the key
        key_node = next((c for c in node.children if c.type == "key_expression"), None)
        if key_node is None:
            return
        key_text = source[key_node.start_byte:key_node.end_byte].decode(errors="replace").strip()

        if key_text not in _PSD1_IMPORT_KEYS:
            # Still recurse in case there are nested hashes (e.g. ModuleVersion entries
            # contain sub-hashes, but we only care about top-level keys for imports)
            return

        line = node.start_point[0] + 1
        value_node = next((c for c in node.children if c.type == "pipeline"), None)
        if value_node is None:
            return

        if key_text == "RootModule":
            # Value is a single string
            strings = _psd1_collect_string_literals(value_node, source)
            for s in strings:
                add_import_edge(file_nid, s, line)

        elif key_text == "NestedModules":
            # Value is a string or @('a', 'b', ...) array — collect all string literals
            strings = _psd1_collect_string_literals(value_node, source)
            for s in strings:
                add_import_edge(file_nid, s, line)

        elif key_text == "RequiredModules":
            # Two forms:
            # 1) 'SimpleModule' — direct string literals in the array
            # 2) @{ ModuleName = 'Foo'; ModuleVersion = '2.0' } — use ModuleName only
            #
            # Strategy: walk the value for hash_entry nodes whose key is 'ModuleName';
            # collect their string values. For the remaining string_literal nodes that
            # are NOT inside a hash_entry subtree, treat them as simple module names.
            module_name_strings: list[str] = []
            inside_hash_entries: set[int] = set()  # byte offsets of handled strings

            def find_modulename_entries(n) -> None:
                if n.type == "hash_entry":
                    sub_key = next((c for c in n.children if c.type == "key_expression"), None)
                    if sub_key is not None:
                        sk_text = source[sub_key.start_byte:sub_key.end_byte].decode(errors="replace").strip()
                        # Collect strings inside *all* sub-keys so we can exclude them
                        for c in n.children:
                            if c.type == "pipeline":
                                for s_node in _collect_string_nodes(c):
                                    inside_hash_entries.add(s_node.start_byte)
                        if sk_text == "ModuleName":
                            for c in n.children:
                                if c.type == "pipeline":
                                    for s in _psd1_collect_string_literals(c, source):
                                        module_name_strings.append(s)
                    return  # don't recurse further into this hash_entry
                for child in n.children:
                    find_modulename_entries(child)

            def _collect_string_nodes(n):
                """Return all string_literal nodes in subtree."""
                if n.type == "string_literal":
                    yield n
                    return
                for child in n.children:
                    yield from _collect_string_nodes(child)

            find_modulename_entries(value_node)

            # Now gather direct string literals not inside hash entries
            direct_strings: list[str] = []
            for s_node in _collect_string_nodes(value_node):
                if s_node.start_byte not in inside_hash_entries:
                    raw = source[s_node.start_byte:s_node.end_byte].decode(errors="replace")
                    direct_strings.append(raw.strip("'\""))

            for s in direct_strings + module_name_strings:
                add_import_edge(file_nid, s, line)

    walk_manifest(root)

    return {"nodes": nodes, "edges": edges, "raw_calls": []}
