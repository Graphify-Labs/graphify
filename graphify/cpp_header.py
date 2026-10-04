"""Bounded lexical C++ header admission without importing optional parser bindings."""
from __future__ import annotations

from pathlib import Path
import re

_DECLARATION = re.compile(
    rb"\b(?:class|namespace)\s+[A-Za-z_]\w*|\btemplate\s*<|::|"
    rb"\b(?:public|private|protected)\s*:|\b(?:struct|union)\s+[A-Za-z_]\w*\s+final\b"
)
_NUMBER = re.compile(rb"(?:[0-9]|\.[0-9])(?:[A-Za-z0-9_.]|'[A-Za-z0-9_])*")
_RAW = re.compile(rb'(?:u8|u|U|L)?R"([^\s()\\]{0,16})\(')


def _code(source: bytes) -> bytes:
    """Hide inert tokens while preserving separation, continuation and literal bounds."""
    result, offset = bytearray(source), 0
    while offset < len(source):
        number = _NUMBER.match(source, offset)
        if number:
            offset = number.end()
            continue
        end = offset
        if source[offset:offset + 2] == b"/*":
            close = source.find(b"*/", offset + 2)
            end = len(source) if close < 0 else close + 2
        elif source[offset:offset + 2] == b"//":
            end = offset + 2
            while end < len(source):
                if (source[end:end + 1] == b"\n"
                        and source[end - 1:end] != b"\\" and source[end - 2:end] != b"\\\r"):
                    break
                end += 1
        else:
            raw = _RAW.match(source, offset)
            if raw:
                close = source.find(b")" + raw[1] + b'"', raw.end())
                end = len(source) if close < 0 else close + len(raw[1]) + 2
            elif source[offset:offset + 1] in {b'"', b"'"}:
                quote, end = source[offset], offset + 1
                while end < len(source):
                    if source[end] == 92:
                        end += 2
                    elif source[end] == quote:
                        end += 1
                        break
                    else:
                        end += 1
        if end > offset:
            end = min(end, len(source))
            result[offset:end] = b" " * (end - offset)
            offset = end
        else:
            offset += 1
    return bytes(result)


def is_cpp_header(path: Path) -> bool:
    """Recognize supported visible declarations; uncertain headers keep C dispatch.

    This admission hint supplies no type/member or SDK authority. Objective-C
    selection remains owned by the facade and precedes this C++ check.
    """
    try:
        with path.open("rb") as stream:
            source = stream.read(256 * 1024)
    except OSError:
        return False
    return _DECLARATION.search(_code(source)) is not None
