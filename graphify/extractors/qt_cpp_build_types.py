"""Immutable source-owned CMake include witnesses; no configured build authority.

Only caller-admitted source bytes create these records. Workers receive typed
values, never mutable project state, directory discoveries or graph labels.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import PurePosixPath, PureWindowsPath
import re


def bad_build_context():
    from graphify.extractors.qt_cpp_test_context import QtTestContextError
    raise QtTestContextError("Accepted build include context is malformed; rebuild the admitted snapshot")


def safe_relative(value, *, directory=False):
    if not _literal(value, 384 if directory else 160):
        return False
    windows = PureWindowsPath(value)
    return (not windows.drive and not windows.root and "\\" not in value
            and not PurePosixPath(value).is_absolute() and ".." not in PurePosixPath(value).parts
            and (directory or value != ".") and not any(ord(c) < 32 or ord(c) == 127 for c in value))


def valid_span(value):
    return (type(value) is tuple and len(value) == 6
            and all(type(item) is int and 0 <= item <= 5_000_000 for item in value)
            and value[0] < value[1] and (value[2], value[4]) < (value[3], value[5]))


def span_fields(value):
    return dict(zip(("start_byte", "end_byte", "start_row", "end_row", "start_column", "end_column"), value))


@dataclass(frozen=True)
class BuildInput:
    source_file: str
    source_sha256: str


@dataclass(frozen=True)
class IncludeRoot:
    directory: str
    literal: str
    command_span: tuple
    token_span: tuple
    visibility: str


@dataclass(frozen=True)
class TargetProfile:
    source_file: str
    build_file: str
    build_sha256: str
    target: str
    target_span: tuple
    source_literal: str
    source_span: tuple
    roots: tuple[IncludeRoot, ...]


@dataclass(frozen=True)
class BuildWitness:
    profile: TargetProfile
    root: IncludeRoot
    importer_file: str
    importer_sha256: str
    include_literal: str
    include_span: tuple
    header_file: str
    header_sha256: str

    def fields(self):
        return {"build_file": self.profile.build_file, "build_sha256": self.profile.build_sha256,
            "target": self.profile.target, "target_span": span_fields(self.profile.target_span),
            "source_file": self.profile.source_file, "source_literal": self.profile.source_literal,
            "source_span": span_fields(self.profile.source_span),
            "root": self.root.directory, "root_literal": self.root.literal,
            "root_span": span_fields(self.root.token_span), "root_command_span": span_fields(self.root.command_span),
            "visibility": self.root.visibility, "importer_file": self.importer_file,
            "importer_sha256": self.importer_sha256, "include_literal": self.include_literal,
            "include_span": span_fields(self.include_span), "header_file": self.header_file,
            "header_sha256": self.header_sha256}


def _literal(value, maximum=384):
    try:
        return (isinstance(value, str) and 0 < len(value.encode("utf-8")) <= maximum
                and not any(ord(c) < 32 or ord(c) == 127 for c in value))
    except UnicodeError:
        return False


def _hash(value):
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def validate_profile(profile):
    if (not isinstance(profile, TargetProfile) or not safe_relative(profile.source_file)
            or not safe_relative(profile.build_file) or not _hash(profile.build_sha256)
            or not _literal(profile.target) or not _literal(profile.source_literal)
            or not valid_span(profile.target_span) or not valid_span(profile.source_span)
            or type(profile.roots) is not tuple or not 1 <= len(profile.roots) <= 50):
        bad_build_context()
    for item in profile.roots:
        if (not isinstance(item, IncludeRoot) or not safe_relative(item.directory, directory=True)
                or not _literal(item.literal) or not valid_span(item.command_span)
                or not valid_span(item.token_span) or item.visibility not in ("PRIVATE", "PUBLIC")):
            bad_build_context()
    if len({item.directory for item in profile.roots}) != len(profile.roots):
        bad_build_context()


def validate_build_witness(witness):
    if not isinstance(witness, BuildWitness):
        bad_build_context()
    validate_profile(witness.profile)
    if (not isinstance(witness.root, IncludeRoot) or witness.root not in witness.profile.roots
            or not safe_relative(witness.importer_file) or not _hash(witness.importer_sha256)
            or not _literal(witness.include_literal) or not valid_span(witness.include_span)
            or not safe_relative(witness.header_file) or not _hash(witness.header_sha256)):
        bad_build_context()


def validate_build_input(value):
    if not isinstance(value, BuildInput) or not safe_relative(value.source_file) or not _hash(value.source_sha256):
        bad_build_context()
