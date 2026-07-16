from collections.abc import Mapping
from typing import NamedTuple

from .exceptions import ParseError

COMMENTCHARS = "#;"


class ParsedLine(NamedTuple):
    lineno: int
    section: str | None
    name: str | None
    value: str | None


def parse_ini_data(
    path: str,
    data: str,
    *,
    strip_inline_comments: bool,
    strip_section_whitespace: bool = False,
) -> tuple[Mapping[str, Mapping[str, str]], Mapping[tuple[str, str | None], int]]:
    """Parse INI data and return sections and sources mappings.

    Args:
        path: Path for error messages
        data: INI content as string
        strip_inline_comments: Whether to strip inline comments from values
        strip_section_whitespace: Whether to strip whitespace from section and key names
            (default: False). When True, addresses issue #4 by stripping Unicode whitespace.

    Returns:
        Tuple of (sections_data, sources) where:
        - sections_data: mapping of section -> {name -> value}
        - sources: mapping of (section, name) -> line number
    """
    tokens = parse_lines(
        path,
        data.splitlines(True),
        strip_inline_comments=strip_inline_comments,
        strip_section_whitespace=strip_section_whitespace,
    )

    sources: dict[tuple[str, str | None], int] = {}
    sections_data: dict[str, dict[str, str]] = {}

    for lineno, section, name, value in tokens:
        if section is None:
            raise ParseError(path, lineno, "no section header defined")
        sources[section, name] = lineno
        if name is None:
            if section in sections_data:
                raise ParseError(path, lineno, f"duplicate section {section!r}")
            sections_data[section] = {}
        else:
            if name in sections_data[section]:
                raise ParseError(path, lineno, f"duplicate name {name!r}")
            assert value is not None
            sections_data[section][name] = value

    return sections_data, sources


def parse_lines(
    path: str,
    line_iter: list[str],
    *,
    strip_inline_comments: bool = False,
    strip_section_whitespace: bool = False,
) -> list[ParsedLine]:
    result: list[ParsedLine] = []
    section = None
    for lineno, line in enumerate(line_iter):
        name, data = _parseline(
            path, line, lineno, strip_inline_comments, strip_section_whitespace
        )
        # new value
        if name is not None and data is not None:
            result.append(ParsedLine(lineno, section, name, data))
        # new section
        elif name is not None and data is None:
            if not name:
                raise ParseError(path, lineno, "empty section name")
            section = name
            result.append(ParsedLine(lineno, section, None, None))
        # continuation
        elif name is None and data is not None:
            if not result:
                raise ParseError(path, lineno, "unexpected value continuation")
            last = result.pop()
            if last.name is None:
                raise ParseError(path, lineno, "unexpected value continuation")

            if last.value:
                last = last._replace(value=f"{last.value}\n{data}")
            else:
                last = last._replace(value=data)
            result.append(last)
    return result


def _parseline(
    path: str,
    line: str,
    lineno: int,
    strip_inline_comments: bool,
    strip_section_whitespace: bool,
) -> tuple[str | None, str | None]:
    # blank lines
    if iscommentline(line):
        line = ""
    else:
        line = line.rstrip()
    if not line:
        return None, None
    # section
    if line[0] == "[":
        realline = line
        for c in COMMENTCHARS:
            line = line.split(c)[0].rstrip()
        if line[-1] == "]":
            section_name = line[1:-1]
            # Optionally strip whitespace from section name (issue #4)
            if strip_section_whitespace:
                section_name = section_name.strip()
            return section_name, None
        return None, realline.strip()
    # value
    elif not line[0].isspace():
        try:
            name, value = line.split("=", 1)
            if ":" in name:
                raise ValueError()
        except ValueError:
            try:
                name, value = line.split(":", 1)
            except ValueError:
                raise ParseError(path, lineno, f"unexpected line: {line!r}") from None

        # Strip key name (always for backward compatibility, optionally with unicode awareness)
        key_name = name.strip()

        # Strip value
        value = value.strip()
        # Strip inline comments from values if requested (issue #55)
        if strip_inline_comments:
            for c in COMMENTCHARS:
                value = value.split(c)[0].rstrip()

        return key_name, value
    # continuation
    else:
        line = line.strip()
        # Strip inline comments from continuations if requested (issue #55)
        if strip_inline_comments:
            for c in COMMENTCHARS:
                line = line.split(c)[0].rstrip()
        return None, line


def iscommentline(line: str) -> bool:
    c = line.lstrip()[:1]
    return c in COMMENTCHARS
