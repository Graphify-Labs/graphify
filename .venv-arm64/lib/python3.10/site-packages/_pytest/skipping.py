# mypy: allow-untyped-defs
"""Support for skip/xfail functions and markers."""

from __future__ import annotations

from collections.abc import Generator
from collections.abc import Mapping
import dataclasses
import os
import platform
import sys
import traceback

from _pytest.config import Config
from _pytest.config import hookimpl
from _pytest.config.argparsing import Parser
from _pytest.mark.structures import Mark
from _pytest.nodes import Item
from _pytest.outcomes import fail
from _pytest.outcomes import skip
from _pytest.outcomes import xfail
from _pytest.raises import AbstractRaises
from _pytest.reports import BaseReport
from _pytest.reports import TestReport
from _pytest.runner import CallInfo
from _pytest.stash import StashKey


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("general")
    group.addoption(
        "--runxfail",
        action="store_true",
        dest="runxfail",
        default=False,
        help="Report the results of xfail tests as if they were not marked",
    )

    parser.addini(
        "strict_xfail",
        "Default for the strict parameter of xfail "
        "markers when not given explicitly (default: False) (alias: xfail_strict)",
        type="bool",
        # None => fallback to `strict`.
        default=None,
        aliases=["xfail_strict"],
    )


def pytest_configure(config: Config) -> None:
    if config.option.runxfail:
        # yay a hack
        import pytest

        old = pytest.xfail
        config.add_cleanup(lambda: setattr(pytest, "xfail", old))

        def nop(*args, **kwargs):
            pass

        nop.Exception = xfail.Exception  # type: ignore[attr-defined]
        setattr(pytest, "xfail", nop)

    config.addinivalue_line(
        "markers",
        "skip(reason=None): skip the given test function with an optional reason. "
        'Example: skip(reason="no way of currently testing this") skips the '
        "test.",
    )
    config.addinivalue_line(
        "markers",
        "skipif(condition, ..., *, reason=...): "
        "skip the given test function if any of the conditions evaluate to True. "
        "Example: skipif(sys.platform == 'win32') skips the test if we are on the win32 platform. "
        "See https://docs.pytest.org/en/stable/reference/reference.html#pytest-mark-skipif",
    )
    config.addinivalue_line(
        "markers",
        "xfail(condition, ..., *, reason=..., run=True, raises=None, strict=strict_xfail): "
        "mark the test function as an expected failure if any of the conditions "
        "evaluate to True. Optionally specify a reason for better reporting "
        "and run=False if you don't even want to execute the test function. "
        "If only specific exception(s) are expected, you can list them in "
        "raises, and if the test fails in other ways, it will be reported as "
        "a true failure. See https://docs.pytest.org/en/stable/reference/reference.html#pytest-mark-xfail",
    )


def evaluate_condition(item: Item, mark: Mark, condition: object) -> tuple[bool, str]:
    """Evaluate a single skipif/xfail condition.

    If an old-style string condition is given, it is eval()'d, otherwise the
    condition is bool()'d. If this fails, an appropriately formatted pytest.fail
    is raised.

    Returns (result, reason). The reason is only relevant if the result is True.
    """
    # String condition.
    if isinstance(condition, str):
        globals_ = {
            "os": os,
            "sys": sys,
            "platform": platform,
            "config": item.config,
        }
        for dictionary in reversed(
            item.ihook.pytest_markeval_namespace(config=item.config)
        ):
            if not isinstance(dictionary, Mapping):
                raise ValueError(
                    f"pytest_markeval_namespace() needs to return a dict, got {dictionary!r}"
                )
            globals_.update(dictionary)
        if hasattr(item, "obj"):
            globals_.update(item.obj.__globals__)
        try:
            filename = f"<{mark.name} condition>"
            condition_code = compile(condition, filename, "eval")
            result = eval(condition_code, globals_)
        except SyntaxError as exc:
            msglines = [
                f"Error evaluating {mark.name!r} condition",
                "    " + condition,
                "    " + " " * (exc.offset or 0) + "^",
                "SyntaxError: invalid syntax",
            ]
            fail("\n".join(msglines), pytrace=False)
        except Exception as exc:
            msglines = [
                f"Error evaluating {mark.name!r} condition",
                "    " + condition,
                *traceback.format_exception_only(exc),
            ]
            fail("\n".join(msglines), pytrace=False)

    # Boolean condition.
    else:
        try:
            result = bool(condition)
        except Exception as exc:
            msglines = [
                f"Error evaluating {mark.name!r} condition as a boolean",
                *traceback.format_exception_only(exc),
            ]
            fail("\n".join(msglines), pytrace=False)

    reason = mark.kwargs.get("reason", None)
    if reason is None:
        if isinstance(condition, str):
            reason = "condition: " + condition
        else:
            # XXX better be checked at collection time
            msg = (
                f"Error evaluating {mark.name!r}: "
                + "you need to specify reason=STRING when using booleans as conditions."
            )
            fail(msg, pytrace=False)

    return result, reason


@dataclasses.dataclass(frozen=True)
class Skip:
    """The result of evaluate_skip_marks()."""

    reason: str = "unconditional skip"


def evaluate_skip_marks(item: Item) -> Skip | None:
    """Evaluate skip and skipif marks on item, returning Skip if triggered."""
    for mark in item.iter_markers(name="skipif"):
        if "condition" not in mark.kwargs:
            conditions = mark.args
        else:
            conditions = (mark.kwargs["condition"],)

        # Unconditional.
        if not conditions:
            reason = mark.kwargs.get("reason", "")
            return Skip(reason)

        # If any of the conditions are true.
        for condition in conditions:
            result, reason = evaluate_condition(item, mark, condition)
            if result:
                return Skip(reason)

    for mark in item.iter_markers(name="skip"):
        try:
            return Skip(*mark.args, **mark.kwargs)
        except TypeError as e:
            raise TypeError(str(e) + " - maybe you meant pytest.mark.skipif?") from None

    return None


@dataclasses.dataclass(frozen=True)
class Xfail:
    """The result of evaluate_xfail_marks()."""

    __slots__ = ("raises", "reason", "run", "strict")

    reason: str
    run: bool
    strict: bool
    raises: (
        type[BaseException]
        | tuple[type[BaseException], ...]
        | AbstractRaises[BaseException]
        | None
    )


def evaluate_xfail_marks(item: Item) -> Xfail | None:
    """Evaluate xfail marks on item, returning Xfail if triggered."""
    for mark in item.iter_markers(name="xfail"):
        run = mark.kwargs.get("run", True)
        strict = mark.kwargs.get("strict")
        if strict is None:
            strict = item.config.getini("strict_xfail")
        if strict is None:
            strict = item.config.getini("strict")
        raises = mark.kwargs.get("raises", None)
        if "condition" not in mark.kwargs:
            conditions = mark.args
        else:
            conditions = (mark.kwargs["condition"],)

        # Unconditional.
        if not conditions:
            reason = mark.kwargs.get("reason", "")
            return Xfail(reason, run, strict, raises)

        # If any of the conditions are true.
        for condition in conditions:
            result, reason = evaluate_condition(item, mark, condition)
            if result:
                return Xfail(reason, run, strict, raises)

    return None


# Saves the xfail mark evaluation. Can be refreshed during call if None.
xfailed_key = StashKey[Xfail | None]()


@hookimpl(tryfirst=True)
def pytest_runtest_setup(item: Item) -> None:
    skipped = evaluate_skip_marks(item)
    if skipped:
        raise skip.Exception(skipped.reason, _use_item_location=True)

    item.stash[xfailed_key] = xfailed = evaluate_xfail_marks(item)
    if xfailed and not item.config.option.runxfail and not xfailed.run:
        xfail("[NOTRUN] " + xfailed.reason)


@hookimpl(wrapper=True)
def pytest_runtest_call(item: Item) -> Generator[None]:
    xfailed = item.stash.get(xfailed_key, None)
    if xfailed is None:
        item.stash[xfailed_key] = xfailed = evaluate_xfail_marks(item)

    if xfailed and not item.config.option.runxfail and not xfailed.run:
        xfail("[NOTRUN] " + xfailed.reason)

    try:
        return (yield)
    finally:
        # The test run may have added an xfail mark dynamically.
        xfailed = item.stash.get(xfailed_key, None)
        if xfailed is None:
            item.stash[xfailed_key] = xfailed = evaluate_xfail_marks(item)


@hookimpl(wrapper=True)
def pytest_runtest_makereport(
    item: Item, call: CallInfo[None]
) -> Generator[None, TestReport, TestReport]:
    rep = yield
    xfailed = item.stash.get(xfailed_key, None)
    if item.config.option.runxfail:
        pass  # don't interfere
    elif call.excinfo and isinstance(call.excinfo.value, xfail.Exception):
        assert call.excinfo.value.msg is not None
        rep.wasxfail = call.excinfo.value.msg
        rep.outcome = "skipped"
    elif not rep.skipped and xfailed:
        if call.excinfo:
            raises = xfailed.raises
            if raises is None or (
                (
                    isinstance(raises, type | tuple)
                    and isinstance(call.excinfo.value, raises)
                )
                or (
                    isinstance(raises, AbstractRaises)
                    and raises.matches(call.excinfo.value)
                )
            ):
                rep.outcome = "skipped"
                rep.wasxfail = xfailed.reason
            else:
                rep.outcome = "failed"
        elif call.when == "call":
            if xfailed.strict:
                rep.outcome = "failed"
                rep.longrepr = "[XPASS(strict)] " + xfailed.reason
            else:
                rep.outcome = "passed"
                rep.wasxfail = xfailed.reason
    return rep


def pytest_report_teststatus(report: BaseReport) -> tuple[str, str, str] | None:
    if hasattr(report, "wasxfail"):
        if report.skipped:
            return "xfailed", "x", "XFAIL"
        elif report.passed:
            return "xpassed", "X", "XPASS"
    return None
