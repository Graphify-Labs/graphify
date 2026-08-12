"""Embedded HTML/JavaScript extraction from Python string regions.

This module is deliberately deterministic and failure-isolated.  It never
executes Python/HTML/JavaScript.  Python AST identifies string regions,
including f-strings, while a tiny HTML/JS structural pass emits GUI semantic
nodes and ``references`` edges:

    control -> handler -> api_method -> surface_spec -> native_handler

The latter two hops are emitted from ``surfaces.py`` and ``native_ports.py``
AST, so repository-wide graph construction resolves one stable semantic chain.
Embedded source locations map back to the host Python file.  Nodes/edges carry
``provenance`` and source-map metadata; source bodies are never attached.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
import hashlib
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Any, Iterable, Mapping


MAX_EMBEDDED_FRAGMENTS = 96
MAX_FRAGMENT_BYTES = 768 * 1024
MAX_CONTROLS = 10_000
MAX_SCRIPT_BLOCKS = 256

_HTML_HINT = re.compile(r"<(?:html|script|button|a|div|section|main|body|input|form|style)\b", re.I)
_HANDLER_CALL = re.compile(r"(?:^|[^A-Za-z0-9_$])(?:await\s+)?([A-Za-z_$][\w$]*)\s*\(")
_API_CALL = re.compile(
    r"\b(?:callApi|callApiRaw|api|detailApi|dispatch_api)\s*\(\s*(['\"])([A-Za-z_][A-Za-z0-9_-]*)\1"
)
_FUNCTION_RE = re.compile(r"\b(?:async\s+)?function\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*\{")
_ARROW_RE = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*(?:async\s*)?(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*\{")
_NAVIGATION_RE = re.compile(r"(?:window\.)?location(?:\.href)?\s*=\s*(['\"])([^'\"]+)\1", re.I)


def _digest(*parts: object) -> str:
    return hashlib.sha256("\x1f".join(str(part) for part in parts).encode("utf-8")).hexdigest()


def _source_location(line: int) -> str:
    return f"L{max(1, int(line or 1))}"


def _line_for_offset(text: str, offset: int, base_line: int) -> int:
    return max(1, int(base_line)) + text.count("\n", 0, max(0, offset))


def _safe_label(value: str, *, limit: int = 240) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()[:limit]


def provenance_for_path(path: str | Path) -> str:
    """Classify source role; embedded nodes inherit this value unchanged."""
    value = str(path).replace("\\", "/").casefold()
    parts = tuple(part for part in value.split("/") if part)
    name = parts[-1] if parts else value
    if any(part in {"fixtures", "fixture", "testdata", "test-data", "samples", "sample"} for part in parts) or name.startswith("fixture") or ".fixture." in name:
        return "fixture"
    if any(part in {"generated", "gen", "dist", "build", "coverage", ".cache"} for part in parts):
        return "generated"
    if any(part in {"vendor", "vendors", "third_party", "third-party", "node_modules"} for part in parts):
        return "vendor"
    try:
        from graphify.paths import _is_test_path  # type: ignore

        if _is_test_path(Path(path)):
            return "test"
    except Exception:
        pass
    if any(part in {"test", "tests", "testing", "spec", "specs", "__tests__"} for part in parts) or name.startswith("test_") or name.endswith("_test.py"):
        return "test"
    return "production"


def stamp_provenance(result: dict[str, Any], path: str | Path) -> dict[str, Any]:
    provenance = provenance_for_path(path)
    for node in result.get("nodes", ()):
        if isinstance(node, dict):
            node.setdefault("provenance", provenance)
    for edge in result.get("edges", ()):
        if isinstance(edge, dict):
            edge.setdefault("provenance", provenance)
    return result


@dataclass(frozen=True)
class VirtualDocument:
    virtual_id: str
    host_file: str
    host_symbol: str
    region_id: str
    text: str
    start_line: int
    provenance: str
    content_hash: str

    def source_map(self, virtual_line: int = 1) -> dict[str, Any]:
        return {
            "host_file": self.host_file,
            "host_symbol": self.host_symbol,
            "region_id": self.region_id,
            "virtual_document_id": self.virtual_id,
            "line_start": self.start_line + max(0, int(virtual_line) - 1),
        }


@dataclass
class _Region:
    text: str
    line: int
    host_symbol: str


def _flatten_string(node: ast.AST | None) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for value in node.values:
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                parts.append(value.value)
            elif isinstance(value, ast.FormattedValue):
                parts.append("__GRAPHIFY_EXPR__")
        return "".join(parts)
    return None


def _target_name(stmt: ast.stmt, fallback: str) -> str:
    target = getattr(stmt, "targets", None)
    if isinstance(target, list) and target:
        value = target[0]
        if isinstance(value, ast.Name):
            return value.id
        if isinstance(value, ast.Attribute):
            return value.attr
    target = getattr(stmt, "target", None)
    if isinstance(target, ast.Name):
        return target.id
    return fallback


def _regions_from_block(body: Iterable[ast.stmt], host_symbol: str, output: list[_Region]) -> None:
    """Walk reachable statements only; stop after unconditional return/raise."""
    for stmt in body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            _regions_from_block(stmt.body, stmt.name, output)
        elif isinstance(stmt, ast.ClassDef):
            _regions_from_block(stmt.body, f"{host_symbol}.{stmt.name}" if host_symbol else stmt.name, output)
        elif isinstance(stmt, ast.If):
            _regions_from_block(stmt.body, host_symbol, output)
            _regions_from_block(stmt.orelse, host_symbol, output)
        elif isinstance(stmt, (ast.For, ast.AsyncFor, ast.While)):
            _regions_from_block(stmt.body, host_symbol, output)
            _regions_from_block(stmt.orelse, host_symbol, output)
        elif isinstance(stmt, (ast.With, ast.AsyncWith)):
            _regions_from_block(stmt.body, host_symbol, output)
        elif isinstance(stmt, ast.Try):
            _regions_from_block(stmt.body, host_symbol, output)
            for handler in stmt.handlers:
                _regions_from_block(handler.body, host_symbol, output)
            _regions_from_block(stmt.orelse, host_symbol, output)
            _regions_from_block(stmt.finalbody, host_symbol, output)
        elif isinstance(stmt, ast.Match):
            for case in stmt.cases:
                _regions_from_block(case.body, host_symbol, output)
        else:
            value: ast.AST | None = None
            if isinstance(stmt, (ast.Assign, ast.AnnAssign, ast.Return, ast.Expr)):
                value = getattr(stmt, "value", None)
            text = _flatten_string(value)
            if text is not None and _HTML_HINT.search(text):
                output.append(_Region(text, int(getattr(value, "lineno", getattr(stmt, "lineno", 1)) or 1), _target_name(stmt, host_symbol or "<module>")))
        if isinstance(stmt, (ast.Return, ast.Raise)):
            break


def discover_virtual_documents(path: str | Path) -> tuple[tuple[VirtualDocument, ...], tuple[dict[str, Any], ...]]:
    source_path = Path(path)
    diagnostics: list[dict[str, Any]] = []
    try:
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
    except (OSError, UnicodeError, SyntaxError) as exc:
        return (), ({"code": "embedded_python_parse_failed", "error_type": type(exc).__name__},)
    regions: list[_Region] = []
    _regions_from_block(tree.body, "<module>", regions)
    documents: list[VirtualDocument] = []
    provenance = provenance_for_path(source_path)
    for index, region in enumerate(regions):
        if index >= MAX_EMBEDDED_FRAGMENTS:
            diagnostics.append({"code": "embedded_fragment_limit", "limit": MAX_EMBEDDED_FRAGMENTS})
            break
        size = len(region.text.encode("utf-8"))
        if size > MAX_FRAGMENT_BYTES:
            diagnostics.append({"code": "embedded_fragment_too_large", "index": index, "bytes": size, "limit": MAX_FRAGMENT_BYTES})
            continue
        content_hash = hashlib.sha256(region.text.encode("utf-8")).hexdigest()
        region_id = f"region-{index}-{content_hash[:16]}"
        virtual_id = "embedded-" + _digest(str(source_path).replace("\\", "/"), region.host_symbol, index, content_hash)
        documents.append(VirtualDocument(virtual_id, str(source_path), region.host_symbol, region_id, region.text, region.line, provenance, content_hash))
    return tuple(documents), tuple(diagnostics)


class _HtmlCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.controls: list[dict[str, Any]] = []
        self.scripts: list[dict[str, Any]] = []
        self._control_stack: list[dict[str, Any]] = []
        self._script: dict[str, Any] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        data = {str(key).casefold(): str(value or "") for key, value in attrs}
        tag_name = tag.casefold()
        if tag_name == "script":
            self._script = {"line": self.getpos()[0], "parts": []}
        if tag_name in {"button", "a"} or data.get("role", "").casefold() == "button" or "onclick" in data:
            if len(self.controls) + len(self._control_stack) < MAX_CONTROLS:
                self._control_stack.append({"tag": tag_name, "attrs": data, "line": self.getpos()[0], "parts": []})

    def handle_endtag(self, tag: str) -> None:
        tag_name = tag.casefold()
        if tag_name == "script" and self._script is not None:
            self.scripts.append({"line": self._script["line"], "text": "".join(self._script["parts"])})
            self._script = None
        for index in range(len(self._control_stack) - 1, -1, -1):
            if self._control_stack[index]["tag"] == tag_name:
                item = self._control_stack.pop(index)
                item["label"] = _safe_label("".join(item.pop("parts")))
                self.controls.append(item)
                break

    def handle_data(self, data: str) -> None:
        if self._script is not None:
            self._script["parts"].append(data)
        if self._control_stack:
            self._control_stack[-1]["parts"].append(data)


def _handler_name(onclick: str) -> str:
    match = _HANDLER_CALL.search(str(onclick or ""))
    if not match:
        return ""
    name = match.group(1)
    return "" if name in {"if", "for", "while", "confirm", "alert"} else name


def _matching_brace(source: str, start: int) -> int:
    depth = 0
    quote = ""
    escaped = False
    line_comment = False
    block_comment = False
    index = start
    while index < len(source):
        char = source[index]
        nxt = source[index + 1] if index + 1 < len(source) else ""
        if line_comment:
            if char == "\n":
                line_comment = False
            index += 1
            continue
        if block_comment:
            if char == "*" and nxt == "/":
                block_comment = False
                index += 2
                continue
            index += 1
            continue
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            index += 1
            continue
        if char == "/" and nxt == "/":
            line_comment = True
            index += 2
            continue
        if char == "/" and nxt == "*":
            block_comment = True
            index += 2
            continue
        if char in {"'", '"', "`"}:
            quote = char
            index += 1
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    return len(source) - 1


def _javascript_functions(script: str) -> list[tuple[str, int, int]]:
    matches: list[tuple[str, int, int]] = []
    seen: set[tuple[str, int]] = set()
    for pattern in (_FUNCTION_RE, _ARROW_RE):
        for match in pattern.finditer(script):
            brace = script.find("{", match.start(), match.end() + 1)
            if brace < 0:
                continue
            key = (match.group(1), match.start())
            if key in seen:
                continue
            seen.add(key)
            matches.append((match.group(1), match.start(), _matching_brace(script, brace)))
    return sorted(matches, key=lambda item: (item[1], item[0]))


def _node(node_id: str, label: str, kind: str, document: VirtualDocument, line: int, semantic_kind: str, **extra: Any) -> dict[str, Any]:
    value = {
        "id": node_id,
        "label": label,
        "file_type": kind,
        "source_file": document.host_file,
        "source_location": _source_location(line),
        "provenance": document.provenance,
        "semantic_kind": semantic_kind,
        "source_map": {**document.source_map(max(1, line - document.start_line + 1)), "content_hash": document.content_hash},
        "metadata": {"semantic_kind": semantic_kind, "host_symbol": document.host_symbol, "region_id": document.region_id, "virtual_document_id": document.virtual_id},
    }
    value.update(extra)
    return value


def _edge(source: str, target: str, context: str, document: VirtualDocument, line: int, **extra: Any) -> dict[str, Any]:
    value = {
        "source": source,
        "target": target,
        "relation": "references",
        "context": context,
        "confidence": "EXTRACTED",
        "source_file": document.host_file,
        "source_location": _source_location(line),
        "provenance": document.provenance,
        "metadata": {"semantic_kind": context, "region_id": document.region_id, "virtual_document_id": document.virtual_id},
        "weight": 1.0,
    }
    value.update(extra)
    return value


def _handler_id(path: str, name: str) -> str:
    return "embedded-handler-" + _digest(path.replace("\\", "/"), name)


def _api_id(name: str) -> str:
    return "semantic-api-" + _digest(name)


def _surface_id(name: str) -> str:
    return "semantic-surface-" + _digest(name)


def _native_id(name: str) -> str:
    return "semantic-native-" + _digest(name.lstrip("_"))


def _extract_document(document: VirtualDocument) -> dict[str, Any]:
    parser = _HtmlCollector()
    try:
        parser.feed(document.text)
    except Exception as exc:
        return {"nodes": [], "edges": [], "diagnostics": [{"code": "embedded_html_parse_failed", "error_type": type(exc).__name__}]}
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    handler_lines: dict[str, int] = {}

    for script_block in parser.scripts[:MAX_SCRIPT_BLOCKS]:
        script = str(script_block.get("text") or "")
        script_base_line = document.start_line + int(script_block.get("line") or 1) - 1
        for name, start, end in _javascript_functions(script):
            line = _line_for_offset(script, start, script_base_line)
            handler_lines.setdefault(name, line)
            handler_id = _handler_id(document.host_file, name)
            nodes.setdefault(handler_id, _node(handler_id, name, "function", document, line, "handler"))
            body = script[start:end + 1]
            for api_match in _API_CALL.finditer(body):
                method = api_match.group(2)
                api_line = _line_for_offset(script, start + api_match.start(), script_base_line)
                api_id = _api_id(method)
                nodes.setdefault(api_id, _node(api_id, method, "api", document, api_line, "api_method"))
                edges.append(_edge(handler_id, api_id, "handler_api", document, api_line))

    for index, control in enumerate(parser.controls):
        attrs = control.get("attrs") or {}
        onclick = str(attrs.get("onclick") or "")
        action = str(attrs.get("data-mg-action") or attrs.get("data-action") or "")
        handler = _handler_name(onclick)
        href = str(attrs.get("href") or "").strip()
        navigation = ""
        if not handler:
            nav_match = _NAVIGATION_RE.search(onclick)
            navigation = (nav_match.group(2) if nav_match else href).strip()
        label = _safe_label(control.get("label") or attrs.get("aria-label") or attrs.get("title") or action or control.get("tag") or "control")
        line = document.start_line + int(control.get("line") or 1) - 1
        control_id = "embedded-control-" + _digest(document.virtual_id, index, label, onclick, action)
        nodes[control_id] = _node(control_id, label, "gui_control", document, line, "gui_control", metadata={"semantic_kind": "gui_control", "host_symbol": document.host_symbol, "region_id": document.region_id, "virtual_document_id": document.virtual_id, "action": action})
        if handler:
            handler_id = _handler_id(document.host_file, handler)
            handler_line = handler_lines.get(handler, line)
            nodes.setdefault(handler_id, _node(handler_id, handler, "function", document, handler_line, "handler"))
            edges.append(_edge(control_id, handler_id, "control_handler", document, line))
        elif navigation:
            local_handler = f"navigate:{navigation}"
            handler_id = _handler_id(document.host_file, local_handler)
            nodes.setdefault(handler_id, _node(handler_id, local_handler, "function", document, line, "handler", metadata={"semantic_kind": "handler", "local_action": "navigation", "target": navigation, "host_symbol": document.host_symbol, "region_id": document.region_id, "virtual_document_id": document.virtual_id}))
            edges.append(_edge(control_id, handler_id, "control_handler", document, line, metadata={"semantic_kind": "control_handler", "local_action": "navigation", "target": navigation, "region_id": document.region_id, "virtual_document_id": document.virtual_id}))

    return {"nodes": list(nodes.values()), "edges": edges, "diagnostics": []}


def _literal(node: ast.AST | None) -> Any:
    try:
        return ast.literal_eval(node) if node is not None else None
    except Exception:
        return None


def _semantic_python_nodes(path: Path, tree: ast.AST, provenance: str) -> dict[str, list[dict[str, Any]]]:
    """Emit cross-file surface/native semantic anchors from Python AST."""
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    source = str(path)
    if path.name == "surfaces.py":
        def add_surface(public: str, handler: str, line: int) -> None:
            api_id, surface_id, native_id = _api_id(public), _surface_id(public), _native_id(handler)
            api_node = {"id": api_id, "label": public, "file_type": "api", "source_file": source, "source_location": _source_location(line), "provenance": provenance, "semantic_kind": "api_method", "metadata": {"semantic_kind": "api_method"}}
            surface_node = {"id": surface_id, "label": f"GuiOperationSpec:{public}", "file_type": "surface", "source_file": source, "source_location": _source_location(line), "provenance": provenance, "semantic_kind": "surface_spec", "metadata": {"semantic_kind": "surface_spec", "native_handler": handler}}
            nodes.setdefault(api_id, api_node); nodes.setdefault(surface_id, surface_node)
            edges.append({"source": api_id, "target": surface_id, "relation": "references", "context": "api_surface", "confidence": "EXTRACTED", "source_file": source, "source_location": _source_location(line), "provenance": provenance, "metadata": {"semantic_kind": "api_surface"}, "weight": 1.0})
            edges.append({"source": surface_id, "target": native_id, "relation": "references", "context": "surface_native", "confidence": "EXTRACTED", "source_file": source, "source_location": _source_location(line), "provenance": provenance, "metadata": {"semantic_kind": "surface_native"}, "weight": 1.0})

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
                continue
            if node.func.id == "_add" and len(node.args) >= 5:
                public = _literal(node.args[0])
                handler = _literal(node.args[4])
                if isinstance(public, str) and isinstance(handler, str):
                    add_surface(public, handler, int(node.lineno))
                continue
            if node.func.id == "_same" and len(node.args) >= 4:
                names = _literal(node.args[0])
                handler = _literal(node.args[3])
                if not isinstance(handler, str) or not isinstance(names, (tuple, list, set)):
                    continue
                for public in names:
                    if isinstance(public, str) and public:
                        add_surface(public, handler, int(node.lineno))
        for loop in tree.body:
            if not isinstance(loop, ast.For) or not isinstance(loop.target, ast.Name):
                continue
            values = _literal(loop.iter)
            if not isinstance(values, (tuple, list, set)) or any(not isinstance(item, str) for item in values):
                continue
            loop_name = loop.target.id
            for stmt in loop.body:
                for call in ast.walk(stmt):
                    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name) or call.func.id != "_add" or len(call.args) < 5:
                        continue
                    if not isinstance(call.args[0], ast.Name) or call.args[0].id != loop_name:
                        continue
                    handler = _literal(call.args[4])
                    if not isinstance(handler, str):
                        continue
                    for public in values:
                        add_surface(public, handler, int(call.lineno))
    elif path.name == "native_ports.py":
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                semantic = node.name.lstrip("_")
                native_id = _native_id(semantic)
                nodes.setdefault(native_id, {"id": native_id, "label": semantic, "file_type": "native", "source_file": source, "source_location": _source_location(node.lineno), "provenance": provenance, "semantic_kind": "native_handler", "metadata": {"semantic_kind": "native_handler"}})
        for node in ast.walk(tree):
            value = None
            if isinstance(node, ast.Assign):
                if any(isinstance(target, ast.Name) and target.id == "methods" for target in node.targets):
                    value = node.value
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "methods":
                value = node.value
            if not isinstance(value, ast.Dict):
                continue
            for key_node, value_node in zip(value.keys, value.values):
                handler = _literal(key_node)
                if not isinstance(handler, str) or not handler:
                    continue
                line = int(getattr(value_node, "lineno", getattr(node, "lineno", 1)) or 1)
                native_id = _native_id(handler)
                nodes.setdefault(native_id, {"id": native_id, "label": handler, "file_type": "native", "source_file": source, "source_location": _source_location(line), "provenance": provenance, "semantic_kind": "native_handler", "metadata": {"semantic_kind": "native_handler", "dispatch_alias": True}})
    return {"nodes": list(nodes.values()), "edges": edges}


def extract_embedded_python(path: str | Path) -> dict[str, Any]:
    source_path = Path(path)
    documents, diagnostics = discover_virtual_documents(source_path)
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []
    all_diagnostics = list(diagnostics)
    for document in documents:
        result = _extract_document(document)
        for node in result["nodes"]:
            nodes.setdefault(str(node.get("id") or ""), node)
        edges.extend(result["edges"])
        all_diagnostics.extend(result["diagnostics"])
    try:
        source = source_path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(source_path))
        semantics = _semantic_python_nodes(source_path, tree, provenance_for_path(source_path))
        for node in semantics["nodes"]:
            nodes.setdefault(str(node.get("id") or ""), node)
        edges.extend(semantics["edges"])
    except (OSError, UnicodeError, SyntaxError) as exc:
        all_diagnostics.append({"code": "embedded_semantic_python_failed", "error_type": type(exc).__name__})
    edge_map: dict[tuple[str, ...], dict[str, Any]] = {}
    for edge in edges:
        key = (
            str(edge.get("source") or ""), str(edge.get("target") or ""),
            str(edge.get("relation") or ""), str(edge.get("context") or ""),
            str(edge.get("provenance") or ""), str(edge.get("source_location") or ""),
        )
        edge_map.setdefault(key, edge)
    return {"nodes": list(nodes.values()), "edges": list(edge_map.values()), "diagnostics": all_diagnostics, "virtual_documents": [doc.virtual_id for doc in documents]}


def merge_embedded_result(base: dict[str, Any], embedded: Mapping[str, Any], path: str | Path) -> dict[str, Any]:
    # Embedded semantic rows already carry source-role provenance. Leave the
    # ordinary AST rows untouched until aggregate cross-file resolution has
    # finished; early metadata changes exact-twin comparisons in alias import
    # de-duplication.
    nodes = base.setdefault("nodes", [])
    edges = base.setdefault("edges", [])
    known_nodes = {str(item.get("id") or "") for item in nodes if isinstance(item, Mapping)}
    for node in embedded.get("nodes", ()):
        if isinstance(node, dict) and str(node.get("id") or "") not in known_nodes:
            nodes.append(node); known_nodes.add(str(node.get("id") or ""))
    known_edges = {
        (str(item.get("source") or ""), str(item.get("target") or ""), str(item.get("relation") or ""), str(item.get("context") or ""), str(item.get("provenance") or ""), str(item.get("source_location") or ""))
        for item in edges if isinstance(item, Mapping)
    }
    for edge in embedded.get("edges", ()):
        if not isinstance(edge, dict):
            continue
        key = (str(edge.get("source") or ""), str(edge.get("target") or ""), str(edge.get("relation") or ""), str(edge.get("context") or ""), str(edge.get("provenance") or ""), str(edge.get("source_location") or ""))
        if key not in known_edges:
            edges.append(edge); known_edges.add(key)
    if embedded.get("diagnostics"):
        base.setdefault("diagnostics", []).extend(embedded["diagnostics"])
    return base


__all__ = [
    "MAX_EMBEDDED_FRAGMENTS", "MAX_FRAGMENT_BYTES", "VirtualDocument",
    "discover_virtual_documents", "extract_embedded_python", "merge_embedded_result",
    "provenance_for_path", "stamp_provenance",
]
