"""Qt 6 qmake literal assignment facts with conditional/expansion rejection."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from graphify.extractors.qml_cmake import uri, version
from graphify.extractors.qml_project_read import ProjectFacts, extract_project, failure

_INTEREST = {"TARGET", "QML_IMPORT_NAME", "QML_IMPORT_VERSION", "QML_IMPORT_MAJOR_VERSION",
             "QML_IMPORT_MINOR_VERSION", "SOURCES", "HEADERS", "RESOURCES", "DISTFILES",
             "QML_FILES", "QML_IMPORT_PATH"}


def _statements(text):
    """Preserve physical spans across line continuation; don't evaluate functions."""
    start, pos, pending = 0, 0, ""
    for raw in text.splitlines(keepends=True):
        body = raw.rstrip("\r\n")
        if pos == 0:
            body = body.removeprefix("\ufeff")
        quote, value = "", ""
        for char in body:
            if char in "\"'":
                quote = "" if quote == char else char if not quote else quote
            if char == "#" and not quote:
                break
            value += char
        continued = value.rstrip().endswith("\\")
        pending += value.rstrip()[:-1] + " " if continued else value
        pos += len(raw)
        if not continued:
            yield start, pos, pending.strip()
            start, pending = pos, ""
    if pending:
        yield start, pos, pending.strip()


def _values(value):
    tokens = re.findall(r'"[^"\r\n]*"|\'[^\'\r\n]*\'|[^\s]+', value)
    if any(any(char in token for char in "$(){};*") for token in tokens):
        return None
    if sum(token.count('"') for token in tokens) % 2 or sum(token.count("'") for token in tokens) % 2:
        return None
    return [token[1:-1] if token.startswith(('"', "'")) else token for token in tokens]


def parse_qmake(source: bytes | str, *, relative_file="project.pro") -> dict:
    try:
        facts = ProjectFacts(source, relative_file, "qmake")
        assignments, scope = {}, 0
        for start, end, statement in _statements(facts.text):
            if not statement:
                continue
            if statement == "}":
                scope -= 1
                if scope < 0:
                    facts.reject("unbalanced_qmake_scope")
                continue
            if "{" in statement or "}" in statement:
                scope += statement.count("{") - statement.count("}")
                facts.reject("conditional_qmake_scope", facts.byte_offsets[start], facts.byte_offsets[end])
                continue
            match = re.fullmatch(r"([A-Za-z_][A-Za-z_0-9]*)\s*(=|\+=|-=|\*=|~=)\s*(.*)", statement)
            if not match:
                facts.reject("unsupported_qmake_statement", facts.byte_offsets[start], facts.byte_offsets[end])
                continue
            key, operator, value = match.groups()
            if key not in _INTEREST:
                continue
            values = _values(value)
            if scope or values is None or operator not in {"=", "+="}:
                facts.reject("conditional_or_expanded_qmake_value", facts.byte_offsets[start], facts.byte_offsets[end])
                continue
            entries = [(entry, start, end) for entry in values]
            assignments[key] = assignments.get(key, []) + entries if operator == "+=" else entries
        if scope:
            facts.reject("unbalanced_qmake_scope")
        names = assignments.get("QML_IMPORT_NAME", [])
        if len(names) > 1 or (names and not uri(names[0][0])):
            facts.reject("invalid_module_uri")
        if not names or facts.diagnostics:
            return facts.result()
        name, start, end = names[0]
        ver_entries = assignments.get("QML_IMPORT_VERSION", [])
        major, minor = assignments.get("QML_IMPORT_MAJOR_VERSION", []), assignments.get("QML_IMPORT_MINOR_VERSION", [])
        if len(ver_entries) > 1 or len(major) > 1 or len(minor) > 1:
            facts.reject("invalid_module_version")
            return facts.result()
        ver = version(ver_entries[0][0]) if ver_entries else version(
            major[0][0] + "." + (minor[0][0] if minor else "0")) if major else None
        if ver is None or (ver_entries and (major or minor)):
            facts.reject("missing_or_conflicting_module_version")
            return facts.result()
        targets = assignments.get("TARGET", [])
        if len(targets) > 1:
            facts.reject("invalid_target_name")
            return facts.result()
        target = targets[0][0] if len(targets) == 1 else Path(relative_file).stem
        key = hashlib.sha256(repr((relative_file, target, name)).encode()).hexdigest()
        module = facts.add_chars("qt_module", (target, name), name, start, end,
                                 uri=name, major=ver[0], minor=ver[1], target_name=target,
                                 module_key=key, build_system="qmake", generated=False,
                                 version_origin="literal_version" if ver_entries else
                                 "literal_major_minor" if minor else "base_major_registration",
                                 minor_upper_bound_known=bool(ver_entries or minor),
                                 resource_prefix=None, no_resource_target_path=False)
        for group, kind in (("SOURCES", "cpp"), ("HEADERS", "cpp"), ("QML_FILES", "qml"),
                            ("DISTFILES", "distribution"), ("RESOURCES", "qrc")):
            for value, start, end in assignments.get(group, []):
                facts.add_chars("qt_source", (key, kind, value), value, start, end, owner=module,
                                module_key=key, value=value, source_kind=kind)
        for value, start, end in assignments.get("QML_IMPORT_PATH", []):
            facts.add_chars("qt_import_path", (key, value), value, start, end, owner=module,
                            module_key=key, value=value, visibility="tooling")
        return facts.result()
    except (UnicodeError, ValueError) as exc:
        return failure(relative_file, "qmake", exc)


def extract_qmake(path: Path, *, root: Path | None = None) -> dict:
    return extract_project(path, root, "qmake", parse_qmake)
