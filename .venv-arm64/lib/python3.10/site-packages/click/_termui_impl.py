"""
This module contains implementations for the termui module. To keep the
import time of Click down, some infrequently used functionality is
placed in this module and only imported as needed.
"""

from __future__ import annotations

import collections.abc as cabc
import contextlib
import io
import math
import os
import shlex
import sys
import time
import typing as t
from gettext import gettext as _
from io import StringIO
from pathlib import Path
from types import TracebackType

from ._compat import _default_text_stdout
from ._compat import CYGWIN
from ._compat import get_best_encoding
from ._compat import isatty
from ._compat import strip_ansi
from ._compat import term_len
from ._compat import WIN
from .exceptions import ClickException
from .utils import echo
from .utils import KeepOpenFile

V = t.TypeVar("V")


class _BufferedTextPagerStream(t.Protocol):
    buffer: t.BinaryIO


def _has_binary_buffer(
    stream: t.BinaryIO | t.TextIO,
) -> t.TypeGuard[_BufferedTextPagerStream]:
    # TextIO is wider than TextIOWrapper; text-only streams such as StringIO
    # are valid TextIO values but do not expose a binary buffer to wrap.
    return getattr(stream, "buffer", None) is not None


if os.name == "nt":
    BEFORE_BAR = "\r"
    AFTER_BAR = "\n"
else:
    BEFORE_BAR = "\r\033[?25l"
    AFTER_BAR = "\033[?25h\n"


class ProgressBar(t.Generic[V]):
    def __init__(
        self,
        iterable: cabc.Iterable[V] | None,
        length: int | None = None,
        fill_char: str = "#",
        empty_char: str = " ",
        bar_template: str = "%(bar)s",
        info_sep: str = "  ",
        hidden: bool = False,
        show_eta: bool = True,
        show_percent: bool | None = None,
        show_pos: bool = False,
        item_show_func: t.Callable[[V | None], str | None] | None = None,
        label: str | None = None,
        file: t.TextIO | None = None,
        color: bool | None = None,
        update_min_steps: int = 1,
        width: int = 30,
    ) -> None:
        self.fill_char = fill_char
        self.empty_char = empty_char
        self.bar_template = bar_template
        self.info_sep = info_sep
        self.hidden = hidden
        self.show_eta = show_eta
        self.show_percent = show_percent
        self.show_pos = show_pos
        self.item_show_func = item_show_func
        self.label: str = label or ""

        if file is None:
            file = _default_text_stdout()

            # There are no standard streams attached to write to. For example,
            # pythonw on Windows.
            if file is None:
                file = StringIO()

        self.file = file
        self.color = color
        self.update_min_steps = update_min_steps
        self._completed_intervals = 0
        self.width: int = width
        self.autowidth: bool = width == 0

        if length is None:
            from operator import length_hint

            length = length_hint(iterable, -1)

            if length == -1:
                length = None
        if iterable is None:
            if length is None:
                raise TypeError("iterable or length is required")
            iterable = t.cast("cabc.Iterable[V]", range(length))
        self.iter: cabc.Iterable[V] = iter(iterable)
        self.length = length
        self.pos: int = 0
        self.avg: list[float] = []
        self.last_eta: float
        self.start: float
        self.start = self.last_eta = time.time()
        self.eta_known: bool = False
        self.finished: bool = False
        self.max_width: int | None = None
        self.entered: bool = False
        self.current_item: V | None = None
        self._is_atty = isatty(self.file)
        self._last_line: str | None = None

    def __enter__(self) -> ProgressBar[V]:
        self.entered = True
        self.render_progress()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.render_finish()

    def __iter__(self) -> cabc.Iterator[V]:
        if not self.entered:
            raise RuntimeError("You need to use progress bars in a with block.")
        self.render_progress()
        return self.generator()

    def __next__(self) -> V:
        # Iteration is defined in terms of a generator function,
        # returned by iter(self); use that to define next(). This works
        # because `self.iter` is an iterable consumed by that generator,
        # so it is re-entry safe. Calling `next(self.generator())`
        # twice works and does "what you want".
        return next(iter(self))

    def render_finish(self) -> None:
        if self.hidden or not self._is_atty:
            return
        self.file.write(AFTER_BAR)
        self.file.flush()

    @property
    def pct(self) -> float:
        if self.finished:
            return 1.0
        return min(self.pos / (float(self.length or 1) or 1), 1.0)

    @property
    def time_per_iteration(self) -> float:
        if not self.avg:
            return 0.0
        return sum(self.avg) / float(len(self.avg))

    @property
    def eta(self) -> float:
        if self.length is not None and not self.finished:
            return self.time_per_iteration * (self.length - self.pos)
        return 0.0

    def format_eta(self) -> str:
        if self.eta_known:
            t = int(self.eta)
            seconds = t % 60
            t //= 60
            minutes = t % 60
            t //= 60
            hours = t % 24
            t //= 24
            if t > 0:
                return "{d}{day_label} {h:02}:{m:02}:{s:02}".format(
                    d=t,
                    day_label=_("d"),
                    h=hours,
                    m=minutes,
                    s=seconds,
                )
            else:
                return f"{hours:02}:{minutes:02}:{seconds:02}"
        return ""

    def format_pos(self) -> str:
        pos = str(self.pos)
        if self.length is not None:
            pos += f"/{self.length}"
        return pos

    def format_pct(self) -> str:
        return f"{int(self.pct * 100): 4}%"[1:]

    def format_bar(self) -> str:
        if self.length is not None:
            bar_length = int(self.pct * self.width)
            bar = self.fill_char * bar_length
            bar += self.empty_char * (self.width - bar_length)
        elif self.finished:
            bar = self.fill_char * self.width
        else:
            chars = list(self.empty_char * (self.width or 1))
            if self.time_per_iteration != 0:
                chars[
                    int(
                        (math.cos(self.pos * self.time_per_iteration) / 2.0 + 0.5)
                        * self.width
                    )
                ] = self.fill_char
            bar = "".join(chars)
        return bar

    def format_progress_line(self) -> str:
        show_percent = self.show_percent

        info_bits = []
        if self.length is not None and show_percent is None:
            show_percent = not self.show_pos

        if self.show_pos:
            info_bits.append(self.format_pos())
        if show_percent:
            info_bits.append(self.format_pct())
        if self.show_eta and self.eta_known and not self.finished:
            info_bits.append(self.format_eta())
        if self.item_show_func is not None:
            item_info = self.item_show_func(self.current_item)
            if item_info is not None:
                info_bits.append(item_info)

        return (
            self.bar_template
            % {
                "label": self.label,
                "bar": self.format_bar(),
                "info": self.info_sep.join(info_bits),
            }
        ).rstrip()

    def render_progress(self) -> None:
        if self.hidden:
            return

        if not self._is_atty:
            # Only output the label once if the output is not a TTY.
            if self._last_line != self.label:
                self._last_line = self.label
                echo(self.label, file=self.file, color=self.color)
            return

        buf = []
        # Update width in case the terminal has been resized
        if self.autowidth:
            import shutil

            old_width = self.width
            self.width = 0
            clutter_length = term_len(self.format_progress_line())
            new_width = max(0, shutil.get_terminal_size().columns - clutter_length)
            if new_width < old_width and self.max_width is not None:
                buf.append(BEFORE_BAR)
                buf.append(" " * self.max_width)
                self.max_width = new_width
            self.width = new_width

        clear_width = self.width
        if self.max_width is not None:
            clear_width = self.max_width

        buf.append(BEFORE_BAR)
        line = self.format_progress_line()
        line_len = term_len(line)
        if self.max_width is None or self.max_width < line_len:
            self.max_width = line_len

        buf.append(line)
        buf.append(" " * (clear_width - line_len))
        line = "".join(buf)
        # Render the line only if it changed.

        if line != self._last_line:
            self._last_line = line
            echo(line, file=self.file, color=self.color, nl=False)
            self.file.flush()

    def make_step(self, n_steps: int) -> None:
        self.pos += n_steps
        if self.length is not None and self.pos >= self.length:
            self.finished = True

        if (time.time() - self.last_eta) < 1.0:
            return

        self.last_eta = time.time()

        # self.avg is a rolling list of length <= 7 of steps where steps are
        # defined as time elapsed divided by the total progress through
        # self.length.
        if self.pos:
            step = (time.time() - self.start) / self.pos
        else:
            step = time.time() - self.start

        self.avg = self.avg[-6:] + [step]

        self.eta_known = self.length is not None

    def update(self, n_steps: int, current_item: V | None = None) -> None:
        """Update the progress bar by advancing a specified number of
        steps, and optionally set the ``current_item`` for this new
        position.

        :param n_steps: Number of steps to advance.
        :param current_item: Optional item to set as ``current_item``
            for the updated position.

        .. versionchanged:: 8.0
            Added the ``current_item`` optional parameter.

        .. versionchanged:: 8.0
            Only render when the number of steps meets the
            ``update_min_steps`` threshold.
        """
        if current_item is not None:
            self.current_item = current_item

        self._completed_intervals += n_steps

        if self._completed_intervals >= self.update_min_steps:
            self.make_step(self._completed_intervals)
            self.render_progress()
            self._completed_intervals = 0

    def finish(self) -> None:
        self.eta_known = False
        self.current_item = None
        self.finished = True

    def generator(self) -> cabc.Iterator[V]:
        """Return a generator which yields the items added to the bar
        during construction, and updates the progress bar *after* the
        yielded block returns.
        """
        # WARNING: the iterator interface for `ProgressBar` relies on
        # this and only works because this is a simple generator which
        # doesn't create or manage additional state. If this function
        # changes, the impact should be evaluated both against
        # `iter(bar)` and `next(bar)`. `next()` in particular may call
        # `self.generator()` repeatedly, and this must remain safe in
        # order for that interface to work.
        if not self.entered:
            raise RuntimeError("You need to use progress bars in a with block.")

        if not self._is_atty:
            yield from self.iter
        else:
            for rv in self.iter:
                self.current_item = rv

                # This allows show_item_func to be updated before the
                # item is processed. Only trigger at the beginning of
                # the update interval.
                if self._completed_intervals == 0:
                    self.render_progress()

                yield rv
                self.update(1)

            self.finish()
            self.render_progress()


class MaybeStripAnsi(io.TextIOWrapper):
    def __init__(self, stream: t.IO[bytes], *, color: bool, **kwargs: t.Any):
        super().__init__(stream, **kwargs)
        self.color = color

    def write(self, text: str) -> int:
        if not self.color:
            text = strip_ansi(text)
        return super().write(text)


def _pager_contextmanager(
    color: bool | None = None,
) -> t.ContextManager[tuple[t.BinaryIO | t.TextIO, str, bool]]:
    """Decide what method to use for paging through text."""
    stdout = _default_text_stdout()

    # There are no standard streams attached to write to. For example,
    # pythonw on Windows.
    if stdout is None:
        stdout = StringIO()

    if not isatty(sys.stdin) or not isatty(stdout):
        return _nullpager(stdout, color)

    # Split using POSIX mode (the default) so that quote characters are
    # stripped from tokens and quoted Windows paths are preserved.
    # Non-POSIX mode retains quotes in tokens, and wrapping tokens
    # with shlex.quote re-introduces quoting issues on Windows.
    pager_cmd_parts = shlex.split(os.environ.get("PAGER", ""))
    if pager_cmd_parts:
        if WIN:
            return _tempfilepager(pager_cmd_parts, color)
        return _pipepager(pager_cmd_parts, color)

    if os.environ.get("TERM") in ("dumb", "emacs"):
        return _nullpager(stdout, color)
    if WIN or sys.platform.startswith("os2"):
        return _tempfilepager(["more"], color)
    return _pipepager(["less"], color)


@contextlib.contextmanager
def get_pager_file(color: bool | None = None) -> t.Generator[t.TextIO, None, None]:
    """Context manager.

    Yields a writable file-like object which can be used as an output pager.

    .. versionadded:: 8.4.0

    :param color: controls if the pager supports ANSI colors or not.  The
                  default is autodetection.
    """
    with _pager_contextmanager(color=color) as (stream, encoding, color):
        # Split streams by capabilities rather than the abstract TextIO /
        # BinaryIO annotations: buffered text streams can be unwrapped to bytes,
        # while other streams are yielded as-is.
        wrapper: MaybeStripAnsi | None = None
        if _has_binary_buffer(stream):
            # Text stream backed by a binary buffer.
            wrapper = MaybeStripAnsi(stream.buffer, color=color, encoding=encoding)
            stream = wrapper
        try:
            # Narrow the BinaryIO | TextIO union that _pager_contextmanager
            # yields; the caller writes text to the pager.
            yield t.cast(t.TextIO, stream)
        finally:
            try:
                stream.flush()
            finally:
                # Hand the binary buffer back to the pager that produced it
                # rather than letting this TextIOWrapper close it on garbage
                # collection. The pager owns the buffer's lifecycle: subprocess
                # pipes and temp files are closed by their own helpers, while a
                # borrowed stdout must stay open for the caller. detach() runs
                # even if flush() raised, so the buffer is never closed here.
                if wrapper is not None:
                    wrapper.detach()


@contextlib.contextmanager
def _pipepager(
    cmd_parts: list[str], color: bool | None = None
) -> t.Iterator[tuple[t.BinaryIO | t.TextIO, str, bool]]:
    """Page through text by feeding it to another program.

    Invokes the pager via :class:`subprocess.Popen` with an ``argv`` list
    produced by :func:`shlex.split`. The command is resolved to an absolute
    path with :func:`shutil.which` as recommended by the
    :mod:`subprocess` docs for Windows compatibility.

    Invoking a pager through this might support colors: if piping to
    ``less`` and the user hasn't decided on colors, ``LESS=-R`` is set
    automatically.
    """
    # Split the command into the invoked CLI and its parameters.
    if not cmd_parts:
        # No usable pager: fall back to stdout through _nullpager so it gets the
        # same borrowed-stream handling and the caller's stream is not closed.
        stdout = _default_text_stdout() or StringIO()
        with _nullpager(stdout, color) as rv:
            yield rv
        return

    import shutil

    cmd = cmd_parts[0]
    cmd_params = cmd_parts[1:]

    cmd_filepath = shutil.which(cmd)
    if not cmd_filepath:
        # No usable pager: fall back to stdout through _nullpager so it gets the
        # same borrowed-stream handling and the caller's stream is not closed.
        stdout = _default_text_stdout() or StringIO()
        with _nullpager(stdout, color) as rv:
            yield rv
        return

    # Produces a normalized absolute path string.
    # multi-call binaries such as busybox derive their identity from the symlink
    # less -> busybox. resolve() causes them to misbehave. (eg. less becomes busybox)
    cmd_path = Path(cmd_filepath).absolute()
    cmd_name = cmd_path.name

    import subprocess

    # Make a local copy of the environment to not affect the global one.
    env = dict(os.environ)

    # If we're piping to less and the user hasn't decided on colors, we enable
    # them by default we find the -R flag in the command line arguments.
    if color is None and cmd_name == "less":
        less_flags = f"{os.environ.get('LESS', '')}{' '.join(cmd_params)}"
        if not less_flags:
            env["LESS"] = "-R"
            color = True
        elif "r" in less_flags or "R" in less_flags:
            color = True

    if color is None:
        color = False

    c = subprocess.Popen(
        [str(cmd_path)] + cmd_params,
        shell=False,
        stdin=subprocess.PIPE,
        env=env,
        errors="replace",
        text=True,
    )
    stdin = t.cast(t.BinaryIO, c.stdin)
    encoding = get_best_encoding(stdin)
    try:
        yield stdin, encoding, color
    except BrokenPipeError:
        # In case the pager exited unexpectedly, ignore the broken pipe error.
        pass
    except Exception as e:
        # In case there is an exception we want to close the pager immediately
        # and let the caller handle it.
        # Otherwise the pager will keep running, and the user may not notice
        # the error message, or worse yet it may leave the terminal in a broken state.
        c.terminate()
        raise e
    finally:
        # We must close stdin and wait for the pager to exit before we continue
        try:
            stdin.close()
        # Close implies flush, so it might throw a BrokenPipeError if the pager
        # process exited already.
        except BrokenPipeError:
            pass

        # Less doesn't respect ^C, but catches it for its own UI purposes (aborting
        # search or other commands inside less).
        #
        # That means when the user hits ^C, the parent process (click) terminates,
        # but less is still alive, paging the output and messing up the terminal.
        #
        # If the user wants to make the pager exit on ^C, they should set
        # `LESS='-K'`. It's not our decision to make.
        while True:
            try:
                c.wait()
            except KeyboardInterrupt:
                pass
            else:
                break


@contextlib.contextmanager
def _tempfilepager(
    cmd_parts: list[str], color: bool | None = None
) -> t.Iterator[tuple[t.BinaryIO | t.TextIO, str, bool]]:
    """Page through text by invoking a program on a temporary file.

    Used as the primary pager strategy on Windows (where piping to
    ``more`` adds spurious ``\\r\\n``), and as a fallback on other
    platforms. The command is resolved to an absolute path with
    :func:`shutil.which`.
    """
    # Split the command into the invoked CLI and its parameters.
    if not cmd_parts:
        # No usable pager: fall back to stdout through _nullpager so it gets the
        # same borrowed-stream handling and the caller's stream is not closed.
        stdout = _default_text_stdout() or StringIO()
        with _nullpager(stdout, color) as rv:
            yield rv
        return

    import shutil
    import subprocess

    cmd = cmd_parts[0]

    cmd_filepath = shutil.which(cmd)
    if not cmd_filepath:
        # No usable pager: fall back to stdout through _nullpager so it gets the
        # same borrowed-stream handling and the caller's stream is not closed.
        stdout = _default_text_stdout() or StringIO()
        with _nullpager(stdout, color) as rv:
            yield rv
        return

    # Produces a normalized absolute path string.
    # multi-call binaries such as busybox derive their identity from the symlink
    # less -> busybox. resolve() causes them to misbehave. (eg. less becomes busybox)
    cmd_path = Path(cmd_filepath).absolute()

    import tempfile

    encoding = get_best_encoding(sys.stdout)
    if color is None:
        color = False
    # On Windows, NamedTemporaryFile cannot be opened by another process
    # while Python still has it open, so we use delete=False and clean up manually
    # rather than using a contextmanager here.
    f = tempfile.NamedTemporaryFile(mode="wb", delete=False)
    try:
        yield t.cast(t.BinaryIO, f), encoding, color
        f.flush()
        f.close()
        subprocess.call([str(cmd_path), f.name])
    finally:
        os.unlink(f.name)


@contextlib.contextmanager
def _nullpager(
    stream: t.TextIO, color: bool | None = None
) -> t.Iterator[tuple[t.TextIO, str, bool]]:
    """Simply print unformatted text. This is the ultimate fallback. Don't close the
    output stream in this case, since it's coming from elsewhere rather than our
    internal helpers.

    The stream is wrapped in :class:`~click.utils.KeepOpenFile` so that, as a
    borrowed stream, it is not closed by a ``with`` block. The wrapper that
    :func:`get_pager_file` builds around it is detached rather than closed.
    """
    encoding = get_best_encoding(stream)

    if color is None:
        color = False

    yield KeepOpenFile(stream), encoding, color  # type: ignore[misc]


class Editor:
    def __init__(
        self,
        editor: str | None = None,
        env: cabc.Mapping[str, str] | None = None,
        require_save: bool = True,
        extension: str = ".txt",
    ) -> None:
        self.editor = editor
        self.env = env
        self.require_save = require_save
        self.extension = extension

    def get_editor(self) -> str:
        if self.editor is not None:
            return self.editor
        for key in "VISUAL", "EDITOR":
            rv = os.environ.get(key)
            if rv:
                return rv
        if WIN:
            return "notepad"

        from shutil import which

        for editor in "sensible-editor", "vim", "nano":
            if which(editor) is not None:
                return editor
        return "vi"

    def edit_files(self, filenames: cabc.Iterable[str]) -> None:
        """Open files in the user's editor."""
        import shlex
        import subprocess

        editor = self.get_editor()
        environ: dict[str, str] | None = None

        if self.env:
            environ = os.environ.copy()
            environ.update(self.env)

        try:
            # Split in POSIX mode (the default) for the same reasons as
            # in pager(): strips quotes from tokens and preserves quoted
            # Windows paths.
            c = subprocess.Popen(
                args=shlex.split(editor) + list(filenames),
                env=environ,
            )
            exit_code = c.wait()
            if exit_code != 0:
                raise ClickException(
                    _("{editor}: Editing failed").format(editor=editor)
                )
        except OSError as e:
            raise ClickException(
                _("{editor}: Editing failed: {e}").format(editor=editor, e=e)
            ) from e

    @t.overload
    def edit(self, text: bytes | bytearray) -> bytes | None: ...

    # We cannot know whether or not the type expected is str or bytes when None
    # is passed, so str is returned as that was what was done before.
    @t.overload
    def edit(self, text: str | None) -> str | None: ...

    def edit(self, text: str | bytes | bytearray | None) -> str | bytes | None:
        import tempfile

        if text is None:
            data: bytes | bytearray = b""
        elif isinstance(text, (bytes, bytearray)):
            data = text
        else:
            if text and not text.endswith("\n"):
                text += "\n"

            if WIN:
                data = text.replace("\n", "\r\n").encode("utf-8-sig")
            else:
                data = text.encode("utf-8")

        fd, name = tempfile.mkstemp(prefix="editor-", suffix=self.extension)
        f: t.BinaryIO

        try:
            with os.fdopen(fd, "wb") as f:
                f.write(data)

            # If the filesystem resolution is 1 second, like Mac OS
            # 10.12 Extended, or 2 seconds, like FAT32, and the editor
            # closes very fast, require_save can fail. Set the modified
            # time to be 2 seconds in the past to work around this.
            os.utime(name, (os.path.getatime(name), os.path.getmtime(name) - 2))
            # Depending on the resolution, the exact value might not be
            # recorded, so get the new recorded value.
            timestamp = os.path.getmtime(name)

            self.edit_files((name,))

            if self.require_save and os.path.getmtime(name) == timestamp:
                return None

            with open(name, "rb") as f:
                rv = f.read()

            if isinstance(text, (bytes, bytearray)):
                return rv

            return rv.decode("utf-8-sig").replace("\r\n", "\n")
        finally:
            os.unlink(name)


def open_url(url: str, wait: bool = False, locate: bool = False) -> int:
    import subprocess

    def _unquote_file(url: str) -> str:
        from urllib.parse import unquote

        if url.startswith("file://"):
            url = unquote(url[7:])

        return url

    if sys.platform == "darwin":
        args = ["open"]
        if wait:
            args.append("-W")
        if locate:
            args.append("-R")
        args.append(_unquote_file(url))
        null = open("/dev/null", "w")
        try:
            return subprocess.Popen(args, stderr=null).wait()
        finally:
            null.close()
    elif WIN:
        if locate:
            url = _unquote_file(url)
            args = ["explorer", "/select,", url]
            try:
                return subprocess.call(args)
            except OSError:
                return 127
        else:
            try:
                os.startfile(url)  # type: ignore[attr-defined]
            except OSError:
                return 127
            return 0
    elif CYGWIN:
        if locate:
            url = _unquote_file(url)
            args = ["cygstart", os.path.dirname(url)]
        else:
            args = ["cygstart"]
            if wait:
                args.append("-w")
            args.append(url)
        try:
            return subprocess.call(args)
        except OSError:
            # Command not found
            return 127

    try:
        if locate:
            url = os.path.dirname(_unquote_file(url)) or "."
        else:
            url = _unquote_file(url)
        c = subprocess.Popen(["xdg-open", url])
        if wait:
            return c.wait()
        return 0
    except OSError:
        if url.startswith(("http://", "https://")) and not locate and not wait:
            import webbrowser

            webbrowser.open(url)
            return 0
        return 1


def _translate_ch_to_exc(ch: str) -> None:
    if ch == "\x03":
        raise KeyboardInterrupt()

    if ch == "\x04" and not WIN:  # Unix-like, Ctrl+D
        raise EOFError()

    if ch == "\x1a" and WIN:  # Windows, Ctrl+Z
        raise EOFError()


if sys.platform == "win32":
    import msvcrt

    @contextlib.contextmanager
    def raw_terminal() -> cabc.Iterator[int]:
        yield -1

    def getchar(echo: bool) -> str:
        # The function `getch` will return a bytes object corresponding to
        # the pressed character. Since Windows 10 build 1803, it will also
        # return \x00 when called a second time after pressing a regular key.
        #
        # `getwch` does not share this probably-bugged behavior. Moreover, it
        # returns a Unicode object by default, which is what we want.
        #
        # Either of these functions will return \x00 or \xe0 to indicate
        # a special key, and you need to call the same function again to get
        # the "rest" of the code. The fun part is that \u00e0 is
        # "latin small letter a with grave", so if you type that on a French
        # keyboard, you _also_ get a \xe0.
        # E.g., consider the Up arrow. This returns \xe0 and then \x48. The
        # resulting Unicode string reads as "a with grave" + "capital H".
        # This is indistinguishable from when the user actually types
        # "a with grave" and then "capital H".
        #
        # When \xe0 is returned, we assume it's part of a special-key sequence
        # and call `getwch` again, but that means that when the user types
        # the \u00e0 character, `getchar` doesn't return until a second
        # character is typed.
        # The alternative is returning immediately, but that would mess up
        # cross-platform handling of arrow keys and others that start with
        # \xe0. Another option is using `getch`, but then we can't reliably
        # read non-ASCII characters, because return values of `getch` are
        # limited to the current 8-bit codepage.
        #
        # Anyway, Click doesn't claim to do this Right(tm), and using `getwch`
        # is doing the right thing in more situations than with `getch`.

        if echo:
            func = t.cast(t.Callable[[], str], msvcrt.getwche)
        else:
            func = t.cast(t.Callable[[], str], msvcrt.getwch)

        rv = func()

        if rv in ("\x00", "\xe0"):
            # \x00 and \xe0 are control characters that indicate special key,
            # see above.
            rv += func()

        _translate_ch_to_exc(rv)
        return rv

else:
    import termios
    import tty

    @contextlib.contextmanager
    def raw_terminal() -> cabc.Iterator[int]:
        f: t.TextIO | None
        fd: int

        if not isatty(sys.stdin):
            f = open("/dev/tty")
            fd = f.fileno()
        else:
            fd = sys.stdin.fileno()
            f = None

        try:
            old_settings = termios.tcgetattr(fd)

            try:
                tty.setraw(fd)
                yield fd
            finally:
                termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)
                sys.stdout.flush()

                if f is not None:
                    f.close()
        except termios.error:
            pass

    def getchar(echo: bool) -> str:
        with raw_terminal() as fd:
            ch = os.read(fd, 32).decode(get_best_encoding(sys.stdin), "replace")

            if echo and isatty(sys.stdout):
                sys.stdout.write(ch)

            _translate_ch_to_exc(ch)
            return ch
