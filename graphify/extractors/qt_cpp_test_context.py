"""Immutable, caller-admitted forward include witnesses for QtTest source views.

Only explicit input paths are read. Literal in-root quoted includes may forward
an observed SDK include; this is neither preprocessor execution nor installed
SDK identity. Context is shared with generic and Qt producers before parsing.
"""
from __future__ import annotations

from bisect import bisect_left
from dataclasses import dataclass, replace
import hashlib
from pathlib import Path
import re

from graphify.extractors.cpp_include_guards import IncludeGuardIndex
from graphify.extractors.cpp_lexical_tokens import identifier_fragment
from graphify.extractors.cpp_test_macro_roles import ordinary_test_callable
from graphify.extractors.qt_cpp_build_types import BuildWitness, validate_build_witness

_NATIVE = {".cpp", ".cc", ".cxx", ".hpp", ".hh", ".hxx", ".h"}
_SDK = {"QTest", "QtTest", "QtTest/QTest", "QtTest/QtTest", "QtQuickTest"}
_OVERRIDE = re.compile(rb"(?m)^(?:\xef\xbb\xbf)?[ \t]*#[ \t]*(?:define|undef)[ \t]+([A-Za-z_]\w*)\b")


class QtTestContextError(ValueError):
    """Source-context integrity failure, independent of C++ grammar admission."""

    code = "QT_CPP_CONTEXT"


@dataclass(frozen=True)
class IncludeWitness:
    source_file: str
    source_sha256: str
    include_literal: str
    span: tuple[int, int, int, int, int, int]
    build_root: BuildWitness | None = None

    def fields(self):
        keys = ("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column")
        result = {"source_file": self.source_file, "source_sha256": self.source_sha256,
                "include_literal": self.include_literal, "span": dict(zip(keys, self.span))}
        if self.build_root is not None:
            result["build_include_witness"] = self.build_root.fields()
        return result


@dataclass(frozen=True)
class TestActivation:
    after: int
    sdk_header: str
    witnesses: tuple[IncludeWitness, ...]
    denied_names: tuple[str, ...] = ()


@dataclass(frozen=True)
class TestDenial:
    after: int
    names: tuple[str, ...]


@dataclass(frozen=True)
class QtTestContext:
    source_sha256: str
    activations: tuple[TestActivation, ...]
    denials: tuple[TestDenial, ...] = ()
    build_witnesses: tuple[BuildWitness, ...] = ()


@dataclass(frozen=True)
class QtTestContexts:
    """Tuple storage survives process dispatch without hidden mutable indexes."""
    paths: tuple[str, ...]
    contexts: tuple[QtTestContext, ...]
    requires_native_refresh: bool = False
    build_inputs: tuple = ()
    build_profiles: tuple = ()
    absences: tuple = ()

    def for_path(self, path):
        key = str(Path(path).resolve())
        position = bisect_left(self.paths, key)
        return self.contexts[position] if position < len(self.paths) and self.paths[position] == key else None


def validate_test_context(context, source):
    """A coherent target read is mandatory; stale context is never a cache hint."""
    if context is not None and (not isinstance(context, QtTestContext)
            or context.source_sha256 != hashlib.sha256(source).hexdigest()):
        raise QtTestContextError("Accepted QtTest include source changed; retry the admitted inputs")
    if context is None:
        return
    if (type(context.activations) is not tuple or len(context.activations) > 50
            or type(context.denials) is not tuple or len(context.denials) > 50
            or type(context.build_witnesses) is not tuple or len(context.build_witnesses) > 50):
        raise QtTestContextError("Accepted QtTest include context is malformed; rebuild the admitted snapshot")
    for witness in context.build_witnesses:
        validate_build_witness(witness)
    for item in context.denials:
        if (not isinstance(item, TestDenial) or type(item.after) is not int or not 0 <= item.after <= len(source)
                or type(item.names) is not tuple or len(item.names) > 50
                or any(not isinstance(name, str) or len(name) > 64 for name in item.names)):
            raise QtTestContextError("Accepted QtTest include denial is malformed; rebuild the admitted snapshot")
    for item in context.activations:
        if (not isinstance(item, TestActivation) or type(item.after) is not int or not 0 <= item.after <= len(source)
                or not isinstance(item.sdk_header, str) or item.sdk_header not in _SDK
                or type(item.witnesses) is not tuple or not 1 <= len(item.witnesses) <= 16
                or type(item.denied_names) is not tuple or len(item.denied_names) > 50
                or any(not isinstance(name, str) or len(name) > 64 for name in item.denied_names)):
            raise QtTestContextError("Accepted QtTest include activation is malformed; rebuild the admitted snapshot")
        for witness in item.witnesses:
            if (not isinstance(witness, IncludeWitness) or not isinstance(witness.source_file, str)
                    or not 0 < len(witness.source_file.encode()) <= 160 or Path(witness.source_file).is_absolute()
                    or ".." in Path(witness.source_file).parts
                    or any(ord(char) < 32 or ord(char) == 127 for char in witness.source_file)
                    or not isinstance(witness.source_sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", witness.source_sha256)
                    or not isinstance(witness.include_literal, str) or len(witness.include_literal.encode()) > 384
                    or any(ord(char) < 32 or ord(char) == 127 for char in witness.include_literal)
                    or type(witness.span) is not tuple or len(witness.span) != 6
                    or any(type(value) is not int or value < 0 for value in witness.span)
                    or witness.span[0] >= witness.span[1]):
                raise QtTestContextError("Accepted QtTest include witness is malformed; rebuild the admitted snapshot")
            if witness.build_root is not None:
                validate_build_witness(witness.build_root)


def verify_test_contexts(contexts, *, root=None):
    """A final collector checkpoint detects changed/unreadable admitted witnesses."""
    if contexts is None:
        return
    if (not isinstance(contexts, QtTestContexts) or type(contexts.paths) is not tuple
            or type(contexts.contexts) is not tuple or len(contexts.paths) != len(contexts.contexts)):
        raise QtTestContextError("Accepted QtTest snapshot is malformed; rebuild the admitted inputs")
    sources = {}
    for path, context in zip(contexts.paths, contexts.contexts):
        try:
            if not isinstance(path, str) or not Path(path).is_absolute():
                raise ValueError
            if root is not None:
                Path(path).resolve().relative_to(Path(root).resolve())
            with Path(path).open("rb") as stream:
                source = stream.read(5_000_001)
        except (OSError, RuntimeError, ValueError) as exc:
            raise QtTestContextError("Accepted QtTest include source is unreadable; retry the admitted inputs") from exc
        validate_test_context(context, source)
        sources[path] = source
    if root is not None:
        from graphify.extractors.qt_cpp_build_integrity import verify_build_context
        verify_build_context(contexts, sources, root=root)
        from graphify.extractors.qt_cpp_test_context_integrity import verify_include_witnesses
        verify_include_witnesses(contexts, sources, root=root)


def build_qt_test_contexts(paths, *, root, project_paths=()):
    """Build one bounded snapshot from explicit, already-dispatched native paths."""
    # Delayed imports keep syntax recovery dependent on immutable context types,
    # while discovery uses the same parser/lexical/AST bounds as its consumers.
    from graphify.extractors.qt_cpp_syntax import QtCppError, _parse_cpp, lexical_code, walk
    from graphify.extractors.qt_cpp_test_syntax import _SPELLING, needs_test_recovery
    from graphify.extractors.qt_cpp_test_launchers import LAUNCHER_PATTERN, needs_launcher_recovery
    spellings = _SPELLING + b"|" + LAUNCHER_PATTERN
    root = Path(root).resolve()
    admitted, ambiguous = {}, set()
    for path in paths:
        path = Path(path)
        if path.suffix.lower() not in _NATIVE:
            continue
        try:
            resolved = path.resolve()
            relative = resolved.relative_to(root).as_posix()
        except (ValueError, OSError, RuntimeError):
            continue
        key = str(resolved)
        if key in admitted:
            ambiguous.add(key)
            continue
        try:
            with path.open("rb") as stream:
                source = stream.read(5_000_001)
            if len(source) > 5_000_000 or len(relative.encode()) > 160:
                continue
            source.decode("utf-8")
        except (OSError, UnicodeError):
            continue
        code, tree = lexical_code(source), _parse_cpp(source)
        includes, denied, possible, events, guards, quotes = [], set(), [], [], IncludeGuardIndex(tree), {}
        try:
            nodes = list(walk(tree))
        except QtCppError:
            nodes = []  # Unavailable source context cannot lend include authority.
        for match in _OVERRIDE.finditer(code):
            if re.fullmatch(spellings, match[1]) and not identifier_fragment(tree, *match.span(1)):
                denied.add(match[1].decode())
                events.append((match.start(), match[1].decode()))
        for node in nodes:
            if ordinary_test_callable(node, source):
                name = node.child_by_field_name("declarator")
                spelling = source[name.start_byte:name.end_byte] if name is not None else b""
                if re.fullmatch(spellings, spelling):
                    denied.add(spelling.decode())
                    events.append((node.start_byte, spelling.decode()))
        for node in nodes:
            if node.type != "preproc_include" or node.parent is None:
                continue
            item = node.child_by_field_name("path")
            literal = source[item.start_byte:item.end_byte] if item is not None else b""
            if len(literal) > 386 or literal[:1] not in {b'<', b'"'}:
                denied.add("*")  # Dynamic include effects cannot prove a macro remains the SDK definition.
                events.append((node.end_byte, "*"))
                continue
            value = literal[1:-1].decode()
            witness = IncludeWitness(relative, hashlib.sha256(source).hexdigest(), value,
                                     (node.start_byte, node.end_byte, node.start_point.row, node.end_point.row,
                                      node.start_point.column, node.end_point.column))
            if literal[:1] == b'"':
                possible.append((node.end_byte, value))
                quotes[node.end_byte, value] = witness
            if not (node.parent.type == "translation_unit" or guards.accepts(node.parent)):
                continue
            includes.append((node.end_byte, literal[:1] == b"<", value, witness))
        admitted[key] = {"source": source, "includes": includes, "possible": possible,
                         "denied": denied, "events": events, "quote_witnesses": quotes,
                         "has_test": needs_test_recovery(code) or needs_launcher_recovery(code)}
    from graphify.extractors.qt_cpp_build_profiles import load_build_profiles
    from graphify.extractors.qt_cpp_include_resolution import IncludeResolver
    inputs, profiles = load_build_profiles(project_paths, {Path(k).relative_to(root).as_posix() for k in admitted}, root=root)
    resolver, memo = IncludeResolver(admitted, ambiguous, profiles, root=root), {}

    def activate(key, stack):
        if key in stack or len(stack) >= 16 or key in ambiguous:
            return None
        origin = stack[0] if stack else key
        cache_key = (resolver.domain(origin), key, len(stack))
        if cache_key in memo:
            return memo[cache_key]
        entry = admitted[key]
        activations = []
        for after, system, value, witness in entry["includes"]:
            if system:
                if value in _SDK:
                    activations.append(TestActivation(after, value, (witness,)))
                    if len(activations) > 50:
                        memo[cache_key] = ()
                        return ()
                continue
            target, build_root = resolver.resolve(origin, key, value, after)
            if not target:
                continue  # A partial extraction never opens an unprovided header.
            inherited = activate(target, (*stack, key))
            if inherited is None:
                memo[cache_key] = None
                return None  # A cycle cannot borrow an otherwise visible SDK include.
            for activation in inherited:
                if len(activation.witnesses) >= 16:
                    continue
                denied = tuple(sorted(set(activation.denied_names) | resolver.denied(origin, target)))
                observed = replace(witness, build_root=build_root) if build_root is not None else witness
                activations.append(TestActivation(after, activation.sdk_header, (observed, *activation.witnesses), denied))
                if len(activations) > 50:
                    memo[cache_key] = ()
                    return ()
        result = tuple(activations) if len(activations) <= 50 else ()
        memo[cache_key] = result
        return result

    def denials(key):
        earliest = {}
        events = list(admitted[key]["events"])
        for after, value in admitted[key]["possible"]:
            target, _ = resolver.resolve(key, key, value, after)
            if target:
                events.extend((after, name) for name in resolver.denied(key, target))
            else:
                events.append((after, "*"))
        for after, name in events:
            earliest[name] = min(after, earliest.get(name, after))
        grouped = {}
        for name, after in earliest.items():
            grouped.setdefault(after, []).append(name)
        return tuple(TestDenial(after, tuple(sorted(names))) for after, names in sorted(grouped.items()))

    keys = tuple(sorted(admitted))
    contexts = []
    for key in keys:
        active, denied = activate(key, ()) or (), denials(key)
        proofs = resolver.witnesses(key)
        contexts.append(QtTestContext(hashlib.sha256(admitted[key]["source"]).hexdigest(),
            active if len(proofs) <= 50 else (), denied, proofs if len(proofs) <= 50 else ()))
    contexts = tuple(contexts)
    relevant = any(admitted[key]["has_test"] for key in keys) or any(item.activations for item in contexts)
    return QtTestContexts(keys if relevant else (), contexts if relevant else (), relevant,
                         inputs if relevant else (), profiles if relevant else (),
                         tuple(sorted(resolver.absences, key=lambda p: (p.importer_file, p.include_literal))) if relevant else ())
