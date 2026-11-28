"""Preserve typed tagged templates with tree-sitter-typescript 0.23."""
from __future__ import annotations

from bisect import bisect_left
import re
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tree_sitter import Node, Parser


_TS_TYPED_TAG_END_RE = re.compile(rb">\s*(?P<backtick>`)")
_TAG_TYPES = ("identifier", "member_expression")


def _mask_type_spans(source: bytes, spans: list[tuple[int, int]]) -> bytes:
    masked = bytearray(source)
    for start, end in spans:
        masked[start:end] = re.sub(rb"[^\r\n]", b" ", source[start:end])
    return bytes(masked)


def _template_at(root: Node, start: int) -> Node | None:
    token = root.descendant_for_byte_range(start, start + 1)
    template = token.parent if token is not None and token.type == "`" else None
    if (template is not None and template.type == "template_string"
            and template.start_byte == start and not template.has_error):
        return template
    return None


def _repair_template_openings(
    source: bytes, parser: Parser, root: Node, endings: list[re.Match[bytes]],
) -> tuple[bytes, Node] | None:
    # A grammar error can consume the opening backtick alone, shifting later
    # templates by one delimiter. The parsed instantiation immediately before
    # that token identifies the candidate type span without scanning raw SQL.
    candidates = []
    for ending in endings:
        start = ending.start("backtick")
        token = root.descendant_for_byte_range(start, start + 1)
        if (token is None or token.type != "`" or token.parent is None
                or not token.parent.is_error):
            continue
        instantiation = token.prev_named_sibling
        if (instantiation is None or instantiation.type != "instantiation_expression"
                or instantiation.has_error):
            continue
        types = instantiation.child_by_field_name("type_arguments")
        tag = next((child for child in instantiation.named_children if not child.is_extra), None)
        if (types is not None and types.end_byte == ending.start() + 1
                and tag is not None and tag.type in _TAG_TYPES and tag.end_byte == types.start_byte):
            candidates.append((start, types.start_byte, types.end_byte))
    if not candidates:
        return None

    masked = _mask_type_spans(source, [(start, end) for _, start, end in candidates])
    recovered = parser.parse(masked).root_node
    for opening, type_start, _ in candidates:
        template = _template_at(recovered, opening)
        call = template.parent if template is not None else None
        tag = call.child_by_field_name("function") if call is not None else None
        if (call is None or call.type != "call_expression"
                or call.child_by_field_name("arguments") != template
                or tag is None or tag.end_byte != type_start):
            return None
    return masked, recovered


def _comparison_type_spans(
    source: bytes, parser: Parser, root: Node, endings: list[re.Match[bytes]],
) -> list[tuple[int, int]]:
    """Identify silently misparsed typed tags using the regular generic-call grammar."""
    templates = []
    for ending in endings:
        start = ending.start("backtick")
        template = _template_at(root, start)
        if template is None:
            continue
        parent = template.parent
        if (parent is not None and parent.type == "call_expression"
                and parent.child_by_field_name("type_arguments") is not None):
            continue
        templates.append((ending.start() + 1, start, template.end_byte))
    if not templates:
        return []

    # For the probe only, turn tag<T>`template` into tag<T>(`template`).
    # The grammar already understands the latter and can check the type list.
    # Preserve template contents so nested candidates remain visible.
    insertions = sorted((offset, token) for _, start, end in templates
                        for offset, token in ((start, b"("), (end, b")")))
    parts = []
    positions = {}
    previous = 0
    for index, (offset, token) in enumerate(insertions):
        parts.extend((source[previous:offset], token))
        positions[offset] = offset + index
        previous = offset
    parts.append(source[previous:])
    recovered = parser.parse(b"".join(parts)).root_node
    inserted_offsets = list(positions.values())

    spans = []
    for angle_end, start, end in templates:
        opening = positions[start]
        token = recovered.descendant_for_byte_range(opening, opening + 1)
        args = token.parent if token is not None and token.type == "(" else None
        if (args is None or args.type != "arguments"
                or args.start_byte != opening or args.end_byte != positions[end] + 1):
            continue
        call = args.parent
        if call is None or call.type != "call_expression":
            continue
        types = call.child_by_field_name("type_arguments")
        tag = call.child_by_field_name("function")
        if (types is None or types.has_error or tag is None
                or tag.type not in _TAG_TYPES
                or tag.end_byte != types.start_byte):
            continue
        type_end = types.end_byte - bisect_left(inserted_offsets, types.end_byte)
        if type_end == angle_end:
            type_start = types.start_byte - bisect_left(inserted_offsets, types.start_byte)
            spans.append((type_start, type_end))
    return spans


def mask_ts_tag_type_arguments(
    source: bytes, parser: Parser, root: Node, endings: list[re.Match[bytes]],
) -> bytes | None:
    """Blank confirmed type arguments and preserve source offsets for extraction."""
    repaired = _repair_template_openings(source, parser, root, endings) if root.has_error else None
    if repaired is not None:
        source, root = repaired
    spans = _comparison_type_spans(source, parser, root, endings)
    if spans:
        return _mask_type_spans(source, spans)
    return source if repaired is not None else None
