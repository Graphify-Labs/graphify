"""Bounded Qt analysis stamps; the caller owns successful publication ordering."""
from __future__ import annotations

import json
import hashlib
import os
import re
import posixpath
from dataclasses import dataclass
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from graphify.extractors.qml_facts import CONTRACT_VERSION
from graphify.paths import write_text_atomic
from graphify.qt_incremental import QT_CPP_SUFFIXES, is_qt_metadata, is_qt_source, qt_analysis_fingerprint

QT_STATE_FILE = ".qt_analysis.json"
QT_STATE_SCHEMA = 1
_DIGEST = re.compile(r"[0-9a-f]{64}\Z")
MAX_CONFIG_BYTES = 1_048_576


@dataclass(frozen=True)
class QtAnalysisState:
    fingerprint: str
    changed: bool
    import_roots: tuple[str, ...]
    has_qt: bool
    current_has_qt: bool


def _read_state(output_root: Path) -> dict | None:
    path = Path(output_root) / QT_STATE_FILE
    try:
        if path.stat().st_size > 1024:
            return None
        with path.open("rb") as stream:
            raw = stream.read(1025)
        if len(raw) > 1024:
            return None
        value = json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeError, ValueError):
        return None
    if not isinstance(value, dict) or type(value.get("schema")) is not int or value["schema"] != QT_STATE_SCHEMA:
        return None
    if not _valid_fingerprint(value.get("fingerprint")) or not isinstance(value.get("has_qt", False), bool):
        return None
    return value


def _valid_fingerprint(value) -> bool:
    return isinstance(value, str) and _DIGEST.fullmatch(value) is not None


def read_qt_fingerprint(output_root: Path) -> str | None:
    """Missing, incompatible and corrupted state force refresh, never cache reuse."""
    value = _read_state(output_root)
    return value["fingerprint"] if value else None


def qt_configuration_changed(output_root: Path, fingerprint: str) -> bool:
    if not _valid_fingerprint(fingerprint):
        raise ValueError("QT_CONFIG: invalid analysis fingerprint")
    return read_qt_fingerprint(output_root) != fingerprint


def save_qt_fingerprint(output_root: Path, fingerprint: str, *, has_qt=False) -> None:
    """Call only after graph/manifest publication succeeds; no automatic writeback."""
    if not _valid_fingerprint(fingerprint):
        raise ValueError("QT_CONFIG: invalid analysis fingerprint")
    path = Path(output_root) / QT_STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    write_text_atomic(path, json.dumps({"schema": QT_STATE_SCHEMA, "fingerprint": fingerprint, "has_qt": has_qt},
                                      sort_keys=True) + "\n")


def _import_roots(root: Path) -> tuple[str, ...]:
    raw = os.environ.get("GRAPHIFY_QML_IMPORT_ROOTS", '["."]')
    if len(raw.encode("utf-8")) > 65536:
        raise ValueError("QT_CONFIG_LIMIT: import root configuration exceeds its byte bound")
    try:
        values = json.loads(raw)
    except ValueError as exc:
        raise ValueError("QT_CONFIG: import roots must be a JSON list") from exc
    if not isinstance(values, list) or len(values) > 256:
        raise ValueError("QT_CONFIG: import roots must be a bounded JSON list")
    roots = []
    for value in values:
        if not isinstance(value, str) or not value or len(value) > 384:
            raise ValueError("QT_CONFIG: malformed import root")
        value = value.replace("\\", "/")
        if value.startswith("/") or ":" in value or "\x00" in value or ".." in value.split("/"):
            raise ValueError("QT_CONFIG: import roots must stay project-relative")
        try:
            (root / value).resolve().relative_to(root)
        except ValueError as exc:
            raise ValueError("QT_CONFIG: import root resolves outside the project") from exc
        roots.append(posixpath.normpath(value))
    return tuple(roots)


def _package_versions() -> str:
    versions = {}
    for package in ("graphifyy", "tree-sitter", "tree-sitter-cpp", "tree-sitter-javascript",
                    "tree-sitter-language-pack"):
        try:
            versions[package] = version(package)
        except PackageNotFoundError:
            versions[package] = "absent"
    return json.dumps(versions, sort_keys=True)


def inspect_qt_analysis(root: Path, out: Path, accepted_paths, *, excludes=(), gitignore=True) -> QtAnalysisState:
    """Inspect only accepted paths/ancestors, preserving root and configuration scope.

    Configured import roots do not authorize a scan. Their ordered names and
    parser contracts affect the stamp; corpus admission remains caller-owned.
    """
    root = Path(root).resolve()
    roots = _import_roots(root)
    paths, directories = [], {root}
    for raw in accepted_paths:
        path = Path(raw)
        path = path if path.is_absolute() else root / path
        try:
            path = path.resolve()
            relative = path.relative_to(root)
        except ValueError as exc:
            raise ValueError("QT_CONFIG: accepted input resolves outside the project") from exc
        paths.append(relative.as_posix())
        if relative.as_posix() == ".":
            raise ValueError("QT_CONFIG: an accepted input must identify a source file")
        parent = path.parent
        while parent != root:
            directories.add(parent)
            parent = parent.parent
        if len(paths) > 100_000 or len(directories) > 100_000:
            raise ValueError("QT_CONFIG_LIMIT: accepted input inventory exceeds its bound")
    configs = []
    names = (".graphifyignore", ".gitignore") if gitignore else (".graphifyignore",)
    for directory in sorted(directories):
        for name in names:
            path = directory / name
            try:
                path.resolve().relative_to(root)
                with path.open("rb") as stream:
                    raw = stream.read(MAX_CONFIG_BYTES + 1)
            except FileNotFoundError:
                continue
            except (OSError, ValueError) as exc:
                raise ValueError("QT_CONFIG: ignore configuration is unreadable or outside root") from exc
            if len(raw) > MAX_CONFIG_BYTES:
                raise ValueError("QT_CONFIG_LIMIT: ignore configuration exceeds its byte bound")
            configs.append((path.relative_to(root).as_posix(), hashlib.sha256(raw).hexdigest()))
    config = {"accepted_paths": sorted(set(paths)), "ignore_files": configs,
              "gitignore": bool(gitignore), "qt_fact_contract": 1}
    profile = "qt6-static:" + hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()
    fingerprint = qt_analysis_fingerprint(parser_version=_package_versions(), fact_version=CONTRACT_VERSION,
                                         import_roots=roots, ignore_patterns=excludes, profile=profile)
    previous = _read_state(out)
    current_has_qt = any(is_qt_source(path) or is_qt_metadata(path) or Path(path).suffix.lower() in QT_CPP_SUFFIXES
                         for path in paths)
    return QtAnalysisState(fingerprint, previous is None or previous["fingerprint"] != fingerprint,
                           roots, current_has_qt or bool(previous and previous.get("has_qt")), current_has_qt)


def commit_qt_analysis(out: Path, state: QtAnalysisState) -> None:
    """Prepare the candidate stamp for its owner's accepted product cohort.

    Manual/watch publication supplies its staging directory and commits the stamp
    with graph/root/manifest products; writing this candidate alone accepts no run.
    """
    save_qt_fingerprint(out, state.fingerprint, has_qt=state.current_has_qt)
