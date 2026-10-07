"""Byte-preserving rewrites for PHP syntax the pinned grammar rejects.

tree-sitter-php 0.24/0.25 ``cast_type`` has no ``void``, and ``cast_expression``
only accepts a unary/include/error-suppression operand. A PHP 8.5 ``(void)``
statement and ``(string) match { ... }`` both become ERROR nodes. The ERROR
swallows the call and, when recovery is unlucky, the enclosing declaration
(#4202). Blanking the unsupported cast keeps byte offsets and leaves a
statement the grammar already parses. ``: void`` return types are a different
production and must not be touched.
"""
from __future__ import annotations

import re

_PHP_CAST_WORD_RE = re.compile(
    rb"[ \t]*(array|binary|bool|boolean|double|float|int|integer|object|real|string|unset|void)[ \t]*",
    re.IGNORECASE,
)
_PHP_WS = b" \t\r\n"
_PHP_NL = (10, 13)


def normalize_php_85(source: bytes) -> bytes:
    """Blank PHP 8.5 casts the pinned grammar cannot parse (#4202).

    * ``(void) expr;`` — the cast is a statement; the expression remains.
    * ``(string) match`` — only the cast token is blanked. ``(string) (match
      ...)`` already parses and is not rewritten.

    Strings and comments are skipped so a literal ``'(void)'`` is unchanged.
    """
    out = bytearray(source)
    n = len(source)
    i = 0
    changed = False
    while i < n:
        c = source[i]
        if c == 47 and i + 1 < n and source[i + 1] == 47:
            i += 2
            while i < n and source[i] not in _PHP_NL:
                i += 1
            continue
        if c == 35 and (i == 0 or source[i - 1] in _PHP_WS or source[i - 1] in b";{}()"):
            i += 1
            while i < n and source[i] not in _PHP_NL:
                i += 1
            continue
        if c == 47 and i + 1 < n and source[i + 1] == 42:
            i += 2
            while i + 1 < n and not (source[i] == 42 and source[i + 1] == 47):
                i += 1
            i = min(n, i + 2)
            continue
        if c in (39, 34):
            quote = c
            i += 1
            while i < n:
                if source[i] == 92:
                    i += 2
                    continue
                if source[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if c == 40:
            word = _PHP_CAST_WORD_RE.match(source, i + 1)
            if word is not None and word.end() < n and source[word.end()] == 41:
                cast_end = word.end() + 1
                j = cast_end
                while j < n and source[j] in _PHP_WS:
                    j += 1
                is_void = word.group(1).lower() == b"void"
                rest = source[j + 5:j + 6]
                is_match = source.startswith(b"match", j) and not (rest.isalnum() or rest == b"_")
                if is_void or is_match:
                    for k in range(i, cast_end):
                        if out[k] not in _PHP_NL:
                            out[k] = 32
                    changed = True
                    i = cast_end
                    continue
        i += 1
    return bytes(out) if changed else source
