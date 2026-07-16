# mypy: allow-untyped-defs
"""Support for providing temporary directories to test functions."""

from __future__ import annotations

import atexit
from collections.abc import Generator
from contextlib import ExitStack
import dataclasses
import os
from pathlib import Path
import re
from shutil import rmtree
import stat
import tempfile
from typing import Any
from typing import final
from typing import Literal

from .pathlib import cleanup_dead_symlinks
from .pathlib import LOCK_TIMEOUT
from .pathlib import make_numbered_dir
from .pathlib import make_numbered_dir_with_cleanup
from .pathlib import rm_rf
from _pytest.compat import get_user_id
from _pytest.config import Config
from _pytest.config import ExitCode
from _pytest.config import hookimpl
from _pytest.config.argparsing import Parser
from _pytest.deprecated import check_ispytest
from _pytest.fixtures import fixture
from _pytest.fixtures import FixtureRequest
from _pytest.monkeypatch import MonkeyPatch
from _pytest.nodes import Item
from _pytest.reports import TestReport
from _pytest.stash import StashKey


tmppath_result_key = StashKey[dict[str, bool]]()
RetentionType = Literal["all", "failed", "none"]


@final
@dataclasses.dataclass
class TempPathFactory:
    """Factory for temporary directories under the common base temp directory,
    as discussed at :ref:`temporary directory location and retention`.
    """

    _given_basetemp: Path | None
    # pluggy TagTracerSub, not currently exposed, so Any.
    _trace: Any
    _basetemp: Path | None
    _retention_count: int
    _retention_policy: RetentionType

    def __init__(
        self,
        given_basetemp: Path | None,
        retention_count: int,
        retention_policy: RetentionType,
        trace,
        basetemp: Path | None = None,
        *,
        _ispytest: bool = False,
    ) -> None:
        check_ispytest(_ispytest)
        if given_basetemp is None:
            self._given_basetemp = None
        else:
            # Use os.path.abspath() to get absolute path instead of resolve() as it
            # does not work the same in all platforms (see #4427).
            # Path.absolute() exists, but it is not public (see https://bugs.python.org/issue25012).
            self._given_basetemp = Path(os.path.abspath(str(given_basetemp)))
        self._trace = trace
        self._retention_count = retention_count
        self._retention_policy = retention_policy
        self._basetemp = basetemp
        # Register cleanups for session finish. Also called atexit as a last
        # resort if sessionfinish for some reason doesn't happen.
        self._exit_stack = ExitStack()

    @classmethod
    def from_config(
        cls,
        config: Config,
        *,
        _ispytest: bool = False,
    ) -> TempPathFactory:
        """Create a factory according to pytest configuration.

        :meta private:
        """
        check_ispytest(_ispytest)
        count = int(config.getini("tmp_path_retention_count"))
        if count < 0:
            raise ValueError(
                f"tmp_path_retention_count must be >= 0. Current input: {count}."
            )

        policy = config.getini("tmp_path_retention_policy")
        if policy not in ("all", "failed", "none"):
            raise ValueError(
                f"tmp_path_retention_policy must be either all, failed, none. Current input: {policy}."
            )

        return cls(
            given_basetemp=config.option.basetemp,
            trace=config.trace.get("tmpdir"),
            retention_count=count,
            retention_policy=policy,
            _ispytest=True,
        )

    def _ensure_relative_to_basetemp(self, basename: str) -> str:
        basename = os.path.normpath(basename)
        if (self.getbasetemp() / basename).resolve().parent != self.getbasetemp():
            raise ValueError(f"{basename} is not a normalized and relative path")
        return basename

    def mktemp(self, basename: str, numbered: bool = True) -> Path:
        """Create a new temporary directory managed by the factory.

        :param basename:
            Directory base name, must be a relative path.

        :param numbered:
            If ``True``, ensure the directory is unique by adding a numbered
            suffix greater than any existing one: ``basename="foo-"`` and ``numbered=True``
            means that this function will create directories named ``"foo-0"``,
            ``"foo-1"``, ``"foo-2"`` and so on.

        :returns:
            The path to the new directory.
        """
        basename = self._ensure_relative_to_basetemp(basename)
        if not numbered:
            p = self.getbasetemp().joinpath(basename)
            p.mkdir(mode=0o700)
        else:
            p = make_numbered_dir(root=self.getbasetemp(), prefix=basename, mode=0o700)
            self._trace("mktemp", p)
        return p

    def getbasetemp(self) -> Path:
        """Return the base temporary directory, creating it if needed.

        :returns:
            The base temporary directory.
        """
        if self._basetemp is not None:
            return self._basetemp

        if self._given_basetemp is not None:
            basetemp = self._given_basetemp
            if basetemp.exists():
                rm_rf(basetemp)
            basetemp.mkdir(mode=0o700)
            basetemp = basetemp.resolve()
        else:
            from_env = os.environ.get("PYTEST_DEBUG_TEMPROOT")
            temproot = Path(from_env or tempfile.gettempdir()).resolve()
            user = get_user() or "unknown"
            # use a sub-directory in the temproot to speed-up
            # make_numbered_dir() call
            rootdir = temproot.joinpath(f"pytest-of-{user}")
            try:
                rootdir.mkdir(mode=0o700, exist_ok=True)
            except OSError:
                # getuser() likely returned illegal characters for the platform, use unknown back off mechanism
                rootdir = temproot.joinpath("pytest-of-unknown")
                rootdir.mkdir(mode=0o700, exist_ok=True)
            # Because we use exist_ok=True with a predictable name, make sure
            # we are the owners, to prevent any funny business (on unix, where
            # temproot is usually shared).
            # Also, to keep things private, fixup any world-readable temp
            # rootdir's permissions. Historically 0o755 was used, so we can't
            # just error out on this, at least for a while.
            # Don't follow symlinks, otherwise we're open to symlink-swapping
            # TOCTOU vulnerability.
            # This check makes us vulnerable to a DoS - a user can `mkdir
            # /tmp/pytest-of-otheruser` and then `otheruser` will fail this
            # check. For now we don't consider it a real problem. otheruser can
            # change their TMPDIR or --basetemp, and maybe give the prankster a
            # good scolding.
            uid = get_user_id()
            if uid is not None:
                stat_follow_symlinks = (
                    False if os.stat in os.supports_follow_symlinks else True
                )
                rootdir_stat = rootdir.stat(follow_symlinks=stat_follow_symlinks)
                if stat.S_ISLNK(rootdir_stat.st_mode):
                    raise OSError(
                        f"The temporary directory {rootdir} is a symbolic link. "
                        "Fix this and try again."
                    )
                if rootdir_stat.st_uid != uid:
                    raise OSError(
                        f"The temporary directory {rootdir} is not owned by the current user. "
                        "Fix this and try again."
                    )
                if (rootdir_stat.st_mode & 0o077) != 0:
                    chmod_follow_symlinks = (
                        False if os.chmod in os.supports_follow_symlinks else True
                    )
                    rootdir.chmod(
                        rootdir_stat.st_mode & ~0o077,
                        follow_symlinks=chmod_follow_symlinks,
                    )
            keep = self._retention_count
            if self._retention_policy == "none":
                keep = 0
            basetemp = make_numbered_dir_with_cleanup(
                prefix="pytest-",
                root=rootdir,
                keep=keep,
                lock_timeout=LOCK_TIMEOUT,
                mode=0o700,
                register=self._exit_stack.callback,
            )
            # Ensure that the cleanup is called on exit (#1120 possibly?).
            # But if the exit stack is closed manually (as it normally should),
            # unregister the atexit to avoid pile up.
            atexit.register(self._exit_stack.close)
            self._exit_stack.callback(atexit.unregister, self._exit_stack.close)
        assert basetemp is not None, basetemp
        self._basetemp = basetemp
        self._trace("new basetemp", basetemp)
        return basetemp


def get_user() -> str | None:
    """Return the current user name, or None if getuser() does not work
    in the current environment (see #1010)."""
    try:
        # In some exotic environments, getpass may not be importable.
        import getpass

        return getpass.getuser()
    except (ImportError, OSError, KeyError):
        return None


def pytest_configure(config: Config) -> None:
    """Create a TempPathFactory and attach it to the config object.

    This is to comply with existing plugins which expect the handler to be
    available at pytest_configure time, but ideally should be moved entirely
    to the tmp_path_factory session fixture.
    """
    mp = MonkeyPatch()
    config.add_cleanup(mp.undo)
    _tmp_path_factory = TempPathFactory.from_config(config, _ispytest=True)
    mp.setattr(config, "_tmp_path_factory", _tmp_path_factory, raising=False)


def pytest_addoption(parser: Parser) -> None:
    parser.addini(
        "tmp_path_retention_count",
        help="How many sessions should we keep the `tmp_path` directories, according to `tmp_path_retention_policy`.",
        default="3",
        # NOTE: Would have been better as an `int` but can't change it now.
        type="string",
    )

    parser.addini(
        "tmp_path_retention_policy",
        help="Controls which directories created by the `tmp_path` fixture are kept around, based on test outcome. "
        "(all/failed/none)",
        type="string",
        default="all",
    )


@fixture(scope="session")
def tmp_path_factory(request: FixtureRequest) -> TempPathFactory:
    """Return a :class:`pytest.TempPathFactory` instance for the test session."""
    # Set dynamically by pytest_configure() above.
    return request.config._tmp_path_factory  # type: ignore


def _mk_tmp(request: FixtureRequest, factory: TempPathFactory) -> Path:
    name = request.node.name
    name = re.sub(r"[\W]", "_", name)
    MAXVAL = 30
    name = name[:MAXVAL]
    return factory.mktemp(name, numbered=True)


@fixture
def tmp_path(
    request: FixtureRequest, tmp_path_factory: TempPathFactory
) -> Generator[Path]:
    """Return a temporary directory (as :class:`pathlib.Path` object)
    which is unique to each test function invocation.
    The temporary directory is created as a subdirectory
    of the base temporary directory, with configurable retention,
    as discussed in :ref:`temporary directory location and retention`.
    """
    path = _mk_tmp(request, tmp_path_factory)
    yield path

    # Remove the tmpdir if the policy is "failed" and the test passed.
    policy = tmp_path_factory._retention_policy
    result_dict = request.node.stash[tmppath_result_key]

    if policy == "failed" and result_dict.get("call", True):
        # We do a "best effort" to remove files, but it might not be possible due to some leaked resource,
        # permissions, etc, in which case we ignore it.
        rmtree(path, ignore_errors=True)

    del request.node.stash[tmppath_result_key]


def pytest_sessionfinish(session, exitstatus: int | ExitCode):
    """After each session, remove base directory if all the tests passed,
    the policy is "failed", and the basetemp is not specified by a user.
    """
    tmp_path_factory: TempPathFactory = session.config._tmp_path_factory
    basetemp = tmp_path_factory._basetemp
    if basetemp is None:
        return

    policy = tmp_path_factory._retention_policy
    if (
        exitstatus == 0
        and policy == "failed"
        and tmp_path_factory._given_basetemp is None
    ):
        if basetemp.is_dir():
            # We do a "best effort" to remove files, but it might not be possible due to some leaked resource,
            # permissions, etc, in which case we ignore it.
            rmtree(basetemp, ignore_errors=True)

    # Remove dead symlinks.
    if basetemp.is_dir():
        cleanup_dead_symlinks(basetemp)

    # Run the numbered dirs and lock file cleanups registered on the ExitStack.
    tmp_path_factory._exit_stack.close()


@hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(
    item: Item, call
) -> Generator[None, TestReport, TestReport]:
    rep = yield
    assert rep.when is not None
    empty: dict[str, bool] = {}
    item.stash.setdefault(tmppath_result_key, empty)[rep.when] = rep.passed
    return rep
