"""Qt 6 literal qt_add_qml_module records; never execute CMake or expand variables."""
from __future__ import annotations

import hashlib
import re
from pathlib import Path

from graphify.extractors.qml_cmake_syntax import commands
from graphify.extractors.qml_project_read import ProjectFacts, extract_project, failure

_SINGLE = {"URI", "VERSION", "RESOURCE_PREFIX", "OUTPUT_DIRECTORY", "TYPEINFO",
           "PLUGIN_TARGET", "CLASS_NAME", "NAMESPACE"}
_LIST = {"QML_FILES", "SOURCES", "RESOURCES", "IMPORTS", "DEPENDENCIES", "OPTIONAL_IMPORTS",
         "DEFAULT_IMPORTS", "IMPORT_PATH", "PAST_MAJOR_VERSIONS"}
_FLAGS = {"STATIC", "SHARED", "NO_PLUGIN", "NO_PLUGIN_OPTIONAL", "NO_CREATE_PLUGIN_TARGET",
          "NO_GENERATE_PLUGIN_SOURCE", "NO_GENERATE_QMLTYPES", "NO_GENERATE_QMLDIR",
          "NO_GENERATE_EXTRA_QMLDIRS", "NO_LINT", "NO_CACHEGEN", "NO_RESOURCE_TARGET_PATH",
          "NO_IMPORT_SCAN", "DESIGNER_SUPPORTED"}
_KEYS = _SINGLE | _LIST | _FLAGS


def version(value: str, *, optional_minor=False):
    match = re.fullmatch(r"(\d{1,6})(?:\.(\d{1,6}))?", value)
    if not match or (not optional_minor and match[2] is None):
        return None
    return int(match[1]), int(match[2]) if match[2] is not None else None


def uri(value: str) -> bool:
    return bool(value) and all(part.isidentifier() for part in value.split("."))


def _sections(tokens):
    sections, active = {}, None
    for token in tokens:
        if token.value in _KEYS:
            if token.value in sections:
                return None
            active = token.value
            sections[active] = []
        elif active is None or active in _FLAGS:
            return None
        else:
            sections[active].append(token)
    if any(len(sections[key]) != 1 for key in sections if key in _SINGLE):
        return None
    return sections


def _module(facts, command):
    start, end = facts.byte_offsets[command.start], facts.byte_offsets[command.end]
    tokens = command.tokens
    if command.scoped or any(token.dynamic for token in tokens):
        facts.reject("conditional_or_expanded_qml_module", start, end)
        return
    sections = _sections(tokens[1:]) if tokens else None
    if not sections or "URI" not in sections:
        facts.reject("unsupported_qml_module_arguments", start, end)
        return
    name = sections["URI"][0].value
    ver = version(sections["VERSION"][0].value) if "VERSION" in sections else (None, None)
    if not uri(name) or ver is None:
        facts.reject("invalid_module_uri_or_version", start, end)
        return
    target = tokens[0].value
    key = hashlib.sha256(repr((facts.file, target, name)).encode()).hexdigest()
    scalar = {key.lower(): values[0].value for key, values in sections.items() if key in _SINGLE}
    module = facts.add("qt_module", (target, name), name, start, end,
                       uri=name, major=ver[0], minor=ver[1], target_name=target, module_key=key,
                       build_system="cmake", generated=False,
                       resource_prefix=scalar.get("resource_prefix"),
                       output_directory=scalar.get("output_directory"),
                       no_resource_target_path="NO_RESOURCE_TARGET_PATH" in sections)
    for group, kind in (("QML_FILES", "qml"), ("SOURCES", "cpp"), ("RESOURCES", "resource")):
        for token in sections.get(group, []):
            facts.add_chars("qt_source", (key, kind, token.value), token.value, token.start, token.end,
                            owner=module, module_key=key, value=token.value, source_kind=kind)
    for group in ("IMPORTS", "DEPENDENCIES", "OPTIONAL_IMPORTS", "DEFAULT_IMPORTS"):
        if any(token.value == "TARGET" for token in sections.get(group, [])):
            facts.reject("target_import_requires_policy_and_target_resolution", start, end)
            continue
        for token in sections.get(group, []):
            parts = token.value.split("/")
            dep_ver = version(parts[1], optional_minor=True) if len(parts) == 2 else (None, None)
            auto = len(parts) == 2 and parts[1] == "auto"
            if len(parts) > 2 or not uri(parts[0]) or (dep_ver is None and not auto):
                facts.reject("unsupported_module_import", facts.byte_offsets[token.start], facts.byte_offsets[token.end])
                continue
            facts.add_chars("qt_module_import", (key, group, token.value), parts[0], token.start, token.end,
                            owner=module, module_key=key, uri=parts[0], major=dep_ver[0] if dep_ver else None,
                            minor=dep_ver[1] if dep_ver else None, auto=auto,
                            visibility="import" if group == "IMPORTS" else group.lower())
    for token in sections.get("IMPORT_PATH", []):
        facts.add_chars("qt_import_path", (key, token.value), token.value, token.start, token.end,
                        owner=module, module_key=key, value=token.value)
    for option in ("PAST_MAJOR_VERSIONS",):
        if option in sections:
            facts.reject("past_major_versions_not_materialized", start, end)


def parse_cmake(source: bytes | str, *, relative_file="CMakeLists.txt") -> dict:
    """Supported declarations are literal, flat and source-local, with exact spans."""
    try:
        facts = ProjectFacts(source, relative_file, "cmake")
        for command in commands(facts.text):
            if command.name in {"qt_add_qml_module", "qt6_add_qml_module"}:
                _module(facts, command)
            elif command.name in {"qt_target_qml_sources", "target_sources",
                                  "set_source_files_properties", "set_property"}:
                # These can change the module's source/version/resource metadata.
                facts.reject("source_mutation_outside_literal_subset", facts.byte_offsets[command.start],
                             facts.byte_offsets[command.end])
        return facts.result()
    except (UnicodeError, ValueError) as exc:
        return failure(relative_file, "cmake", exc)


def extract_cmake(path: Path, *, root: Path | None = None) -> dict:
    return extract_project(path, root, "cmake", parse_cmake)
