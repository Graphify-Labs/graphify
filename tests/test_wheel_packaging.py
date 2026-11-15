"""Packaging guard (#1121 follow-up): the 5 skillgen guards check the *repo tree*,
not the *built wheel*. A host whose references bundle or always-on block fails to
match the `package-data` globs would pass `--check`/`--audit-coverage` yet make
`graphify install` hard-exit with "not found in package" for real users.

This builds the wheel once and asserts every committed skill artifact ships in it.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
import tempfile
import zipfile
from contextlib import contextmanager
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]
PKG = REPO / "graphify"


def _has_build() -> bool:
    try:
        subprocess.run(
            [sys.executable, "-m", "build", "--version"],
            check=True, capture_output=True,
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def _skill_bodies() -> list[Path]:
    """Every distinct skill body a platform installs (the SKILL.md is copied from
    one of these). A body missing from the wheel makes `graphify install
    --platform <host>` hard-exit "not found in package" — the exact failure that
    motivated adding the agents platform's skill-agents.md to package-data."""
    from graphify.__main__ import _PLATFORM_CONFIG

    names = {cfg["skill_file"] for cfg in _PLATFORM_CONFIG.values()}
    return sorted({PKG / name for name in names})


def _expected_artifacts() -> list[Path]:
    """Every committed skill body + references/*.md (per host) + always_on/*.md block."""
    bodies = _skill_bodies()
    refs = sorted((PKG / "skills").glob("*/references/*.md"))
    always = sorted((PKG / "always_on").glob("*.md"))
    # Sanity: if these are empty the test wiring is broken, not the wheel.
    assert bodies, "no platform skill bodies found — packaging test mis-wired"
    assert refs, "no skills/*/references/*.md found in repo — packaging test mis-wired"
    assert always, "no always_on/*.md found in repo — packaging test mis-wired"
    return bodies + refs + always


@contextmanager
def _wheel_build_lock():
    """Serialise wheel builds that share one checkout's ``build/`` dir (#4603).

    ``python -m build --no-isolation`` runs setuptools in the repo, whose
    default ``build/`` dir is shared by every process on that checkout: two
    concurrent pytest runs deleted each other's staged files and one run then
    skipped all dependent tests. The lock file lives in the system temp dir,
    keyed by the repo path, so it is shared across processes on the same
    checkout without adding anything to the checkout itself. fcntl locks are
    released by the OS even when the holder is killed, so a dead run never
    wedges later ones. Platforms without fcntl fall back to no locking.
    """
    try:
        import fcntl
    except ImportError:
        yield
        return
    key = hashlib.sha256(str(REPO).encode()).hexdigest()[:16]
    lock_path = Path(tempfile.gettempdir()) / f"graphify-wheel-build-{key}.lock"
    with open(lock_path, "a+") as fh:
        fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(fh.fileno(), fcntl.LOCK_UN)


@pytest.fixture(scope="module")
def wheel_namelist(tmp_path_factory) -> set[str]:
    if not _has_build():
        pytest.skip("`python -m build` unavailable (dev extra not installed)")
    out = tmp_path_factory.mktemp("wheel")
    with _wheel_build_lock():
        proc = subprocess.run(
            [sys.executable, "-m", "build", "--wheel", "--no-isolation",
             "--outdir", str(out), str(REPO)],
            capture_output=True, text=True,
        )
    if proc.returncode != 0:
        # A wheel build that fails here fails for a packaging reason the guards
        # below exist to catch (or a genuinely broken checkout); skipping hid
        # exactly that, reporting 133 green skips instead (#4603).
        pytest.fail(f"wheel build failed in this env:\n{proc.stderr[-800:]}")
    wheels = list(out.glob("graphifyy-*.whl"))
    assert wheels, "no wheel produced"
    with zipfile.ZipFile(max(wheels, key=lambda p: p.stat().st_mtime)) as z:
        return set(z.namelist())


@pytest.mark.parametrize(
    "artifact",
    _expected_artifacts(),
    ids=lambda p: str(p.relative_to(PKG)),
)
def test_skill_artifact_ships_in_wheel(artifact: Path, wheel_namelist: set[str]) -> None:
    rel = "graphify/" + artifact.relative_to(PKG).as_posix()
    assert rel in wheel_namelist, (
        f"{rel} is committed in the repo but NOT in the built wheel — "
        f"`graphify install` would hard-exit for this host. Check the "
        f"[tool.setuptools.package-data] globs in pyproject.toml."
    )
