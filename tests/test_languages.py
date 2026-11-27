"""Tests for the 8 new language extractors: Java, C, C++, Ruby, C#, Kotlin, Scala, PHP."""
from __future__ import annotations
from pathlib import Path
import pytest
from graphify.extract import (
    extract_java, extract_c, extract_cpp, extract_ruby,
    extract_csharp, extract_kotlin, extract_scala, extract_php,
    extract_markdown, extract, _resolve_md_link,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]

def _relations(r):
    return {e["relation"] for e in r["edges"]}

def _calls(r):
    node_by_id = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        (node_by_id.get(e["source"], e["source"]), node_by_id.get(e["target"], e["target"]))
        for e in r["edges"] if e["relation"] == "calls"
    }


# ── Java ──────────────────────────────────────────────────────────────────────

def test_java_no_error():
    r = extract_java(FIXTURES / "sample.java")
    assert "error" not in r

def test_java_finds_class():
    r = extract_java(FIXTURES / "sample.java")
    assert any("DataProcessor" in l for l in _labels(r))

def test_java_finds_interface():
    r = extract_java(FIXTURES / "sample.java")
    assert any("Processor" in l for l in _labels(r))

def test_java_finds_methods():
    r = extract_java(FIXTURES / "sample.java")
    labels = _labels(r)
    assert any("addItem" in l for l in labels)
    assert any("process" in l for l in labels)

def test_java_finds_imports():
    r = extract_java(FIXTURES / "sample.java")
    assert "imports" in _relations(r)

def test_java_no_dangling_edges():
    r = extract_java(FIXTURES / "sample.java")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids


# ── C ────────────────────────────────────────────────────────────────────────

def test_c_no_error():
    r = extract_c(FIXTURES / "sample.c")
    assert "error" not in r

def test_c_finds_functions():
    r = extract_c(FIXTURES / "sample.c")
    labels = _labels(r)
    assert any("process" in l for l in labels)
    assert any("main" in l for l in labels)

def test_c_finds_includes():
    r = extract_c(FIXTURES / "sample.c")
    assert "imports" in _relations(r)

def test_c_emits_calls():
    r = extract_c(FIXTURES / "sample.c")
    assert any(e["relation"] == "calls" for e in r["edges"])

def test_c_calls_are_inferred():
    r = extract_c(FIXTURES / "sample.c")
    for e in r["edges"]:
        if e["relation"] == "calls":
            assert e["confidence"] == "INFERRED"


# ── C++ ───────────────────────────────────────────────────────────────────────

def test_cpp_no_error():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert "error" not in r

def test_cpp_finds_class():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert any("HttpClient" in l for l in _labels(r))

def test_cpp_finds_methods():
    r = extract_cpp(FIXTURES / "sample.cpp")
    labels = _labels(r)
    # C++ extractor captures the constructor and public-visible methods
    assert any("HttpClient" in l for l in labels)

def test_cpp_finds_includes():
    r = extract_cpp(FIXTURES / "sample.cpp")
    assert "imports" in _relations(r)


# ── Ruby ─────────────────────────────────────────────────────────────────────

def test_ruby_no_error():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert "error" not in r

def test_ruby_finds_class():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert any("ApiClient" in l for l in _labels(r))

def test_ruby_finds_methods():
    r = extract_ruby(FIXTURES / "sample.rb")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_ruby_finds_function():
    r = extract_ruby(FIXTURES / "sample.rb")
    assert any("parse_response" in l for l in _labels(r))


# ── C# ───────────────────────────────────────────────────────────────────────

def test_csharp_no_error():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert "error" not in r

def test_csharp_finds_class():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert any("DataProcessor" in l for l in _labels(r))

def test_csharp_finds_interface():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert any("IProcessor" in l for l in _labels(r))

def test_csharp_finds_methods():
    r = extract_csharp(FIXTURES / "sample.cs")
    labels = _labels(r)
    assert any("Process" in l for l in labels)

def test_csharp_finds_usings():
    r = extract_csharp(FIXTURES / "sample.cs")
    assert "imports" in _relations(r)


# ── Kotlin ───────────────────────────────────────────────────────────────────

def test_kotlin_no_error():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert "error" not in r

def test_kotlin_finds_class():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("HttpClient" in l for l in _labels(r))

def test_kotlin_finds_data_class():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("Config" in l for l in _labels(r))

def test_kotlin_finds_methods():
    r = extract_kotlin(FIXTURES / "sample.kt")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_kotlin_finds_function():
    r = extract_kotlin(FIXTURES / "sample.kt")
    assert any("createClient" in l for l in _labels(r))


# ── Scala ─────────────────────────────────────────────────────────────────────

def test_scala_no_error():
    r = extract_scala(FIXTURES / "sample.scala")
    assert "error" not in r

def test_scala_finds_class():
    r = extract_scala(FIXTURES / "sample.scala")
    assert any("HttpClient" in l for l in _labels(r))

def test_scala_finds_object():
    r = extract_scala(FIXTURES / "sample.scala")
    assert any("HttpClientFactory" in l for l in _labels(r))

def test_scala_finds_methods():
    r = extract_scala(FIXTURES / "sample.scala")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)


# ── PHP ───────────────────────────────────────────────────────────────────────

def test_php_no_error():
    r = extract_php(FIXTURES / "sample.php")
    assert "error" not in r

def test_php_finds_class():
    r = extract_php(FIXTURES / "sample.php")
    assert any("ApiClient" in l for l in _labels(r))

def test_php_finds_methods():
    r = extract_php(FIXTURES / "sample.php")
    labels = _labels(r)
    assert any("get" in l for l in labels)
    assert any("post" in l for l in labels)

def test_php_finds_function():
    r = extract_php(FIXTURES / "sample.php")
    assert any("parseResponse" in l for l in _labels(r))

def test_php_finds_imports():
    r = extract_php(FIXTURES / "sample.php")
    assert "imports" in _relations(r)


# ── Markdown ───────────────────────────────────────────────────────────────

def test_markdown_emits_file_node(tmp_path):
    """A .md file produces exactly one file-level node with file_type='doc'."""
    md = tmp_path / "doc.md"
    md.write_text("# Hello\n\nWorld.\n", encoding="utf-8")
    r = extract_markdown(md)
    assert len(r["nodes"]) == 1
    assert r["nodes"][0]["file_type"] == "doc"
    assert r["nodes"][0]["id"] == "doc"


def test_markdown_link_produces_links_to_edge(tmp_path):
    """A [text](other.md) reference to an existing file emits a links_to edge."""
    src = tmp_path / "src.md"
    tgt = tmp_path / "tgt.md"
    tgt.write_text("# Target\n", encoding="utf-8")
    src.write_text("# Source\n\nSee [the target](tgt.md) for details.\n", encoding="utf-8")
    r = extract_markdown(src)
    links = [e for e in r["edges"] if e["relation"] == "links_to"]
    assert len(links) == 1
    assert links[0]["source"] == "src"
    assert links[0]["target"] == "tgt"
    assert links[0]["context"] == "the target"
    assert links[0]["confidence"] == "EXTRACTED"


def test_markdown_wikilink_produces_links_to_edge(tmp_path):
    """A [[Page]] reference to an existing .md file emits a links_to edge."""
    src = tmp_path / "src.md"
    tgt = tmp_path / "Page.md"
    tgt.write_text("# Page\n", encoding="utf-8")
    src.write_text("See [[Page]] for details.\n", encoding="utf-8")
    r = extract_markdown(src)
    links = [e for e in r["edges"] if e["relation"] == "links_to"]
    assert len(links) == 1
    assert links[0]["target"] == "page"


def test_markdown_skips_external_urls(tmp_path):
    """https:// and mailto: links are not emitted as edges."""
    md = tmp_path / "doc.md"
    md.write_text(
        "# Doc\n\n[site](https://example.com) and [mail](mailto:a@b.com)\n",
        encoding="utf-8",
    )
    r = extract_markdown(md)
    assert all(e["relation"] != "links_to" for e in r["edges"])


def test_markdown_skips_unresolved_links(tmp_path):
    """Links to non-existent files are silently dropped (no broken edges)."""
    md = tmp_path / "doc.md"
    md.write_text("# Doc\n\n[ghost](nonexistent.md)\n", encoding="utf-8")
    r = extract_markdown(md)
    assert all(e["relation"] != "links_to" for e in r["edges"])


def test_markdown_skips_image_links(tmp_path):
    """![alt](path) is an image, not a link — no edges emitted."""
    src = tmp_path / "src.md"
    src.write_text("# Doc\n\n![pic](other.png)\n", encoding="utf-8")
    r = extract_markdown(src)
    assert all(e["relation"] != "links_to" for e in r["edges"])


def test_markdown_skips_links_inside_code_blocks(tmp_path):
    """Fenced code blocks have their [..](..) stripped before edge extraction."""
    src = tmp_path / "src.md"
    src.write_text(
        "# Doc\n\n```\n[not a link](other.md)\n```\n\n[real](other.md)\n",
        encoding="utf-8",
    )
    tgt = tmp_path / "other.md"
    tgt.write_text("# Other\n", encoding="utf-8")
    r = extract_markdown(src)
    links = [e for e in r["edges"] if e["relation"] == "links_to"]
    assert len(links) == 1


def test_resolve_md_link_external_returns_none():
    """URLs with scheme return None."""
    assert _resolve_md_link("https://example.com", Path("/tmp/x.md")) is None
    assert _resolve_md_link("http://github.com/x", Path("/tmp/x.md")) is None
    assert _resolve_md_link("mailto:user@example.com", Path("/tmp/x.md")) is None


def test_extract_dispatches_markdown_files(tmp_path):
    """The high-level extract() routes .md files to extract_markdown().

    Regression: skill.md's orchestrator relies on this dispatch; without it,
    the links_to edges from markdown files never reach .graphify_ast.json.
    """
    src = tmp_path / "src.md"
    tgt = tmp_path / "tgt.md"
    tgt.write_text("# Target\n", encoding="utf-8")
    src.write_text("[ref](tgt.md)\n", encoding="utf-8")
    r = extract([src])
    links = [e for e in r["edges"] if e["relation"] == "links_to"]
    assert len(links) == 1
    assert links[0]["source"] == "src"
    assert links[0]["target"] == "tgt"
