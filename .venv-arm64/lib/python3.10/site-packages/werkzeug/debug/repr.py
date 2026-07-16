"""Object representations for debugging purposes. Unlike the default
repr, these expose more information and produce HTML instead of ASCII.

Together with the CSS and JavaScript of the debugger this gives a
colorful and more compact output.
"""

from __future__ import annotations

import codecs
import re
import sys
import typing as t
from collections import deque
from traceback import format_exception_only

from markupsafe import escape

missing = object()
_paragraph_re = re.compile(r"(?:\r\n|\r|\n){2,}")
RegexType = type(_paragraph_re)

HELP_HTML = """\
<div class=box>
  <h3>%(title)s</h3>
  <pre class=help>%(text)s</pre>
</div>\
"""
OBJECT_DUMP_HTML = """\
<div class=box>
  <h3>%(title)s</h3>
  %(repr)s
  <table>%(items)s</table>
</div>\
"""


def debug_repr(obj: object) -> str:
    """Creates a debug repr of an object as HTML string."""
    return DebugReprGenerator().repr(obj)


def dump(obj: object = missing) -> None:
    """Print the object details to stdout._write (for the interactive
    console of the web debugger.
    """
    gen = DebugReprGenerator()
    if obj is missing:
        rv = gen.dump_locals(sys._getframe(1).f_locals)
    else:
        rv = gen.dump_object(obj)
    sys.stdout._write(rv)  # type: ignore


class _Helper:
    """Displays an HTML version of the normal help, for the interactive
    debugger only because it requires a patched sys.stdout.
    """

    def __repr__(self) -> str:
        return "Type help(object) for help about object."

    def __call__(self, topic: t.Any | None = None) -> None:
        if topic is None:
            sys.stdout._write(f"<span class=help>{self!r}</span>")  # type: ignore
            return
        import pydoc

        pydoc.help(topic)
        rv = sys.stdout.reset()  # type: ignore
        paragraphs = _paragraph_re.split(rv)
        if len(paragraphs) > 1:
            title = paragraphs[0]
            text = "\n\n".join(paragraphs[1:])
        else:
            title = "Help"
            text = paragraphs[0]
        sys.stdout._write(HELP_HTML % {"title": title, "text": text})  # type: ignore


helper = _Helper()


def _add_subclass_info(inner: str, obj: object, base: type | tuple[type, ...]) -> str:
    if isinstance(base, tuple):
        for cls in base:
            if type(obj) is cls:
                return inner
    elif type(obj) is base:
        return inner
    module = ""
    if obj.__class__.__module__ not in ("__builtin__", "exceptions"):
        module = f'<span class="module">{obj.__class__.__module__}.</span>'
    return f"{module}{type(obj).__name__}({inner})"


def _sequence_repr_maker(
    left: str, right: str, base: type, limit: int = 8
) -> t.Callable[[DebugReprGenerator, t.Iterable[t.Any], bool], str]:
    def proxy(self: DebugReprGenerator, obj: t.Iterable[t.Any], recursive: bool) -> str:
        if recursive:
            return _add_subclass_info(f"{left}...{right}", obj, base)
        buf = [left]
        have_extended_section = False
        for idx, item in enumerate(obj):
            if idx:
                buf.append(", ")
            if idx == limit:
                buf.append('<span class="extended">')
                have_extended_section = True
            buf.append(self.repr(item))
        if have_extended_section:
            buf.append("</span>")
        buf.append(right)
        return _add_subclass_info("".join(buf), obj, base)

    return proxy


class DebugReprGenerator:
    def __init__(self) -> None:
        self._stack: list[t.Any] = []

    list_repr = _sequence_repr_maker("[", "]", list)
    tuple_repr = _sequence_repr_maker("(", ")", tuple)
    set_repr = _sequence_repr_maker("set([", "])", set)
    frozenset_repr = _sequence_repr_maker("frozenset([", "])", frozenset)
    deque_repr = _sequence_repr_maker(
        '<span class="module">collections.</span>deque([', "])", deque
    )

    def regex_repr(self, obj: t.Pattern[t.AnyStr]) -> str:
        pattern = repr(obj.pattern)
        pattern = codecs.decode(pattern, "unicode-escape", "ignore")
        pattern = f"r{pattern}"
        return f're.compile(<span class="string regex">{pattern}</span>)'

    def string_repr(self, obj: str | bytes, limit: int = 70) -> str:
        buf = ['<span class="string">']
        r = repr(obj)

        # shorten the repr when the hidden part would be at least 3 chars
        if len(r) - limit > 2:
            buf.extend(
                (
                    escape(r[:limit]),
                    '<span class="extended">',
                    escape(r[limit:]),
                    "</span>",
                )
            )
        else:
            buf.append(escape(r))

        buf.append("</span>")
        out = "".join(buf)

        # if the repr looks like a standard string, add subclass info if needed
        if r[0] in "'\"" or (r[0] == "b" and r[1] in "'\""):
            return _add_subclass_info(out, obj, (bytes, str))

        # otherwise, assume the repr distinguishes the subclass already
        return out

    def dict_repr(
        self,
        d: dict[int, None] | dict[str, int] | dict[str | int, int],
        recursive: bool,
        limit: int = 5,
    ) -> str:
        if recursive:
            return _add_subclass_info("{...}", d, dict)
        buf = ["{"]
        have_extended_section = False
        for idx, (key, value) in enumerate(d.items()):
            if idx:
                buf.append(", ")
            if idx == limit - 1:
                buf.append('<span class="extended">')
                have_extended_section = True
            buf.append(
                f'<span class="pair"><span class="key">{self.repr(key)}</span>:'
                f' <span class="value">{self.repr(value)}</span></span>'
            )
        if have_extended_section:
            buf.append("</span>")
        buf.append("}")
        return _add_subclass_info("".join(buf), d, dict)

    def object_repr(self, obj: t.Any) -> str:
        r = repr(obj)
        return f'<span class="object">{escape(r)}</span>'

    def dispatch_repr(self, obj: t.Any, recursive: bool) -> str:
        if obj is helper:
            return f'<span class="help">{helper!r}</span>'
        if isinstance(obj, (int, float, complex)):
            return f'<span class="number">{obj!r}</span>'
        if isinstance(obj, str) or isinstance(obj, bytes):
            return self.string_repr(obj)
        if isinstance(obj, RegexType):
            return self.regex_repr(obj)
        if isinstance(obj, list):
            return self.list_repr(obj, recursive)
        if isinstance(obj, tuple):
            return self.tuple_repr(obj, recursive)
        if isinstance(obj, set):
            return self.set_repr(obj, recursive)
        if isinstance(obj, frozenset):
            return self.frozenset_repr(obj, recursive)
        if isinstance(obj, dict):
            return self.dict_repr(obj, recursive)
        if isinstance(obj, deque):
            return self.deque_repr(obj, recursive)
        return self.object_repr(obj)

    def fallback_repr(self) -> str:
        try:
            info = "".join(format_exception_only(*sys.exc_info()[:2]))
        except Exception:
            info = "?"
        return (
            '<span class="brokenrepr">'
            f"&lt;broken repr ({escape(info.strip())})&gt;</span>"
        )

    def repr(self, obj: object) -> str:
        recursive = False
        for item in self._stack:
            if item is obj:
                recursive = True
                break
        self._stack.append(obj)
        try:
            try:
                return self.dispatch_repr(obj, recursive)
            except Exception:
                return self.fallback_repr()
        finally:
            self._stack.pop()

    def dump_object(self, obj: object) -> str:
        repr = None
        items: list[tuple[str, str]] | None = None

        if isinstance(obj, dict):
            title = "Contents of"
            items = []
            for key, value in obj.items():
                if not isinstance(key, str):
                    items = None
                    break
                items.append((key, self.repr(value)))
        if items is None:
            items = []
            repr = self.repr(obj)
            for key in dir(obj):
                try:
                    items.append((key, self.repr(getattr(obj, key))))
                except Exception:
                    pass
            title = "Details for"
        title += f" {object.__repr__(obj)[1:-1]}"
        return self.render_object_dump(items, title, repr)

    def dump_locals(self, d: dict[str, t.Any]) -> str:
        items = [(key, self.repr(value)) for key, value in d.items()]
        return self.render_object_dump(items, "Local variables in frame")

    def render_object_dump(
        self, items: list[tuple[str, str]], title: str, repr: str | None = None
    ) -> str:
        html_items = []
        for key, value in items:
            html_items.append(f"<tr><th>{escape(key)}<td><pre class=repr>{value}</pre>")
        if not html_items:
            html_items.append("<tr><td><em>Nothing</em>")
        return OBJECT_DUMP_HTML % {
            "title": escape(title),
            "repr": f"<pre class=repr>{repr if repr else ''}</pre>",
            "items": "\n".join(html_items),
        }
