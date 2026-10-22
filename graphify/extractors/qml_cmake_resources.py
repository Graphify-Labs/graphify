"""Literal target-form Qt resource mappings without policy/default expansion."""
from __future__ import annotations

from graphify.extractors.qml_cmake_properties import properties_for, reject
from graphify.extractors.qml_project_read import literal_path
from graphify.extractors.qml_resources import resource_url


def add_resources(facts, command, properties, consumed):
    """Record immediate PREFIX/FILES mappings with the aliases in effect here."""
    tokens = command.tokens
    values = [token.value for token in tokens]
    # Variable-output form, inferred prefixes, BASE/path rewriting, generated
    # files and arbitrary Qt/CMake options need their own evidence contract.
    # CMake argument keywords remain keywords when quoted. A path such as
    # ./DISCARD_FILE_CONTENTS is distinct, but the unsupported empty-content flag
    # must never become a source endpoint or a guessed filename in any position.
    if (command.scoped or len(tokens) < 6 or any(token.dynamic for token in tokens)
            or "DISCARD_FILE_CONTENTS" in values
            or values[2] != "PREFIX" or values[4] != "FILES"
            or any(value in {"PREFIX", "FILES", "BASE", "LANG", "OPTIONS", "BIG_RESOURCES", "OUTPUT_TARGETS"}
                   for value in values[5:])):
        reject(facts, command, "unsupported_literal_resources_arguments")
        return
    prefix = values[3]
    for token in tokens[5:]:
        path = literal_path(facts.file, token.value)
        alias = properties_for(facts, token, properties).get("QT_RESOURCE_ALIAS", token.value)
        logical = resource_url(prefix, alias)
        if path is None or logical is None:
            reject(facts, command, "resource_path_escape_or_invalid_alias")
            continue
        consumed.add(path)
        facts.add_chars("resource_alias", (values[0], values[1], logical, token.value), logical,
                        token.start, token.end, logical_url=logical, target_path=path,
                        value=token.value, prefix=prefix, alias=alias, locale="", origin="cmake",
                        target_name=values[0], resource_name=values[1], generated=False)
