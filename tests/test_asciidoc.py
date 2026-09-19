"""AsciiDoc documentation reaches the graph (#2938).

`.adoc` was in no extension set: a project documented in AsciiDoc had only
the PNGs beside its docs ingested. Now `.adoc`/`.asciidoc` are documents —
sliced, token-estimated and digested like markdown — and a structural pass
mirrors the markdown extractor: page node, section headings nested by
level, and `include::`/`xref:`/`link:` targets as `references` edges onto
the linked document's own node.
"""
from __future__ import annotations

import io
from contextlib import redirect_stdout
from pathlib import Path

import pytest

from graphify.detect import DOC_EXTENSIONS, FileType, classify_file, detect
from graphify.extract import _get_extractor, extract
from graphify.extractors.asciidoc import (
    ASCIIDOC_EXTENSIONS,
    _resolve_doc_link,
    extract_asciidoc,
)
from graphify.extractors.markdown import _MD_LINKABLE_EXTS
from graphify.file_slice import _SPLITTABLE_TEXT_SUFFIXES

GUIDE = """= Operations Guide
:author: Ops Team
:toc:

// a comment line
== Deploy

See xref:runbook.adoc[the runbook], link:https://example.com[site],
link:checklist.md[checklist] and <<parts/alerts.adoc#p1,alerts>>.
Also <<in-page-anchor>> and xref:runbook#steps[again].

include::parts/alerts.adoc[]
include::{snippets}/gen.adoc[]

----
== not a heading inside a listing
xref:ignored.adoc[]
----

....
include::ignored-too.adoc[]
....

=== Rollback

== Monitor
"""


@pytest.fixture
def docs(tmp_path):
    d = tmp_path / "docs"
    (d / "parts").mkdir(parents=True)
    (d / "guide.adoc").write_text(GUIDE, encoding="utf-8")
    (d / "runbook.adoc").write_text("= Runbook\n\n== Steps\n", encoding="utf-8")
    (d / "checklist.md").write_text("# Checklist\n\nSee [guide](./guide.adoc).\n", encoding="utf-8")
    (d / "parts" / "alerts.adoc").write_text("== Alerts\n", encoding="utf-8")
    return d


def _by(result):
    nodes = {n["id"]: n for n in result["nodes"]}
    edges = [(nodes[e["source"]]["label"] if e["source"] in nodes else e["source"],
              e["relation"],
              Path(e["target_file"]).name if e.get("target_file") else
              (nodes[e["target"]]["label"] if e["target"] in nodes else e["target"]))
             for e in result["edges"]]
    return nodes, edges


# ---------------------------------------------------------------------------
# Detection, dispatch, slicing
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ext", sorted(ASCIIDOC_EXTENSIONS))
def test_asciidoc_is_a_document_everywhere_a_document_is_decided(ext):
    assert ext in DOC_EXTENSIONS
    assert classify_file(Path(f"x{ext}")) is FileType.DOCUMENT
    assert _get_extractor(Path(f"x{ext}")) is extract_asciidoc
    assert ext in _SPLITTABLE_TEXT_SUFFIXES  # an oversized manual is sliced, not truncated
    assert ext in _MD_LINKABLE_EXTS  # a markdown doc may link to it


def test_detect_lists_adoc_files_as_documents(docs):
    with redirect_stdout(io.StringIO()):
        found = detect(docs.parent)["files"]
    names = {Path(p).name for p in found["document"]}
    assert {"guide.adoc", "runbook.adoc", "alerts.adoc", "checklist.md"} <= names


# ---------------------------------------------------------------------------
# Structure
# ---------------------------------------------------------------------------

def test_the_page_node_carries_the_document_title_and_header_attributes(docs):
    nodes, _ = _by(extract_asciidoc(docs / "guide.adoc"))
    page = next(n for n in nodes.values() if n["node_kind"] == "page")
    assert page["label"] == "guide.adoc"
    assert page["title"] == "Operations Guide"
    assert page["frontmatter"]["author"] == "Ops Team"
    assert page["file_type"] == "document"


def test_sections_nest_by_level_like_markdown_headings(docs):
    nodes, edges = _by(extract_asciidoc(docs / "guide.adoc"))
    headings = [n["label"] for n in nodes.values() if n["node_kind"] == "heading"]
    assert headings == ["Deploy", "Rollback", "Monitor"]
    assert ("guide.adoc", "contains", "Deploy") in edges
    assert ("Deploy", "contains", "Rollback") in edges
    assert ("guide.adoc", "contains", "Monitor") in edges


def test_delimited_blocks_and_comments_are_skipped(docs):
    nodes, edges = _by(extract_asciidoc(docs / "guide.adoc"))
    labels = {n["label"] for n in nodes.values()}
    assert "not a heading inside a listing" not in labels
    assert not any(t in ("ignored.adoc", "ignored-too.adoc") for _, _, t in edges)


def test_a_repeated_section_title_still_yields_two_nodes(tmp_path):
    p = tmp_path / "a.adoc"
    p.write_text("== Usage\n\n== Usage\n", encoding="utf-8")
    nodes, _ = _by(extract_asciidoc(p))
    assert sum(1 for n in nodes.values() if n["label"] == "Usage") == 2


def test_a_document_without_a_title_line_still_has_a_page_node(tmp_path):
    p = tmp_path / "frag.adoc"
    p.write_text("Just prose.\n\n== Part\n", encoding="utf-8")
    nodes, _ = _by(extract_asciidoc(p))
    page = next(n for n in nodes.values() if n["node_kind"] == "page")
    assert "title" not in page and page["label"] == "frag.adoc"


def test_an_unreadable_file_reports_an_error_not_a_crash(tmp_path):
    r = extract_asciidoc(tmp_path / "missing.adoc")
    assert r["nodes"] == [] and "error" in r


# ---------------------------------------------------------------------------
# References
# ---------------------------------------------------------------------------

def test_include_xref_link_and_angle_xref_become_references(docs):
    _, edges = _by(extract_asciidoc(docs / "guide.adoc"))
    refs = {t for s, r, t in edges if r == "references"}
    assert refs == {"runbook.adoc", "alerts.adoc", "checklist.md"}


def test_each_target_is_referenced_once_however_often_it_is_named(docs):
    """runbook is named by xref twice (one extension-less, with an anchor)."""
    _, edges = _by(extract_asciidoc(docs / "guide.adoc"))
    assert sum(1 for s, r, t in edges if r == "references" and t == "runbook.adoc") == 1


@pytest.mark.parametrize("raw", [
    "https://example.com/x.adoc", "mailto:a@b.c", "#anchor", "", "{docdir}/x.adoc",
    "diagram.png", "script.py",
])
def test_external_anchor_attribute_and_non_document_targets_are_skipped(raw, tmp_path):
    assert _resolve_doc_link(raw, tmp_path) is None


def test_an_extensionless_xref_names_a_sibling_adoc(tmp_path):
    assert _resolve_doc_link("runbook#steps", tmp_path) == tmp_path / "runbook.adoc"
    assert _resolve_doc_link("../guide.adoc", tmp_path / "parts") == tmp_path / "guide.adoc"


def test_an_existing_target_is_stamped_for_the_incremental_remap(docs):
    r = extract_asciidoc(docs / "guide.adoc")
    stamped = {Path(e["target_file"]).name for e in r["edges"] if e.get("target_file")}
    assert {"runbook.adoc", "alerts.adoc", "checklist.md"} <= stamped


# ---------------------------------------------------------------------------
# Corpus level
# ---------------------------------------------------------------------------

def test_references_merge_into_the_linked_documents_own_nodes(docs):
    root = docs.parent
    files = sorted(p for p in docs.rglob("*") if p.is_file())
    with redirect_stdout(io.StringIO()):
        g = extract(files, cache_root=root, root=root)
    labels = {n["id"]: n["label"] for n in g["nodes"]}
    refs = {(labels[e["source"]], labels.get(e["target"], "DANGLING"))
            for e in g["edges"] if e["relation"] == "references"}
    assert ("guide.adoc", "runbook.adoc") in refs
    assert ("guide.adoc", "alerts.adoc") in refs
    assert ("guide.adoc", "checklist.md") in refs
    assert ("checklist.md", "guide.adoc") in refs  # markdown -> asciidoc link resolves too
    assert "DANGLING" not in {t for _, t in refs}
    assert not any("target_file" in e for e in g["edges"])


def test_a_nested_block_closes_only_on_its_own_delimiter_length(tmp_path):
    """`====` opens an example block; a `======` inside it is a nested block,
    not the close - the outer block ends at the next `====`."""
    p = tmp_path / "n.adoc"
    p.write_text("== Real" + chr(10) + "====" + chr(10) + "== Inside outer" + chr(10) + "======" + chr(10)
                 + "== Inside nested" + chr(10) + "======" + chr(10) + "== Still inside outer" + chr(10) + "====" + chr(10)
                 + "== After" + chr(10), encoding="utf-8")
    nodes, _ = _by(extract_asciidoc(p))
    assert [n["label"] for n in nodes.values() if n["node_kind"] == "heading"] == ["Real", "After"]


def test_both_extensions_are_in_the_hook_source_list():
    from graphify.cli import _HOOK_SOURCE_EXTS
    assert ".adoc" in _HOOK_SOURCE_EXTS and ".asciidoc" in _HOOK_SOURCE_EXTS
