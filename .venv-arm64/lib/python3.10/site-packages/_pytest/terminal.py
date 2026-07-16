# mypy: allow-untyped-defs
"""Terminal reporting of the full testing process.

This is a good source for looking at the various reporting hooks.
"""

from __future__ import annotations

import argparse
from collections import Counter
from collections.abc import Callable
from collections.abc import Generator
from collections.abc import Mapping
from collections.abc import Sequence
import dataclasses
import datetime
from functools import partial
import inspect
from pathlib import Path
import platform
import sys
import textwrap
from typing import Any
from typing import ClassVar
from typing import final
from typing import Literal
from typing import NamedTuple
from typing import TextIO
from typing import TYPE_CHECKING
import warnings

import pluggy

from _pytest import compat
from _pytest import nodes
from _pytest import timing
from _pytest._code import ExceptionInfo
from _pytest._code.code import ExceptionRepr
from _pytest._io import TerminalWriter
from _pytest._io.wcwidth import wcswidth
import _pytest._version
from _pytest.compat import running_on_ci
from _pytest.config import _PluggyPlugin
from _pytest.config import Config
from _pytest.config import ExitCode
from _pytest.config import hookimpl
from _pytest.config.argparsing import Parser
from _pytest.nodes import Item
from _pytest.nodes import Node
from _pytest.pathlib import absolutepath
from _pytest.pathlib import bestrelpath
from _pytest.reports import BaseReport
from _pytest.reports import CollectReport
from _pytest.reports import TestReport


if TYPE_CHECKING:
    from _pytest.main import Session


REPORT_COLLECTING_RESOLUTION = 0.5

KNOWN_TYPES = (
    "failed",
    "passed",
    "skipped",
    "deselected",
    "xfailed",
    "xpassed",
    "warnings",
    "error",
    "subtests passed",
    "subtests failed",
    "subtests skipped",
)

_REPORTCHARS_DEFAULT = "fE"


class MoreQuietAction(argparse.Action):
    """A modified copy of the argparse count action which counts down and updates
    the legacy quiet attribute at the same time.

    Used to unify verbosity handling.
    """

    def __init__(
        self,
        option_strings: Sequence[str],
        dest: str,
        default: object = None,
        required: bool = False,
        help: str | None = None,
    ) -> None:
        super().__init__(
            option_strings=option_strings,
            dest=dest,
            nargs=0,
            default=default,
            required=required,
            help=help,
        )

    def __call__(
        self,
        parser: argparse.ArgumentParser,
        namespace: argparse.Namespace,
        values: str | Sequence[object] | None,
        option_string: str | None = None,
    ) -> None:
        new_count = getattr(namespace, self.dest, 0) - 1
        setattr(namespace, self.dest, new_count)
        # todo Deprecate config.quiet
        namespace.quiet = getattr(namespace, "quiet", 0) + 1


class TestShortLogReport(NamedTuple):
    """Used to store the test status result category, shortletter and verbose word.
    For example ``"rerun", "R", ("RERUN", {"yellow": True})``.

    :ivar category:
        The class of result, for example ``“passed”``, ``“skipped”``, ``“error”``, or the empty string.

    :ivar letter:
        The short letter shown as testing progresses, for example ``"."``, ``"s"``, ``"E"``, or the empty string.

    :ivar word:
        Verbose word is shown as testing progresses in verbose mode, for example ``"PASSED"``, ``"SKIPPED"``,
        ``"ERROR"``, or the empty string.
    """

    category: str
    letter: str
    word: str | tuple[str, Mapping[str, bool]]


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("terminal reporting", "Reporting", after="general")
    group._addoption(  # private to use reserved lower-case short option
        "-v",
        "--verbose",
        action="count",
        default=0,
        dest="verbose",
        help="Increase verbosity",
    )
    group.addoption(
        "--no-header",
        action="store_true",
        default=False,
        dest="no_header",
        help="Disable header",
    )
    group.addoption(
        "--no-summary",
        action="store_true",
        default=False,
        dest="no_summary",
        help="Disable summary",
    )
    group.addoption(
        "--no-fold-skipped",
        action="store_false",
        dest="fold_skipped",
        default=True,
        help="Do not fold skipped tests in short summary.",
    )
    group.addoption(
        "--force-short-summary",
        action="store_true",
        dest="force_short_summary",
        default=False,
        help="Force condensed summary output regardless of verbosity level.",
    )
    group._addoption(  # private to use reserved lower-case short option
        "-q",
        "--quiet",
        action=MoreQuietAction,
        default=0,
        dest="verbose",
        help="Decrease verbosity",
    )
    group.addoption(
        "--verbosity",
        dest="verbose",
        type=int,
        default=0,
        help="Set verbosity. Default: 0.",
    )
    group._addoption(  # private to use reserved lower-case short option
        "-r",
        "--report-chars",
        action="store",
        dest="reportchars",
        default=_REPORTCHARS_DEFAULT,
        metavar="chars",
        help="Show extra test summary info as specified by chars: (f)ailed, "
        "(E)rror, (s)kipped, (x)failed, (X)passed, "
        "(p)assed, (P)assed with output, (a)ll except passed (p/P), or (A)ll. "
        "(w)arnings are enabled by default (see --disable-warnings), "
        "'N' can be used to reset the list. (default: 'fE').",
    )
    group.addoption(
        "--disable-warnings",
        "--disable-pytest-warnings",
        default=False,
        dest="disable_warnings",
        action="store_true",
        help="Disable warnings summary",
    )
    group._addoption(  # private to use reserved lower-case short option
        "-l",
        "--showlocals",
        action="store_true",
        dest="showlocals",
        default=False,
        help="Show locals in tracebacks (disabled by default)",
    )
    group.addoption(
        "--no-showlocals",
        action="store_false",
        dest="showlocals",
        help="Hide locals in tracebacks (negate --showlocals passed through addopts)",
    )
    group.addoption(
        "--tb",
        metavar="style",
        action="store",
        dest="tbstyle",
        default="auto",
        choices=["auto", "long", "short", "no", "line", "native"],
        help="Traceback print mode (auto/long/short/line/native/no)",
    )
    group.addoption(
        "--xfail-tb",
        action="store_true",
        dest="xfail_tb",
        default=False,
        help="Show tracebacks for xfail (as long as --tb != no)",
    )
    group.addoption(
        "--show-capture",
        action="store",
        dest="showcapture",
        choices=["no", "stdout", "stderr", "log", "all"],
        default="all",
        help="Controls how captured stdout/stderr/log is shown on failed tests. "
        "Default: all.",
    )
    group.addoption(
        "--fulltrace",
        "--full-trace",
        action="store_true",
        default=False,
        help="Don't cut any tracebacks (default is to cut)",
    )
    group.addoption(
        "--color",
        metavar="color",
        action="store",
        dest="color",
        default="auto",
        choices=["yes", "no", "auto"],
        help="Color terminal output (yes/no/auto)",
    )
    group.addoption(
        "--code-highlight",
        default="yes",
        choices=["yes", "no"],
        help="Whether code should be highlighted (only if --color is also enabled). "
        "Default: yes.",
    )

    parser.addini(
        "console_output_style",
        help='Console output: "classic", or with additional progress information '
        '("progress" (percentage) | "count" | "progress-even-when-capture-no" (forces '
        "progress even when capture=no)",
        default="progress",
    )
    Config._add_verbosity_ini(
        parser,
        Config.VERBOSITY_TEST_CASES,
        help=(
            "Specify a verbosity level for test case execution, overriding the main level. "
            "Higher levels will provide more detailed information about each test case executed."
        ),
    )


def pytest_configure(config: Config) -> None:
    reporter = TerminalReporter(config, sys.stdout)
    config.pluginmanager.register(reporter, "terminalreporter")
    if config.option.debug or config.option.traceconfig:

        def mywriter(tags, args):
            msg = " ".join(map(str, args))
            reporter.write_line("[traceconfig] " + msg)

        config.trace.root.setprocessor("pytest:config", mywriter)

    # See terminalprogress.py.
    # On Windows it's safe to load by default.
    if sys.platform == "win32":
        config.pluginmanager.import_plugin("terminalprogress")


def getreportopt(config: Config) -> str:
    reportchars: str = config.option.reportchars

    old_aliases = {"F", "S"}
    reportopts = ""
    for char in reportchars:
        if char in old_aliases:
            char = char.lower()
        if char == "a":
            reportopts = "sxXEf"
        elif char == "A":
            reportopts = "PpsxXEf"
        elif char == "N":
            reportopts = ""
        elif char not in reportopts:
            reportopts += char

    if not config.option.disable_warnings and "w" not in reportopts:
        reportopts = "w" + reportopts
    elif config.option.disable_warnings and "w" in reportopts:
        reportopts = reportopts.replace("w", "")

    return reportopts


@hookimpl(trylast=True)  # after _pytest.runner
def pytest_report_teststatus(report: BaseReport) -> tuple[str, str, str]:
    letter = "F"
    if report.passed:
        letter = "."
    elif report.skipped:
        letter = "s"

    outcome: str = report.outcome
    if report.when in ("collect", "setup", "teardown") and outcome == "failed":
        outcome = "error"
        letter = "E"

    return outcome, letter, outcome.upper()


@dataclasses.dataclass
class WarningReport:
    """Simple structure to hold warnings information captured by ``pytest_warning_recorded``.

    :ivar str message:
        User friendly message about the warning.
    :ivar str|None nodeid:
        nodeid that generated the warning (see ``get_location``).
    :ivar tuple fslocation:
        File system location of the source of the warning (see ``get_location``).
    """

    message: str
    nodeid: str | None = None
    fslocation: tuple[str, int] | None = None

    count_towards_summary: ClassVar = True

    def get_location(self, config: Config) -> str | None:
        """Return the more user-friendly information about the location of a warning, or None."""
        if self.nodeid:
            return self.nodeid
        if self.fslocation:
            filename, linenum = self.fslocation
            relpath = bestrelpath(config.invocation_params.dir, absolutepath(filename))
            return f"{relpath}:{linenum}"
        return None


@final
class TerminalReporter:
    def __init__(self, config: Config, file: TextIO | None = None) -> None:
        import _pytest.config

        self.config = config
        self._numcollected = 0
        self._session: Session | None = None
        self._showfspath: bool | None = None

        self.stats: dict[str, list[Any]] = {}
        self._main_color: str | None = None
        self._known_types: list[str] | None = None
        self.startpath = config.invocation_params.dir
        if file is None:
            file = sys.stdout
        self._tw = _pytest.config.create_terminal_writer(config, file)
        self._screen_width = self._tw.fullwidth
        self.currentfspath: None | Path | str | int = None
        self.reportchars = getreportopt(config)
        self.foldskipped = config.option.fold_skipped
        self.hasmarkup = self._tw.hasmarkup
        # isatty should be a method but was wrongly implemented as a boolean.
        # We use CallableBool here to support both.
        self.isatty = compat.CallableBool(file.isatty())
        self._progress_nodeids_reported: set[str] = set()
        self._timing_nodeids_reported: set[str] = set()
        self._show_progress_info = self._determine_show_progress_info()
        self._collect_report_last_write = timing.Instant()
        self._already_displayed_warnings: int | None = None
        self._keyboardinterrupt_memo: ExceptionRepr | None = None

    def _determine_show_progress_info(
        self,
    ) -> Literal["progress", "count", "times", False]:
        """Return whether we should display progress information based on the current config."""
        # do not show progress if we are not capturing output (#3038) unless explicitly
        # overridden by progress-even-when-capture-no
        if (
            self.config.getoption("capture", "no") == "no"
            and self.config.getini("console_output_style")
            != "progress-even-when-capture-no"
        ):
            return False
        # do not show progress if we are showing fixture setup/teardown
        if self.config.getoption("setupshow", False):
            return False
        cfg: str = self.config.getini("console_output_style")
        if cfg in {"progress", "progress-even-when-capture-no"}:
            return "progress"
        elif cfg == "count":
            return "count"
        elif cfg == "times":
            return "times"
        else:
            return False

    @property
    def verbosity(self) -> int:
        verbosity: int = self.config.option.verbose
        return verbosity

    @property
    def showheader(self) -> bool:
        return self.verbosity >= 0

    @property
    def no_header(self) -> bool:
        return bool(self.config.option.no_header)

    @property
    def no_summary(self) -> bool:
        return bool(self.config.option.no_summary)

    @property
    def showfspath(self) -> bool:
        if self._showfspath is None:
            return self.config.get_verbosity(Config.VERBOSITY_TEST_CASES) >= 0
        return self._showfspath

    @showfspath.setter
    def showfspath(self, value: bool | None) -> None:
        self._showfspath = value

    @property
    def showlongtestinfo(self) -> bool:
        return self.config.get_verbosity(Config.VERBOSITY_TEST_CASES) > 0

    @property
    def reported_progress(self) -> int:
        """The amount of items reported in the progress so far.

        :meta private:
        """
        return len(self._progress_nodeids_reported)

    def hasopt(self, char: str) -> bool:
        char = {"xfailed": "x", "skipped": "s"}.get(char, char)
        return char in self.reportchars

    def write_fspath_result(self, nodeid: str, res: str, **markup: bool) -> None:
        fspath = self.config.rootpath / nodeid.split("::", maxsplit=1)[0]
        if self.currentfspath is None or fspath != self.currentfspath:
            if self.currentfspath is not None and self._show_progress_info:
                self._write_progress_information_filling_space()
            self.currentfspath = fspath
            relfspath = bestrelpath(self.startpath, fspath)
            self._tw.line()
            self._tw.write(relfspath + " ")
        self._tw.write(res, flush=True, **markup)

    def write_ensure_prefix(self, prefix: str, extra: str = "", **kwargs) -> None:
        if self.currentfspath != prefix:
            self._tw.line()
            self.currentfspath = prefix
            self._tw.write(prefix)
        if extra:
            self._tw.write(extra, **kwargs)
            self.currentfspath = -2

    def ensure_newline(self) -> None:
        if self.currentfspath:
            self._tw.line()
            self.currentfspath = None

    def wrap_write(
        self,
        content: str,
        *,
        flush: bool = False,
        margin: int = 8,
        line_sep: str = "\n",
        **markup: bool,
    ) -> None:
        """Wrap message with margin for progress info."""
        width_of_current_line = self._tw.width_of_current_line
        wrapped = line_sep.join(
            textwrap.wrap(
                " " * width_of_current_line + content,
                width=self._screen_width - margin,
                drop_whitespace=True,
                replace_whitespace=False,
            ),
        )
        wrapped = wrapped[width_of_current_line:]
        self._tw.write(wrapped, flush=flush, **markup)

    def write(self, content: str, *, flush: bool = False, **markup: bool) -> None:
        self._tw.write(content, flush=flush, **markup)

    def write_raw(self, content: str, *, flush: bool = False) -> None:
        self._tw.write_raw(content, flush=flush)

    def flush(self) -> None:
        self._tw.flush()

    def write_line(self, line: str | bytes, **markup: bool) -> None:
        if not isinstance(line, str):
            line = str(line, errors="replace")
        self.ensure_newline()
        self._tw.line(line, **markup)

    def rewrite(self, line: str, **markup: bool) -> None:
        """Rewinds the terminal cursor to the beginning and writes the given line.

        :param erase:
            If True, will also add spaces until the full terminal width to ensure
            previous lines are properly erased.

        The rest of the keyword arguments are markup instructions.
        """
        erase = markup.pop("erase", False)
        if erase:
            fill_count = self._tw.fullwidth - len(line) - 1
            fill = " " * fill_count
        else:
            fill = ""
        line = str(line)
        self._tw.write("\r" + line + fill, **markup)

    def write_sep(
        self,
        sep: str,
        title: str | None = None,
        fullwidth: int | None = None,
        **markup: bool,
    ) -> None:
        self.ensure_newline()
        self._tw.sep(sep, title, fullwidth, **markup)

    def section(self, title: str, sep: str = "=", **kw: bool) -> None:
        self._tw.sep(sep, title, **kw)

    def line(self, msg: str, **kw: bool) -> None:
        self._tw.line(msg, **kw)

    def _add_stats(self, category: str, items: Sequence[Any]) -> None:
        set_main_color = category not in self.stats
        self.stats.setdefault(category, []).extend(items)
        if set_main_color:
            self._set_main_color()

    def pytest_internalerror(self, excrepr: ExceptionRepr) -> bool:
        for line in str(excrepr).split("\n"):
            self.write_line("INTERNALERROR> " + line)
        return True

    def pytest_warning_recorded(
        self,
        warning_message: warnings.WarningMessage,
        nodeid: str,
    ) -> None:
        from _pytest.warnings import warning_record_to_str

        fslocation = warning_message.filename, warning_message.lineno
        message = warning_record_to_str(warning_message)

        warning_report = WarningReport(
            fslocation=fslocation, message=message, nodeid=nodeid
        )
        self._add_stats("warnings", [warning_report])

    def pytest_plugin_registered(self, plugin: _PluggyPlugin) -> None:
        if self.config.option.traceconfig:
            msg = f"PLUGIN registered: {plugin}"
            # XXX This event may happen during setup/teardown time
            #     which unfortunately captures our output here
            #     which garbles our output if we use self.write_line.
            self.write_line(msg)

    def pytest_deselected(self, items: Sequence[Item]) -> None:
        self._add_stats("deselected", items)

    def pytest_runtest_logstart(
        self, nodeid: str, location: tuple[str, int | None, str]
    ) -> None:
        fspath, lineno, domain = location
        # Ensure that the path is printed before the
        # 1st test of a module starts running.
        if self.showlongtestinfo:
            line = self._locationline(nodeid, fspath, lineno, domain)
            self.write_ensure_prefix(line, "")
            self.flush()
        elif self.showfspath:
            self.write_fspath_result(nodeid, "")
            self.flush()

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        self._tests_ran = True
        rep = report

        res = TestShortLogReport(
            *self.config.hook.pytest_report_teststatus(report=rep, config=self.config)
        )
        category, letter, word = res.category, res.letter, res.word
        if not isinstance(word, tuple):
            markup = None
        else:
            word, markup = word
        self._add_stats(category, [rep])
        if not letter and not word:
            # Probably passed setup/teardown.
            return
        if markup is None:
            was_xfail = hasattr(report, "wasxfail")
            if rep.passed and not was_xfail:
                markup = {"green": True}
            elif rep.passed and was_xfail:
                markup = {"yellow": True}
            elif rep.failed:
                markup = {"red": True}
            elif rep.skipped:
                markup = {"yellow": True}
            else:
                markup = {}
        self._progress_nodeids_reported.add(rep.nodeid)
        if self.config.get_verbosity(Config.VERBOSITY_TEST_CASES) <= 0:
            self._tw.write(letter, **markup)
            # When running in xdist, the logreport and logfinish of multiple
            # items are interspersed, e.g. `logreport`, `logreport`,
            # `logfinish`, `logfinish`. To avoid the "past edge" calculation
            # from getting confused and overflowing (#7166), do the past edge
            # printing here and not in logfinish, except for the 100% which
            # should only be printed after all teardowns are finished.
            if self._show_progress_info and not self._is_last_item:
                self._write_progress_information_if_past_edge()
        else:
            line = self._locationline(rep.nodeid, *rep.location)
            running_xdist = hasattr(rep, "node")
            if not running_xdist:
                self.write_ensure_prefix(line, word, **markup)
                if rep.skipped or hasattr(report, "wasxfail"):
                    reason = _get_raw_skip_reason(rep)
                    if self.config.get_verbosity(Config.VERBOSITY_TEST_CASES) < 2:
                        available_width = (
                            (self._tw.fullwidth - self._tw.width_of_current_line)
                            - len(" [100%]")
                            - 1
                        )
                        formatted_reason = _format_trimmed(
                            " ({})", reason, available_width
                        )
                    else:
                        formatted_reason = f" ({reason})"

                    if reason and formatted_reason is not None:
                        self.wrap_write(formatted_reason)
                if self._show_progress_info:
                    self._write_progress_information_filling_space()
            else:
                self.ensure_newline()
                self._tw.write(f"[{rep.node.gateway.id}]")
                if self._show_progress_info:
                    self._tw.write(
                        self._get_progress_information_message() + " ", cyan=True
                    )
                else:
                    self._tw.write(" ")
                self._tw.write(word, **markup)
                self._tw.write(" " + line)
                self.currentfspath = -2
        self.flush()

    @property
    def _is_last_item(self) -> bool:
        assert self._session is not None
        return self.reported_progress == self._session.testscollected

    @hookimpl(wrapper=True)
    def pytest_runtestloop(self) -> Generator[None, object, object]:
        result = yield

        # Write the final/100% progress -- deferred until the loop is complete.
        if (
            self.config.get_verbosity(Config.VERBOSITY_TEST_CASES) <= 0
            and self._show_progress_info
            and self.reported_progress
        ):
            self._write_progress_information_filling_space()

        return result

    def _get_progress_information_message(self) -> str:
        assert self._session
        collected = self._session.testscollected
        if self._show_progress_info == "count":
            if collected:
                progress = self.reported_progress
                counter_format = f"{{:{len(str(collected))}d}}"
                format_string = f" [{counter_format}/{{}}]"
                return format_string.format(progress, collected)
            return f" [ {collected} / {collected} ]"
        if self._show_progress_info == "times":
            if not collected:
                return ""
            all_reports = (
                self._get_reports_to_display("passed")
                + self._get_reports_to_display("xpassed")
                + self._get_reports_to_display("failed")
                + self._get_reports_to_display("xfailed")
                + self._get_reports_to_display("skipped")
                + self._get_reports_to_display("error")
                + self._get_reports_to_display("")
            )
            current_location = all_reports[-1].location[0]
            not_reported = [
                r for r in all_reports if r.nodeid not in self._timing_nodeids_reported
            ]
            tests_in_module = sum(
                i.location[0] == current_location for i in self._session.items
            )
            tests_completed = sum(
                r.when == "setup"
                for r in not_reported
                if r.location[0] == current_location
            )
            last_in_module = tests_completed == tests_in_module
            if self.showlongtestinfo or last_in_module:
                self._timing_nodeids_reported.update(r.nodeid for r in not_reported)
                return format_node_duration(
                    sum(r.duration for r in not_reported if isinstance(r, TestReport))
                )
            return ""
        if collected:
            return f" [{self.reported_progress * 100 // collected:3d}%]"
        return " [100%]"

    def _write_progress_information_if_past_edge(self) -> None:
        w = self._width_of_current_line
        if self._show_progress_info == "count":
            assert self._session
            num_tests = self._session.testscollected
            progress_length = len(f" [{num_tests}/{num_tests}]")
        elif self._show_progress_info == "times":
            progress_length = len(" 99h 59m")
        else:
            progress_length = len(" [100%]")
        past_edge = w + progress_length + 1 >= self._screen_width
        if past_edge:
            main_color, _ = self._get_main_color()
            msg = self._get_progress_information_message()
            self._tw.write(msg + "\n", **{main_color: True})

    def _write_progress_information_filling_space(self) -> None:
        color, _ = self._get_main_color()
        msg = self._get_progress_information_message()
        w = self._width_of_current_line
        fill = self._tw.fullwidth - w - 1
        self.write(msg.rjust(fill), flush=True, **{color: True})

    @property
    def _width_of_current_line(self) -> int:
        """Return the width of the current line."""
        return self._tw.width_of_current_line

    def pytest_collection(self) -> None:
        if self.isatty():
            if self.config.option.verbose >= 0:
                self.write("collecting ... ", flush=True, bold=True)
        elif self.config.option.verbose >= 1:
            self.write("collecting ... ", flush=True, bold=True)

    def pytest_collectreport(self, report: CollectReport) -> None:
        if report.failed:
            self._add_stats("error", [report])
        elif report.skipped:
            self._add_stats("skipped", [report])
        items = [x for x in report.result if isinstance(x, Item)]
        self._numcollected += len(items)
        if self.isatty():
            self.report_collect()

    def report_collect(self, final: bool = False) -> None:
        if self.config.option.verbose < 0:
            return

        if not final:
            # Only write the "collecting" report every `REPORT_COLLECTING_RESOLUTION`.
            if (
                self._collect_report_last_write.elapsed().seconds
                < REPORT_COLLECTING_RESOLUTION
            ):
                return
            self._collect_report_last_write = timing.Instant()

        errors = len(self.stats.get("error", []))
        skipped = len(self.stats.get("skipped", []))
        deselected = len(self.stats.get("deselected", []))
        selected = self._numcollected - deselected
        line = "collected " if final else "collecting "
        line += (
            str(self._numcollected) + " item" + ("" if self._numcollected == 1 else "s")
        )
        if errors:
            line += f" / {errors} error{'s' if errors != 1 else ''}"
        if deselected:
            line += f" / {deselected} deselected"
        if skipped:
            line += f" / {skipped} skipped"
        if self._numcollected > selected:
            line += f" / {selected} selected"
        if self.isatty():
            self.rewrite(line, bold=True, erase=True)
            if final:
                self.write("\n")
        else:
            self.write_line(line)

    @hookimpl(trylast=True)
    def pytest_sessionstart(self, session: Session) -> None:
        self._session = session
        self._session_start = timing.Instant()
        if not self.showheader:
            return
        self.write_sep("=", "test session starts", bold=True)
        verinfo = platform.python_version()
        if not self.no_header:
            msg = f"platform {sys.platform} -- Python {verinfo}"
            pypy_version_info = getattr(sys, "pypy_version_info", None)
            if pypy_version_info:
                verinfo = ".".join(map(str, pypy_version_info[:3]))
                msg += f"[pypy-{verinfo}-{pypy_version_info[3]}]"
            msg += f", pytest-{_pytest._version.version}, pluggy-{pluggy.__version__}"
            if (
                self.verbosity > 0
                or self.config.option.debug
                or getattr(self.config.option, "pastebin", None)
            ):
                msg += " -- " + str(sys.executable)
            self.write_line(msg)
            lines = self.config.hook.pytest_report_header(
                config=self.config, start_path=self.startpath
            )
            self._write_report_lines_from_hooks(lines)

    def _write_report_lines_from_hooks(
        self, lines: Sequence[str | Sequence[str]]
    ) -> None:
        for line_or_lines in reversed(lines):
            if isinstance(line_or_lines, str):
                self.write_line(line_or_lines)
            else:
                for line in line_or_lines:
                    self.write_line(line)

    def pytest_report_header(self, config: Config) -> list[str]:
        result = [f"rootdir: {config.rootpath}"]

        if config.inipath:
            warning = ""
            if config._ignored_config_files:
                warning = f" (WARNING: ignoring pytest config in {', '.join(config._ignored_config_files)}!)"
            result.append(
                "configfile: " + bestrelpath(config.rootpath, config.inipath) + warning
            )

        if config.args_source == Config.ArgsSource.TESTPATHS:
            testpaths: list[str] = config.getini("testpaths")
            result.append("testpaths: {}".format(", ".join(testpaths)))

        plugininfo = config.pluginmanager.list_plugin_distinfo()
        if plugininfo:
            result.append(
                "plugins: {}".format(", ".join(_plugin_nameversions(plugininfo)))
            )
        return result

    def pytest_collection_finish(self, session: Session) -> None:
        self.report_collect(True)

        lines = self.config.hook.pytest_report_collectionfinish(
            config=self.config,
            start_path=self.startpath,
            items=session.items,
        )
        self._write_report_lines_from_hooks(lines)

        if self.config.getoption("collectonly"):
            if session.items:
                if self.config.option.verbose > -1:
                    self._tw.line("")
                self._printcollecteditems(session.items)

            failed = self.stats.get("failed")
            if failed:
                self._tw.sep("!", "collection failures")
                for rep in failed:
                    rep.toterminal(self._tw)

    def _printcollecteditems(self, items: Sequence[Item]) -> None:
        test_cases_verbosity = self.config.get_verbosity(Config.VERBOSITY_TEST_CASES)
        if test_cases_verbosity < 0:
            if test_cases_verbosity < -1:
                counts = Counter(item.nodeid.split("::", 1)[0] for item in items)
                for name, count in sorted(counts.items()):
                    self._tw.line(f"{name}: {count}")
            else:
                for item in items:
                    self._tw.line(item.nodeid)
            return
        stack: list[Node] = []
        indent = ""
        for item in items:
            needed_collectors = item.listchain()[1:]  # strip root node
            while stack:
                if stack == needed_collectors[: len(stack)]:
                    break
                stack.pop()
            for col in needed_collectors[len(stack) :]:
                stack.append(col)
                indent = (len(stack) - 1) * "  "
                self._tw.line(f"{indent}{col}")
                if test_cases_verbosity >= 1:
                    obj = getattr(col, "obj", None)
                    doc = inspect.getdoc(obj) if obj else None
                    if doc:
                        for line in doc.splitlines():
                            self._tw.line("{}{}".format(indent + "  ", line))

    @hookimpl(wrapper=True)
    def pytest_sessionfinish(
        self, session: Session, exitstatus: int | ExitCode
    ) -> Generator[None]:
        result = yield
        self._tw.line("")
        summary_exit_codes = (
            ExitCode.OK,
            ExitCode.TESTS_FAILED,
            ExitCode.INTERRUPTED,
            ExitCode.USAGE_ERROR,
            ExitCode.NO_TESTS_COLLECTED,
            ExitCode.MAX_WARNINGS_ERROR,
        )
        if exitstatus in summary_exit_codes and not self.no_summary:
            self.config.hook.pytest_terminal_summary(
                terminalreporter=self, exitstatus=exitstatus, config=self.config
            )
        # Check --max-warnings threshold after all warnings have been collected.
        max_warnings = self._get_max_warnings()
        if max_warnings is not None and session.exitstatus == ExitCode.OK:
            warning_count = len(self.stats.get("warnings", []))
            if warning_count > max_warnings:
                session.exitstatus = ExitCode.MAX_WARNINGS_ERROR
                self.write_line(
                    "Tests pass, but maximum allowed warnings exceeded: "
                    f"{warning_count} > {max_warnings}",
                    red=True,
                )
        if session.shouldfail:
            self.write_sep("!", str(session.shouldfail), red=True)
        if exitstatus == ExitCode.INTERRUPTED:
            self._report_keyboardinterrupt()
            self._keyboardinterrupt_memo = None
        elif session.shouldstop:
            self.write_sep("!", str(session.shouldstop), red=True)
        self.summary_stats()
        return result

    @hookimpl(wrapper=True)
    def pytest_terminal_summary(self) -> Generator[None]:
        self.summary_errors()
        self.summary_failures()
        self.summary_xfailures()
        self.summary_warnings()
        self.summary_passes()
        self.summary_xpasses()
        try:
            return (yield)
        finally:
            self.short_test_summary()
            # Display any extra warnings from teardown here (if any).
            self.summary_warnings()

    def pytest_keyboard_interrupt(self, excinfo: ExceptionInfo[BaseException]) -> None:
        self._keyboardinterrupt_memo = excinfo.getrepr(funcargs=True)

    def pytest_unconfigure(self) -> None:
        if self._keyboardinterrupt_memo is not None:
            self._report_keyboardinterrupt()

    def _report_keyboardinterrupt(self) -> None:
        excrepr = self._keyboardinterrupt_memo
        assert excrepr is not None
        assert excrepr.reprcrash is not None
        msg = excrepr.reprcrash.message
        self.write_sep("!", msg)
        if "KeyboardInterrupt" in msg:
            if self.config.option.fulltrace:
                excrepr.toterminal(self._tw)
            else:
                excrepr.reprcrash.toterminal(self._tw)
                self._tw.line(
                    "(to show a full traceback on KeyboardInterrupt use --full-trace)",
                    yellow=True,
                )

    def _locationline(
        self, nodeid: str, fspath: str, lineno: int | None, domain: str
    ) -> str:
        def mkrel(nodeid: str) -> str:
            line = self.config.cwd_relative_nodeid(nodeid)
            if domain and line.endswith(domain):
                line = line[: -len(domain)]
                values = domain.split("[")
                values[0] = values[0].replace(".", "::")  # don't replace '.' in params
                line += "[".join(values)
            return line

        # fspath comes from testid which has a "/"-normalized path.
        if fspath:
            res = mkrel(nodeid)
            if self.verbosity >= 2 and (
                nodeid.split("::", maxsplit=1)[0] != nodes.norm_sep(fspath)
            ):
                res += " <- " + bestrelpath(self.startpath, Path(fspath))
        else:
            res = "[location]"
        return res + " "

    def _getfailureheadline(self, rep):
        head_line = rep.head_line
        if head_line:
            return head_line
        return "test session"  # XXX?

    def _getcrashline(self, rep):
        try:
            return str(rep.longrepr.reprcrash)
        except AttributeError:
            try:
                return str(rep.longrepr)[:50]
            except AttributeError:
                return ""

    def _get_max_warnings(self) -> int | None:
        """Return the max_warnings threshold, from CLI or INI, or None if unset."""
        value = self.config.option.max_warnings
        if value is not None:
            return int(value)
        ini_value = self.config.getini("max_warnings")
        if ini_value:
            return int(ini_value)
        return None

    #
    # Summaries for sessionfinish.
    #
    def getreports(self, name: str):
        return [x for x in self.stats.get(name, ()) if not hasattr(x, "_pdbshown")]

    def summary_warnings(self) -> None:
        if self.hasopt("w"):
            all_warnings: list[WarningReport] | None = self.stats.get("warnings")
            if not all_warnings:
                return

            final = self._already_displayed_warnings is not None
            if final:
                warning_reports = all_warnings[self._already_displayed_warnings :]
            else:
                warning_reports = all_warnings
            self._already_displayed_warnings = len(warning_reports)
            if not warning_reports:
                return

            reports_grouped_by_message: dict[str, list[WarningReport]] = {}
            for wr in warning_reports:
                reports_grouped_by_message.setdefault(wr.message, []).append(wr)

            def collapsed_location_report(reports: list[WarningReport]) -> str:
                locations = []
                for w in reports:
                    location = w.get_location(self.config)
                    if location:
                        locations.append(location)

                if len(locations) < 10:
                    return "\n".join(map(str, locations))

                counts_by_filename = Counter(
                    str(loc).split("::", 1)[0] for loc in locations
                )
                return "\n".join(
                    "{}: {} warning{}".format(k, v, "s" if v > 1 else "")
                    for k, v in counts_by_filename.items()
                )

            title = "warnings summary (final)" if final else "warnings summary"
            self.write_sep("=", title, yellow=True, bold=False)
            for message, message_reports in reports_grouped_by_message.items():
                maybe_location = collapsed_location_report(message_reports)
                if maybe_location:
                    self._tw.line(maybe_location)
                    lines = message.splitlines()
                    indented = "\n".join("  " + x for x in lines)
                    message = indented.rstrip()
                else:
                    message = message.rstrip()
                self._tw.line(message)
                self._tw.line()
            self._tw.line(
                "-- Docs: https://docs.pytest.org/en/stable/how-to/capture-warnings.html"
            )

    def summary_passes(self) -> None:
        self.summary_passes_combined("passed", "PASSES", "P")

    def summary_xpasses(self) -> None:
        self.summary_passes_combined("xpassed", "XPASSES", "X")

    def summary_passes_combined(
        self, which_reports: str, sep_title: str, needed_opt: str
    ) -> None:
        if self.config.option.tbstyle != "no":
            if self.hasopt(needed_opt):
                reports: list[TestReport] = self.getreports(which_reports)
                if not reports:
                    return
                self.write_sep("=", sep_title)
                for rep in reports:
                    if rep.sections:
                        msg = self._getfailureheadline(rep)
                        self.write_sep("_", msg, green=True, bold=True)
                        self._outrep_summary(rep)
                    self._handle_teardown_sections(rep.nodeid)

    def _get_teardown_reports(self, nodeid: str) -> list[TestReport]:
        reports = self.getreports("")
        return [
            report
            for report in reports
            if report.when == "teardown" and report.nodeid == nodeid
        ]

    def _handle_teardown_sections(self, nodeid: str) -> None:
        for report in self._get_teardown_reports(nodeid):
            self.print_teardown_sections(report)

    def print_teardown_sections(self, rep: TestReport) -> None:
        showcapture = self.config.option.showcapture
        if showcapture == "no":
            return
        for secname, content in rep.sections:
            if showcapture != "all" and showcapture not in secname:
                continue
            if "teardown" in secname:
                self._tw.sep("-", secname)
                if content[-1:] == "\n":
                    content = content[:-1]
                self._tw.line(content)

    def summary_failures(self) -> None:
        style = self.config.option.tbstyle
        self.summary_failures_combined("failed", "FAILURES", style=style)

    def summary_xfailures(self) -> None:
        show_tb = self.config.option.xfail_tb
        style = self.config.option.tbstyle if show_tb else "no"
        self.summary_failures_combined("xfailed", "XFAILURES", style=style)

    def summary_failures_combined(
        self,
        which_reports: str,
        sep_title: str,
        *,
        style: str,
        needed_opt: str | None = None,
    ) -> None:
        if style != "no":
            if not needed_opt or self.hasopt(needed_opt):
                reports: list[BaseReport] = self.getreports(which_reports)
                if not reports:
                    return
                self.write_sep("=", sep_title)
                if style == "line":
                    for rep in reports:
                        line = self._getcrashline(rep)
                        self._outrep_summary(rep)
                        self.write_line(line)
                else:
                    for rep in reports:
                        msg = self._getfailureheadline(rep)
                        self.write_sep("_", msg, red=True, bold=True)
                        self._outrep_summary(rep)
                        self._handle_teardown_sections(rep.nodeid)

    def summary_errors(self) -> None:
        if self.config.option.tbstyle != "no":
            reports: list[BaseReport] = self.getreports("error")
            if not reports:
                return
            self.write_sep("=", "ERRORS")
            for rep in self.stats["error"]:
                msg = self._getfailureheadline(rep)
                if rep.when == "collect":
                    msg = "ERROR collecting " + msg
                else:
                    msg = f"ERROR at {rep.when} of {msg}"
                self.write_sep("_", msg, red=True, bold=True)
                self._outrep_summary(rep)

    def _outrep_summary(self, rep: BaseReport) -> None:
        rep.toterminal(self._tw)
        showcapture = self.config.option.showcapture
        if showcapture == "no":
            return
        for secname, content in rep.sections:
            if showcapture != "all" and showcapture not in secname:
                continue
            self._tw.sep("-", secname)
            if content[-1:] == "\n":
                content = content[:-1]
            self._tw.line(content)

    def summary_stats(self) -> None:
        if self.verbosity < -1:
            return

        session_duration = self._session_start.elapsed()
        (parts, main_color) = self.build_summary_stats_line()
        line_parts = []

        display_sep = self.verbosity >= 0
        if display_sep:
            fullwidth = self._tw.fullwidth
        for text, markup in parts:
            with_markup = self._tw.markup(text, **markup)
            if display_sep:
                fullwidth += len(with_markup) - len(text)
            line_parts.append(with_markup)
        msg = ", ".join(line_parts)

        main_markup = {main_color: True}
        duration = f" in {format_session_duration(session_duration.seconds)}"
        duration_with_markup = self._tw.markup(duration, **main_markup)
        if display_sep:
            fullwidth += len(duration_with_markup) - len(duration)
        msg += duration_with_markup

        if display_sep:
            markup_for_end_sep = self._tw.markup("", **main_markup)
            if markup_for_end_sep.endswith("\x1b[0m"):
                markup_for_end_sep = markup_for_end_sep[:-4]
            fullwidth += len(markup_for_end_sep)
            msg += markup_for_end_sep

        if display_sep:
            self.write_sep("=", msg, fullwidth=fullwidth, **main_markup)
        else:
            self.write_line(msg, **main_markup)

    def short_test_summary(self) -> None:
        if not self.reportchars:
            return

        def show_simple(lines: list[str], *, stat: str) -> None:
            failed = self.stats.get(stat, [])
            if not failed:
                return
            config = self.config
            for rep in failed:
                color = _color_for_type.get(stat, _color_for_type_default)
                line = _get_line_with_reprcrash_message(
                    config, rep, self._tw, {color: True}
                )
                lines.append(line)

        def show_xfailed(lines: list[str]) -> None:
            xfailed = self.stats.get("xfailed", [])
            for rep in xfailed:
                verbose_word, verbose_markup = rep._get_verbose_word_with_markup(
                    self.config, {_color_for_type["warnings"]: True}
                )
                markup_word = self._tw.markup(verbose_word, **verbose_markup)
                nodeid = _get_node_id_with_markup(self._tw, self.config, rep)
                line = f"{markup_word} {nodeid}"
                reason = rep.wasxfail
                if reason:
                    line += " - " + str(reason)

                lines.append(line)

        def show_xpassed(lines: list[str]) -> None:
            xpassed = self.stats.get("xpassed", [])
            for rep in xpassed:
                verbose_word, verbose_markup = rep._get_verbose_word_with_markup(
                    self.config, {_color_for_type["warnings"]: True}
                )
                markup_word = self._tw.markup(verbose_word, **verbose_markup)
                nodeid = _get_node_id_with_markup(self._tw, self.config, rep)
                line = f"{markup_word} {nodeid}"
                reason = rep.wasxfail
                if reason:
                    line += " - " + str(reason)
                lines.append(line)

        def show_skipped_folded(lines: list[str]) -> None:
            skipped: list[CollectReport] = self.stats.get("skipped", [])
            fskips = _folded_skips(self.startpath, skipped) if skipped else []
            if not fskips:
                return
            verbose_word, verbose_markup = skipped[0]._get_verbose_word_with_markup(
                self.config, {_color_for_type["warnings"]: True}
            )
            markup_word = self._tw.markup(verbose_word, **verbose_markup)
            prefix = "Skipped: "
            for num, fspath, lineno, reason in fskips:
                if reason.startswith(prefix):
                    reason = reason[len(prefix) :]
                if lineno is not None:
                    lines.append(f"{markup_word} [{num}] {fspath}:{lineno}: {reason}")
                else:
                    lines.append(f"{markup_word} [{num}] {fspath}: {reason}")

        def show_skipped_unfolded(lines: list[str]) -> None:
            skipped: list[CollectReport] = self.stats.get("skipped", [])

            for rep in skipped:
                assert rep.longrepr is not None
                assert isinstance(rep.longrepr, tuple), (rep, rep.longrepr)
                assert len(rep.longrepr) == 3, (rep, rep.longrepr)

                verbose_word, verbose_markup = rep._get_verbose_word_with_markup(
                    self.config, {_color_for_type["warnings"]: True}
                )
                markup_word = self._tw.markup(verbose_word, **verbose_markup)
                nodeid = _get_node_id_with_markup(self._tw, self.config, rep)
                line = f"{markup_word} {nodeid}"
                reason = rep.longrepr[2]
                if reason:
                    line += " - " + str(reason)
                lines.append(line)

        def show_skipped(lines: list[str]) -> None:
            if self.foldskipped:
                show_skipped_folded(lines)
            else:
                show_skipped_unfolded(lines)

        REPORTCHAR_ACTIONS: Mapping[str, Callable[[list[str]], None]] = {
            "x": show_xfailed,
            "X": show_xpassed,
            "f": partial(show_simple, stat="failed"),
            "s": show_skipped,
            "p": partial(show_simple, stat="passed"),
            "E": partial(show_simple, stat="error"),
        }

        lines: list[str] = []
        for char in self.reportchars:
            action = REPORTCHAR_ACTIONS.get(char)
            if action:  # skipping e.g. "P" (passed with output) here.
                action(lines)

        if lines:
            self.write_sep("=", "short test summary info", cyan=True, bold=True)
            for line in lines:
                self.write_line(line)

    def _get_main_color(self) -> tuple[str, list[str]]:
        if self._main_color is None or self._known_types is None or self._is_last_item:
            self._set_main_color()
            assert self._main_color
            assert self._known_types
        return self._main_color, self._known_types

    def _determine_main_color(self, unknown_type_seen: bool) -> str:
        stats = self.stats
        if "failed" in stats or "error" in stats:
            main_color = "red"
        elif "warnings" in stats or "xpassed" in stats or unknown_type_seen:
            main_color = "yellow"
        elif "passed" in stats or not self._is_last_item:
            main_color = "green"
        else:
            main_color = "yellow"
        return main_color

    def _set_main_color(self) -> None:
        unknown_types: list[str] = []
        for found_type in self.stats:
            if found_type:  # setup/teardown reports have an empty key, ignore them
                if found_type not in KNOWN_TYPES and found_type not in unknown_types:
                    unknown_types.append(found_type)
        self._known_types = list(KNOWN_TYPES) + unknown_types
        self._main_color = self._determine_main_color(bool(unknown_types))

    def build_summary_stats_line(self) -> tuple[list[tuple[str, dict[str, bool]]], str]:
        """
        Build the parts used in the last summary stats line.

        The summary stats line is the line shown at the end, "=== 12 passed, 2 errors in Xs===".

        This function builds a list of the "parts" that make up for the text in that line, in
        the example above it would be::

            [
                ("12 passed", {"green": True}),
                ("2 errors", {"red": True}
            ]

        That last dict for each line is a "markup dictionary", used by TerminalWriter to
        color output.

        The final color of the line is also determined by this function, and is the second
        element of the returned tuple.
        """
        if self.config.getoption("collectonly"):
            return self._build_collect_only_summary_stats_line()
        else:
            return self._build_normal_summary_stats_line()

    def _get_reports_to_display(self, key: str) -> list[Any]:
        """Get test/collection reports for the given status key, such as `passed` or `error`."""
        reports = self.stats.get(key, [])
        return [x for x in reports if getattr(x, "count_towards_summary", True)]

    def _build_normal_summary_stats_line(
        self,
    ) -> tuple[list[tuple[str, dict[str, bool]]], str]:
        main_color, known_types = self._get_main_color()
        parts = []

        for key in known_types:
            reports = self._get_reports_to_display(key)
            if reports:
                count = len(reports)
                color = _color_for_type.get(key, _color_for_type_default)
                markup = {color: True, "bold": color == main_color}
                parts.append(("%d %s" % pluralize(count, key), markup))  # noqa: UP031

        if not parts:
            parts = [("no tests ran", {_color_for_type_default: True})]

        return parts, main_color

    def _build_collect_only_summary_stats_line(
        self,
    ) -> tuple[list[tuple[str, dict[str, bool]]], str]:
        deselected = len(self._get_reports_to_display("deselected"))
        errors = len(self._get_reports_to_display("error"))

        if self._numcollected == 0:
            parts = [("no tests collected", {"yellow": True})]
            main_color = "yellow"

        elif deselected == 0:
            main_color = "green"
            collected_output = "%d %s collected" % pluralize(self._numcollected, "test")  # noqa: UP031
            parts = [(collected_output, {main_color: True})]
        else:
            all_tests_were_deselected = self._numcollected == deselected
            if all_tests_were_deselected:
                main_color = "yellow"
                collected_output = f"no tests collected ({deselected} deselected)"
            else:
                main_color = "green"
                selected = self._numcollected - deselected
                collected_output = f"{selected}/{self._numcollected} tests collected ({deselected} deselected)"

            parts = [(collected_output, {main_color: True})]

        if errors:
            main_color = _color_for_type["error"]
            parts += [("%d %s" % pluralize(errors, "error"), {main_color: True})]  # noqa: UP031

        return parts, main_color


def _get_node_id_with_markup(tw: TerminalWriter, config: Config, rep: BaseReport):
    nodeid = config.cwd_relative_nodeid(rep.nodeid)
    path, *parts = nodeid.split("::")
    if parts:
        parts_markup = tw.markup("::".join(parts), bold=True)
        return path + "::" + parts_markup
    else:
        return path


def _format_trimmed(format: str, msg: str, available_width: int) -> str | None:
    """Format msg into format, ellipsizing it if doesn't fit in available_width.

    Returns None if even the ellipsis can't fit.
    """
    # Only use the first line.
    i = msg.find("\n")
    if i != -1:
        msg = msg[:i]

    ellipsis = "..."
    format_width = wcswidth(format.format(""))
    if format_width + len(ellipsis) > available_width:
        return None

    if format_width + wcswidth(msg) > available_width:
        available_width -= len(ellipsis)
        msg = msg[:available_width]
        while format_width + wcswidth(msg) > available_width:
            msg = msg[:-1]
        msg += ellipsis

    return format.format(msg)


def _get_line_with_reprcrash_message(
    config: Config, rep: BaseReport, tw: TerminalWriter, word_markup: dict[str, bool]
) -> str:
    """Get summary line for a report, trying to add reprcrash message."""
    verbose_word, verbose_markup = rep._get_verbose_word_with_markup(
        config, word_markup
    )
    word = tw.markup(verbose_word, **verbose_markup)
    node = _get_node_id_with_markup(tw, config, rep)

    line = f"{word} {node}"
    line_width = wcswidth(line)

    msg: str | None
    try:
        if isinstance(rep.longrepr, str):
            msg = rep.longrepr
        else:
            # Type ignored intentionally -- possible AttributeError expected.
            msg = rep.longrepr.reprcrash.message  # type: ignore[union-attr]
    except AttributeError:
        pass
    else:
        if (
            running_on_ci() or config.option.verbose >= 2
        ) and not config.option.force_short_summary:
            msg = f" - {msg}"
        else:
            available_width = tw.fullwidth - line_width
            msg = _format_trimmed(" - {}", msg, available_width)
        if msg is not None:
            line += msg

    return line


def _folded_skips(
    startpath: Path,
    skipped: Sequence[CollectReport],
) -> list[tuple[int, str, int | None, str]]:
    d: dict[tuple[str, int | None, str], list[CollectReport]] = {}
    for event in skipped:
        assert event.longrepr is not None
        assert isinstance(event.longrepr, tuple), (event, event.longrepr)
        assert len(event.longrepr) == 3, (event, event.longrepr)
        fspath, lineno, reason = event.longrepr
        # For consistency, report all fspaths in relative form.
        fspath = bestrelpath(startpath, Path(fspath))
        keywords = getattr(event, "keywords", {})
        # Folding reports with global pytestmark variable.
        # This is a workaround, because for now we cannot identify the scope of a skip marker
        # TODO: Revisit after marks scope would be fixed.
        if (
            event.when == "setup"
            and "skip" in keywords
            and "pytestmark" not in keywords
        ):
            key: tuple[str, int | None, str] = (fspath, None, reason)
        else:
            key = (fspath, lineno, reason)
        d.setdefault(key, []).append(event)
    values: list[tuple[int, str, int | None, str]] = []
    for key, events in d.items():
        values.append((len(events), *key))
    return values


_color_for_type = {
    "failed": "red",
    "error": "red",
    "warnings": "yellow",
    "passed": "green",
    "subtests passed": "green",
    "subtests failed": "red",
}
_color_for_type_default = "yellow"


def pluralize(count: int, noun: str) -> tuple[int, str]:
    # No need to pluralize words such as `failed` or `passed`.
    if noun not in ["error", "warnings", "test"]:
        return count, noun

    # The `warnings` key is plural. To avoid API breakage, we keep it that way but
    # set it to singular here so we can determine plurality in the same way as we do
    # for `error`.
    noun = noun.replace("warnings", "warning")

    return count, noun + "s" if count != 1 else noun


def _plugin_nameversions(plugininfo) -> list[str]:
    values: list[str] = []
    for plugin, dist in plugininfo:
        # Gets us name and version!
        name = f"{dist.project_name}-{dist.version}"
        # Questionable convenience, but it keeps things short.
        if name.startswith("pytest-"):
            name = name[7:]
        # We decided to print python package names they can have more than one plugin.
        if name not in values:
            values.append(name)
    return values


def format_session_duration(seconds: float) -> str:
    """Format the given seconds in a human readable manner to show in the final summary."""
    if seconds < 60:
        return f"{seconds:.2f}s"
    else:
        dt = datetime.timedelta(seconds=int(seconds))
        return f"{seconds:.2f}s ({dt})"


def format_node_duration(seconds: float) -> str:
    """Format the given seconds in a human readable manner to show in the test progress."""
    # The formatting is designed to be compact and readable, with at most 7 characters
    # for durations below 100 hours.
    if seconds < 0.00001:
        return f" {seconds * 1000000:.3f}us"
    if seconds < 0.0001:
        return f" {seconds * 1000000:.2f}us"
    if seconds < 0.001:
        return f" {seconds * 1000000:.1f}us"
    if seconds < 0.01:
        return f" {seconds * 1000:.3f}ms"
    if seconds < 0.1:
        return f" {seconds * 1000:.2f}ms"
    if seconds < 1:
        return f" {seconds * 1000:.1f}ms"
    if seconds < 60:
        return f" {seconds:.3f}s"
    if seconds < 3600:
        return f" {seconds // 60:.0f}m {seconds % 60:.0f}s"
    return f" {seconds // 3600:.0f}h {(seconds % 3600) // 60:.0f}m"


def _get_raw_skip_reason(report: TestReport) -> str:
    """Get the reason string of a skip/xfail/xpass test report.

    The string is just the part given by the user.
    """
    if hasattr(report, "wasxfail"):
        reason = report.wasxfail
        if reason.startswith("reason: "):
            reason = reason[len("reason: ") :]
        return reason
    else:
        assert report.skipped
        assert isinstance(report.longrepr, tuple)
        _, _, reason = report.longrepr
        if reason.startswith("Skipped: "):
            reason = reason[len("Skipped: ") :]
        elif reason == "Skipped":
            reason = ""
        return reason


class TerminalProgressPlugin:
    """Terminal progress reporting plugin using OSC 9;4 ANSI sequences.

    Emits OSC 9;4 sequences to indicate test progress to terminal
    tabs/windows/etc.

    Not all terminal emulators support this feature.

    Ref: https://conemu.github.io/en/AnsiEscapeCodes.html#ConEmu_specific_OSC
    """

    def __init__(self, tr: TerminalReporter) -> None:
        self._tr = tr
        self._session: Session | None = None
        self._has_failures = False

    def _emit_progress(
        self,
        state: Literal["remove", "normal", "error", "indeterminate", "paused"],
        progress: int | None = None,
    ) -> None:
        """Emit OSC 9;4 sequence for indicating progress to the terminal.

        :param state:
            Progress state to set.
        :param progress:
            Progress value 0-100. Required for "normal", optional for "error"
            and "paused", otherwise ignored.
        """
        assert progress is None or 0 <= progress <= 100

        # OSC 9;4 sequence: ESC ] 9 ; 4 ; state ; progress ST
        # ST can be ESC \ or BEL. ESC \ seems better supported.
        match state:
            case "remove":
                sequence = "\x1b]9;4;0;\x1b\\"
            case "normal":
                assert progress is not None
                sequence = f"\x1b]9;4;1;{progress}\x1b\\"
            case "error":
                if progress is not None:
                    sequence = f"\x1b]9;4;2;{progress}\x1b\\"
                else:
                    sequence = "\x1b]9;4;2;\x1b\\"
            case "indeterminate":
                sequence = "\x1b]9;4;3;\x1b\\"
            case "paused":
                if progress is not None:
                    sequence = f"\x1b]9;4;4;{progress}\x1b\\"
                else:
                    sequence = "\x1b]9;4;4;\x1b\\"

        self._tr.write_raw(sequence, flush=True)

    @hookimpl
    def pytest_sessionstart(self, session: Session) -> None:
        self._session = session
        # Show indeterminate progress during collection.
        self._emit_progress("indeterminate")

    @hookimpl
    def pytest_collection_finish(self) -> None:
        assert self._session is not None
        if self._session.testscollected > 0:
            # Switch from indeterminate to 0% progress.
            self._emit_progress("normal", 0)

    @hookimpl
    def pytest_runtest_logreport(self, report: TestReport) -> None:
        if report.failed:
            self._has_failures = True

        # Let's consider the "call" phase for progress.
        if report.when != "call":
            return

        # Calculate and emit progress.
        assert self._session is not None
        collected = self._session.testscollected
        if collected > 0:
            reported = self._tr.reported_progress
            progress = min(reported * 100 // collected, 100)
            self._emit_progress("error" if self._has_failures else "normal", progress)

    @hookimpl
    def pytest_sessionfinish(self) -> None:
        self._emit_progress("remove")
