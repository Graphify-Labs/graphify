"""Deterministic extraction for fixed- and free-format COBOL source."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from graphify.extractors.base import _make_id, _read_source_text


_NAME = r"[A-Z0-9][A-Z0-9-]*"
_PROGRAM = re.compile(rf"\bPROGRAM-ID\s*\.\s*({_NAME})", re.IGNORECASE)
_PARAGRAPH = re.compile(
    rf"^({_NAME})(?:\s+(SECTION))?\s*\.\s*$", re.IGNORECASE
)
_PERFORM = re.compile(
    rf"\bPERFORM\s+({_NAME})(?:\s+(?:THRU|THROUGH)\s+({_NAME}))?\b",
    re.IGNORECASE,
)
_COPY = re.compile(
    rf"\bCOPY\s+(?:'([^']+)'|\"([^\"]+)\"|({_NAME}(?:\.[A-Z0-9-]+)?))",
    re.IGNORECASE,
)
# `GO TO A` and `GO TO A B C DEPENDING ON X`. _GO_TO finds the statement,
# _GO_TO_WORDS the words that follow it, separated by spaces or commas. Which of
# those are targets is decided by _go_to_targets: the words of whatever
# statement comes next on the line match as well.
_GO_TO = re.compile(r"\bGO\s+TO\s+", re.IGNORECASE)
_GO_TO_WORDS = re.compile(rf"{_NAME}(?:[\s,]+{_NAME})*", re.IGNORECASE)
_CALL = re.compile(r"\bCALL\s+(['\"])([A-Z0-9-]+)\1", re.IGNORECASE)
_END_PROGRAM = re.compile(r"\bEND\s+PROGRAM\b", re.IGNORECASE)
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
# In `A OF SEC` and `A IN SEC` the section only qualifies paragraph A: A is the
# target, the section is not.
_GO_TO_QUALIFIERS = frozenset({"OF", "IN"})


def _go_to_targets(words: list[str]) -> list[str]:
    """The procedure names a GO TO jumps to, from the words that follow it.

    A plain `GO TO A` has exactly one target, so only the first word counts:
    the rest of the line belongs to the next statement (`... GO TO A ELSE SET
    B TO TRUE`). Only `GO TO A B C DEPENDING ON X` has several, and there the
    list runs up to DEPENDING, with the section of a qualified name left out.
    """
    if "DEPENDING" not in words:
        return words[:1]
    targets: list[str] = []
    skip = False
    for word in words[:words.index("DEPENDING")]:
        if skip:
            skip = False
        elif word in _GO_TO_QUALIFIERS:
            skip = True
        else:
            targets.append(word)
    return targets
# A line that begins with a statement verb. Only procedure code has these; a
# data description begins with a level number. The verb must be a whole word:
# `OPEN-FILES.` is a name, not an OPEN statement.
_STATEMENT = re.compile(
    r"^(?:ACCEPT|ADD|ALLOCATE|ALTER|CALL|CANCEL|CLOSE|COMMIT|COMPUTE|CONTINUE"
    r"|DELETE|DISPLAY|DIVIDE|ENTRY|EVALUATE|EXIT|FREE|GENERATE|GO|GOBACK|IF"
    r"|INITIALIZE|INITIATE|INSPECT|INVOKE|JSON|MERGE|MOVE|MULTIPLY"
    r"|NEXT\s+SENTENCE|OPEN|PERFORM|RAISE|READ|RELEASE|RESUME|RETURN|REWRITE"
    r"|ROLLBACK|SEARCH|SET|SORT|START|STOP|STRING|SUBTRACT|SUPPRESS|TERMINATE"
    r"|UNLOCK|UNSTRING|VALIDATE|WRITE|XML)(?![A-Z0-9-])"
)
# What an EXEC SQL block does that is a declaration, not a statement to run:
# these stand in the DATA DIVISION as well (`EXEC SQL INCLUDE SQLCA END-EXEC`).
_SQL_DECLARATION = re.compile(r"^(?:INCLUDE|DECLARE|BEGIN\s+DECLARE|END\s+DECLARE)\b")
_EXEC = re.compile(r"\bEXEC\s+(SQL|CICS)\b")


def _code_lines(source: str) -> list[tuple[int, str]]:
    """Return logical COBOL lines with fixed-format continuations joined."""
    physical = source.splitlines()
    forced_free = bool(
        re.search(r">>\s*SOURCE\s+FORMAT\s+(?:IS\s+)?FREE", source, re.IGNORECASE)
    )
    # A fixed-format line is a 6-column sequence area followed by the indicator
    # in column 7. The sequence area is blank on some files but carries a
    # sequence NUMBER on legacy mainframe source (the historical norm), so match
    # both: six spaces, or six digits, followed by a valid indicator (space =
    # code, `*`/`/` = comment, `-` = continuation, `D` = debug). Requiring six
    # blank columns misclassified every sequence-numbered file as free-format,
    # which then kept the sequence number in the code and dropped every paragraph
    # (its `^NAME.$` anchor no longer matched) and PERFORM edge.
    fixed_markers = sum(
        bool(re.match(r"^(?: {6}|\d{6})[ *\-/dD]", line))
        for line in physical if line.strip()
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


def _procedure_copybook_start(code_lines: list[tuple[int, str]]) -> int | None:
    """The line where the procedure code of a headerless copybook begins.

    A copybook of procedure code is pasted into the PROCEDURE DIVISION of the
    program that copies it, so it has paragraphs and statements but no
    `PROCEDURE DIVISION` header of its own. Read by the header alone, such a
    file is taken for data from its first line to its last, and every paragraph
    and PERFORM in it is lost.

    Returns the line of the first paragraph or section header, but only when
    the file has neither a PROGRAM-ID nor a PROCEDURE DIVISION header and a
    statement follows that header. A lone `NAME.` line is not enough: a data
    copybook can have one where a VALUE clause runs on to the next line
    (`SPACES.`). Returns None for every other file, which is then read as before.

    An EXEC block after the header counts as a statement, except an EXEC SQL
    declaration (INCLUDE, DECLARE), which a data copybook has as well.
    """
    start: int | None = None
    has_statement = False
    in_exec = False
    # Inside an EXEC SQL block whose first word has not been read yet: it
    # stands on a later line than `EXEC SQL` and decides what the block is.
    sql_undecided = False
    for line, code in code_lines:
        # Quoted text is blanked: a VALUE can read `'EXEC SQL COMMIT'`.
        upper = _mask_strings(code.upper()).strip()
        if in_exec:
            if sql_undecided and upper:
                sql_undecided = False
                if start is not None and not _SQL_DECLARATION.match(upper):
                    has_statement = True
            if "END-EXEC" in upper:
                in_exec = False
                sql_undecided = False
            continue
        if _PROGRAM.search(upper) or "PROCEDURE DIVISION" in upper:
            return None
        embedded = _EXEC.search(upper)
        if embedded:
            if "END-EXEC" not in upper:
                in_exec = True
            rest = upper[embedded.end():].strip()
            if embedded.group(1) == "SQL" and not rest:
                sql_undecided = in_exec
            elif start is not None and not (
                embedded.group(1) == "SQL" and _SQL_DECLARATION.match(rest)
            ):
                # An embedded statement is procedure code once a paragraph has begun.
                has_statement = True
            continue
        if start is None:
            header = _PARAGRAPH.match(upper)
            if header and header.group(1) not in _NOT_PARAGRAPHS:
                start = line
        elif _STATEMENT.match(upper):
            has_statement = True
    return start if has_statement else None


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
        source = _read_source_text(path)
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
        context: str | None = None,
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
        if context:
            edge["context"] = context
        edges.append(edge)

    add_node(file_id, path.name, 1, kind="file")

    code_lines = _code_lines(source)
    current_program = file_id
    current_scope = file_id
    in_procedure = False
    in_exec = False
    paragraphs: dict[tuple[str, str], str] = {}
    pending_performs: list[tuple[str, str, str, int]] = []
    pending_go_tos: list[tuple[str, str, str, int]] = []
    # A nested (contained) program's PROGRAM-ID switches current_program with
    # no record of what it switched FROM; everything after its own END
    # PROGRAM, including code physically back in the enclosing program, kept
    # attributing to the nested one forever. Each PROGRAM-ID pushes the
    # program it is nested under (possibly file_id, for a top-level one), and
    # END PROGRAM pops back to it, so sibling and nested programs alike
    # restore the right scope once their own body ends.
    program_stack: list[str] = []
    procedure_start = _procedure_copybook_start(code_lines)

    for line, code in code_lines:
        upper = code.upper().strip()

        if in_exec:
            if "END-EXEC" in upper:
                in_exec = False
            continue
        if _EXEC.search(upper):
            if "END-EXEC" not in upper:
                in_exec = True
            continue

        if _END_PROGRAM.search(upper):
            if program_stack:
                current_program = program_stack.pop()
                current_scope = current_program
                in_procedure = True
            continue

        program_match = _PROGRAM.search(upper)
        if program_match:
            name = program_match.group(1).upper()
            program_stack.append(current_program)
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

        if procedure_start is not None and line >= procedure_start:
            in_procedure = True

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
            # `PERFORM A THRU Z` runs the range A..Z, so both endpoints are
            # performed — link both. Only the entry paragraph was captured
            # before, leaving the range-end with no inbound edge ("what performs
            # Z?" answered nothing even though this paragraph does). Intermediate
            # paragraphs in the range are not individually linked (that needs
            # source ordering); the two endpoints are the reliable, common signal.
            for group in (match.group(1), match.group(2)):
                if group is None:
                    continue
                name = group.upper()
                if name not in _PERFORM_MODIFIERS:
                    pending_performs.append((current_scope, current_program, name, line))

        # `GO TO X` transfers control to paragraph X. Without an edge for it, a
        # paragraph that is only ever reached by a jump has no inbound edge at
        # all and looks like dead code, and a walk along the control flow stops
        # at every jump. `GO TO A B C DEPENDING ON X` can reach each of A, B, C.
        jumps = list(_GO_TO.finditer(masked))
        for index, match in enumerate(jumps):
            # Up to the next GO TO on the line, which has targets of its own.
            end = jumps[index + 1].start() if index + 1 < len(jumps) else len(masked)
            words = _GO_TO_WORDS.match(masked, match.end(), end)
            if words is None:
                continue
            for name in _go_to_targets(re.split(r"[\s,]+", words.group())):
                pending_go_tos.append((current_scope, current_program, name, line))

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
        else:
            # Not a paragraph of this file. It may be one of a copybook the
            # program copies, or of the program that copies this copybook:
            # resolve_cobol_copybook_performs decides once every file is read.
            raw_calls.append({
                "caller_nid": caller_id,
                "callee": name,
                "language": "cobol",
                "cobol_perform": True,
                "source_file": source_file,
                "source_location": f"L{line}",
            })

    # After the PERFORMs, so that a paragraph that both performs and jumps to
    # the same target keeps its plain PERFORM edge (one edge per pair).
    for caller_id, program_id, name, line in pending_go_tos:
        target_id = paragraphs.get((program_id, name.casefold()))
        if target_id is not None:
            add_edge(caller_id, target_id, "calls", line, context="go_to")

    clean_edges = [
        edge for edge in edges
        if edge["source"] in seen_ids
        and (edge["target"] in seen_ids or edge["relation"] == "imports_from")
    ]
    return {"nodes": nodes, "edges": clean_edges, "raw_calls": raw_calls}


def resolve_cobol_copybook_performs(
    per_file: list[dict], all_nodes: list[dict], all_edges: list[dict]
) -> None:
    """Link a PERFORM to a paragraph in another file of the same program.

    The compiler pastes every copybook into the program that copies it, so one
    program is spread over several files: a program can perform a paragraph of
    a copybook, a copybook a paragraph of the program, and one copybook a
    paragraph of another. The extractor reads a file at a time and leaves each
    PERFORM it cannot resolve there in ``raw_calls`` (``cobol_perform``).

    A program's files are the program itself and every copybook reached from
    it through ``imports_from`` edges, copybooks that copy copybooks included.
    A PERFORM is linked only to a paragraph of those files, and only when
    exactly one of them has a paragraph of that name. A copybook that several
    programs copy is part of each, so a PERFORM in it can get one edge per
    program. Nothing is matched by name across programs.
    """
    cobol: dict[str, str] = {}
    for node in all_nodes:
        metadata = node.get("metadata")
        if isinstance(metadata, dict) and metadata.get("language") == "cobol" and node.get("id"):
            cobol[node["id"]] = str(metadata.get("kind", ""))

    # A paragraph belongs to the program or, in a copybook, to the file that
    # contains it. A program's copybooks hang off the program node, a
    # copybook's own off its file node.
    owner: dict[str, str] = {}
    copied: dict[str, set[str]] = {}
    existing: set[tuple[str, str]] = set()
    for edge in all_edges:
        source, target, relation = edge.get("source"), edge.get("target"), edge.get("relation")
        if not isinstance(source, str) or not isinstance(target, str):
            continue
        if relation == "calls":
            existing.add((source, target))
        elif source not in cobol:
            continue
        elif relation == "contains" and cobol.get(target) in ("paragraph", "section"):
            owner[target] = source
        elif relation == "imports_from" and cobol.get(target) == "file":
            copied.setdefault(source, set()).add(target)

    labels = {node["id"]: str(node.get("label", "")).upper() for node in all_nodes if node.get("id") in owner}
    paragraphs: dict[str, dict[str, list[str]]] = {}
    for paragraph_id, scope in owner.items():
        paragraphs.setdefault(scope, {}).setdefault(labels[paragraph_id], []).append(paragraph_id)

    def files_of(root: str) -> set[str]:
        """The program (or copybook) and every copybook reached from it."""
        seen = {root}
        stack = [root]
        while stack:
            for copybook in copied.get(stack.pop(), ()):
                if copybook not in seen:
                    seen.add(copybook)
                    stack.append(copybook)
        return seen

    programs = {nid: files_of(nid) for nid in sorted(cobol) if cobol[nid] == "program"}

    for result in per_file:
        for call in result.get("raw_calls", []):
            if not call.get("cobol_perform"):
                continue
            caller = call.get("caller_nid")
            name = str(call.get("callee", "")).upper()
            if not isinstance(caller, str) or not name:
                continue
            scope = owner.get(caller, caller)
            units = [files for files in programs.values() if scope in files]
            if not units and cobol.get(scope) == "file":
                # A copybook no program in the corpus copies still has its own copybooks.
                units = [files_of(scope)]
            for files in units:
                candidates = sorted(
                    paragraph_id
                    for other in files
                    if other != scope
                    for paragraph_id in paragraphs.get(other, {}).get(name, ())
                )
                if len(candidates) != 1 or candidates[0] == caller:
                    continue
                pair = (caller, candidates[0])
                if pair in existing:
                    continue
                existing.add(pair)
                all_edges.append({
                    "source": caller,
                    "target": candidates[0],
                    "relation": "calls",
                    "context": "copybook_perform",
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": call.get("source_file", ""),
                    "source_location": call.get("source_location"),
                    "weight": 1.0,
                })
