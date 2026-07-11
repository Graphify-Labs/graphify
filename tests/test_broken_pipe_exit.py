"""Regression tests for a nonzero exit / crash when stdout is closed early.

When graphify output is piped into a reader that stops before consuming it all
(a shell `head`, PowerShell `Select-Object -First N`, or a pager the user
quits), the OS closes graphify's stdout mid-write. POSIX surfaces this as
BrokenPipeError; Windows surfaces it as OSError(EINVAL) on the flush. Before the
fix this escaped the interpreter's shutdown flush as a noisy
"Exception ignored on flushing sys.stdout" message plus a nonzero exit (120 /
-1). A downstream `head` closing the pipe is not an error, so graphify must
exit 0 the way `foo | head` does.

These tests drive the real entry point (`main`) with `_main` monkeypatched to
raise the exact exceptions a closed pipe produces, and assert the exit code
contract. An end-to-end subprocess reproduction is intentionally avoided here:
whether the pre-fix crash fires depends on a buffering race between the reader's
close() and the writer's final flush, which makes it flaky as an automated
regression lock. The mechanism (which exception, which exit code) is what this
suite pins down.
"""
from __future__ import annotations

import errno

import pytest

from graphify import __main__ as mainmod


def _raise(exc: BaseException):
    """Return a zero-arg callable that raises `exc` (a stand-in for _main)."""
    def _boom() -> None:
        raise exc
    return _boom


@pytest.fixture
def _guard_fd_ops(monkeypatch):
    """Stub the fd syscalls _exit_on_closed_pipe uses.

    _exit_on_closed_pipe redirects the *real* stdout fd to devnull; without
    this guard it would clobber the test runner's own stdout.
    """
    monkeypatch.setattr(mainmod.os, "open", lambda *a, **k: 0)
    monkeypatch.setattr(mainmod.os, "dup2", lambda *a, **k: None)


class TestClosedPipeExitsZero:
    def test_broken_pipe_exits_zero(self, monkeypatch, _guard_fd_ops):
        """POSIX: a BrokenPipeError from writing to a closed pipe -> exit 0."""
        monkeypatch.setattr(mainmod, "_main", _raise(BrokenPipeError()))
        with pytest.raises(SystemExit) as exc:
            mainmod.main()
        assert exc.value.code == 0

    def test_windows_einval_exits_zero(self, monkeypatch, _guard_fd_ops):
        """Windows: a closed pipe surfaces as OSError(EINVAL) -> exit 0."""
        monkeypatch.setattr(
            mainmod, "_main", _raise(OSError(errno.EINVAL, "Invalid argument"))
        )
        with pytest.raises(SystemExit) as exc:
            mainmod.main()
        assert exc.value.code == 0

    def test_epipe_exits_zero(self, monkeypatch, _guard_fd_ops):
        """An explicit EPIPE OSError (not a BrokenPipeError subclass) -> exit 0."""
        monkeypatch.setattr(
            mainmod, "_main", _raise(OSError(errno.EPIPE, "Broken pipe"))
        )
        with pytest.raises(SystemExit) as exc:
            mainmod.main()
        assert exc.value.code == 0


class TestUnrelatedErrorsStillPropagate:
    def test_unrelated_oserror_propagates(self, monkeypatch, _guard_fd_ops):
        """A non-pipe OSError (e.g. ENOENT) must NOT be swallowed as a clean exit.

        Guards against the fix masking real failures like a missing graph.json.
        """
        monkeypatch.setattr(
            mainmod, "_main", _raise(OSError(errno.ENOENT, "No such file"))
        )
        with pytest.raises(OSError) as exc:
            mainmod.main()
        assert exc.value.errno == errno.ENOENT

    def test_value_error_propagates(self, monkeypatch, _guard_fd_ops):
        """Ordinary application errors must surface, not turn into exit 0."""
        monkeypatch.setattr(mainmod, "_main", _raise(ValueError("bad graph")))
        with pytest.raises(ValueError):
            mainmod.main()
