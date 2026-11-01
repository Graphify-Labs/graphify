"""Bounded lexical QRC output pairs; no CMake evaluation or inherited-value proof."""
from __future__ import annotations

import re
from collections import Counter

from graphify.extractors.qml_cmake_properties import properties_for, reject
from graphify.extractors.qml_cmake_syntax import commands
from graphify.extractors.qml_project_read import MetadataError, literal_path
from graphify.qml_resolution_types import fact_edge

_RESOURCES = {"qt_add_resources", "qt6_add_resources"}
_MODULES = {"qt_add_qml_module", "qt6_add_qml_module"}
# These names delimit the deliberately small source-local profile. Includes,
# package discovery, user functions and writers can alter variables implicitly.
_PREFIX = _RESOURCES | _MODULES | {
    "cmake_minimum_required", "project", "qt_add_executable", "qt6_add_executable",
    "set_target_properties", "set_source_files_properties", "target_sources",
}
_IDENTIFIER = re.compile(r"[A-Za-z_][A-Za-z_0-9]*")
_MAX_COMMANDS = 10_000


def command_inventory(text):
    """Bound the retained inventory before the whole-file eligibility prepass."""
    inventory = []
    for command in commands(text):
        if len(inventory) == _MAX_COMMANDS:
            raise MetadataError("QML_PROJECT_LIMIT", "cmake_command_limit")
        inventory.append(command)
    return inventory


def output_pairs(inventory, source_file, text):
    """Find adjacent pairs without treating arbitrary variable text as expansion.

    Every token identifier participates in the census, including literal paths.
    Exactly the producer name and consumer reference may mention the output.
    This conservative source-local contract does not inspect inherited values.
    """
    names, counts, property_paths = [], Counter(), set()
    for command in inventory:
        identifiers = [command.name]
        for token in command.tokens:
            identifiers.extend(_IDENTIFIER.findall(token.value))
        names.append(identifiers)
        counts.update(identifiers)
        # QRC input properties have no accepted interpretation in this profile,
        # including later/scoped declarations that cannot rewrite this input.
        if command.name == "set_source_files_properties":
            for token in command.tokens:
                if token.value == "PROPERTIES":
                    break
                path = literal_path(source_file, token.value)
                if path is not None:
                    property_paths.add(path)
    pairs, seen, blocked = {}, set(), False
    for index, command in enumerate(inventory):
        tokens = command.tokens
        if (not blocked and not command.scoped and command.name in _RESOURCES
                and len(tokens) >= 2 and not any(token.dynamic for token in tokens)):
            variable = tokens[0].value
            paths = [literal_path(source_file, token.value) for token in tokens[1:]]
            if (_IDENTIFIER.fullmatch(variable) and variable not in seen
                    and counts[variable] == 2 and all(path is not None for path in paths)
                    and len(set(paths)) == len(paths) and not property_paths.intersection(paths)
                    and all(token.value.lower().endswith(".qrc") for token in tokens[1:])
                    and index + 1 < len(inventory)):
                consumer = inventory[index + 1]
                use = consumer.tokens
                if (not consumer.scoped and consumer.name == "target_sources" and len(use) == 3
                        and not use[0].dynamic and use[1].value == "PRIVATE"
                        and use[2].value == "${" + variable + "}"
                        and text[use[2].start:use[2].end] == use[2].value):
                    pairs[index] = consumer
        seen.update(names[index])
        if command.scoped or command.name not in _PREFIX:
            blocked = True
    return pairs


def add_output_resources(facts, command, consumer, modules, properties, consumed):
    """Bind literal QRC inputs to the current unique module and explicit use site."""
    owners = modules.get(consumer.tokens[0].value, [])
    inputs = command.tokens[1:]
    paths = [literal_path(facts.file, token.value) for token in inputs]
    if (len(owners) != 1 or any(path in consumed for path in paths)
            or any(properties_for(facts, token, properties) for token in inputs)):
        reject(facts, command, "resource_output_module_or_input_unavailable")
        return
    module, key = owners[0]
    variable = command.tokens[0].value
    sources = []
    for token, path in zip(inputs, paths):
        consumed.add(path)
        sources.append(facts.add_chars(
            "qt_source", (key, "qrc", token.value), token.value, token.start, token.end,
            owner=module, module_key=key, value=token.value, source_kind="qrc",
            output_variable=variable, generated=False))
    token = consumer.tokens[2]
    use = facts.add_chars("qt_generated_resource_use", (key, variable, tuple(paths)),
                          token.value, token.start, token.end, owner=module,
                          module_key=key, output_variable=variable, generated=True)
    # The source reference points to the actual QRC declaration. No generated
    # C++ filename, native provider or XML alias is synthesized at this boundary.
    for source in sources:
        facts.edges.append(fact_edge(use["id"], source["id"], "references", use,
                                     "qt_generated_resource_input", span=facts.span(
                                         facts.byte_offsets[token.start],
                                         facts.byte_offsets[token.end])))
