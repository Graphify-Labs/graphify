# mypy: allow-untyped-defs
"""Implementation of the cache provider."""

# This plugin was not named "cache" to avoid conflicts with the external
# pytest-cache version.
from __future__ import annotations

from collections.abc import Generator
from collections.abc import Iterable
import dataclasses
import errno
import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import final

from .pathlib import resolve_from_str
from .pathlib import rm_rf
from .reports import CollectReport
from _pytest import nodes
from _pytest._io import TerminalWriter
from _pytest.config import Config
from _pytest.config import ExitCode
from _pytest.config import hookimpl
from _pytest.config.argparsing import Parser
from _pytest.deprecated import check_ispytest
from _pytest.fixtures import fixture
from _pytest.fixtures import FixtureRequest
from _pytest.main import Session
from _pytest.nodes import Directory
from _pytest.nodes import File
from _pytest.reports import TestReport


CACHEDIR_FILES: dict[str, bytes] = {
    "README.md": b"""\
# pytest cache directory #

This directory contains data from the pytest's cache plugin,
which provides the `--lf` and `--ff` options, as well as the `cache` fixture.

**Do not** commit this to version control.

See [the docs](https://docs.pytest.org/en/stable/how-to/cache.html) for more information.
""",
    ".gitignore": b"# Created by pytest automatically.\n*\n",
    "CACHEDIR.TAG": b"""\
Signature: 8a477f597d28d172789f06886806bc55
# This file is a cache directory tag created by pytest.
# For information about cache directory tags, see:
#	https://bford.info/cachedir/spec.html
""",
}


def _make_cachedir(target: Path) -> None:
    """Create the pytest cache directory atomically with supporting files.

    Creates a temporary directory with README.md, .gitignore, and CACHEDIR.TAG,
    then atomically renames it to the target location. If another process wins
    the race, the temporary directory is cleaned up.
    """
    target.parent.mkdir(parents=True, exist_ok=True)
    path = Path(tempfile.mkdtemp(prefix="pytest-cache-files-", dir=target.parent))
    try:
        # Reset permissions to the default, see #12308.
        # Note: there's no way to get the current umask atomically, eek.
        umask = os.umask(0o022)
        os.umask(umask)
        path.chmod(0o777 - umask)

        for name, content in CACHEDIR_FILES.items():
            path.joinpath(name).write_bytes(content)

        path.rename(target)
    except OSError as e:
        # If 2 concurrent pytests both race to the rename, the loser
        # gets "Directory not empty" from the rename. In this case,
        # everything is handled so just continue after cleanup.
        # On Windows, the error is a FileExistsError which translates to EEXIST.
        if e.errno not in (errno.ENOTEMPTY, errno.EEXIST):
            raise
    finally:
        shutil.rmtree(path, ignore_errors=True)


@final
@dataclasses.dataclass
class Cache:
    """Instance of the `cache` fixture."""

    _cachedir: Path = dataclasses.field(repr=False)
    _config: Config = dataclasses.field(repr=False)

    # Sub-directory under cache-dir for directories created by `mkdir()`.
    _CACHE_PREFIX_DIRS = "d"

    # Sub-directory under cache-dir for values created by `set()`.
    _CACHE_PREFIX_VALUES = "v"

    def __init__(
        self, cachedir: Path, config: Config, *, _ispytest: bool = False
    ) -> None:
        check_ispytest(_ispytest)
        self._cachedir = cachedir
        self._config = config

    @classmethod
    def for_config(cls, config: Config, *, _ispytest: bool = False) -> Cache:
        """Create the Cache instance for a Config.

        :meta private:
        """
        check_ispytest(_ispytest)
        cachedir = cls.cache_dir_from_config(config, _ispytest=True)
        if config.getoption("cacheclear") and cachedir.is_dir():
            cls.clear_cache(cachedir, _ispytest=True)
        return cls(cachedir, config, _ispytest=True)

    @classmethod
    def clear_cache(cls, cachedir: Path, _ispytest: bool = False) -> None:
        """Clear the sub-directories used to hold cached directories and values.

        :meta private:
        """
        check_ispytest(_ispytest)
        for prefix in (cls._CACHE_PREFIX_DIRS, cls._CACHE_PREFIX_VALUES):
            d = cachedir / prefix
            if d.is_dir():
                rm_rf(d)

    @staticmethod
    def cache_dir_from_config(config: Config, *, _ispytest: bool = False) -> Path:
        """Get the path to the cache directory for a Config.

        :meta private:
        """
        check_ispytest(_ispytest)
        return resolve_from_str(config.getini("cache_dir"), config.rootpath)

    def warn(self, fmt: str, *, _ispytest: bool = False, **args: object) -> None:
        """Issue a cache warning.

        :meta private:
        """
        check_ispytest(_ispytest)
        import warnings

        from _pytest.warning_types import PytestCacheWarning

        warnings.warn(
            PytestCacheWarning(fmt.format(**args) if args else fmt),
            self._config.hook,
            stacklevel=3,
        )

    def _mkdir(self, path: Path) -> None:
        self._ensure_cache_dir_and_supporting_files()
        path.mkdir(exist_ok=True, parents=True)

    def mkdir(self, name: str) -> Path:
        """Return a directory path object with the given name.

        If the directory does not yet exist, it will be created. You can use
        it to manage files to e.g. store/retrieve database dumps across test
        sessions.

        .. versionadded:: 7.0

        :param name:
            Must be a string not containing a ``/`` separator.
            Make sure the name contains your plugin or application
            identifiers to prevent clashes with other cache users.
        """
        path = Path(name)
        if len(path.parts) > 1:
            raise ValueError("name is not allowed to contain path separators")
        res = self._cachedir.joinpath(self._CACHE_PREFIX_DIRS, path)
        self._mkdir(res)
        return res

    def _getvaluepath(self, key: str) -> Path:
        return self._cachedir.joinpath(self._CACHE_PREFIX_VALUES, Path(key))

    def get(self, key: str, default):
        """Return the cached value for the given key.

        If no value was yet cached or the value cannot be read, the specified
        default is returned.

        :param key:
            Must be a ``/`` separated value. Usually the first
            name is the name of your plugin or your application.
        :param default:
            The value to return in case of a cache-miss or invalid cache value.
        """
        path = self._getvaluepath(key)
        try:
            with path.open("r", encoding="UTF-8") as f:
                return json.load(f)
        except (ValueError, OSError):
            return default

    def set(self, key: str, value: object) -> None:
        """Save value for the given key.

        :param key:
            Must be a ``/`` separated value. Usually the first
            name is the name of your plugin or your application.
        :param value:
            Must be of any combination of basic python types,
            including nested types like lists of dictionaries.
        """
        path = self._getvaluepath(key)
        try:
            self._mkdir(path.parent)
        except OSError as exc:
            self.warn(
                f"could not create cache path {path}: {exc}",
                _ispytest=True,
            )
            return
        data = json.dumps(value, ensure_ascii=False, indent=2)
        try:
            f = path.open("w", encoding="UTF-8")
        except OSError as exc:
            self.warn(
                f"cache could not write path {path}: {exc}",
                _ispytest=True,
            )
        else:
            with f:
                f.write(data)

    def _ensure_cache_dir_and_supporting_files(self) -> None:
        """Create the cache dir and its supporting files."""
        if not self._cachedir.is_dir():
            _make_cachedir(self._cachedir)


class LFPluginCollWrapper:
    def __init__(self, lfplugin: LFPlugin) -> None:
        self.lfplugin = lfplugin
        self._collected_at_least_one_failure = False

    @hookimpl(wrapper=True)
    def pytest_make_collect_report(
        self, collector: nodes.Collector
    ) -> Generator[None, CollectReport, CollectReport]:
        res = yield
        if isinstance(collector, Session | Directory):
            # Sort any lf-paths to the beginning.
            lf_paths = self.lfplugin._last_failed_paths

            # Use stable sort to prioritize last failed.
            def sort_key(node: nodes.Item | nodes.Collector) -> bool:
                return node.path in lf_paths

            res.result = sorted(
                res.result,
                key=sort_key,
                reverse=True,
            )

        elif isinstance(collector, File):
            if collector.path in self.lfplugin._last_failed_paths:
                result = res.result
                lastfailed = self.lfplugin.lastfailed

                # Only filter with known failures.
                if not self._collected_at_least_one_failure:
                    if not any(x.nodeid in lastfailed for x in result):
                        return res
                    self.lfplugin.config.pluginmanager.register(
                        LFPluginCollSkipfiles(self.lfplugin), "lfplugin-collskip"
                    )
                    self._collected_at_least_one_failure = True

                session = collector.session
                result[:] = [
                    x
                    for x in result
                    if x.nodeid in lastfailed
                    # Include any passed arguments (not trivial to filter).
                    or session.isinitpath(x.path)
                    # Keep all sub-collectors.
                    or isinstance(x, nodes.Collector)
                ]

        return res


class LFPluginCollSkipfiles:
    def __init__(self, lfplugin: LFPlugin) -> None:
        self.lfplugin = lfplugin

    @hookimpl
    def pytest_make_collect_report(
        self, collector: nodes.Collector
    ) -> CollectReport | None:
        if isinstance(collector, File):
            if collector.path not in self.lfplugin._last_failed_paths:
                self.lfplugin._skipped_files += 1

                return CollectReport(
                    collector.nodeid, "passed", longrepr=None, result=[]
                )
        return None


class LFPlugin:
    """Plugin which implements the --lf (run last-failing) option."""

    def __init__(self, config: Config) -> None:
        self.config = config
        active_keys = "lf", "failedfirst"
        self.active = any(config.getoption(key) for key in active_keys)
        assert config.cache
        self.lastfailed: dict[str, bool] = config.cache.get("cache/lastfailed", {})
        self._previously_failed_count: int | None = None
        self._report_status: str | None = None
        self._skipped_files = 0  # count skipped files during collection due to --lf

        if config.getoption("lf"):
            self._last_failed_paths = self.get_last_failed_paths()
            config.pluginmanager.register(
                LFPluginCollWrapper(self), "lfplugin-collwrapper"
            )

    def get_last_failed_paths(self) -> set[Path]:
        """Return a set with all Paths of the previously failed nodeids and
        their parents."""
        rootpath = self.config.rootpath
        result = set()
        for nodeid in self.lastfailed:
            path = rootpath / nodeid.split("::")[0]
            result.add(path)
            result.update(path.parents)
        return {x for x in result if x.exists()}

    def pytest_report_collectionfinish(self) -> str | None:
        if self.active and self.config.get_verbosity() >= 0:
            return f"run-last-failure: {self._report_status}"
        return None

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        if (report.when == "call" and report.passed) or report.skipped:
            self.lastfailed.pop(report.nodeid, None)
        elif report.failed:
            self.lastfailed[report.nodeid] = True

    def pytest_collectreport(self, report: CollectReport) -> None:
        passed = report.outcome in ("passed", "skipped")
        if passed:
            if report.nodeid in self.lastfailed:
                self.lastfailed.pop(report.nodeid)
                self.lastfailed.update((item.nodeid, True) for item in report.result)
        else:
            self.lastfailed[report.nodeid] = True

    @hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(
        self, config: Config, items: list[nodes.Item]
    ) -> Generator[None]:
        res = yield

        if not self.active:
            return res

        if self.lastfailed:
            previously_failed = []
            previously_passed = []
            for item in items:
                if item.nodeid in self.lastfailed:
                    previously_failed.append(item)
                else:
                    previously_passed.append(item)
            self._previously_failed_count = len(previously_failed)

            if not previously_failed:
                # Running a subset of all tests with recorded failures
                # only outside of it.
                self._report_status = (
                    f"{len(self.lastfailed)} known failures not in selected tests"
                )
            else:
                if self.config.getoption("lf"):
                    items[:] = previously_failed
                    config.hook.pytest_deselected(items=previously_passed)
                else:  # --failedfirst
                    items[:] = previously_failed + previously_passed

                noun = "failure" if self._previously_failed_count == 1 else "failures"
                suffix = " first" if self.config.getoption("failedfirst") else ""
                self._report_status = (
                    f"rerun previous {self._previously_failed_count} {noun}{suffix}"
                )

            if self._skipped_files > 0:
                files_noun = "file" if self._skipped_files == 1 else "files"
                self._report_status += f" (skipped {self._skipped_files} {files_noun})"
        else:
            self._report_status = "no previously failed tests, "
            if self.config.getoption("last_failed_no_failures") == "none":
                self._report_status += "deselecting all items."
                config.hook.pytest_deselected(items=items[:])
                items[:] = []
            else:
                self._report_status += "not deselecting items."

        return res

    def pytest_sessionfinish(self, session: Session) -> None:
        config = self.config
        if config.getoption("cacheshow") or hasattr(config, "workerinput"):
            return

        assert config.cache is not None
        saved_lastfailed = config.cache.get("cache/lastfailed", {})
        if saved_lastfailed != self.lastfailed:
            config.cache.set("cache/lastfailed", self.lastfailed)


class NFPlugin:
    """Plugin which implements the --nf (run new-first) option."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.active = config.option.newfirst
        assert config.cache is not None
        self.cached_nodeids = set(config.cache.get("cache/nodeids", []))

    @hookimpl(wrapper=True, tryfirst=True)
    def pytest_collection_modifyitems(self, items: list[nodes.Item]) -> Generator[None]:
        res = yield

        if self.active:
            new_items: dict[str, nodes.Item] = {}
            other_items: dict[str, nodes.Item] = {}
            for item in items:
                if item.nodeid not in self.cached_nodeids:
                    new_items[item.nodeid] = item
                else:
                    other_items[item.nodeid] = item

            items[:] = self._get_increasing_order(
                new_items.values()
            ) + self._get_increasing_order(other_items.values())
            self.cached_nodeids.update(new_items)
        else:
            self.cached_nodeids.update(item.nodeid for item in items)

        return res

    def _get_increasing_order(self, items: Iterable[nodes.Item]) -> list[nodes.Item]:
        return sorted(items, key=lambda item: item.path.stat().st_mtime, reverse=True)

    def pytest_sessionfinish(self) -> None:
        config = self.config
        if config.getoption("cacheshow") or hasattr(config, "workerinput"):
            return

        if config.getoption("collectonly"):
            return

        assert config.cache is not None
        config.cache.set("cache/nodeids", sorted(self.cached_nodeids))


def pytest_addoption(parser: Parser) -> None:
    """Add command-line options for cache functionality.

    :param parser: Parser object to add command-line options to.
    """
    group = parser.getgroup("general")
    group.addoption(
        "--lf",
        "--last-failed",
        action="store_true",
        dest="lf",
        help="Rerun only the tests that failed at the last run (or all if none failed)",
    )
    group.addoption(
        "--ff",
        "--failed-first",
        action="store_true",
        dest="failedfirst",
        help="Run all tests, but run the last failures first. "
        "This may re-order tests and thus lead to "
        "repeated fixture setup/teardown.",
    )
    group.addoption(
        "--nf",
        "--new-first",
        action="store_true",
        dest="newfirst",
        help="Run tests from new files first, then the rest of the tests "
        "sorted by file mtime",
    )
    group.addoption(
        "--cache-show",
        action="append",
        nargs="?",
        dest="cacheshow",
        help=(
            "Show cache contents, don't perform collection or tests. "
            "Optional argument: glob (default: '*')."
        ),
    )
    group.addoption(
        "--cache-clear",
        action="store_true",
        dest="cacheclear",
        help="Remove all cache contents at start of test run",
    )
    cache_dir_default = ".pytest_cache"
    if "TOX_ENV_DIR" in os.environ:
        cache_dir_default = os.path.join(os.environ["TOX_ENV_DIR"], cache_dir_default)
    parser.addini("cache_dir", default=cache_dir_default, help="Cache directory path")
    group.addoption(
        "--lfnf",
        "--last-failed-no-failures",
        action="store",
        dest="last_failed_no_failures",
        choices=("all", "none"),
        default="all",
        help="With ``--lf``, determines whether to execute tests when there "
        "are no previously (known) failures or when no "
        "cached ``lastfailed`` data was found. "
        "``all`` (the default) runs the full test suite again. "
        "``none`` just emits a message about no known failures and exits successfully.",
    )


def pytest_cmdline_main(config: Config) -> int | ExitCode | None:
    if config.option.cacheshow and not config.option.help:
        from _pytest.main import wrap_session

        return wrap_session(config, cacheshow)
    return None


@hookimpl(tryfirst=True)
def pytest_configure(config: Config) -> None:
    """Configure cache system and register related plugins.

    Creates the Cache instance and registers the last-failed (LFPlugin)
    and new-first (NFPlugin) plugins with the plugin manager.

    :param config: pytest configuration object.
    """
    config.cache = Cache.for_config(config, _ispytest=True)
    config.pluginmanager.register(LFPlugin(config), "lfplugin")
    config.pluginmanager.register(NFPlugin(config), "nfplugin")


@fixture
def cache(request: FixtureRequest) -> Cache:
    """Return a cache object that can persist state between testing sessions.

    cache.get(key, default)
    cache.set(key, value)

    Keys must be ``/`` separated strings, where the first part is usually the
    name of your plugin or application to avoid clashes with other cache users.

    Values can be any object handled by the json stdlib module.
    """
    assert request.config.cache is not None
    return request.config.cache


def pytest_report_header(config: Config) -> str | None:
    """Display cachedir with --cache-show and if non-default."""
    if config.option.verbose > 0 or config.getini("cache_dir") != ".pytest_cache":
        assert config.cache is not None
        cachedir = config.cache._cachedir
        # TODO: evaluate generating upward relative paths
        # starting with .., ../.. if sensible

        try:
            displaypath = cachedir.relative_to(config.rootpath)
        except ValueError:
            displaypath = cachedir
        return f"cachedir: {displaypath}"
    return None


def cacheshow(config: Config, session: Session) -> int:
    """Display cache contents when --cache-show is used.

    Shows cached values and directories matching the specified glob pattern
    (default: '*'). Displays cache location, cached test results, and
    any cached directories created by plugins.

    :param config: pytest configuration object.
    :param session: pytest session object.
    :returns: Exit code (0 for success).
    """
    from pprint import pformat

    assert config.cache is not None

    tw = TerminalWriter()
    tw.line("cachedir: " + str(config.cache._cachedir))
    if not config.cache._cachedir.is_dir():
        tw.line("cache is empty")
        return 0

    glob = config.option.cacheshow[0]
    if glob is None:
        glob = "*"

    dummy = object()
    basedir = config.cache._cachedir
    vdir = basedir / Cache._CACHE_PREFIX_VALUES
    tw.sep("-", f"cache values for {glob!r}")
    for valpath in sorted(x for x in vdir.rglob(glob) if x.is_file()):
        key = str(valpath.relative_to(vdir))
        val = config.cache.get(key, dummy)
        if val is dummy:
            tw.line(f"{key} contains unreadable content, will be ignored")
        else:
            tw.line(f"{key} contains:")
            for line in pformat(val).splitlines():
                tw.line("  " + line)

    ddir = basedir / Cache._CACHE_PREFIX_DIRS
    if ddir.is_dir():
        contents = sorted(ddir.rglob(glob))
        tw.sep("-", f"cache directories for {glob!r}")
        for p in contents:
            # if p.is_dir():
            #    print("%s/" % p.relative_to(basedir))
            if p.is_file():
                key = str(p.relative_to(basedir))
                tw.line(f"{key} is a file of length {p.stat().st_size}")
    return 0
