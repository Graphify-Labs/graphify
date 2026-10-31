"""Parser-free declaration hints for ambiguous C-family headers.

Callers mask inert tokens first. This hint chooses a grammar only; source parsing
and accepted declaration scope remain the owners of facts and relationships.
"""
from __future__ import annotations

import re


_HEAD = re.compile(rb"[A-Za-z_][\w\s:*&<>~]*\Z")
_WORDS = re.compile(rb"[A-Za-z_]\w*")
_STATEMENTS = {b"return", b"throw", b"co_return", b"co_yield", b"if", b"while", b"for", b"switch",
               b"sizeof", b"alignof", b"decltype", b"static_cast", b"reinterpret_cast", b"const_cast", b"dynamic_cast"}
_REFERENCE = re.compile(
    rb"(?:^|[,(])\s*(?:(?:const|volatile|typename|unsigned|signed|long|short)\s+)*"
    rb"[A-Za-z_]\w*(?:::[A-Za-z_]\w*)*(?:\s*<[^;{}()]*>)?\s*"
    rb"(?:(?:const|volatile)\s*)*(?:\*\s*(?:(?:const|volatile)\s*)*)*&&?\s*"
    rb"(?:[A-Za-z_]\w*)?\s*(?=,|$|=|\)|\[)"
)


def _without_directives(code):
    """Macro bodies cannot stand in for source declarations, including continuations."""
    result, continuation = [], False
    for line in code.splitlines(keepends=True):
        hidden = continuation or line.lstrip(b" \t").startswith(b"#")
        continuation = hidden and line.rstrip(b"\r\n").endswith(b"\\")
        result.append(bytes(10 if value == 10 else 13 if value == 13 else 32 for value in line) if hidden else line)
    return b"".join(result)


def _default_initializer(head):
    """Only a member's top-level assignment counts; array/type expressions do not."""
    parentheses = brackets = 0
    for offset, token in enumerate(head):
        parentheses += (token == 40) - (token == 41)
        brackets += (token == 91) - (token == 93)
        if (token == 61 and parentheses == brackets == 0
                and head[offset - 1:offset] not in (b"=", b"!", b"<", b">")
                and head[offset + 1:offset + 2] != b"="):
            return True
    return False


def has_cpp_declaration_hint(code):
    """Visit declaration contexts once; expression bodies cannot provide type evidence."""
    code = _without_directives(code)
    start = offset = 0
    contexts = []
    body_count = 0
    while offset < len(code):
        token = code[offset]
        eligible = body_count == 0
        if token == 123:  # A C struct body can contain C++-only reference fields.
            head = code[start:offset].strip()
            words = _WORDS.findall(head)
            if (eligible and contexts and contexts[-1] == "data"
                    and (_default_initializer(head) or
                         _HEAD.fullmatch(head) and len(words) >= 2
                         and words[0] not in {b"struct", b"union", b"enum", b"typedef"})):
                return True
            data = (re.match(rb"(?:typedef\s+)?(?:struct|union)\b", head) is not None
                    and b"(" not in head and b"=" not in head)
            context = "data" if eligible and data else "body"
            contexts.append(context)
            body_count += context == "body"
            start = offset + 1
        elif token == 125:
            if contexts:
                body_count -= contexts.pop() == "body"
            start = offset + 1
        elif token == 59:
            head = code[start:offset].strip()
            if head.startswith(b"typedef "):
                head = head[8:].lstrip()
            if eligible and (_REFERENCE.match(head) or
                             contexts and contexts[-1] == "data" and _default_initializer(head)):
                return True
            start = offset + 1
        elif token == 40:
            opening, depth = offset, 1
            offset += 1
            while offset < len(code) and depth:
                depth += (code[offset] == 40) - (code[offset] == 41)
                offset += 1
            if depth:
                return False
            head = code[start:opening].strip()
            if eligible and _HEAD.fullmatch(head):
                words = _WORDS.findall(head)
                tail = offset
                while tail < len(code) and code[tail] in b" \t\r\n\v\f":
                    tail += 1
                if (words and words[0] not in _STATEMENTS
                        and code.startswith((b";", b"{", b"const", b"volatile", b"noexcept", b"->", b"&"), tail)
                        and (_REFERENCE.match(head) or len(words) >= 2 and _REFERENCE.search(code[opening + 1:offset - 1]))):
                    return True
            continue
        offset += 1
    return False
