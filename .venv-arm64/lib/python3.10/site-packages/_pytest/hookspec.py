# mypy: allow-untyped-defs
# ruff: noqa: T100
"""Hook specifications for pytest plugins which are invoked by pytest itself
and by builtin plugins."""

from __future__ import annotations

from collections.abc import Mapping
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from typing import TYPE_CHECKING

from pluggy import HookspecMarker


if TYPE_CHECKING:
    import pdb
    from typing import Literal
    import warnings

    from _pytest._code.code import ExceptionInfo
    from _pytest._code.code import ExceptionRepr
    from _pytest.config import _PluggyPlugin
    from _pytest.config import Config
    from _pytest.config import ExitCode
    from _pytest.config import PytestPluginManager
    from _pytest.config.argparsing import Parser
    from _pytest.fixtures import FixtureDef
    from _pytest.fixtures import SubRequest
    from _pytest.main import Session
    from _pytest.nodes import Collector
    from _pytest.nodes import Item
    from _pytest.outcomes import Exit
    from _pytest.python import Class
    from _pytest.python import Function
    from _pytest.python import Metafunc
    from _pytest.python import Module
    from _pytest.reports import CollectReport
    from _pytest.reports import TestReport
    from _pytest.runner import CallInfo
    from _pytest.terminal import TerminalReporter
    from _pytest.terminal import TestShortLogReport


hookspec = HookspecMarker("pytest")

# -------------------------------------------------------------------------
# Initialization hooks called for every plugin
# -------------------------------------------------------------------------


@hookspec(historic=True)
def pytest_addhooks(pluginmanager: PytestPluginManager) -> None:
    """Called at plugin registration time to allow adding new hooks via a call to
    :func:`pluginmanager.add_hookspecs(module_or_class, prefix) <pytest.PytestPluginManager.add_hookspecs>`.

    :param pluginmanager: The pytest plugin manager.

    .. note::
        This hook is incompatible with hook wrappers.

    Use in conftest plugins
    =======================

    If a conftest plugin implements this hook, it will be called immediately
    when the conftest is registered.
    """


@hookspec(historic=True)
def pytest_plugin_registered(
    plugin: _PluggyPlugin,
    plugin_name: str,
    manager: PytestPluginManager,
) -> None:
    """A new pytest plugin got registered.

    :param plugin: The plugin module or instance.
    :param plugin_name: The name by which the plugin is registered.
    :param manager: The pytest plugin manager.

    .. note::
        This hook is incompatible with hook wrappers.

    Use in conftest plugins
    =======================

    If a conftest plugin implements this hook, it will be called immediately
    when the conftest is registered, once for each plugin registered thus far
    (including itself!), and for all plugins thereafter when they are
    registered.
    """


@hookspec(historic=True)
def pytest_addoption(parser: Parser, pluginmanager: PytestPluginManager) -> None:
    """Register argparse-style options and config-style config values,
    called once at the beginning of a test run.

    :param parser:
        To add command line options, call
        :py:func:`parser.addoption(...) <pytest.Parser.addoption>`.
        To add config-file values call :py:func:`parser.addini(...)
        <pytest.Parser.addini>`.

    :param pluginmanager:
        The pytest plugin manager, which can be used to install :py:func:`~pytest.hookspec`'s
        or :py:func:`~pytest.hookimpl`'s and allow one plugin to call another plugin's hooks
        to change how command line options are added.

    Options can later be accessed through the
    :py:class:`config <pytest.Config>` object, respectively:

    - :py:func:`config.getoption(name) <pytest.Config.getoption>` to
      retrieve the value of a command line option.

    - :py:func:`config.getini(name) <pytest.Config.getini>` to retrieve
      a value read from a configuration file.

    The config object is passed around on many internal objects via the ``.config``
    attribute or can be retrieved as the ``pytestconfig`` fixture.

    .. note::
        This hook is incompatible with hook wrappers.

    Use in conftest plugins
    =======================

    If a conftest plugin implements this hook, it will be called immediately
    when the conftest is registered.

    This hook is only called for :ref:`initial conftests <pluginorder>`.
    """


@hookspec(historic=True)
def pytest_configure(config: Config) -> None:
    """Allow plugins and conftest files to perform initial configuration.

    .. note::
        This hook is incompatible with hook wrappers.

    :param config: The pytest config object.

    Use in conftest plugins
    =======================

    This hook is called for every :ref:`initial conftest <pluginorder>` file
    after command line options have been parsed. After that, the hook is called
    for other conftest files as they are registered.
    """


# -------------------------------------------------------------------------
# Bootstrapping hooks called for plugins registered early enough:
# internal and 3rd party plugins.
# -------------------------------------------------------------------------


@hookspec(firstresult=True)
def pytest_cmdline_parse(
    pluginmanager: PytestPluginManager, args: list[str]
) -> Config | None:
    """Return an initialized :class:`~pytest.Config`, parsing the specified args.

    Stops at first non-None result, see :ref:`firstresult`.

    .. note::
        This hook is only called for plugin classes passed to the
        ``plugins`` arg when using `pytest.main`_ to perform an in-process
        test run.

    :param pluginmanager: The pytest plugin manager.
    :param args: List of arguments passed on the command line.
    :returns: A pytest config object.

    Use in conftest plugins
    =======================

    This hook is not called for conftest files.
    """


def pytest_load_initial_conftests(
    early_config: Config, parser: Parser, args: list[str]
) -> None:
    """Called to implement the loading of :ref:`initial conftest files
    <pluginorder>` ahead of command line option parsing.

    :param early_config: The pytest config object.
    :param args: Arguments passed on the command line.
    :param parser: To add command line options.

    Use in conftest plugins
    =======================

    This hook is not called for conftest files.
    """


@hookspec(firstresult=True)
def pytest_cmdline_main(config: Config) -> ExitCode | int | None:
    """Called for performing the main command line action.

    The default implementation will invoke the configure hooks and
    :hook:`pytest_runtestloop`.

    Stops at first non-None result, see :ref:`firstresult`.

    :param config: The pytest config object.
    :returns: The exit code.

    Use in conftest plugins
    =======================

    This hook is only called for :ref:`initial conftests <pluginorder>`.
    """


# -------------------------------------------------------------------------
# collection hooks
# -------------------------------------------------------------------------


@hookspec(firstresult=True)
def pytest_collection(session: Session) -> object | None:
    """Perform the collection phase for the given session.

    Stops at first non-None result, see :ref:`firstresult`.
    The return value is not used, but only stops further processing.

    The default collection phase is this (see individual hooks for full details):

    1. Starting from ``session`` as the initial collector:

      1. ``pytest_collectstart(collector)``
      2. ``report = pytest_make_collect_report(collector)``
      3. ``pytest_exception_interact(collector, call, report)`` if an interactive exception occurred
      4. For each collected node:

        1. If an item, ``pytest_itemcollected(item)``
        2. If a collector, recurse into it.

      5. ``pytest_collectreport(report)``

    2. ``pytest_collection_modifyitems(session, config, items)``

      1. ``pytest_deselected(items)`` for any deselected items (may be called multiple times)

    3. Set ``session.items`` to the list of collected items
    4. ``pytest_collection_finish(session)``
    5. Set ``session.testscollected`` to the number of collected items

    You can implement this hook to only perform some action before collection,
    for example the terminal plugin uses it to start displaying the collection
    counter (and returns `None`).

    :param session: The pytest session object.

    Use in conftest plugins
    =======================

    This hook is only called for :ref:`initial conftests <pluginorder>`.
    """


def pytest_collection_modifyitems(
    session: Session, config: Config, items: list[Item]
) -> None:
    """Called after collection has been performed. May filter or re-order
    the items in-place.

    When items are deselected (filtered out from ``items``),
    the hook :hook:`pytest_deselected` must be called explicitly
    with the deselected items to properly notify other plugins,
    e.g. with ``config.hook.pytest_deselected(items=deselected_items)``.

    :param session: The pytest session object.
    :param config: The pytest config object.
    :param items: List of item objects.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


def pytest_collection_finish(session: Session) -> None:
    """Called after collection has been performed and modified.

    :param session: The pytest session object.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


@hookspec(firstresult=True)
def pytest_ignore_collect(collection_path: Path, config: Config) -> bool | None:
    """Return ``True`` to ignore this path for collection.

    Return ``None`` to let other plugins ignore the path for collection.

    Returning ``False`` will forcefully *not* ignore this path for collection,
    without giving a chance for other plugins to ignore this path.

    This hook is consulted for all files and directories prior to calling
    more specific hooks.

    Stops at first non-None result, see :ref:`firstresult`.

    :param collection_path: The path to analyze.
    :type collection_path: pathlib.Path
    :param config: The pytest config object.

    .. versionchanged:: 7.0.0
        The ``collection_path`` parameter was added as a :class:`pathlib.Path`
        equivalent of the ``path`` parameter. The ``path`` parameter
        has been deprecated and removed in pytest 9.0.0.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given collection path, only
    conftest files in parent directories of the collection path are consulted
    (if the path is a directory, its own conftest file is *not* consulted - a
    directory cannot ignore itself!).
    """


@hookspec(firstresult=True)
def pytest_collect_directory(path: Path, parent: Collector) -> Collector | None:
    """Create a :class:`~pytest.Collector` for the given directory, or None if
    not relevant.

    .. versionadded:: 8.0

    For best results, the returned collector should be a subclass of
    :class:`~pytest.Directory`, but this is not required.

    The new node needs to have the specified ``parent`` as a parent.

    Stops at first non-None result, see :ref:`firstresult`.

    :param path: The path to analyze.
    :type path: pathlib.Path

    See :ref:`custom directory collectors` for a simple example of use of this
    hook.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given collection path, only
    conftest files in parent directories of the collection path are consulted
    (if the path is a directory, its own conftest file is *not* consulted - a
    directory cannot collect itself!).
    """


def pytest_collect_file(file_path: Path, parent: Collector) -> Collector | None:
    """Create a :class:`~pytest.Collector` for the given path, or None if not relevant.

    For best results, the returned collector should be a subclass of
    :class:`~pytest.File`, but this is not required.

    The new node needs to have the specified ``parent`` as a parent.

    :param file_path: The path to analyze.
    :type file_path: pathlib.Path

    .. versionchanged:: 7.0.0
        The ``file_path`` parameter was added as a :class:`pathlib.Path`
        equivalent of the ``path`` parameter. The ``path`` parameter
        has been deprecated and removed in pytest 9.0.0.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given file path, only
    conftest files in parent directories of the file path are consulted.
    """


# logging hooks for collection


def pytest_collectstart(collector: Collector) -> None:
    """Collector starts collecting.

    :param collector:
        The collector.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given collector, only
    conftest files in the collector's directory and its parent directories are
    consulted.
    """


def pytest_itemcollected(item: Item) -> None:
    """We just collected a test item.

    :param item:
        The item.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_collectreport(report: CollectReport) -> None:
    """Collector finished collecting.

    :param report:
        The collect report.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given collector, only
    conftest files in the collector's directory and its parent directories are
    consulted.
    """


def pytest_deselected(items: Sequence[Item]) -> None:
    """Called for deselected test items, e.g. by keyword.

    Note that this hook has two integration aspects for plugins:

    - it can be *implemented* to be notified of deselected items
    - it must be *called* from :hook:`pytest_collection_modifyitems`
      implementations when items are deselected (to properly notify other plugins).

    May be called multiple times.

    :param items:
        The items.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook.
    """


@hookspec(firstresult=True)
def pytest_make_collect_report(collector: Collector) -> CollectReport | None:
    """Perform :func:`collector.collect() <pytest.Collector.collect>` and return
    a :class:`~pytest.CollectReport`.

    Stops at first non-None result, see :ref:`firstresult`.

    :param collector:
        The collector.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given collector, only
    conftest files in the collector's directory and its parent directories are
    consulted.
    """


# -------------------------------------------------------------------------
# Python test function related hooks
# -------------------------------------------------------------------------


@hookspec(firstresult=True)
def pytest_pycollect_makemodule(module_path: Path, parent) -> Module | None:
    """Return a :class:`pytest.Module` collector or None for the given path.

    This hook will be called for each matching test module path.
    The :hook:`pytest_collect_file` hook needs to be used if you want to
    create test modules for files that do not match as a test module.

    Stops at first non-None result, see :ref:`firstresult`.

    :param module_path: The path of the module to collect.
    :type module_path: pathlib.Path

    .. versionchanged:: 7.0.0
        The ``module_path`` parameter was added as a :class:`pathlib.Path`
        equivalent of the ``path`` parameter. The ``path`` parameter has been
        deprecated in favor of ``module_path`` and removed in pytest 9.0.0.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given parent collector,
    only conftest files in the collector's directory and its parent directories
    are consulted.
    """


@hookspec(firstresult=True)
def pytest_pycollect_makeitem(
    collector: Module | Class, name: str, obj: object
) -> None | Item | Collector | list[Item | Collector]:
    """Return a custom item/collector for a Python object in a module, or None.

    Stops at first non-None result, see :ref:`firstresult`.

    :param collector:
        The module/class collector.
    :param name:
        The name of the object in the module/class.
    :param obj:
        The object.
    :returns:
        The created items/collectors.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given collector, only
    conftest files in the collector's directory and its parent directories
    are consulted.
    """


@hookspec(firstresult=True)
def pytest_pyfunc_call(pyfuncitem: Function) -> object | None:
    """Call underlying test function.

    Stops at first non-None result, see :ref:`firstresult`.

    :param pyfuncitem:
        The function item.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only
    conftest files in the item's directory and its parent directories
    are consulted.
    """


def pytest_generate_tests(metafunc: Metafunc) -> None:
    """Generate (multiple) parametrized calls to a test function.

    :param metafunc:
        The :class:`~pytest.Metafunc` helper for the test function.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given function definition,
    only conftest files in the functions's directory and its parent directories
    are consulted.
    """


@hookspec(firstresult=True)
def pytest_make_parametrize_id(config: Config, val: object, argname: str) -> str | None:
    """Return a user-friendly string representation of the given ``val``
    that will be used by @pytest.mark.parametrize calls, or None if the hook
    doesn't know about ``val``.

    The parameter name is available as ``argname``, if required.

    Stops at first non-None result, see :ref:`firstresult`.

    :param config: The pytest config object.
    :param val: The parametrized value.
    :param argname: The automatic parameter name produced by pytest.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook.
    """


# -------------------------------------------------------------------------
# runtest related hooks
# -------------------------------------------------------------------------


@hookspec(firstresult=True)
def pytest_runtestloop(session: Session) -> object | None:
    """Perform the main runtest loop (after collection finished).

    The default hook implementation performs the runtest protocol for all items
    collected in the session (``session.items``), unless the collection failed
    or the ``collectonly`` pytest option is set.

    If at any point :py:func:`pytest.exit` is called, the loop is
    terminated immediately.

    If at any point ``session.shouldfail`` or ``session.shouldstop`` are set, the
    loop is terminated after the runtest protocol for the current item is finished.

    :param session: The pytest session object.

    Stops at first non-None result, see :ref:`firstresult`.
    The return value is not used, but only stops further processing.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook.
    """


@hookspec(firstresult=True)
def pytest_runtest_protocol(item: Item, nextitem: Item | None) -> object | None:
    """Perform the runtest protocol for a single test item.

    The default runtest protocol is this (see individual hooks for full details):

    - ``pytest_runtest_logstart(nodeid, location)``

    - Setup phase:
        - ``call = pytest_runtest_setup(item)`` (wrapped in ``CallInfo(when="setup")``)
        - ``report = pytest_runtest_makereport(item, call)``
        - ``pytest_runtest_logreport(report)``
        - ``pytest_exception_interact(call, report)`` if an interactive exception occurred

    - Call phase, if the setup passed and the ``setuponly`` pytest option is not set:
        - ``call = pytest_runtest_call(item)`` (wrapped in ``CallInfo(when="call")``)
        - ``report = pytest_runtest_makereport(item, call)``
        - ``pytest_runtest_logreport(report)``
        - ``pytest_exception_interact(call, report)`` if an interactive exception occurred

    - Teardown phase:
        - ``call = pytest_runtest_teardown(item, nextitem)`` (wrapped in ``CallInfo(when="teardown")``)
        - ``report = pytest_runtest_makereport(item, call)``
        - ``pytest_runtest_logreport(report)``
        - ``pytest_exception_interact(call, report)`` if an interactive exception occurred

    - ``pytest_runtest_logfinish(nodeid, location)``

    :param item: Test item for which the runtest protocol is performed.
    :param nextitem: The scheduled-to-be-next test item (or None if this is the end my friend).

    Stops at first non-None result, see :ref:`firstresult`.
    The return value is not used, but only stops further processing.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook.
    """


def pytest_runtest_logstart(nodeid: str, location: tuple[str, int | None, str]) -> None:
    """Called at the start of running the runtest protocol for a single item.

    See :hook:`pytest_runtest_protocol` for a description of the runtest protocol.

    :param nodeid: Full node ID of the item.
    :param location: A tuple of ``(filename, lineno, testname)``
        where ``filename`` is a file path relative to ``config.rootpath``
        and ``lineno`` is 0-based.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_runtest_logfinish(
    nodeid: str, location: tuple[str, int | None, str]
) -> None:
    """Called at the end of running the runtest protocol for a single item.

    See :hook:`pytest_runtest_protocol` for a description of the runtest protocol.

    :param nodeid: Full node ID of the item.
    :param location: A tuple of ``(filename, lineno, testname)``
        where ``filename`` is a file path relative to ``config.rootpath``
        and ``lineno`` is 0-based.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_runtest_setup(item: Item) -> None:
    """Called to perform the setup phase for a test item.

    The default implementation runs ``setup()`` on ``item`` and all of its
    parents (which haven't been setup yet). This includes obtaining the
    values of fixtures required by the item (which haven't been obtained
    yet).

    :param item:
        The item.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_runtest_call(item: Item) -> None:
    """Called to run the test for test item (the call phase).

    The default implementation calls ``item.runtest()``.

    :param item:
        The item.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_runtest_teardown(item: Item, nextitem: Item | None) -> None:
    """Called to perform the teardown phase for a test item.

    The default implementation runs the finalizers and calls ``teardown()``
    on ``item`` and all of its parents (which need to be torn down). This
    includes running the teardown phase of fixtures required by the item (if
    they go out of scope).

    :param item:
        The item.
    :param nextitem:
        The scheduled-to-be-next test item (None if no further test item is
        scheduled). This argument is used to perform exact teardowns, i.e.
        calling just enough finalizers so that nextitem only needs to call
        setup functions.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


@hookspec(firstresult=True)
def pytest_runtest_makereport(item: Item, call: CallInfo[None]) -> TestReport | None:
    """Called to create a :class:`~pytest.TestReport` for each of
    the setup, call and teardown runtest phases of a test item.

    See :hook:`pytest_runtest_protocol` for a description of the runtest protocol.

    :param item: The item.
    :param call: The :class:`~pytest.CallInfo` for the phase.

    Stops at first non-None result, see :ref:`firstresult`.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_runtest_logreport(report: TestReport) -> None:
    """Process the :class:`~pytest.TestReport` produced for each
    of the setup, call and teardown runtest phases of an item.

    See :hook:`pytest_runtest_protocol` for a description of the runtest protocol.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


@hookspec(firstresult=True)
def pytest_report_to_serializable(
    config: Config,
    report: CollectReport | TestReport,
) -> dict[str, Any] | None:
    """Serialize the given report object into a data structure suitable for
    sending over the wire, e.g. converted to JSON.

    :param config: The pytest config object.
    :param report: The report.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. The exact details may depend
    on the plugin which calls the hook.
    """


@hookspec(firstresult=True)
def pytest_report_from_serializable(
    config: Config,
    data: dict[str, Any],
) -> CollectReport | TestReport | None:
    """Restore a report object previously serialized with
    :hook:`pytest_report_to_serializable`.

    :param config: The pytest config object.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. The exact details may depend
    on the plugin which calls the hook.
    """


# -------------------------------------------------------------------------
# Fixture related hooks
# -------------------------------------------------------------------------


@hookspec(firstresult=True)
def pytest_fixture_setup(
    fixturedef: FixtureDef[Any], request: SubRequest
) -> object | None:
    """Perform fixture setup execution.

    :param fixturedef:
        The fixture definition object.
    :param request:
        The fixture request object.
    :returns:
        The return value of the call to the fixture function.

    Stops at first non-None result, see :ref:`firstresult`.

    .. note::
        If the fixture function returns None, other implementations of
        this hook function will continue to be called, according to the
        behavior of the :ref:`firstresult` option.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given fixture, only
    conftest files in the fixture scope's directory and its parent directories
    are consulted.
    """


def pytest_fixture_post_finalizer(
    fixturedef: FixtureDef[Any], request: SubRequest
) -> None:
    """Called after fixture teardown, but before the cache is cleared, so
    the fixture result ``fixturedef.cached_result`` is still available (not
    ``None``).

    :param fixturedef:
        The fixture definition object.
    :param request:
        The fixture request object.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given fixture, only
    conftest files in the fixture scope's directory and its parent directories
    are consulted.
    """


# -------------------------------------------------------------------------
# test session related hooks
# -------------------------------------------------------------------------


def pytest_sessionstart(session: Session) -> None:
    """Called after the ``Session`` object has been created and before performing collection
    and entering the run test loop.

    :param session: The pytest session object.

    Use in conftest plugins
    =======================

    This hook is only called for :ref:`initial conftests <pluginorder>`.
    """


def pytest_sessionfinish(
    session: Session,
    exitstatus: int | ExitCode,
) -> None:
    """Called after whole test run finished, right before returning the exit status to the system.

    :param session: The pytest session object.
    :param exitstatus: The status which pytest will return to the system.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook.
    """


def pytest_unconfigure(config: Config) -> None:
    """Called before test process is exited.

    :param config: The pytest config object.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook.
    """


# -------------------------------------------------------------------------
# hooks for customizing the assert methods
# -------------------------------------------------------------------------


def pytest_assertrepr_compare(
    config: Config, op: str, left: object, right: object
) -> list[str] | None:
    """Return explanation for comparisons in failing assert expressions.

    Return None for no custom explanation, otherwise return a list
    of strings. The strings will be joined by newlines but any newlines
    *in* a string will be escaped. Note that all but the first line will
    be indented slightly, the intention is for the first line to be a summary.

    :param config: The pytest config object.
    :param op: The operator, e.g. `"=="`, `"!="`, `"not in"`.
    :param left: The left operand.
    :param right: The right operand.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


def pytest_assertion_pass(item: Item, lineno: int, orig: str, expl: str) -> None:
    """Called whenever an assertion passes.

    .. versionadded:: 5.0

    Use this hook to do some processing after a passing assertion.
    The original assertion information is available in the `orig` string
    and the pytest introspected assertion information is available in the
    `expl` string.

    This hook must be explicitly enabled by the :confval:`enable_assertion_pass_hook`
    configuration option:

    .. tab:: toml

        .. code-block:: toml

            [pytest]
            enable_assertion_pass_hook = true

    .. tab:: ini

        .. code-block:: ini

            [pytest]
            enable_assertion_pass_hook = true

    You need to **clean the .pyc** files in your project directory and interpreter libraries
    when enabling this option, as assertions will require to be re-written.

    :param item: pytest item object of current test.
    :param lineno: Line number of the assert statement.
    :param orig: String with the original assertion.
    :param expl: String with the assert explanation.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in the item's directory and its parent directories are consulted.
    """


# -------------------------------------------------------------------------
# Hooks for influencing reporting (invoked from _pytest_terminal).
# -------------------------------------------------------------------------


def pytest_report_header(config: Config, start_path: Path) -> str | list[str]:  # type: ignore[empty-body]
    """Return a string or list of strings to be displayed as header info for terminal reporting.

    :param config: The pytest config object.
    :param start_path: The starting dir.
    :type start_path: pathlib.Path

    .. note::

        Lines returned by a plugin are displayed before those of plugins which
        ran before it.
        If you want to have your line(s) displayed first, use
        :ref:`trylast=True <plugin-hookorder>`.

    .. versionchanged:: 7.0.0
        The ``start_path`` parameter was added as a :class:`pathlib.Path`
        equivalent of the ``startdir`` parameter. The ``startdir`` parameter
        has been deprecated and removed in pytest 9.0.0.

    Use in conftest plugins
    =======================

    This hook is only called for :ref:`initial conftests <pluginorder>`.
    """


def pytest_report_collectionfinish(  # type: ignore[empty-body]
    config: Config,
    start_path: Path,
    items: Sequence[Item],
) -> str | list[str]:
    """Return a string or list of strings to be displayed after collection
    has finished successfully.

    These strings will be displayed after the standard "collected X items" message.

    .. versionadded:: 3.2

    :param config: The pytest config object.
    :param start_path: The starting dir.
    :type start_path: pathlib.Path
    :param items: List of pytest items that are going to be executed; this list should not be modified.

    .. note::

        Lines returned by a plugin are displayed before those of plugins which
        ran before it.
        If you want to have your line(s) displayed first, use
        :ref:`trylast=True <plugin-hookorder>`.

    .. versionchanged:: 7.0.0
        The ``start_path`` parameter was added as a :class:`pathlib.Path`
        equivalent of the ``startdir`` parameter. The ``startdir`` parameter
        has been deprecated and removed in pytest 9.0.0.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


@hookspec(firstresult=True)
def pytest_report_teststatus(  # type:ignore[empty-body]
    report: CollectReport | TestReport, config: Config
) -> TestShortLogReport | tuple[str, str, str | tuple[str, Mapping[str, bool]]]:
    """Return result-category, shortletter and verbose word for status
    reporting.

    The result-category is a category in which to count the result, for
    example "passed", "skipped", "error" or the empty string.

    The shortletter is shown as testing progresses, for example ".", "s",
    "E" or the empty string.

    The verbose word is shown as testing progresses in verbose mode, for
    example "PASSED", "SKIPPED", "ERROR" or the empty string.

    pytest may style these implicitly according to the report outcome.
    To provide explicit styling, return a tuple for the verbose word,
    for example ``"rerun", "R", ("RERUN", {"yellow": True})``.

    :param report: The report object whose status is to be returned.
    :param config: The pytest config object.
    :returns: The test status.

    Stops at first non-None result, see :ref:`firstresult`.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


def pytest_terminal_summary(
    terminalreporter: TerminalReporter,
    exitstatus: ExitCode,
    config: Config,
) -> None:
    """Add a section to terminal summary reporting.

    :param terminalreporter: The internal terminal reporter object.
    :param exitstatus: The exit status that will be reported back to the OS.
    :param config: The pytest config object.

    .. versionadded:: 4.2
        The ``config`` parameter.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


@hookspec(historic=True)
def pytest_warning_recorded(
    warning_message: warnings.WarningMessage,
    when: Literal["config", "collect", "runtest"],
    nodeid: str,
    location: tuple[str, int, str] | None,
) -> None:
    """Process a warning captured by the internal pytest warnings plugin.

    :param warning_message:
        The captured warning. This is the same object produced by :class:`warnings.catch_warnings`,
        and contains the same attributes as the parameters of :py:func:`warnings.showwarning`.

    :param when:
        Indicates when the warning was captured. Possible values:

        * ``"config"``: during pytest configuration/initialization stage.
        * ``"collect"``: during test collection.
        * ``"runtest"``: during test execution.

    :param nodeid:
        Full id of the item. Empty string for warnings that are not specific to
        a particular node.

    :param location:
        When available, holds information about the execution context of the captured
        warning (filename, linenumber, function). ``function`` evaluates to <module>
        when the execution context is at the module level.

    .. versionadded:: 6.0

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. If the warning is specific to a
    particular node, only conftest files in parent directories of the node are
    consulted.
    """


# -------------------------------------------------------------------------
# Hooks for influencing skipping
# -------------------------------------------------------------------------


def pytest_markeval_namespace(  # type:ignore[empty-body]
    config: Config,
) -> dict[str, Any]:
    """Called when constructing the globals dictionary used for
    evaluating string conditions in xfail/skipif markers.

    This is useful when the condition for a marker requires
    objects that are expensive or impossible to obtain during
    collection time, which is required by normal boolean
    conditions.

    .. versionadded:: 6.2

    :param config: The pytest config object.
    :returns: A dictionary of additional globals to add.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given item, only conftest
    files in parent directories of the item are consulted.
    """


# -------------------------------------------------------------------------
# error handling and internal debugging hooks
# -------------------------------------------------------------------------


def pytest_internalerror(
    excrepr: ExceptionRepr,
    excinfo: ExceptionInfo[BaseException],
) -> bool | None:
    """Called for internal errors.

    Return True to suppress the fallback handling of printing an
    INTERNALERROR message directly to sys.stderr.

    :param excrepr: The exception repr object.
    :param excinfo: The exception info.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


def pytest_keyboard_interrupt(
    excinfo: ExceptionInfo[KeyboardInterrupt | Exit],
) -> None:
    """Called for keyboard interrupt.

    :param excinfo: The exception info.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


def pytest_exception_interact(
    node: Item | Collector,
    call: CallInfo[Any],
    report: CollectReport | TestReport,
) -> None:
    """Called when an exception was raised which can potentially be
    interactively handled.

    May be called during collection (see :hook:`pytest_make_collect_report`),
    in which case ``report`` is a :class:`~pytest.CollectReport`.

    May be called during runtest of an item (see :hook:`pytest_runtest_protocol`),
    in which case ``report`` is a :class:`~pytest.TestReport`.

    This hook is not called if the exception that was raised is an internal
    exception like ``skip.Exception``.

    :param node:
        The item or collector.
    :param call:
        The call information. Contains the exception.
    :param report:
        The collection or test report.

    Use in conftest plugins
    =======================

    Any conftest file can implement this hook. For a given node, only conftest
    files in parent directories of the node are consulted.
    """


def pytest_enter_pdb(config: Config, pdb: pdb.Pdb) -> None:
    """Called upon pdb.set_trace().

    Can be used by plugins to take special action just before the python
    debugger enters interactive mode.

    :param config: The pytest config object.
    :param pdb: The Pdb instance.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """


def pytest_leave_pdb(config: Config, pdb: pdb.Pdb) -> None:
    """Called when leaving pdb (e.g. with continue after pdb.set_trace()).

    Can be used by plugins to take special action just after the python
    debugger leaves interactive mode.

    :param config: The pytest config object.
    :param pdb: The Pdb instance.

    Use in conftest plugins
    =======================

    Any conftest plugin can implement this hook.
    """
