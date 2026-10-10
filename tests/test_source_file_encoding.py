r"""A source file that is not UTF-8 must still give the same graph.

tree-sitter treats its input as UTF-8, and the extractors handed it the raw
file bytes. Two encodings that real Windows projects still contain broke that,
silently:

* UTF-16 (Visual Studio "Unicode", Windows PowerShell 5.1 ``Out-File`` and
  ``>``, older SSMS scripts): the interleaved NUL bytes parse as nothing, so the
  file contributed **no nodes at all**.
* Windows-1252 (Notepad's historical ANSI default): ``CaféOrder`` is
  ``Caf\xe9Order``; ``\xe9`` is not UTF-8, the identifier was cut at it, and the
  class came out as ``Order``.

Every source read in extraction now goes through ``_read_source_bytes`` /
``_read_source_text``: valid UTF-8 (BOM or not) is passed through byte for byte,
a BOM'd UTF-16/UTF-32 file is decoded exactly, and anything else is read as
cp1252 (then latin-1, which cannot fail) with a one-time warning naming the
file. The fallback is fixed rather than the host locale so the same bytes give
the same node ids on every machine.

These tests write bytes directly, so they pin the behaviour on every platform.
"""
from __future__ import annotations

import importlib.util
import os
from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.extractors import base
from graphify.extractors.base import _read_source_bytes, _read_source_text


@pytest.fixture(autouse=True)
def _fresh_warnings():
    base._warned_source_encodings.clear()
    yield
    base._warned_source_encodings.clear()


# ── the decoder ───────────────────────────────────────────────────────────────

def _write(tmp_path: Path, data: bytes, name: str = "f.cs") -> Path:
    p = tmp_path / name
    p.write_bytes(data)
    return p


@pytest.mark.parametrize("data", [
    b"class Order {}\n",
    "class CaféOrder {}\n".encode("utf-8"),
    "class CaféOrder {}\n".encode("utf-8-sig"),
    "class CaféOrder {}\r\n".encode("utf-8"),
    b"",
])
def test_valid_utf8_is_passed_through_byte_for_byte(tmp_path, capsys, data):
    # Node ids, byte offsets and cache keys of every existing UTF-8 file must not move.
    assert _read_source_bytes(_write(tmp_path, data)) == data
    assert capsys.readouterr().err == ""


@pytest.mark.parametrize("codec", ["utf-16", "utf-16-be-bom", "utf-32", "utf-32-be-bom"])
def test_bom_marked_utf16_and_utf32_are_decoded_exactly(tmp_path, capsys, codec):
    text = "class CaféOrder { void Pay() { Charge(); } }\n"
    if codec.endswith("-be-bom"):
        bare = codec.removesuffix("-bom")
        data = "﻿".encode(bare) + text.encode(bare)
    else:
        data = text.encode(codec)
    assert _read_source_bytes(_write(tmp_path, data)) == text.encode("utf-8")
    assert capsys.readouterr().err == "", "an exactly-decoded file is not a guess; no warning"


def test_utf16_le_file_starting_with_nul_is_not_mistaken_for_utf32(tmp_path):
    # FF FE 00 00 is both the UTF-32-LE BOM and a UTF-16-LE BOM followed by U+0000.
    data = "\x00ab".encode("utf-16")
    assert data.startswith(b"\xff\xfe\x00\x00")
    assert _read_source_bytes(_write(tmp_path, data)) == "\x00ab".encode("utf-8")


def test_cp1252_is_read_whole_and_warned_once(tmp_path, capsys):
    p = _write(tmp_path, "class CaféOrder {}\n".encode("cp1252"))
    assert _read_source_bytes(p) == "class CaféOrder {}\n".encode("utf-8")
    err = capsys.readouterr().err
    assert str(p) in err and "cp1252" in err and "not valid UTF-8" in err
    _read_source_bytes(p)
    assert capsys.readouterr().err == "", "one warning per file per process"


def test_warn_false_is_silent(tmp_path, capsys):
    p = _write(tmp_path, "class CaféOrder {}\n".encode("cp1252"))
    assert _read_source_bytes(p, warn=False) == "class CaféOrder {}\n".encode("utf-8")
    assert capsys.readouterr().err == ""


def test_bytes_cp1252_does_not_define_fall_back_to_latin1(tmp_path, capsys):
    # 0x81 has no cp1252 mapping; latin-1 maps every byte, so the read still succeeds.
    p = _write(tmp_path, b"class Caf\x81Order {}\n")
    assert _read_source_bytes(p) == "class Caf\x81Order {}\n".encode("utf-8")
    assert "latin-1" in capsys.readouterr().err


def test_fallback_does_not_follow_the_host_locale(tmp_path, monkeypatch):
    # The same bytes must give the same node ids on every machine.
    import locale
    monkeypatch.setattr(locale, "getpreferredencoding", lambda do_setlocale=True: "cp437")
    monkeypatch.setattr(locale, "getencoding", lambda: "cp437", raising=False)
    p = _write(tmp_path, "class CaféOrder {}\n".encode("cp1252"))
    assert _read_source_bytes(p, warn=False) == "class CaféOrder {}\n".encode("utf-8")


@pytest.mark.parametrize("data", [
    "a = 1\r\nb = 'é'\r\n".encode("utf-8"),
    "a = 1\rb = 2\r".encode("utf-8"),
    "﻿a = 'é'\n".encode("utf-8"),
    "a = 1\r\n\rb = 2\n".encode("utf-8"),
])
def test_read_source_text_matches_read_text_for_utf8(tmp_path, data):
    # Regex extractors that used read_text(encoding="utf-8") must see identical text,
    # including universal-newline translation and a kept BOM.
    p = _write(tmp_path, data, "f.txt")
    assert _read_source_text(p) == p.read_text(encoding="utf-8")


def test_read_source_text_decodes_utf16(tmp_path):
    p = _write(tmp_path, "a = 'é'\r\nb = 2\r\n".encode("utf-16"), "f.txt")
    assert _read_source_text(p) == "a = 'é'\nb = 2\n"


# ── real extraction ───────────────────────────────────────────────────────────

ENCODINGS = {
    "utf-16": lambda s: s.encode("utf-16"),
    "utf-16-be": lambda s: "﻿".encode("utf-16-be") + s.encode("utf-16-be"),
    "utf-32": lambda s: s.encode("utf-32"),
    "cp1252": lambda s: s.encode("cp1252"),
}


def _graph(tmp_path: Path, files: dict[str, bytes]):
    for name, data in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(data)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    nodes = {(n["id"], n["label"]) for n in r["nodes"]}
    edges = {(e["source"], e["target"], e["relation"]) for e in r["edges"]}
    return nodes, edges


SOURCES = {
    "Order.cs": (
        "namespace Shop {\n  public class CaféOrder {\n    public void Pay() { Charge(); }\n"
        "    public void Charge() { }\n  }\n}\n",
        "CaféOrder",
    ),
    "Order.java": (
        "public class CaféOrder {\n  public void pay() { charge(); }\n  public void charge() { }\n}\n",
        "CaféOrder",
    ),
    "order.py": (
        "class CaféOrder:\n    def pay(self):\n        return self.charge()\n\n"
        "    def charge(self):\n        return 1\n",
        "CaféOrder",
    ),
}


@pytest.mark.parametrize("encoding", list(ENCODINGS))
@pytest.mark.parametrize("name", list(SOURCES))
def test_graph_is_identical_to_the_utf8_graph(tmp_path, name, encoding):
    text, cls = SOURCES[name]
    want_nodes, want_edges = _graph(tmp_path / "utf8", {name: text.encode("utf-8")})
    assert cls in {label for _, label in want_nodes}
    assert any(rel == "calls" for _, _, rel in want_edges)

    got_nodes, got_edges = _graph(tmp_path / encoding, {name: ENCODINGS[encoding](text)})
    assert got_nodes == want_nodes
    assert got_edges == want_edges


def test_cp1252_file_warns_once_through_every_pass(tmp_path, capsys):
    text, _ = SOURCES["order.py"]
    _graph(tmp_path, {"order.py": text.encode("cp1252")})
    err = capsys.readouterr().err
    assert err.count("order.py is not valid UTF-8") == 1, err


def test_utf16_python_import_resolves_across_files(tmp_path):
    # The cross-file resolution pass re-reads the importer's source.
    files = {
        "pkg/__init__.py": b"",
        "pkg/helpers.py": "def helper():\n    return 1\n".encode("utf-8"),
        "pkg/main.py": "from pkg.helpers import helper\n\n\ndef run():\n    return helper()\n".encode("utf-16"),
    }
    nodes, edges = _graph(tmp_path, files)
    label = dict(nodes)
    calls = {(label.get(s), label.get(t)) for s, t, rel in edges if rel == "calls"}
    assert ("run()", "helper()") in calls, calls


@pytest.mark.parametrize("name, text, want", [
    pytest.param(
        "schema.sql",
        "CREATE TABLE Orders (id INT);\nCREATE VIEW RecentOrders AS SELECT id FROM Orders;\n",
        {"Orders", "RecentOrders"},
        marks=pytest.mark.skipif(
            importlib.util.find_spec("tree_sitter_sql") is None,
            reason="tree-sitter-sql not installed (optional [sql] extra)",
        ),
    ),
    ("Deploy.ps1",
     "function Invoke-Deploy {\n    Get-Config\n}\nfunction Get-Config {\n    return 1\n}\n",
     {"Invoke-Deploy()", "Get-Config()"}),
    ("Card.svelte",
     "<script>\n  export function formatPrice(p) { return p; }\n</script>\n<p>{formatPrice(1)}</p>\n",
     {"formatPrice()"}),
])
def test_utf16_files_from_windows_tools_are_extracted(tmp_path, name, text, want):
    nodes, _ = _graph(tmp_path, {name: text.encode("utf-16")})
    labels = {label for _, label in nodes}
    assert want <= labels, labels


def test_utf16_spock_spec_keeps_its_feature_methods(tmp_path):
    spec = (
        "import spock.lang.Specification\n\n"
        "class OrderSpec extends Specification {\n"
        "    def \"pays the café order\"() {\n        expect: true\n    }\n}\n"
    )
    nodes, _ = _graph(tmp_path, {"OrderSpec.groovy": spec.encode("utf-16")})
    labels = {label for _, label in nodes}
    assert "OrderSpec" in labels, labels
    assert any("pays the café order" in label for label in labels), labels


def test_utf16_catch2_test_case_is_recovered(tmp_path):
    src = '#include "catch.hpp"\n\nTEST_CASE("pays the café order") {\n    REQUIRE(true);\n}\n'
    nodes, _ = _graph(tmp_path, {"order_test.cpp": src.encode("utf-16")})
    labels = {label for _, label in nodes}
    assert any("pays the café order" in label for label in labels), labels


# ── the semantic pass: whole-file and slice readers must agree ───────────────

@pytest.mark.parametrize("encoding", ["utf-8", "utf-8-sig", "utf-16", "cp1252"])
def test_whole_file_and_slice_readers_give_the_same_text(tmp_path, encoding):
    # A document small enough to send whole goes through llm._file_to_text; a
    # bigger one is cut by offsets into file_slice.unit_source_text. If the two
    # read a file differently, a UTF-16 note reaches the model as NUL-riddled
    # garbage when small and as clean text when big.
    from graphify.file_slice import unit_source_text
    from graphify.llm import _file_to_text

    text = "# Café notes\r\n\r\nSome text about the café.\r\n"
    p = tmp_path / "notes.md"
    p.write_bytes(text.encode(encoding))
    assert _file_to_text(p) == unit_source_text(p)
    assert _file_to_text(p).lstrip("﻿") == text.replace("\r\n", "\n")
