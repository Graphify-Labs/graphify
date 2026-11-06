"""scip_index.py — decode a real SCIP index (``index.scip``) without a protobuf dependency.

SCIP (https://github.com/sourcegraph/scip) is the index format written by
scip-python, scip-typescript, scip-java, rust-analyzer and other compiler-grade
indexers. An index is a protobuf ``Index`` message; this module reads the wire
format directly and returns the same JSON-shaped dict that ``scip print --json``
prints, so callers can treat both the same way.

Entry point:
  decode_scip_index(data: bytes) -> ScipIndex

Returned shape (the ``Scip*`` TypedDicts below; field names as in scip.proto;
absent optional fields are left out):
  metadata:         { project_root, tool_info: { name, version } }
  documents[]:      { relative_path, language, occurrences[], symbols[] }
  occurrences[]:    { range: [start_line, start_char, (end_line,) end_char],
                      symbol, symbol_roles }
  symbols[]:        { symbol, kind, display_name, documentation[],
                      relationships[], enclosing_symbol }
  relationships[]:  { symbol, is_reference, is_implementation,
                      is_type_definition, is_definition }
  external_symbols: [ symbol records, as above ]

Ranges are SCIP's: zero-based lines and characters. SCIP 0.4 added typed
``single_line_range`` / ``multi_line_range`` fields next to the deprecated
packed ``range``; both are read and returned as ``range``, the typed one
winning when an occurrence has both. ``kind`` is the enum name ("Method",
"Class", ...), or "UnspecifiedKind". Unknown fields are skipped, so newer
indexes still decode.

Malformed input raises ``ScipDecodeError`` (a ``ValueError``): a truncated
varint, a length running past its message, an unknown wire type, or a field
holding a number where scip.proto has a string or a message (and the reverse).
Nothing is guessed from a damaged index.
"""

from __future__ import annotations

import re
from collections.abc import Iterator
from typing import TypeAlias, TypedDict


class ScipDecodeError(ValueError):
    """The bytes are not a well-formed SCIP protobuf index."""


class ScipToolInfo(TypedDict, total=False):
    name: str
    version: str


class ScipMetadata(TypedDict, total=False):
    project_root: str
    tool_info: ScipToolInfo


class ScipOccurrence(TypedDict):
    range: list[int]
    symbol: str
    symbol_roles: int


class ScipRelationship(TypedDict):
    symbol: str
    is_reference: bool
    is_implementation: bool
    is_type_definition: bool
    is_definition: bool


class _ScipSymbolFields(TypedDict):
    symbol: str
    kind: str
    documentation: list[str]
    relationships: list[ScipRelationship]


class ScipSymbol(_ScipSymbolFields, total=False):
    """A SymbolInformation; ``display_name`` and ``enclosing_symbol`` only when the indexer wrote them."""

    display_name: str
    enclosing_symbol: str


class _ScipDocumentFields(TypedDict):
    relative_path: str
    occurrences: list[ScipOccurrence]
    symbols: list[ScipSymbol]


class ScipDocument(_ScipDocumentFields, total=False):
    language: str


class _ScipIndexFields(TypedDict):
    documents: list[ScipDocument]


class ScipIndex(_ScipIndexFields, total=False):
    metadata: ScipMetadata
    external_symbols: list[ScipSymbol]


# Field numbers from scip.proto (sourcegraph/scip v0.10).
_INDEX_METADATA, _INDEX_DOCUMENTS, _INDEX_EXTERNAL_SYMBOLS = 1, 2, 3
_METADATA_TOOL_INFO, _METADATA_PROJECT_ROOT = 2, 3
_TOOL_NAME, _TOOL_VERSION = 1, 2
_DOC_RELATIVE_PATH, _DOC_OCCURRENCES, _DOC_SYMBOLS, _DOC_LANGUAGE = 1, 2, 3, 4
_OCC_RANGE, _OCC_SYMBOL, _OCC_ROLES = 1, 2, 3
_OCC_SINGLE_LINE_RANGE, _OCC_MULTI_LINE_RANGE = 8, 9
_SYM_SYMBOL, _SYM_DOCUMENTATION, _SYM_RELATIONSHIPS = 1, 3, 4
_SYM_KIND, _SYM_DISPLAY_NAME, _SYM_ENCLOSING = 5, 6, 8
_REL_SYMBOL, _REL_IS_REFERENCE, _REL_IS_IMPLEMENTATION = 1, 2, 3
_REL_IS_TYPE_DEFINITION, _REL_IS_DEFINITION = 4, 5

_VARINT, _I64, _LEN, _I32 = 0, 1, 2, 5
_MAX_VARINT_BYTES = 10  # a 64-bit value; protobuf never writes a longer varint

# A field's value off the wire: an int for varints, a memoryview for length-delimited fields (strings, messages,
# packed ints), None for the fixed-width ones, which SCIP does not use.
_FieldValue: TypeAlias = int | memoryview | None

# SymbolInformation.Kind, by number (scip.proto v0.10; 83 is unused there).
_KINDS = {
    0: "UnspecifiedKind",
    1: "Array",
    2: "Assertion",
    3: "AssociatedType",
    4: "Attribute",
    5: "Axiom",
    6: "Boolean",
    7: "Class",
    8: "Constant",
    9: "Constructor",
    10: "DataFamily",
    11: "Enum",
    12: "EnumMember",
    13: "Event",
    14: "Fact",
    15: "Field",
    16: "File",
    17: "Function",
    18: "Getter",
    19: "Grammar",
    20: "Instance",
    21: "Interface",
    22: "Key",
    23: "Lang",
    24: "Lemma",
    25: "Macro",
    26: "Method",
    27: "MethodReceiver",
    28: "Message",
    29: "Module",
    30: "Namespace",
    31: "Null",
    32: "Number",
    33: "Object",
    34: "Operator",
    35: "Package",
    36: "PackageObject",
    37: "Parameter",
    38: "ParameterLabel",
    39: "Pattern",
    40: "Predicate",
    41: "Property",
    42: "Protocol",
    43: "Quasiquoter",
    44: "SelfParameter",
    45: "Setter",
    46: "Signature",
    47: "Subscript",
    48: "String",
    49: "Struct",
    50: "Tactic",
    51: "Theorem",
    52: "ThisParameter",
    53: "Trait",
    54: "Type",
    55: "TypeAlias",
    56: "TypeClass",
    57: "TypeFamily",
    58: "TypeParameter",
    59: "Union",
    60: "Value",
    61: "Variable",
    62: "Contract",
    63: "Error",
    64: "Library",
    65: "Modifier",
    66: "AbstractMethod",
    67: "MethodSpecification",
    68: "ProtocolMethod",
    69: "PureVirtualMethod",
    70: "TraitMethod",
    71: "TypeClassMethod",
    72: "Accessor",
    73: "Delegate",
    74: "MethodAlias",
    75: "SingletonClass",
    76: "SingletonMethod",
    77: "StaticDataMember",
    78: "StaticEvent",
    79: "StaticField",
    80: "StaticMethod",
    81: "StaticProperty",
    82: "StaticVariable",
    84: "Extension",
    85: "Mixin",
    86: "Concept",
}


# The last descriptor of a SCIP symbol ('scheme manager package version descriptors'): a name, possibly
# backquoted with `` for a backquote, followed by its suffix. Method: 'name(disambiguator).'; type 'name#';
# term 'name.'; namespace 'name/'; macro 'name!'; meta 'name:'; parameter '(name)'; type parameter '[name]'.
_METHOD_DESCRIPTOR = re.compile(r"(`(?:[^`]|``)+`|[^\s/#.`()\[\]!:]+)\([^()]*\)\.$")
_NAME_DESCRIPTOR = re.compile(r"(`(?:[^`]|``)+`|[^\s/#.`()\[\]!:]+)[/#.:!]$")
_PARAMETER_DESCRIPTOR = re.compile(r"[(\[]([^()\[\]]+)[)\]]$")


def symbol_display_name(symbol: str) -> str:
    """A short label for a SCIP symbol from its last descriptor: 'Square' for '...shapes`/Square#', 'area()' for
    '.../Square#area().', 'side' for a parameter '(side)'. '' for document-local symbols ('local 3')."""
    if not symbol or symbol.startswith("local "):
        return ""
    method = _METHOD_DESCRIPTOR.search(symbol)
    if method:
        return _unquote(method.group(1)) + "()"
    for pattern in (_NAME_DESCRIPTOR, _PARAMETER_DESCRIPTOR):
        found = pattern.search(symbol)
        if found:
            return _unquote(found.group(1))
    return ""


def _unquote(name: str) -> str:
    if len(name) > 1 and name[0] == name[-1] == "`":
        return name[1:-1].replace("``", "`")
    return name


def decode_scip_index(data: bytes) -> ScipIndex:
    """Decode a SCIP protobuf index into the JSON shape ``scip print --json`` uses."""
    index: ScipIndex = {"documents": []}
    external: list[ScipSymbol] = []
    for number, _, value in _fields(memoryview(data)):
        if number == _INDEX_METADATA:
            index["metadata"] = _metadata(_message(value))
        elif number == _INDEX_DOCUMENTS:
            index["documents"].append(_document(_message(value)))
        elif number == _INDEX_EXTERNAL_SYMBOLS:
            external.append(_symbol(_message(value)))
    if external:
        index["external_symbols"] = external
    return index


def _metadata(buf: memoryview) -> ScipMetadata:
    meta: ScipMetadata = {}
    for number, _, value in _fields(buf):
        if number == _METADATA_PROJECT_ROOT:
            meta["project_root"] = _text(value)
        elif number == _METADATA_TOOL_INFO:
            meta["tool_info"] = _tool_info(_message(value))
    return meta


def _tool_info(buf: memoryview) -> ScipToolInfo:
    tool: ScipToolInfo = {}
    for number, _, value in _fields(buf):
        if number == _TOOL_NAME:
            tool["name"] = _text(value)
        elif number == _TOOL_VERSION:
            tool["version"] = _text(value)
    return tool


def _document(buf: memoryview) -> ScipDocument:
    doc: ScipDocument = {"relative_path": "", "occurrences": [], "symbols": []}
    for number, _, value in _fields(buf):
        if number == _DOC_RELATIVE_PATH:
            doc["relative_path"] = _text(value)
        elif number == _DOC_LANGUAGE:
            doc["language"] = _text(value)
        elif number == _DOC_OCCURRENCES:
            doc["occurrences"].append(_occurrence(_message(value)))
        elif number == _DOC_SYMBOLS:
            doc["symbols"].append(_symbol(_message(value)))
    return doc


def _occurrence(buf: memoryview) -> ScipOccurrence:
    occ: ScipOccurrence = {"range": [], "symbol": "", "symbol_roles": 0}
    typed: list[int] | None = None
    for number, wire, value in _fields(buf):
        if number == _OCC_RANGE:
            occ["range"] += _ints(wire, value)  # unpacked writers send one field per int
        elif number == _OCC_SINGLE_LINE_RANGE:
            # line, start_character, end_character
            typed = _typed_range(_message(value), 3)
        elif number == _OCC_MULTI_LINE_RANGE:
            # start_line, start_character, end_line, end_character
            typed = _typed_range(_message(value), 4)
        elif number == _OCC_SYMBOL:
            occ["symbol"] = _text(value)
        elif number == _OCC_ROLES:
            occ["symbol_roles"] = _int(value)
    if typed is not None:
        occ["range"] = typed
    return occ


def _typed_range(buf: memoryview, size: int) -> list[int]:
    """A SingleLineRange or MultiLineRange as the packed list. proto3 leaves zero fields out, so they default to 0."""
    values = [0] * size
    for number, _, value in _fields(buf):
        if 1 <= number <= size:
            values[number - 1] = _int(value)
    return values


def _symbol(buf: memoryview) -> ScipSymbol:
    sym: ScipSymbol = {
        "symbol": "",
        "kind": _KINDS[0],
        "documentation": [],
        "relationships": [],
    }
    for number, _, value in _fields(buf):
        if number == _SYM_SYMBOL:
            sym["symbol"] = _text(value)
        elif number == _SYM_DOCUMENTATION:
            sym["documentation"].append(_text(value))
        elif number == _SYM_RELATIONSHIPS:
            sym["relationships"].append(_relationship(_message(value)))
        elif number == _SYM_KIND:
            sym["kind"] = _KINDS.get(_int(value), _KINDS[0])
        elif number == _SYM_DISPLAY_NAME:
            sym["display_name"] = _text(value)
        elif number == _SYM_ENCLOSING:
            sym["enclosing_symbol"] = _text(value)
    return sym


def _relationship(buf: memoryview) -> ScipRelationship:
    symbol = ""
    flags: dict[int, bool] = {}
    for number, _, value in _fields(buf):
        if number == _REL_SYMBOL:
            symbol = _text(value)
        elif _REL_IS_REFERENCE <= number <= _REL_IS_DEFINITION:
            flags[number] = bool(_int(value))
    return {
        "symbol": symbol,
        "is_reference": flags.get(_REL_IS_REFERENCE, False),
        "is_implementation": flags.get(_REL_IS_IMPLEMENTATION, False),
        "is_type_definition": flags.get(_REL_IS_TYPE_DEFINITION, False),
        "is_definition": flags.get(_REL_IS_DEFINITION, False),
    }


def _fields(buf: memoryview) -> Iterator[tuple[int, int, _FieldValue]]:
    """Yield (field number, wire type, value) for each field of one message."""
    i, end = 0, len(buf)
    while i < end:
        key, i = _varint(buf, i)
        number, wire = key >> 3, key & 7
        value: _FieldValue
        if wire == _VARINT:
            value, i = _varint(buf, i)
        elif wire == _LEN:
            size, i = _varint(buf, i)
            if i + size > end:
                raise ScipDecodeError(f"field {number} runs past the end of its message")
            value, i = buf[i : i + size], i + size
        elif wire in (_I64, _I32):
            value, i = None, i + (8 if wire == _I64 else 4)
        else:
            raise ScipDecodeError(f"unknown wire type {wire} in field {number}")
        yield number, wire, value


def _varint(buf: memoryview, i: int) -> tuple[int, int]:
    value = shift = 0
    while True:
        if i >= len(buf):
            raise ScipDecodeError("the data ends inside a varint")
        if shift >= 7 * _MAX_VARINT_BYTES:
            raise ScipDecodeError(f"a varint longer than {_MAX_VARINT_BYTES} bytes")
        byte = buf[i]
        i += 1
        value |= (byte & 0x7F) << shift
        if byte < 0x80:
            return value, i
        shift += 7


def _ints(wire: int, value: _FieldValue) -> list[int]:
    """A repeated int32: packed (one length-delimited run) or written one varint at a time."""
    if wire == _VARINT:
        return [_int(value)]
    packed, out, i = _message(value), [], 0
    while i < len(packed):
        n, i = _varint(packed, i)
        out.append(n)
    return out


def _int(value: _FieldValue) -> int:
    if not isinstance(value, int):
        raise ScipDecodeError("a number field holds a string or a message")
    return value


def _message(value: _FieldValue) -> memoryview:
    if not isinstance(value, memoryview):
        raise ScipDecodeError("a string or message field holds a number")
    return value


def _text(value: _FieldValue) -> str:
    return bytes(_message(value)).decode("utf-8", errors="replace")
