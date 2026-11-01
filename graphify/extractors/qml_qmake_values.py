"""Bounded qmake lexical assignments with original positions and no evaluation.

This reader owns statement coverage and literal path interpretation. The caller
owns module facts; uncertain metadata cannot become module lookup authority.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from graphify.extractors.qml_project_read import literal_path


PATH_KEYS = {"SOURCES", "HEADERS", "RESOURCES", "DISTFILES", "QML_FILES",
             "QML_IMPORT_PATH", "QMLPATHS"}
INTEREST = PATH_KEYS | {"TARGET", "QML_IMPORT_NAME", "QML_IMPORT_VERSION",
                        "QML_IMPORT_MAJOR_VERSION", "QML_IMPORT_MINOR_VERSION"}
_ASSIGNMENT = re.compile(r"([A-Za-z_][A-Za-z_0-9.]*)\s*(=|\+=|-=|\*=|~=)\s*(.*)")
_TOKENS = re.compile(r'"[^"\r\n]*"|\x27[^\x27\r\n]*\x27|[^\s]+')
_MAX_SCOPES = 64


@dataclass(frozen=True)
class QmakeValue:
    value: str
    source_value: str
    start: int
    end: int
    path_origin: str = "literal"


def statements(text):
    """Join continuations with a position map into the unmodified source text."""
    pending, positions, pos = "", [], 0
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        quote, length = "", len(body)
        for index, char in enumerate(body):
            if char in "\"'":
                quote = "" if quote == char else char if not quote else quote
            if char == "#" and not quote:
                length = index
                break
        value = body[:length]
        if pos == 0 and value.startswith("\ufeff"):
            value = value[1:]
            offset = 1
        else:
            offset = 0
        continued = value.rstrip().endswith("\\")
        if continued:
            value = value.rstrip()[:-1]
        pending += value
        positions.extend(range(pos + offset, pos + offset + len(value)))
        if continued:
            pending += " "
            positions.append(pos + len(body))
        elif pending.strip():
            yield pending, positions
            pending, positions = "", []
        else:
            pending, positions = "", []
        pos += len(raw)
    if pending.strip():
        yield pending, positions


def values(text, offset, positions, key, source_file):
    """Interpret only an exact PWD prefix; reject all other expansions and escapes."""
    result, previous_end = [], 0
    for token in _TOKENS.finditer(text):
        spelling = token.group()
        if ((result and token.start() == previous_end) or
                spelling.count('"') % 2 or spelling.count("'") % 2 or
                (not spelling.startswith(('"', "'")) and any(char in spelling for char in "\"'"))):
            return None, "conditional_or_expanded_qmake_value"
        previous_end = token.end()
        value = spelling[1:-1] if spelling.startswith(('"', "'")) else spelling
        source_value = value
        origin = "literal"
        if key in PATH_KEYS and (value == "$$PWD" or value.startswith("$$PWD/")):
            value, origin = value[5:].lstrip("/") or ".", "current_file_pwd"
        if any(char in value for char in "$(){};*"):
            return None, "conditional_or_expanded_qmake_value"
        if key in PATH_KEYS:
            if max(len(value.encode("utf-8")), len(source_value.encode("utf-8"))) > 384:
                return None, "qmake_path_limit"
            if literal_path(source_file, value) is None:
                return None, "qmake_path_outside_accepted_root"
        start = positions[offset + token.start()]
        end = positions[offset + token.end() - 1] + 1
        result.append(QmakeValue(value, source_value, start, end, origin))
    return result, None


def assignments(facts):
    """Retain observable lexical coverage while withholding failed module authority."""
    accepted, scope = {}, 0
    for statement, positions in statements(facts.text):
        text = statement.strip()
        start, end = positions[0], positions[-1] + 1

        # Balanced scope delimiters have no branch truth. Relevance belongs to
        # statements inside them, so an unrelated toolchain scope is harmless.
        if text == "}":
            scope -= 1
            if scope < 0:
                facts.reject("unbalanced_qmake_scope")
                scope = 0
            continue
        if text in {"} else {", "}else{"}:
            if scope == 0:
                facts.reject("unbalanced_qmake_scope")
            continue
        if text.endswith("{") and not _ASSIGNMENT.fullmatch(text):
            scope += 1
            if scope > _MAX_SCOPES:
                facts.reject("qmake_scope_limit")
                return accepted
            continue

        # A log string can mention qmake assignment syntax without changing
        # project facts. Classify known display statements before searching keys.
        if re.fullmatch(r"(?:message|warning)\([^\r\n]*\)", text):
            _coverage(facts, "qt_qmake_statement", "ignored", "unrelated_build_statement",
                      start, end, conditional=bool(scope))
            continue

        match = _ASSIGNMENT.fullmatch(statement.strip())
        conditional = bool(scope)
        if match:
            leading = len(statement) - len(statement.lstrip())
        else:
            # A condition prefix remains opaque. It may contain qmake test
            # functions; finding an assignment is never evaluating the prefix.
            candidates = list(_ASSIGNMENT.finditer(statement))
            match = candidates[-1] if candidates else None
            leading, conditional = 0, True
        if not match:
            _coverage(facts, "qt_qmake_statement", "unresolved", "unsupported_qmake_statement",
                      start, end, conditional=bool(scope))
            facts.reject("unsupported_qmake_statement", facts.byte_offsets[start], facts.byte_offsets[end])
            continue
        key, operator, value = match.groups()
        if key == "PWD":
            facts.reject("qmake_pwd_reassignment", facts.byte_offsets[start], facts.byte_offsets[end])
            continue
        if key not in INTEREST:
            _coverage(facts, "qt_qmake_statement", "ignored", "unrelated_build_setting",
                      start, end, conditional=conditional, qmake_variable=key)
            continue
        if conditional:
            _coverage(facts, "qt_qmake_statement", "unresolved", "conditional_qmake_value",
                      start, end, conditional=True, qmake_variable=key)
            facts.reject("conditional_or_expanded_qmake_value", facts.byte_offsets[start], facts.byte_offsets[end])
            continue
        entries, reason = values(value, leading + match.start(3), positions, key, facts.file)
        if entries is None or operator not in {"=", "+="}:
            facts.reject(reason or "conditional_or_expanded_qmake_value",
                         facts.byte_offsets[start], facts.byte_offsets[end])
            continue
        # Individual lexical values remain inspectable even if a later unknown
        # mutation blocks the file's module authority. They never enter lookup.
        for entry in entries:
            facts.add_chars("qt_qmake_assignment", (key, operator, entry.value), key,
                            entry.start, entry.end, status="observed", conditional=False,
                            reason="unconditional_literal_assignment", qmake_variable=key,
                            operator=operator, value=entry.value, source_value=entry.source_value,
                            path_origin=entry.path_origin)
        accepted[key] = accepted.get(key, []) + entries if operator == "+=" else entries
    if scope:
        facts.reject("unbalanced_qmake_scope")
    return accepted


def _coverage(facts, kind, status, reason, start, end, **fields):
    """Coverage records use safe categories, never unbounded source/provider text."""
    variable = fields.get("qmake_variable", "statement")
    facts.add_chars(kind, (variable, status, reason), variable, start, end,
                    status=status, reason=reason, **fields)
