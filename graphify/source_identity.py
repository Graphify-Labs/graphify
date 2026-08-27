from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, TypeGuard

from graphify.paths import GRAPHIFY_OUT, write_json_atomic


IDENTITY_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
DETECTOR_NAME = "graphify.detect"
DETECTOR_VERSION = "1"
SOURCE_MANIFEST_FILENAME = "source_manifest.json"
PENDING_FILENAME = ".graphify_pending"
_OTHER_PENDING_FILENAMES = (".pending_changes", ".rebuild.lock", "needs_update")
_MAX_SOURCE_MANIFEST_BYTES = 64 * 1024 * 1024


class FreshnessReason(str, Enum):
    MISSING_IDENTITY = "missing_identity"
    WRONG_ROOT = "wrong_root"
    REVISION_MISMATCH = "revision_mismatch"
    MISSING_MANIFEST = "missing_manifest"
    MANIFEST_MISMATCH = "manifest_mismatch"
    CHANGED_SUPPORTED_FILES = "changed_supported_files"
    PENDING_RECONCILIATION = "pending_reconciliation"


def _is_sha256(value: object) -> TypeGuard[str]:
    return (
        isinstance(value, str)
        and len(value) == 64
        and all(character in "0123456789abcdef" for character in value)
    )


@dataclass(frozen=True)
class DetectorIdentity:
    name: str = DETECTOR_NAME
    version: str = DETECTOR_VERSION

    def to_dict(self) -> dict[str, str]:
        return {"name": self.name, "version": self.version}

    @classmethod
    def parse(cls, value: object) -> DetectorIdentity | None:
        if not isinstance(value, dict):
            return None
        name = value.get("name")
        version = value.get("version")
        if not isinstance(name, str) or not isinstance(version, str):
            return None
        return cls(name=name, version=version)


CURRENT_DETECTOR = DetectorIdentity()


@dataclass(frozen=True)
class SourceIdentity:
    root: str
    revision: str | None
    manifest_digest: str
    detector: DetectorIdentity = CURRENT_DETECTOR
    schema_version: int = IDENTITY_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "root": self.root,
            "revision": self.revision,
            "manifest_digest": self.manifest_digest,
            "detector": self.detector.to_dict(),
        }

    @classmethod
    def parse(cls, value: object) -> SourceIdentity | None:
        if not isinstance(value, dict):
            return None
        schema_version = value.get("schema_version")
        root = value.get("root")
        revision = value.get("revision")
        manifest_digest = value.get("manifest_digest")
        detector = DetectorIdentity.parse(value.get("detector"))
        if schema_version != IDENTITY_SCHEMA_VERSION:
            return None
        if not isinstance(root, str) or not root:
            return None
        if revision is not None and not isinstance(revision, str):
            return None
        if not _is_sha256(manifest_digest):
            return None
        if detector is None:
            return None
        return cls(
            root=root,
            revision=revision,
            manifest_digest=manifest_digest,
            detector=detector,
            schema_version=schema_version,
        )


@dataclass(frozen=True)
class SourceManifestEntry:
    path: str
    sha256: str
    type: str

    def to_dict(self) -> dict[str, str]:
        return {"path": self.path, "sha256": self.sha256, "type": self.type}

    @classmethod
    def parse(cls, value: object) -> SourceManifestEntry | None:
        if not isinstance(value, dict):
            return None
        path = value.get("path")
        sha256 = value.get("sha256")
        file_type = value.get("type")
        if not isinstance(path, str) or not path:
            return None
        if not _is_sha256(sha256):
            return None
        if not isinstance(file_type, str) or not file_type:
            return None
        return cls(path=path, sha256=sha256, type=file_type)


@dataclass(frozen=True)
class SourceManifest:
    files: tuple[SourceManifestEntry, ...]
    detector: DetectorIdentity = CURRENT_DETECTOR
    schema_version: int = MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "detector": self.detector.to_dict(),
            "files": [entry.to_dict() for entry in self.files],
        }

    def digest(self) -> str:
        return hashlib.sha256(_canonical_json(self.to_dict())).hexdigest()

    @classmethod
    def parse(cls, value: object) -> SourceManifest | None:
        if not isinstance(value, dict):
            return None
        if value.get("schema_version") != MANIFEST_SCHEMA_VERSION:
            return None
        detector = DetectorIdentity.parse(value.get("detector"))
        raw_files = value.get("files")
        if detector is None or not isinstance(raw_files, list):
            return None
        files: list[SourceManifestEntry] = []
        for raw in raw_files:
            entry = SourceManifestEntry.parse(raw)
            if entry is None:
                return None
            files.append(entry)
        if files != sorted(files, key=lambda entry: (entry.path, entry.type)):
            return None
        if len({entry.path for entry in files}) != len(files):
            return None
        return cls(files=tuple(files), detector=detector)


@dataclass(frozen=True)
class FreshnessStatus:
    graph_path: str
    source_identity: SourceIdentity | None
    reasons: tuple[FreshnessReason, ...]
    schema_version: int = IDENTITY_SCHEMA_VERSION

    @property
    def eligible(self) -> bool:
        return not self.reasons

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": self.schema_version,
            "eligible": self.eligible,
            "reason_codes": [reason.value for reason in self.reasons],
            "source_identity": (
                self.source_identity.to_dict() if self.source_identity is not None else None
            ),
            "graph_path": self.graph_path,
        }


class SourceChangedDuringRead(RuntimeError):
    pass


def default_graph_path(root: Path) -> Path:
    return root / GRAPHIFY_OUT / "graph.json"


def pending_path(graph_path: Path) -> Path:
    return graph_path.parent / PENDING_FILENAME


def begin_reconciliation(graph_path: Path) -> None:
    marker = pending_path(graph_path)
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("1\n", encoding="utf-8")


def _canonical_json(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _git_revision(root: Path) -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
            env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"},
        )
    except (OSError, subprocess.SubprocessError):
        return None
    revision = result.stdout.strip()
    return revision if result.returncode == 0 and revision else None


def _read_build_options(graph_path: Path) -> tuple[list[str], bool]:
    config_path = graph_path.parent / ".graphify_build.json"
    try:
        value: Any = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return [], True
    if not isinstance(value, dict):
        return [], True
    raw_excludes = value.get("excludes")
    excludes = (
        [item for item in raw_excludes if isinstance(item, str) and item]
        if isinstance(raw_excludes, list)
        else []
    )
    gitignore = value.get("gitignore")
    return excludes, gitignore if isinstance(gitignore, bool) else True


def _detect_source(root: Path, graph_path: Path) -> dict[str, object]:
    from graphify.detect import detect

    excludes, gitignore = _read_build_options(graph_path)
    return detect(
        root,
        extra_excludes=excludes or None,
        cache_root=graph_path.parent.parent,
        gitignore=gitignore,
    )


def _manifest_paths(
    root: Path,
    detection: dict[str, object],
) -> list[tuple[str, Path, str]]:
    raw_files = detection.get("files")
    if not isinstance(raw_files, dict):
        raise ValueError("detection result has no files map")
    paths: list[tuple[str, Path, str]] = []
    seen: set[str] = set()
    for raw_type, raw_entries in raw_files.items():
        if not isinstance(raw_type, str) or not isinstance(raw_entries, list):
            raise ValueError("detection files map has an invalid entry")
        for raw_path in raw_entries:
            if not isinstance(raw_path, str):
                raise ValueError("detection file path is not a string")
            path = Path(os.path.abspath(raw_path))
            try:
                relative = path.relative_to(root).as_posix()
            except ValueError:
                relative = path.as_posix()
            relative = unicodedata.normalize("NFC", relative)
            if relative in seen:
                raise ValueError(f"duplicate detected file path: {relative}")
            seen.add(relative)
            paths.append((relative, path, raw_type))
    return sorted(paths, key=lambda item: (item[0], item[2]))


def _hash_file(item: tuple[str, Path, str]) -> SourceManifestEntry:
    relative, path, file_type = item
    try:
        before = path.stat()
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(chunk)
        after = path.stat()
    except OSError as exc:
        raise SourceChangedDuringRead(str(path)) from exc
    before_signature = (before.st_dev, before.st_ino, before.st_size, before.st_mtime_ns)
    after_signature = (after.st_dev, after.st_ino, after.st_size, after.st_mtime_ns)
    if before_signature != after_signature:
        raise SourceChangedDuringRead(str(path))
    return SourceManifestEntry(path=relative, sha256=digest.hexdigest(), type=file_type)


def build_source_manifest(
    root: Path,
    *,
    graph_path: Path,
    detection: dict[str, object] | None = None,
) -> SourceManifest:
    resolved_root = root.resolve()
    current_detection = detection or _detect_source(resolved_root, graph_path)
    paths = _manifest_paths(resolved_root, current_detection)
    with ThreadPoolExecutor() as pool:
        files = tuple(pool.map(_hash_file, paths))
    return SourceManifest(files=files)


def _extraction_manifest_covers(
    root: Path,
    detection: dict[str, object],
    manifest_path: Path,
    coverage_kinds: dict[str, str] | None,
) -> bool:
    from graphify.detect import load_manifest

    loaded = load_manifest(str(manifest_path), root=root)
    if not isinstance(loaded, dict):
        return False
    for relative, path, file_type in _manifest_paths(root, detection):
        entry = loaded.get(str(path))
        if not isinstance(entry, dict):
            return False
        coverage_kind = None
        if coverage_kinds is not None:
            coverage_kind = coverage_kinds.get(relative) or coverage_kinds.get(str(path))
            if coverage_kind is None:
                return False
        if coverage_kind not in (None, "ast", "semantic"):
            return False
        required_hash = (
            f"{coverage_kind}_hash"
            if coverage_kind is not None
            else ("ast_hash" if file_type == "code" else "semantic_hash")
        )
        expected = entry.get(required_hash)
        if not isinstance(expected, str) or not expected:
            return False
        digest = hashlib.md5(usedforsecurity=False)
        try:
            with path.open("rb") as source:
                for chunk in iter(lambda: source.read(1024 * 1024), b""):
                    digest.update(chunk)
        except OSError:
            return False
        if digest.hexdigest() != expected:
            return False
    return True


def publish_source_identity(
    graph_path: Path,
    root: Path,
    *,
    detection: dict[str, object] | None = None,
    extraction_manifest_path: Path | None = None,
    coverage_kinds: dict[str, str] | None = None,
) -> SourceIdentity:
    resolved_graph = graph_path.resolve()
    resolved_root = root.resolve()
    try:
        graph: Any = json.loads(resolved_graph.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"cannot publish identity for {resolved_graph}") from exc
    if not isinstance(graph, dict):
        raise ValueError(f"graph artifact is not an object: {resolved_graph}")

    current_detection = detection or _detect_source(resolved_root, resolved_graph)
    if extraction_manifest_path is not None and not _extraction_manifest_covers(
        resolved_root,
        current_detection,
        extraction_manifest_path,
        coverage_kinds,
    ):
        raise ValueError("extraction manifest does not cover the detected source files")

    manifest = build_source_manifest(
        resolved_root,
        graph_path=resolved_graph,
        detection=current_detection,
    )
    identity = SourceIdentity(
        root=str(resolved_root),
        revision=_git_revision(resolved_root),
        manifest_digest=manifest.digest(),
    )
    graph["source_identity"] = identity.to_dict()

    manifest_path = resolved_graph.parent / SOURCE_MANIFEST_FILENAME
    write_json_atomic(manifest_path, manifest.to_dict(), indent=2, ensure_ascii=False)
    write_json_atomic(resolved_graph, graph, indent=2, ensure_ascii=False)
    pending_path(resolved_graph).unlink(missing_ok=True)
    return identity


def _load_graph_identity(graph_path: Path) -> SourceIdentity | None:
    try:
        from graphify.security import check_graph_file_size_cap

        check_graph_file_size_cap(graph_path)
        value: Any = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(value, dict):
        return None
    return SourceIdentity.parse(value.get("source_identity"))


def _load_source_manifest(path: Path) -> SourceManifest | None:
    try:
        if path.stat().st_size > _MAX_SOURCE_MANIFEST_BYTES:
            return None
        value: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return SourceManifest.parse(value)


def freshness_status(root: Path, graph_path: Path | None = None) -> FreshnessStatus:
    resolved_root = root.resolve()
    resolved_graph = (graph_path or default_graph_path(resolved_root)).resolve()
    reasons: list[FreshnessReason] = []

    pending_names = (PENDING_FILENAME, *_OTHER_PENDING_FILENAMES)
    if any((resolved_graph.parent / name).exists() for name in pending_names):
        reasons.append(FreshnessReason.PENDING_RECONCILIATION)

    identity = _load_graph_identity(resolved_graph)
    if identity is None:
        reasons.append(FreshnessReason.MISSING_IDENTITY)
        return FreshnessStatus(str(resolved_graph), None, tuple(reasons))

    if Path(identity.root) != resolved_root:
        reasons.append(FreshnessReason.WRONG_ROOT)

    if identity.revision != _git_revision(resolved_root):
        reasons.append(FreshnessReason.REVISION_MISMATCH)

    manifest_path = resolved_graph.parent / SOURCE_MANIFEST_FILENAME
    if not manifest_path.is_file():
        reasons.append(FreshnessReason.MISSING_MANIFEST)
        return FreshnessStatus(str(resolved_graph), identity, tuple(reasons))

    stored_manifest = _load_source_manifest(manifest_path)
    if (
        stored_manifest is None
        or stored_manifest.detector != CURRENT_DETECTOR
        or stored_manifest.digest() != identity.manifest_digest
        or identity.detector != CURRENT_DETECTOR
    ):
        reasons.append(FreshnessReason.MANIFEST_MISMATCH)

    try:
        current_manifest = build_source_manifest(resolved_root, graph_path=resolved_graph)
    except (OSError, ValueError, SourceChangedDuringRead):
        current_manifest = None
    if current_manifest is None or current_manifest.digest() != identity.manifest_digest:
        reasons.append(FreshnessReason.CHANGED_SUPPORTED_FILES)

    return FreshnessStatus(str(resolved_graph), identity, tuple(reasons))


def format_bound_identity(identity: SourceIdentity) -> str:
    revision = identity.revision or "none"
    return (
        f"source root={identity.root} revision={revision} "
        f"manifest={identity.manifest_digest} "
        f"detector={identity.detector.name}/{identity.detector.version}"
    )


def status_command(args: list[str]) -> int:
    root = Path(".")
    graph_path: Path | None = None
    json_output = False
    positional: list[str] = []
    i = 0
    while i < len(args):
        arg = args[i]
        if arg == "--json":
            json_output = True
            i += 1
        elif arg == "--graph" and i + 1 < len(args):
            graph_path = Path(args[i + 1])
            i += 2
        elif arg.startswith("--graph="):
            graph_path = Path(arg.split("=", 1)[1])
            i += 1
        elif arg.startswith("-"):
            print(f"error: unknown status option: {arg}", file=sys.stderr)
            return 2
        else:
            positional.append(arg)
            i += 1
    if len(positional) > 1:
        print("error: status accepts at most one source path", file=sys.stderr)
        return 2
    if positional:
        root = Path(positional[0])
    if not root.exists() or not root.is_dir():
        print(f"error: source path not found: {root}", file=sys.stderr)
        return 2

    resolved_root = root.resolve()
    resolved_graph = (graph_path or default_graph_path(resolved_root)).resolve()
    status = freshness_status(resolved_root, resolved_graph)
    if json_output:
        print(json.dumps(status.to_dict(), ensure_ascii=False, sort_keys=True))
    elif status.eligible:
        print(f"Current: {resolved_graph}")
        if status.source_identity is not None:
            print(format_bound_identity(status.source_identity))
    else:
        print(f"Stale: {resolved_graph}")
        for reason in status.reasons:
            print(f"  {reason.value}")
    return 0 if status.eligible else 1
