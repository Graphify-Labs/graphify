"""Caller-owned product transactions; AST caches and runtime execution are separate.

Products are prepared on disk before publication. Ordinary exceptions restore the
prior cohort; process/power loss is not a multi-file atomicity guarantee. Failed
rollback retains recovery copies and reports integrity failure explicitly.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import stat
import sys
import tempfile

from graphify.paths import os_replace_with_fallback


def _same(left: Path, right: Path) -> bool:
    """Compare bounded chunks rather than duplicating large graph payloads in memory."""
    if not left.is_file() or not right.is_file() or left.stat().st_size != right.stat().st_size:
        return False
    with left.open("rb") as a, right.open("rb") as b:
        while True:
            chunk, other = a.read(1_048_576), b.read(1_048_576)
            if chunk != other:
                return False
            if not chunk:
                return True


def _remove_owned(path: Path) -> None:
    """Only transaction-owned copies may have their Windows read-only bit cleared."""
    try:
        path.unlink(missing_ok=True)
    except PermissionError:
        if os.name != "nt" or path.is_symlink():
            raise
        path.chmod(stat.S_IWRITE)
        path.unlink(missing_ok=True)


class ProductPublication:
    """One bounded output cohort with explicit stage/commit/rollback ownership.

    The caller supplies names and its replace boundary, preserving existing OS
    compatibility hooks. Existing serializers write independent stage paths;
    stages never establish accepted graph/root/manifest/state on their own.
    """

    def __init__(self, output: Path, names, *, replace=os_replace_with_fallback):
        self.output, self.replace = Path(output), replace
        self.targets, self.originals, self.stages = {}, {}, {}
        self.attempted, self.committed, self.recovery = [], False, False
        names = tuple(names)
        if len(names) > 32 or any(not isinstance(name, str) for name in names):
            raise ValueError("GRAPH_PUBLICATION_FAILED: invalid product inventory")
        if len(set(names)) != len(names):
            raise ValueError("GRAPH_PUBLICATION_FAILED: duplicate product inventory")
        seen = set()
        for name in names:
            if (not name or len(name) > 128 or any(char in name for char in "/\\:\0")
                    or Path(name).name != name or name in {".", ".."}):
                raise ValueError("GRAPH_PUBLICATION_FAILED: invalid product name")
            try:
                target = Path(os.path.realpath(self.output / name))
            except Exception as error:
                raise OSError("GRAPH_PUBLICATION_FAILED: cannot resolve product destination; prior products retained") from error
            identity = os.path.normcase(str(target))
            if identity in seen:
                raise ValueError("GRAPH_PUBLICATION_FAILED: products share one destination")
            seen.add(identity)
            self.targets[name] = target
        scratch_created = False
        try:
            # Setup is part of the publication boundary too. An OS error may
            # include private paths, and a partial setup owns only its scratch.
            self.output.mkdir(parents=True, exist_ok=True)
            self.scratch = Path(tempfile.mkdtemp(dir=self.output, prefix=".gfy-publish-"))
            scratch_created = True
            self.staging, self.snapshot, self.restore = (self.scratch / part for part in ("stage", "old", "restore"))
            for folder in (self.staging, self.snapshot, self.restore):
                folder.mkdir()
            for name, target in self.targets.items():
                original = self.snapshot / name
                if target.exists():
                    if not target.is_file():
                        raise OSError("GRAPH_PUBLICATION_FAILED: destination is not a file")
                    shutil.copy2(target, original)
                    self.originals[name] = original
                else:
                    self.originals[name] = None
        except BaseException as error:
            if scratch_created:
                try:
                    self._cleanup()
                except Exception as cleanup_error:
                    raise OSError("GRAPH_PUBLICATION_CLEANUP: prior products retained; setup cleanup retry required") from cleanup_error
            if isinstance(error, Exception):
                raise OSError("GRAPH_PUBLICATION_FAILED: cannot prepare product transaction; prior products retained") from error
            raise

    def __enter__(self):
        return self

    def stage(self, name: str) -> Path:
        """Seed prior bytes for existing serializers without touching accepted products."""
        if name not in self.targets:
            raise ValueError("GRAPH_PUBLICATION_FAILED: unknown product")
        if name not in self.stages:
            staged = self.staging / name
            original = self.originals[name]
            if original is not None:
                shutil.copy2(original, staged)
                # Own staging is writable even when its original is not. The
                # real destination is checked only if publication changes it.
                staged.chmod(staged.stat().st_mode | stat.S_IWRITE)
            self.stages[name] = staged
        return self.stages[name]

    def commit(self) -> tuple[str, ...]:
        """Publish prepared changes, then mark one coherent cohort committed."""
        changed = []
        # Even an unchanged stage must agree with its snapshot: another writer
        # cannot silently change one member while this run advances the rest.
        for name, target in self.targets.items():
            original = self.originals[name]
            if original is not None and not _same(target, original):
                raise OSError("GRAPH_PUBLICATION_FAILED: destination changed during preparation")
            if original is None and target.exists():
                raise OSError("GRAPH_PUBLICATION_FAILED: destination appeared during preparation")
        for name, stage in self.stages.items():
            target, original = self.targets[name], self.originals[name]
            if not stage.is_file():
                raise OSError("GRAPH_PUBLICATION_FAILED: staged product is missing")
            if original is not None and _same(stage, original):
                continue
            if original is not None:
                mode = target.stat().st_mode
                if os.name == "nt" and not mode & stat.S_IWRITE:
                    raise PermissionError("GRAPH_PUBLICATION_FAILED: read-only " + name)
                stage.chmod(stat.S_IMODE(mode))
            changed.append(name)
        try:
            for name in changed:
                self.targets[name].parent.mkdir(parents=True, exist_ok=True)
                self.attempted.append(name)
                self.replace(self.stages[name], self.targets[name])
        except BaseException:
            self._rollback()
            raise
        self.committed = True
        return tuple(changed)

    def _rollback(self) -> None:
        """Restore durable originals; a second fault keeps all remaining recovery copies."""
        # Retain recovery evidence until EVERY restoration finishes. Ordinary
        # non-OS faults and an interrupted rollback must not trigger cleanup.
        self.recovery = True
        failed = False
        for name in reversed(self.attempted):
            target, original = self.targets[name], self.originals[name]
            try:
                if original is None:
                    _remove_owned(target)
                elif not _same(target, original):
                    # Copy rather than consume recovery evidence until every
                    # restored target has completed and can be read back.
                    restore = self.restore / name
                    shutil.copy2(original, restore)
                    os_replace_with_fallback(restore, target)
                    if not _same(target, original):
                        raise OSError("Restored product does not match its snapshot")
            except Exception:
                failed = True
        if failed:
            raise OSError("GRAPH_PUBLICATION_RECOVERY: rollback incomplete; recovery copies retained")
        self.recovery = False

    def _cleanup(self) -> None:
        """Remove only known copies; unknown/locked files are retained for diagnosis."""
        for part in ("stage", "old", "restore"):
            # Reconstruct owned children so partially completed setup does not
            # require every stage attribute to have been assigned already.
            folder = self.scratch / part
            for name in self.targets:
                _remove_owned(folder / name)
            if folder.exists():
                folder.rmdir()
        self.scratch.rmdir()

    def __exit__(self, kind, error, traceback):
        if self.recovery:
            return False
        try:
            self._cleanup()
        except Exception:
            if self.committed:
                # Publication succeeded. Cleanup cannot retroactively report
                # a failed graph operation after its cohort became authoritative.
                print("warning: GRAPH_PUBLICATION_CLEANUP: committed products retained; cleanup retry required",
                      file=sys.stderr)
            else:
                raise OSError("GRAPH_PUBLICATION_CLEANUP: prior products retained; cleanup retry required") from error
        if isinstance(error, Exception) and not self.committed:
            # Do not expose serializer bodies or filesystem paths in the new
            # diagnostic. Chaining retains the precise internal failure cause.
            raise OSError("GRAPH_PUBLICATION_FAILED: product preparation or publication failed; prior products retained") from error
        return False
