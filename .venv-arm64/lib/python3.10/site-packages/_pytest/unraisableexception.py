from __future__ import annotations

import collections
from collections.abc import Callable
import functools
import gc
import sys
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


# This is a stash item and not a simple constant to allow pytester to override it.
gc_collect_iterations_key = StashKey[int]()


def gc_collect_harder(iterations: int) -> None:
    for _ in range(iterations):
        gc.collect()


class UnraisableMeta(NamedTuple):
    msg: str
    cause_msg: str
    exc_value: BaseException | None


unraisable_exceptions: StashKey[collections.deque[UnraisableMeta | BaseException]] = (
    StashKey()
)


def collect_unraisable(config: Config) -> None:
    pop_unraisable = config.stash[unraisable_exceptions].pop
    errors: list[pytest.PytestUnraisableExceptionWarning | RuntimeError] = []
    meta = None
    hook_error = None
    try:
        while True:
            try:
                meta = pop_unraisable()
            except IndexError:
                break

            if isinstance(meta, BaseException):
                hook_error = RuntimeError("Failed to process unraisable exception")
                hook_error.__cause__ = meta
                errors.append(hook_error)
                continue

            msg = meta.msg
            try:
                warnings.warn(pytest.PytestUnraisableExceptionWarning(msg))
            except pytest.PytestUnraisableExceptionWarning as e:
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
            raise ExceptionGroup("multiple unraisable exception warnings", errors)
    finally:
        del errors, meta, hook_error


def cleanup(
    *, config: Config, prev_hook: Callable[[sys.UnraisableHookArgs], object]
) -> None:
    # On PyPy, objects (e.g. coroutines) can survive GC rounds because executing
    # their __del__ can resurrect them. The Trio project determined experimentally
    # that 5 passes are needed on PyPy to flush everything. On CPython, reference
    # counting handles most cleanup immediately, so 1 pass is sufficient.
    _default_gc_collect_iterations = 5 if sys.implementation.name == "pypy" else 1
    gc_collect_iterations = config.stash.get(
        gc_collect_iterations_key, _default_gc_collect_iterations
    )
    try:
        try:
            gc_collect_harder(gc_collect_iterations)
            collect_unraisable(config)
        finally:
            sys.unraisablehook = prev_hook
    finally:
        del config.stash[unraisable_exceptions]


def unraisable_hook(
    unraisable: sys.UnraisableHookArgs,
    /,
    *,
    append: Callable[[UnraisableMeta | BaseException], object],
) -> None:
    try:
        # we need to compute these strings here as they might change after
        # the unraisablehook finishes and before the metadata object is
        # collected by a pytest hook
        err_msg = (
            "Exception ignored in" if unraisable.err_msg is None else unraisable.err_msg
        )
        summary = f"{err_msg}: {unraisable.object!r}"
        traceback_message = "\n\n" + "".join(
            traceback.format_exception(
                unraisable.exc_type,
                unraisable.exc_value,
                unraisable.exc_traceback,
            )
        )
        tracemalloc_tb = "\n" + tracemalloc_message(unraisable.object)
        msg = summary + traceback_message + tracemalloc_tb
        cause_msg = summary + tracemalloc_tb

        append(
            UnraisableMeta(
                msg=msg,
                cause_msg=cause_msg,
                exc_value=unraisable.exc_value,
            )
        )
    except BaseException as e:
        append(e)
        # Raising this will cause the exception to be logged twice, once in our
        # collect_unraisable and once by the unraisablehook calling machinery
        # which is fine - this should never happen anyway and if it does
        # it should probably be reported as a pytest bug.
        raise


def pytest_configure(config: Config) -> None:
    prev_hook = sys.unraisablehook
    deque: collections.deque[UnraisableMeta | BaseException] = collections.deque()
    config.stash[unraisable_exceptions] = deque
    config.add_cleanup(functools.partial(cleanup, config=config, prev_hook=prev_hook))
    sys.unraisablehook = functools.partial(unraisable_hook, append=deque.append)


def pytest_unconfigure(config: Config) -> None:
    # Runs before ``_cleanup_stack.close()``, so warning filters from
    # cleanup-stack-managed contexts (notably the ``warnings`` plugin's
    # ``catch_warnings``) are still installed when garbage-collected
    # finalizers fire. A ``config.add_cleanup`` callback would instead
    # couple correctness to LIFO pop order across plugins' cleanups.
    if unraisable_exceptions not in config.stash:
        # ``pytest_configure`` did not complete (e.g. a usage error raised
        # in another plugin's configure), so the queue stash was never set.
        return
    # PyPy can resurrect objects in __del__, so it needs several GC passes
    # (5, per the Trio project); CPython frees cycles in one pass. See #14441.
    _default_gc_collect_iterations = 5 if sys.implementation.name == "pypy" else 1
    gc_collect_iterations = config.stash.get(
        gc_collect_iterations_key, _default_gc_collect_iterations
    )
    gc_collect_harder(gc_collect_iterations)
    collect_unraisable(config)


@pytest.hookimpl(trylast=True)
def pytest_runtest_setup(item: Item) -> None:
    collect_unraisable(item.config)


@pytest.hookimpl(trylast=True)
def pytest_runtest_call(item: Item) -> None:
    collect_unraisable(item.config)


@pytest.hookimpl(trylast=True)
def pytest_runtest_teardown(item: Item) -> None:
    collect_unraisable(item.config)
