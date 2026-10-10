"""Tests for how graphify.ingest classifies and routes a URL."""
from __future__ import annotations

import urllib.parse

import pytest

import graphify.ingest as ingest_mod
from graphify.ingest import _detect_url_type


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.com/user/status/1", "tweet"),
        ("https://twitter.com/user/status/1", "tweet"),
        ("https://mobile.twitter.com/user/status/1", "tweet"),
        ("https://X.COM/user/status/1", "tweet"),
        ("https://arxiv.org/abs/2301.12345", "arxiv"),
        ("https://export.arxiv.org/abs/2301.12345", "arxiv"),
        ("https://github.com/owner/repo", "github"),
        ("https://www.youtube.com/watch?v=abc", "youtube"),
        ("https://youtu.be/abc", "youtube"),
    ],
)
def test_known_hosts_keep_their_type(url, expected):
    assert _detect_url_type(url) == expected


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        # Hosts that end in "x.com" without being x.com.
        ("https://www.dropbox.com/scl/fi/abc123/paper.pdf?dl=1", "pdf"),
        ("https://www.netflix.com/title/80057281", "webpage"),
        ("https://www.linux.com/news/", "webpage"),
        ("https://developer.box.com/guides/", "webpage"),
        ("https://x.com.example.org/status/1", "webpage"),
        # The name only appears in the path or the query.
        ("https://example.org/why-arxiv.org-matters", "webpage"),
        ("https://example.org/?ref=github.com", "webpage"),
        ("https://example.org/embed?src=youtube.com", "webpage"),
    ],
)
def test_a_host_is_matched_whole_not_as_url_text(url, expected):
    assert _detect_url_type(url) == expected


def test_a_dropbox_pdf_is_downloaded_not_saved_as_a_tweet_stub(tmp_path, monkeypatch):
    """dropbox.com contains "x.com", so the link went to the tweet oEmbed endpoint
    and was saved as an empty "Tweet at ... (could not fetch content)" note."""
    url = "https://www.dropbox.com/scl/fi/abc123/paper.pdf?dl=1"
    fetched = []

    def fake_safe_fetch(u):
        fetched.append(u)
        return b"%PDF-1.7 test"

    def no_text_fetch(u):
        raise AssertionError(f"unexpected text fetch: {u}")

    monkeypatch.setattr(ingest_mod, "validate_url", lambda u: u)
    monkeypatch.setattr(ingest_mod, "safe_fetch", fake_safe_fetch)
    monkeypatch.setattr(ingest_mod, "safe_fetch_text", no_text_fetch)

    out = ingest_mod.ingest(url, tmp_path)

    assert fetched == [url]
    assert out.suffix == ".pdf"
    assert out.read_bytes() == b"%PDF-1.7 test"


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.com/user/status/1", "https://twitter.com/user/status/1"),
        ("https://mobile.x.com/user/status/1", "https://mobile.twitter.com/user/status/1"),
        ("https://X.COM/user/status/1", "https://twitter.com/user/status/1"),
        # "x.com" outside the host must survive untouched.
        (
            "https://x.com/user/status/1?next=https://x.com/home",
            "https://twitter.com/user/status/1?next=https://x.com/home",
        ),
        (
            "https://twitter.com/dropbox.com_fan/status/1",
            "https://twitter.com/dropbox.com_fan/status/1",
        ),
    ],
)
def test_tweet_oembed_rewrites_only_the_host(url, expected, monkeypatch):
    """The x.com -> twitter.com rewrite for oEmbed was a replace over the whole
    URL, so "x.com" inside the path or query (e.g. a dropbox.com handle, a
    ?next= link) was rewritten too, sending oEmbed a different URL."""
    requested = []

    def fake_fetch_text(u):
        requested.append(u)
        return '{"html": "<p>hi</p>", "author_name": "someone"}'

    monkeypatch.setattr(ingest_mod, "safe_fetch_text", fake_fetch_text)

    ingest_mod._fetch_tweet(url, None, None)

    query = urllib.parse.parse_qs(urllib.parse.urlsplit(requested[0]).query)
    assert query["url"] == [expected]
