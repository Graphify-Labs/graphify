# mypy: allow-untyped-defs
# This module was imported from the cpython standard library
# (https://github.com/python/cpython/) at commit
# c5140945c723ae6c4b7ee81ff720ac8ea4b52cfd (python3.12).
#
#
#  Original Author:      Fred L. Drake, Jr.
#                        fdrake@acm.org
#
#  This is a simple little module I wrote to make life easier.  I didn't
#  see anything quite like it in the library, though I may have overlooked
#  something.  I wrote this when I was trying to read some heavily nested
#  tuples with fairly non-descriptive content.  This is modeled very much
#  after Lisp/Scheme - style pretty-printing of lists.  If you find it
#  useful, thank small children who sleep at night.
from __future__ import annotations

import collections as _collections
from collections.abc import Callable
from collections.abc import Iterator
import dataclasses as _dataclasses
from io import StringIO as _StringIO
import re
import types as _types
from typing import Any
from typing import IO


class _safe_key:
    """Helper function for key functions when sorting unorderable objects.

    The wrapped-object will fallback to a Py2.x style comparison for
    unorderable types (sorting first comparing the type name and then by
    the obj ids).  Does not work recursively, so dict.items() must have
    _safe_key applied to both the key and the value.

    """

    __slots__ = ["obj"]

    def __init__(self, obj):
        self.obj = obj

    def __lt__(self, other):
        try:
            return self.obj < other.obj
        except TypeError:
            return (str(type(self.obj)), id(self.obj)) < (
                str(type(other.obj)),
                id(other.obj),
            )


def _safe_tuple(t):
    """Helper function for comparing 2-tuples"""
    return _safe_key(t[0]), _safe_key(t[1])


class PrettyPrinter:
    def __init__(
        self,
        indent: int = 4,
        width: int = 80,
        depth: int | None = None,
    ) -> None:
        """Handle pretty printing operations onto a stream using a set of
        configured parameters.

        indent
            Number of spaces to indent for each level of nesting.

        width
            Attempted maximum number of columns in the output.

        depth
            The maximum depth to print out nested structures.

        """
        if indent < 0:
            raise ValueError("indent must be >= 0")
        if depth is not None and depth <= 0:
            raise ValueError("depth must be > 0")
        if not width:
            raise ValueError("width must be != 0")
        self._depth = depth
        self._indent_per_level = indent
        self._width = width

    def pformat(self, object: Any) -> str:
        sio = _StringIO()
        self._format(object, sio, 0, 0, set(), 0)
        return sio.getvalue()

    def _format(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        objid = id(object)
        if objid in context:
            stream.write(_recursion(object))
            return

        p = self._dispatch.get(type(object).__repr__, None)
        if p is not None:
            context.add(objid)
            p(self, object, stream, indent, allowance, context, level + 1)
            context.remove(objid)
        elif (
            _dataclasses.is_dataclass(object)
            and not isinstance(object, type)
            and object.__dataclass_params__.repr  # type:ignore[attr-defined]
            and
            # Check dataclass has generated repr method.
            hasattr(object.__repr__, "__wrapped__")
            and "__create_fn__" in object.__repr__.__wrapped__.__qualname__
        ):
            context.add(objid)
            self._pprint_dataclass(
                object, stream, indent, allowance, context, level + 1
            )
            context.remove(objid)
        else:
            stream.write(self._repr(object, context, level))

    def _pprint_dataclass(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        cls_name = object.__class__.__name__
        items = [
            (f.name, getattr(object, f.name))
            for f in _dataclasses.fields(object)
            if f.repr
        ]
        stream.write(cls_name + "(")
        self._format_namespace_items(items, stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch: dict[
        Callable[..., str],
        Callable[[PrettyPrinter, Any, IO[str], int, int, set[int], int], None],
    ] = {}

    def _pprint_dict(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        write = stream.write
        write("{")
        items = object.items()
        self._format_dict_items(items, stream, indent, allowance, context, level)
        write("}")

    _dispatch[dict.__repr__] = _pprint_dict

    def _pprint_ordered_dict(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if not len(object):
            stream.write(repr(object))
            return
        cls = object.__class__
        stream.write(cls.__name__ + "(")
        self._pprint_dict(object, stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch[_collections.OrderedDict.__repr__] = _pprint_ordered_dict

    def _pprint_list(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        stream.write("[")
        self._format_items(object, stream, indent, allowance, context, level)
        stream.write("]")

    _dispatch[list.__repr__] = _pprint_list

    def _pprint_tuple(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        stream.write("(")
        self._format_items(object, stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch[tuple.__repr__] = _pprint_tuple

    def _pprint_set(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if not len(object):
            stream.write(repr(object))
            return
        typ = object.__class__
        if typ is set:
            stream.write("{")
            endchar = "}"
        else:
            stream.write(typ.__name__ + "({")
            endchar = "})"
        object = sorted(object, key=_safe_key)
        self._format_items(object, stream, indent, allowance, context, level)
        stream.write(endchar)

    _dispatch[set.__repr__] = _pprint_set
    _dispatch[frozenset.__repr__] = _pprint_set

    def _pprint_str(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        write = stream.write
        if not len(object):
            write(repr(object))
            return
        chunks = []
        lines = object.splitlines(True)
        if level == 1:
            indent += 1
            allowance += 1
        max_width1 = max_width = self._width - indent
        for i, line in enumerate(lines):
            rep = repr(line)
            if i == len(lines) - 1:
                max_width1 -= allowance
            if len(rep) <= max_width1:
                chunks.append(rep)
            else:
                # A list of alternating (non-space, space) strings
                parts = re.findall(r"\S*\s*", line)
                assert parts
                assert not parts[-1]
                parts.pop()  # drop empty last part
                max_width2 = max_width
                current = ""
                for j, part in enumerate(parts):
                    candidate = current + part
                    if j == len(parts) - 1 and i == len(lines) - 1:
                        max_width2 -= allowance
                    if len(repr(candidate)) > max_width2:
                        if current:
                            chunks.append(repr(current))
                        current = part
                    else:
                        current = candidate
                if current:
                    chunks.append(repr(current))
        if len(chunks) == 1:
            write(rep)
            return
        if level == 1:
            write("(")
        for i, rep in enumerate(chunks):
            if i > 0:
                write("\n" + " " * indent)
            write(rep)
        if level == 1:
            write(")")

    _dispatch[str.__repr__] = _pprint_str

    def _pprint_bytes(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        write = stream.write
        if len(object) <= 4:
            write(repr(object))
            return
        parens = level == 1
        if parens:
            indent += 1
            allowance += 1
            write("(")
        delim = ""
        for rep in _wrap_bytes_repr(object, self._width - indent, allowance):
            write(delim)
            write(rep)
            if not delim:
                delim = "\n" + " " * indent
        if parens:
            write(")")

    _dispatch[bytes.__repr__] = _pprint_bytes

    def _pprint_bytearray(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        write = stream.write
        write("bytearray(")
        self._pprint_bytes(
            bytes(object), stream, indent + 10, allowance + 1, context, level + 1
        )
        write(")")

    _dispatch[bytearray.__repr__] = _pprint_bytearray

    def _pprint_mappingproxy(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        stream.write("mappingproxy(")
        self._format(object.copy(), stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch[_types.MappingProxyType.__repr__] = _pprint_mappingproxy

    def _pprint_simplenamespace(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if type(object) is _types.SimpleNamespace:
            # The SimpleNamespace repr is "namespace" instead of the class
            # name, so we do the same here. For subclasses; use the class name.
            cls_name = "namespace"
        else:
            cls_name = object.__class__.__name__
        items = object.__dict__.items()
        stream.write(cls_name + "(")
        self._format_namespace_items(items, stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch[_types.SimpleNamespace.__repr__] = _pprint_simplenamespace

    def _format_dict_items(
        self,
        items: list[tuple[Any, Any]],
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if not items:
            return

        write = stream.write
        item_indent = indent + self._indent_per_level
        delimnl = "\n" + " " * item_indent
        for key, ent in items:
            write(delimnl)
            write(self._repr(key, context, level))
            write(": ")
            self._format(ent, stream, item_indent, 1, context, level)
            write(",")

        write("\n" + " " * indent)

    def _format_namespace_items(
        self,
        items: list[tuple[Any, Any]],
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if not items:
            return

        write = stream.write
        item_indent = indent + self._indent_per_level
        delimnl = "\n" + " " * item_indent
        for key, ent in items:
            write(delimnl)
            write(key)
            write("=")
            if id(ent) in context:
                # Special-case representation of recursion to match standard
                # recursive dataclass repr.
                write("...")
            else:
                self._format(
                    ent,
                    stream,
                    item_indent + len(key) + 1,
                    1,
                    context,
                    level,
                )

            write(",")

        write("\n" + " " * indent)

    def _format_items(
        self,
        items: list[Any],
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if not items:
            return

        write = stream.write
        item_indent = indent + self._indent_per_level
        delimnl = "\n" + " " * item_indent

        for item in items:
            write(delimnl)
            self._format(item, stream, item_indent, 1, context, level)
            write(",")

        write("\n" + " " * indent)

    def _repr(self, object: Any, context: set[int], level: int) -> str:
        return self._safe_repr(object, context.copy(), self._depth, level)

    def _pprint_default_dict(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        rdf = self._repr(object.default_factory, context, level)
        stream.write(f"{object.__class__.__name__}({rdf}, ")
        self._pprint_dict(object, stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch[_collections.defaultdict.__repr__] = _pprint_default_dict

    def _pprint_counter(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        stream.write(object.__class__.__name__ + "(")

        if object:
            stream.write("{")
            items = object.most_common()
            self._format_dict_items(items, stream, indent, allowance, context, level)
            stream.write("}")

        stream.write(")")

    _dispatch[_collections.Counter.__repr__] = _pprint_counter

    def _pprint_chain_map(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        if not len(object.maps) or (len(object.maps) == 1 and not len(object.maps[0])):
            stream.write(repr(object))
            return

        stream.write(object.__class__.__name__ + "(")
        self._format_items(object.maps, stream, indent, allowance, context, level)
        stream.write(")")

    _dispatch[_collections.ChainMap.__repr__] = _pprint_chain_map

    def _pprint_deque(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        stream.write(object.__class__.__name__ + "(")
        if object.maxlen is not None:
            stream.write(f"maxlen={object.maxlen}, ")
        stream.write("[")

        self._format_items(object, stream, indent, allowance + 1, context, level)
        stream.write("])")

    _dispatch[_collections.deque.__repr__] = _pprint_deque

    def _pprint_user_dict(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        self._format(object.data, stream, indent, allowance, context, level - 1)

    _dispatch[_collections.UserDict.__repr__] = _pprint_user_dict

    def _pprint_user_list(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        self._format(object.data, stream, indent, allowance, context, level - 1)

    _dispatch[_collections.UserList.__repr__] = _pprint_user_list

    def _pprint_user_string(
        self,
        object: Any,
        stream: IO[str],
        indent: int,
        allowance: int,
        context: set[int],
        level: int,
    ) -> None:
        self._format(object.data, stream, indent, allowance, context, level - 1)

    _dispatch[_collections.UserString.__repr__] = _pprint_user_string

    def _safe_repr(
        self, object: Any, context: set[int], maxlevels: int | None, level: int
    ) -> str:
        typ = type(object)
        if typ in _builtin_scalars:
            return repr(object)

        r = getattr(typ, "__repr__", None)

        if issubclass(typ, dict) and r is dict.__repr__:
            if not object:
                return "{}"
            objid = id(object)
            if maxlevels and level >= maxlevels:
                return "{...}"
            if objid in context:
                return _recursion(object)
            context.add(objid)
            components: list[str] = []
            append = components.append
            level += 1
            for k, v in object.items():
                krepr = self._safe_repr(k, context, maxlevels, level)
                vrepr = self._safe_repr(v, context, maxlevels, level)
                append(f"{krepr}: {vrepr}")
            context.remove(objid)
            return "{{{}}}".format(", ".join(components))

        if (issubclass(typ, list) and r is list.__repr__) or (
            issubclass(typ, tuple) and r is tuple.__repr__
        ):
            if issubclass(typ, list):
                if not object:
                    return "[]"
                format = "[%s]"
            elif len(object) == 1:
                format = "(%s,)"
            else:
                if not object:
                    return "()"
                format = "(%s)"
            objid = id(object)
            if maxlevels and level >= maxlevels:
                return format % "..."
            if objid in context:
                return _recursion(object)
            context.add(objid)
            components = []
            append = components.append
            level += 1
            for o in object:
                orepr = self._safe_repr(o, context, maxlevels, level)
                append(orepr)
            context.remove(objid)
            return format % ", ".join(components)

        return repr(object)


_builtin_scalars = frozenset(
    {str, bytes, bytearray, float, complex, bool, type(None), int}
)


def _recursion(object: Any) -> str:
    return f"<Recursion on {type(object).__name__} with id={id(object)}>"


def _wrap_bytes_repr(object: Any, width: int, allowance: int) -> Iterator[str]:
    current = b""
    last = len(object) // 4 * 4
    for i in range(0, len(object), 4):
        part = object[i : i + 4]
        candidate = current + part
        if i == last:
            width -= allowance
        if len(repr(candidate)) > width:
            if current:
                yield repr(current)
            current = part
        else:
            current = candidate
    if current:
        yield repr(current)
