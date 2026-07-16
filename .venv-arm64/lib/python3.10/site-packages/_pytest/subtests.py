"""Builtin plugin that adds subtests support."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from collections.abc import Iterator
from collections.abc import Mapping
from contextlib import AbstractContextManager
from contextlib import contextmanager
from contextlib import ExitStack
from contextlib import nullcontext
import dataclasses
import time
from types import TracebackType
from typing import Any
from typing import TYPE_CHECKING

import pluggy

from _pytest._code import ExceptionInfo
from _pytest._io.saferepr import saferepr
from _pytest.capture import CaptureFixture
from _pytest.capture import FDCapture
from _pytest.capture import SysCapture
from _pytest.config import Config
from _pytest.config import hookimpl
from _pytest.config.argparsing import Parser
from _pytest.deprecated import check_ispytest
from _pytest.fixtures import fixture
from _pytest.fixtures import SubRequest
from _pytest.logging import catching_logs
from _pytest.logging import LogCaptureHandler
from _pytest.logging import LoggingPlugin
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from _pytest.runner import check_interactive_exception
from _pytest.runner import get_reraise_exceptions
from _pytest.stash import StashKey


if TYPE_CHECKING:
    from typing_extensions import Self


def pytest_addoption(parser: Parser) -> None:
    Config._add_verbosity_ini(
        parser,
        Config.VERBOSITY_SUBTESTS,
        help=(
            "Specify verbosity level for subtests. "
            "Higher levels will generate output for passed subtests. Failed subtests are always reported."
        ),
    )


@dataclasses.dataclass(frozen=True, slots=True, kw_only=True)
class SubtestContext:
    """The values passed to Subtests.test() that are included in the test report."""

    msg: str | None
    kwargs: Mapping[str, Any]

    def __post_init__(self) -> None:
        # Brute-force the returned kwargs dict to be JSON serializable (pytest-dev/pytest-xdist#1273).
        object.__setattr__(
            self, "kwargs", {k: saferepr(v) for (k, v) in self.kwargs.items()}
        )

    def _to_json(self) -> dict[str, Any]:
        result = dataclasses.asdict(self)
        return result

    @classmethod
    def _from_json(cls, d: dict[str, Any]) -> Self:
        return cls(msg=d["msg"], kwargs=d["kwargs"])


@dataclasses.dataclass(init=False)
class SubtestReport(TestReport):
    context: SubtestContext

    @property
    def head_line(self) -> str:
        _, _, domain = self.location
        return f"{domain} {self._sub_test_description()}"

    def _sub_test_description(self) -> str:
        parts = []
        if self.context.msg is not None:
            parts.append(f"[{self.context.msg}]")
        if self.context.kwargs:
            params_desc = ", ".join(
                f"{k}={v}" for (k, v) in self.context.kwargs.items()
            )
            parts.append(f"({params_desc})")
        return " ".join(parts) or "(<subtest>)"

    def _to_json(self) -> dict[str, Any]:
        data = super()._to_json()
        del data["context"]
        data["_report_type"] = "SubTestReport"
        data["_subtest.context"] = self.context._to_json()
        return data

    @classmethod
    def _from_json(cls, reportdict: dict[str, Any]) -> SubtestReport:
        report = super()._from_json(reportdict)
        report.context = SubtestContext._from_json(reportdict["_subtest.context"])
        return report

    @classmethod
    def _new(
        cls,
        test_report: TestReport,
        context: SubtestContext,
        captured_output: Captured | None,
        captured_logs: CapturedLogs | None,
    ) -> Self:
        result = super()._from_json(test_report._to_json())
        result.context = context

        if captured_output:
            if captured_output.out:
                result.sections.append(("Captured stdout call", captured_output.out))
            if captured_output.err:
                result.sections.append(("Captured stderr call", captured_output.err))

        if captured_logs and (log := captured_logs.handler.stream.getvalue()):
            result.sections.append(("Captured log call", log))

        return result


@fixture
def subtests(request: SubRequest) -> Subtests:
    """Provides subtests functionality."""
    capmam = request.node.config.pluginmanager.get_plugin("capturemanager")
    suspend_capture_ctx = (
        capmam.global_and_fixture_disabled if capmam is not None else nullcontext
    )
    return Subtests(request.node.ihook, suspend_capture_ctx, request, _ispytest=True)


class Subtests:
    """Subtests fixture, enables declaring subtests inside test functions via the :meth:`test` method."""

    def __init__(
        self,
        ihook: pluggy.HookRelay,
        suspend_capture_ctx: Callable[[], AbstractContextManager[None]],
        request: SubRequest,
        *,
        _ispytest: bool = False,
    ) -> None:
        check_ispytest(_ispytest)
        self._ihook = ihook
        self._suspend_capture_ctx = suspend_capture_ctx
        self._request = request

    def test(
        self,
        msg: str | None = None,
        **kwargs: Any,
    ) -> _SubTestContextManager:
        """
        Context manager for subtests, capturing exceptions raised inside the subtest scope and
        reporting assertion failures and errors individually.

        Usage
        -----

        .. code-block:: python

            def test(subtests):
                for i in range(5):
                    with subtests.test("custom message", i=i):
                        assert i % 2 == 0

        :param msg:
            If given, the message will be shown in the test report in case of subtest failure.

        :param kwargs:
            Arbitrary values that are also added to the subtest report.
        """
        return _SubTestContextManager(
            self._ihook,
            msg,
            kwargs,
            request=self._request,
            suspend_capture_ctx=self._suspend_capture_ctx,
            config=self._request.config,
        )


@dataclasses.dataclass
class _SubTestContextManager:
    """
    Context manager for subtests, capturing exceptions raised inside the subtest scope and handling
    them through the pytest machinery.
    """

    # Note: initially the logic for this context manager was implemented directly
    # in Subtests.test() as a @contextmanager, however, it is not possible to control the output fully when
    # exiting from it due to an exception when in `--exitfirst` mode, so this was refactored into an
    # explicit context manager class (pytest-dev/pytest-subtests#134).

    ihook: pluggy.HookRelay
    msg: str | None
    kwargs: dict[str, Any]
    suspend_capture_ctx: Callable[[], AbstractContextManager[None]]
    request: SubRequest
    config: Config

    def __enter__(self) -> None:
        __tracebackhide__ = True

        self._start = time.time()
        self._precise_start = time.perf_counter()
        self._exc_info = None

        self._exit_stack = ExitStack()
        self._captured_output = self._exit_stack.enter_context(
            capturing_output(self.request)
        )
        self._captured_logs = self._exit_stack.enter_context(
            capturing_logs(self.request)
        )

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> bool:
        __tracebackhide__ = True
        if exc_val is not None:
            exc_info = ExceptionInfo.from_exception(exc_val)
        else:
            exc_info = None

        self._exit_stack.close()

        precise_stop = time.perf_counter()
        duration = precise_stop - self._precise_start
        stop = time.time()

        call_info = CallInfo[None](
            None,
            exc_info,
            start=self._start,
            stop=stop,
            duration=duration,
            when="call",
            _ispytest=True,
        )
        report = self.ihook.pytest_runtest_makereport(
            item=self.request.node, call=call_info
        )
        sub_report = SubtestReport._new(
            report,
            SubtestContext(msg=self.msg, kwargs=self.kwargs),
            captured_output=self._captured_output,
            captured_logs=self._captured_logs,
        )

        if sub_report.failed:
            failed_subtests = self.config.stash[failed_subtests_key]
            failed_subtests[self.request.node.nodeid] += 1

        with self.suspend_capture_ctx():
            self.ihook.pytest_runtest_logreport(report=sub_report)

        if check_interactive_exception(call_info, sub_report):
            self.ihook.pytest_exception_interact(
                node=self.request.node, call=call_info, report=sub_report
            )

        if exc_val is not None:
            if isinstance(exc_val, get_reraise_exceptions(self.config)):
                return False
            if self.request.session.shouldfail:
                return False
        return True


@contextmanager
def capturing_output(request: SubRequest) -> Iterator[Captured]:
    option = request.config.getoption("capture", None)

    capman = request.config.pluginmanager.getplugin("capturemanager")
    if getattr(capman, "_capture_fixture", None):
        # capsys or capfd are active, subtest should not capture.
        fixture = None
    elif option == "sys":
        fixture = CaptureFixture(SysCapture, request, _ispytest=True)
    elif option == "fd":
        fixture = CaptureFixture(FDCapture, request, _ispytest=True)
    else:
        fixture = None

    if fixture is not None:
        fixture._start()

    captured = Captured()
    try:
        yield captured
    finally:
        if fixture is not None:
            out, err = fixture.readouterr()
            fixture.close()
            captured.out = out
            captured.err = err


@contextmanager
def capturing_logs(
    request: SubRequest,
) -> Iterator[CapturedLogs | None]:
    logging_plugin: LoggingPlugin | None = request.config.pluginmanager.getplugin(
        "logging-plugin"
    )
    if logging_plugin is None:
        yield None
    else:
        handler = LogCaptureHandler()
        handler.setFormatter(logging_plugin.formatter)

        captured_logs = CapturedLogs(handler)
        with catching_logs(handler, level=logging_plugin.log_level):
            yield captured_logs


@dataclasses.dataclass
class Captured:
    out: str = ""
    err: str = ""


@dataclasses.dataclass
class CapturedLogs:
    handler: LogCaptureHandler


def pytest_report_to_serializable(report: TestReport) -> dict[str, Any] | None:
    if isinstance(report, SubtestReport):
        return report._to_json()
    return None


def pytest_report_from_serializable(data: dict[str, Any]) -> SubtestReport | None:
    if data.get("_report_type") == "SubTestReport":
        return SubtestReport._from_json(data)
    return None


# Dict of nodeid -> number of failed subtests.
# Used to fail top-level tests that passed but contain failed subtests.
failed_subtests_key = StashKey[defaultdict[str, int]]()


def pytest_configure(config: Config) -> None:
    config.stash[failed_subtests_key] = defaultdict(int)


@hookimpl(tryfirst=True)
def pytest_report_teststatus(
    report: TestReport,
    config: Config,
) -> tuple[str, str, str | Mapping[str, bool]] | None:
    if report.when != "call":
        return None

    quiet = config.get_verbosity(Config.VERBOSITY_SUBTESTS) == 0
    if isinstance(report, SubtestReport):
        outcome = report.outcome
        description = report._sub_test_description()

        if hasattr(report, "wasxfail"):
            if quiet:
                return "", "", ""
            elif outcome == "skipped":
                category = "xfailed"
                short = "y"  # x letter is used for regular xfail, y for subtest xfail
                status = "SUBXFAIL"
            # outcome == "passed" in an xfail is only possible via a @pytest.mark.xfail mark, which
            # is not applicable to a subtest, which only handles pytest.xfail().
            else:  # pragma: no cover
                # This should not normally happen, unless some plugin is setting wasxfail without
                # the correct outcome. Pytest expects the call outcome to be either skipped or
                # passed in case of xfail.
                # Let's pass this report to the next hook.
                return None
            return category, short, f"{status}{description}"

        if report.failed:
            return outcome, "u", f"SUBFAILED{description}"
        else:
            if report.passed:
                if quiet:
                    return "", "", ""
                else:
                    return f"subtests {outcome}", "u", f"SUBPASSED{description}"
            elif report.skipped:
                if quiet:
                    return "", "", ""
                else:
                    return outcome, "-", f"SUBSKIPPED{description}"

    else:
        failed_subtests_count = config.stash[failed_subtests_key][report.nodeid]
        # Top-level test, fail if it contains failed subtests and it has passed.
        if report.passed and failed_subtests_count > 0:
            report.outcome = "failed"
            suffix = "s" if failed_subtests_count > 1 else ""
            report.longrepr = f"contains {failed_subtests_count} failed subtest{suffix}"

    return None
