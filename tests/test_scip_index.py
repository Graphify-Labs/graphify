"""Tests for real SCIP indexes: graphify.scip_index (protobuf decoding) and scip_ingest.ingest_scip_index."""

from __future__ import annotations

import os
import threading
from pathlib import Path

import pytest

from graphify.scip_index import ScipDecodeError, decode_scip_index, symbol_display_name
from graphify.scip_ingest import ingest_scip_index

FIXTURES = Path(__file__).parent / "fixtures" / "scip"


# ---------------------------------------------------------------------------
# A tiny protobuf writer, so each test states the exact bytes it decodes
# ---------------------------------------------------------------------------


def _varint(value: int) -> bytes:
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        out.append(byte | (0x80 if value else 0))
        if not value:
            return bytes(out)


def _len(field: int, payload: bytes) -> bytes:
    return _varint(field << 3 | 2) + _varint(len(payload)) + payload


def _int(field: int, value: int) -> bytes:
    return _varint(field << 3) + _varint(value)


def _packed(field: int, values: list[int]) -> bytes:
    return _len(field, b"".join(_varint(v) for v in values))


def _occurrence(symbol: str, rng: bytes, roles: int = 0) -> bytes:
    return _len(2, rng + _len(2, symbol.encode()) + (_int(3, roles) if roles else b""))


def _document(path: str, *parts: bytes, language: str = "") -> bytes:
    body = _len(1, path.encode()) + (_len(4, language.encode()) if language else b"")
    return _len(2, body + b"".join(parts))


def _symbol_info(symbol: str, *extra: bytes) -> bytes:
    return _len(3, _len(1, symbol.encode()) + b"".join(extra))


BASE = "scip-python python pkg 1.0 `pkg.shapes`/Shape#"
CHILD = "scip-python python pkg 1.0 `pkg.shapes`/Square#"


# ---------------------------------------------------------------------------
# decode_scip_index
# ---------------------------------------------------------------------------


def test_decode_metadata_documents_and_packed_ranges() -> None:
    meta = _len(1, _len(2, _len(1, b"scip-python") + _len(2, b"0.6.8")) + _len(3, b"file:///repo"))
    doc = _document(
        "pkg/shapes.py", _occurrence(BASE, _packed(1, [3, 6, 11]), roles=1), language="python"
    )
    decoded = decode_scip_index(meta + doc)
    assert decoded.get("metadata") == {
        "tool_info": {"name": "scip-python", "version": "0.6.8"},
        "project_root": "file:///repo",
    }
    assert decoded["documents"] == [
        {
            "relative_path": "pkg/shapes.py",
            "language": "python",
            "occurrences": [{"range": [3, 6, 11], "symbol": BASE, "symbol_roles": 1}],
            "symbols": [],
        }
    ]


def test_decode_typed_ranges_with_proto3_zero_omission() -> None:
    # SingleLineRange on line 0: proto3 leaves the zero `line` field out entirely.
    single = _len(8, _int(2, 4) + _int(3, 9))
    multi = _len(9, _int(1, 2) + _int(2, 1) + _int(3, 5) + _int(4, 0))
    doc = _document("a.py", _occurrence(BASE, single), _occurrence(CHILD, multi))
    occurrences = decode_scip_index(doc)["documents"][0]["occurrences"]
    assert [o["range"] for o in occurrences] == [[0, 4, 9], [2, 1, 5, 0]]


def test_decode_typed_range_wins_over_the_deprecated_packed_one() -> None:
    both = _packed(1, [7, 0, 3]) + _len(8, _int(1, 4) + _int(3, 2))
    doc = _document("a.py", _occurrence(BASE, both))
    assert decode_scip_index(doc)["documents"][0]["occurrences"][0]["range"] == [4, 0, 2]


def test_decode_unpacked_repeated_range() -> None:
    unpacked = _int(1, 5) + _int(1, 0) + _int(1, 8)
    doc = _document("a.py", _occurrence(BASE, unpacked))
    assert decode_scip_index(doc)["documents"][0]["occurrences"][0]["range"] == [5, 0, 8]


def test_decode_symbol_information_and_relationships() -> None:
    relationship = _len(4, _len(1, BASE.encode()) + _int(3, 1))
    info = _symbol_info(
        CHILD, _len(3, b"A square."), relationship, _int(5, 7), _len(6, b"Square"), _len(8, b"pkg")
    )
    decoded = decode_scip_index(_document("a.py", info))
    assert decoded["documents"][0]["symbols"] == [
        {
            "symbol": CHILD,
            "kind": "Class",
            "documentation": ["A square."],
            "relationships": [
                {
                    "symbol": BASE,
                    "is_reference": False,
                    "is_implementation": True,
                    "is_type_definition": False,
                    "is_definition": False,
                }
            ],
            "display_name": "Square",
            "enclosing_symbol": "pkg",
        }
    ]


def test_decode_external_symbols_and_unknown_kinds() -> None:
    external = _len(
        3, _len(1, b"scip-python python requests 2.31 `requests`/Session#") + _int(5, 9999)
    )
    decoded = decode_scip_index(external)
    assert [s["kind"] for s in decoded.get("external_symbols", [])] == ["UnspecifiedKind"]
    assert decoded["documents"] == []


def test_decode_skips_unknown_and_fixed_width_fields() -> None:
    """Newer indexes may add fields: they are skipped, not an error."""
    future = (
        _len(15, b"new")
        + _int(16, 3)
        + _varint(17 << 3 | 1)
        + bytes(8)
        + _varint(18 << 3 | 5)
        + bytes(4)
    )
    doc = _document("a.py", future, _occurrence(BASE, _packed(1, [1, 0, 2])))
    assert decode_scip_index(doc)["documents"][0]["occurrences"][0]["symbol"] == BASE


@pytest.mark.parametrize(
    "data",
    [
        bytes([0x80]),  # a varint that never ends
        _varint(2 << 3 | 2) + _varint(10) + b"abc",  # a length that runs past the data
        _varint(2 << 3 | 3),  # wire type 3 (deprecated groups) is not SCIP
        _int(2, 5),  # a document written as a number, not a message
        _varint(2 << 3) + b"\xff" * 10 + b"\x01",  # a varint longer than protobuf's 10 bytes
        _document("a.py", _len(2, _len(3, b"x"))),  # symbol_roles written as bytes, not a number
    ],
)
def test_decode_malformed_raises(data: bytes) -> None:
    with pytest.raises(ScipDecodeError):
        decode_scip_index(data)


@pytest.mark.parametrize(
    ("symbol", "label"),
    [
        ("scip-python python pkg 1.0 `pkg.shapes`/Square#", "Square"),
        ("scip-python python pkg 1.0 `pkg.shapes`/Square#area().", "area()"),
        ("scip-python python pkg 1.0 `pkg.shapes`/total(+1).", "total()"),
        ("scip-python python pkg 1.0 `pkg.shapes`/Square#__init__().(side)", "side"),
        ("rust-analyzer cargo relay 1.0 services/upstream/UpstreamQuery#", "UpstreamQuery"),
        ("rust-analyzer cargo relay 1.0 lib/Thing#[T]", "T"),
        ("rust-analyzer cargo relay 1.0 macros/format!", "format"),
        ("scip-typescript npm web 1.0 src/`api.ts`/", "api.ts"),
        ("x y z 1 `odd``name`.", "odd`name"),
        ("local 4", ""),
        ("", ""),
    ],
)
def test_symbol_display_name(symbol: str, label: str) -> None:
    assert symbol_display_name(symbol) == label


# ---------------------------------------------------------------------------
# ingest_scip_index
# ---------------------------------------------------------------------------


def _shapes_index() -> bytes:
    return _document(
        "pkg/shapes.py",
        _occurrence(
            CHILD, _packed(1, [11, 2, 9])
        ),  # a reference, before the definition in the file
        _occurrence(BASE, _packed(1, [3, 6, 11]), roles=1),
        _occurrence(CHILD, _packed(1, [8, 6, 12]), roles=1),
        _occurrence("local 0", _packed(1, [9, 4, 5]), roles=1),
        _symbol_info(BASE),
        _symbol_info(CHILD, _len(4, _len(1, BASE.encode()) + _int(3, 1))),
        _symbol_info("local 0"),
        language="python",
    )


def test_ingest_index_nodes_sit_on_their_definition_line() -> None:
    result = ingest_scip_index(_shapes_index())
    nodes = {n["label"]: n for n in result["nodes"]}
    assert set(nodes) == {"Shape", "Square"}  # the document-local symbol is left out
    assert nodes["Shape"]["source_location"] == "L4"  # zero-based line 3 is the fourth line
    assert nodes["Square"]["source_location"] == "L9"  # its definition, not the earlier reference
    assert all(n["source_file"] == "pkg/shapes.py" for n in result["nodes"])


def test_ingest_index_relationships_become_edges() -> None:
    result = ingest_scip_index(_shapes_index())
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    assert [(labels[e["source"]], labels[e["target"]], e["relation"]) for e in result["edges"]] == [
        ("Square", "Shape", "scip_impl")
    ]


def test_ingest_index_from_a_path_and_from_bytes_agree(tmp_path: Path) -> None:
    path = tmp_path / "index.scip"
    path.write_bytes(_shapes_index())
    assert (
        ingest_scip_index(path)
        == ingest_scip_index(str(path))
        == ingest_scip_index(_shapes_index())
    )


def test_ingest_index_errors_are_returned_not_raised(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert "read error" in ingest_scip_index(tmp_path / "missing.scip").get("error", "")
    assert "decode error" in ingest_scip_index(bytes([0x80])).get("error", "")
    monkeypatch.setenv("GRAPHIFY_MAX_GRAPH_BYTES", "10")
    path = tmp_path / "big.scip"
    path.write_bytes(_shapes_index())
    for source in (path, _shapes_index()):
        result = ingest_scip_index(source)
        assert result == {"nodes": [], "edges": [], "error": "scip index too large to ingest"}


def test_ingest_index_is_deterministic() -> None:
    assert ingest_scip_index(_shapes_index()) == ingest_scip_index(_shapes_index())


# ---------------------------------------------------------------------------
# A real index, written by scip-python 0.6.8 from tests/fixtures/scip/shapes.py:
#   cd <folder with shapes.py> && npx @sourcegraph/scip-python@0.6.8 index \
#       --project-name shapes --project-version 1.0.0 --output index.scip
# ---------------------------------------------------------------------------


def _scip_symbol(node: dict[str, object]) -> str:
    metadata = node["metadata"]
    assert isinstance(metadata, dict)
    symbol = metadata["scip_symbol"]
    assert isinstance(symbol, str)
    return symbol


def test_real_scip_python_index() -> None:
    decoded = decode_scip_index((FIXTURES / "shapes.scip").read_bytes())
    assert decoded.get("metadata", {}).get("tool_info") == {
        "name": "scip-python",
        "version": "0.6.8",
    }
    assert [d["relative_path"] for d in decoded["documents"]] == ["shapes.py"]

    result = ingest_scip_index(FIXTURES / "shapes.scip")
    located = {(n["label"], n["source_location"]) for n in result["nodes"]}
    source = (FIXTURES / "shapes.py").read_text().splitlines()
    for label, needle in (
        ("Shape", "class Shape:"),
        ("Square", "class Square(Shape):"),
        ("total()", "def total("),
    ):
        line = next(i for i, text in enumerate(source, 1) if text.startswith(needle))
        assert (label, f"L{line}") in located

    by_id = {n["id"]: _scip_symbol(n).split("/")[-1] for n in result["nodes"]}
    implements = {
        (by_id[e["source"]], by_id[e["target"]])
        for e in result["edges"]
        if e["relation"] == "scip_impl"
    }
    assert implements == {("Square#", "Shape#"), ("Square#area().", "Shape#area().")}


@pytest.mark.skipif(not hasattr(os, "mkfifo"), reason="needs a FIFO")
def test_ingest_index_reads_no_more_than_the_cap_from_a_sizeless_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A FIFO reports size 0, so only the bounded read stops it from being read to the end."""
    fifo = tmp_path / "index.scip"
    os.mkfifo(fifo)
    monkeypatch.setenv("GRAPHIFY_MAX_GRAPH_BYTES", "100")

    def write() -> None:
        with open(fifo, "wb") as handle:
            handle.write(b"\x00" * 10_000)

    writer = threading.Thread(target=write)
    writer.start()
    result = ingest_scip_index(fifo)
    writer.join()
    assert result == {"nodes": [], "edges": [], "error": "scip index too large to ingest"}
