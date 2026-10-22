"""Literal CMake tokenization with source positions and unevaluated scope barriers."""
from __future__ import annotations

import re
from dataclasses import dataclass

from graphify.extractors.qml_project_read import MetadataError


@dataclass(frozen=True)
class Token:
    value: str
    start: int
    end: int
    dynamic: bool = False


@dataclass(frozen=True)
class Command:
    name: str
    tokens: tuple[Token, ...]
    start: int
    end: int
    scoped: bool


def _bracket(text, offset):
    match = re.match(r"\[(=*)\[", text[offset:])
    if not match:
        return None
    close = "]" + match[1] + "]"
    start = offset + len(match[0])
    end = text.find(close, start)
    if end < 0:
        raise MetadataError("QML_CMAKE_SYNTAX", "unclosed_bracket")
    return start, end, end + len(close)


def commands(text: str):
    """Yield flat commands; declarations inside control/function scopes stay scoped."""
    pos, scopes = 0, []
    while pos < len(text):
        if text[pos].isspace() or (pos == 0 and text[pos] == "\ufeff"):
            pos += 1
            continue
        if text[pos] == "#":
            block = _bracket(text, pos + 1)
            pos = block[2] if block else text.find("\n", pos)
            if pos < 0:
                return
            continue
        match = re.match(r"([A-Za-z_][A-Za-z_0-9]*)\s*\(", text[pos:])
        if not match:
            raise MetadataError("QML_CMAKE_SYNTAX", "unsupported_command_syntax")
        name, start = match[1].lower(), pos
        pos += len(match[0])
        tokens = []
        while pos < len(text) and text[pos] != ")":
            if text[pos].isspace():
                pos += 1
                continue
            if text[pos] == "#":
                block = _bracket(text, pos + 1)
                pos = block[2] if block else text.find("\n", pos)
                if pos < 0:
                    raise MetadataError("QML_CMAKE_SYNTAX", "unclosed_command")
                continue
            token_start = pos
            block = _bracket(text, pos)
            if block:
                value, pos = text[block[0]:block[1]], block[2]
            elif text[pos] == '"':
                pos += 1
                while pos < len(text) and text[pos] != '"':
                    if text[pos] == "\\":
                        pos += 1
                    pos += 1
                if pos >= len(text):
                    raise MetadataError("QML_CMAKE_SYNTAX", "unclosed_quote")
                value = text[token_start + 1:pos]
                pos += 1
            else:
                while pos < len(text) and not text[pos].isspace() and text[pos] != ")":
                    pos += 1
                value = text[token_start:pos]
            tokens.append(Token(value, token_start, pos,
                                any(char in value for char in "$;\\()")))
            if len(tokens) > 10_000:
                raise MetadataError("QML_PROJECT_LIMIT", "cmake_token_limit")
        if pos >= len(text):
            raise MetadataError("QML_CMAKE_SYNTAX", "unclosed_command")
        pos += 1
        if name in {"endif", "endforeach", "endwhile", "endfunction", "endmacro", "endblock"}:
            expected = name.removeprefix("end")
            if not scopes or scopes.pop() != expected:
                raise MetadataError("QML_CMAKE_SYNTAX", "unbalanced_scope")
        yield Command(name, tuple(tokens), start, pos, bool(scopes))
        if name in {"if", "foreach", "while", "function", "macro", "block"}:
            scopes.append(name)
            if len(scopes) > 64:
                raise MetadataError("QML_PROJECT_LIMIT", "cmake_scope_limit")
    if scopes:
        raise MetadataError("QML_CMAKE_SYNTAX", "unclosed_scope")
