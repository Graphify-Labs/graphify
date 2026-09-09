"""Regression tests for wikilink heading anchors (#3333).

`_MD_WIKILINK_RE` was `\\[\\[([^\\]|#]+)(?:[#|][^\\]]*)?\\]\\]`, which had two
defects:

1. `[[#Heading]]` did not match at all — the page-name group demanded at least
   one character before the `#`, so a same-page anchor never entered the link
   list and the whole `[[#Heading]]` convention was silently invisible.
2. In `[[Page#Heading|alias]]` the non-capturing group swallowed everything from
   the `#` onward, so the fragment was discarded and the link could only ever
   resolve to `Page`.

The extractor already emits a node per heading, so a same-page anchor has a real
target: the fix resolves it to that heading's node, attributed to the section the
link was written in (the same parent rule heading nesting uses). Resolution is
existence-gated — an anchor naming no heading in the file stays edge-free.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extractors.base import _file_stem, _make_id
from graphify.extractors.markdown import _MD_WIKILINK_RE, extract_markdown


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _refs(result: dict) -> set[tuple[str, str]]:
    return {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "references"
    }


def _page(path: Path) -> str:
    """Id of *path*'s own page node, as `extract_markdown` builds it."""
    return _make_id(str(path))


def _heading(path: Path, title: str) -> str:
    """Id of a heading node inside *path*."""
    return _make_id(_file_stem(path), title)


# --- the regex itself -------------------------------------------------------

def test_same_page_anchor_matches():
    m = _MD_WIKILINK_RE.search("[[#SomeHeading]]")
    assert m is not None
    assert m.group(1) == ""
    assert m.group(2) == "SomeHeading"


def test_cross_page_anchor_keeps_both_halves():
    m = _MD_WIKILINK_RE.search("[[Other Page#SomeHeading|alias]]")
    assert m is not None
    assert m.group(1) == "Other Page"
    assert m.group(2) == "SomeHeading"


def test_plain_and_aliased_wikilinks_are_unchanged():
    assert _MD_WIKILINK_RE.search("[[Other Page]]").group(1) == "Other Page"
    assert _MD_WIKILINK_RE.search("[[Other Page|alias]]").group(1) == "Other Page"
    assert _MD_WIKILINK_RE.search("![[embedded.png]]") is None


# --- resolution -------------------------------------------------------------

def test_same_page_anchor_links_to_the_heading_node(tmp_path: Path):
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\nSee [[#Setup]].\n\n## Setup\n\nInstall it.\n",
    )

    result = extract_markdown(doc)

    assert (_heading(doc, "Notes"), _heading(doc, "Setup")) in _refs(result)


def test_the_anchor_is_attributed_to_its_enclosing_section(tmp_path: Path):
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\n## Overview\n\nSee [[#Setup]].\n\n## Setup\n\nInstall it.\n",
    )

    result = extract_markdown(doc)

    assert (_heading(doc, "Overview"), _heading(doc, "Setup")) in _refs(result)
    assert (_heading(doc, "Notes"), _heading(doc, "Setup")) not in _refs(result)


def test_an_anchor_above_its_target_resolves(tmp_path: Path):
    """The heading is declared below the link, so resolution must be deferred."""
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\n[[#Later]]\n\n## Later\n",
    )

    result = extract_markdown(doc)

    assert (_heading(doc, "Notes"), _heading(doc, "Later")) in _refs(result)


def test_the_longhand_same_page_form_resolves_too(tmp_path: Path):
    """`[[notes#Usage]]` inside notes.md is the same link as `[[#Usage]]`, and
    used to be dropped entirely by the self-reference guard."""
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\nSee [[notes#Usage]].\n\n## Usage\n\nRun it.\n",
    )

    result = extract_markdown(doc)

    assert (_heading(doc, "Notes"), _heading(doc, "Usage")) in _refs(result)


def test_an_anchor_naming_no_heading_is_not_fabricated(tmp_path: Path):
    doc = _write(tmp_path / "notes.md", "# Notes\n\nSee [[#Nowhere]].\n")

    result = extract_markdown(doc)

    assert _refs(result) == set()


def test_an_anchor_to_its_own_section_is_not_a_self_loop(tmp_path: Path):
    doc = _write(tmp_path / "notes.md", "# Notes\n\nSee [[#Notes]].\n")

    result = extract_markdown(doc)

    assert _refs(result) == set()


def test_repeated_anchors_in_one_section_yield_one_edge(tmp_path: Path):
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\n[[#Setup]] and again [[#Setup]].\n\n## Setup\n",
    )

    result = extract_markdown(doc)

    assert len([
        edge for edge in result["edges"]
        if edge["relation"] == "references"
    ]) == 1


def test_a_duplicate_heading_title_resolves_to_the_first(tmp_path: Path):
    """The second `## Setup` gets a line-suffixed id; Obsidian's own anchor
    resolution picks the first, and so does this."""
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\n[[#Setup]]\n\n## Setup\n\n## Setup\n",
    )

    result = extract_markdown(doc)

    assert (_heading(doc, "Notes"), _heading(doc, "Setup")) in _refs(result)


def test_a_cross_page_anchored_link_still_reaches_the_page(tmp_path: Path):
    """Unchanged behavior: a fragment into *another* file resolves to the page,
    since a heading id there cannot be verified from inside this extractor."""
    doc = _write(tmp_path / "notes.md", "# Notes\n\nSee [[other#Details|d]].\n")
    other = _write(tmp_path / "other.md", "# Other\n\n## Details\n")

    result = extract_markdown(doc)

    assert (_page(doc), _page(other)) in _refs(result)


def test_an_empty_wikilink_names_nothing(tmp_path: Path):
    doc = _write(tmp_path / "notes.md", "# Notes\n\n[[]] and [[|alias]]\n")

    result = extract_markdown(doc)

    assert _refs(result) == set()


def test_an_anchor_inside_a_fenced_block_is_ignored(tmp_path: Path):
    doc = _write(
        tmp_path / "notes.md",
        "# Notes\n\n```\n[[#Setup]]\n```\n\n## Setup\n",
    )

    result = extract_markdown(doc)

    assert _refs(result) == set()
