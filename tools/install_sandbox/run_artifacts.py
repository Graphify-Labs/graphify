"""Host-owned install-sandbox run artifacts and managed-run retention."""

from __future__ import annotations

import json
import os
import re
import shutil
import stat
import sys
import threading
import uuid
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TextIO


SCHEMA_VERSION = 1
MANAGED_ROOT = Path(__file__).resolve().parent / "out"
TERMINAL_STATES = frozenset({"passed", "failed", "incomplete", "interrupted"})
VALID_STATES = TERMINAL_STATES | {"running"}
VALID_SCOPES = frozenset({"user", "project", "both"})

_SELECTION_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*\Z")
_RUN_ID_RE = re.compile(
    r"(?P<stamp>\d{8}T\d{6}Z)-"
    r"(?P<selection>[A-Za-z0-9][A-Za-z0-9._-]*)-"
    r"(?P<scope>user|project|both)"
    r"(?:-(?P<collision>\d{2,}))?\Z"
)

Clock = Callable[[], datetime]
WarningSink = Callable[[str], None]


class ArtifactError(ValueError):
    """An unsafe or invalid artifact destination was requested."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        raise ArtifactError("artifact timestamps must be timezone-aware")
    return value.astimezone(timezone.utc)


def _timestamp(value: datetime) -> str:
    return _as_utc(value).isoformat().replace("+00:00", "Z")


def _parse_timestamp(value: object) -> datetime:
    if not isinstance(value, str):
        raise ValueError("timestamp is not a string")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp has no timezone")
    return parsed.astimezone(timezone.utc)


def _atomic_write_json(path: Path, value: Mapping[str, Any]) -> None:
    """Replace *path* with one complete JSON document from the same directory."""

    encoded = (json.dumps(value, indent=2, sort_keys=True) + "\n").encode("utf-8")
    temporary = path.parent / f".{path.name}.{uuid.uuid4().hex}.tmp"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _is_within(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _selection_name(*, target: str | None, all_targets: bool) -> str:
    if bool(target) == bool(all_targets):
        raise ArtifactError("select exactly one target mode")
    selection = "all" if all_targets else str(target)
    if not _SELECTION_RE.fullmatch(selection):
        raise ArtifactError(f"unsafe selection for run ID: {selection!r}")
    return selection


def make_run_id(
    *,
    target: str | None,
    all_targets: bool,
    scope: str,
    started_at: datetime,
    collision: int = 1,
) -> str:
    """Return the sortable managed run ID for a selection and UTC instant."""

    if scope not in VALID_SCOPES:
        raise ArtifactError(f"unsupported scope: {scope!r}")
    if collision < 1:
        raise ArtifactError("collision number must be positive")
    selection = _selection_name(target=target, all_targets=all_targets)
    stamp = _as_utc(started_at).strftime("%Y%m%dT%H%M%SZ")
    suffix = "" if collision == 1 else f"-{collision:02d}"
    return f"{stamp}-{selection}-{scope}{suffix}"


def _prepare_managed_root(root: Path) -> Path:
    if root.is_symlink():
        raise ArtifactError(f"managed output root must not be a symlink: {root}")
    try:
        root.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise ArtifactError(f"cannot create managed output root {root}: {exc}") from exc
    if root.is_symlink() or not root.is_dir():
        raise ArtifactError(f"managed output root is not a real directory: {root}")
    return root.resolve()


def _allocate_managed_output(
    root: Path,
    *,
    target: str | None,
    all_targets: bool,
    scope: str,
    started_at: datetime,
) -> tuple[str, Path]:
    managed_root = _prepare_managed_root(root)
    collision = 1
    while True:
        run_id = make_run_id(
            target=target,
            all_targets=all_targets,
            scope=scope,
            started_at=started_at,
            collision=collision,
        )
        output = managed_root / run_id
        try:
            output.mkdir()
        except FileExistsError:
            collision += 1
            continue
        return run_id, output


def _allocate_external_output(output: Path, managed_root: Path) -> Path:
    requested = output.expanduser()
    if requested.is_symlink():
        raise ArtifactError(f"external output must not be a symlink: {requested}")

    lexical_output = Path(os.path.abspath(requested))
    lexical_root = Path(os.path.abspath(managed_root.expanduser()))
    resolved_output = requested.resolve(strict=False)
    resolved_root = managed_root.expanduser().resolve(strict=False)
    if _is_within(lexical_output, lexical_root) or _is_within(
        resolved_output,
        resolved_root,
    ):
        raise ArtifactError(
            f"explicit --output must be outside the managed output root: {managed_root}"
        )

    if requested.exists():
        if requested.is_symlink() or not requested.is_dir():
            raise ArtifactError(f"external output is not a real directory: {requested}")
        try:
            next(requested.iterdir())
        except StopIteration:
            pass
        except OSError as exc:
            raise ArtifactError(f"cannot inspect external output {requested}: {exc}") from exc
        else:
            raise ArtifactError(f"external output must be empty: {requested}")
    else:
        try:
            requested.mkdir(parents=True)
        except FileExistsError as exc:
            raise ArtifactError(
                f"external output changed while it was being allocated: {requested}"
            ) from exc
        except OSError as exc:
            raise ArtifactError(f"cannot create external output {requested}: {exc}") from exc

    if requested.is_symlink() or not requested.is_dir():
        raise ArtifactError(f"external output is not a real directory: {requested}")
    return requested.resolve()


class PhaseLogger:
    """Write phase-labelled host output to ``runner.log`` and the console."""

    def __init__(
        self,
        path: Path,
        *,
        phase: str,
        clock: Clock = _utc_now,
        stdout: TextIO | None = None,
        stderr: TextIO | None = None,
    ) -> None:
        if not phase:
            raise ArtifactError("log phase must not be empty")
        self.path = path
        self._phase = phase
        self._clock = clock
        self._stdout = stdout or sys.stdout
        self._stderr = stderr or sys.stderr
        self._stream = path.open("x", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()

    @property
    def closed(self) -> bool:
        return self._stream.closed

    def set_phase(self, phase: str) -> None:
        if not phase:
            raise ArtifactError("log phase must not be empty")
        with self._lock:
            if self.closed:
                raise RuntimeError("runner log is closed")
            self._phase = phase

    def write(self, stream: str, text: str) -> None:
        """Write labelled *text* and mirror it to the named console stream."""

        if stream not in {"command", "stdout", "stderr"}:
            raise ArtifactError(f"unsupported log stream: {stream!r}")
        if not isinstance(text, str):
            raise TypeError("log text must be a string")
        if not text:
            return

        with self._lock:
            if self.closed:
                raise RuntimeError("runner log is closed")
            timestamp = _timestamp(self._clock())
            destination = self._stderr if stream == "stderr" else self._stdout
            for line in text.splitlines() or [""]:
                rendered = f"[{timestamp}] [{self._phase}] [{stream}] {line}\n"
                self._stream.write(rendered)
                destination.write(rendered)
            self._stream.flush()
            destination.flush()

    def close(self) -> None:
        with self._lock:
            if not self.closed:
                self._stream.flush()
                self._stream.close()


@dataclass
class RunArtifacts:
    """A host-owned run directory, metadata document, and mirrored logger."""

    output: Path
    run_id: str
    managed: bool
    started_at: datetime
    logger: PhaseLogger
    _metadata: dict[str, Any] = field(repr=False)
    _clock: Clock = field(repr=False)

    @classmethod
    def allocate(
        cls,
        *,
        repo: Path,
        target: str | None,
        all_targets: bool,
        scope: str,
        output: Path | None = None,
        managed_root: Path = MANAGED_ROOT,
        clock: Clock = _utc_now,
        phase: str = "host_preflight",
    ) -> RunArtifacts:
        """Allocate one fresh run and create its host artifacts immediately."""

        if not phase:
            raise ArtifactError("run phase must not be empty")
        started_at = _as_utc(clock())
        if output is None:
            run_id, allocated_output = _allocate_managed_output(
                managed_root,
                target=target,
                all_targets=all_targets,
                scope=scope,
                started_at=started_at,
            )
            managed = True
        else:
            run_id = make_run_id(
                target=target,
                all_targets=all_targets,
                scope=scope,
                started_at=started_at,
            )
            allocated_output = _allocate_external_output(output, managed_root)
            managed = False

        selection = {
            "all": all_targets,
            "target": target,
            "scope": scope,
        }
        metadata: dict[str, Any] = {
            "schema_version": SCHEMA_VERSION,
            "run_id": run_id,
            "managed": managed,
            "started_at": _timestamp(started_at),
            "updated_at": _timestamp(started_at),
            "finished_at": None,
            "repository": str(_resolved(repo)),
            "output": str(allocated_output),
            "selection": selection,
            "phase": phase,
            "state": "running",
            "exit_code": None,
        }
        _atomic_write_json(allocated_output / "run.json", metadata)
        logger = PhaseLogger(
            allocated_output / "runner.log",
            phase=phase,
            clock=clock,
        )
        return cls(
            output=allocated_output,
            run_id=run_id,
            managed=managed,
            started_at=started_at,
            logger=logger,
            _metadata=metadata,
            _clock=clock,
        )

    @property
    def metadata(self) -> Mapping[str, Any]:
        return dict(self._metadata)

    def set_phase(self, phase: str) -> None:
        """Move a running invocation to another host phase atomically."""

        if self._metadata["state"] != "running":
            raise RuntimeError("cannot change phase after run finalization")
        if not phase:
            raise ArtifactError("run phase must not be empty")
        updated = dict(self._metadata)
        updated["phase"] = phase
        updated["updated_at"] = _timestamp(self._clock())
        _atomic_write_json(self.output / "run.json", updated)
        self._metadata = updated
        self.logger.set_phase(phase)

    def complete_outputs(self) -> bool:
        """Return whether fresh container-owned manifest and report files exist."""

        return complete_outputs(self.output, self.started_at)

    def finalize(self, state: str, exit_code: int) -> None:
        """Close host logging and atomically record one terminal state."""

        if state not in TERMINAL_STATES:
            raise ArtifactError(f"invalid terminal run state: {state!r}")
        if self._metadata["state"] != "running":
            raise RuntimeError("run has already been finalized")
        if not isinstance(exit_code, int):
            raise TypeError("exit code must be an integer")

        finished_at = _as_utc(self._clock())
        updated = dict(self._metadata)
        updated.update(
            {
                "state": state,
                "exit_code": exit_code,
                "updated_at": _timestamp(finished_at),
                "finished_at": _timestamp(finished_at),
            }
        )
        try:
            self.logger.close()
        finally:
            _atomic_write_json(self.output / "run.json", updated)
            self._metadata = updated


def fresh_regular_file(path: Path, started_at: datetime) -> bool:
    """Return whether *path* is a fresh, non-empty regular file, not a symlink."""

    try:
        details = path.lstat()
    except OSError:
        return False
    return (
        stat.S_ISREG(details.st_mode)
        and not path.is_symlink()
        and details.st_size > 0
        and details.st_mtime >= _as_utc(started_at).timestamp()
    )


def complete_outputs(output: Path, started_at: datetime) -> bool:
    """Check the complete, fresh container-owned top-level output contract."""

    return all(
        fresh_regular_file(output / name, started_at)
        for name in ("manifest.json", "report.md")
    )


@dataclass(frozen=True)
class _PruneCandidate:
    path: Path
    started_at: datetime
    collision: int


def _warn_to_stderr(message: str) -> None:
    print(f"warning: {message}", file=sys.stderr)


def _prune_candidate(path: Path, warn: WarningSink) -> _PruneCandidate | None:
    try:
        if path.is_symlink():
            warn(f"preserving symlinked managed-root entry: {path}")
            return None
        if not path.is_dir():
            warn(f"preserving non-directory managed-root entry: {path}")
            return None
        metadata_path = path / "run.json"
        if metadata_path.is_symlink():
            warn(f"preserving run with symlinked metadata: {path}")
            return None
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            warn(f"preserving unmarked managed-root directory: {path}")
            return None
        except (OSError, UnicodeError) as exc:
            warn(f"preserving unreadable run metadata at {path}: {exc}")
            return None
        except json.JSONDecodeError as exc:
            warn(f"preserving malformed run metadata at {path}: {exc}")
            return None
    except FileNotFoundError:
        return None
    except OSError as exc:
        warn(f"preserving managed-root entry that could not be inspected at {path}: {exc}")
        return None

    if not isinstance(metadata, dict):
        warn(f"preserving malformed run metadata at {path}: expected an object")
        return None
    if metadata.get("schema_version") != SCHEMA_VERSION:
        warn(f"preserving run with unknown metadata schema at {path}")
        return None
    if metadata.get("managed") is not True:
        warn(f"preserving externally owned run at {path}")
        return None
    if metadata.get("run_id") != path.name:
        warn(f"preserving run whose ID does not match its directory at {path}")
        return None

    match = _RUN_ID_RE.fullmatch(path.name)
    if match is None:
        warn(f"preserving managed run with malformed ID at {path}")
        return None
    if metadata.get("output") != str(path.resolve()):
        warn(f"preserving run whose recorded output path does not match {path}")
        return None
    if not isinstance(metadata.get("repository"), str):
        warn(f"preserving run without a repository path at {path}")
        return None
    if not isinstance(metadata.get("phase"), str) or not metadata["phase"]:
        warn(f"preserving run without a phase at {path}")
        return None

    selection = metadata.get("selection")
    expected_selection = match.group("selection")
    if (
        not isinstance(selection, dict)
        or selection.get("scope") != match.group("scope")
        or selection.get("all") is not (expected_selection == "all")
        or selection.get("target")
        != (None if expected_selection == "all" else expected_selection)
    ):
        warn(f"preserving run with malformed selection metadata at {path}")
        return None

    state = metadata.get("state")
    if state == "running":
        warn(f"preserving running managed run: {path}")
        return None
    if state not in TERMINAL_STATES:
        warn(f"preserving run with unknown state at {path}")
        return None
    if not isinstance(metadata.get("exit_code"), int):
        warn(f"preserving terminal run without an exit code at {path}")
        return None
    if not isinstance(metadata.get("finished_at"), str):
        warn(f"preserving terminal run without a finished timestamp at {path}")
        return None

    try:
        started_at = _parse_timestamp(metadata.get("started_at"))
        _parse_timestamp(metadata.get("updated_at"))
        _parse_timestamp(metadata.get("finished_at"))
    except (TypeError, ValueError) as exc:
        warn(f"preserving run with malformed timestamps at {path}: {exc}")
        return None
    collision_text = match.group("collision")
    collision = int(collision_text) if collision_text is not None else 1
    return _PruneCandidate(path=path, started_at=started_at, collision=collision)


def prune_managed_runs(
    root: Path = MANAGED_ROOT,
    *,
    keep: int = 5,
    warn: WarningSink = _warn_to_stderr,
) -> tuple[Path, ...]:
    """Remove only surplus, positively marked terminal managed runs."""

    if keep < 0:
        raise ArtifactError("managed-run retention must not be negative")
    if root.is_symlink():
        warn(f"refusing to prune symlinked managed output root: {root}")
        return ()
    try:
        entries = tuple(root.iterdir())
    except FileNotFoundError:
        return ()
    except OSError as exc:
        warn(f"could not inspect managed output root {root}: {exc}")
        return ()

    candidates = [
        candidate
        for entry in entries
        if (candidate := _prune_candidate(entry, warn)) is not None
    ]
    candidates.sort(
        key=lambda candidate: (
            candidate.started_at,
            candidate.collision,
            candidate.path.name,
        ),
        reverse=True,
    )

    removed: list[Path] = []
    for candidate in candidates[keep:]:
        # Re-read the positive ownership marker immediately before deletion.
        if _prune_candidate(candidate.path, warn) is None:
            continue
        try:
            shutil.rmtree(candidate.path)
        except FileNotFoundError:
            continue
        except OSError as exc:
            warn(f"could not prune managed run {candidate.path}: {exc}")
            continue
        removed.append(candidate.path)
    return tuple(removed)
