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


@pytest.mark.parametrize(
    ("first_url", "second_url"),
    [
        ("https://example.org/report.pdf?version=1", "https://example.org/report.pdf?version=2"),
        ("https://example.org/photo.png?version=1", "https://example.org/photo.png?version=2"),
        ("https://example.org/report.pdf", "https://example.org/report.pdf"),
        ("https://example.org/report+a.pdf", "https://example.org/report_a.pdf"),
        ("https://example.org/" + "a" * 90 + "1.pdf", "https://example.org/" + "a" * 90 + "2.pdf"),
    ],
)
def test_binary_captures_preserve_colliding_payloads(first_url, second_url, tmp_path, monkeypatch):
    payloads = iter([b"first capture", b"second capture"])
    fetched = []

    def fetch(url):
        fetched.append(url)
        return next(payloads)

    monkeypatch.setattr(ingest_mod, "validate_url", lambda url: url)
    monkeypatch.setattr(ingest_mod, "safe_fetch", fetch)

    first = ingest_mod.ingest(first_url, tmp_path)
    second = ingest_mod.ingest(second_url, tmp_path)

    assert first != second
    assert second.name == f"{first.stem}_1{first.suffix}"
    assert first.read_bytes() == b"first capture"
    assert second.read_bytes() == b"second capture"
    assert fetched == [first_url, second_url]
    assert set(tmp_path.iterdir()) == {first, second}


@pytest.mark.parametrize(
    ("entry_kind", "numbered"),
    [("file", False), ("file", True), ("dangling_link", False),
     ("dangling_link", True), ("live_link", True), ("directory", False), ("directory", True)],
)
def test_binary_captures_skip_existing_entries(entry_kind, numbered, tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    preferred = corpus / "example_org_report_pdf.pdf"
    occupied = preferred.with_name("example_org_report_pdf_1.pdf") if numbered else preferred
    sentinel = tmp_path / "sentinel"
    if numbered:
        preferred.write_bytes(b"retained base")
    if entry_kind == "file":
        occupied.write_bytes(b"retained file")
    elif entry_kind == "directory":
        occupied.mkdir()
    else:
        if entry_kind == "live_link":
            sentinel.write_bytes(b"outside sentinel")
        try:
            occupied.symlink_to(sentinel)
        except (OSError, NotImplementedError) as exc:
            pytest.skip(f"host cannot create symlinks: {exc}")

    monkeypatch.setattr(ingest_mod, "validate_url", lambda url: url)
    monkeypatch.setattr(ingest_mod, "safe_fetch", lambda url: b"new capture")
    result = ingest_mod.ingest("https://example.org/report.pdf", corpus)

    expected_number = 2 if numbered else 1
    assert result == corpus / f"example_org_report_pdf_{expected_number}.pdf"
    assert result.read_bytes() == b"new capture"
    if numbered:
        assert preferred.read_bytes() == b"retained base"
    if entry_kind == "file":
        assert occupied.read_bytes() == b"retained file"
    elif entry_kind == "directory":
        assert occupied.is_dir() and not list(occupied.iterdir())
    else:
        assert occupied.is_symlink() and occupied.readlink() == sentinel
        if entry_kind == "live_link":
            assert sentinel.read_bytes() == b"outside sentinel"
        else:
            assert not sentinel.exists()


@pytest.mark.parametrize("error_type", [PermissionError, OSError])
def test_binary_capture_inspection_error_precedes_fetch(error_type, tmp_path, monkeypatch):
    from pathlib import Path

    preferred = tmp_path / "example_org_report_pdf.pdf"
    original_lstat = Path.lstat
    inspected = []
    fetched = []

    def lstat(path, *args, **kwargs):
        if path == preferred:
            inspected.append(path)
            raise error_type("cannot inspect destination")
        return original_lstat(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(ingest_mod, "safe_fetch", lambda url: fetched.append(url) or b"new capture")
    with pytest.raises(error_type, match="cannot inspect destination"):
        ingest_mod._download_binary("https://example.org/report.pdf", ".pdf", tmp_path)
    assert inspected == [preferred]
    assert fetched == []
    assert not list(tmp_path.iterdir())


@pytest.mark.parametrize("suffix", [".pdf", ".png"])
def test_binary_capture_free_name_is_unchanged(suffix, tmp_path, monkeypatch):
    monkeypatch.setattr(ingest_mod, "validate_url", lambda url: url)
    monkeypatch.setattr(ingest_mod, "safe_fetch", lambda url: b"capture")
    result = ingest_mod.ingest(f"https://example.org/report{suffix}", tmp_path)
    assert result == tmp_path / f"example_org_report_{suffix[1:]}{suffix}"
    assert result.read_bytes() == b"capture"


def test_binary_capture_fetch_failure_preserves_existing_file(tmp_path, monkeypatch):
    retained = tmp_path / "example_org_report_pdf.pdf"
    retained.write_bytes(b"retained capture")

    def fail_fetch(url):
        raise OSError("download failed")

    monkeypatch.setattr(ingest_mod, "validate_url", lambda url: url)
    monkeypatch.setattr(ingest_mod, "safe_fetch", fail_fetch)
    with pytest.raises(RuntimeError, match="download failed"):
        ingest_mod.ingest("https://example.org/report.pdf", tmp_path)
    assert retained.read_bytes() == b"retained capture"
    assert list(tmp_path.iterdir()) == [retained]
