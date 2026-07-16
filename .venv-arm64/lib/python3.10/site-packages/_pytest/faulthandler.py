from __future__ import annotations

from collections.abc import Generator
import os
import sys

from _pytest.config import Config
from _pytest.config.argparsing import Parser
from _pytest.nodes import Item
from _pytest.stash import StashKey
import pytest


fault_handler_original_stderr_fd_key = StashKey[int]()
fault_handler_stderr_fd_key = StashKey[int]()


def pytest_addoption(parser: Parser) -> None:
    help_timeout = (
        "Dump the traceback of all threads if a test takes "
        "more than TIMEOUT seconds to finish"
    )
    help_exit_on_timeout = (
        "Exit the test process if a test takes more than "
        "faulthandler_timeout seconds to finish"
    )
    parser.addini("faulthandler_timeout", help_timeout, default=0.0)
    parser.addini(
        "faulthandler_exit_on_timeout", help_exit_on_timeout, type="bool", default=False
    )


def pytest_configure(config: Config) -> None:
    import faulthandler

    # at teardown we want to restore the original faulthandler fileno
    # but faulthandler has no api to return the original fileno
    # so here we stash the stderr fileno to be used at teardown
    # sys.stderr and sys.__stderr__ may be closed or patched during the session
    # so we can't rely on their values being good at that point (#11572).
    stderr_fileno = get_stderr_fileno()
    if faulthandler.is_enabled():
        config.stash[fault_handler_original_stderr_fd_key] = stderr_fileno
    config.stash[fault_handler_stderr_fd_key] = os.dup(stderr_fileno)
    faulthandler.enable(file=config.stash[fault_handler_stderr_fd_key])


def pytest_unconfigure(config: Config) -> None:
    import faulthandler

    faulthandler.disable()
    # Close the dup file installed during pytest_configure.
    if fault_handler_stderr_fd_key in config.stash:
        os.close(config.stash[fault_handler_stderr_fd_key])
        del config.stash[fault_handler_stderr_fd_key]
    # Re-enable the faulthandler if it was originally enabled.
    if fault_handler_original_stderr_fd_key in config.stash:
        faulthandler.enable(config.stash[fault_handler_original_stderr_fd_key])
        del config.stash[fault_handler_original_stderr_fd_key]


def get_stderr_fileno() -> int:
    try:
        fileno = sys.stderr.fileno()
        # The Twisted Logger will return an invalid file descriptor since it is not backed
        # by an FD. So, let's also forward this to the same code path as with pytest-xdist.
        if fileno == -1:
            raise AttributeError()
        return fileno
    except (AttributeError, ValueError):
        # pytest-xdist monkeypatches sys.stderr with an object that is not an actual file.
        # https://docs.python.org/3/library/faulthandler.html#issue-with-file-descriptors
        # This is potentially dangerous, but the best we can do.
        assert sys.__stderr__ is not None
        return sys.__stderr__.fileno()


def get_timeout_config_value(config: Config) -> float:
    return float(config.getini("faulthandler_timeout") or 0.0)


def get_exit_on_timeout_config_value(config: Config) -> bool:
    exit_on_timeout = config.getini("faulthandler_exit_on_timeout")
    assert isinstance(exit_on_timeout, bool)
    return exit_on_timeout


@pytest.hookimpl(wrapper=True, trylast=True)
def pytest_runtest_protocol(item: Item) -> Generator[None, object, object]:
    timeout = get_timeout_config_value(item.config)
    exit_on_timeout = get_exit_on_timeout_config_value(item.config)
    if timeout > 0:
        import faulthandler

        stderr = item.config.stash[fault_handler_stderr_fd_key]
        faulthandler.dump_traceback_later(timeout, file=stderr, exit=exit_on_timeout)
        try:
            return (yield)
        finally:
            faulthandler.cancel_dump_traceback_later()
    else:
        return (yield)


@pytest.hookimpl(tryfirst=True)
def pytest_enter_pdb() -> None:
    """Cancel any traceback dumping due to timeout before entering pdb."""
    import faulthandler

    faulthandler.cancel_dump_traceback_later()


@pytest.hookimpl(tryfirst=True)
def pytest_exception_interact() -> None:
    """Cancel any traceback dumping due to an interactive exception being
    raised."""
    import faulthandler

    faulthandler.cancel_dump_traceback_later()
