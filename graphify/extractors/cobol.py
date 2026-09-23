"""Deterministic extraction for fixed- and free-format COBOL source."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _make_id


_NAME = r"[A-Z0-9][A-Z0-9-]*"
_PROGRAM = re.compile(rf"\bPROGRAM-ID\s*\.\s*({_NAME})", re.IGNORECASE)
_PARAGRAPH = re.compile(
    rf"^({_NAME})(?:\s+(SECTION))?\s*\.\s*$", re.IGNORECASE
)
_PERFORM = re.compile(rf"\bPERFORM\s+({_NAME})\b", re.IGNORECASE)
_COPY = re.compile(
    rf"\bCOPY\s+(?:'([^']+)'|\"([^\"]+)\"|({_NAME}(?:\.[A-Z0-9-]+)?))",
    re.IGNORECASE,
)
_CALL = re.compile(r"\bCALL\s+(['\"])([A-Z0-9-]+)\1", re.IGNORECASE)
_DATA_ITEM = re.compile(
    rf"^\s*(?:0[1-9]|[1-4][0-9]|66|77|88)\s+({_NAME})\b", re.IGNORECASE
)
_NOT_PARAGRAPHS = frozenset({
    "IDENTIFICATION", "ENVIRONMENT", "DATA", "PROCEDURE", "FILE",
    "WORKING-STORAGE", "LOCAL-STORAGE", "LINKAGE", "CONFIGURATION",
    "INPUT-OUTPUT", "STOP", "EXIT", "GOBACK", "CONTINUE", "DISPLAY", "MOVE",
    "COMPUTE", "ADD", "SUBTRACT", "MULTIPLY", "DIVIDE", "PERFORM", "COPY",
    "CALL", "IF", "ELSE", "END-IF", "END-PERFORM", "END-EXEC",
})
_PERFORM_MODIFIERS = frozenset({
    "UNTIL", "VARYING", "TIMES", "WITH", "TEST", "FOREVER",
})


def _code_lines(source: str) -> list[tuple[int, str]]:
    """Return logical COBOL lines with fixed-format continuations joined."""
    physical = source.splitlines()
    forced_free = bool(
        re.search(r">>\s*SOURCE\s+FORMAT\s+(?:IS\s+)?FREE", source, re.IGNORECASE)
    )
    fixed_markers = sum(
        bool(re.match(r"^ {6}[ *\-/ ]", line)) for line in physical if line.strip()
    )
    nonempty = sum(bool(line.strip()) for line in physical)
    free = forced_free or fixed_markers < max(1, nonempty // 2)

    logical: list[tuple[int, str]] = []
    for number, line in enumerate(physical, 1):
        if free:
            code = line.split("*>", 1)[0].rstrip()
            if not code.strip() or code.lstrip().startswith(">>"):
                continue
            logical.append((number, code))
            continue

        if len(line) < 7:
            continue
        indicator = line[6]
        if indicator in "*/":
            continue
        code = line[7:72].split("*>", 1)[0].rstrip()
        if not code.strip():
            continue
        if indicator == "-" and logical:
            prior_number, prior = logical[-1]
            joiner = "" if prior.rstrip().endswith("-") else " "
            logical[-1] = (prior_number, prior.rstrip() + joiner + code.lstrip())
        else:
            logical.append((number, code))
    return logical


def _mask_strings(code: str) -> str:
    return re.sub(r"'[^']*'|\"[^\"]*\"", lambda match: " " * len(match.group()), code)


def _starts_inside_string(code: str, offset: int) -> bool:
    """Whether *offset* lies inside a COBOL quoted literal."""
    for match in re.finditer(r"'(?:''|[^'])*'|\"(?:\"\"|[^\"])*\"", code):
        if match.start() <= offset < match.end():
            return True
    return False


def extract_cobol(path: Path) -> dict:
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": str(exc)}

    source_file = str(path)
    file_id = _make_id(source_file)
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    raw_calls: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_edges: set[tuple[str, str, str]] = set()

    def add_node(
        nid: str,
        label: str,
        line: int,
        *,
        kind: str,
        source_backed: bool = True,
        callable_node: bool = False,
    ) -> str:
        if nid not in seen_ids:
            seen_ids.add(nid)
            item: dict[str, Any] = {
                "id": nid,
                "label": label,
                "file_type": "code",
                "source_location": f"L{line}",
                "metadata": {"language": "cobol", "kind": kind},
            }
            if source_backed:
                item["source_file"] = source_file
            if callable_node:
                item["_callable"] = True
            nodes.append(item)
        return nid

    def add_edge(
        source_id: str,
        target_id: str,
        relation: str,
        line: int,
        *,
        target_file: str | None = None,
    ) -> None:
        key = (source_id, target_id, relation)
        if not source_id or not target_id or source_id == target_id or key in seen_edges:
            return
        seen_edges.add(key)
        edge: dict[str, Any] = {
            "source": source_id,
            "target": target_id,
            "relation": relation,
            "confidence": "EXTRACTED",
            "source_file": source_file,
            "source_location": f"L{line}",
            "weight": 1.0,
        }
        if target_file:
            edge["target_file"] = target_file
        edges.append(edge)

    add_node(file_id, path.name, 1, kind="file")

    code_lines = _code_lines(source)
    current_program = file_id
    current_scope = file_id
    in_procedure = False
    in_exec = False
    paragraphs: dict[tuple[str, str], str] = {}
    pending_performs: list[tuple[str, str, str, int]] = []

    for line, code in code_lines:
        upper = code.upper().strip()

        if in_exec:
            if "END-EXEC" in upper:
                in_exec = False
            continue
        if re.search(r"\bEXEC\s+(?:SQL|CICS)\b", upper):
            if "END-EXEC" not in upper:
                in_exec = True
            continue

        program_match = _PROGRAM.search(upper)
        if program_match:
            name = program_match.group(1).upper()
            current_program = add_node(
                _make_id(file_id, "program", name.casefold()),
                name,
                line,
                kind="program",
                callable_node=True,
            )
            add_edge(file_id, current_program, "contains", line)
            current_scope = current_program
            in_procedure = False
            continue

        copy_match = _COPY.search(code)
        if copy_match:
            written = next(group for group in copy_match.groups() if group)
            copy_name = written.rstrip(".")
            copy_path = Path(copy_name)
            if not copy_path.suffix:
                copy_path = copy_path.with_suffix(".cpy")
            target = path.parent / copy_path
            reference_id = add_node(
                _make_id(current_program, "copybook", copy_name.casefold()),
                Path(copy_name).stem.upper(),
                line,
                kind="copybook_reference",
            )
            add_edge(current_program, reference_id, "contains", line)
            add_edge(
                current_program,
                _make_id(str(target)),
                "imports_from",
                line,
                target_file=str(target),
            )

        if "PROCEDURE DIVISION" in upper:
            in_procedure = True
            current_scope = current_program
            continue

        if not in_procedure:
            item = _DATA_ITEM.match(upper)
            if item:
                name = item.group(1).upper()
                if name != "FILLER":
                    item_id = add_node(
                        _make_id(current_program, "data", name.casefold()),
                        name,
                        line,
                        kind="data_item",
                    )
                    add_edge(current_program, item_id, "contains", line)
            continue

        paragraph = _PARAGRAPH.match(upper)
        if paragraph and paragraph.group(1) not in _NOT_PARAGRAPHS:
            name = paragraph.group(1).upper()
            key = (current_program, name.casefold())
            paragraph_id = paragraphs.get(key)
            if paragraph_id is None:
                paragraph_id = add_node(
                    _make_id(current_program, "paragraph", name.casefold()),
                    name,
                    line,
                    kind="section" if paragraph.group(2) else "paragraph",
                    callable_node=True,
                )
                paragraphs[key] = paragraph_id
                add_edge(current_program, paragraph_id, "contains", line)
            current_scope = paragraph_id
            continue

        masked = _mask_strings(upper)
        for match in _PERFORM.finditer(masked):
            name = match.group(1).upper()
            if name not in _PERFORM_MODIFIERS:
                pending_performs.append((current_scope, current_program, name, line))

        for match in _CALL.finditer(upper):
            if _starts_inside_string(upper, match.start()):
                continue
            callee = match.group(2).upper()
            raw_calls.append({
                "caller_nid": current_scope,
                "callee": callee,
                "language": "cobol",
                "source_file": source_file,
                "source_location": f"L{line}",
            })

    for caller_id, program_id, name, line in pending_performs:
        target_id = paragraphs.get((program_id, name.casefold()))
        if target_id is not None:
            add_edge(caller_id, target_id, "calls", line)

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}
