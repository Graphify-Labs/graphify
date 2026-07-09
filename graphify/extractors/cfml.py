"""CFML (ColdFusion) extractor for .cfc/.cfm/.cfs files, using tree-sitter-cfml."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id, _read_text
from graphify.extractors.resolution import _cfml_resolve_component

# Common CFML built-in functions, filtered out of cross-file call resolution so
# they don't accumulate into god-nodes (mirrors _LANGUAGE_BUILTIN_GLOBALS, #726).
_CFML_BUILTINS = frozenset({
    "writeoutput", "writedump", "writelog", "structnew", "structkeyexists",
    "structdelete", "structcount", "structcopy", "structinsert", "structget",
    "structeach", "structsort", "structappend", "structisempty", "structkeylist",
    "structkeyarray", "structkeytranslate",
    "arraynew", "arraylen", "arrayappend", "arrayinsertat", "arraydeleteat",
    "arrayslice", "arraysort", "arrayfilter", "arraymap", "arrayeach",
    "arraytolist", "arraycontains", "arrayfind",
    "listappend", "listtoarray", "listlen", "listgetat", "listfind",
    "listcontains", "listfirst", "listlast", "listrest", "listsort",
    "querynew", "queryexecute", "queryaddrow", "querysetcell",
    "isdefined", "isnull", "isarray", "isstruct", "isquery", "isjson",
    "issimplevalue", "isnumeric", "isboolean", "isdate", "isvalid",
    "iscustomfunction", "isobject", "variablesexists",
    "len", "trim", "ltrim", "rtrim", "ucase", "lcase", "left", "right",
    "mid", "replace", "replacenocase", "find", "findnocase", "refind",
    "refindnocase", "rereplace", "rereplacenocase", "reversestring",
    "dateformat", "timeformat", "now", "createdate", "createdatetime",
    "createtime", "createodbcdate", "createodbcdatetime", "dateadd",
    "datediff", "datecompare", "day", "month", "year", "hour", "minute",
    "second", "dayofweek",
    "serializejson", "deserializejson", "encodeforhtml", "encodeforhtmlattribute",
    "encodeforjavascript", "encodeforurl", "encodeforxml", "htmleditformat",
    "htmlcodeformat", "urlencodedformat", "duplicate", "tostring", "tobinary",
    "tobase64", "tonumeric",
    "val", "int", "abs", "round", "min", "max", "randrange", "rand",
    "createuuid", "createguid", "throw", "rethrow", "abort", "location",
    "getfunctionlist", "getmetadata", "gettemplatepath", "getbasetagdata",
    "expandpath", "fileexists", "directoryexists", "fileread", "filewrite",
    "fileopen", "fileclose", "directorylist", "directorycreate",
    "javacast", "precisionevaluate",
})


def _tag_name(node, source: bytes) -> str:
    """Recover a CF tag's lowercase keyword ('function', 'set', 'property', ...).

    The paired forms (cf_tag/cf_start_tag/cf_end_tag) expose it as a real
    cf_tag_name child, but the generic self-closing form (cf_selfclose_tag --
    shared by cfproperty/cfargument/cfinclude/cfimport/... alike) has its
    keyword consumed by the external scanner without emitting any node for it,
    so it's recovered here from the node's own raw text instead.
    """
    for child in node.children:
        if child.type == "cf_tag_name":
            return _read_text(child, source).lower()
    m = re.match(r"</?cf([a-zA-Z][a-zA-Z0-9_]*)", _read_text(node, source))
    return m.group(1).lower() if m else ""


def _iter_tag_attributes(tag_node):
    """Yield a tag's cf_attribute children, whether bare or cf_tag_attributes-wrapped."""
    for child in tag_node.children:
        if child.type == "cf_attribute":
            yield child
        elif child.type == "cf_tag_attributes":
            for gc in child.children:
                if gc.type == "cf_attribute":
                    yield gc


def _tag_attr(tag_node, name: str, source: bytes) -> str | None:
    """Static string value of a tag attribute, or None if absent/dynamic (#hash#)."""
    for attr in _iter_tag_attributes(tag_node):
        name_node = next((c for c in attr.children if c.type == "cf_attribute_name"), None)
        if name_node is None or _read_text(name_node, source).lower() != name:
            continue
        for value_holder in attr.children:
            if value_holder.type in ("quoted_cf_attribute_value", "cf_attribute_value"):
                value_node = next(
                    (c for c in value_holder.children if c.type == "attribute_value"), None
                )
                return _read_text(value_node, source) if value_node is not None else None
        return None
    return None


def _script_attr(node, name: str, source: bytes) -> str | None:
    """Static string value of a cfscript component_attribute (extends=..., name=...)."""
    for child in node.children:
        if child.type != "component_attribute":
            continue
        ident = next((c for c in child.children if c.type == "identifier"), None)
        if ident is None or _read_text(ident, source).lower() != name:
            continue
        string_node = next((c for c in child.children if c.type == "string"), None)
        return _string_fragment(string_node, source) if string_node is not None else None
    return None


def _string_fragment(string_node, source: bytes) -> str | None:
    frag = next((c for c in string_node.children if c.type == "string_fragment"), None)
    return _read_text(frag, source) if frag is not None else None


def extract_cfml(path: Path) -> dict:
    """Extract components, functions, properties, includes, and calls from CFML.

    Handles .cfc/.cfm (both tag- and script-syntax) and .cfs (pure CFScript),
    using the tree-sitter-cfml grammars: ``cfml`` for tag-based markup,
    ``cfscript`` for script-style component bodies (the cfml grammar treats a
    top-level ``component { ... }``/``interface { ... }`` block as opaque,
    unparsed content, so script-style .cfc files are re-parsed with the
    cfscript grammar instead). A ``<cfscript>`` block embedded in an otherwise
    tag-based file is likewise re-parsed with the cfscript grammar and merged
    in, with line numbers offset to the enclosing file.

    Produces nodes for:
    - the file itself (doubling as the component/interface definition)
    - cffunction tags / cfscript function declarations
    - cfproperty tags / cfscript property declarations

    Produces edges for:
    - file --inherits--> base component (extends=, resolved by dotted path)
    - file --implements--> interface (implements=, comma-separated)
    - file --contains--> function / property
    - file --imports--> cfinclude template (resolved relative to this file) /
      cfimport taglib (stub -- not a resolvable single file)
    - function --instantiates--> component (new Foo()/createObject("component", "Foo"))
    - function --calls--> other function (same-file; cross-file via raw_calls)

    Member calls (obj.method()) are not resolved -- CFML has no static typing
    to infer a receiver's component from, so guessing would produce wrong
    cross-file edges; they're silently skipped like every other bespoke
    extractor without receiver-type inference.
    """
    try:
        import tree_sitter_cfml as ts_cfml
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree-sitter-cfml not installed"}

    try:
        source = path.read_bytes()
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    cfml_parser = Parser(Language(ts_cfml.language_cfml()))
    script_parser = Parser(Language(ts_cfml.language_cfscript()))

    try:
        if path.suffix.lower() == ".cfs":
            root = script_parser.parse(source).root_node
        else:
            root = cfml_parser.parse(source).root_node
            if root.child_count == 1 and root.children[0].type == "component_file":
                # Top-level `component { ... }` / `interface { ... }` script
                # syntax: the cfml (tag) grammar treats this as an opaque blob.
                root = script_parser.parse(source).root_node
    except Exception as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    raw_calls: list[dict] = []
    seen_ids: set[str] = {file_nid}
    seen_edges: set[tuple[str, str, str]] = set()
    seen_call_pairs: set[tuple[str, str]] = set()
    local_functions: dict[str, str] = {}  # lowercase name -> fn_nid, same-file calls
    call_sites: list = []  # (node, source, caller_nid, line), resolved after decls

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}"})

    def add_edge(src: str, tgt: str, relation: str, line: int, context: str | None = None) -> None:
        key = (src, tgt, relation)
        if key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict = {"source": src, "target": tgt, "relation": relation,
                      "confidence": "EXTRACTED", "source_file": str_path,
                      "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    def link_component(src_nid: str, dotted_name: str, relation: str, line: int,
                        resolve: bool = True) -> None:
        tgt_nid = (_cfml_resolve_component(path, dotted_name) if resolve else None)
        if tgt_nid is None:
            tgt_nid = _make_id(dotted_name)
            if tgt_nid != src_nid:
                add_node(tgt_nid, dotted_name, line)
        if tgt_nid != src_nid:
            add_edge(src_nid, tgt_nid, relation, line)

    def link_file(src_nid: str, raw_path: str, relation: str, line: int) -> None:
        # cfinclude target: a plain relative file path, not a dotted component
        # name -- resolved relative to this file's own directory.
        candidate = (path.parent / raw_path)
        tgt_nid = _make_id(str(candidate.resolve())) if candidate.is_file() else _make_id(raw_path)
        if tgt_nid != src_nid:
            add_node(tgt_nid, raw_path, line)
            add_edge(src_nid, tgt_nid, relation, line)

    def add_instantiation(caller_nid: str, dotted_name: str, line: int) -> None:
        tgt_nid = _cfml_resolve_component(path, dotted_name) or _make_id(dotted_name)
        if tgt_nid == caller_nid:
            return
        add_node(tgt_nid, dotted_name, line)
        pair = (caller_nid, tgt_nid)
        if pair in seen_call_pairs:
            return
        seen_call_pairs.add(pair)
        add_edge(caller_nid, tgt_nid, "instantiates", line, context="call")

    def handle_call_like(node, source: bytes, caller_nid: str, line: int) -> None:
        if node.type == "new_expression":
            target_node = next(
                (c for c in node.children if c.is_named and c.type != "arguments"), None
            )
            if target_node is not None:
                dotted = _read_text(target_node, source)
                if dotted:
                    add_instantiation(caller_nid, dotted, line)
            return

        if not node.children:
            return
        callee_node = node.children[0]
        if callee_node.type == "member_expression":
            return  # no receiver-type inference for CFML -- skip rather than guess
        if callee_node.type != "identifier":
            return
        callee = _read_text(callee_node, source)
        if not callee:
            return
        if callee.lower() == "createobject":
            args_node = next((c for c in node.children if c.type == "arguments"), None)
            str_args = [c for c in args_node.children if c.type == "string"] if args_node else []
            if len(str_args) >= 2:
                kind = _string_fragment(str_args[0], source)
                dotted = _string_fragment(str_args[1], source)
                if kind and kind.lower() == "component" and dotted:
                    add_instantiation(caller_nid, dotted, line)
            return
        if callee.lower() in _CFML_BUILTINS:
            return
        local_target = local_functions.get(callee.lower())
        if local_target:
            if local_target == caller_nid:
                return
            pair = (caller_nid, local_target)
            if pair not in seen_call_pairs:
                seen_call_pairs.add(pair)
                add_edge(caller_nid, local_target, "calls", line, context="call")
            return
        raw_calls.append({"source_file": str_path, "source_location": f"L{line}",
                          "caller_nid": caller_nid, "callee": callee})

    def walk(node, source: bytes, caller_nid: str, line_offset: int) -> None:
        # `source` is the byte buffer node's own offsets are relative to -- the
        # full file for the primary tree, or the extracted <cfscript> snippet
        # for a nested reparse (see the cf_script_tag branch below). Using the
        # wrong buffer silently reads garbage text at the right line number.
        t = node.type
        line = node.start_point[0] + line_offset + 1

        if t == "cf_component_open_tag" or t == "component":
            get_attr = _tag_attr if t == "cf_component_open_tag" else _script_attr
            extends = get_attr(node, "extends", source)
            implements = get_attr(node, "implements", source)
            if extends:
                link_component(file_nid, extends, "inherits", line)
            if implements:
                for iface in re.split(r"\s*,\s*", implements.strip()):
                    if iface:
                        link_component(file_nid, iface, "implements", line)

        elif t == "cf_function_tag":
            name = _tag_attr(node, "name", source)
            if name:
                fn_nid = _make_id(stem, name)
                add_node(fn_nid, f"{name}()", line)
                add_edge(file_nid, fn_nid, "contains", line)
                local_functions[name.lower()] = fn_nid
                caller_nid = fn_nid
        elif t == "function_declaration":
            name_node = next((c for c in node.children if c.type == "identifier"), None)
            if name_node is not None:
                name = _read_text(name_node, source)
                fn_nid = _make_id(stem, name)
                add_node(fn_nid, f"{name}()", line)
                add_edge(file_nid, fn_nid, "contains", line)
                local_functions[name.lower()] = fn_nid
                caller_nid = fn_nid

        elif t == "cf_selfclose_tag":
            kw = _tag_name(node, source)
            if kw == "property":
                name = _tag_attr(node, "name", source)
                if name:
                    prop_nid = _make_id(stem, name)
                    add_node(prop_nid, name, line)
                    add_edge(file_nid, prop_nid, "contains", line)
            elif kw == "include":
                template = _tag_attr(node, "template", source)
                if template:
                    link_file(file_nid, template, "imports", line)
            elif kw == "import":
                taglib = _tag_attr(node, "taglib", source)
                if taglib:
                    link_component(file_nid, taglib, "imports", line, resolve=False)
        elif t == "property_declaration":
            name = _script_attr(node, "name", source)
            if name:
                prop_nid = _make_id(stem, name)
                add_node(prop_nid, name, line)
                add_edge(file_nid, prop_nid, "contains", line)

        elif t == "cf_script_tag":
            content = next((c for c in node.children if c.type == "cf_script_content"), None)
            if content is not None and content.end_byte > content.start_byte:
                snippet = source[content.start_byte:content.end_byte]
                sub_root = script_parser.parse(snippet).root_node
                walk(sub_root, snippet, caller_nid, line_offset + content.start_point[0])
            return  # cf_script_content has no children of its own to recurse into

        elif t in ("call_expression", "new_expression"):
            # Deferred to a second pass (below) so a call to a function
            # declared LATER in the same file still resolves via
            # local_functions instead of falling through to raw_calls.
            call_sites.append((node, source, caller_nid, line))

        for child in node.children:
            walk(child, source, caller_nid, line_offset)

    walk(root, source, file_nid, 0)
    for node, node_source, caller_nid, line in call_sites:
        handle_call_like(node, node_source, caller_nid, line)

    return {"nodes": nodes, "edges": edges, "raw_calls": raw_calls}
