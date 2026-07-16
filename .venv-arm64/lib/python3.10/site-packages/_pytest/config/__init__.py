# mypy: allow-untyped-defs
"""Command line options, config-file and conftest.py processing."""

from __future__ import annotations

import argparse
import builtins
import collections.abc
from collections.abc import Callable
from collections.abc import Generator
from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import MutableMapping
from collections.abc import Sequence
import contextlib
import copy
import dataclasses
import enum
from functools import lru_cache
import glob
import importlib
import importlib.metadata
import inspect
import os
import pathlib
import re
import shlex
import sys
from textwrap import dedent
import types
from types import FunctionType
from typing import Any
from typing import cast
from typing import Final
from typing import final
from typing import IO
from typing import TextIO
from typing import TYPE_CHECKING
import warnings

from pluggy import HookimplMarker
from pluggy import HookimplOpts
from pluggy import HookspecMarker
from pluggy import HookspecOpts
from pluggy import PluginManager

from .exceptions import PrintHelp as PrintHelp
from .exceptions import UsageError as UsageError
from .findpaths import ConfigDict
from .findpaths import ConfigValue
from .findpaths import determine_setup
from .findpaths import parse_override_ini
from _pytest import __version__
import _pytest._code
from _pytest._code import ExceptionInfo
from _pytest._code import filter_traceback
from _pytest._code.code import TracebackStyle
from _pytest._io import TerminalWriter
from _pytest.compat import assert_never
from _pytest.compat import deprecated
from _pytest.compat import NOTSET
from _pytest.config.argparsing import Argument
from _pytest.config.argparsing import FILE_OR_DIR
from _pytest.config.argparsing import Parser
import _pytest.deprecated
import _pytest.hookspec
from _pytest.outcomes import fail
from _pytest.outcomes import Skipped
from _pytest.pathlib import absolutepath
from _pytest.pathlib import bestrelpath
from _pytest.pathlib import import_path
from _pytest.pathlib import ImportMode
from _pytest.pathlib import resolve_package_path
from _pytest.pathlib import safe_exists
from _pytest.stash import Stash
from _pytest.warning_types import PytestConfigWarning
from _pytest.warning_types import warn_explicit_for


if TYPE_CHECKING:
    from _pytest.assertion.rewrite import AssertionRewritingHook
    from _pytest.cacheprovider import Cache
    from _pytest.terminal import TerminalReporter

_PluggyPlugin = object
"""A type to represent plugin objects.

Plugins can be any namespace, so we can't narrow it down much, but we use an
alias to make the intent clear.

Ideally this type would be provided by pluggy itself.
"""


hookimpl = HookimplMarker("pytest")
hookspec = HookspecMarker("pytest")


@final
class ExitCode(enum.IntEnum):
    """Encodes the valid exit codes by pytest.

    Currently users and plugins may supply other exit codes as well.

    .. versionadded:: 5.0
    """

    #: Tests passed.
    OK = 0
    #: Tests failed.
    TESTS_FAILED = 1
    #: pytest was interrupted.
    INTERRUPTED = 2
    #: An internal error got in the way.
    INTERNAL_ERROR = 3
    #: pytest was misused.
    USAGE_ERROR = 4
    #: pytest couldn't find tests.
    NO_TESTS_COLLECTED = 5
    #: All tests pass, but maximum number of warnings exceeded.
    MAX_WARNINGS_ERROR = 6

    __module__ = "pytest"


class ConftestImportFailure(Exception):
    def __init__(
        self,
        path: pathlib.Path,
        *,
        cause: Exception,
    ) -> None:
        self.path = path
        self.cause = cause

    def __str__(self) -> str:
        return f"{type(self.cause).__name__}: {self.cause} (from {self.path})"


def filter_traceback_for_conftest_import_failure(
    entry: _pytest._code.TracebackEntry,
) -> bool:
    """Filter tracebacks entries which point to pytest internals or importlib.

    Make a special case for importlib because we use it to import test modules and conftest files
    in _pytest.pathlib.import_path.
    """
    return filter_traceback(entry) and "importlib" not in str(entry.path).split(os.sep)


def print_conftest_import_error(e: ConftestImportFailure, file: TextIO) -> None:
    exc_info = ExceptionInfo.from_exception(e.cause)
    tw = TerminalWriter(file)
    tw.line(f"ImportError while loading conftest '{e.path}'.", red=True)
    exc_info.traceback = exc_info.traceback.filter(
        filter_traceback_for_conftest_import_failure
    )
    exc_repr = (
        exc_info.getrepr(style="short", chain=False)
        if exc_info.traceback
        else exc_info.exconly()
    )
    formatted_tb = str(exc_repr)
    for line in formatted_tb.splitlines():
        tw.line(line.rstrip(), red=True)


def print_usage_error(e: UsageError, file: TextIO) -> None:
    tw = TerminalWriter(file)
    for msg in e.args:
        tw.line(f"ERROR: {msg}\n", red=True)


def _get_prog_name(argv: Sequence[str]) -> str:
    """Determine the CLI program name from the argument vector.

    :param argv: The argument vector (typically ``sys.argv``).
    :returns: ``"python -m pytest"`` when invoked via ``python -m``,
              ``"pytest"`` otherwise.
    """
    argv0 = argv[0] if argv else ""
    if os.path.basename(argv0) == "__main__.py":
        return "python -m pytest"
    return "pytest"


def main(
    args: list[str] | os.PathLike[str] | None = None,
    plugins: Sequence[str | _PluggyPlugin] | None = None,
) -> int | ExitCode:
    """Perform an in-process test run.

    :param args:
        List of command line arguments. If `None` or not given, defaults to reading
        arguments directly from the process command line (:data:`sys.argv`).
    :param plugins: List of plugin objects to be auto-registered during initialization.

    :returns: An exit code.
    """
    return _main(args=args, plugins=plugins, prog="pytest.main()")


def _main(
    *,
    args: list[str] | os.PathLike[str] | None = None,
    plugins: Sequence[str | _PluggyPlugin] | None = None,
    prog: str,
) -> int | ExitCode:
    # Handle a single `--version`/`-V` argument early to avoid starting up the entire pytest infrastructure.
    new_args = sys.argv[1:] if args is None else args
    if (
        isinstance(new_args, Sequence)
        and (new_args.count("--version") + new_args.count("-V")) == 1
    ):
        sys.stdout.write(f"pytest {__version__}\n")
        return ExitCode.OK

    old_pytest_version = os.environ.get("PYTEST_VERSION")
    try:
        os.environ["PYTEST_VERSION"] = __version__
        try:
            config = _prepareconfig(new_args, plugins, prog=prog)
        except ConftestImportFailure as e:
            print_conftest_import_error(e, file=sys.stderr)
            return ExitCode.USAGE_ERROR

        try:
            ret: ExitCode | int = config.hook.pytest_cmdline_main(config=config)
            try:
                return ExitCode(ret)
            except ValueError:
                return ret
        finally:
            config._ensure_unconfigure()
    except UsageError as e:
        print_usage_error(e, file=sys.stderr)
        return ExitCode.USAGE_ERROR
    finally:
        if old_pytest_version is None:
            os.environ.pop("PYTEST_VERSION", None)
        else:
            os.environ["PYTEST_VERSION"] = old_pytest_version


def _console_main() -> int:
    """The CLI entry point of pytest (internal).

    This is the real implementation used by entry points and ``__main__.py``.
    """
    # https://docs.python.org/3/library/signal.html#note-on-sigpipe
    try:
        code = _main(prog=_get_prog_name(sys.argv))
        sys.stdout.flush()
        return code
    except BrokenPipeError:
        # Python flushes standard streams on exit; redirect remaining output
        # to devnull to avoid another BrokenPipeError at shutdown
        devnull = os.open(os.devnull, os.O_WRONLY)
        os.dup2(devnull, sys.stdout.fileno())
        return 1  # Python exits with error code 1 on EPIPE


def console_main() -> int:
    """The CLI entry point of pytest.

    .. deprecated:: 9.1
        This function is slated for removal in pytest 10.
        It is not meant for programmable use; use :func:`pytest.main` instead.
    """
    import warnings

    from _pytest.deprecated import CONSOLE_MAIN

    warnings.warn(CONSOLE_MAIN, stacklevel=2)
    return _console_main()


class cmdline:  # compatibility namespace
    main = staticmethod(main)


def filename_arg(path: str, optname: str) -> str:
    """Argparse type validator for filename arguments.

    :path: Path of filename.
    :optname: Name of the option.
    """
    if os.path.isdir(path):
        raise UsageError(f"{optname} must be a filename, given: {path}")
    return path


def directory_arg(path: str, optname: str) -> str:
    """Argparse type validator for directory arguments.

    :path: Path of directory.
    :optname: Name of the option.
    """
    if not os.path.isdir(path):
        raise UsageError(f"{optname} must be a directory, given: {path}")
    return path


# Plugins that cannot be disabled via "-p no:X" currently.
essential_plugins = (
    "mark",
    "main",
    "runner",
    "fixtures",
    "helpconfig",  # Provides -p.
)

default_plugins = (
    *essential_plugins,
    "python",
    "terminal",
    "debugging",
    "unittest",
    "capture",
    "skipping",
    "legacypath",
    "tmpdir",
    "monkeypatch",
    "recwarn",
    "pastebin",
    "assertion",
    "junitxml",
    "doctest",
    "cacheprovider",
    "setuponly",
    "setupplan",
    "stepwise",
    "unraisableexception",
    "threadexception",
    "warnings",
    "logging",
    "reports",
    "faulthandler",
    "subtests",
)

builtin_plugins = {
    *default_plugins,
    "pytester",
    "pytester_assertions",
    "terminalprogress",
}


def get_config(
    args: Iterable[str] | None = None,
    plugins: Sequence[str | _PluggyPlugin] | None = None,
    *,
    prog: str | None = None,
) -> Config:
    # Subsequent calls to main will create a fresh instance.
    pluginmanager = PytestPluginManager()
    invocation_params = Config.InvocationParams(
        args=args or (),
        plugins=plugins,
        dir=pathlib.Path.cwd(),
    )
    config = Config(pluginmanager, invocation_params=invocation_params, prog=prog)

    if invocation_params.args:
        # Handle any "-p no:plugin" args.
        pluginmanager.consider_preparse(invocation_params.args, exclude_only=True)

    for spec in default_plugins:
        pluginmanager.import_plugin(spec)

    return config


def get_plugin_manager() -> PytestPluginManager:
    """Obtain a new instance of the
    :py:class:`pytest.PytestPluginManager`, with default plugins
    already loaded.

    This function can be used by integration with other tools, like hooking
    into pytest to run tests into an IDE.
    """
    return get_config().pluginmanager


def _prepareconfig(
    args: list[str] | os.PathLike[str],
    plugins: Sequence[str | _PluggyPlugin] | None = None,
    *,
    prog: str | None = None,
) -> Config:
    if isinstance(args, os.PathLike):
        args = [os.fspath(args)]
    elif not isinstance(args, list):
        msg = (  # type:ignore[unreachable]
            "`args` parameter expected to be a list of strings, got: {!r} (type: {})"
        )
        raise TypeError(msg.format(args, type(args)))

    initial_config = get_config(args, plugins, prog=prog)
    pluginmanager = initial_config.pluginmanager
    try:
        if plugins:
            for plugin in plugins:
                if isinstance(plugin, str):
                    pluginmanager.consider_pluginarg(plugin)
                else:
                    pluginmanager.register(plugin)
        config: Config = pluginmanager.hook.pytest_cmdline_parse(
            pluginmanager=pluginmanager, args=args
        )
        return config
    except BaseException:
        initial_config._ensure_unconfigure()
        raise


def _get_directory(path: pathlib.Path) -> pathlib.Path:
    """Get the directory of a path - itself if already a directory."""
    if path.is_file():
        return path.parent
    else:
        return path


def _get_legacy_hook_marks(
    method: Any,
    hook_type: str,
    opt_names: tuple[str, ...],
) -> dict[str, bool]:
    if TYPE_CHECKING:
        # abuse typeguard from importlib to avoid massive method type union that's lacking an alias
        assert inspect.isroutine(method)
    known_marks: set[str] = {m.name for m in getattr(method, "pytestmark", [])}
    must_warn: list[str] = []
    opts: dict[str, bool] = {}
    for opt_name in opt_names:
        opt_attr = getattr(method, opt_name, AttributeError)
        if opt_attr is not AttributeError:
            must_warn.append(f"{opt_name}={opt_attr}")
            opts[opt_name] = True
        elif opt_name in known_marks:
            must_warn.append(f"{opt_name}=True")
            opts[opt_name] = True
        else:
            opts[opt_name] = False
    if must_warn:
        hook_opts = ", ".join(must_warn)
        message = _pytest.deprecated.HOOK_LEGACY_MARKING.format(
            type=hook_type,
            fullname=method.__qualname__,
            hook_opts=hook_opts,
        )
        warn_explicit_for(cast(FunctionType, method), message)
    return opts


@final
class PytestPluginManager(PluginManager):
    """A :py:class:`pluggy.PluginManager <pluggy.PluginManager>` with
    additional pytest-specific functionality:

    * Loading plugins from the command line, ``PYTEST_PLUGINS`` env variable and
      ``pytest_plugins`` global variables found in plugins being loaded.
    * ``conftest.py`` loading during start-up.
    """

    def __init__(self) -> None:
        from _pytest.assertion import DummyRewriteHook
        from _pytest.assertion import RewriteHook

        super().__init__("pytest")

        # -- State related to local conftest plugins.
        # All loaded conftest modules.
        self._conftest_plugins: set[types.ModuleType] = set()
        # All conftest modules applicable for a directory.
        # This includes the directory's own conftest modules as well
        # as those of its parent directories.
        self._dirpath2confmods: dict[pathlib.Path, list[types.ModuleType]] = {}
        # Cutoff directory above which conftests are no longer discovered.
        self._confcutdir: pathlib.Path | None = None
        # If set, conftest loading is skipped.
        self._noconftest = False

        # _getconftestmodules()'s call to _get_directory() causes a stat
        # storm when it's called potentially thousands of times in a test
        # session (#9478), often with the same path, so cache it.
        self._get_directory = lru_cache(256)(_get_directory)

        # plugins that were explicitly skipped with pytest.skip
        # list of (module name, skip reason)
        # previously we would issue a warning when a plugin was skipped, but
        # since we refactored warnings as first citizens of Config, they are
        # just stored here to be used later.
        self.skipped_plugins: list[tuple[str, str]] = []

        self.add_hookspecs(_pytest.hookspec)
        self.register(self)
        if os.environ.get("PYTEST_DEBUG"):
            err: IO[str] = sys.stderr
            encoding: str = getattr(err, "encoding", "utf8")
            try:
                err = open(
                    os.dup(err.fileno()),
                    mode=err.mode,
                    buffering=1,
                    encoding=encoding,
                )
            except Exception:
                pass
            self.trace.root.setwriter(err.write)
            self.enable_tracing()

        # Config._consider_importhook will set a real object if required.
        self.rewrite_hook: RewriteHook = DummyRewriteHook()
        # Used to know when we are importing conftests after the pytest_configure stage.
        self._configured = False

    def parse_hookimpl_opts(
        self, plugin: _PluggyPlugin, name: str
    ) -> HookimplOpts | None:
        """:meta private:"""
        # pytest hooks are always prefixed with "pytest_",
        # so we avoid accessing possibly non-readable attributes
        # (see issue #1073).
        if not name.startswith("pytest_"):
            return None
        # Ignore names which cannot be hooks.
        if name == "pytest_plugins":
            return None

        opts = super().parse_hookimpl_opts(plugin, name)
        if opts is not None:
            return opts

        method = getattr(plugin, name)
        # Consider only actual functions for hooks (#3775).
        if not inspect.isroutine(method):
            return None
        # Collect unmarked hooks as long as they have the `pytest_' prefix.
        legacy = _get_legacy_hook_marks(
            method, "impl", ("tryfirst", "trylast", "optionalhook", "hookwrapper")
        )
        return cast(HookimplOpts, legacy)

    def parse_hookspec_opts(self, module_or_class, name: str) -> HookspecOpts | None:
        """:meta private:"""
        opts = super().parse_hookspec_opts(module_or_class, name)
        if opts is None:
            method = getattr(module_or_class, name)
            if name.startswith("pytest_"):
                legacy = _get_legacy_hook_marks(
                    method, "spec", ("firstresult", "historic")
                )
                opts = cast(HookspecOpts, legacy)
        return opts

    def register(self, plugin: _PluggyPlugin, name: str | None = None) -> str | None:
        if name in _pytest.deprecated.DEPRECATED_EXTERNAL_PLUGINS:
            warnings.warn(
                PytestConfigWarning(
                    "{} plugin has been merged into the core, "
                    "please remove it from your requirements.".format(
                        name.replace("_", "-")
                    )
                )
            )
            return None
        plugin_name = super().register(plugin, name)
        if plugin_name is not None:
            self.hook.pytest_plugin_registered.call_historic(
                kwargs=dict(
                    plugin=plugin,
                    plugin_name=plugin_name,
                    manager=self,
                )
            )

            if isinstance(plugin, types.ModuleType):
                self.consider_module(plugin)
        return plugin_name

    def getplugin(self, name: str):
        # Support deprecated naming because plugins (xdist e.g.) use it.
        plugin: _PluggyPlugin | None = self.get_plugin(name)
        return plugin

    def hasplugin(self, name: str) -> bool:
        """Return whether a plugin with the given name is registered."""
        return bool(self.get_plugin(name))

    def pytest_configure(self, config: Config) -> None:
        """:meta private:"""
        # XXX now that the pluginmanager exposes hookimpl(tryfirst...)
        # we should remove tryfirst/trylast as markers.
        config.addinivalue_line(
            "markers",
            "tryfirst: mark a hook implementation function such that the "
            "plugin machinery will try to call it first/as early as possible. "
            "DEPRECATED, use @pytest.hookimpl(tryfirst=True) instead.",
        )
        config.addinivalue_line(
            "markers",
            "trylast: mark a hook implementation function such that the "
            "plugin machinery will try to call it last/as late as possible. "
            "DEPRECATED, use @pytest.hookimpl(trylast=True) instead.",
        )
        self._configured = True

    #
    # Internal API for local conftest plugin handling.
    #
    def _set_initial_conftests(
        self,
        args: Sequence[str | pathlib.Path],
        pyargs: bool,
        noconftest: bool,
        rootpath: pathlib.Path,
        confcutdir: pathlib.Path | None,
        invocation_dir: pathlib.Path,
        importmode: ImportMode | str,
        *,
        consider_namespace_packages: bool,
    ) -> None:
        """Load initial conftest files given a preparsed "namespace".

        As conftest files may add their own command line options which have
        arguments ('--my-opt somepath') we might get some false positives.
        All builtin and 3rd party plugins will have been loaded, however, so
        common options will not confuse our logic here.
        """
        self._confcutdir = (
            absolutepath(invocation_dir / confcutdir) if confcutdir else None
        )
        self._noconftest = noconftest
        self._using_pyargs = pyargs

        anchors = []
        for initial_path in args:
            path = str(initial_path)
            # remove node-id syntax
            i = path.find("::")
            if i != -1:
                path = path[:i]
            anchor = absolutepath(invocation_dir / path)
            # Ensure we do not break if what appears to be an anchor
            # is in fact a very long option (#10169, #11394).
            if not safe_exists(anchor):
                continue

            anchors.append(anchor)
            # Let's also consider test* subdirs.
            if anchor.is_dir():
                anchors.extend(x for x in anchor.glob("test*") if x.is_dir())
        if not anchors:
            anchors.append(invocation_dir)
            anchors.extend(x for x in invocation_dir.glob("test*") if x.is_dir())

        for anchor in anchors:
            self._loadconftestmodules(
                anchor,
                importmode,
                rootpath,
                consider_namespace_packages=consider_namespace_packages,
            )

    def _is_in_confcutdir(self, path: pathlib.Path) -> bool:
        """Whether to consider the given path to load conftests from."""
        if self._confcutdir is None:
            return True
        # The semantics here are literally:
        #   Do not load a conftest if it is found upwards from confcut dir.
        # But this is *not* the same as:
        #   Load only conftests from confcutdir or below.
        # At first glance they might seem the same thing, however we do support use cases where
        # we want to load conftests that are not found in confcutdir or below, but are found
        # in completely different directory hierarchies like packages installed
        # in out-of-source trees.
        # (see #9767 for a regression where the logic was inverted).
        return path not in self._confcutdir.parents

    def _loadconftestmodules(
        self,
        path: pathlib.Path,
        importmode: str | ImportMode,
        rootpath: pathlib.Path,
        *,
        consider_namespace_packages: bool,
    ) -> None:
        if self._noconftest:
            return

        directory = self._get_directory(path)

        # Optimization: avoid repeated searches in the same directory.
        # Assumes always called with same importmode and rootpath.
        if directory in self._dirpath2confmods:
            return

        clist = []
        for parent in reversed((directory, *directory.parents)):
            if self._is_in_confcutdir(parent):
                conftestpath = parent / "conftest.py"
                if conftestpath.is_file():
                    mod = self._importconftest(
                        conftestpath,
                        importmode,
                        rootpath,
                        consider_namespace_packages=consider_namespace_packages,
                    )
                    clist.append(mod)
        self._dirpath2confmods[directory] = clist

    def _getconftestmodules(self, path: pathlib.Path) -> Sequence[types.ModuleType]:
        directory = self._get_directory(path)
        return self._dirpath2confmods.get(directory, ())

    def _rget_with_confmod(
        self,
        name: str,
        path: pathlib.Path,
    ) -> tuple[types.ModuleType, Any]:
        modules = self._getconftestmodules(path)
        for mod in reversed(modules):
            try:
                return mod, getattr(mod, name)
            except AttributeError:
                continue
        raise KeyError(name)

    def _importconftest(
        self,
        conftestpath: pathlib.Path,
        importmode: str | ImportMode,
        rootpath: pathlib.Path,
        *,
        consider_namespace_packages: bool,
    ) -> types.ModuleType:
        conftestpath_plugin_name = str(conftestpath)
        existing = self.get_plugin(conftestpath_plugin_name)
        if existing is not None:
            return cast(types.ModuleType, existing)

        # conftest.py files there are not in a Python package all have module
        # name "conftest", and thus conflict with each other. Clear the existing
        # before loading the new one, otherwise the existing one will be
        # returned from the module cache.
        pkgpath = resolve_package_path(conftestpath)
        if pkgpath is None:
            try:
                del sys.modules[conftestpath.stem]
            except KeyError:
                pass

        try:
            mod = import_path(
                conftestpath,
                mode=importmode,
                root=rootpath,
                consider_namespace_packages=consider_namespace_packages,
            )
        except Exception as e:
            assert e.__traceback__ is not None
            raise ConftestImportFailure(conftestpath, cause=e) from e

        self._check_non_top_pytest_plugins(mod, conftestpath)

        self._conftest_plugins.add(mod)
        dirpath = conftestpath.parent
        if dirpath in self._dirpath2confmods:
            for path, mods in self._dirpath2confmods.items():
                if dirpath in path.parents or path == dirpath:
                    if mod in mods:
                        raise AssertionError(
                            f"While trying to load conftest path {conftestpath!s}, "
                            f"found that the module {mod} is already loaded with path {mod.__file__}. "
                            "This is not supposed to happen. Please report this issue to pytest."
                        )
                    mods.append(mod)
        self.trace(f"loading conftestmodule {mod!r}")
        self.consider_conftest(mod, registration_name=conftestpath_plugin_name)
        return mod

    def _check_non_top_pytest_plugins(
        self,
        mod: types.ModuleType,
        conftestpath: pathlib.Path,
    ) -> None:
        if (
            hasattr(mod, "pytest_plugins")
            and self._configured
            and not self._using_pyargs
        ):
            msg = (
                "Defining 'pytest_plugins' in a non-top-level conftest is no longer supported:\n"
                "It affects the entire test suite instead of just below the conftest as expected.\n"
                "  {}\n"
                "Please move it to a top level conftest file at the rootdir:\n"
                "  {}\n"
                "For more information, visit:\n"
                "  https://docs.pytest.org/en/stable/deprecations.html#pytest-plugins-in-non-top-level-conftest-files"
            )
            fail(msg.format(conftestpath, self._confcutdir), pytrace=False)

    #
    # API for bootstrapping plugin loading
    #
    #

    def consider_preparse(
        self, args: Sequence[str], *, exclude_only: bool = False
    ) -> None:
        """:meta private:"""
        i = 0
        n = len(args)
        while i < n:
            opt = args[i]
            i += 1
            if isinstance(opt, str):
                if opt == "-p":
                    try:
                        parg = args[i]
                    except IndexError:
                        return
                    i += 1
                elif opt.startswith("-p"):
                    parg = opt[2:]
                else:
                    continue
                parg = parg.strip()
                if exclude_only and not parg.startswith("no:"):
                    continue
                self.consider_pluginarg(parg)

    def consider_pluginarg(self, arg: str) -> None:
        """:meta private:"""
        if arg.startswith("no:"):
            name = arg[3:]
            if name in essential_plugins:
                raise UsageError(f"plugin {name} cannot be disabled")

            if name.endswith("conftest.py"):
                raise UsageError(
                    f"Blocking conftest files using -p is not supported: -p no:{name}\n"
                    "conftest.py files are not plugins and cannot be disabled via -p.\n"
                )

            # PR #4304: remove stepwise if cacheprovider is blocked.
            if name == "cacheprovider":
                self.set_blocked("stepwise")
                self.set_blocked("pytest_stepwise")

            self.set_blocked(name)
            if not name.startswith("pytest_"):
                self.set_blocked("pytest_" + name)
        else:
            name = arg
            # Unblock the plugin.
            self.unblock(name)
            if not name.startswith("pytest_"):
                self.unblock("pytest_" + name)
            self.import_plugin(arg, consider_entry_points=True)

    def consider_conftest(
        self, conftestmodule: types.ModuleType, registration_name: str
    ) -> None:
        """:meta private:"""
        self.register(conftestmodule, name=registration_name)

    def consider_env(self) -> None:
        """:meta private:"""
        self._import_plugin_specs(os.environ.get("PYTEST_PLUGINS"))

    def consider_module(self, mod: types.ModuleType) -> None:
        """:meta private:"""
        self._import_plugin_specs(getattr(mod, "pytest_plugins", []))

    def _import_plugin_specs(
        self, spec: None | types.ModuleType | str | Sequence[str]
    ) -> None:
        plugins = _get_plugin_specs_as_list(spec)
        for import_spec in plugins:
            self.import_plugin(import_spec)

    def import_plugin(self, modname: str, consider_entry_points: bool = False) -> None:
        """Import a plugin with ``modname``.

        If ``consider_entry_points`` is True, entry point names are also
        considered to find a plugin.
        """
        # Most often modname refers to builtin modules, e.g. "pytester",
        # "terminal" or "capture".  Those plugins are registered under their
        # basename for historic purposes but must be imported with the
        # _pytest prefix.
        assert isinstance(modname, str), (
            f"module name as text required, got {modname!r}"
        )
        if self.is_blocked(modname) or self.get_plugin(modname) is not None:
            return

        importspec = "_pytest." + modname if modname in builtin_plugins else modname
        self.rewrite_hook.mark_rewrite(importspec)

        if consider_entry_points:
            loaded = self.load_setuptools_entrypoints("pytest11", name=modname)
            if loaded:
                return

        try:
            if sys.version_info >= (3, 11):
                mod = importlib.import_module(importspec)
            else:
                # On Python 3.10, import_module breaks
                # testing/test_config.py::test_disable_plugin_autoload.
                __import__(importspec)
                mod = sys.modules[importspec]
        except ImportError as e:
            raise ImportError(
                f'Error importing plugin "{modname}": {e.args[0]}'
            ).with_traceback(e.__traceback__) from e

        except Skipped as e:
            self.skipped_plugins.append((modname, e.msg or ""))
        else:
            self.register(mod, modname)


def _get_plugin_specs_as_list(
    specs: None | types.ModuleType | str | Sequence[str],
) -> list[str]:
    """Parse a plugins specification into a list of plugin names."""
    # None means empty.
    if specs is None:
        return []
    # Workaround for #3899 - a submodule which happens to be called "pytest_plugins".
    if isinstance(specs, types.ModuleType):
        return []
    # Comma-separated list.
    if isinstance(specs, str):
        return specs.split(",") if specs else []
    # Direct specification.
    if isinstance(specs, collections.abc.Sequence):
        return list(specs)
    raise UsageError(
        f"Plugins may be specified as a sequence or a ','-separated string of plugin names. Got: {specs!r}"
    )


def _iter_rewritable_modules(package_files: Iterable[str]) -> Iterator[str]:
    """Given an iterable of file names in a source distribution, return the "names" that should
    be marked for assertion rewrite.

    For example the package "pytest_mock/__init__.py" should be added as "pytest_mock" in
    the assertion rewrite mechanism.

    This function has to deal with dist-info based distributions and egg based distributions
    (which are still very much in use for "editable" installs).

    Here are the file names as seen in a dist-info based distribution:

        pytest_mock/__init__.py
        pytest_mock/_version.py
        pytest_mock/plugin.py
        pytest_mock.egg-info/PKG-INFO

    Here are the file names as seen in an egg based distribution:

        src/pytest_mock/__init__.py
        src/pytest_mock/_version.py
        src/pytest_mock/plugin.py
        src/pytest_mock.egg-info/PKG-INFO
        LICENSE
        setup.py

    We have to take in account those two distribution flavors in order to determine which
    names should be considered for assertion rewriting.

    More information:
        https://github.com/pytest-dev/pytest-mock/issues/167
    """
    package_files = list(package_files)
    seen_some = False
    for fn in package_files:
        is_simple_module = "/" not in fn and fn.endswith(".py")
        is_package = fn.count("/") == 1 and fn.endswith("__init__.py")
        if is_simple_module:
            module_name, _ = os.path.splitext(fn)
            # we ignore "setup.py" at the root of the distribution
            # as well as editable installation finder modules made by setuptools
            if module_name != "setup" and not module_name.startswith("__editable__"):
                seen_some = True
                yield module_name
        elif is_package:
            package_name = os.path.dirname(fn)
            seen_some = True
            yield package_name

    if not seen_some:
        # At this point we did not find any packages or modules suitable for assertion
        # rewriting, so we try again by stripping the first path component (to account for
        # "src" based source trees for example).
        # This approach lets us have the common case continue to be fast, as egg-distributions
        # are rarer.
        new_package_files = []
        for fn in package_files:
            parts = fn.split("/")
            new_fn = "/".join(parts[1:])
            if new_fn:
                new_package_files.append(new_fn)
        if new_package_files:
            yield from _iter_rewritable_modules(new_package_files)


class _DeprecatedInicfgProxy(MutableMapping[str, Any]):
    """Compatibility proxy for the deprecated Config.inicfg."""

    __slots__ = ("_config",)

    def __init__(self, config: Config) -> None:
        self._config = config

    def __getitem__(self, key: str) -> Any:
        return self._config._inicfg[key].value

    def __setitem__(self, key: str, value: Any) -> None:
        self._config._inicfg[key] = ConfigValue(value, origin="override", mode="toml")

    def __delitem__(self, key: str) -> None:
        del self._config._inicfg[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._config._inicfg)

    def __len__(self) -> int:
        return len(self._config._inicfg)


@final
class Config:
    """Access to configuration values, pluginmanager and plugin hooks.

    :param PytestPluginManager pluginmanager:
        A pytest PluginManager.

    :param InvocationParams invocation_params:
        Object containing parameters regarding the :func:`pytest.main`
        invocation.
    """

    @final
    @dataclasses.dataclass(frozen=True)
    class InvocationParams:
        """Holds parameters passed during :func:`pytest.main`.

        The object attributes are read-only.

        .. versionadded:: 5.1

        .. note::

            Note that the environment variable ``PYTEST_ADDOPTS`` and the ``addopts``
            configuration option are handled by pytest, not being included in the ``args`` attribute.

            Plugins accessing ``InvocationParams`` must be aware of that.
        """

        args: tuple[str, ...]
        """The command-line arguments as passed to :func:`pytest.main`."""
        plugins: Sequence[str | _PluggyPlugin] | None
        """Extra plugins, might be `None`."""
        dir: pathlib.Path
        """The directory from which :func:`pytest.main` was invoked."""

        def __init__(
            self,
            *,
            args: Iterable[str],
            plugins: Sequence[str | _PluggyPlugin] | None,
            dir: pathlib.Path,
        ) -> None:
            object.__setattr__(self, "args", tuple(args))
            object.__setattr__(self, "plugins", plugins)
            object.__setattr__(self, "dir", dir)

    class ArgsSource(enum.Enum):
        """Indicates the source of the test arguments.

        .. versionadded:: 7.2
        """

        #: Command line arguments.
        ARGS = enum.auto()
        #: Invocation directory.
        INVOCATION_DIR = enum.auto()
        INCOVATION_DIR = INVOCATION_DIR  # backwards compatibility alias
        #: 'testpaths' configuration value.
        TESTPATHS = enum.auto()

    # Set by cacheprovider plugin.
    cache: Cache

    def __init__(
        self,
        pluginmanager: PytestPluginManager,
        *,
        invocation_params: InvocationParams | None = None,
        prog: str | None = None,
    ) -> None:
        if invocation_params is None:
            invocation_params = self.InvocationParams(
                args=(), plugins=None, dir=pathlib.Path.cwd()
            )

        self.option = argparse.Namespace()
        """Access to command line option as attributes.

        :type: argparse.Namespace
        """

        self.invocation_params = invocation_params
        """The parameters with which pytest was invoked.

        :type: InvocationParams
        """

        self._parser = Parser(
            usage=f"%(prog)s [options] [{FILE_OR_DIR}] [{FILE_OR_DIR}] [...]",
            processopt=self._processopt,
            prog=prog,
            _ispytest=True,
        )
        self.pluginmanager = pluginmanager
        """The plugin manager handles plugin registration and hook invocation.

        :type: PytestPluginManager
        """

        self.stash = Stash()
        """A place where plugins can store information on the config for their
        own use.

        :type: Stash
        """
        # Deprecated alias. Was never public. Can be removed in a few releases.
        self._store = self.stash

        self.trace = self.pluginmanager.trace.root.get("config")
        self.hook = self.pluginmanager.hook
        self._inicache: dict[str, Any] = {}
        self._inicfg: ConfigDict = {}
        self._cleanup_stack = contextlib.ExitStack()
        self.pluginmanager.register(self, "pytestconfig")
        self._configured = False
        self.hook.pytest_addoption.call_historic(
            kwargs=dict(parser=self._parser, pluginmanager=self.pluginmanager)
        )
        self.args_source = Config.ArgsSource.ARGS
        self.args: list[str] = []

    if TYPE_CHECKING:

        @deprecated(
            "config.inicfg is deprecated, use config.getini() to access configuration values instead.",
        )
        @property
        def inicfg(self) -> _DeprecatedInicfgProxy:
            raise NotImplementedError()
    else:

        @property
        def inicfg(self) -> _DeprecatedInicfgProxy:
            warnings.warn(
                _pytest.deprecated.CONFIG_INICFG,
                stacklevel=2,
            )
            return _DeprecatedInicfgProxy(self)

    @property
    def rootpath(self) -> pathlib.Path:
        """The path to the :ref:`rootdir <rootdir>`.

        .. versionadded:: 6.1
        """
        return self._rootpath

    @property
    def inipath(self) -> pathlib.Path | None:
        """The path to the :ref:`configfile <configfiles>`.

        .. versionadded:: 6.1
        """
        return self._inipath

    def add_cleanup(self, func: Callable[[], None]) -> None:
        """Add a function to be called when the config object gets out of
        use (usually coinciding with pytest_unconfigure).
        """
        self._cleanup_stack.callback(func)

    def _do_configure(self) -> None:
        assert not self._configured
        self._configured = True
        self.hook.pytest_configure.call_historic(kwargs=dict(config=self))

    def _ensure_unconfigure(self) -> None:
        try:
            if self._configured:
                self._configured = False
                try:
                    self.hook.pytest_unconfigure(config=self)
                finally:
                    self.hook.pytest_configure._call_history = []
        finally:
            try:
                self._cleanup_stack.close()
            finally:
                self._cleanup_stack = contextlib.ExitStack()

    def get_terminal_writer(self) -> TerminalWriter:
        terminalreporter: TerminalReporter | None = self.pluginmanager.get_plugin(
            "terminalreporter"
        )
        assert terminalreporter is not None
        return terminalreporter._tw

    def pytest_cmdline_parse(
        self, pluginmanager: PytestPluginManager, args: list[str]
    ) -> Config:
        try:
            self.parse(args)
        except UsageError:
            # Handle `--version --version` and `--help` here in a minimal fashion.
            # This gets done via helpconfig normally, but its
            # pytest_cmdline_main is not called in case of errors.
            if getattr(self.option, "version", False) or "--version" in args:
                from _pytest.helpconfig import show_version_verbose

                # Note that `--version` (single argument) is handled early by `Config.main()`, so the only
                # way we are reaching this point is via `--version --version`.
                show_version_verbose(self)
            elif (
                getattr(self.option, "help", False) or "--help" in args or "-h" in args
            ):
                self._parser.optparser.print_help()
                sys.stdout.write(
                    "\nNOTE: displaying only minimal help due to UsageError.\n\n"
                )

            raise

        return self

    def notify_exception(
        self,
        excinfo: ExceptionInfo[BaseException],
        option: argparse.Namespace | None = None,
    ) -> None:
        if option and getattr(option, "fulltrace", False):
            style: TracebackStyle = "long"
        else:
            style = "native"
        excrepr = excinfo.getrepr(
            funcargs=True, showlocals=getattr(option, "showlocals", False), style=style
        )
        res = self.hook.pytest_internalerror(excrepr=excrepr, excinfo=excinfo)
        if not any(res):
            for line in str(excrepr).split("\n"):
                sys.stderr.write(f"INTERNALERROR> {line}\n")
                sys.stderr.flush()

    def cwd_relative_nodeid(self, nodeid: str) -> str:
        # nodeid's are relative to the rootpath, compute relative to cwd.
        if self.invocation_params.dir != self.rootpath:
            base_path_part, *nodeid_part = nodeid.split("::")
            # Only process path part
            fullpath = self.rootpath / base_path_part
            relative_path = bestrelpath(self.invocation_params.dir, fullpath)

            nodeid = "::".join([relative_path, *nodeid_part])
        return nodeid

    @classmethod
    def fromdictargs(cls, option_dict: Mapping[str, Any], args: list[str]) -> Config:
        """Constructor usable for subprocesses."""
        config = get_config(args)
        config.option.__dict__.update(option_dict)
        config.parse(args, addopts=False)
        for x in config.option.plugins:
            config.pluginmanager.consider_pluginarg(x)
        return config

    def _processopt(self, opt: Argument) -> None:
        if not hasattr(self.option, opt.dest):
            setattr(self.option, opt.dest, opt.default)

    @hookimpl(trylast=True)
    def pytest_load_initial_conftests(self, early_config: Config) -> None:
        # We haven't fully parsed the command line arguments yet, so
        # early_config.args it not set yet. But we need it for
        # discovering the initial conftests. So "pre-run" the logic here.
        # It will be done for real in `parse()`.
        args, _args_source = early_config._decide_args(
            args=early_config.known_args_namespace.file_or_dir,
            pyargs=early_config.known_args_namespace.pyargs,
            testpaths=early_config.getini("testpaths"),
            invocation_dir=early_config.invocation_params.dir,
            rootpath=early_config.rootpath,
            warn=False,
        )
        self.pluginmanager._set_initial_conftests(
            args=args,
            pyargs=early_config.known_args_namespace.pyargs,
            noconftest=early_config.known_args_namespace.noconftest,
            rootpath=early_config.rootpath,
            confcutdir=early_config.known_args_namespace.confcutdir,
            invocation_dir=early_config.invocation_params.dir,
            importmode=early_config.known_args_namespace.importmode,
            consider_namespace_packages=early_config.getini(
                "consider_namespace_packages"
            ),
        )

    def _consider_importhook(self) -> None:
        """Install the PEP 302 import hook if using assertion rewriting.

        Needs to parse the --assert=<mode> option from the commandline
        and find all the installed plugins to mark them for rewriting
        by the importhook.
        """
        mode = getattr(self.known_args_namespace, "assertmode", "plain")

        disable_autoload = getattr(
            self.known_args_namespace, "disable_plugin_autoload", False
        ) or bool(os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD"))
        if mode == "rewrite":
            import _pytest.assertion

            try:
                hook = _pytest.assertion.install_importhook(self)
            except SystemError:
                mode = "plain"
            else:
                self._mark_plugins_for_rewrite(hook, disable_autoload)
        self._warn_about_missing_assertion(mode)

    def _mark_plugins_for_rewrite(
        self, hook: AssertionRewritingHook, disable_autoload: bool
    ) -> None:
        """Given an importhook, mark for rewrite any top-level
        modules or packages in the distribution package for
        all pytest plugins."""
        self.pluginmanager.rewrite_hook = hook

        if disable_autoload:
            # We don't autoload from distribution package entry points,
            # no need to continue.
            return

        package_files = (
            str(file)
            for dist in importlib.metadata.distributions()
            if any(ep.group == "pytest11" for ep in dist.entry_points)
            for file in dist.files or []
        )

        for name in _iter_rewritable_modules(package_files):
            hook.mark_rewrite(name)

    def _configure_python_path(self) -> None:
        # `pythonpath = a b` will set `sys.path` to `[a, b, x, y, z, ...]`
        for path in reversed(self.getini("pythonpath")):
            sys.path.insert(0, str(path))
        self.add_cleanup(self._unconfigure_python_path)

    def _unconfigure_python_path(self) -> None:
        for path in self.getini("pythonpath"):
            path_str = str(path)
            if path_str in sys.path:
                sys.path.remove(path_str)

    def _validate_args(self, args: list[str], via: str) -> list[str]:
        """Validate known args."""
        self._parser.extra_info["config source"] = via
        try:
            self._parser.parse_known_and_unknown_args(
                args, namespace=copy.copy(self.option)
            )
        finally:
            self._parser.extra_info.pop("config source", None)

        return args

    def _decide_args(
        self,
        *,
        args: list[str],
        pyargs: bool,
        testpaths: list[str],
        invocation_dir: pathlib.Path,
        rootpath: pathlib.Path,
        warn: bool,
    ) -> tuple[list[str], ArgsSource]:
        """Decide the args (initial paths/nodeids) to use given the relevant inputs.

        :param warn: Whether can issue warnings.

        :returns: The args and the args source. Guaranteed to be non-empty.
        """
        if args:
            source = Config.ArgsSource.ARGS
            result = args
        else:
            if invocation_dir == rootpath:
                source = Config.ArgsSource.TESTPATHS
                if pyargs:
                    result = testpaths
                else:
                    result = []
                    for path in testpaths:
                        result.extend(sorted(glob.iglob(path, recursive=True)))
                    if testpaths and not result:
                        if warn:
                            warning_text = (
                                "No files were found in testpaths; "
                                "consider removing or adjusting your testpaths configuration. "
                                "Searching recursively from the current directory instead."
                            )
                            self.issue_config_time_warning(
                                PytestConfigWarning(warning_text), stacklevel=3
                            )
            else:
                result = []
            if not result:
                source = Config.ArgsSource.INVOCATION_DIR
                result = [str(invocation_dir)]
        return result, source

    @hookimpl(wrapper=True)
    def pytest_collection(self) -> Generator[None, object, object]:
        # Validate invalid configuration keys after collection is done so we
        # take in account options added by late-loading conftest files.
        try:
            return (yield)
        finally:
            self._validate_config_options()

    def _checkversion(self) -> None:
        import pytest

        minver = self.getini("minversion")
        if minver:
            # Imported lazily to improve start-up time.
            from packaging.version import Version

            if Version(minver) > Version(pytest.__version__):
                raise pytest.UsageError(
                    f"{self.inipath}: 'minversion' requires pytest-{minver}, actual pytest-{pytest.__version__}'"
                )

    def _validate_config_options(self) -> None:
        for key in sorted(self._get_unknown_ini_keys()):
            self._warn_or_fail_if_strict(f"Unknown config option: {key}\n")

    def _validate_plugins(self) -> None:
        required_plugins = sorted(self.getini("required_plugins"))
        if not required_plugins:
            return

        # Imported lazily to improve start-up time.
        from packaging.requirements import InvalidRequirement
        from packaging.requirements import Requirement
        from packaging.version import Version

        plugin_info = self.pluginmanager.list_plugin_distinfo()
        plugin_dist_info = {dist.project_name: dist.version for _, dist in plugin_info}

        missing_plugins = []
        for required_plugin in required_plugins:
            try:
                req = Requirement(required_plugin)
            except InvalidRequirement:
                missing_plugins.append(required_plugin)
                continue

            if req.name not in plugin_dist_info:
                missing_plugins.append(required_plugin)
            elif not req.specifier.contains(
                Version(plugin_dist_info[req.name]), prereleases=True
            ):
                missing_plugins.append(required_plugin)

        if missing_plugins:
            raise UsageError(
                "Missing required plugins: {}".format(", ".join(missing_plugins)),
            )

    def _warn_or_fail_if_strict(self, message: str) -> None:
        strict_config = self.getini("strict_config")
        if strict_config is None:
            strict_config = self.getini("strict")
        if strict_config:
            raise UsageError(message)

        self.issue_config_time_warning(PytestConfigWarning(message), stacklevel=3)

    def _get_unknown_ini_keys(self) -> set[str]:
        known_keys = self._parser._inidict.keys() | self._parser._ini_aliases.keys()
        return self._inicfg.keys() - known_keys

    def parse(self, args: list[str], addopts: bool = True) -> None:
        # Parse given cmdline arguments into this config object.
        assert self.args == [], (
            "can only parse cmdline args at most once per Config object"
        )

        self.hook.pytest_addhooks.call_historic(
            kwargs=dict(pluginmanager=self.pluginmanager)
        )

        if addopts:
            env_addopts = os.environ.get("PYTEST_ADDOPTS", "")
            if len(env_addopts):
                args[:] = (
                    self._validate_args(shlex.split(env_addopts), "via PYTEST_ADDOPTS")
                    + args
                )

        # At this point, self.option contains only defaults from the _processopt
        # callback.
        ns = self._parser.parse_known_args(args, namespace=copy.copy(self.option))
        rootpath, inipath, inicfg, ignored_config_files = determine_setup(
            inifile=ns.inifilename,
            override_ini=ns.override_ini,
            args=ns.file_or_dir,
            rootdir_cmd_arg=ns.rootdir or None,
            invocation_dir=self.invocation_params.dir,
        )
        self._rootpath = rootpath
        self._inipath = inipath
        self._ignored_config_files = ignored_config_files
        self._inicfg = inicfg
        self._parser.extra_info["rootdir"] = str(self.rootpath)
        self._parser.extra_info["inifile"] = str(self.inipath)

        self._parser.addini("addopts", "Extra command line options", "args")
        self._parser.addini("minversion", "Minimally required pytest version")
        self._parser.addini(
            "pythonpath", type="paths", help="Add paths to sys.path", default=[]
        )
        self._parser.addini(
            "required_plugins",
            "Plugins that must be present for pytest to run",
            type="args",
            default=[],
        )

        if addopts:
            args[:] = (
                self._validate_args(self.getini("addopts"), "via addopts config") + args
            )

        self.known_args_namespace = self._parser.parse_known_args(
            args, namespace=copy.copy(self.option)
        )
        if addopts:
            # addopts may have added overrides (especially via OverrideIniAction).
            # The thing can be endlessly circular but we only do one level (#14442).
            if overrides := parse_override_ini(self.known_args_namespace.override_ini):
                self._inicfg.update(overrides)
                self._inicache.clear()
        self._checkversion()
        self._consider_importhook()
        self._configure_python_path()
        self.pluginmanager.consider_preparse(args, exclude_only=False)
        if (
            not os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD")
            and not self.known_args_namespace.disable_plugin_autoload
        ):
            # Autoloading from distribution package entry point has
            # not been disabled.
            self.pluginmanager.load_setuptools_entrypoints("pytest11")
        # Otherwise only plugins explicitly specified in PYTEST_PLUGINS
        # are going to be loaded.
        self.pluginmanager.consider_env()

        # Parse again, now including options added in pytest_addoption
        # by third-party plugins loaded above. This way they're available
        # on early_config in the pytest_load_initial_conftests hook call below.
        self.known_args_namespace = self._parser.parse_known_args(
            args, namespace=copy.copy(self.option)
        )

        self._validate_plugins()
        self._warn_about_skipped_plugins()

        if self.known_args_namespace.confcutdir is None:
            if self.inipath is not None:
                confcutdir = str(self.inipath.parent)
            else:
                confcutdir = str(self.rootpath)
            self.known_args_namespace.confcutdir = confcutdir
        try:
            self.hook.pytest_load_initial_conftests(
                early_config=self, args=args, parser=self._parser
            )
        except ConftestImportFailure as e:
            if self.known_args_namespace.help or self.known_args_namespace.version:
                # we don't want to prevent --help/--version to work
                # so just let it pass and print a warning at the end
                self.issue_config_time_warning(
                    PytestConfigWarning(f"could not load initial conftests: {e.path}"),
                    stacklevel=2,
                )
            else:
                raise

        try:
            self._parser.parse(args, namespace=self.option)
        except PrintHelp:
            return

        self.args, self.args_source = self._decide_args(
            args=getattr(self.option, FILE_OR_DIR),
            pyargs=self.option.pyargs,
            testpaths=self.getini("testpaths"),
            invocation_dir=self.invocation_params.dir,
            rootpath=self.rootpath,
            warn=True,
        )

    def issue_config_time_warning(self, warning: Warning, stacklevel: int) -> None:
        """Issue and handle a warning during the "configure" stage.

        During ``pytest_configure`` we can't capture warnings using the ``catch_warnings_for_item``
        function because it is not possible to have hook wrappers around ``pytest_configure``.

        This function is mainly intended for plugins that need to issue warnings during
        ``pytest_configure`` (or similar stages).

        :param warning: The warning instance.
        :param stacklevel: stacklevel forwarded to warnings.warn.
        """
        if self.pluginmanager.is_blocked("warnings"):
            return

        cmdline_filters = self.known_args_namespace.pythonwarnings or []
        config_filters = self.getini("filterwarnings")

        with warnings.catch_warnings(record=True) as records:
            warnings.simplefilter("always", type(warning))
            apply_warning_filters(config_filters, cmdline_filters)
            warnings.warn(warning, stacklevel=stacklevel)

        if records:
            frame = sys._getframe(stacklevel - 1)
            location = frame.f_code.co_filename, frame.f_lineno, frame.f_code.co_name
            self.hook.pytest_warning_recorded.call_historic(
                kwargs=dict(
                    warning_message=records[0],
                    when="config",
                    nodeid="",
                    location=location,
                )
            )

    def addinivalue_line(self, name: str, line: str) -> None:
        """Add a line to a configuration option. The option must have been
        declared but might not yet be set in which case the line becomes
        the first line in its value."""
        x = self.getini(name)
        assert isinstance(x, list)
        x.append(line)  # modifies the cached list inline

    def getini(self, name: str) -> Any:
        """Return configuration value the an :ref:`configuration file <configfiles>`.

        If a configuration value is not defined in a
        :ref:`configuration file <configfiles>`, then the ``default`` value
        provided while registering the configuration through
        :func:`parser.addini <pytest.Parser.addini>` will be returned.
        Please note that you can even provide ``None`` as a valid
        default value.

        If ``default`` is not provided while registering using
        :func:`parser.addini <pytest.Parser.addini>`, then a default value
        based on the ``type`` parameter passed to
        :func:`parser.addini <pytest.Parser.addini>` will be returned.
        The default values based on ``type`` are:
        ``paths``, ``pathlist``, ``args`` and ``linelist`` : empty list ``[]``
        ``bool`` : ``False``
        ``string`` : empty string ``""``
        ``int`` : ``0``
        ``float`` : ``0.0``

        If neither the ``default`` nor the ``type`` parameter is passed
        while registering the configuration through
        :func:`parser.addini <pytest.Parser.addini>`, then the configuration
        is treated as a string and a default empty string '' is returned.

        If the specified name hasn't been registered through a prior
        :func:`parser.addini <pytest.Parser.addini>` call (usually from a
        plugin), a ValueError is raised.
        """
        canonical_name = self._parser._ini_aliases.get(name, name)
        try:
            return self._inicache[canonical_name]
        except KeyError:
            pass
        self._inicache[canonical_name] = val = self._getini(canonical_name)
        return val

    # Meant for easy monkeypatching by legacypath plugin.
    # Can be inlined back (with no cover removed) once legacypath is gone.
    def _getini_unknown_type(self, name: str, type: str, value: object):
        msg = (
            f"Option {name} has unknown configuration type {type} with value {value!r}"
        )
        raise ValueError(msg)  # pragma: no cover

    def _getini(self, name: str):
        # If this is an alias, resolve to canonical name.
        canonical_name = self._parser._ini_aliases.get(name, name)

        try:
            _description, type, default = self._parser._inidict[canonical_name]
        except KeyError as e:
            raise ValueError(f"unknown configuration value: {name!r}") from e

        # Collect all possible values (canonical name + aliases) from _inicfg.
        # Each candidate is (ConfigValue, is_canonical).
        candidates = []
        if canonical_name in self._inicfg:
            candidates.append((self._inicfg[canonical_name], True))
        for alias, target in self._parser._ini_aliases.items():
            if target == canonical_name and alias in self._inicfg:
                candidates.append((self._inicfg[alias], False))

        if not candidates:
            return default

        # Pick the best candidate based on precedence:
        # 1. CLI override takes precedence over file, then
        # 2. Canonical name takes precedence over alias.
        selected = max(candidates, key=lambda x: (x[0].origin == "override", x[1]))[0]
        value = selected.value
        mode = selected.mode

        if mode == "ini":
            # In ini mode, values are always str | list[str].
            assert isinstance(value, (str, list))
            return self._getini_ini(name, canonical_name, type, value, default)
        elif mode == "toml":
            return self._getini_toml(name, canonical_name, type, value, default)
        else:
            assert_never(mode)

    def _getini_ini(
        self,
        name: str,
        canonical_name: str,
        type: str,
        value: str | list[str],
        default: Any,
    ):
        """Handle config values read in INI mode.

        In INI mode, values are stored as str or list[str] only, and coerced
        from string based on the registered type.
        """
        # Note: some coercions are only required if we are reading from .ini
        # files, because the file format doesn't contain type information, but
        # when reading from toml (in ini mode) we will get either str or list of
        # str values (see load_config_dict_from_file). For example:
        #
        #   ini:
        #     a_line_list = "tests acceptance"
        #
        # in this case, we need to split the string to obtain a list of strings.
        #
        #   toml (ini mode):
        #     a_line_list = ["tests", "acceptance"]
        #
        # in this case, we already have a list ready to use.
        if type == "paths":
            dp = (
                self.inipath.parent
                if self.inipath is not None
                else self.invocation_params.dir
            )
            input_values = shlex.split(value) if isinstance(value, str) else value
            return [dp / x for x in input_values]
        elif type == "args":
            return shlex.split(value) if isinstance(value, str) else value
        elif type == "linelist":
            if isinstance(value, str):
                return [t for t in map(lambda x: x.strip(), value.split("\n")) if t]
            else:
                return value
        elif type == "bool":
            return _strtobool(str(value).strip())
        elif type == "string":
            return value
        elif type == "int":
            if not isinstance(value, str):
                raise TypeError(
                    f"Expected an int string for option {name} of type integer, but got: {value!r}"
                ) from None
            return int(value)
        elif type == "float":
            if not isinstance(value, str):
                raise TypeError(
                    f"Expected a float string for option {name} of type float, but got: {value!r}"
                ) from None
            return float(value)
        else:
            return self._getini_unknown_type(name, type, value)

    def _getini_toml(
        self,
        name: str,
        canonical_name: str,
        type: str,
        value: object,
        default: Any,
    ):
        """Handle TOML config values with strict type validation and no coercion.

        In TOML mode, values already have native types from TOML parsing.
        We validate types match expectations exactly, including list items.
        """
        value_type = builtins.type(value).__name__
        if type == "paths":
            # Expect a list of strings.
            if not isinstance(value, list):
                raise TypeError(
                    f"{self.inipath}: config option '{name}' expects a list for type 'paths', "
                    f"got {value_type}: {value!r}"
                )
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    item_type = builtins.type(item).__name__
                    raise TypeError(
                        f"{self.inipath}: config option '{name}' expects a list of strings, "
                        f"but item at index {i} is {item_type}: {item!r}"
                    )
            dp = (
                self.inipath.parent
                if self.inipath is not None
                else self.invocation_params.dir
            )
            return [dp / x for x in value]
        elif type in {"args", "linelist"}:
            # Expect a list of strings.
            if not isinstance(value, list):
                raise TypeError(
                    f"{self.inipath}: config option '{name}' expects a list for type '{type}', "
                    f"got {value_type}: {value!r}"
                )
            for i, item in enumerate(value):
                if not isinstance(item, str):
                    item_type = builtins.type(item).__name__
                    raise TypeError(
                        f"{self.inipath}: config option '{name}' expects a list of strings, "
                        f"but item at index {i} is {item_type}: {item!r}"
                    )
            return list(value)
        elif type == "bool":
            # Expect a boolean.
            if not isinstance(value, bool):
                raise TypeError(
                    f"{self.inipath}: config option '{name}' expects a bool, "
                    f"got {value_type}: {value!r}"
                )
            return value
        elif type == "int":
            # Expect an integer (but not bool, which is a subclass of int).
            if not isinstance(value, int) or isinstance(value, bool):
                raise TypeError(
                    f"{self.inipath}: config option '{name}' expects an int, "
                    f"got {value_type}: {value!r}"
                )
            return value
        elif type == "float":
            # Expect a float or integer only.
            if not isinstance(value, (float, int)) or isinstance(value, bool):
                raise TypeError(
                    f"{self.inipath}: config option '{name}' expects a float, "
                    f"got {value_type}: {value!r}"
                )
            return value
        elif type == "string":
            # Expect a string.
            if not isinstance(value, str):
                raise TypeError(
                    f"{self.inipath}: config option '{name}' expects a string, "
                    f"got {value_type}: {value!r}"
                )
            return value
        else:
            return self._getini_unknown_type(name, type, value)

    def _getconftest_pathlist(
        self, name: str, path: pathlib.Path
    ) -> list[pathlib.Path] | None:
        try:
            mod, relroots = self.pluginmanager._rget_with_confmod(name, path)
        except KeyError:
            return None
        assert mod.__file__ is not None
        modpath = pathlib.Path(mod.__file__).parent
        values: list[pathlib.Path] = []
        for relroot in relroots:
            if isinstance(relroot, os.PathLike):
                relroot = pathlib.Path(relroot)
            else:
                relroot = relroot.replace("/", os.sep)
                relroot = absolutepath(modpath / relroot)
            values.append(relroot)
        return values

    def getoption(self, name: str, default: Any = NOTSET, skip: bool = False):
        """Return command line option value.

        :param name: Name of the option. You may also specify
            the literal ``--OPT`` option instead of the "dest" option name.
        :param default: Fallback value if no option of that name is **declared** via :hook:`pytest_addoption`.
            Note this parameter will be ignored when the option is **declared** even if the option's value is ``None``.
        :param skip: If ``True``, raise :func:`pytest.skip` if option is undeclared or has a ``None`` value.
            Note that even if ``True``, if a default was specified it will be returned instead of a skip.
        """
        name = self._parser._opt2dest.get(name, name)
        try:
            val = getattr(self.option, name)
            if val is None and skip:
                raise AttributeError(name)
            return val
        except AttributeError as e:
            if default is not NOTSET:
                return default
            if skip:
                import pytest

                pytest.skip(f"no {name!r} option found")
            raise ValueError(f"no option named {name!r}") from e

    def getvalue(self, name: str, path=None):
        """Deprecated, use getoption() instead."""
        return self.getoption(name)

    def getvalueorskip(self, name: str, path=None):
        """Deprecated, use getoption(skip=True) instead."""
        return self.getoption(name, skip=True)

    #: Verbosity type for failed assertions (see :confval:`verbosity_assertions`).
    VERBOSITY_ASSERTIONS: Final = "assertions"
    #: Verbosity type for test case execution (see :confval:`verbosity_test_cases`).
    VERBOSITY_TEST_CASES: Final = "test_cases"
    #: Verbosity type for failed subtests (see :confval:`verbosity_subtests`).
    VERBOSITY_SUBTESTS: Final = "subtests"

    _VERBOSITY_INI_DEFAULT: Final = "auto"

    def get_verbosity(self, verbosity_type: str | None = None) -> int:
        r"""Retrieve the verbosity level for a fine-grained verbosity type.

        :param verbosity_type: Verbosity type to get level for. If a level is
            configured for the given type, that value will be returned. If the
            given type is not a known verbosity type, the global verbosity
            level will be returned. If the given type is None (default), the
            global verbosity level will be returned.

        To configure a level for a fine-grained verbosity type, the
        configuration file should have a setting for the configuration name
        and a numeric value for the verbosity level. A special value of "auto"
        can be used to explicitly use the global verbosity level.

        Example:

        .. tab:: toml

            .. code-block:: toml

                [tool.pytest]
                verbosity_assertions = 2

        .. tab:: ini

            .. code-block:: ini

                [pytest]
                verbosity_assertions = 2

        .. code-block:: console

            pytest -v

        .. code-block:: python

            print(config.get_verbosity())  # 1
            print(config.get_verbosity(Config.VERBOSITY_ASSERTIONS))  # 2
        """
        global_level = self.getoption("verbose", default=0)
        assert isinstance(global_level, int)
        if verbosity_type is None:
            return global_level

        ini_name = Config._verbosity_ini_name(verbosity_type)
        if ini_name not in self._parser._inidict:
            return global_level

        level = self.getini(ini_name)
        if level == Config._VERBOSITY_INI_DEFAULT:
            return global_level

        return int(level)

    @staticmethod
    def _verbosity_ini_name(verbosity_type: str) -> str:
        return f"verbosity_{verbosity_type}"

    @staticmethod
    def _add_verbosity_ini(parser: Parser, verbosity_type: str, help: str) -> None:
        """Add a output verbosity configuration option for the given output type.

        :param parser: Parser for command line arguments and config-file values.
        :param verbosity_type: Fine-grained verbosity category.
        :param help: Description of the output this type controls.

        The value should be retrieved via a call to
        :py:func:`config.get_verbosity(type) <pytest.Config.get_verbosity>`.
        """
        parser.addini(
            Config._verbosity_ini_name(verbosity_type),
            help=help,
            type="string",
            default=Config._VERBOSITY_INI_DEFAULT,
        )

    def _warn_about_missing_assertion(self, mode: str) -> None:
        if not _assertion_supported():
            if mode == "plain":
                warning_text = (
                    "ASSERTIONS ARE NOT EXECUTED"
                    " and FAILING TESTS WILL PASS.  Are you"
                    " using python -O?"
                )
            else:
                warning_text = (
                    "assertions not in test modules or"
                    " plugins will be ignored"
                    " because assert statements are not executed "
                    "by the underlying Python interpreter "
                    "(are you using python -O?)\n"
                )
            self.issue_config_time_warning(
                PytestConfigWarning(warning_text),
                stacklevel=3,
            )

    def _warn_about_skipped_plugins(self) -> None:
        for module_name, msg in self.pluginmanager.skipped_plugins:
            self.issue_config_time_warning(
                PytestConfigWarning(f"skipped plugin {module_name!r}: {msg}"),
                stacklevel=2,
            )


def _assertion_supported() -> bool:
    try:
        assert False
    except AssertionError:
        return True
    else:
        return False  # type: ignore[unreachable]


def create_terminal_writer(
    config: Config, file: TextIO | None = None
) -> TerminalWriter:
    """Create a TerminalWriter instance configured according to the options
    in the config object.

    Every code which requires a TerminalWriter object and has access to a
    config object should use this function.
    """
    tw = TerminalWriter(file=file)

    if config.option.color == "yes":
        tw.hasmarkup = True
    elif config.option.color == "no":
        tw.hasmarkup = False

    if config.option.code_highlight == "yes":
        tw.code_highlight = True
    elif config.option.code_highlight == "no":
        tw.code_highlight = False

    return tw


def _strtobool(val: str) -> bool:
    """Convert a string representation of truth to True or False.

    True values are 'y', 'yes', 't', 'true', 'on', and '1'; false values
    are 'n', 'no', 'f', 'false', 'off', and '0'.  Raises ValueError if
    'val' is anything else.

    .. note:: Copied from distutils.util.
    """
    val = val.lower()
    if val in ("y", "yes", "t", "true", "on", "1"):
        return True
    elif val in ("n", "no", "f", "false", "off", "0"):
        return False
    else:
        raise ValueError(f"invalid truth value {val!r}")


@lru_cache(maxsize=50)
def parse_warning_filter(
    arg: str, *, escape: bool
) -> tuple[warnings._ActionKind, str, type[Warning], str, int]:
    """Parse a warnings filter string.

    This is copied from warnings._setoption with the following changes:

    * Does not apply the filter.
    * Escaping is optional.
    * Raises UsageError so we get nice error messages on failure.
    """
    __tracebackhide__ = True
    error_template = dedent(
        f"""\
        while parsing the following warning configuration:

          {arg}

        This error occurred:

        {{error}}
        """
    )

    parts = arg.split(":")
    if len(parts) > 5:
        doc_url = (
            "https://docs.python.org/3/library/warnings.html#describing-warning-filters"
        )
        error = dedent(
            f"""\
            Too many fields ({len(parts)}), expected at most 5 separated by colons:

              action:message:category:module:line

            For more information please consult: {doc_url}
            """
        )
        raise UsageError(error_template.format(error=error))

    while len(parts) < 5:
        parts.append("")
    action_, message, category_, module, lineno_ = (s.strip() for s in parts)
    try:
        action: warnings._ActionKind = warnings._getaction(action_)  # type: ignore[attr-defined]
    except warnings._OptionError as e:
        raise UsageError(error_template.format(error=str(e))) from None
    try:
        category: type[Warning] = _resolve_warning_category(category_)
    except ImportError:
        raise
    except Exception:
        exc_info = ExceptionInfo.from_current()
        exception_text = exc_info.getrepr(style="native")
        raise UsageError(error_template.format(error=exception_text)) from None
    if message and escape:
        message = re.escape(message)
    if module and escape:
        module = re.escape(module) + r"\Z"
    if lineno_:
        try:
            lineno = int(lineno_)
            if lineno < 0:
                raise ValueError("number is negative")
        except ValueError as e:
            raise UsageError(
                error_template.format(error=f"invalid lineno {lineno_!r}: {e}")
            ) from None
    else:
        lineno = 0
    try:
        re.compile(message)
        re.compile(module)
    except re.error as e:
        raise UsageError(
            error_template.format(error=f"Invalid regex {e.pattern!r}: {e}")
        ) from None
    return action, message, category, module, lineno


def _resolve_warning_category(category: str) -> type[Warning]:
    """
    Copied from warnings._getcategory, but changed so it lets exceptions (specially ImportErrors)
    propagate so we can get access to their tracebacks (#9218).
    """
    __tracebackhide__ = True
    if not category:
        return Warning

    if "." not in category:
        import builtins as m

        klass = category
    else:
        module, _, klass = category.rpartition(".")
        m = importlib.import_module(module)
    cat = getattr(m, klass)
    if not issubclass(cat, Warning):
        raise UsageError(f"{cat} is not a Warning subclass")
    return cast(type[Warning], cat)


def apply_warning_filters(
    config_filters: Iterable[str], cmdline_filters: Iterable[str]
) -> None:
    """Applies pytest-configured filters to the warnings module"""
    # Filters should have this precedence: cmdline options, config.
    # Filters should be applied in the inverse order of precedence.
    for arg in config_filters:
        try:
            warnings.filterwarnings(*parse_warning_filter(arg, escape=False))
        except ImportError as e:
            warnings.warn(
                f"Failed to import filter module '{e.name}': {arg}", PytestConfigWarning
            )
            continue

    for arg in cmdline_filters:
        try:
            warnings.filterwarnings(*parse_warning_filter(arg, escape=True))
        except ImportError as e:
            warnings.warn(
                f"Failed to import filter module '{e.name}': {arg}", PytestConfigWarning
            )
            continue
