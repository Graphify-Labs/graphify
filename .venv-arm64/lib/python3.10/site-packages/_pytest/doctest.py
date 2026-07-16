# mypy: allow-untyped-defs
"""Discover and run doctests in modules and test files."""

from __future__ import annotations

import bdb
from collections.abc import Callable
from collections.abc import Generator
from collections.abc import Iterable
from collections.abc import Sequence
from contextlib import contextmanager
import functools
import inspect
import os
from pathlib import Path
import platform
import re
import sys
import traceback
import types
from typing import Any
from typing import TYPE_CHECKING
import warnings

from _pytest import outcomes
from _pytest._code.code import ExceptionInfo
from _pytest._code.code import ReprFileLocation
from _pytest._code.code import TerminalRepr
from _pytest._io import TerminalWriter
from _pytest.compat import safe_getattr
from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.fixtures import fixture
from _pytest.fixtures import TopRequest
from _pytest.nodes import Collector
from _pytest.nodes import Item
from _pytest.outcomes import OutcomeException
from _pytest.outcomes import skip
from _pytest.pathlib import fnmatch_ex
from _pytest.python import Module
from _pytest.python_api import approx
from _pytest.warning_types import PytestWarning


if TYPE_CHECKING:
    import doctest

    from typing_extensions import Self

DOCTEST_REPORT_CHOICE_NONE = "none"
DOCTEST_REPORT_CHOICE_CDIFF = "cdiff"
DOCTEST_REPORT_CHOICE_NDIFF = "ndiff"
DOCTEST_REPORT_CHOICE_UDIFF = "udiff"
DOCTEST_REPORT_CHOICE_ONLY_FIRST_FAILURE = "only_first_failure"

DOCTEST_REPORT_CHOICES = (
    DOCTEST_REPORT_CHOICE_NONE,
    DOCTEST_REPORT_CHOICE_CDIFF,
    DOCTEST_REPORT_CHOICE_NDIFF,
    DOCTEST_REPORT_CHOICE_UDIFF,
    DOCTEST_REPORT_CHOICE_ONLY_FIRST_FAILURE,
)

# Lazy definition of runner class
RUNNER_CLASS = None
# Lazy definition of output checker class
CHECKER_CLASS: type[doctest.OutputChecker] | None = None


def pytest_addoption(parser: Parser) -> None:
    parser.addini(
        "doctest_optionflags",
        "Option flags for doctests",
        type="args",
        default=["ELLIPSIS"],
    )
    parser.addini(
        "doctest_encoding", "Encoding used for doctest files", default="utf-8"
    )
    group = parser.getgroup("collect")
    group.addoption(
        "--doctest-modules",
        action="store_true",
        default=False,
        help="Run doctests in all .py modules",
        dest="doctestmodules",
    )
    group.addoption(
        "--doctest-report",
        type=str.lower,
        default="udiff",
        help="Choose another output format for diffs on doctest failure",
        choices=DOCTEST_REPORT_CHOICES,
        dest="doctestreport",
    )
    group.addoption(
        "--doctest-glob",
        action="append",
        default=[],
        metavar="pat",
        help="Doctests file matching pattern, default: test*.txt",
        dest="doctestglob",
    )
    group.addoption(
        "--doctest-ignore-import-errors",
        action="store_true",
        default=False,
        help="Ignore doctest collection errors",
        dest="doctest_ignore_import_errors",
    )
    group.addoption(
        "--doctest-continue-on-failure",
        action="store_true",
        default=False,
        help="For a given doctest, continue to run after the first failure",
        dest="doctest_continue_on_failure",
    )


def pytest_unconfigure() -> None:
    global RUNNER_CLASS

    RUNNER_CLASS = None


def pytest_collect_file(
    file_path: Path,
    parent: Collector,
) -> DoctestModule | DoctestTextfile | None:
    config = parent.config
    if file_path.suffix == ".py":
        if config.option.doctestmodules and not any(
            (_is_setup_py(file_path), _is_main_py(file_path))
        ):
            return DoctestModule.from_parent(parent, path=file_path)
    elif _is_doctest(config, file_path, parent):
        return DoctestTextfile.from_parent(parent, path=file_path)
    return None


def _is_setup_py(path: Path) -> bool:
    if path.name != "setup.py":
        return False
    contents = path.read_bytes()
    return b"setuptools" in contents or b"distutils" in contents


def _is_doctest(config: Config, path: Path, parent: Collector) -> bool:
    if path.suffix in (".txt", ".rst") and parent.session.isinitpath(path):
        return True
    globs = config.getoption("doctestglob") or ["test*.txt"]
    return any(fnmatch_ex(glob, path) for glob in globs)


def _is_main_py(path: Path) -> bool:
    return path.name == "__main__.py"


class ReprFailDoctest(TerminalRepr):
    def __init__(
        self, reprlocation_lines: Sequence[tuple[ReprFileLocation, Sequence[str]]]
    ) -> None:
        self.reprlocation_lines = reprlocation_lines

    def toterminal(self, tw: TerminalWriter) -> None:
        for reprlocation, lines in self.reprlocation_lines:
            for line in lines:
                tw.line(line)
            reprlocation.toterminal(tw)


class MultipleDoctestFailures(Exception):
    def __init__(self, failures: Sequence[doctest.DocTestFailure]) -> None:
        super().__init__()
        self.failures = failures


def _init_runner_class() -> type[doctest.DocTestRunner]:
    import doctest

    class PytestDoctestRunner(doctest.DebugRunner):
        """Runner to collect failures.

        Note that the out variable in this case is a list instead of a
        stdout-like object.
        """

        def __init__(
            self,
            checker: doctest.OutputChecker | None = None,
            verbose: bool | None = None,
            optionflags: int = 0,
            continue_on_failure: bool = True,
        ) -> None:
            super().__init__(checker=checker, verbose=verbose, optionflags=optionflags)
            self.continue_on_failure = continue_on_failure

        def report_failure(
            self,
            out,
            test: doctest.DocTest,
            example: doctest.Example,
            got: str,
        ) -> None:
            failure = doctest.DocTestFailure(test, example, got)
            if self.continue_on_failure:
                out.append(failure)
            else:
                raise failure

        def report_unexpected_exception(
            self,
            out,
            test: doctest.DocTest,
            example: doctest.Example,
            exc_info: tuple[type[BaseException], BaseException, types.TracebackType],
        ) -> None:
            if isinstance(exc_info[1], OutcomeException):
                raise exc_info[1]
            if isinstance(exc_info[1], bdb.BdbQuit):
                outcomes.exit("Quitting debugger")
            failure = doctest.UnexpectedException(test, example, exc_info)
            if self.continue_on_failure:
                out.append(failure)
            else:
                raise failure

    return PytestDoctestRunner


def _get_runner(
    checker: doctest.OutputChecker | None = None,
    verbose: bool | None = None,
    optionflags: int = 0,
    continue_on_failure: bool = True,
) -> doctest.DocTestRunner:
    # We need this in order to do a lazy import on doctest
    global RUNNER_CLASS
    if RUNNER_CLASS is None:
        RUNNER_CLASS = _init_runner_class()
    # Type ignored because the continue_on_failure argument is only defined on
    # PytestDoctestRunner, which is lazily defined so can't be used as a type.
    return RUNNER_CLASS(  # type: ignore
        checker=checker,
        verbose=verbose,
        optionflags=optionflags,
        continue_on_failure=continue_on_failure,
    )


class DoctestItem(Item):
    def __init__(
        self,
        name: str,
        parent: DoctestTextfile | DoctestModule,
        runner: doctest.DocTestRunner,
        dtest: doctest.DocTest,
    ) -> None:
        super().__init__(name, parent)
        self.runner = runner
        self.dtest = dtest

        # Stuff needed for fixture support.
        self.obj = None
        fm = self.session._fixturemanager
        fixtureinfo = fm.getfixtureinfo(node=self, func=None, cls=None)
        self._fixtureinfo = fixtureinfo
        self.fixturenames = fixtureinfo.names_closure
        self._initrequest()

    @classmethod
    def from_parent(  # type: ignore[override]
        cls,
        parent: DoctestTextfile | DoctestModule,
        *,
        name: str,
        runner: doctest.DocTestRunner,
        dtest: doctest.DocTest,
    ) -> Self:
        # incompatible signature due to imposed limits on subclass
        """The public named constructor."""
        return super().from_parent(name=name, parent=parent, runner=runner, dtest=dtest)

    def _initrequest(self) -> None:
        self.funcargs: dict[str, object] = {}
        self._request = TopRequest(self, _ispytest=True)  # type: ignore[arg-type]

    def setup(self) -> None:
        self._request._fillfixtures()
        globs = dict(getfixture=self._request.getfixturevalue)
        for name, value in self._request.getfixturevalue("doctest_namespace").items():
            globs[name] = value
        self.dtest.globs.update(globs)

    def runtest(self) -> None:
        _check_all_skipped(self.dtest)
        self._disable_output_capturing_for_darwin()
        failures: list[doctest.DocTestFailure] = []
        # Type ignored because we change the type of `out` from what
        # doctest expects.
        self.runner.run(self.dtest, out=failures)  # type: ignore[arg-type]
        if failures:
            raise MultipleDoctestFailures(failures)

    def _disable_output_capturing_for_darwin(self) -> None:
        """Disable output capturing. Otherwise, stdout is lost to doctest (#985)."""
        if platform.system() != "Darwin":
            return
        capman = self.config.pluginmanager.getplugin("capturemanager")
        if capman:
            capman.suspend_global_capture(in_=True)
            out, err = capman.read_global_capture()
            sys.stdout.write(out)
            sys.stderr.write(err)

    # TODO: Type ignored -- breaks Liskov Substitution.
    def repr_failure(  # type: ignore[override]
        self,
        excinfo: ExceptionInfo[BaseException],
    ) -> str | TerminalRepr:
        import doctest

        failures: (
            Sequence[doctest.DocTestFailure | doctest.UnexpectedException] | None
        ) = None
        if isinstance(
            excinfo.value, doctest.DocTestFailure | doctest.UnexpectedException
        ):
            failures = [excinfo.value]
        elif isinstance(excinfo.value, MultipleDoctestFailures):
            failures = excinfo.value.failures

        if failures is None:
            return super().repr_failure(excinfo)

        reprlocation_lines = []
        for failure in failures:
            example = failure.example
            test = failure.test
            filename = test.filename
            if test.lineno is None:
                lineno = None
            else:
                lineno = test.lineno + example.lineno + 1
            message = type(failure).__name__
            # TODO: ReprFileLocation doesn't expect a None lineno.
            reprlocation = ReprFileLocation(filename, lineno, message)  # type: ignore[arg-type]
            checker = _get_checker()
            report_choice = _get_report_choice(self.config.getoption("doctestreport"))
            if lineno is not None:
                assert failure.test.docstring is not None
                lines = failure.test.docstring.splitlines(False)
                # add line numbers to the left of the error message
                assert test.lineno is not None
                lines = [
                    f"{i + test.lineno + 1:03d} {x}" for (i, x) in enumerate(lines)
                ]
                # trim docstring error lines to 10
                lines = lines[max(example.lineno - 9, 0) : example.lineno + 1]
            else:
                lines = [
                    "EXAMPLE LOCATION UNKNOWN, not showing all tests of that example"
                ]
                indent = ">>>"
                for line in example.source.splitlines():
                    lines.append(f"??? {indent} {line}")
                    indent = "..."
            if isinstance(failure, doctest.DocTestFailure):
                lines += checker.output_difference(
                    example, failure.got, report_choice
                ).split("\n")
            else:
                inner_excinfo = ExceptionInfo.from_exc_info(failure.exc_info)
                lines += [f"UNEXPECTED EXCEPTION: {inner_excinfo.value!r}"]
                lines += [
                    x.strip("\n") for x in traceback.format_exception(*failure.exc_info)
                ]
            reprlocation_lines.append((reprlocation, lines))
        return ReprFailDoctest(reprlocation_lines)

    def reportinfo(self) -> tuple[os.PathLike[str] | str, int | None, str]:
        return self.path, self.dtest.lineno, f"[doctest] {self.name}"


def _get_flag_lookup() -> dict[str, int]:
    import doctest

    return dict(
        DONT_ACCEPT_TRUE_FOR_1=doctest.DONT_ACCEPT_TRUE_FOR_1,
        DONT_ACCEPT_BLANKLINE=doctest.DONT_ACCEPT_BLANKLINE,
        NORMALIZE_WHITESPACE=doctest.NORMALIZE_WHITESPACE,
        ELLIPSIS=doctest.ELLIPSIS,
        IGNORE_EXCEPTION_DETAIL=doctest.IGNORE_EXCEPTION_DETAIL,
        COMPARISON_FLAGS=doctest.COMPARISON_FLAGS,
        ALLOW_UNICODE=_get_allow_unicode_flag(),
        ALLOW_BYTES=_get_allow_bytes_flag(),
        NUMBER=_get_number_flag(),
    )


def get_optionflags(config: Config) -> int:
    optionflags_str = config.getini("doctest_optionflags")
    flag_lookup_table = _get_flag_lookup()
    flag_acc = 0
    for flag in optionflags_str:
        flag_acc |= flag_lookup_table[flag]
    return flag_acc


def _get_continue_on_failure(config: Config) -> bool:
    continue_on_failure: bool = config.getvalue("doctest_continue_on_failure")
    if continue_on_failure:
        # We need to turn off this if we use pdb since we should stop at
        # the first failure.
        if config.getvalue("usepdb"):
            continue_on_failure = False
    return continue_on_failure


class DoctestTextfile(Module):
    obj = None

    def collect(self) -> Iterable[DoctestItem]:
        import doctest

        # Inspired by doctest.testfile; ideally we would use it directly,
        # but it doesn't support passing a custom checker.
        encoding = self.config.getini("doctest_encoding")
        text = self.path.read_text(encoding)
        filename = str(self.path)
        name = self.path.name
        globs = {"__name__": "__main__"}

        optionflags = get_optionflags(self.config)

        runner = _get_runner(
            verbose=False,
            optionflags=optionflags,
            checker=_get_checker(),
            continue_on_failure=_get_continue_on_failure(self.config),
        )

        parser = doctest.DocTestParser()
        test = parser.get_doctest(text, globs, name, filename, 0)
        if test.examples:
            yield DoctestItem.from_parent(
                self, name=test.name, runner=runner, dtest=test
            )


def _check_all_skipped(test: doctest.DocTest) -> None:
    """Raise pytest.skip() if all examples in the given DocTest have the SKIP
    option set."""
    import doctest

    all_skipped = all(x.options.get(doctest.SKIP, False) for x in test.examples)
    if all_skipped:
        skip("all tests skipped by +SKIP option")


def _is_mocked(obj: object) -> bool:
    """Return if an object is possibly a mock object by checking the
    existence of a highly improbable attribute."""
    return (
        safe_getattr(obj, "pytest_mock_example_attribute_that_shouldnt_exist", None)
        is not None
    )


@contextmanager
def _patch_unwrap_mock_aware() -> Generator[None]:
    """Context manager which replaces ``inspect.unwrap`` with a version
    that's aware of mock objects and doesn't recurse into them."""
    real_unwrap = inspect.unwrap

    def _mock_aware_unwrap(
        func: Callable[..., Any], *, stop: Callable[[Any], Any] | None = None
    ) -> Any:
        try:
            if stop is None or stop is _is_mocked:
                return real_unwrap(func, stop=_is_mocked)
            _stop = stop
            return real_unwrap(func, stop=lambda obj: _is_mocked(obj) or _stop(func))
        except Exception as e:
            warnings.warn(
                f"Got {e!r} when unwrapping {func!r}.  This is usually caused "
                "by a violation of Python's object protocol; see e.g. "
                "https://github.com/pytest-dev/pytest/issues/5080",
                PytestWarning,
            )
            raise

    inspect.unwrap = _mock_aware_unwrap
    try:
        yield
    finally:
        inspect.unwrap = real_unwrap


class DoctestModule(Module):
    def collect(self) -> Iterable[DoctestItem]:
        import doctest

        class MockAwareDocTestFinder(doctest.DocTestFinder):
            py_ver_info_minor = sys.version_info[:2]
            is_find_lineno_broken = (
                py_ver_info_minor < (3, 11)
                or (py_ver_info_minor == (3, 11) and sys.version_info.micro < 9)
                or (py_ver_info_minor == (3, 12) and sys.version_info.micro < 3)
            )
            if is_find_lineno_broken:

                def _find_lineno(self, obj, source_lines):
                    """On older Pythons, doctest code does not take into account
                    `@property`. https://github.com/python/cpython/issues/61648

                    Moreover, wrapped Doctests need to be unwrapped so the correct
                    line number is returned. #8796
                    """
                    if isinstance(obj, property):
                        obj = getattr(obj, "fget", obj)

                    if hasattr(obj, "__wrapped__"):
                        # Get the main obj in case of it being wrapped
                        obj = inspect.unwrap(obj)

                    # Type ignored because this is a private function.
                    return super()._find_lineno(  # type:ignore[misc]
                        obj,
                        source_lines,
                    )

            if sys.version_info < (3, 13):

                def _from_module(self, module, object):
                    """`cached_property` objects are never considered a part
                    of the 'current module'. As such they are skipped by doctest.
                    Here we override `_from_module` to check the underlying
                    function instead. https://github.com/python/cpython/issues/107995
                    """
                    if isinstance(object, functools.cached_property):
                        object = object.func

                    # Type ignored because this is a private function.
                    return super()._from_module(module, object)  # type: ignore[misc]

        try:
            module = self.obj
        except Collector.CollectError:
            if self.config.getvalue("doctest_ignore_import_errors"):
                skip(f"unable to import module {self.path!r}")
            else:
                raise

        # doctests supports fixtures via `getfixture` and autouse.
        self.session._fixturemanager.parsefactories(self)

        # Uses internal doctest module parsing mechanism.
        finder = MockAwareDocTestFinder()
        optionflags = get_optionflags(self.config)
        runner = _get_runner(
            verbose=False,
            optionflags=optionflags,
            checker=_get_checker(),
            continue_on_failure=_get_continue_on_failure(self.config),
        )

        for test in finder.find(module, module.__name__):
            if test.examples:  # skip empty doctests
                yield DoctestItem.from_parent(
                    self, name=test.name, runner=runner, dtest=test
                )


def _init_checker_class() -> type[doctest.OutputChecker]:
    import doctest

    class LiteralsOutputChecker(doctest.OutputChecker):
        # Based on doctest_nose_plugin.py from the nltk project
        # (https://github.com/nltk/nltk) and on the "numtest" doctest extension
        # by Sebastien Boisgerault (https://github.com/boisgera/numtest).

        _unicode_literal_re = re.compile(r"(\W|^)[uU]([rR]?[\'\"])", re.UNICODE)
        _bytes_literal_re = re.compile(r"(\W|^)[bB]([rR]?[\'\"])", re.UNICODE)
        _number_re = re.compile(
            r"""
            (?P<number>
              (?P<mantissa>
                (?P<integer1> [+-]?\d*)\.(?P<fraction>\d+)
                |
                (?P<integer2> [+-]?\d+)\.
              )
              (?:
                [Ee]
                (?P<exponent1> [+-]?\d+)
              )?
              |
              (?P<integer3> [+-]?\d+)
              (?:
                [Ee]
                (?P<exponent2> [+-]?\d+)
              )
            )
            """,
            re.VERBOSE,
        )

        def check_output(self, want: str, got: str, optionflags: int) -> bool:
            if super().check_output(want, got, optionflags):
                return True

            allow_unicode = optionflags & _get_allow_unicode_flag()
            allow_bytes = optionflags & _get_allow_bytes_flag()
            allow_number = optionflags & _get_number_flag()

            if not allow_unicode and not allow_bytes and not allow_number:
                return False

            def remove_prefixes(regex: re.Pattern[str], txt: str) -> str:
                return re.sub(regex, r"\1\2", txt)

            if allow_unicode:
                want = remove_prefixes(self._unicode_literal_re, want)
                got = remove_prefixes(self._unicode_literal_re, got)

            if allow_bytes:
                want = remove_prefixes(self._bytes_literal_re, want)
                got = remove_prefixes(self._bytes_literal_re, got)

            if allow_number:
                got = self._remove_unwanted_precision(want, got)

            return super().check_output(want, got, optionflags)

        def _remove_unwanted_precision(self, want: str, got: str) -> str:
            wants = list(self._number_re.finditer(want))
            gots = list(self._number_re.finditer(got))
            if len(wants) != len(gots):
                return got
            offset = 0
            for w, g in zip(wants, gots, strict=True):
                fraction: str | None = w.group("fraction")
                exponent: str | None = w.group("exponent1")
                if exponent is None:
                    exponent = w.group("exponent2")
                precision = 0 if fraction is None else len(fraction)
                if exponent is not None:
                    precision -= int(exponent)
                if float(w.group()) == approx(float(g.group()), abs=10**-precision):
                    # They're close enough. Replace the text we actually
                    # got with the text we want, so that it will match when we
                    # check the string literally.
                    got = (
                        got[: g.start() + offset] + w.group() + got[g.end() + offset :]
                    )
                    offset += w.end() - w.start() - (g.end() - g.start())
            return got

    return LiteralsOutputChecker


def _get_checker() -> doctest.OutputChecker:
    """Return a doctest.OutputChecker subclass that supports some
    additional options:

    * ALLOW_UNICODE and ALLOW_BYTES options to ignore u'' and b''
      prefixes (respectively) in string literals. Useful when the same
      doctest should run in Python 2 and Python 3.

    * NUMBER to ignore floating-point differences smaller than the
      precision of the literal number in the doctest.

    An inner class is used to avoid importing "doctest" at the module
    level.
    """
    global CHECKER_CLASS
    if CHECKER_CLASS is None:
        CHECKER_CLASS = _init_checker_class()
    return CHECKER_CLASS()


def _get_allow_unicode_flag() -> int:
    """Register and return the ALLOW_UNICODE flag."""
    import doctest

    return doctest.register_optionflag("ALLOW_UNICODE")


def _get_allow_bytes_flag() -> int:
    """Register and return the ALLOW_BYTES flag."""
    import doctest

    return doctest.register_optionflag("ALLOW_BYTES")


def _get_number_flag() -> int:
    """Register and return the NUMBER flag."""
    import doctest

    return doctest.register_optionflag("NUMBER")


def _get_report_choice(key: str) -> int:
    """Return the actual `doctest` module flag value.

    We want to do it as late as possible to avoid importing `doctest` and all
    its dependencies when parsing options, as it adds overhead and breaks tests.
    """
    import doctest

    return {
        DOCTEST_REPORT_CHOICE_UDIFF: doctest.REPORT_UDIFF,
        DOCTEST_REPORT_CHOICE_CDIFF: doctest.REPORT_CDIFF,
        DOCTEST_REPORT_CHOICE_NDIFF: doctest.REPORT_NDIFF,
        DOCTEST_REPORT_CHOICE_ONLY_FIRST_FAILURE: doctest.REPORT_ONLY_FIRST_FAILURE,
        DOCTEST_REPORT_CHOICE_NONE: 0,
    }[key]


@fixture(scope="session")
def doctest_namespace() -> dict[str, Any]:
    """Fixture that returns a :py:class:`dict` that will be injected into the
    namespace of doctests.

    Usually this fixture is used in conjunction with another ``autouse`` fixture:

    .. code-block:: python

        @pytest.fixture(autouse=True)
        def add_np(doctest_namespace):
            doctest_namespace["np"] = numpy

    For more details: :ref:`doctest_namespace`.
    """
    return dict()
