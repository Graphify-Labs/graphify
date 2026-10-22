"""Qt 6 qmake module facts with bounded current-file paths and lexical coverage."""
from __future__ import annotations

import hashlib
from pathlib import Path

from graphify.extractors.qml_cmake import uri, version
from graphify.extractors.qml_project_read import ProjectFacts, extract_project, failure
from graphify.extractors.qml_qmake_values import assignments


def parse_qmake(source: bytes | str, *, relative_file="project.pro") -> dict:
    try:
        facts = ProjectFacts(source, relative_file, "qmake")
        accepted = assignments(facts)
        names = accepted.get("QML_IMPORT_NAME", [])
        if len(names) > 1 or (names and not uri(names[0].value)):
            facts.reject("invalid_module_uri")
        if not names or facts.diagnostics:
            _import_paths(facts, accepted, None, None)
            return facts.result()
        entry = names[0]
        name, start, end = entry.value, entry.start, entry.end
        ver_entries = accepted.get("QML_IMPORT_VERSION", [])
        major, minor = accepted.get("QML_IMPORT_MAJOR_VERSION", []), accepted.get("QML_IMPORT_MINOR_VERSION", [])
        if len(ver_entries) > 1 or len(major) > 1 or len(minor) > 1:
            facts.reject("invalid_module_version")
            return facts.result()
        ver = version(ver_entries[0].value) if ver_entries else version(
            major[0].value + "." + (minor[0].value if minor else "0")) if major else None
        if ver is None or (ver_entries and (major or minor)):
            facts.reject("missing_or_conflicting_module_version")
            return facts.result()
        targets = accepted.get("TARGET", [])
        if len(targets) > 1:
            facts.reject("invalid_target_name")
            return facts.result()
        target = targets[0].value if len(targets) == 1 else Path(relative_file).stem
        key = hashlib.sha256(repr((relative_file, target, name)).encode()).hexdigest()
        module = facts.add_chars("qt_module", (target, name), name, start, end,
                                 uri=name, major=ver[0], minor=ver[1], target_name=target,
                                 module_key=key, build_system="qmake", generated=False,
                                 version_origin="literal_version" if ver_entries else
                                 "literal_major_minor" if minor else "base_major_registration",
                                 minor_upper_bound_known=bool(ver_entries or minor),
                                 resource_prefix=None, no_resource_target_path=False)
        # Accepted lexical paths stay relative to this metadata file. Project
        # indexing joins only already admitted source facts; no disk discovery.
        for group, kind in (("SOURCES", "cpp"), ("HEADERS", "cpp"), ("QML_FILES", "qml"),
                            ("DISTFILES", "distribution"), ("RESOURCES", "qrc")):
            for entry in accepted.get(group, []):
                facts.add_chars("qt_source", (key, kind, entry.value), entry.value,
                                entry.start, entry.end, owner=module,
                                module_key=key, value=entry.value, source_kind=kind,
                                source_value=entry.source_value, path_origin=entry.path_origin)
        # Tooling hints and build scanner roots are separate facts. Neither is
        # an application runtime search path or an implicit analysis root.
        _import_paths(facts, accepted, module, key)
        return facts.result()
    except (UnicodeError, ValueError) as exc:
        return failure(relative_file, "qmake", exc)


def _import_paths(facts, accepted, module, key):
    """Ordinary .pro files may declare hints without creating a QML module."""
    for group, visibility in (("QML_IMPORT_PATH", "tooling"), ("QMLPATHS", "build")):
        for entry in accepted.get(group, []):
            facts.add_chars("qt_import_path", (key, group, entry.value), entry.value,
                            entry.start, entry.end, owner=module, module_key=key,
                            value=entry.value, visibility=visibility, qmake_variable=group,
                            source_value=entry.source_value, path_origin=entry.path_origin)


def extract_qmake(path: Path, *, root: Path | None = None) -> dict:
    return extract_project(path, root, "qmake", parse_qmake)
