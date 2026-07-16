from __future__ import annotations

import code
import sys
import typing as t
from contextvars import ContextVar
from types import CodeType

from markupsafe import escape

from .repr import debug_repr
from .repr import dump
from .repr import helper

_stream: ContextVar[HTMLStringO] = ContextVar("werkzeug.debug.console.stream")
_ipy: ContextVar[_InteractiveConsole] = ContextVar("werkzeug.debug.console.ipy")


class HTMLStringO:
    """A StringO version that HTML escapes on write."""

    def __init__(self) -> None:
        self._buffer: list[str] = []

    def isatty(self) -> bool:
        return False

    def close(self) -> None:
        pass

    def flush(self) -> None:
        pass

    def seek(self, n: int, mode: int = 0) -> None:
        pass

    def readline(self) -> str:
        if len(self._buffer) == 0:
            return ""
        ret = self._buffer[0]
        del self._buffer[0]
        return ret

    def reset(self) -> str:
        val = "".join(self._buffer)
        del self._buffer[:]
        return val

    def _write(self, x: str) -> None:
        self._buffer.append(x)

    def write(self, x: str) -> None:
        self._write(escape(x))

    def writelines(self, x: t.Iterable[str]) -> None:
        self._write(escape("".join(x)))


class ThreadedStream:
    """Thread-local wrapper for sys.stdout for the interactive console."""

    @staticmethod
    def push() -> None:
        if not isinstance(sys.stdout, ThreadedStream):
            sys.stdout = t.cast(t.TextIO, ThreadedStream())

        _stream.set(HTMLStringO())

    @staticmethod
    def fetch() -> str:
        try:
            stream = _stream.get()
        except LookupError:
            return ""

        return stream.reset()

    @staticmethod
    def displayhook(obj: object) -> None:
        try:
            stream = _stream.get()
        except LookupError:
            return _displayhook(obj)  # type: ignore

        # stream._write bypasses escaping as debug_repr is
        # already generating HTML for us.
        if obj is not None:
            _ipy.get().locals["_"] = obj
            stream._write(debug_repr(obj))

    def __setattr__(self, name: str, value: t.Any) -> None:
        raise AttributeError(f"read only attribute {name}")

    def __dir__(self) -> list[str]:
        return dir(sys.__stdout__)

    def __getattribute__(self, name: str) -> t.Any:
        try:
            stream = _stream.get()
        except LookupError:
            stream = sys.__stdout__  # type: ignore[assignment]

        return getattr(stream, name)

    def __repr__(self) -> str:
        return repr(sys.__stdout__)


# add the threaded stream as display hook
_displayhook = sys.displayhook
sys.displayhook = ThreadedStream.displayhook


class _ConsoleLoader:
    def __init__(self) -> None:
        self._storage: dict[int, str] = {}

    def register(self, code: CodeType, source: str) -> None:
        self._storage[id(code)] = source
        # register code objects of wrapped functions too.
        for var in code.co_consts:
            if isinstance(var, CodeType):
                self._storage[id(var)] = source

    def get_source_by_code(self, code: CodeType) -> str | None:
        try:
            return self._storage[id(code)]
        except KeyError:
            return None


class _InteractiveConsole(code.InteractiveInterpreter):
    locals: dict[str, t.Any]

    def __init__(self, globals: dict[str, t.Any], locals: dict[str, t.Any]) -> None:
        self.loader = _ConsoleLoader()
        locals = {
            **globals,
            **locals,
            "dump": dump,
            "help": helper,
            "__loader__": self.loader,
        }
        super().__init__(locals)
        original_compile = self.compile

        def compile(source: str, filename: str, symbol: str) -> CodeType | None:
            code = original_compile(source, filename, symbol)

            if code is not None:
                self.loader.register(code, source)

            return code

        self.compile = compile  # type: ignore[assignment]
        self.more = False
        self.buffer: list[str] = []

    def runsource(self, source: str, **kwargs: t.Any) -> str:  # type: ignore
        source = f"{source.rstrip()}\n"
        ThreadedStream.push()
        prompt = "... " if self.more else ">>> "
        try:
            source_to_eval = "".join(self.buffer + [source])
            if super().runsource(source_to_eval, "<debugger>", "single"):
                self.more = True
                self.buffer.append(source)
            else:
                self.more = False
                del self.buffer[:]
        finally:
            output = ThreadedStream.fetch()
        return f"{prompt}{escape(source)}{output}"

    def runcode(self, code: CodeType) -> None:
        try:
            exec(code, self.locals)
        except Exception:
            self.showtraceback()

    def showtraceback(self) -> None:
        from .tbtools import DebugTraceback

        exc = t.cast(BaseException, sys.exc_info()[1])
        te = DebugTraceback(exc, skip=1)
        sys.stdout._write(te.render_traceback_html())  # type: ignore

    def showsyntaxerror(self, filename: str | None = None) -> None:
        from .tbtools import DebugTraceback

        exc = t.cast(BaseException, sys.exc_info()[1])
        te = DebugTraceback(exc, skip=4)
        sys.stdout._write(te.render_traceback_html())  # type: ignore

    def write(self, data: str) -> None:
        sys.stdout.write(data)


class Console:
    """An interactive console."""

    def __init__(
        self,
        globals: dict[str, t.Any] | None = None,
        locals: dict[str, t.Any] | None = None,
    ) -> None:
        if locals is None:
            locals = {}
        if globals is None:
            globals = {}
        self._ipy = _InteractiveConsole(globals, locals)

    def eval(self, code: str) -> str:
        _ipy.set(self._ipy)
        old_sys_stdout = sys.stdout
        try:
            return self._ipy.runsource(code)
        finally:
            sys.stdout = old_sys_stdout
