from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import TYPE_CHECKING, Any, Generator

if TYPE_CHECKING:
    from prompt_toolkit.input.base import Input
    from prompt_toolkit.output.base import Output

    from .application import Application

__all__ = [
    "AppSession",
    "get_app_session",
    "get_app",
    "get_app_or_none",
    "set_app",
    "create_app_session",
    "create_app_session_from_tty",
]


class AppSession:
    """
    An AppSession is an interactive session, usually connected to one terminal.
    Within one such session, interaction with many applications can happen, one
    after the other.

    The input/output device is not supposed to change during one session.

    Warning: Always use the `create_app_session` function to create an
    instance, so that it gets activated correctly.

    :param input: Use this as a default input for all applications
        running in this session, unless an input is passed to the `Application`
        explicitly.
    :param output: Use this as a default output.
    """

    def __init__(
        self, input: Input | None = None, output: Output | None = None
    ) -> None:
        self._input = input
        self._output = output

        # The application will be set dynamically by the `set_app` context
        # manager. This is called in the application itself.
        self.app: Application[Any] | None = None

    def __repr__(self) -> str:
        return f"AppSession(app={self.app!r})"

    @property
    def input(self) -> Input:
        if self._input is None:
            from prompt_toolkit.input.defaults import create_input

            self._input = create_input()
        return self._input

    @property
    def output(self) -> Output:
        if self._output is None:
            from prompt_toolkit.output.defaults import create_output

            self._output = create_output()
        return self._output


_current_app_session: ContextVar[AppSession] = ContextVar(
    "_current_app_session", default=AppSession()
)


def get_app_session() -> AppSession:
    return _current_app_session.get()


def get_app() -> Application[Any]:
    """
    Get the current active (running) Application.
    An :class:`.Application` is active during the
    :meth:`.Application.run_async` call.

    We assume that there can only be one :class:`.Application` active at the
    same time. There is only one terminal window, with only one stdin and
    stdout. This makes the code significantly easier than passing around the
    :class:`.Application` everywhere.

    If no :class:`.Application` is running, then return by default a
    :class:`.DummyApplication`. For practical reasons, we prefer to not raise
    an exception. This way, we don't have to check all over the place whether
    an actual `Application` was returned.

    (For applications like pymux where we can have more than one `Application`,
    we'll use a work-around to handle that.)
    """
    session = _current_app_session.get()
    if session.app is not None:
        return session.app

    from .dummy import DummyApplication

    return DummyApplication()


def get_app_or_none() -> Application[Any] | None:
    """
    Get the current active (running) Application, or return `None` if no
    application is running.
    """
    session = _current_app_session.get()
    return session.app


@contextmanager
def set_app(app: Application[Any]) -> Generator[None, None, None]:
    """
    Context manager that sets the given :class:`.Application` active in an
    `AppSession`.

    This should only be called by the `Application` itself.
    The application will automatically be active while its running. If you want
    the application to be active in other threads/coroutines, where that's not
    the case, use `contextvars.copy_context()`, or use `Application.context` to
    run it in the appropriate context.
    """
    session = _current_app_session.get()

    previous_app = session.app
    session.app = app
    try:
        yield
    finally:
        session.app = previous_app


@contextmanager
def create_app_session(
    input: Input | None = None, output: Output | None = None
) -> Generator[AppSession, None, None]:
    """
    Create a separate AppSession.

    This is useful if there can be multiple individual ``AppSession``'s going
    on. Like in the case of a Telnet/SSH server.
    """
    # If no input/output is specified, fall back to the current input/output,
    # if there was one that was set/created for the current session.
    # (Note that we check `_input`/`_output` and not `input`/`output`. This is
    # because we don't want to accidentally create a new input/output objects
    # here and store it in the "parent" `AppSession`. Especially, when
    # combining pytest's `capsys` fixture and `create_app_session`, sys.stdin
    # and sys.stderr are patched for every test, so we don't want to leak
    # those outputs object across `AppSession`s.)
    if input is None:
        input = get_app_session()._input
    if output is None:
        output = get_app_session()._output

    # Create new `AppSession` and activate.
    session = AppSession(input=input, output=output)

    token = _current_app_session.set(session)
    try:
        yield session
    finally:
        _current_app_session.reset(token)


@contextmanager
def create_app_session_from_tty() -> Generator[AppSession, None, None]:
    """
    Create `AppSession` that always prefers the TTY input/output.

    Even if `sys.stdin` and `sys.stdout` are connected to input/output pipes,
    this will still use the terminal for interaction (because `sys.stderr` is
    still connected to the terminal).

    Usage::

        from prompt_toolkit.shortcuts import prompt

        with create_app_session_from_tty():
            prompt('>')
    """
    from prompt_toolkit.input.defaults import create_input
    from prompt_toolkit.output.defaults import create_output

    input = create_input(always_prefer_tty=True)
    output = create_output(always_prefer_tty=True)

    with create_app_session(input=input, output=output) as app_session:
        yield app_session
