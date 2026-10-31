"""Revalidate immutable target/root and negative lookup witnesses at publication.

Only admitted native/build inputs are read. Fresh lookup checks filesystem
metadata for shadows; it cannot discover or open an unprovided header.
"""
from __future__ import annotations

import hashlib
from pathlib import Path

from graphify.extractors.qt_cpp_build_profiles import profiles_from_sources
from graphify.extractors.qt_cpp_build_types import bad_build_context, validate_build_input, validate_profile
from graphify.extractors.qt_cpp_include_resolution import IncludeResolver, verify_absences


def verify_build_context(contexts, sources, *, root):
    """No cached authority survives a changed build file or newly present shadow."""
    from graphify.extractors.qt_cpp_test_context import QtTestContextError
    for values in (contexts.build_inputs, contexts.build_profiles, contexts.absences):
        if type(values) is not tuple or len(values) > 100_000:
            bad_build_context()
    root, build_sources = Path(root).resolve(), {}
    for item in contexts.build_inputs:
        validate_build_input(item)
        if item.source_file in build_sources:
            bad_build_context()
        try:
            path = (root / item.source_file).resolve()
            path.relative_to(root)
            with path.open("rb") as stream:
                raw = stream.read(5_000_001)
            if len(raw) > 5_000_000 or hashlib.sha256(raw).hexdigest() != item.source_sha256:
                raise ValueError
        except (OSError, RuntimeError, ValueError) as exc:
            raise QtTestContextError("Accepted build include source changed; retry the admitted inputs") from exc
        build_sources[item.source_file] = raw
    for profile in contexts.build_profiles:
        validate_profile(profile)
    native = {Path(key).relative_to(root).as_posix() for key in sources}
    profiles = profiles_from_sources(build_sources, native, root=root)
    if profiles != contexts.build_profiles:
        bad_build_context()
    verify_absences(contexts.absences, root=root)
    # Recompute every quoted lookup in the actual target domain. This checks
    # omitted/forged proof as well as absence of competing root candidates.
    admitted = _quoted_inputs(sources, root)
    resolver = IncludeResolver(admitted, set(), profiles, root=root)
    for path, context in zip(contexts.paths, contexts.contexts):
        resolver.denied(path, path)
        if resolver.witnesses(path) != context.build_witnesses:
            raise QtTestContextError("Accepted build include lookup changed; retry the admitted inputs")
        # Omitting every build field must not turn an unresolved quoted header
        # into a denial-free SDK context. Source effects remain rejection-only.
        for after, literal in admitted[path]["possible"]:
            target, _ = resolver.resolve(path, path, literal, after)
            if (not target or "*" in resolver.denied(path, target)) and not any(
                    item.after <= after and "*" in item.names for item in context.denials):
                bad_build_context()
        for activation in context.activations:
            for witness in activation.witnesses[:-1]:
                key = str((root / witness.source_file).resolve())
                if key not in admitted:
                    bad_build_context()
                target, _ = resolver.resolve(path, key, witness.include_literal, witness.span[1])
                if not target or "*" in resolver.denied(path, target) and "*" not in activation.denied_names:
                    bad_build_context()


def _quoted_inputs(sources, root):
    from graphify.extractors.qt_cpp_syntax import _parse_cpp, walk
    from graphify.extractors.qt_cpp_test_context import IncludeWitness
    admitted = {}
    for key, source in sources.items():
        relative, quotes = Path(key).relative_to(root).as_posix(), {}
        for node in walk(_parse_cpp(source)):
            if node.type != "preproc_include":
                continue
            item = node.child_by_field_name("path")
            literal = source[item.start_byte:item.end_byte] if item is not None else b""
            if len(literal) < 2 or len(literal) > 386 or literal[:1] != b'"':
                continue
            value = literal[1:-1].decode("utf-8")
            quotes[node.end_byte, value] = IncludeWitness(relative, hashlib.sha256(source).hexdigest(), value,
                (node.start_byte, node.end_byte, node.start_point.row, node.end_point.row,
                 node.start_point.column, node.end_point.column))
        admitted[key] = {"source": source, "denied": set(), "possible": tuple(quotes), "quote_witnesses": quotes}
    return admitted
