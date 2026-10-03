"""Bounded literal/call syntax over comment/string-masked accepted C++ bytes."""
from __future__ import annotations

import json
import re

from graphify.extractors.qt_cpp_syntax import source_span

_CALLEE = re.compile(rb'\b(?:[A-Za-z_]\w*|this)(?:(?:::|->|\.)[A-Za-z_]\w*)*(?:\s*<[^;{}\n]*>)?\s*\(')


def closing(code, position, opening=b"(", close=b")"):
    depth = 0
    for index in range(position, min(len(code), position + 100_000)):
        token = code[index:index + 1]
        if token == opening:
            depth += 1
        elif token == close:
            depth -= 1
            if not depth:
                return index
    return None


def argument_ranges(code, start, end):
    """Separators in nested selectors, lambdas and initializer maps are not arguments."""
    depths, ranges, begin = [0, 0, 0, 0], [], start
    pairs = {40: (0, 1), 41: (0, -1), 91: (1, 1), 93: (1, -1),
             123: (2, 1), 125: (2, -1), 60: (3, 1), 62: (3, -1)}
    for index in range(start, end):
        token = code[index]
        if token in pairs:
            slot, change = pairs[token]
            depths[slot] = max(0, depths[slot] + change)
        if token == 44 and not any(depths):
            ranges.append((begin, index))
            begin = index + 1
    if begin < end:
        ranges.append((begin, end))
    return ranges


def calls(unit, mapping, names):
    """Only executable function-body occurrences, never declaration signatures."""
    for match in _CALLEE.finditer(unit.code):
        left = match.group().rfind(b"(") + match.start()
        callee = unit.code[match.start():left].decode().strip()
        plain = re.sub(r"<.*>", "", callee).strip()
        name = re.split(r"::|->|\.", plain)[-1]
        if name not in names:
            continue
        owner = mapping.owner_at(match.start())
        body = owner.get("body") if owner else None
        if body is None or not (body.start_byte <= match.start() < body.end_byte):
            continue
        right = closing(unit.code, left)
        if right is None:
            continue
        args = [{"text": unit.source[a:b].decode().strip(), "code": unit.code[a:b].decode().strip(),
                 "start_byte": a, "end_byte": b, "span": source_span(unit.source, a, b)}
                for a, b in argument_ranges(unit.code, left + 1, right) if unit.source[a:b].strip()]
        receiver = re.split(r"->|\.", plain)[-2] if "->" in plain or "." in plain else ""
        before = unit.code[max(0, match.start() - 8):match.start()].rstrip()
        computed_receiver = not receiver and (before.endswith(b"->") or before.endswith(b"."))
        yield {"name": name, "callee": plain, "receiver": receiver, "args": args, "owner": owner,
               "computed_receiver": computed_receiver,
               "start_byte": match.start(), "end_byte": right + 1,
               "span": source_span(unit.source, match.start(), right + 1)}


def literal_string(expression):
    """Decode only a literal or supported literal wrapper; never execute C++/QML."""
    value = expression.strip()
    for _ in range(4):
        wrapper = re.fullmatch(r'(?:QStringLiteral|QLatin1String|QString|QByteArray|QUrl|QUrl::fromLocalFile)\s*\((.*)\)', value, re.S)
        if wrapper:
            value = wrapper[1].strip()
        else:
            break
    if not re.fullmatch(r'(?:u8|u|U|L)?"(?:[^"\\]|\\.)*"', value, re.S):
        return None
    try:
        decoded = json.loads(value[value.index('"'):])
    except ValueError:
        return None
    return decoded if isinstance(decoded, str) and len(decoded.encode()) <= 256 else None


def conditional_at(unit, position):
    """Source conditions are evidence, not a claim that a branch executes."""
    from graphify.extractors.qt_cpp_syntax import walk
    for syntax in walk(unit.root):
        if syntax.type in {"if_statement", "switch_statement", "conditional_expression", "preproc_if", "preproc_ifdef"}:
            if syntax.start_byte <= position < syntax.end_byte:
                return True
    return False
