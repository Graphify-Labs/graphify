"""Bounded original-source proof for pointer-to-member data declarations.

The pinned grammar rejects a literal class qualifier before a pointer binding.
Only that qualifier is blanked for parsing; it remains source metadata, never a
canonical class target or ordinary object-pointer type. No corpus is reread.
"""
from __future__ import annotations

import re

from graphify.extractors.cpp_declarators import member_declarator

_QUALIFIER = re.compile(rb"(?<![\w:])(?P<owner>(?:::)?[A-Za-z_]\w*(?:\s*::\s*[A-Za-z_]\w*)*)\s*::\s*(?P<star>\*)")
# C++ lexical keywords cannot name a class/namespace qualifier. Recovery must
# not launder an invalid primitive/keyword owner into an ordinary pointer.
_KEYWORDS = set("""alignas alignof and and_eq asm auto bitand bitor bool break case catch
char char8_t char16_t char32_t class compl concept const consteval constexpr constinit
const_cast continue contract_assert co_await co_return co_yield decltype default delete
do double dynamic_cast else enum explicit export extern false float for friend goto if
inline int long mutable namespace new noexcept not not_eq nullptr operator or or_eq
private protected public register reinterpret_cast requires return short signed sizeof
static static_assert static_cast struct switch template this thread_local throw true try
typedef typeid typename union unsigned using virtual void volatile wchar_t while xor xor_eq""".split())


def has_member_pointer(code):
    return bool(re.search(rb"::\s*\*", code))


def _candidates(code, tree, walk):
    fields = [node for node in walk(tree) if node.type in {"field_declaration", "declaration", "ERROR"}
              and node.parent is not None and node.parent.type == "field_declaration_list"]
    found = []
    for match in _QUALIFIER.finditer(code):
        owner = re.sub(rb"\s+", b"", match["owner"]).decode()
        if (any(part in _KEYWORDS for part in owner.split("::"))
                or (match.start() and code[match.start() - 1] >= 128)):
            continue
        owners = [node for node in fields if node.start_byte <= match.start() < match.end() <= node.end_byte]
        if len(owners) != 1:
            continue
        field = owners[0]
        value_type = field.child_by_field_name("type")
        initializer = field.child_by_field_name("default_value")
        assigned = next((child.end_byte for child in field.children if child.type == "="), None)
        before = code[field.start_byte:match.start()].rstrip()
        # A preceding template/dependent scope cannot be silently truncated to
        # a convenient literal suffix. Type-less and initializer expressions
        # do not establish this field-declaration compatibility boundary.
        if ((value_type is not None and value_type.end_byte > match.start())
                or (initializer is not None and initializer.start_byte <= match.start())
                or (assigned is not None and assigned <= match.start())
                or not before or before.endswith((b">", b"::"))):
            continue
        found.append((match, field))
    return found


def _records(source, parsed, tree, *, walk, span, code):
    records = []
    for match, field in _candidates(code, tree, walk):
        if field.has_error:
            return ()
        matches = []
        for declarator in field.children_by_field_name("declarator"):
            pointers = [node for node in walk(declarator)
                        if node.type == "pointer_declarator" and node.start_byte == match.start("star")]
            role = member_declarator(declarator, parsed)
            if len(pointers) != 1 or role is None or role[1]:
                continue
            names = [node for node in walk(declarator) if node.type == "field_identifier"
                     and source[node.start_byte:node.end_byte].decode() == role[0]]
            if len(names) != 1:
                continue
            matches.append((declarator, names[0], role[0]))
        if len(matches) != 1:
            return ()
        declarator, name, spelling = matches[0]
        if any(item["parsed_span"]["start_byte"] == declarator.start_byte
               and item["parsed_span"]["end_byte"] == declarator.end_byte for item in records):
            return ()
        start = min(match.start(), declarator.start_byte)
        records.append({"name": spelling, "owner_spelling": re.sub(rb"\s+", b"", match["owner"]).decode(),
                        "kind": "function" if any(node.type == "function_declarator" for node in walk(declarator)) else "data",
                        "owner_span": span(source, match.start(), match.start("star")),
                        "parsed_span": span(source, declarator.start_byte, declarator.end_byte),
                        "span": span(source, start, declarator.end_byte),
                        "declaration_span": span(source, field.start_byte, field.end_byte),
                        "name_span": span(source, name.start_byte, name.end_byte)})
    return tuple(records)


def recover_member_pointers(source, code, *, parse, walk, span):
    """Prove repaired fields locally; the Qt facade still owns full-file admission."""
    if not has_member_pointer(code):
        return source
    tree = parse(source)
    candidates = _candidates(code, tree, walk)
    if not candidates:
        return source
    parsed = bytearray(source)
    for match, _ in candidates:
        start, end = match.start(), match.start("star")
        parsed[start:end] = re.sub(rb"[^\r\n]", b" ", source[start:end])
    normalized = bytes(parsed)
    recovered = parse(normalized)
    records = _records(source, normalized, recovered, walk=walk, span=span, code=code)
    return normalized if len(records) == len(candidates) else source


def member_pointer_records(source, parsed, *, tree=None):
    """Borrow original bytes plus one accepted parsing view, with the same limits."""
    from graphify.extractors.qt_cpp_syntax import MAX_CPP_BYTES, _parse_cpp, lexical_code, source_span, walk
    if len(source) > MAX_CPP_BYTES or len(source) != len(parsed):
        return ()
    code = lexical_code(source)
    if not has_member_pointer(code):
        return ()
    tree = tree if tree is not None else _parse_cpp(parsed)
    # Generic C++ may retain partial-input flags. Locally proven field spans
    # still include their original qualifier; this grants no Qt/type authority.
    return _records(source, parsed, tree, walk=walk, span=source_span, code=code)


def annotate_member_pointer_fields(result, source, parsed):
    """Attach exact structural proof to generic fields; never change IDs/owners."""
    records = member_pointer_records(source, parsed)
    for node in result.get("nodes", []):
        metadata = node.get("metadata", {}).get("cpp_declarator", {})
        if metadata.get("kind") != "field" or node.get("_callable"):
            continue
        matches = [record for record in records if metadata.get("span") == record["parsed_span"]
                   and node.get("label") == record["name"]]
        if len(matches) != 1:
            continue
        record = matches[0]
        metadata.update(span=record["span"], member_pointer={"contract_version": 1,
            "kind": record["kind"], "owner_spelling": record["owner_spelling"],
            "owner_status": "source_only", "owner_span": record["owner_span"]})
        node["source_location"] = f"L{record['span']['start_row'] + 1}"
