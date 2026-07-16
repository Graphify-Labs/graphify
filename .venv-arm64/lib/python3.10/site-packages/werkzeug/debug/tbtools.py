from __future__ import annotations

import itertools
import linecache
import os
import re
import sys
import sysconfig
import traceback
import typing as t

from markupsafe import escape

from ..utils import cached_property
from .console import Console

HEADER = """\
<!doctype html>
<html lang=en>
  <head>
    <title>%(title)s // Werkzeug Debugger</title>
    <link rel="stylesheet" href="?__debugger__=yes&amp;cmd=resource&amp;f=style.css">
    <link rel="shortcut icon"
        href="?__debugger__=yes&amp;cmd=resource&amp;f=console.png">
    <script src="?__debugger__=yes&amp;cmd=resource&amp;f=debugger.js"></script>
    <script>
      var CONSOLE_MODE = %(console)s,
          EVALEX = %(evalex)s,
          EVALEX_TRUSTED = %(evalex_trusted)s,
          SECRET = "%(secret)s";
    </script>
  </head>
  <body style="background-color: #fff">
    <div class="debugger">
"""

FOOTER = """\
      <div class="footer">
        Brought to you by <strong class="arthur">DON'T PANIC</strong>, your
        friendly Werkzeug powered traceback interpreter.
      </div>
    </div>

    <div class="pin-prompt">
      <div class="inner">
        <h3>Console Locked</h3>
        <p>
          The console is locked and needs to be unlocked by entering the PIN.
          You can find the PIN printed out on the standard output of your
          shell that runs the server.
        <form>
          <p>PIN:
            <input type=text name=pin size=14>
            <input type=submit name=btn value="Confirm Pin">
        </form>
      </div>
    </div>
  </body>
</html>
"""

PAGE_HTML = (
    HEADER
    + """\
<h1>%(exception_type)s</h1>
<div class="detail">
  <p class="errormsg">%(exception)s</p>
</div>
<h2 class="traceback">Traceback <em>(most recent call last)</em></h2>
%(summary)s
<div class="plain">
    <p>
      This is the Copy/Paste friendly version of the traceback.
    </p>
    <textarea cols="50" rows="10" name="code" readonly>%(plaintext)s</textarea>
</div>
<div class="explanation">
  The debugger caught an exception in your WSGI application.  You can now
  look at the traceback which led to the error.  <span class="nojavascript">
  If you enable JavaScript you can also use additional features such as code
  execution (if the evalex feature is enabled), automatic pasting of the
  exceptions and much more.</span>
</div>
"""
    + FOOTER
    + """
<!--

%(plaintext_cs)s

-->
"""
)

CONSOLE_HTML = (
    HEADER
    + """\
<h1>Interactive Console</h1>
<div class="explanation">
In this console you can execute Python expressions in the context of the
application.  The initial namespace was created by the debugger automatically.
</div>
<div class="console"><div class="inner">The Console requires JavaScript.</div></div>
"""
    + FOOTER
)

SUMMARY_HTML = """\
<div class="%(classes)s">
  %(title)s
  <ul>%(frames)s</ul>
  %(description)s
</div>
"""

FRAME_HTML = """\
<div class="frame" id="frame-%(id)d">
  <h4>File <cite class="filename">"%(filename)s"</cite>,
      line <em class="line">%(lineno)s</em>,
      in <code class="function">%(function_name)s</code></h4>
  <div class="source %(library)s">%(lines)s</div>
</div>
"""


def _process_traceback(
    exc: BaseException,
    te: traceback.TracebackException | None = None,
    *,
    skip: int = 0,
    hide: bool = True,
) -> traceback.TracebackException:
    if te is None:
        te = traceback.TracebackException.from_exception(exc, lookup_lines=False)

    # Get the frames the same way StackSummary.extract did, in order
    # to match each frame with the FrameSummary to augment.
    frame_gen = traceback.walk_tb(exc.__traceback__)
    limit = getattr(sys, "tracebacklimit", None)

    if limit is not None:
        if limit < 0:
            limit = 0

        frame_gen = itertools.islice(frame_gen, limit)

    if skip:
        frame_gen = itertools.islice(frame_gen, skip, None)
        del te.stack[:skip]

    new_stack: list[DebugFrameSummary] = []
    hidden = False

    # Match each frame with the FrameSummary that was generated.
    # Hide frames using Paste's __traceback_hide__ rules. Replace
    # all visible FrameSummary with DebugFrameSummary.
    for (f, _), fs in zip(frame_gen, te.stack):
        if hide:
            hide_value = f.f_locals.get("__traceback_hide__", False)

            if hide_value in {"before", "before_and_this"}:
                new_stack = []
                hidden = False

                if hide_value == "before_and_this":
                    continue
            elif hide_value in {"reset", "reset_and_this"}:
                hidden = False

                if hide_value == "reset_and_this":
                    continue
            elif hide_value in {"after", "after_and_this"}:
                hidden = True

                if hide_value == "after_and_this":
                    continue
            elif hide_value or hidden:
                continue

        frame_args: dict[str, t.Any] = {
            "filename": fs.filename,
            "lineno": fs.lineno,
            "name": fs.name,
            "locals": f.f_locals,
            "globals": f.f_globals,
        }

        if sys.version_info >= (3, 11):
            frame_args["colno"] = fs.colno
            frame_args["end_colno"] = fs.end_colno

        new_stack.append(DebugFrameSummary(**frame_args))

    # The codeop module is used to compile code from the interactive
    # debugger. Hide any codeop frames from the bottom of the traceback.
    while new_stack:
        module = new_stack[0].global_ns.get("__name__")

        if module is None:
            module = new_stack[0].local_ns.get("__name__")

        if module == "codeop":
            del new_stack[0]
        else:
            break

    te.stack[:] = new_stack

    if te.__context__:
        context_exc = t.cast(BaseException, exc.__context__)
        te.__context__ = _process_traceback(context_exc, te.__context__, hide=hide)

    if te.__cause__:
        cause_exc = t.cast(BaseException, exc.__cause__)
        te.__cause__ = _process_traceback(cause_exc, te.__cause__, hide=hide)

    return te


class DebugTraceback:
    __slots__ = ("_te", "_cache_all_tracebacks", "_cache_all_frames")

    def __init__(
        self,
        exc: BaseException,
        te: traceback.TracebackException | None = None,
        *,
        skip: int = 0,
        hide: bool = True,
    ) -> None:
        self._te = _process_traceback(exc, te, skip=skip, hide=hide)

    def __str__(self) -> str:
        return f"<{type(self).__name__} {self._te}>"

    @cached_property
    def all_tracebacks(
        self,
    ) -> list[tuple[str | None, traceback.TracebackException]]:
        out: list[tuple[str | None, traceback.TracebackException]] = []
        current: traceback.TracebackException | None = self._te

        while current is not None:
            if current.__cause__ is not None:
                chained_msg = (
                    "The above exception was the direct cause of the"
                    " following exception"
                )
                chained_exc = current.__cause__
            elif current.__context__ is not None and not current.__suppress_context__:
                chained_msg = (
                    "During handling of the above exception, another exception occurred"
                )
                chained_exc = current.__context__
            else:
                chained_msg = None
                chained_exc = None

            out.append((chained_msg, current))
            current = chained_exc

        return out

    @cached_property
    def all_frames(self) -> list[DebugFrameSummary]:
        return [
            f  # type: ignore[misc]
            for _, te in self.all_tracebacks
            for f in te.stack
        ]

    def render_traceback_text(self) -> str:
        return "".join(self._te.format())

    def render_traceback_html(self, include_title: bool = True) -> str:
        library_frames = [f.is_library for f in self.all_frames]
        mark_library = 0 < sum(library_frames) < len(library_frames)
        rows = []

        if not library_frames:
            classes = "traceback noframe-traceback"
        else:
            classes = "traceback"

            for msg, current in reversed(self.all_tracebacks):
                row_parts = []

                if msg is not None:
                    row_parts.append(f'<li><div class="exc-divider">{msg}:</div>')

                for frame in current.stack:
                    frame = t.cast(DebugFrameSummary, frame)
                    info = f' title="{escape(frame.info)}"' if frame.info else ""
                    row_parts.append(f"<li{info}>{frame.render_html(mark_library)}")

                rows.append("\n".join(row_parts))

        if sys.version_info < (3, 13):
            exc_type_str = self._te.exc_type.__name__
        else:
            exc_type_str = self._te.exc_type_str

        is_syntax_error = exc_type_str == "SyntaxError"

        if include_title:
            if is_syntax_error:
                title = "Syntax Error"
            else:
                title = "Traceback <em>(most recent call last)</em>:"
        else:
            title = ""

        exc_full = escape("".join(self._te.format_exception_only()))

        if is_syntax_error:
            description = f"<pre class=syntaxerror>{exc_full}</pre>"
        else:
            description = f"<blockquote>{exc_full}</blockquote>"

        return SUMMARY_HTML % {
            "classes": classes,
            "title": f"<h3>{title}</h3>",
            "frames": "\n".join(rows),
            "description": description,
        }

    def render_debugger_html(
        self, evalex: bool, secret: str, evalex_trusted: bool
    ) -> str:
        exc_lines = list(self._te.format_exception_only())
        plaintext = "".join(self._te.format())

        if sys.version_info < (3, 13):
            exc_type_str = self._te.exc_type.__name__
        else:
            exc_type_str = self._te.exc_type_str

        return PAGE_HTML % {
            "evalex": "true" if evalex else "false",
            "evalex_trusted": "true" if evalex_trusted else "false",
            "console": "false",
            "title": escape(exc_lines[0]),
            "exception": escape("".join(exc_lines)),
            "exception_type": escape(exc_type_str),
            "summary": self.render_traceback_html(include_title=False),
            "plaintext": escape(plaintext),
            "plaintext_cs": re.sub("-{2,}", "-", plaintext),
            "secret": secret,
        }


class DebugFrameSummary(traceback.FrameSummary):
    """A :class:`traceback.FrameSummary` that can evaluate code in the
    frame's namespace.
    """

    __slots__ = (
        "local_ns",
        "global_ns",
        "_cache_info",
        "_cache_is_library",
        "_cache_console",
    )

    def __init__(
        self,
        *,
        locals: dict[str, t.Any],
        globals: dict[str, t.Any],
        **kwargs: t.Any,
    ) -> None:
        super().__init__(locals=None, **kwargs)
        self.local_ns = locals
        self.global_ns = globals

    @cached_property
    def info(self) -> str | None:
        return self.local_ns.get("__traceback_info__")

    @cached_property
    def is_library(self) -> bool:
        return any(
            self.filename.startswith((path, os.path.realpath(path)))
            for path in sysconfig.get_paths().values()
        )

    @cached_property
    def console(self) -> Console:
        return Console(self.global_ns, self.local_ns)

    def eval(self, code: str) -> t.Any:
        return self.console.eval(code)

    def render_html(self, mark_library: bool) -> str:
        context = 5
        lines = linecache.getlines(self.filename)
        line_idx = self.lineno - 1  # type: ignore[operator]
        start_idx = max(0, line_idx - context)
        stop_idx = min(len(lines), line_idx + context + 1)
        rendered_lines = []

        def render_line(line: str, cls: str) -> None:
            line = line.expandtabs().rstrip()
            stripped_line = line.strip()
            prefix = len(line) - len(stripped_line)
            colno = getattr(self, "colno", 0)
            end_colno = getattr(self, "end_colno", 0)

            if cls == "current" and colno and end_colno:
                arrow = (
                    f'\n<span class="ws">{" " * prefix}</span>'
                    f"{' ' * (colno - prefix)}{'^' * (end_colno - colno)}"
                )
            else:
                arrow = ""

            rendered_lines.append(
                f'<pre class="line {cls}"><span class="ws">{" " * prefix}</span>'
                f"{escape(stripped_line) if stripped_line else ' '}"
                f"{arrow if arrow else ''}</pre>"
            )

        if line_idx < len(lines):
            for line in lines[start_idx:line_idx]:
                render_line(line, "before")

            render_line(lines[line_idx], "current")

            for line in lines[line_idx + 1 : stop_idx]:
                render_line(line, "after")

        return FRAME_HTML % {
            "id": id(self),
            "filename": escape(self.filename),
            "lineno": self.lineno,
            "function_name": escape(self.name),
            "lines": "\n".join(rendered_lines),
            "library": "library" if mark_library and self.is_library else "",
        }


def render_console_html(secret: str, evalex_trusted: bool) -> str:
    return CONSOLE_HTML % {
        "evalex": "true",
        "evalex_trusted": "true" if evalex_trusted else "false",
        "console": "true",
        "title": "Console",
        "secret": secret,
    }
