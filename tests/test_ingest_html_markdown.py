"""`_html_to_markdown` keeps the word boundaries a page carries.

markdownify drops an inline element that holds nothing but whitespace, and takes the
whitespace with it, so two words are ingested as one.
"""
from __future__ import annotations

import pytest

from graphify.ingest import _html_to_markdown

pytest.importorskip("markdownify")

URL = "https://example.test/page"


@pytest.mark.parametrize(
    "tag", ["a", "b", "strong", "em", "i", "s", "del", "code", "sub", "sup"]
)
def test_whitespace_only_element_keeps_the_word_boundary(tag: str) -> None:
    attributes = ' href="https://example.test"' if tag == "a" else ""

    assert _html_to_markdown(f"<p>Hello<{tag}{attributes}> </{tag}>world</p>", URL).strip() == "Hello world"


def test_space_between_two_styled_runs_survives() -> None:
    """An editor that emits one element per styled run puts the space in its own element."""
    html = "<p><b>First</b><b> </b><b>Last</b></p>"

    assert _html_to_markdown(html, URL).strip() == "**First** **Last**"


@pytest.mark.parametrize(
    ("html", "expected"),
    [
        ("<p>Hello <b>bold</b> world</p>", "Hello **bold** world"),
        ("<p>Hello <em>it</em> world</p>", "Hello *it* world"),
        ("<p>Hello <code>x</code> world</p>", "Hello `x` world"),
        ("<h1>Title</h1>", "# Title"),
        ("<ul><li>item</li></ul>", "- item"),
        ('<p>a<img src="x.png">b</p>', "ab"),
    ],
)
def test_conversion_options_and_content_are_unchanged(html: str, expected: str) -> None:
    """The control: headings stay ATX, bullets stay `-`, images stay stripped."""
    assert _html_to_markdown(html, URL).strip() == expected


def test_script_and_style_text_never_reaches_the_output() -> None:
    html = "<p>Hello</p><script>var secret = 1;</script><style>p{color:red}</style>"

    markdown = _html_to_markdown(html, URL)

    assert "secret" not in markdown
    assert "color:red" not in markdown
