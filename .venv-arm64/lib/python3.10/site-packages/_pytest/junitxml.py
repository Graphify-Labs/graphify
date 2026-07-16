# mypy: allow-untyped-defs
"""Report test results in JUnit-XML format, for use with Jenkins and build
integration servers.

Based on initial code from Ross Lawley.

Output conforms to
https://github.com/jenkinsci/xunit-plugin/blob/master/src/main/resources/org/jenkinsci/plugins/xunit/types/model/xsd/junit-10.xsd
"""

from __future__ import annotations

from collections.abc import Callable
import functools
import os
import platform
import re
import xml.etree.ElementTree as ET

from _pytest import nodes
from _pytest import timing
from _pytest._code.code import ExceptionRepr
from _pytest._code.code import ReprFileLocation
from _pytest.config import Config
from _pytest.config import filename_arg
from _pytest.config.argparsing import Parser
from _pytest.fixtures import FixtureRequest
from _pytest.reports import TestReport
from _pytest.stash import StashKey
from _pytest.terminal import TerminalReporter
import pytest


xml_key = StashKey["LogXML"]()


def bin_xml_escape(arg: object) -> str:
    r"""Visually escape invalid XML characters.

    For example, transforms
        'hello\aworld\b'
    into
        'hello#x07world#x08'
    Note that the #xABs are *not* XML escapes - missing the ampersand &#xAB.
    The idea is to escape visually for the user rather than for XML itself.
    """

    def repl(matchobj: re.Match[str]) -> str:
        i = ord(matchobj.group())
        if i <= 0xFF:
            return f"#x{i:02X}"
        else:
            return f"#x{i:04X}"

    # The spec range of valid chars is:
    # Char ::= #x9 | #xA | #xD | [#x20-#xD7FF] | [#xE000-#xFFFD] | [#x10000-#x10FFFF]
    # For an unknown(?) reason, we disallow #x7F (DEL) as well.
    illegal_xml_re = "[^\u0009\u000a\u000d\u0020-\u007e\u0080-\ud7ff\ue000-\ufffd\U00010000-\U0010ffff]"
    return re.sub(illegal_xml_re, repl, str(arg))


def merge_family(left, right) -> None:
    result = {}
    for kl, vl in left.items():
        for kr, vr in right.items():
            if not isinstance(vl, list):
                raise TypeError(type(vl))
            result[kl] = vl + vr
    left.update(result)


families = {  # pylint: disable=dict-init-mutate
    "_base": {"testcase": ["classname", "name"]},
    "_base_legacy": {"testcase": ["file", "line", "url"]},
}
# xUnit 1.x inherits legacy attributes.
families["xunit1"] = families["_base"].copy()
merge_family(families["xunit1"], families["_base_legacy"])

# xUnit 2.x uses strict base attributes.
families["xunit2"] = families["_base"]


class _NodeReporter:
    def __init__(self, nodeid: str | TestReport, xml: LogXML) -> None:
        self.id = nodeid
        self.xml = xml
        self.add_stats = self.xml.add_stats
        self.family = self.xml.family
        self.duration = 0.0
        self.properties: list[tuple[str, str]] = []
        self.nodes: list[ET.Element] = []
        self.attrs: dict[str, str] = {}

    def append(self, node: ET.Element) -> None:
        self.xml.add_stats(node.tag)
        self.nodes.append(node)

    def add_property(self, name: str, value: object) -> None:
        self.properties.append((str(name), bin_xml_escape(value)))

    def add_attribute(self, name: str, value: object) -> None:
        self.attrs[str(name)] = bin_xml_escape(value)

    def make_properties_node(self) -> ET.Element | None:
        """Return a Junit node containing custom properties, if any."""
        if self.properties:
            properties = ET.Element("properties")
            for name, value in self.properties:
                properties.append(ET.Element("property", name=name, value=value))
            return properties
        return None

    def record_testreport(self, testreport: TestReport) -> None:
        names = mangle_test_address(testreport.nodeid)
        existing_attrs = self.attrs
        classnames = names[:-1]
        if self.xml.prefix:
            classnames.insert(0, self.xml.prefix)
        attrs: dict[str, str] = {
            "classname": ".".join(classnames),
            "name": bin_xml_escape(names[-1]),
            "file": testreport.location[0],
        }
        if testreport.location[1] is not None:
            attrs["line"] = str(testreport.location[1])
        if hasattr(testreport, "url"):
            attrs["url"] = testreport.url
        self.attrs = attrs
        self.attrs.update(existing_attrs)  # Restore any user-defined attributes.

        # Preserve legacy testcase behavior.
        if self.family == "xunit1":
            return

        # Filter out attributes not permitted by this test family.
        # Including custom attributes because they are not valid here.
        temp_attrs = {}
        for key in self.attrs:
            if key in families[self.family]["testcase"]:
                temp_attrs[key] = self.attrs[key]
        self.attrs = temp_attrs

    def to_xml(self) -> ET.Element:
        testcase = ET.Element("testcase", self.attrs, time=f"{self.duration:.3f}")
        properties = self.make_properties_node()
        if properties is not None:
            testcase.append(properties)
        testcase.extend(self.nodes)
        return testcase

    def _add_simple(self, tag: str, message: str, data: str | None = None) -> None:
        node = ET.Element(tag, message=message)
        node.text = bin_xml_escape(data)
        self.append(node)

    def write_captured_output(self, report: TestReport) -> None:
        if not self.xml.log_passing_tests and report.passed:
            return

        content_out = report.capstdout
        content_log = report.caplog
        content_err = report.capstderr
        if self.xml.logging == "no":
            return
        content_all = ""
        if self.xml.logging in ["log", "all"]:
            content_all = self._prepare_content(content_log, " Captured Log ")
        if self.xml.logging in ["system-out", "out-err", "all"]:
            content_all += self._prepare_content(content_out, " Captured Out ")
            self._write_content(report, content_all, "system-out")
            content_all = ""
        if self.xml.logging in ["system-err", "out-err", "all"]:
            content_all += self._prepare_content(content_err, " Captured Err ")
            self._write_content(report, content_all, "system-err")
            content_all = ""
        if content_all:
            self._write_content(report, content_all, "system-out")

    def _prepare_content(self, content: str, header: str) -> str:
        return "\n".join([header.center(80, "-"), content, ""])

    def _write_content(self, report: TestReport, content: str, jheader: str) -> None:
        tag = ET.Element(jheader)
        tag.text = bin_xml_escape(content)
        self.append(tag)

    def append_pass(self, report: TestReport) -> None:
        self.add_stats("passed")

    def append_failure(self, report: TestReport) -> None:
        # msg = str(report.longrepr.reprtraceback.extraline)
        if hasattr(report, "wasxfail"):
            self._add_simple("skipped", "xfail-marked test passes unexpectedly")
        else:
            assert report.longrepr is not None
            reprcrash: ReprFileLocation | None = getattr(
                report.longrepr, "reprcrash", None
            )
            if reprcrash is not None:
                message = reprcrash.message
            else:
                message = str(report.longrepr)
            message = bin_xml_escape(message)
            self._add_simple("failure", message, str(report.longrepr))

    def append_collect_error(self, report: TestReport) -> None:
        # msg = str(report.longrepr.reprtraceback.extraline)
        assert report.longrepr is not None
        self._add_simple("error", "collection failure", str(report.longrepr))

    def append_collect_skipped(self, report: TestReport) -> None:
        self._add_simple("skipped", "collection skipped", str(report.longrepr))

    def append_error(self, report: TestReport) -> None:
        assert report.longrepr is not None
        reprcrash: ReprFileLocation | None = getattr(report.longrepr, "reprcrash", None)
        if reprcrash is not None:
            reason = reprcrash.message
        else:
            reason = str(report.longrepr)

        if report.when == "teardown":
            msg = f'failed on teardown with "{reason}"'
        else:
            msg = f'failed on setup with "{reason}"'
        self._add_simple("error", bin_xml_escape(msg), str(report.longrepr))

    def append_skipped(self, report: TestReport) -> None:
        if hasattr(report, "wasxfail"):
            xfailreason = report.wasxfail
            if xfailreason.startswith("reason: "):
                xfailreason = xfailreason[8:]
            xfailreason = bin_xml_escape(xfailreason)
            skipped = ET.Element("skipped", type="pytest.xfail", message=xfailreason)
            self.append(skipped)
        else:
            assert isinstance(report.longrepr, tuple)
            filename, lineno, skipreason = report.longrepr
            if skipreason.startswith("Skipped: "):
                skipreason = skipreason[9:]
            details = f"{filename}:{lineno}: {skipreason}"

            skipped = ET.Element(
                "skipped", type="pytest.skip", message=bin_xml_escape(skipreason)
            )
            skipped.text = bin_xml_escape(details)
            self.append(skipped)
            self.write_captured_output(report)

    def finalize(self) -> None:
        data = self.to_xml()
        self.__dict__.clear()
        # Type ignored because mypy doesn't like overriding a method.
        # Also the return value doesn't match...
        self.to_xml = lambda: data  # type: ignore[method-assign]


def _warn_incompatibility_with_xunit2(
    request: FixtureRequest, fixture_name: str
) -> None:
    """Emit a PytestWarning about the given fixture being incompatible with newer xunit revisions."""
    from _pytest.warning_types import PytestWarning

    xml = request.config.stash.get(xml_key, None)
    if xml is not None and xml.family not in ("xunit1", "legacy"):
        request.node.warn(
            PytestWarning(
                f"{fixture_name} is incompatible with junit_family '{xml.family}' (use 'legacy' or 'xunit1')"
            )
        )


@pytest.fixture
def record_property(request: FixtureRequest) -> Callable[[str, object], None]:
    """Add extra properties to the calling test.

    User properties become part of the test report and are available to the
    configured reporters, like JUnit XML.

    The fixture is callable with ``name, value``. The value is automatically
    XML-encoded.

    Example::

        def test_function(record_property):
            record_property("example_key", 1)
    """
    _warn_incompatibility_with_xunit2(request, "record_property")

    def append_property(name: str, value: object) -> None:
        request.node.user_properties.append((name, value))

    return append_property


@pytest.fixture
def record_xml_attribute(request: FixtureRequest) -> Callable[[str, object], None]:
    """Add extra xml attributes to the tag for the calling test.

    The fixture is callable with ``name, value``. The value is
    automatically XML-encoded.
    """
    from _pytest.warning_types import PytestExperimentalApiWarning

    request.node.warn(
        PytestExperimentalApiWarning("record_xml_attribute is an experimental feature")
    )

    _warn_incompatibility_with_xunit2(request, "record_xml_attribute")

    # Declare noop
    def add_attr_noop(name: str, value: object) -> None:
        pass

    attr_func = add_attr_noop

    xml = request.config.stash.get(xml_key, None)
    if xml is not None:
        node_reporter = xml.node_reporter(request.node.nodeid)
        attr_func = node_reporter.add_attribute

    return attr_func


def _check_record_param_type(param: str, v: str) -> None:
    """Used by record_testsuite_property to check that the given parameter name is of the proper
    type."""
    __tracebackhide__ = True
    if not isinstance(v, str):
        msg = "{param} parameter needs to be a string, but {g} given"  # type: ignore[unreachable]
        raise TypeError(msg.format(param=param, g=type(v).__name__))


@pytest.fixture(scope="session")
def record_testsuite_property(request: FixtureRequest) -> Callable[[str, object], None]:
    """Record a new ``<property>`` tag as child of the root ``<testsuite>``.

    This is suitable to writing global information regarding the entire test
    suite, and is compatible with ``xunit2`` JUnit family.

    This is a ``session``-scoped fixture which is called with ``(name, value)``. Example:

    .. code-block:: python

        def test_foo(record_testsuite_property):
            record_testsuite_property("ARCH", "PPC")
            record_testsuite_property("STORAGE_TYPE", "CEPH")

    :param name:
        The property name.
    :param value:
        The property value. Will be converted to a string.

    .. warning::

        Currently this fixture **does not work** with the
        `pytest-xdist <https://github.com/pytest-dev/pytest-xdist>`__ plugin. See
        :issue:`7767` for details.
    """
    __tracebackhide__ = True

    def record_func(name: str, value: object) -> None:
        """No-op function in case --junit-xml was not passed in the command-line."""
        __tracebackhide__ = True
        _check_record_param_type("name", name)

    xml = request.config.stash.get(xml_key, None)
    if xml is not None:
        record_func = xml.add_global_property
    return record_func


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("terminal reporting")
    group.addoption(
        "--junitxml",
        "--junit-xml",
        action="store",
        dest="xmlpath",
        metavar="path",
        type=functools.partial(filename_arg, optname="--junitxml"),
        default=None,
        help="Create junit-xml style report file at given path",
    )
    group.addoption(
        "--junitprefix",
        "--junit-prefix",
        action="store",
        metavar="str",
        default=None,
        help="Prepend prefix to classnames in junit-xml output",
    )
    parser.addini(
        "junit_suite_name", "Test suite name for JUnit report", default="pytest"
    )
    parser.addini(
        "junit_logging",
        "Write captured log messages to JUnit report: "
        "one of no|log|system-out|system-err|out-err|all",
        default="no",
    )
    parser.addini(
        "junit_log_passing_tests",
        "Capture log information for passing tests to JUnit report: ",
        type="bool",
        default=True,
    )
    parser.addini(
        "junit_duration_report",
        "Duration time to report: one of total|call",
        default="total",
    )  # choices=['total', 'call'])
    parser.addini(
        "junit_family",
        "Emit XML for schema: one of legacy|xunit1|xunit2",
        default="xunit2",
    )


def pytest_configure(config: Config) -> None:
    xmlpath = config.option.xmlpath
    # Prevent opening xmllog on worker nodes (xdist).
    if xmlpath and not hasattr(config, "workerinput"):
        junit_family = config.getini("junit_family")
        config.stash[xml_key] = LogXML(
            xmlpath,
            config.option.junitprefix,
            config.getini("junit_suite_name"),
            config.getini("junit_logging"),
            config.getini("junit_duration_report"),
            junit_family,
            config.getini("junit_log_passing_tests"),
        )
        config.pluginmanager.register(config.stash[xml_key])


def pytest_unconfigure(config: Config) -> None:
    xml = config.stash.get(xml_key, None)
    if xml:
        del config.stash[xml_key]
        config.pluginmanager.unregister(xml)


def mangle_test_address(address: str) -> list[str]:
    path, possible_open_bracket, params = address.partition("[")
    names = path.split("::")
    # Convert file path to dotted path.
    names[0] = names[0].replace(nodes.SEP, ".")
    names[0] = re.sub(r"\.py$", "", names[0])
    # Put any params back.
    names[-1] += possible_open_bracket + params
    return names


class LogXML:
    def __init__(
        self,
        logfile,
        prefix: str | None,
        suite_name: str = "pytest",
        logging: str = "no",
        report_duration: str = "total",
        family="xunit1",
        log_passing_tests: bool = True,
    ) -> None:
        logfile = os.path.expanduser(os.path.expandvars(logfile))
        self.logfile = os.path.normpath(os.path.abspath(logfile))
        self.prefix = prefix
        self.suite_name = suite_name
        self.logging = logging
        self.log_passing_tests = log_passing_tests
        self.report_duration = report_duration
        self.family = family
        self.stats: dict[str, int] = dict.fromkeys(
            ["error", "passed", "failure", "skipped"], 0
        )
        self.node_reporters: dict[tuple[str | TestReport, object], _NodeReporter] = {}
        self.node_reporters_ordered: list[_NodeReporter] = []
        self.global_properties: list[tuple[str, str]] = []

        # List of reports that failed on call but teardown is pending.
        self.open_reports: list[TestReport] = []
        self.cnt_double_fail_tests = 0

        # Replaces convenience family with real family.
        if self.family == "legacy":
            self.family = "xunit1"

    def finalize(self, report: TestReport) -> None:
        nodeid = getattr(report, "nodeid", report)
        # Local hack to handle xdist report order.
        workernode = getattr(report, "node", None)
        reporter = self.node_reporters.pop((nodeid, workernode))

        for propname, propvalue in report.user_properties:
            reporter.add_property(propname, str(propvalue))

        if reporter is not None:
            reporter.finalize()

    def node_reporter(self, report: TestReport | str) -> _NodeReporter:
        nodeid: str | TestReport = getattr(report, "nodeid", report)
        # Local hack to handle xdist report order.
        workernode = getattr(report, "node", None)

        key = nodeid, workernode

        if key in self.node_reporters:
            # TODO: breaks for --dist=each
            return self.node_reporters[key]

        reporter = _NodeReporter(nodeid, self)

        self.node_reporters[key] = reporter
        self.node_reporters_ordered.append(reporter)

        return reporter

    def add_stats(self, key: str) -> None:
        if key in self.stats:
            self.stats[key] += 1

    def _opentestcase(self, report: TestReport) -> _NodeReporter:
        reporter = self.node_reporter(report)
        reporter.record_testreport(report)
        return reporter

    def pytest_runtest_logreport(self, report: TestReport) -> None:
        """Handle a setup/call/teardown report, generating the appropriate
        XML tags as necessary.

        Note: due to plugins like xdist, this hook may be called in interlaced
        order with reports from other nodes. For example:

        Usual call order:
            -> setup node1
            -> call node1
            -> teardown node1
            -> setup node2
            -> call node2
            -> teardown node2

        Possible call order in xdist:
            -> setup node1
            -> call node1
            -> setup node2
            -> call node2
            -> teardown node2
            -> teardown node1
        """
        close_report = None
        if report.passed:
            if report.when == "call":  # ignore setup/teardown
                reporter = self._opentestcase(report)
                reporter.append_pass(report)
        elif report.failed:
            if report.when == "teardown":
                # The following vars are needed when xdist plugin is used.
                report_wid = getattr(report, "worker_id", None)
                report_ii = getattr(report, "item_index", None)
                close_report = next(
                    (
                        rep
                        for rep in self.open_reports
                        if (
                            rep.nodeid == report.nodeid
                            and getattr(rep, "item_index", None) == report_ii
                            and getattr(rep, "worker_id", None) == report_wid
                        )
                    ),
                    None,
                )
                if close_report:
                    # We need to open new testcase in case we have failure in
                    # call and error in teardown in order to follow junit
                    # schema.
                    self.finalize(close_report)
                else:
                    # A passing call with a teardown error creates separate
                    # terminal reports, but JUnit XML keeps one testcase
                    # element for that item (#3850).
                    self.cnt_double_fail_tests += int(
                        (
                            report.nodeid,
                            getattr(report, "node", None),
                        )
                        in self.node_reporters
                    )
            reporter = self._opentestcase(report)
            if report.when == "call":
                reporter.append_failure(report)
                self.open_reports.append(report)
                if not self.log_passing_tests:
                    reporter.write_captured_output(report)
            else:
                reporter.append_error(report)
        elif report.skipped:
            reporter = self._opentestcase(report)
            reporter.append_skipped(report)
        self.update_testcase_duration(report)
        if report.when == "teardown":
            reporter = self._opentestcase(report)
            reporter.write_captured_output(report)

            self.finalize(report)
            report_wid = getattr(report, "worker_id", None)
            report_ii = getattr(report, "item_index", None)
            close_report = next(
                (
                    rep
                    for rep in self.open_reports
                    if (
                        rep.nodeid == report.nodeid
                        and getattr(rep, "item_index", None) == report_ii
                        and getattr(rep, "worker_id", None) == report_wid
                    )
                ),
                None,
            )
            if close_report:
                self.open_reports.remove(close_report)

    def update_testcase_duration(self, report: TestReport) -> None:
        """Accumulate total duration for nodeid from given report and update
        the Junit.testcase with the new total if already created."""
        if self.report_duration in {"total", report.when}:
            reporter = self.node_reporter(report)
            reporter.duration += getattr(report, "duration", 0.0)

    def pytest_collectreport(self, report: TestReport) -> None:
        if not report.passed:
            reporter = self._opentestcase(report)
            if report.failed:
                reporter.append_collect_error(report)
            else:
                reporter.append_collect_skipped(report)

    def pytest_internalerror(self, excrepr: ExceptionRepr) -> None:
        reporter = self.node_reporter("internal")
        reporter.attrs.update(classname="pytest", name="internal")
        reporter._add_simple("error", "internal error", str(excrepr))

    def pytest_sessionstart(self) -> None:
        self.suite_start = timing.Instant()

    def pytest_sessionfinish(self) -> None:
        dirname = os.path.dirname(os.path.abspath(self.logfile))
        # exist_ok avoids filesystem race conditions between checking path existence and requesting creation
        os.makedirs(dirname, exist_ok=True)

        with open(self.logfile, "w", encoding="utf-8") as logfile:
            duration = self.suite_start.elapsed()

            numtests = (
                self.stats["passed"]
                + self.stats["failure"]
                + self.stats["skipped"]
                + self.stats["error"]
                - self.cnt_double_fail_tests
            )
            logfile.write('<?xml version="1.0" encoding="utf-8"?>')

            suite_node = ET.Element(
                "testsuite",
                name=self.suite_name,
                errors=str(self.stats["error"]),
                failures=str(self.stats["failure"]),
                skipped=str(self.stats["skipped"]),
                tests=str(numtests),
                time=f"{duration.seconds:.3f}",
                timestamp=self.suite_start.as_utc().astimezone().isoformat(),
                hostname=platform.node(),
            )
            global_properties = self._get_global_properties_node()
            if global_properties is not None:
                suite_node.append(global_properties)
            for node_reporter in self.node_reporters_ordered:
                suite_node.append(node_reporter.to_xml())
            testsuites = ET.Element("testsuites")
            testsuites.set("name", "pytest tests")
            testsuites.append(suite_node)
            logfile.write(ET.tostring(testsuites, encoding="unicode"))

    def pytest_terminal_summary(
        self, terminalreporter: TerminalReporter, config: pytest.Config
    ) -> None:
        if config.get_verbosity() >= 0:
            terminalreporter.write_sep("-", f"generated xml file: {self.logfile}")

    def add_global_property(self, name: str, value: object) -> None:
        __tracebackhide__ = True
        _check_record_param_type("name", name)
        self.global_properties.append((name, bin_xml_escape(value)))

    def _get_global_properties_node(self) -> ET.Element | None:
        """Return a Junit node containing custom properties, if any."""
        if self.global_properties:
            properties = ET.Element("properties")
            for name, value in self.global_properties:
                properties.append(ET.Element("property", name=name, value=value))
            return properties
        return None
