"""PageIndex-style hierarchical section map for text documents."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


_HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")


@dataclass(frozen=True)
class DocumentSection:
    section_id: str
    title: str
    path: str
    level: int
    start_line: int
    end_line: int
    parent_id: str | None
    content_ref: str


@dataclass(frozen=True)
class DocumentIndex:
    source_file: str
    content_ref: str
    sections: tuple[DocumentSection, ...]


def _section_id(source_file: str, path: str, start_line: int) -> str:
    digest = hashlib.sha256(f"{source_file}\0{path}\0{start_line}".encode()).hexdigest()[:20]
    return f"docsec:{digest}"


def build_document_index(source_file: str, text: str) -> DocumentIndex:
    """Build a stable hierarchy whose section hashes support lazy validation."""

    lines = text.splitlines()
    headings: list[tuple[int, int, str]] = []
    fence_marker: str | None = None
    fence_length = 0
    for line_number, line in enumerate(lines, 1):
        if fence_marker is not None:
            candidate = line.lstrip(" ")
            indent = len(line) - len(candidate)
            marker_length = len(candidate) - len(candidate.lstrip(fence_marker))
            if (
                indent <= 3
                and marker_length >= fence_length
                and not candidate[marker_length:].strip()
            ):
                fence_marker = None
                fence_length = 0
            continue

        fence = _FENCE_OPEN.match(line)
        if fence and not (fence.group(1)[0] == "`" and "`" in fence.group(2)):
            fence_marker = fence.group(1)[0]
            fence_length = len(fence.group(1))
            continue

        match = _HEADING.match(line)
        if match:
            headings.append((len(match.group(1)), line_number, match.group(2).strip()))

    sections: list[DocumentSection] = []
    stack: list[tuple[int, str, str]] = []
    for index, (level, start, title) in enumerate(headings):
        while stack and stack[-1][0] >= level:
            stack.pop()
        path_parts = [item[1] for item in stack] + [title]
        path = " / ".join(path_parts)
        parent_id = stack[-1][2] if stack else None
        end = len(lines)
        for next_level, next_start, _next_title in headings[index + 1:]:
            if next_level <= level:
                end = next_start - 1
                break
        content = "\n".join(lines[start - 1:end])
        section_id = _section_id(source_file, path, start)
        sections.append(DocumentSection(
            section_id=section_id,
            title=title,
            path=path,
            level=level,
            start_line=start,
            end_line=end,
            parent_id=parent_id,
            content_ref="sha256:" + hashlib.sha256(content.encode()).hexdigest(),
        ))
        stack.append((level, title, section_id))
    return DocumentIndex(
        source_file=source_file,
        content_ref="sha256:" + hashlib.sha256(text.encode()).hexdigest(),
        sections=tuple(sections),
    )
