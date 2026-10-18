"""Source-local CMake source properties with explicit irrelevant native metadata."""
from __future__ import annotations

from pathlib import PurePosixPath

from graphify.extractors.qml_project_read import literal_path


_NATIVE_SUFFIXES = {".c", ".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
_RC_COMPILE_PROPERTIES = {"INCLUDE_DIRECTORIES", "OBJECT_DEPENDS"}


def native_source(token):
    """HEADER_FILE_ONLY controls object compilation, not AUTOMOC header ownership."""
    return PurePosixPath(token.value).suffix.lower() in _NATIVE_SUFFIXES


def reject(facts, command, reason="source_mutation_outside_literal_subset"):
    facts.reject(reason, facts.byte_offsets[command.start], facts.byte_offsets[command.end])


def native_resource(tokens):
    """A literal RC input cannot expose a QML/C++ provider or runtime QRC URL."""
    return bool(tokens) and all(not token.dynamic and
                               PurePosixPath(token.value).suffix.lower() == ".rc"
                               for token in tokens)


def source_properties(facts, command, properties, consumed):
    """Apply only explicitly supported properties; later runtime mutations fail closed."""
    tokens = command.tokens
    values = [token.value for token in tokens]
    if "PROPERTIES" not in values:
        reject(facts, command)
        return
    split = values.index("PROPERTIES")
    paths, pairs = tokens[:split], tokens[split + 1:]
    # CMake consumes these argument values as scope selectors even when quoted.
    # Neither local property authority nor the RC exemption can resolve another
    # directory's scope. ./DIRECTORY remains a distinct literal path spelling.
    if any(token.value in {"DIRECTORY", "TARGET_DIRECTORY"} for token in paths):
        reject(facts, command, "unsupported_source_property_scope")
        return
    if not paths or not pairs or len(pairs) % 2 or any(token.dynamic for token in paths):
        reject(facts, command)
        return
    names = [token.value for token in pairs[::2]]
    # These properties affect only RC compilation/rebuild prerequisites, never
    # QML/native membership or QRC URLs. Values and repeated assignments stay
    # opaque: no expansion, dependency read, or provider fact is authorized.
    if native_resource(paths) and set(names) <= _RC_COMPILE_PROPERTIES:
        return
    allowed = {"QT_RESOURCE_ALIAS", "QT_QML_SINGLETON_TYPE", "HEADER_FILE_ONLY"}
    if (command.scoped or len(set(names)) != len(names) or set(names) - allowed
            or any(token.dynamic for token in pairs)):
        reject(facts, command)
        return
    updates = dict(zip(names, (token.value for token in pairs[1::2])))
    if any(updates.get(name, "TRUE") not in {"TRUE", "FALSE", "ON", "OFF", "1", "0"}
           for name in {"QT_QML_SINGLETON_TYPE", "HEADER_FILE_ONLY"}):
        reject(facts, command, "unsupported_source_property_value")
        return
    for token in paths:
        path = literal_path(facts.file, token.value)
        key = path if path is not None else token.value
        if key in consumed:
            reject(facts, command, "source_property_after_metadata_use")
            continue
        properties.setdefault(key, {}).update(updates)
        # A source property remains its own declaration even when it is tooling
        # only; it does not authorize reading another file or executing a script.
        facts.add_chars("qt_source_property", (token.value, tuple(updates.items())), token.value,
                        token.start, command.end, value=token.value, properties=updates)


def properties_for(facts, token, properties):
    path = literal_path(facts.file, token.value)
    return properties.get(path if path is not None else token.value, {})


def target_sources(facts, command, modules, properties, consumed):
    """Attach literal private implementation files to exactly one local module."""
    tokens = command.tokens
    if len(tokens) < 3 or tokens[1].value != "PRIVATE" or tokens[0].dynamic:
        reject(facts, command)
        return
    sources = tokens[2:]
    if native_resource(sources):
        return
    owners = modules.get(tokens[0].value, [])
    if command.scoped or len(owners) != 1 or any(token.dynamic for token in sources):
        reject(facts, command)
        return
    module, key = owners[0]
    for token in sources:
        props = properties_for(facts, token, properties)
        header_only = props.get("HEADER_FILE_ONLY") in {"TRUE", "ON", "1"}
        tooling = header_only and not native_source(token)
        if not tooling and not native_source(token):
            reject(facts, command, "unsupported_target_source_kind")
            continue
        # Native headers remain target/AUTOMOC inputs regardless of object-file
        # compilation. Only explicit nonnative IDE inputs lack provider authority.
        kind = "qt_tooling_source" if tooling else "qt_source"
        fields = {"header_file_only": header_only} if "HEADER_FILE_ONLY" in props else {}
        consumed.add(literal_path(facts.file, token.value) or token.value)
        facts.add_chars(kind, (key, "tooling" if tooling else "cpp", token.value),
                        token.value, token.start, token.end, owner=module, module_key=key,
                        value=token.value, source_kind="tooling" if tooling else "cpp", **fields)
