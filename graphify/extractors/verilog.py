"""Verilog extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id, _read_text


def _sv_first_identifier(node, source: bytes) -> str | None:
    """First `simple_identifier` under node in pre-order, or None.

    tree-sitter-verilog 1.0.3 nests declaration names a few levels deep instead
    of exposing a `name` field. Scope the search to the right child node (e.g.
    `function_identifier`) or this returns the return-type instead of the name.
    """
    if node is None:
        return None
    for child in node.children:
        if child.type == "simple_identifier":
            return _read_text(child, source)
        found = _sv_first_identifier(child, source)
        if found:
            return found
    return None

def _sv_child(node, type_name: str) -> object | None:
    if node is None:
        return None
    for child in node.children:
        if child.type == type_name:
            return child
    return None

_SV_BUILTIN_TYPES = frozenset({
    "bit", "logic", "reg", "wire", "int", "integer", "shortint", "longint",
    "byte", "time", "real", "shortreal", "void", "string", "type", "event",
    "mailbox", "semaphore", "process", "chandle",
})

_SV_NON_TYPE_WORDS = frozenset({
    "return", "if", "else", "for", "foreach", "while", "case", "begin", "end",
    "function", "task", "class", "endclass", "endfunction", "endtask",
})

_SV_PARENS_INNER = r"(?:[^()]|\([^()]*\))*"

_SV_PARENS = r"\(" + _SV_PARENS_INNER + r"\)"

_SV_FUNC_RE = re.compile(
    r"\bfunction\s+([A-Za-z_]\w*(?:\s*#\s*" + _SV_PARENS + r")?)\s+(\w+)\s*"
    r"\((" + _SV_PARENS_INNER + r")\)\s*;",
    re.MULTILINE,
)

_SV_PARAM_RE = re.compile(
    r"\s*(?:input|output|inout|ref|const\s+ref)?\s*"
    r"([A-Za-z_]\w*(?:\s*#\s*" + _SV_PARENS + r")?)\s+\w+"
)

def _sv_strip_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//.*", "", text)

def _sv_split_type_list(text: str) -> list[str]:
    parts: list[str] = []
    depth = 0
    start = 0
    for idx, ch in enumerate(text):
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(0, depth - 1)
        elif ch == "," and depth == 0:
            item = text[start:idx].strip()
            if item:
                parts.append(item)
            start = idx + 1
    item = text[start:].strip()
    if item:
        parts.append(item)
    return parts

def _sv_collect_type_refs(type_text: str, generic: bool = False,
                          skip: frozenset[str] = frozenset()) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    text = type_text.strip()
    if not text:
        return refs
    head = re.match(r"([A-Za-z_]\w*)", text)
    if head:
        name = head.group(1)
        # `skip` carries the enclosing class's `#(type T = ...)` parameters so
        # they are not mistaken for referenced types.
        if name not in _SV_BUILTIN_TYPES and name not in _SV_NON_TYPE_WORDS and name not in skip:
            refs.append((name, "generic_arg" if generic else "type"))
    params = re.search(r"#\s*\((" + _SV_PARENS_INNER + r")\)", text)
    if params:
        for arg in _sv_split_type_list(params.group(1)):
            refs.extend(_sv_collect_type_refs(arg, generic=True, skip=skip))
    return refs

def _augment_systemverilog_semantics(
    raw: str,
    stem: str,
    str_path: str,
    file_nid: str,
    nodes: list[dict],
    edges: list[dict],
    seen_ids: set[str],
) -> None:
    label_to_nid = {node["label"]: node["id"] for node in nodes}

    def line_for(offset: int) -> int:
        return raw.count("\n", 0, offset) + 1

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}",
                          "confidence_score": 1.0})
        label_to_nid[label] = nid

    def ensure_type(label: str, line: int) -> str:
        if label in label_to_nid:
            return label_to_nid[label]
        nid = _make_id(stem, label)
        add_node(nid, label, line)
        return nid

    def add_edge(src: str, target_label: str, relation: str, line: int, context: str | None = None) -> None:
        tgt = ensure_type(target_label, line)
        edge = {"source": src, "target": tgt, "relation": relation,
                "confidence": "EXTRACTED", "confidence_score": 1.0,
                "source_file": str_path, "source_location": f"L{line}", "weight": 1.0}
        if context:
            edge["context"] = context
        edges.append(edge)

    text = _sv_strip_comments(raw)
    # Consuming `endclass` (rather than a lookahead) makes each match own its
    # terminator, so back-to-back or malformed classes cannot bleed bodies.
    class_re = re.compile(
        r"\b(?:(interface)\s+)?class\s+(\w+)([^;{]*)\s*;(.*?)\bendclass\b",
        re.DOTALL,
    )
    for match in class_re.finditer(text):
        class_name = match.group(2)
        header = match.group(3) or ""
        body = match.group(4) or ""
        line = line_for(match.start())
        # `#(type T = Payload)` declares `T` as a class type parameter, not a
        # referenced type — collect these to skip below.
        type_params = frozenset(re.findall(r"\btype\s+(\w+)", header))
        class_nid = _make_id(stem, class_name)
        add_node(class_nid, class_name, line)
        edges.append({"source": file_nid, "target": class_nid, "relation": "defines",
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str_path, "source_location": f"L{line}", "weight": 1.0})

        ext = re.search(r"\bextends\s+(\w+)", header)
        if ext:
            add_edge(class_nid, ext.group(1), "inherits", line)
        impl = re.search(r"\bimplements\s+([^;{]+)", header)
        if impl:
            for iface_name in _sv_split_type_list(impl.group(1)):
                add_edge(class_nid, iface_name.split("#", 1)[0].strip(), "implements", line)

        body_without_functions = re.sub(
            r"\bfunction\b.*?\bendfunction\b",
            lambda m: "\n" * m.group(0).count("\n"),
            body,
            flags=re.DOTALL,
        )
        # Optional leading class-property qualifiers (rand/local/protected/etc.)
        # must be consumed: otherwise a qualified field like `rand Config x;`
        # (three tokens) fails the `<type> <name>;` shape and its type reference
        # is silently dropped.
        for field in re.finditer(r"^\s*(?:(?:rand|randc|local|protected|static|const|automatic|var)\s+)*([A-Za-z_]\w*(?:\s*#\s*\([^;]+?\))?)\s+\w+\s*;", body_without_functions, re.MULTILINE):
            # Count to the start of the type token (group 1), not the match
            # start: `^\s*` consumes the leading newline(s), so field.start()
            # would resolve to the class's line instead of the field's.
            field_line = line + body_without_functions.count("\n", 0, field.start(1))
            for ref_name, role in _sv_collect_type_refs(field.group(1), skip=type_params):
                add_edge(class_nid, ref_name, "references", field_line, "generic_arg" if role == "generic_arg" else "field")

        for fm in _SV_FUNC_RE.finditer(body):
            return_type, func_name, params = fm.group(1), fm.group(2), fm.group(3)
            func_line = line + body.count("\n", 0, fm.start())
            func_nid = _make_id(class_nid, func_name)
            add_node(func_nid, func_name, func_line)
            edges.append({"source": class_nid, "target": func_nid, "relation": "method",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": str_path, "source_location": f"L{func_line}", "weight": 1.0})
            for ref_name, role in _sv_collect_type_refs(return_type, skip=type_params):
                add_edge(func_nid, ref_name, "references", func_line, "generic_arg" if role == "generic_arg" else "return_type")
            for param in _sv_split_type_list(params):
                pm = _SV_PARAM_RE.match(param)
                if not pm:
                    continue
                for ref_name, role in _sv_collect_type_refs(pm.group(1), skip=type_params):
                    add_edge(func_nid, ref_name, "references", func_line, "generic_arg" if role == "generic_arg" else "parameter_type")

def extract_verilog(path: Path) -> dict:
    """Extract modules, functions, tasks, package imports, instantiations, and
    SystemVerilog class semantics (inherits/implements edges, field/parameter/
    return-type references) from .v/.sv files."""
    try:
        import tree_sitter_verilog as tsverilog
        from tree_sitter import Language, Parser
    except ImportError:
        return {"nodes": [], "edges": [], "error": "tree_sitter_verilog not installed"}

    try:
        language = Language(tsverilog.language())
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

    def add_node(nid: str, label: str, line: int) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str_path, "source_location": f"L{line}",
                          "confidence_score": 1.0})

    def add_edge(src: str, tgt: str, relation: str, line: int,
                 confidence: str = "EXTRACTED", score: float = 1.0) -> None:
        edges.append({"source": src, "target": tgt, "relation": relation,
                      "confidence": confidence, "confidence_score": score,
                      "source_file": str_path, "source_location": f"L{line}", "weight": 1.0})

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    def walk(node, module_nid: str | None = None) -> None:
        t = node.type

        # SystemVerilog class bodies are handled by _augment_systemverilog_semantics
        # (regex over source text). Skip their subtrees so in-class methods are not
        # double-emitted here — and with the wrong, return-type-derived name.
        if t in ("class_declaration", "interface_class_declaration"):
            return

        if t == "module_declaration":
            mod_name = _sv_first_identifier(_sv_child(node, "module_header"), source)
            if mod_name:
                line = node.start_point[0] + 1
                nid = _make_id(stem, mod_name)
                add_node(nid, mod_name, line)
                add_edge(file_nid, nid, "defines", line)
                for child in node.children:
                    walk(child, nid)
                return

        # `function_prototype` only appears inside class/interface-class bodies
        # (skipped above) and nests its name differently; it is intentionally not
        # handled here.
        elif t == "function_declaration":
            fn_body = _sv_child(node, "function_body_declaration")
            func_name = _sv_first_identifier(_sv_child(fn_body, "function_identifier"), source)
            if func_name:
                line = node.start_point[0] + 1
                parent = module_nid or file_nid
                nid = _make_id(parent, func_name)
                add_node(nid, f"{func_name}()", line)
                add_edge(parent, nid, "contains", line)

        elif t == "task_declaration":
            tk_body = _sv_child(node, "task_body_declaration")
            task_name = _sv_first_identifier(_sv_child(tk_body, "task_identifier"), source)
            if task_name:
                line = node.start_point[0] + 1
                parent = module_nid or file_nid
                nid = _make_id(parent, task_name)
                add_node(nid, task_name, line)
                add_edge(parent, nid, "contains", line)

        elif t == "package_import_declaration":
            for child in node.children:
                if child.type == "package_import_item":
                    pkg_text = _read_text(child, source)
                    pkg_name = pkg_text.split("::")[0].strip()
                    if pkg_name:
                        line = node.start_point[0] + 1
                        tgt_nid = _make_id(pkg_name)
                        add_node(tgt_nid, pkg_name, line)
                        src_nid = module_nid or file_nid
                        add_edge(src_nid, tgt_nid, "imports_from", line)

        elif t in ("module_instantiation", "checker_instantiation"):
            # `leaf u_leaf();` parses as checker_instantiation in 1.0.3;
            # module_instantiation (when it occurs) exposes a `module_type` field.
            # Both reduce to the first identifier under the node — the instantiated
            # type, not the instance name (which appears later).
            if module_nid:
                type_node = node.child_by_field_name("module_type")
                inst_type = (_read_text(type_node, source).strip() if type_node
                             else _sv_first_identifier(node, source))
                if inst_type:
                    line = node.start_point[0] + 1
                    tgt_nid = _make_id(inst_type)
                    add_node(tgt_nid, inst_type, line)
                    add_edge(module_nid, tgt_nid, "instantiates", line)

        for child in node.children:
            walk(child, module_nid)

    walk(root)
    _augment_systemverilog_semantics(
        source.decode("utf-8", errors="replace"),
        stem,
        str_path,
        file_nid,
        nodes,
        edges,
        seen_ids,
    )
    return {"nodes": nodes, "edges": edges}
