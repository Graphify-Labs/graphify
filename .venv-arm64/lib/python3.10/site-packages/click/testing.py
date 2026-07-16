from __future__ import annotations

import collections.abc as cabc
import contextlib
import io
import os
import pdb
import shlex
import sys
import tempfile
import typing as t
from types import TracebackType

from . import _compat
from . import formatting
from . import termui
from . import utils
from ._compat import _find_binary_reader

if t.TYPE_CHECKING:
    from _typeshed import ReadableBuffer

    from .core import Command

if sys.platform == "win32":
    CaptureMode: t.TypeAlias = t.Literal["sys"]  # pyright: ignore[reportRedeclaration]
else:
    CaptureMode: t.TypeAlias = t.Literal["sys", "fd"]  # pyright: ignore[reportRedeclaration]
ExceptionInfo: t.TypeAlias = tuple[type[BaseException], BaseException, TracebackType]


class EchoingStdin:
    _input: t.BinaryIO
    _output: t.BinaryIO
    _paused: bool

    def __init__(self, input: t.BinaryIO, output: t.BinaryIO) -> None:
        self._input = input
        self._output = output
        self._paused = False

    def __getattr__(self, x: str) -> t.Any:
        return getattr(self._input, x)

    def _echo(self, rv: bytes) -> bytes:
        if not self._paused:
            self._output.write(rv)

        return rv

    def read(self, n: int = -1) -> bytes:
        return self._echo(self._input.read(n))

    def read1(self, n: int = -1) -> bytes:
        return self._echo(self._input.read1(n))  # type: ignore

    def readline(self, n: int = -1) -> bytes:
        return self._echo(self._input.readline(n))

    def readlines(self) -> list[bytes]:
        return [self._echo(x) for x in self._input.readlines()]

    def __iter__(self) -> cabc.Iterator[bytes]:
        return iter(self._echo(x) for x in self._input)

    def __repr__(self) -> str:
        return repr(self._input)


@contextlib.contextmanager
def _pause_echo(stream: EchoingStdin | None) -> cabc.Generator[None]:
    if stream is None:
        yield
    else:
        stream._paused = True
        yield
        stream._paused = False


class _FDCapture:
    """Redirect a file descriptor to a temporary file for capture.

    Saves the current target of *targetfd* via :func:`os.dup`, then
    redirects it to a temporary file via :func:`os.dup2`. On
    :meth:`stop`, restores the original ``fd`` and returns the captured
    bytes. Inspired by Pytest's ``FDCapture``.

    .. versionadded:: 8.4.0
    """

    _targetfd: int
    saved_fd: int
    _tmpfile: t.BinaryIO | None

    def __init__(self, targetfd: int) -> None:
        self._targetfd = targetfd
        self.saved_fd = -1
        self._tmpfile = None

    def start(self) -> None:
        self.saved_fd = os.dup(self._targetfd)
        self._tmpfile = tempfile.TemporaryFile(buffering=0)
        os.dup2(self._tmpfile.fileno(), self._targetfd)

    def stop(self) -> bytes:
        assert self._tmpfile is not None, "_FDCapture.start() was not called"
        os.dup2(self.saved_fd, self._targetfd)
        os.close(self.saved_fd)
        self.saved_fd = -1
        self._tmpfile.seek(0)
        data = self._tmpfile.read()
        self._tmpfile.close()
        self._tmpfile = None
        return data


class BytesIOCopy(io.BytesIO):
    """Patch ``io.BytesIO`` to let the written stream be copied to another.

    .. versionadded:: 8.2
    """

    copy_to: io.BytesIO

    def __init__(self, copy_to: io.BytesIO) -> None:
        super().__init__()
        self.copy_to = copy_to

    def flush(self) -> None:
        super().flush()
        self.copy_to.flush()

    def write(self, b: ReadableBuffer) -> int:
        self.copy_to.write(b)
        return super().write(b)


class StreamMixer:
    """Mixes `<stdout>` and `<stderr>` streams.

    The result is available in the ``output`` attribute.

    .. versionadded:: 8.2
    """

    output: io.BytesIO
    stdout: BytesIOCopy
    stderr: BytesIOCopy

    def __init__(self) -> None:
        self.output = io.BytesIO()
        self.stdout = BytesIOCopy(copy_to=self.output)
        self.stderr = BytesIOCopy(copy_to=self.output)


class _NamedTextIOWrapper(io.TextIOWrapper):
    """A :class:`~io.TextIOWrapper` with custom ``name`` and ``mode``
    that does not close its underlying buffer.

    When ``CliRunner`` runs in ``fd`` mode, ``_original_fd`` is patched to
    point at the saved (pre-redirection) ``fd``, so C-level consumers that call
    :meth:`fileno` (like ``faulthandler`` or ``subprocess``) keep working. In
    the default ``sys`` mode ``_original_fd`` stays at ``-1`` and
    :meth:`fileno` raises :exc:`io.UnsupportedOperation`, matching the
    pre-``8.3.3`` behavior.
    """

    _name: str
    _mode: str
    _original_fd: int

    def __init__(
        self,
        buffer: t.BinaryIO,
        name: str,
        mode: str,
        **kwargs: t.Any,
    ) -> None:
        super().__init__(buffer, **kwargs)
        self._name = name
        self._mode = mode
        self._original_fd = -1

    def close(self) -> None:
        """The buffer this object contains belongs to some other object,
        so prevent the default ``__del__`` implementation from closing
        that buffer.

        .. versionadded:: 8.3.2
        """

    def fileno(self) -> int:
        """Return the file descriptor of the saved original stream when
        ``CliRunner`` runs in ``fd`` mode. Otherwise delegate to
        :class:`~io.TextIOWrapper`, which raises
        :exc:`io.UnsupportedOperation` for a ``BytesIO``-backed buffer.
        """
        if self._original_fd >= 0:
            return self._original_fd
        return super().fileno()

    @property
    def name(self) -> str:
        return self._name

    @property
    def mode(self) -> str:
        return self._mode


def make_input_stream(
    input: str | bytes | t.IO[t.Any] | None, charset: str
) -> t.BinaryIO:
    # Is already an input stream.
    if hasattr(input, "read"):
        rv = _find_binary_reader(t.cast("t.IO[t.Any]", input))

        if rv is not None:
            return rv

        raise TypeError("Could not find binary reader for input stream.")

    if input is None:
        input = b""
    elif isinstance(input, str):
        input = input.encode(charset)

    return io.BytesIO(input)


class Result:
    """Holds the captured result of an invoked CLI script.

    :param runner: The runner that created the result
    :param stdout_bytes: The standard output as bytes.
    :param stderr_bytes: The standard error as bytes.
    :param output_bytes: A mix of ``stdout_bytes`` and ``stderr_bytes``, as the
        user would see  it in its terminal.
    :param return_value: The value returned from the invoked command.
    :param exit_code: The exit code as integer.
    :param exception: The exception that happened if one did.
    :param exc_info: Exception information (exception type, exception instance,
        traceback type).

    .. versionchanged:: 8.2
        ``stderr_bytes`` no longer optional, ``output_bytes`` introduced and
        ``mix_stderr`` has been removed.

    .. versionadded:: 8.0
        Added ``return_value``.
    """

    runner: CliRunner
    stdout_bytes: bytes
    stderr_bytes: bytes
    output_bytes: bytes
    return_value: t.Any
    exit_code: int
    exception: BaseException | None
    exc_info: ExceptionInfo | None

    def __init__(
        self,
        runner: CliRunner,
        stdout_bytes: bytes,
        stderr_bytes: bytes,
        output_bytes: bytes,
        return_value: t.Any,
        exit_code: int,
        exception: BaseException | None,
        exc_info: ExceptionInfo | None = None,
    ) -> None:
        self.runner = runner
        self.stdout_bytes = stdout_bytes
        self.stderr_bytes = stderr_bytes
        self.output_bytes = output_bytes
        self.return_value = return_value
        self.exit_code = exit_code
        self.exception = exception
        self.exc_info = exc_info

    @property
    def output(self) -> str:
        """The terminal output as unicode string, as the user would see it.

        .. versionchanged:: 8.2
            No longer a proxy for ``self.stdout``. Now has its own independent stream
            that is mixing `<stdout>` and `<stderr>`, in the order they were written.
        """
        return self.output_bytes.decode(self.runner.charset, "replace").replace(
            "\r\n", "\n"
        )

    @property
    def stdout(self) -> str:
        """The standard output as unicode string."""
        return self.stdout_bytes.decode(self.runner.charset, "replace").replace(
            "\r\n", "\n"
        )

    @property
    def stderr(self) -> str:
        """The standard error as unicode string.

        .. versionchanged:: 8.2
            No longer raise an exception, always returns the `<stderr>` string.
        """
        return self.stderr_bytes.decode(self.runner.charset, "replace").replace(
            "\r\n", "\n"
        )

    def __repr__(self) -> str:
        exc_str = repr(self.exception) if self.exception else "okay"
        return f"<{type(self).__name__} {exc_str}>"


class CliRunner:
    """The CLI runner provides functionality to invoke a Click command line
    script for unittesting purposes in a isolated environment.  This only
    works in single-threaded systems without any concurrency as it changes the
    global interpreter state.

    :param charset: the character set for the input and output data.
    :param env: a dictionary with environment variables for overriding.
    :param echo_stdin: if this is set to `True`, then reading from `<stdin>` writes
                       to `<stdout>`.  This is useful for showing examples in
                       some circumstances.  Note that regular prompts
                       will automatically echo the input.
    :param catch_exceptions: Whether to catch any exceptions other than
                             ``SystemExit`` when running :meth:`~CliRunner.invoke`.
    :param capture: Selects the output capture strategy. ``sys`` (default)
        captures Python-level writes only and leaves
        :meth:`sys.stdout.fileno` raising :exc:`io.UnsupportedOperation`, so
        user code that calls :func:`os.dup2` on ``sys.stdout.fileno()`` cannot
        clobber the host runner's stdout. ``fd`` redirects file descriptors
        ``1`` and ``2`` via :func:`os.dup2` to a temporary file, also catching
        output from stale stream references, C extensions, and subprocesses.
        ``fd`` is not supported on Windows.

    .. versionchanged:: 8.4.0
        Added the ``capture`` parameter. The default ``sys`` mode no longer
        exposes the original fd through :meth:`fileno`, reverting the change
        introduced in ``8.3.3`` that broke Pytest's ``fd``-level capture
        teardown. Use ``capture="fd"`` to restore that behavior with proper
        isolation. :issue:`3384`

    .. versionchanged:: 8.2
        Added the ``catch_exceptions`` parameter.

    .. versionchanged:: 8.2
        ``mix_stderr`` parameter has been removed.
    """

    charset: str
    env: cabc.Mapping[str, str | None]
    echo_stdin: bool
    catch_exceptions: bool
    capture: CaptureMode

    def __init__(
        self,
        charset: str = "utf-8",
        env: cabc.Mapping[str, str | None] | None = None,
        echo_stdin: bool = False,
        catch_exceptions: bool = True,
        capture: CaptureMode = "sys",
    ) -> None:
        if capture not in {"sys", "fd"}:
            raise ValueError(
                f"capture={capture!r} is not valid. Choose from 'sys' or 'fd'."
            )
        if capture == "fd" and sys.platform == "win32":
            raise ValueError(
                f"capture={capture!r} is not supported on Windows. Use 'sys'."
            )
        self.charset = charset
        self.env = env or {}
        self.echo_stdin = echo_stdin
        self.catch_exceptions = catch_exceptions
        self.capture = capture

    def get_default_prog_name(self, cli: Command) -> str:
        """Given a command object it will return the default program name
        for it.  The default is the `name` attribute or ``"root"`` if not
        set.
        """
        return cli.name or "root"

    def make_env(
        self, overrides: cabc.Mapping[str, str | None] | None = None
    ) -> cabc.Mapping[str, str | None]:
        """Returns the environment overrides for invoking a script."""
        rv = dict(self.env)
        if overrides:
            rv.update(overrides)
        return rv

    @contextlib.contextmanager
    def isolation(
        self,
        input: str | bytes | t.IO[t.Any] | None = None,
        env: cabc.Mapping[str, str | None] | None = None,
        color: bool = False,
    ) -> cabc.Generator[tuple[io.BytesIO, io.BytesIO, io.BytesIO]]:
        """A context manager that sets up the isolation for invoking of a
        command line tool.  This sets up `<stdin>` with the given input data
        and `os.environ` with the overrides from the given dictionary.
        This also rebinds some internals in Click to be mocked (like the
        prompt functionality).

        This is automatically done in the :meth:`invoke` method.

        :param input: the input stream to put into `sys.stdin`.
        :param env: the environment overrides as dictionary.
        :param color: whether the output should contain color codes. The
                      application can still override this explicitly.

        .. versionadded:: 8.2
            An additional output stream is returned, which is a mix of
            `<stdout>` and `<stderr>` streams.

        .. versionchanged:: 8.2
            Always returns the `<stderr>` stream.

        .. versionchanged:: 8.0
            `<stderr>` is opened with ``errors="backslashreplace"``
            instead of the default ``"strict"``.

        .. versionchanged:: 4.0
            Added the ``color`` parameter.
        """
        bytes_input = make_input_stream(input, self.charset)
        echo_input = None

        old_stdin = sys.stdin
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        old_forced_width = formatting.FORCED_WIDTH
        formatting.FORCED_WIDTH = 80

        env = self.make_env(env)

        stream_mixer = StreamMixer()

        if self.echo_stdin:
            bytes_input = echo_input = t.cast(
                t.BinaryIO, EchoingStdin(bytes_input, stream_mixer.stdout)
            )

        sys.stdin = text_input = _NamedTextIOWrapper(
            bytes_input, encoding=self.charset, name="<stdin>", mode="r"
        )

        if self.echo_stdin:
            # Force unbuffered reads, otherwise TextIOWrapper reads a
            # large chunk which is echoed early.
            text_input._CHUNK_SIZE = 1  # type: ignore

        sys.stdout = _NamedTextIOWrapper(
            stream_mixer.stdout,
            encoding=self.charset,
            name="<stdout>",
            mode="w",
        )

        sys.stderr = _NamedTextIOWrapper(
            stream_mixer.stderr,
            encoding=self.charset,
            name="<stderr>",
            mode="w",
            errors="backslashreplace",
        )

        @_pause_echo(echo_input)  # type: ignore
        def visible_input(prompt: str | None = None) -> str:
            sys.stdout.write(prompt or "")
            try:
                val = next(text_input).rstrip("\r\n")
            except StopIteration as e:
                raise EOFError() from e
            sys.stdout.write(f"{val}\n")
            sys.stdout.flush()
            return val

        @_pause_echo(echo_input)  # type: ignore
        def hidden_input(prompt: str | None = None) -> str:
            sys.stdout.write(f"{prompt or ''}\n")
            sys.stdout.flush()
            try:
                return next(text_input).rstrip("\r\n")
            except StopIteration as e:
                raise EOFError() from e

        @_pause_echo(echo_input)  # type: ignore
        def _getchar(echo: bool) -> str:
            char = sys.stdin.read(1)

            if echo:
                sys.stdout.write(char)

            sys.stdout.flush()
            return char

        default_color = color

        def should_strip_ansi(
            stream: t.IO[t.Any] | None = None, color: bool | None = None
        ) -> bool:
            if color is None:
                return not default_color
            return not color

        old_visible_prompt_func = termui.visible_prompt_func
        old_hidden_prompt_func = termui.hidden_prompt_func
        old__getchar_func = termui._getchar
        old_should_strip_ansi = utils.should_strip_ansi  # type: ignore
        old__compat_should_strip_ansi = _compat.should_strip_ansi
        old_pdb_init = pdb.Pdb.__init__
        termui.visible_prompt_func = visible_input
        termui.hidden_prompt_func = hidden_input
        termui._getchar = _getchar
        utils.should_strip_ansi = should_strip_ansi  # type: ignore
        _compat.should_strip_ansi = should_strip_ansi

        def _patched_pdb_init(
            self: pdb.Pdb,
            completekey: str = "tab",
            stdin: t.IO[str] | None = None,
            stdout: t.IO[str] | None = None,
            **kwargs: t.Any,
        ) -> None:
            """Default ``pdb.Pdb`` to real terminal streams during
            ``CliRunner`` isolation.

            Without this patch, ``pdb.Pdb.__init__`` inherits from
            ``cmd.Cmd`` which falls back to ``sys.stdin``/``sys.stdout``
            when no explicit streams are provided. During isolation
            those are ``BytesIO``-backed wrappers, so the debugger
            reads from an empty buffer and writes to captured output,
            making interactive debugging impossible.

            By defaulting to ``sys.__stdin__``/``sys.__stdout__`` (the
            original terminal streams Python preserves regardless of
            redirection), debuggers can interact with the user while
            ``click.echo`` output is still captured normally.

            This covers ``pdb.set_trace()``, ``breakpoint()``,
            ``pdb.post_mortem()``, and debuggers that subclass
            ``pdb.Pdb`` (ipdb, pdbpp). Explicit ``stdin``/``stdout``
            arguments are honored and not overridden. Debuggers that
            do not subclass ``pdb.Pdb`` (pudb, debugpy) are not
            covered.
            """
            if stdin is None:
                stdin = sys.__stdin__
            if stdout is None:
                stdout = sys.__stdout__
            old_pdb_init(
                self, completekey=completekey, stdin=stdin, stdout=stdout, **kwargs
            )

        pdb.Pdb.__init__ = _patched_pdb_init  # type: ignore[assignment]

        old_env = {}
        try:
            for key, value in env.items():
                old_env[key] = os.environ.get(key)
                if value is None:
                    try:
                        del os.environ[key]
                    except Exception:
                        pass
                else:
                    os.environ[key] = value
            yield (stream_mixer.stdout, stream_mixer.stderr, stream_mixer.output)
        finally:
            for key, value in old_env.items():
                if value is None:
                    try:
                        del os.environ[key]
                    except Exception:
                        pass
                else:
                    os.environ[key] = value
            sys.stdout = old_stdout
            sys.stderr = old_stderr
            sys.stdin = old_stdin
            termui.visible_prompt_func = old_visible_prompt_func
            termui.hidden_prompt_func = old_hidden_prompt_func
            termui._getchar = old__getchar_func
            utils.should_strip_ansi = old_should_strip_ansi  # type: ignore
            _compat.should_strip_ansi = old__compat_should_strip_ansi
            formatting.FORCED_WIDTH = old_forced_width
            pdb.Pdb.__init__ = old_pdb_init  # type: ignore[method-assign]

    def invoke(
        self,
        cli: Command,
        args: str | cabc.Sequence[str] | None = None,
        input: str | bytes | t.IO[t.Any] | None = None,
        env: cabc.Mapping[str, str | None] | None = None,
        catch_exceptions: bool | None = None,
        color: bool = False,
        **extra: t.Any,
    ) -> Result:
        """Invokes a command in an isolated environment.  The arguments are
        forwarded directly to the command line script, the `extra` keyword
        arguments are passed to the :meth:`~clickpkg.Command.main` function of
        the command.

        This returns a :class:`Result` object.

        :param cli: the command to invoke
        :param args: the arguments to invoke. It may be given as an iterable
                     or a string. When given as string it will be interpreted
                     as a Unix shell command. More details at
                     :func:`shlex.split`.
        :param input: the input data for `sys.stdin`.
        :param env: the environment overrides.
        :param catch_exceptions: Whether to catch any other exceptions than
                                 ``SystemExit``. If :data:`None`, the value
                                 from :class:`CliRunner` is used.
        :param extra: the keyword arguments to pass to :meth:`main`.
        :param color: whether the output should contain color codes. The
                      application can still override this explicitly.

        .. versionadded:: 8.2
            The result object has the ``output_bytes`` attribute with
            the mix of ``stdout_bytes`` and ``stderr_bytes``, as the user would
            see it in its terminal.

        .. versionchanged:: 8.2
            The result object always returns the ``stderr_bytes`` stream.

        .. versionchanged:: 8.0
            The result object has the ``return_value`` attribute with
            the value returned from the invoked command.

        .. versionchanged:: 4.0
            Added the ``color`` parameter.

        .. versionchanged:: 3.0
            Added the ``catch_exceptions`` parameter.

        .. versionchanged:: 3.0
            The result object has the ``exc_info`` attribute with the
            traceback if available.
        """
        exc_info = None
        if catch_exceptions is None:
            catch_exceptions = self.catch_exceptions

        # Set up fd capture before isolation replaces sys.stdout and sys.stderr.
        cap_out: _FDCapture | None = None
        cap_err: _FDCapture | None = None

        if self.capture == "fd":
            cap_out = _FDCapture(1)
            cap_err = _FDCapture(2)
            try:
                cap_out.start()
                cap_err.start()
            except OSError:
                cap_out = cap_err = None

        with self.isolation(input=input, env=env, color=color) as outstreams:
            # Point the captured streams' fileno() at the saved (original)
            # fd so that C-level consumers like faulthandler keep working
            # while fd 1/2 are redirected to the capture tmpfile.
            if cap_out is not None and cap_err is not None:
                sys.stdout._original_fd = cap_out.saved_fd  # type: ignore[union-attr]
                sys.stderr._original_fd = cap_err.saved_fd  # type: ignore[union-attr]

            return_value = None
            exception: BaseException | None = None
            exit_code = 0

            if isinstance(args, str):
                args = shlex.split(args)

            try:
                prog_name = extra.pop("prog_name")
            except KeyError:
                prog_name = self.get_default_prog_name(cli)

            try:
                return_value = cli.main(args=args or (), prog_name=prog_name, **extra)
            except SystemExit as e:
                exc_info = sys.exc_info()
                e_code = t.cast("int | t.Any | None", e.code)

                if e_code is None:
                    e_code = 0

                if e_code != 0:
                    exception = e

                if not isinstance(e_code, int):
                    sys.stdout.write(str(e_code))
                    sys.stdout.write("\n")
                    e_code = 1

                exit_code = e_code

            except Exception as e:
                if not catch_exceptions:
                    raise
                exception = e
                exit_code = 1
                exc_info = sys.exc_info()
            finally:
                sys.stdout.flush()
                sys.stderr.flush()

                # Stop fd capture and merge the captured bytes into
                # the stdout/stderr BytesIO streams. BytesIOCopy mirrors
                # those writes into outstreams[2] automatically.
                if cap_out is not None and cap_err is not None:
                    fd_out = cap_out.stop()
                    fd_err = cap_err.stop()
                    if fd_out:
                        outstreams[0].write(fd_out)
                    if fd_err:
                        outstreams[1].write(fd_err)

                stdout = outstreams[0].getvalue()
                stderr = outstreams[1].getvalue()
                output = outstreams[2].getvalue()

        return Result(
            runner=self,
            stdout_bytes=stdout,
            stderr_bytes=stderr,
            output_bytes=output,
            return_value=return_value,
            exit_code=exit_code,
            exception=exception,
            exc_info=exc_info,  # type: ignore
        )

    @contextlib.contextmanager
    def isolated_filesystem(
        self, temp_dir: str | os.PathLike[str] | None = None
    ) -> cabc.Generator[str]:
        """A context manager that creates a temporary directory and
        changes the current working directory to it. This isolates tests
        that affect the contents of the CWD to prevent them from
        interfering with each other.

        :param temp_dir: Create the temporary directory under this
            directory. If given, the created directory is not removed
            when exiting.

        .. versionchanged:: 8.0
            Added the ``temp_dir`` parameter.
        """
        cwd = os.getcwd()
        dt = tempfile.mkdtemp(dir=temp_dir)
        os.chdir(dt)

        try:
            yield dt
        finally:
            os.chdir(cwd)

            if temp_dir is None:
                import shutil

                try:
                    shutil.rmtree(dt)
                except OSError:
                    pass
