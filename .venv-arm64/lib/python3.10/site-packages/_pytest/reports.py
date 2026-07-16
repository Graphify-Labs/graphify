# mypy: allow-untyped-defs
from __future__ import annotations

from collections.abc import Iterable
from collections.abc import Iterator
from collections.abc import Mapping
from collections.abc import Sequence
import dataclasses
from io import StringIO
import os
from pprint import pprint
import sys
from typing import Any
from typing import cast
from typing import final
from typing import Literal
from typing import NoReturn
from typing import TYPE_CHECKING

from _pytest._code.code import ExceptionChainRepr
from _pytest._code.code import ExceptionInfo
from _pytest._code.code import ExceptionRepr
from _pytest._code.code import ReprEntry
from _pytest._code.code import ReprEntryNative
from _pytest._code.code import ReprExceptionInfo
from _pytest._code.code import ReprFileLocation
from _pytest._code.code import ReprFuncArgs
from _pytest._code.code import ReprLocals
from _pytest._code.code import ReprTraceback
from _pytest._code.code import TerminalRepr
from _pytest._io import TerminalWriter
from _pytest.config import Config
from _pytest.nodes import Collector
from _pytest.nodes import Item
from _pytest.outcomes import fail
from _pytest.outcomes import skip


if sys.version_info < (3, 11):
    from exceptiongroup import BaseExceptionGroup


if TYPE_CHECKING:
    from typing_extensions import Self

    from _pytest.runner import CallInfo


def getworkerinfoline(node):
    try:
        return node._workerinfocache
    except AttributeError:
        d = node.workerinfo
        ver = "{}.{}.{}".format(*d["version_info"][:3])
        node._workerinfocache = s = "[{}] {} -- Python {} {}".format(
            d["id"], d["sysplatform"], ver, d["executable"]
        )
        return s


class BaseReport:
    when: str | None
    location: tuple[str, int | None, str] | None
    longrepr: (
        None | ExceptionInfo[BaseException] | tuple[str, int, str] | str | TerminalRepr
    )
    sections: list[tuple[str, str]]
    nodeid: str
    outcome: Literal["passed", "failed", "skipped"]

    def __init__(self, **kw: Any) -> None:
        self.__dict__.update(kw)

    if TYPE_CHECKING:
        # Can have arbitrary fields given to __init__().
        def __getattr__(self, key: str) -> Any: ...

    def toterminal(self, out: TerminalWriter) -> None:
        if hasattr(self, "node"):
            worker_info = getworkerinfoline(self.node)
            if worker_info:
                out.line(worker_info)

        longrepr = self.longrepr
        if longrepr is None:
            return

        if hasattr(longrepr, "toterminal"):
            longrepr_terminal = cast(TerminalRepr, longrepr)
            longrepr_terminal.toterminal(out)
        else:
            try:
                s = str(longrepr)
            except UnicodeEncodeError:
                s = "<unprintable longrepr>"
            out.line(s)

    def get_sections(self, prefix: str) -> Iterator[tuple[str, str]]:
        for name, content in self.sections:
            if name.startswith(prefix):
                yield prefix, content

    @property
    def longreprtext(self) -> str:
        """Read-only property that returns the full string representation of
        ``longrepr``.

        .. versionadded:: 3.0
        """
        file = StringIO()
        tw = TerminalWriter(file)
        tw.hasmarkup = False
        self.toterminal(tw)
        exc = file.getvalue()
        return exc.strip()

    @property
    def caplog(self) -> str:
        """Return captured log lines, if log capturing is enabled.

        .. versionadded:: 3.5
        """
        return "\n".join(
            content for (prefix, content) in self.get_sections("Captured log")
        )

    @property
    def capstdout(self) -> str:
        """Return captured text from stdout, if capturing is enabled.

        .. versionadded:: 3.0
        """
        return "".join(
            content for (prefix, content) in self.get_sections("Captured stdout")
        )

    @property
    def capstderr(self) -> str:
        """Return captured text from stderr, if capturing is enabled.

        .. versionadded:: 3.0
        """
        return "".join(
            content for (prefix, content) in self.get_sections("Captured stderr")
        )

    @property
    def passed(self) -> bool:
        """Whether the outcome is passed."""
        return self.outcome == "passed"

    @property
    def failed(self) -> bool:
        """Whether the outcome is failed."""
        return self.outcome == "failed"

    @property
    def skipped(self) -> bool:
        """Whether the outcome is skipped."""
        return self.outcome == "skipped"

    @property
    def fspath(self) -> str:
        """The path portion of the reported node, as a string."""
        return self.nodeid.split("::")[0]

    @property
    def count_towards_summary(self) -> bool:
        """**Experimental** Whether this report should be counted towards the
        totals shown at the end of the test session: "1 passed, 1 failure, etc".

        .. note::

            This function is considered **experimental**, so beware that it is subject to changes
            even in patch releases.
        """
        return True

    @property
    def head_line(self) -> str | None:
        """**Experimental** The head line shown with longrepr output for this
        report, more commonly during traceback representation during
        failures::

            ________ Test.foo ________


        In the example above, the head_line is "Test.foo".

        .. note::

            This function is considered **experimental**, so beware that it is subject to changes
            even in patch releases.
        """
        if self.location is not None:
            _fspath, _lineno, domain = self.location
            return domain
        return None

    def _get_verbose_word_with_markup(
        self, config: Config, default_markup: Mapping[str, bool]
    ) -> tuple[str, Mapping[str, bool]]:
        _category, _short, verbose = config.hook.pytest_report_teststatus(
            report=self, config=config
        )

        if isinstance(verbose, str):
            return verbose, default_markup

        if isinstance(verbose, Sequence) and len(verbose) == 2:
            word, markup = verbose
            if isinstance(word, str) and isinstance(markup, Mapping):
                return word, markup

        fail(  # pragma: no cover
            "pytest_report_teststatus() hook (from a plugin) returned "
            f"an invalid verbose value: {verbose!r}.\nExpected either a string "
            "or a tuple of (word, markup)."
        )

    def _to_json(self) -> dict[str, Any]:
        """Return the contents of this report as a dict of builtin entries,
        suitable for serialization.

        This was originally the serialize_report() function from xdist (ca03269).

        Experimental method.
        """
        return _report_to_json(self)

    @classmethod
    def _from_json(cls, reportdict: dict[str, object]) -> Self:
        """Create either a TestReport or CollectReport, depending on the calling class.

        It is the callers responsibility to know which class to pass here.

        This was originally the serialize_report() function from xdist (ca03269).

        Experimental method.
        """
        kwargs = _report_kwargs_from_json(reportdict)
        return cls(**kwargs)


def _report_unserialization_failure(
    type_name: str, report_class: type[BaseReport], reportdict
) -> NoReturn:
    url = "https://github.com/pytest-dev/pytest/issues"
    stream = StringIO()
    pprint("-" * 100, stream=stream)
    pprint(f"INTERNALERROR: Unknown entry type returned: {type_name}", stream=stream)
    pprint(f"report_name: {report_class}", stream=stream)
    pprint(reportdict, stream=stream)
    pprint(f"Please report this bug at {url}", stream=stream)
    pprint("-" * 100, stream=stream)
    raise RuntimeError(stream.getvalue())


def _format_failed_longrepr(
    item: Item, call: CallInfo[None], excinfo: ExceptionInfo[BaseException]
):
    if call.when == "call":
        longrepr = item.repr_failure(excinfo)
    else:
        # Exception in setup or teardown.
        longrepr = item._repr_failure_py(
            excinfo, style=item.config.getoption("tbstyle", "auto")
        )
    return longrepr


def _format_exception_group_all_skipped_longrepr(
    item: Item,
    excinfo: ExceptionInfo[BaseExceptionGroup[BaseException | BaseExceptionGroup]],
) -> tuple[str, int, str]:
    r = excinfo._getreprcrash()
    assert r is not None, (
        "There should always be a traceback entry for skipping a test."
    )
    if all(
        getattr(skip, "_use_item_location", False) for skip in excinfo.value.exceptions
    ):
        path, line = item.reportinfo()[:2]
        assert line is not None
        loc = (os.fspath(path), line + 1)
        default_msg = "skipped"
    else:
        loc = (str(r.path), r.lineno)
        default_msg = r.message

    # Get all unique skip messages.
    msgs: list[str] = []
    for exception in excinfo.value.exceptions:
        m = getattr(exception, "msg", None) or (
            exception.args[0] if exception.args else None
        )
        if m and m not in msgs:
            msgs.append(m)

    reason = "; ".join(msgs) if msgs else default_msg
    longrepr = (*loc, reason)
    return longrepr


class TestReport(BaseReport):
    """Basic test report object (also used for setup and teardown calls if
    they fail).

    Reports can contain arbitrary extra attributes.
    """

    __test__ = False

    # Defined by skipping plugin.
    # xfail reason if xfailed, otherwise not defined. Use hasattr to distinguish.
    wasxfail: str

    def __init__(
        self,
        nodeid: str,
        location: tuple[str, int | None, str],
        keywords: Mapping[str, Any],
        outcome: Literal["passed", "failed", "skipped"],
        longrepr: None
        | ExceptionInfo[BaseException]
        | tuple[str, int, str]
        | str
        | TerminalRepr,
        when: Literal["setup", "call", "teardown"],
        sections: Iterable[tuple[str, str]] = (),
        duration: float = 0,
        start: float = 0,
        stop: float = 0,
        user_properties: Iterable[tuple[str, object]] | None = None,
        **extra,
    ) -> None:
        #: Normalized collection nodeid.
        self.nodeid = nodeid

        #: A (filesystempath, lineno, domaininfo) tuple indicating the
        #: actual location of a test item - it might be different from the
        #: collected one e.g. if a method is inherited from a different module.
        #: The filesystempath may be relative to ``config.rootdir``.
        #: The line number is 0-based.
        self.location: tuple[str, int | None, str] = location

        #: A name -> value dictionary containing all keywords and
        #: markers associated with a test invocation.
        self.keywords: Mapping[str, Any] = keywords

        #: Test outcome, always one of "passed", "failed", "skipped".
        self.outcome = outcome

        #: None or a failure representation.
        self.longrepr = longrepr

        #: One of 'setup', 'call', 'teardown' to indicate runtest phase.
        self.when: Literal["setup", "call", "teardown"] = when

        #: User properties is a list of tuples (name, value) that holds user
        #: defined properties of the test.
        self.user_properties = list(user_properties or [])

        #: Tuples of str ``(heading, content)`` with extra information
        #: for the test report. Used by pytest to add text captured
        #: from ``stdout``, ``stderr``, and intercepted logging events. May
        #: be used by other plugins to add arbitrary information to reports.
        self.sections = list(sections)

        #: Time it took to run just the test.
        self.duration: float = duration

        #: The system time when the call started, in seconds since the epoch.
        self.start: float = start
        #: The system time when the call ended, in seconds since the epoch.
        self.stop: float = stop

        self.__dict__.update(extra)

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.nodeid!r} when={self.when!r} outcome={self.outcome!r}>"

    @classmethod
    def from_item_and_call(cls, item: Item, call: CallInfo[None]) -> TestReport:
        """Create and fill a TestReport with standard item and call info.

        :param item: The item.
        :param call: The call info.
        """
        when = call.when
        # Remove "collect" from the Literal type -- only for collection calls.
        assert when != "collect"
        duration = call.duration
        start = call.start
        stop = call.stop
        keywords = {x: 1 for x in item.keywords}
        excinfo = call.excinfo
        sections = []
        if not call.excinfo:
            outcome: Literal["passed", "failed", "skipped"] = "passed"
            longrepr: (
                None
                | ExceptionInfo[BaseException]
                | tuple[str, int, str]
                | str
                | TerminalRepr
            ) = None
        else:
            if not isinstance(excinfo, ExceptionInfo):
                outcome = "failed"
                longrepr = excinfo
            elif isinstance(excinfo.value, skip.Exception):
                outcome = "skipped"
                r = excinfo._getreprcrash()
                assert r is not None, (
                    "There should always be a traceback entry for skipping a test."
                )
                if excinfo.value._use_item_location:
                    path, line = item.reportinfo()[:2]
                    assert line is not None
                    longrepr = (os.fspath(path), line + 1, r.message)
                else:
                    longrepr = (str(r.path), r.lineno, r.message)
            elif isinstance(excinfo.value, BaseExceptionGroup) and (
                excinfo.value.split(skip.Exception)[1] is None
            ):
                # All exceptions in the group are skip exceptions.
                outcome = "skipped"
                excinfo = cast(
                    ExceptionInfo[
                        BaseExceptionGroup[BaseException | BaseExceptionGroup]
                    ],
                    excinfo,
                )
                longrepr = _format_exception_group_all_skipped_longrepr(item, excinfo)
            else:
                outcome = "failed"
                longrepr = _format_failed_longrepr(item, call, excinfo)
        for rwhen, key, content in item._report_sections:
            sections.append((f"Captured {key} {rwhen}", content))
        return cls(
            item.nodeid,
            item.location,
            keywords,
            outcome,
            longrepr,
            when,
            sections,
            duration,
            start,
            stop,
            user_properties=item.user_properties,
        )


@final
class CollectReport(BaseReport):
    """Collection report object.

    Reports can contain arbitrary extra attributes.
    """

    when = "collect"

    def __init__(
        self,
        nodeid: str,
        outcome: Literal["passed", "failed", "skipped"],
        longrepr: None
        | ExceptionInfo[BaseException]
        | tuple[str, int, str]
        | str
        | TerminalRepr,
        result: list[Item | Collector] | None,
        sections: Iterable[tuple[str, str]] = (),
        **extra,
    ) -> None:
        #: Normalized collection nodeid.
        self.nodeid = nodeid

        #: Test outcome, always one of "passed", "failed", "skipped".
        self.outcome = outcome

        #: None or a failure representation.
        self.longrepr = longrepr

        #: The collected items and collection nodes.
        self.result = result or []

        #: Tuples of str ``(heading, content)`` with extra information
        #: for the test report. Used by pytest to add text captured
        #: from ``stdout``, ``stderr``, and intercepted logging events. May
        #: be used by other plugins to add arbitrary information to reports.
        self.sections = list(sections)

        self.__dict__.update(extra)

    @property
    def location(  # type:ignore[override]
        self,
    ) -> tuple[str, int | None, str] | None:
        return (self.fspath, None, self.fspath)

    def __repr__(self) -> str:
        return f"<CollectReport {self.nodeid!r} lenresult={len(self.result)} outcome={self.outcome!r}>"


class CollectErrorRepr(TerminalRepr):
    def __init__(self, msg: str) -> None:
        self.longrepr = msg

    def toterminal(self, out: TerminalWriter) -> None:
        out.line(self.longrepr, red=True)


def pytest_report_to_serializable(
    report: CollectReport | TestReport,
) -> dict[str, Any] | None:
    if isinstance(report, TestReport | CollectReport):
        data = report._to_json()
        data["$report_type"] = report.__class__.__name__
        return data
    # TODO: Check if this is actually reachable.
    return None  # type: ignore[unreachable]


def pytest_report_from_serializable(
    data: dict[str, Any],
) -> CollectReport | TestReport | None:
    if "$report_type" in data:
        if data["$report_type"] == "TestReport":
            return TestReport._from_json(data)
        elif data["$report_type"] == "CollectReport":
            return CollectReport._from_json(data)
        assert False, "Unknown report_type unserialize data: {}".format(
            data["$report_type"]
        )
    return None


def _report_to_json(report: BaseReport) -> dict[str, Any]:
    """Return the contents of this report as a dict of builtin entries,
    suitable for serialization.

    This was originally the serialize_report() function from xdist (ca03269).
    """

    def serialize_repr_entry(
        entry: ReprEntry | ReprEntryNative,
    ) -> dict[str, Any]:
        data = dataclasses.asdict(entry)
        for key, value in data.items():
            if hasattr(value, "__dict__"):
                data[key] = dataclasses.asdict(value)
        entry_data = {"type": type(entry).__name__, "data": data}
        return entry_data

    def serialize_repr_traceback(reprtraceback: ReprTraceback) -> dict[str, Any]:
        result = dataclasses.asdict(reprtraceback)
        result["reprentries"] = [
            serialize_repr_entry(x) for x in reprtraceback.reprentries
        ]
        return result

    def serialize_repr_crash(
        reprcrash: ReprFileLocation | None,
    ) -> dict[str, Any] | None:
        if reprcrash is not None:
            return dataclasses.asdict(reprcrash)
        else:
            return None

    def serialize_exception_longrepr(rep: BaseReport) -> dict[str, Any]:
        assert rep.longrepr is not None
        # TODO: Investigate whether the duck typing is really necessary here.
        longrepr = cast(ExceptionRepr, rep.longrepr)
        result: dict[str, Any] = {
            "reprcrash": serialize_repr_crash(longrepr.reprcrash),
            "reprtraceback": serialize_repr_traceback(longrepr.reprtraceback),
            "sections": longrepr.sections,
        }
        if isinstance(longrepr, ExceptionChainRepr):
            result["chain"] = []
            for repr_traceback, repr_crash, description in longrepr.chain:
                result["chain"].append(
                    (
                        serialize_repr_traceback(repr_traceback),
                        serialize_repr_crash(repr_crash),
                        description,
                    )
                )
        else:
            result["chain"] = None
        return result

    d = report.__dict__.copy()
    if hasattr(report.longrepr, "toterminal"):
        if hasattr(report.longrepr, "reprtraceback") and hasattr(
            report.longrepr, "reprcrash"
        ):
            d["longrepr"] = serialize_exception_longrepr(report)
        else:
            d["longrepr"] = str(report.longrepr)
    else:
        d["longrepr"] = report.longrepr
    for name in d:
        if isinstance(d[name], os.PathLike):
            d[name] = os.fspath(d[name])
        elif name == "result":
            d[name] = None  # for now
    return d


def _report_kwargs_from_json(reportdict: dict[str, Any]) -> dict[str, Any]:
    """Return **kwargs that can be used to construct a TestReport or
    CollectReport instance.

    This was originally the serialize_report() function from xdist (ca03269).
    """

    def deserialize_repr_entry(entry_data):
        data = entry_data["data"]
        entry_type = entry_data["type"]
        if entry_type == "ReprEntry":
            reprfuncargs = None
            reprfileloc = None
            reprlocals = None
            if data["reprfuncargs"]:
                reprfuncargs = ReprFuncArgs(**data["reprfuncargs"])
            if data["reprfileloc"]:
                reprfileloc = ReprFileLocation(**data["reprfileloc"])
            if data["reprlocals"]:
                reprlocals = ReprLocals(data["reprlocals"]["lines"])

            reprentry: ReprEntry | ReprEntryNative = ReprEntry(
                lines=data["lines"],
                reprfuncargs=reprfuncargs,
                reprlocals=reprlocals,
                reprfileloc=reprfileloc,
                style=data["style"],
            )
        elif entry_type == "ReprEntryNative":
            reprentry = ReprEntryNative(data["lines"])
        else:
            _report_unserialization_failure(entry_type, TestReport, reportdict)
        return reprentry

    def deserialize_repr_traceback(repr_traceback_dict):
        repr_traceback_dict["reprentries"] = [
            deserialize_repr_entry(x) for x in repr_traceback_dict["reprentries"]
        ]
        return ReprTraceback(**repr_traceback_dict)

    def deserialize_repr_crash(repr_crash_dict: dict[str, Any] | None):
        if repr_crash_dict is not None:
            return ReprFileLocation(**repr_crash_dict)
        else:
            return None

    if (
        reportdict["longrepr"]
        and "reprcrash" in reportdict["longrepr"]
        and "reprtraceback" in reportdict["longrepr"]
    ):
        reprtraceback = deserialize_repr_traceback(
            reportdict["longrepr"]["reprtraceback"]
        )
        reprcrash = deserialize_repr_crash(reportdict["longrepr"]["reprcrash"])
        if reportdict["longrepr"]["chain"]:
            chain = []
            for repr_traceback_data, repr_crash_data, description in reportdict[
                "longrepr"
            ]["chain"]:
                chain.append(
                    (
                        deserialize_repr_traceback(repr_traceback_data),
                        deserialize_repr_crash(repr_crash_data),
                        description,
                    )
                )
            exception_info: ExceptionChainRepr | ReprExceptionInfo = ExceptionChainRepr(
                chain
            )
        else:
            exception_info = ReprExceptionInfo(
                reprtraceback=reprtraceback,
                reprcrash=reprcrash,
            )

        for section in reportdict["longrepr"]["sections"]:
            exception_info.addsection(*section)
        reportdict["longrepr"] = exception_info

    return reportdict
