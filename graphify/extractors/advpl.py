"""AdvPL/TLPP structural extractor (regex/scanner based, no tree-sitter)."""
from __future__ import annotations

import re
from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id


_PROTHEUSDOC_RE = re.compile(
    r"/\*/\{Protheus\.doc\}[\s\S]*?/\*/", re.IGNORECASE
)
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")
_STRING_RE = re.compile(r'"(?:[^"\n]|"")*"|\'(?:[^\'\n]|\'\')*\'')
_INCLUDE_RE = re.compile(
    r"^\s*#\s*include\s*[<\"']([^>\"']+)[>\"']", re.IGNORECASE | re.MULTILINE
)
_FUNCTION_RE = re.compile(
    r"^\s*(?:(user|static)\s+)?function\s+([A-Za-z_]\w*)\s*\(",
    re.IGNORECASE | re.MULTILINE,
)
_CLASS_RE = re.compile(
    r"^\s*class\s+([A-Za-z_]\w*)"
    r"(?:\s+from\s+(?:longnameclass\s+)?([A-Za-z_][\w.]*))?",
    re.IGNORECASE | re.MULTILINE,
)
_ENDCLASS_RE = re.compile(r"^\s*end\s*class\b", re.IGNORECASE | re.MULTILINE)
_METHOD_DECL_RE = re.compile(
    r"^\s*(?:(?:public|private|protected|static)\s+)*method\s+([A-Za-z_]\w*)\s*\(",
    re.IGNORECASE | re.MULTILINE,
)
_METHOD_IMPL_RE = re.compile(
    r"^\s*method\s+([A-Za-z_]\w*)\s*\([^\n]*?\)"
    r"(?:\s+as\s+[A-Za-z_][\w.]*)?\s+class\s+([A-Za-z_]\w*)\b",
    re.IGNORECASE | re.MULTILINE,
)
_CALL_RE = re.compile(r"(?<![\w:>.&])([A-Za-z_]\w*)\s*\(")

_NON_CALLS = frozenset({
    "and", "begin", "case", "catch", "class", "do", "else", "elseif",
    "end", "endcase", "endclass", "enddo", "endif", "endsequence",
    "endtry", "exit", "for", "function", "if", "method", "next", "or",
    "recover", "return", "sequence", "static", "switch", "try", "user",
    "while",
})


def _mask(match: re.Match[str]) -> str:
    """Hide syntax while preserving offsets and line numbers."""
    return "".join("\n" if char == "\n" else " " for char in match.group(0))


def _read_source(path: Path) -> str:
    data = path.read_bytes()
    try:
        return data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return data.decode("cp1252", errors="replace")


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, offset) + 1


def _resolve_include(path: Path, reference: str) -> Path | None:
    relative = Path(reference.replace("\\", "/"))
    candidate = path.parent / relative
    if candidate.is_file():
        return candidate.resolve()
    # Protheus sources commonly uppercase include paths. Resolve each relative
    # component locally without guessing external AppServer include paths.
    current = path.parent
    try:
        for part in relative.parts:
            if part == "..":
                current = current.parent
                continue
            current = next(
                child for child in current.iterdir()
                if child.name.casefold() == part.casefold()
            )
        return current.resolve() if current.is_file() else None
    except (OSError, StopIteration):
        return None


def extract_advpl(path: Path) -> dict:
    """Extract basic AdvPL/TLPP functions, classes, methods, includes, and calls."""
    try:
        source = _read_source(path)
    except OSError:
        return {"nodes": [], "edges": []}

    str_path = str(path)
    stem = _file_stem(path)
    file_nid = _make_id(str_path)
    nodes: list[dict] = []
    edges: list[dict] = []
    raw_calls: list[dict] = []
    node_by_id: dict[str, dict] = {}
    edge_keys: set[tuple[str, str, str]] = set()

    def add_node(
        nid: str,
        label: str,
        line: int | None,
        *,
        source_file: str | None = str_path,
        file_local: bool = False,
    ) -> None:
        if nid in node_by_id:
            return
        node = {
            "id": nid,
            "label": label,
            "file_type": "code",
            "source_file": source_file,
            "source_location": f"L{line}" if line is not None else None,
        }
        if file_local:
            node["_file_local"] = True
        nodes.append(node)
        node_by_id[nid] = node

    def add_edge(source_id: str, target_id: str, relation: str, line: int) -> None:
        key = (source_id, target_id, relation)
        if key in edge_keys:
            return
        edge_keys.add(key)
        edges.append({
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "context": "import" if relation == "imports" else None,
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": str_path,
            "source_location": f"L{line}",
            "weight": 1.0,
        })

    add_node(file_nid, path.name, 1)

    # ProtheusDOC must be removed first: its unusual /*/{...} ... /*/ delimiters
    # otherwise make a normal C-style comment regex stop at the opening token.
    def mask_string(match: re.Match[str]) -> str:
        line_start = source.rfind("\n", 0, match.start()) + 1
        if re.match(r"^\s*#\s*include\b", source[line_start:match.start()], re.IGNORECASE):
            return match.group(0)
        return _mask(match)

    clean = _STRING_RE.sub(mask_string, source)
    clean = _PROTHEUSDOC_RE.sub(_mask, clean)
    clean = _BLOCK_COMMENT_RE.sub(_mask, clean)
    clean = _LINE_COMMENT_RE.sub(_mask, clean)

    for match in _INCLUDE_RE.finditer(clean):
        reference = match.group(1).strip()
        resolved = _resolve_include(path, reference)
        if resolved is None:
            continue
        target_nid = _make_id(str(resolved))
        add_node(target_nid, resolved.name, 1, source_file=str(resolved))
        add_edge(file_nid, target_nid, "imports", _line(clean, match.start()))

    code = clean
    functions: dict[str, tuple[str, str]] = {}
    user_functions: dict[str, str] = {}
    callable_matches: list[tuple[int, int, str]] = []

    for match in _FUNCTION_RE.finditer(code):
        kind = (match.group(1) or "function").lower()
        name = match.group(2)
        key = name.casefold()
        nid = _make_id(stem, key)
        add_node(
            nid,
            f"{name}()",
            _line(code, match.start()),
            file_local=kind == "static",
        )
        add_edge(file_nid, nid, "contains", _line(code, match.start()))
        functions[key] = (nid, kind)
        if kind == "user":
            user_functions[key] = nid
        callable_matches.append((match.start(), match.end(), nid))

    classes: dict[str, str] = {}
    class_starts: list[int] = []
    for match in _CLASS_RE.finditer(code):
        name = match.group(1)
        class_nid = _make_id(stem, name.casefold())
        classes[name.casefold()] = class_nid
        class_starts.append(match.start())
        line = _line(code, match.start())
        add_node(class_nid, name, line)
        add_edge(file_nid, class_nid, "contains", line)
        if match.group(2):
            base = match.group(2)
            base_nid = _make_id(base.casefold())
            add_node(base_nid, base, line, source_file=None)
            add_edge(class_nid, base_nid, "inherits", line)

        end_match = _ENDCLASS_RE.search(code, match.end())
        class_body = code[match.end():end_match.start() if end_match else len(code)]
        for method_match in _METHOD_DECL_RE.finditer(class_body):
            method_name = method_match.group(1)
            method_nid = _make_id(class_nid, method_name.casefold())
            method_line = _line(code, match.end() + method_match.start())
            add_node(method_nid, f".{method_name}()", method_line)
            add_edge(class_nid, method_nid, "method", method_line)

    for match in _METHOD_IMPL_RE.finditer(code):
        method_name, class_name = match.group(1), match.group(2)
        class_nid = classes.get(class_name.casefold())
        if class_nid is None:
            class_nid = _make_id(stem, class_name.casefold())
            add_node(class_nid, class_name, _line(code, match.start()))
            add_edge(file_nid, class_nid, "contains", _line(code, match.start()))
            classes[class_name.casefold()] = class_nid
        method_nid = _make_id(class_nid, method_name.casefold())
        line = _line(code, match.start())
        add_node(method_nid, f".{method_name}()", line)
        add_edge(class_nid, method_nid, "method", line)
        callable_matches.append((match.start(), match.end(), method_nid))

    boundaries = sorted(
        {start for start, _, _ in callable_matches} | set(class_starts) | {len(code)}
    )
    class_names = set(classes)
    for start, body_start, caller_nid in callable_matches:
        body_end = next(boundary for boundary in boundaries if boundary > start)
        body = code[body_start:body_end]
        for call_match in _CALL_RE.finditer(body):
            callee = call_match.group(1)
            callee_key = callee.casefold()
            if callee_key in _NON_CALLS or callee_key in class_names:
                continue
            target = functions.get(callee_key, (None, ""))[0]
            if target is None and callee_key.startswith("u_"):
                callee_key = callee_key[2:]
                target = user_functions.get(callee_key)
            line = _line(code, body_start + call_match.start())
            if target is not None:
                add_edge(caller_nid, target, "calls", line)
            else:
                raw_calls.append({
                    "callee": callee_key,
                    "caller_nid": caller_nid,
                    "source_file": str_path,
                    "source_location": f"L{line}",
                    "is_member_call": False,
                })

    return {
        "nodes": nodes,
        "edges": edges,
        "raw_calls": raw_calls,
        "input_tokens": 0,
        "output_tokens": 0,
    }
