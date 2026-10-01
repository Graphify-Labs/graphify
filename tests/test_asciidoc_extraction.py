"""AsciiDoc files extract like Markdown documents (#3238).

``.adoc`` / ``.asciidoc`` files were invisible to the graph: no extractor
claimed them, so they contributed nothing. They now ride the Markdown
extractor (headings ``=`` / ``==`` / ``===`` nest like ``#`` / ``##`` /
``###``), are classified as documents, and are sliced/linked as documents.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import DOC_EXTENSIONS, FileType, classify_file
from graphify.extract import _get_extractor
from graphify.extractors.markdown import extract_markdown

_GUIDE_ADOC = """\
= Guide

Start here.

== Rendering

Details.

=== Pinned

More details.
"""


def _write(tmp_path: Path, name: str, body: str) -> Path:
    p = tmp_path / name
    p.write_text(body, encoding="utf-8")
    return p


def test_adoc_extensions_are_documents():
    assert ".adoc" in DOC_EXTENSIONS
    assert ".asciidoc" in DOC_EXTENSIONS


def test_adoc_classified_as_document(tmp_path: Path):
    assert classify_file(_write(tmp_path, "guide.adoc", _GUIDE_ADOC)) is FileType.DOCUMENT
    assert classify_file(_write(tmp_path, "guide.asciidoc", _GUIDE_ADOC)) is FileType.DOCUMENT


def test_adoc_dispatch_uses_markdown_extractor(tmp_path: Path):
    assert _get_extractor(_write(tmp_path, "a.adoc", "x")) is extract_markdown
    assert _get_extractor(_write(tmp_path, "a.asciidoc", "x")) is extract_markdown


def test_adoc_headings_extracted_like_markdown(tmp_path: Path):
    result = extract_markdown(_write(tmp_path, "guide.adoc", _GUIDE_ADOC))
    by_label = {n["label"]: n for n in result["nodes"]}
    assert set(by_label) == {"guide.adoc", "Guide", "Rendering", "Pinned"}
    assert by_label["Guide"]["node_kind"] == "heading"
    contains = {(e["source"], e["target"]) for e in result["edges"] if e["relation"] == "contains"}
    page = by_label["guide.adoc"]["id"]
    assert (page, by_label["Guide"]["id"]) in contains
    assert (by_label["Guide"]["id"], by_label["Rendering"]["id"]) in contains
    assert (by_label["Rendering"]["id"], by_label["Pinned"]["id"]) in contains


def test_adoc_bare_equals_line_is_not_a_heading(tmp_path: Path):
    # A setext-style `===` underline (no trailing text) must not mint a node.
    result = extract_markdown(_write(tmp_path, "n.adoc", "Title\n=====\n\nBody.\n"))
    assert [n["label"] for n in result["nodes"]] == ["n.adoc"]


def test_markdown_headings_still_work(tmp_path: Path):
    result = extract_markdown(_write(tmp_path, "g.md", "# Guide\n\n## Rendering\n"))
    assert {n["label"] for n in result["nodes"]} == {"g.md", "Guide", "Rendering"}
