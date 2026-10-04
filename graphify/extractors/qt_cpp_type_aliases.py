"""Accepted header alias shadows; no include execution or corpus discovery.

Facts retain original declarations and literal includes. Included aliases block
outer spelling fallback; this module never pretends to preprocess their targets.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path, PurePosixPath
import posixpath
import re

from graphify.extractors.qt_cpp_facts import qt_metadata
from graphify.extractors.qt_cpp_syntax import MAX_CPP_BYTES, QtCppError, lexical_code, walk

_IDENTIFIER = re.compile(r"[A-Za-z_]\w*")
_QUALIFIED = re.compile(r"[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*")
_DEPENDENCY = re.compile(rb"\b(?:using\s+(?:[A-Za-z_]\w*\s*=|(?:::)?[A-Za-z_]\w*::)|typedef\b|namespace\s+[A-Za-z_]\w*\s*=)")
_HEADERS = {".h", ".hpp", ".hh", ".hxx"}


def type_dependency_source(path):
    """Inspect only an explicitly admitted header, bounded like the native reader."""
    if Path(path).suffix.lower() not in _HEADERS:
        return False
    try:
        with Path(path).open("rb") as stream:
            source = stream.read(MAX_CPP_BYTES + 1)
    except OSError as exc:
        raise QtCppError("QT_CPP_READ", "Cannot read admitted header dependency") from exc
    # Comments must not admit an otherwise unrelated header. Include literals
    # are retained for the admission hint only; parsed facts provide authority.
    code = lexical_code(source)
    includes = re.finditer(rb"#\s*include", code)
    return bool(_DEPENDENCY.search(code) or any(re.match(rb'\s*"', source[match.end():]) for match in includes))


def _include(unit, syntax):
    literal = unit.field(syntax, "path")
    if not (literal.startswith('"') and literal.endswith('"')):
        return ""
    value = literal[1:-1]
    return value if value and len(value.encode()) <= 384 and "\\" not in value and not PurePosixPath(value).is_absolute() else ""


def add_type_dependency_facts(mapping, facts):
    """One source owns standalone namespace/class aliases and literal includes."""
    from graphify.extractors.qt_cpp_type_scope import NativeTypeScope
    index = NativeTypeScope(mapping.unit, mapping)
    for (scopes, name), records in index.bindings.items():
        if any(scope[0] == "block" for scope in scopes):
            continue
        scope = scopes[-1] if scopes else ("global", "")
        for syntax, target, kind, conditional in records:
            if kind not in {"alias_declaration", "type_definition", "using_declaration", "namespace_alias_definition"}:
                continue
            facts.add("type_alias", name, syntax, scope_name=scope[1], scope_kind=scope[0],
                      binding_kind=kind, target_spelling=target, conditional=conditional,
                      status="source", reason="included_alias_target_unverified")
    for syntax in walk(mapping.unit.tree):
        if syntax.type == "preproc_include" and (literal := _include(mapping.unit, syntax)):
            facts.add("type_include", literal, syntax, value=literal, status="source")


def _accepted(node):
    md = qt_metadata(node)
    if md.get("kind") not in {"type_alias", "type_include"}:
        return None
    file, span = node.get("source_file"), md.get("span", {})
    valid_file = (isinstance(file, str) and file and "\\" not in file and ":" not in file
                  and not PurePosixPath(file).is_absolute() and ".." not in PurePosixPath(file).parts)
    numeric = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
    valid_span = (isinstance(span, dict) and all(type(span.get(key)) is int and span[key] >= 0 for key in numeric)
                  and span["start_byte"] < span["end_byte"] and span["start_row"] <= span["end_row"]
                  and (span["start_row"] != span["end_row"] or span["start_column"] < span["end_column"]))
    if not valid_file or not valid_span or node.get("_origin") != "ast" or node.get("file_type") != "code":
        raise ValueError("QT_METADATA: invalid type dependency provenance")
    if node.get("source_location") != f'L{span["start_row"] + 1}-L{span["end_row"] + 1}':
        raise ValueError("QT_METADATA: invalid type dependency location")
    if md["kind"] == "type_alias" and node.get("label") != f'Qt type_alias: {md.get("raw_name", "")}':
        raise ValueError("QT_METADATA: invalid type dependency name")
    if md["kind"] == "type_alias":
        scope, name = md.get("scope_name"), md.get("raw_name")
        if (not isinstance(scope, str) or (scope and not _QUALIFIED.fullmatch(scope))
                or not isinstance(name, str) or not _IDENTIFIER.fullmatch(name)
                or md.get("scope_kind") not in {"global", "namespace", "class"}
                or (md["scope_kind"] == "global") != (scope == "")):
            raise ValueError("QT_METADATA: invalid type alias scope")
    elif md.get("value") != md.get("raw_name") or not isinstance(md.get("value"), str):
        raise ValueError("QT_METADATA: invalid type include literal")
    return file, md


class IncludedAliasShadows:
    """Immutable accepted dependency snapshot, with bounded include graph walks."""

    def __init__(self, unit, nodes):
        self.unit = unit
        self.aliases, self.includes = defaultdict(set), defaultdict(set)
        paths = set()
        for node in nodes:
            record = _accepted(node)
            if record is None:
                continue
            file, md = record
            paths.add(file)
            if md["kind"] == "type_alias":
                self.aliases[file].add((md["scope_name"], md["raw_name"]))
            else:
                self.includes[file].add(md["value"])
        self.paths = frozenset(paths)
        self.direct = tuple((syntax.end_byte, _include(unit, syntax)) for syntax in walk(unit.tree)
                            if syntax.type == "preproc_include" and _include(unit, syntax))

    def _target(self, owner, literal):
        # Quoted includes search the source directory before the explicit scan
        # root. Only accepted fact paths participate; no header is opened here.
        for base in (posixpath.dirname(owner), ""):
            target = posixpath.normpath(posixpath.join(base, literal))
            if target in self.paths and not target.startswith("../"):
                return target
        return ""

    def blocks(self, scope, name, byte):
        key = scope[-1][1] if scope and scope[-1][0] != "block" else "" if not scope else None
        if key is None:
            return False
        pending = [self._target(self.unit.relative_file, literal) for end, literal in self.direct if end <= byte]
        seen = set()
        while pending:
            file = pending.pop()
            if not file or file in seen:
                continue
            seen.add(file)
            if len(seen) > 128:
                raise QtCppError("QT_CPP_LIMIT", "Type dependency walk exceeds 128 accepted headers")
            if (key, name) in self.aliases[file]:
                return True
            pending.extend(self._target(file, literal) for literal in self.includes[file])
        return False
