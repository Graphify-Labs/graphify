from __future__ import annotations

import collections
from collections.abc import Callable
import functools
import sys
import threading
import traceback
from typing import NamedTuple
from typing import TYPE_CHECKING
import warnings

from _pytest.config import Config
from _pytest.nodes import Item
from _pytest.stash import StashKey
from _pytest.tracemalloc import tracemalloc_message
import pytest


if TYPE_CHECKING:
    pass

if sys.version_info < (3, 11):
    from exceptiongroup import ExceptionGroup


class ThreadExceptionMeta(NamedTuple):
    msg: str
    cause_msg: str
    exc_value: BaseException | None


thread_exceptions: StashKey[collections.deque[ThreadExceptionMeta | BaseException]] = (
    StashKey()
)


def collect_thread_exception(config: Config) -> None:
    pop_thread_exception = config.stash[thread_exceptions].pop
    errors: list[pytest.PytestUnhandledThreadExceptionWarning | RuntimeError] = []
    meta = None
    hook_error = None
    try:
        while True:
            try:
                meta = pop_thread_exception()
            except IndexError:
                break

            if isinstance(meta, BaseException):
                hook_error = RuntimeError("Failed to process thread exception")
                hook_error.__cause__ = meta
                errors.append(hook_error)
                continue

            msg = meta.msg
            try:
                warnings.warn(pytest.PytestUnhandledThreadExceptionWarning(msg))
            except pytest.PytestUnhandledThreadExceptionWarning as e:
                # This except happens when the warning is treated as an error (e.g. `-Werror`).
                if meta.exc_value is not None:
                    # Exceptions have a better way to show the traceback, but
                    # warnings do not, so hide the traceback from the msg and
                    # set the cause so the traceback shows up in the right place.
                    e.args = (meta.cause_msg,)
                    e.__cause__ = meta.exc_value
                errors.append(e)

        if len(errors) == 1:
            raise errors[0]
        if errors:
            raise ExceptionGroup("multiple thread exception warnings", errors)
    finally:
        del errors, meta, hook_error


def cleanup(
    *, config: Config, prev_hook: Callable[[threading.ExceptHookArgs], object]
) -> None:
    try:
        try:
            # We don't join threads here, so exceptions raised from any
            # threads still running by the time _threading_atexits joins them
            # do not get captured (see #13027).
            collect_thread_exception(config)
        finally:
            threading.excepthook = prev_hook
    finally:
        del config.stash[thread_exceptions]


def thread_exception_hook(
    args: threading.ExceptHookArgs,
    /,
    *,
    append: Callable[[ThreadExceptionMeta | BaseException], object],
) -> None:
    try:
        # we need to compute these strings here as they might change after
        # the excepthook finishes and before the metadata object is
        # collected by a pytest hook
        thread_name = "<unknown>" if args.thread is None else args.thread.name
        summary = f"Exception in thread {thread_name}"
        traceback_message = "\n\n" + "".join(
            traceback.format_exception(
                args.exc_type,
                args.exc_value,
                args.exc_traceback,
            )
        )
        tracemalloc_tb = "\n" + tracemalloc_message(args.thread)
        msg = summary + traceback_message + tracemalloc_tb
        cause_msg = summary + tracemalloc_tb

        append(
            ThreadExceptionMeta(
                # Compute these strings here as they might change later
                msg=msg,
                cause_msg=cause_msg,
                exc_value=args.exc_value,
            )
        )
    except BaseException as e:
        append(e)
        # Raising this will cause the exception to be logged twice, once in our
        # collect_thread_exception and once by sys.excepthook
        # which is fine - this should never happen anyway and if it does
        # it should probably be reported as a pytest bug.
        raise


def pytest_configure(config: Config) -> None:
    prev_hook = threading.excepthook
    deque: collections.deque[ThreadExceptionMeta | BaseException] = collections.deque()
    config.stash[thread_exceptions] = deque
    config.add_cleanup(functools.partial(cleanup, config=config, prev_hook=prev_hook))
    threading.excepthook = functools.partial(thread_exception_hook, append=deque.append)


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item: Item) -> None:
    collect_thread_exception(item.config)


@pytest.hookimpl(trylast=True)
def pytest_runtest_call(item: Item) -> None:
    collect_thread_exception(item.config)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: Item) -> None:
    collect_thread_exception(item.config)
