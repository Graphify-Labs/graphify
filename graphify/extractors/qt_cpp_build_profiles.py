"""Literal source-local executable ownership for admitted CMake include context.

This tokenizes inputs without executing CMake, following includes, expanding
variables or borrowing configured/transitive compiler properties.
"""
from __future__ import annotations

from collections import Counter, defaultdict
import hashlib
from pathlib import Path, PureWindowsPath
import re

from graphify.extractors.qml_cmake_outputs import command_inventory
from graphify.extractors.qml_project_read import ProjectFacts
from graphify.extractors.qt_cpp_build_types import BuildInput, IncludeRoot, TargetProfile, safe_relative, _literal
from graphify.extractors.qt_cpp_build_effects import SourceEffects
from graphify.extractors.qt_cpp_build_data import has_unsafe_shadow

_TARGETS = {"qt_add_executable", "qt6_add_executable", "add_executable"}
_FLAGS = {"WIN32", "MACOSX_BUNDLE", "EXCLUDE_FROM_ALL", "MANUAL_FINALIZATION"}
_NAME = re.compile(r"[A-Za-z0-9_.+-]{1,384}")
_GLOBAL = {"include", "add_subdirectory", "include_directories"}


def literal_location(root, build_file, value, *, directory=False):
    """Reject foreign Windows forms even on POSIX, before resolving an in-root literal."""
    if (not _literal(value)
            or PureWindowsPath(value).drive or PureWindowsPath(value).root or "\\" in value
            or any(c in value for c in "$;\x00") or any(ord(c) < 32 or ord(c) == 127 for c in value)):
        return None
    try:
        resolved = (Path(root) / Path(build_file).parent / value).resolve()
        relative = resolved.relative_to(Path(root).resolve()).as_posix()
    except (OSError, RuntimeError, ValueError):
        return None
    return relative if safe_relative(relative, directory=directory) else None


def _span(facts, start, end):
    value = facts.span(facts.byte_offsets[start], facts.byte_offsets[end])
    return tuple(value[key] for key in ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"))


def _target(command):
    if not command.tokens:
        return None
    token = command.tokens[0]
    return token.value if not token.dynamic and _NAME.fullmatch(token.value) else None


def _sources(command, *, defining):
    tokens = command.tokens[1:]
    if command.scoped or any(t.dynamic for t in tokens):
        return None
    if defining:
        if any(t.value in {"IMPORTED", "ALIAS", "INTERFACE"} for t in tokens):
            return None
        return [t for t in tokens if t.value not in _FLAGS]
    values, visibility = [], None
    for token in tokens:
        if token.value in {"PRIVATE", "PUBLIC", "INTERFACE"}:
            visibility = token.value
        elif visibility is None or token.value in {"FILE_SET", "BASE_DIRS", "FILES", "TYPE"}:
            return None
        elif visibility in {"PRIVATE", "PUBLIC"}:
            values.append(token)
    return values


def _roots(command, facts, root):
    if command.scoped or any(t.dynamic for t in command.tokens):
        return None
    values, visibility = [], None
    for token in command.tokens[1:]:
        if token.value in {"PRIVATE", "PUBLIC", "INTERFACE"}:
            visibility = token.value
            continue
        if visibility is None or token.value in {"SYSTEM", "BEFORE", "AFTER"}:
            return None
        location = literal_location(root, facts.file, token.value, directory=True)
        if location is None:
            return None
        if visibility in {"PRIVATE", "PUBLIC"}:
            values.append(IncludeRoot(location, token.value, _span(facts, command.start, command.end),
                                      _span(facts, token.start, token.end), visibility))
    return values


def _property_targets(command):
    """Only exact literal target setter owners can constrain a root mutation."""
    tokens = command.tokens
    delimiter = "PROPERTIES" if command.name == "set_target_properties" else "PROPERTY"
    end = next((index for index, token in enumerate(tokens) if token.value == delimiter), None)
    if end is None or command.name == "set_property" and (not tokens or tokens[0].value != "TARGET"):
        return None
    owners = tokens[:end] if command.name == "set_target_properties" else tokens[1:end]
    if command.name == "set_property":
        owners = [token for token in owners if token.value not in {"APPEND", "APPEND_STRING"}]
    if not owners or any(token.dynamic or not _NAME.fullmatch(token.value) for token in owners):
        return None
    return {token.value for token in owners}


def _positive_command_shadowed(commands):
    """Positive literal calls cannot borrow builtin identity from another manifest.

    Definitions may be activated across supplied files. Unknown names cannot be
    isolated, and configured order/function execution is outside this profile.
    """
    positive = _TARGETS | {"target_sources", "target_include_directories"}
    for command in commands:
        if command.name not in {"function", "macro"}:
            continue
        if not command.tokens:
            return True
        name = command.tokens[0]
        if (name.dynamic or not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name.value)
                or name.value.lower() in positive):
            return True
    return False


def profiles_from_sources(sources, admitted, *, root):
    """All positive ownership is from exact source tokens and already-admitted native paths."""
    definitions, mutations, invalid, claims = defaultdict(list), defaultdict(list), set(), defaultdict(set)
    unknown_roots = False
    effects, inventories = [], []
    for file, raw in sources.items():
        try:
            facts = ProjectFacts(raw, file, "cmake")
            commands = command_inventory(facts.text)
        except (ValueError, UnicodeError):
            return ()  # Unknown source-local ownership cannot lend a root.
        inventories.append((facts, raw, commands))
    if any(_positive_command_shadowed(commands) for _, _, commands in inventories):
        return ()
    cohort_shadowed = any(has_unsafe_shadow(commands) for _, _, commands in inventories)
    for facts, raw, commands in inventories:
        file = facts.file
        globally_blocked = any(c.name in _GLOBAL for c in commands)
        positive = {c.start for c in commands if c.name in _TARGETS | {"target_sources"}
                    and _target(c) is not None and _sources(c, defining=c.name in _TARGETS) is not None}
        effects.append(SourceEffects(commands, facts.text, file, positive, cohort_shadowed=cohort_shadowed))
        for command in commands:
            target = _target(command)
            if command.name in {"function", "macro"} and command.tokens and command.tokens[0].value.lower() in (
                    _TARGETS | {"target_sources", "target_include_directories"}):
                globally_blocked = True
            if command.name in _TARGETS and target and command.start in positive:
                definitions[target].append((facts, raw, command, globally_blocked))
            elif target and (command.name == "target_include_directories"
                             or command.name == "target_sources" and command.start in positive):
                mutations[target].append((facts, command))
            elif command.name == "target_include_directories":
                unknown_roots = True
            elif command.name in {"set_target_properties", "set_property"}:
                if any(t.value in {"INCLUDE_DIRECTORIES", "INTERFACE_INCLUDE_DIRECTORIES"} for t in command.tokens):
                    owners = _property_targets(command)
                    if owners is None:
                        unknown_roots = True
                    else:
                        invalid.update(owners)
        if globally_blocked:
            invalid.update(_target(c) for c in commands if c.name in _TARGETS)
        # Competing literal membership denies authority even when that target
        # has no usable roots or has an unsupported conditional/root option.
        for command in commands:
            if command.start not in positive:
                continue
            owner = _target(command)
            for token in command.tokens[1:]:
                location = None if token.dynamic else literal_location(root, file, token.value)
                if location in admitted:
                    claims[location].add(owner)
    # An unnamed target root writer cannot be isolated to another target/file.
    # It denies context only; it never chooses a value or evaluates CMake.
    if unknown_roots:
        return ()
    candidates = []
    for target, declarations in definitions.items():
        if len(declarations) != 1 or target in invalid:
            continue
        facts, raw, declaration, blocked = declarations[0]
        declared = _sources(declaration, defining=True)
        if blocked or declared is None:
            continue
        members, roots, bad = list(declared), [], False
        for owner, command in mutations.get(target, []):
            if owner.file != facts.file or command.start < declaration.end:
                bad = True
                break
            if command.name == "target_sources":
                extra = _sources(command, defining=False)
                if extra is None:
                    bad = True
                    break
                members.extend(extra)
            else:
                extra = _roots(command, facts, root)
                if extra is None:
                    bad = True
                    break
                roots.extend(extra)
        if bad or not roots or len(roots) > 50 or len({item.directory for item in roots}) != len(roots):
            continue
        # Repeated membership tokens are not multiple owners, but a file in
        # separate source targets/configurations cannot choose one global scope.
        by_source = {}
        for token in members:
            source_file = literal_location(root, facts.file, token.value)
            if source_file in admitted:
                by_source.setdefault(source_file, token)
        for source_file, token in by_source.items():
            if not all(index.permits(target, source_file, locate=lambda file, value: literal_location(root, file, value))
                       for index in effects):
                continue
            candidates.append(TargetProfile(source_file, facts.file, hashlib.sha256(raw).hexdigest(), target,
                _span(facts, declaration.start, declaration.end), token.value, _span(facts, token.start, token.end), tuple(roots)))
    counts = Counter(profile.source_file for profile in candidates)
    return tuple(sorted((p for p in candidates if counts[p.source_file] == 1
                         and claims[p.source_file] == {p.target}), key=lambda p: p.source_file))


def load_build_profiles(paths, admitted, *, root):
    """Read only explicit in-root CMake inputs, bounded like native context sources."""
    inputs, sources = [], {}
    for value in paths:
        path = Path(value)
        if path.name != "CMakeLists.txt" and path.suffix.lower() != ".cmake":
            continue
        try:
            path = path.resolve()
            relative = path.relative_to(Path(root).resolve()).as_posix()
            if not safe_relative(relative):
                continue
            with path.open("rb") as stream:
                raw = stream.read(5_000_001)
            if len(raw) > 5_000_000:
                return (), ()
            raw.decode("utf-8")
        except (OSError, RuntimeError, UnicodeError, ValueError):
            return (), ()
        if relative in sources:
            return (), ()
        sources[relative] = raw
        inputs.append(BuildInput(relative, hashlib.sha256(raw).hexdigest()))
    return tuple(sorted(inputs, key=lambda p: p.source_file)), profiles_from_sources(sources, admitted, root=root)
