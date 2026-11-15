r"""A C# file that is not UTF-8 keeps its names when it has a preprocessor directive.

``extract_csharp`` blanks directives before parsing (#5003) and hands the
blanked bytes to the parser as ``source_override``. It read those bytes with
``path.read_bytes()``, so for any file with a directive, even a lone
``#region``, the Windows-1252 / UTF-16 decoding of #4145 was skipped and
tree-sitter saw the raw bytes again: ``Prüfe`` came out as ``Pr``, and an
identifier like that in a method body could derail the parse for the rest of
the type, dropping every member after it.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from graphify.extract import extract
from graphify.extractors import base


@pytest.fixture(autouse=True)
def _fresh_warnings():
    base._warned_source_encodings.clear()
    yield
    base._warned_source_encodings.clear()


ENCODINGS = {
    "cp1252": lambda s: s.encode("cp1252"),
    "utf-16": lambda s: s.encode("utf-16"),
}

# A directive (here only #region) plus a non-ASCII identifier that is both
# declared and called, followed by more members.
SOURCE = (
    "namespace Shop {\n"
    "  public class Order {\n"
    "    #region checks\n"
    "    public bool Run() { return Prüfe() && Next(); }\n"
    "    public bool Prüfe() { return Next(); }\n"
    "    public bool Next() { return Last(); }\n"
    "    public bool Last() { return true; }\n"
    "    #endregion\n"
    "  }\n"
    "}\n"
)


def _graph(tmp_path: Path, data: bytes):
    tmp_path.mkdir(parents=True, exist_ok=True)
    (tmp_path / "Order.cs").write_bytes(data)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path("Order.cs")], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)
    nodes = {(n["id"], n["label"]) for n in r["nodes"]}
    edges = {(e["source"], e["target"], e["relation"]) for e in r["edges"]}
    return nodes, edges


@pytest.mark.parametrize("encoding", list(ENCODINGS))
def test_file_with_directive_gives_the_utf8_graph(tmp_path, encoding):
    want_nodes, want_edges = _graph(tmp_path / "utf8", SOURCE.encode("utf-8"))
    labels = {label for _, label in want_nodes}
    assert any("Prüfe" in label for label in labels), labels

    got_nodes, got_edges = _graph(tmp_path / encoding, ENCODINGS[encoding](SOURCE))
    assert got_nodes == want_nodes
    assert got_edges == want_edges


def test_cp1252_identifier_in_a_body_does_not_drop_later_members(tmp_path):
    nodes, edges = _graph(tmp_path, SOURCE.encode("cp1252"))
    labels = {label for _, label in nodes}
    assert not any(label.endswith(".Pr()") for label in labels), labels
    for name in ("Prüfe", "Next", "Last"):
        assert any(label.endswith(f".{name}()") for label in labels), (name, labels)


def test_cp1252_file_with_directive_warns_once(tmp_path, capsys):
    _graph(tmp_path, SOURCE.encode("cp1252"))
    err = capsys.readouterr().err
    assert err.count("Order.cs is not valid UTF-8") == 1, err


def test_prior_ast_cache_is_not_reused(tmp_path, monkeypatch):
    import graphify.cache as cache
    assert cache._AST_CACHE_SCHEMA > 45
    with monkeypatch.context() as old:
        old.setattr(cache, "_AST_CACHE_SCHEMA", 45)
        _graph(tmp_path, SOURCE.encode("cp1252"))
        # Plant the cut name as if this entry predated the fix.
        for path in (tmp_path / ".cache").rglob("*.json"):
            text = path.read_text(encoding="utf-8")
            path.write_text(text.replace("Prüfe", "Pr").replace("Pr\u00fcfe", "Pr"), encoding="utf-8")
    nodes, _ = _graph(tmp_path, SOURCE.encode("cp1252"))
    assert any(label.endswith(".Prüfe()") for _, label in nodes)
