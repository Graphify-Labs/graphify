"""Tests for graphify.ingest."""

from __future__ import annotations
import json
import re
from pathlib import Path
import pytest
from graphify.ingest import (
    _detect_url_type,
    _fetch_tweet,
    _fetch_xquik_tweet,
    ingest,
    save_query_result,
)


TWEET_URL = "https://x.com/example/status/1893456789012345678"


def test_fetch_tweet_uses_xquik_when_configured(monkeypatch):
    requests = []

    def fake_fetch(url, max_bytes=10_485_760, timeout=15, headers=None):
        requests.append((url, headers))
        return json.dumps(
            {
                "tweet": {
                    "id": "1893456789012345678",
                    "text": "Complete post text from Xquik.",
                },
                "author": {"username": "example_user"},
            }
        )

    monkeypatch.setenv("XQUIK_API_KEY", "test-key")
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert r"Complete post text from Xquik\." in content
    assert r"# Tweet by @example\_user" in content
    assert requests == [
        (
            "https://xquik.com/api/v1/x/tweets/1893456789012345678",
            {"x-api-key": "test-key"},
        )
    ]


def test_fetch_tweet_falls_back_to_oembed(monkeypatch):
    requests = []

    def fake_fetch(url, max_bytes=10_485_760, timeout=15, headers=None):
        requests.append((url, headers))
        if url.startswith("https://xquik.com/"):
            return '{"tweet": {"id": "wrong"}, "author": {}}'
        return json.dumps(
            {
                "html": "<blockquote>Fallback text &amp; context</blockquote>",
                "author_name": "Example",
            }
        )

    monkeypatch.setenv("XQUIK_API_KEY", "test-key")
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert "Fallback text &amp; context" in content
    assert "test-key" not in content
    assert len(requests) == 2
    assert requests[1][1] is None


@pytest.mark.parametrize("error_type", [RuntimeError, LookupError])
def test_fetch_tweet_falls_back_when_xquik_fetch_fails(monkeypatch, error_type):
    def fake_fetch(url, max_bytes=10_485_760, timeout=15, headers=None):
        if url.startswith("https://xquik.com/"):
            raise error_type("request transport failed")
        return json.dumps(
            {
                "html": "<blockquote>Fallback text</blockquote>",
                "author_name": "Fallback Author",
            }
        )

    monkeypatch.setenv("XQUIK_API_KEY", "test-key")
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert "Fallback text" in content
    assert "# Tweet by @Fallback Author" in content


@pytest.mark.parametrize("error_type", [RuntimeError, LookupError])
def test_fetch_tweet_uses_stub_when_oembed_fetch_fails(monkeypatch, error_type):
    def fail_fetch(*args, **kwargs):
        raise error_type("request transport failed")

    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fail_fetch)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert "could not fetch content" in content


def test_fetch_tweet_uses_oembed_without_xquik_key(monkeypatch):
    requests = []

    def fake_fetch(url, max_bytes=10_485_760, timeout=15, headers=None):
        requests.append((url, headers))
        return json.dumps(
            {
                "html": "<blockquote>Public text &mdash; Example</blockquote>",
                "author_name": "Example",
            }
        )

    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert "Public text — Example" in content
    assert len(requests) == 1
    assert requests[0][0].startswith("https://publish.twitter.com/oembed?")


def test_fetch_xquik_tweet_rejects_wrong_post(monkeypatch):
    monkeypatch.setattr(
        "graphify.ingest.safe_fetch_text",
        lambda *args, **kwargs: (
            '{"tweet": {"id": "123", "text": "wrong"}, "author": {"username": "example_user"}}'
        ),
    )

    with pytest.raises(ValueError, match="wrong post"):
        _fetch_xquik_tweet(TWEET_URL, "test-key")


def test_detect_url_type_requires_an_exact_x_or_twitter_host():
    assert _detect_url_type(TWEET_URL) == "tweet"
    assert _detect_url_type("x.com/user/status/123") == "tweet"
    assert _detect_url_type("https://mobile.twitter.com/user/status/123") == "tweet"
    assert _detect_url_type("https://notx.com/user/status/123") == "webpage"
    assert _detect_url_type("https://example.com/x.com/user/status/123") == "webpage"


@pytest.mark.parametrize(
    "url",
    ["https://example.com/x.com/user/status/123", "https://x.com/example"],
)
def test_fetch_tweet_rejects_invalid_status_url_without_requesting_oembed(monkeypatch, url):
    requests = []
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    monkeypatch.setattr(
        "graphify.ingest.safe_fetch_text",
        lambda *args, **kwargs: requests.append((args, kwargs)),
    )

    with pytest.raises(ValueError):
        _fetch_tweet(url, None, None)

    assert requests == []


@pytest.mark.parametrize("provider", ["xquik", "oembed"])
def test_fetch_tweet_escapes_raw_html_from_provider_content(monkeypatch, provider):
    def fake_fetch(url, max_bytes=10_485_760, timeout=15, headers=None):
        if provider == "xquik":
            return json.dumps(
                {
                    "tweet": {
                        "id": "1893456789012345678",
                        "text": "<script>alert(1)</script> & context",
                    },
                    "author": {"username": "example_user"},
                }
            )
        return json.dumps(
            {
                "html": (
                    "<blockquote>&lt;script&gt;alert(1)&lt;/script&gt; "
                    "&amp; context</blockquote>"
                ),
                "author_name": "<b>Example</b>",
            }
        )

    if provider == "xquik":
        monkeypatch.setenv("XQUIK_API_KEY", "test-key")
    else:
        monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", fake_fetch)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert "<script>" not in content
    assert r"&lt;script&gt;alert\(1\)&lt;\/script&gt; &amp; context" in content
    if provider == "oembed":
        assert r"# Tweet by @&lt;b&gt;Example&lt;\/b&gt;" in content


@pytest.mark.parametrize("payload", ["[]", "{}", '{"html": 7}'])
def test_fetch_tweet_falls_back_when_oembed_json_has_wrong_shape(monkeypatch, payload):
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    monkeypatch.setattr("graphify.ingest.safe_fetch_text", lambda *args, **kwargs: payload)

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert "could not fetch content" in content


def test_fetch_tweet_escapes_markdown_links_and_images(monkeypatch):
    monkeypatch.setenv("XQUIK_API_KEY", "test-key")
    monkeypatch.setattr(
        "graphify.ingest.safe_fetch_text",
        lambda *args, **kwargs: json.dumps(
            {
                "tweet": {
                    "id": "1893456789012345678",
                    "text": "![proof](https://attacker.example/pixel) [run](javascript:alert(1))",
                },
                "author": {"username": "example_user"},
            }
        ),
    )

    content, _ = _fetch_tweet(TWEET_URL, None, None)

    assert r"\!\[proof\]\(https\:\/\/attacker\.example\/pixel\)" in content
    assert r"\[run\]\(javascript\:alert\(1\)\)" in content


def test_fetch_tweet_emits_safe_clickable_source_url(monkeypatch):
    url = f"{TWEET_URL}?note=<script>\n[unsafe]"
    monkeypatch.delenv("XQUIK_API_KEY", raising=False)
    monkeypatch.setattr(
        "graphify.ingest.safe_fetch_text",
        lambda *args, **kwargs: json.dumps(
            {"html": "<blockquote>Post text</blockquote>", "author_name": "Example"}
        ),
    )

    content, _ = _fetch_tweet(url, None, None)

    assert (
        "Source: <https://x.com/example/status/1893456789012345678"
        "?note=%3Cscript%3E%0A%5Bunsafe%5D>"
    ) in content


def test_ingest_wraps_malformed_url_validation_error(tmp_path):
    with pytest.raises(ValueError, match=r"^ingest:"):
        ingest("https://[::1", tmp_path)


def test_ingest_wraps_invalid_tweet_status_url(tmp_path):
    with pytest.raises(ValueError, match=r"^ingest:"):
        ingest("https://x.com/example", tmp_path)


def test_file_created(tmp_path):
    out = save_query_result("what is attention?", "Attention is...", tmp_path / "memory")
    assert out.exists()


def test_filename_format(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("what connects A to B?", "They share...", mem)
    assert out.name.startswith("query_")
    assert out.suffix == ".md"


def test_frontmatter_question(tmp_path):
    mem = tmp_path / "memory"
    question = "what is attention?"
    out = save_query_result(question, "Attention is softmax.", mem)
    content = out.read_text()
    assert "question:" in content
    assert "attention" in content.lower()


def test_frontmatter_type(tmp_path):
    mem = tmp_path / "memory"
    out = save_query_result("q", "a", mem, query_type="path_query")
    content = out.read_text()
    assert 'type: "path_query"' in content


def test_source_nodes_included(tmp_path):
    mem = tmp_path / "memory"
    nodes = ["AttentionLayer", "SoftmaxFunc"]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    assert "AttentionLayer" in content
    assert "SoftmaxFunc" in content


def test_source_nodes_capped_at_10(tmp_path):
    mem = tmp_path / "memory"
    nodes = [f"Node{i}" for i in range(20)]
    out = save_query_result("q", "a", mem, source_nodes=nodes)
    content = out.read_text()
    # Only first 10 should appear in frontmatter source_nodes line
    fm_line = [l for l in content.splitlines() if l.startswith("source_nodes:")][0]
    assert fm_line.count('"Node') == 10


def test_memory_dir_created(tmp_path):
    mem = tmp_path / "deep" / "memory"
    assert not mem.exists()
    save_query_result("q", "a", mem)
    assert mem.exists()


def test_answer_in_body(tmp_path):
    mem = tmp_path / "memory"
    answer = "The answer is forty-two."
    out = save_query_result("what is the answer?", answer, mem)
    content = out.read_text()
    assert answer in content

def test_outcome_in_frontmatter_and_body(tmp_path):
    """An outcome signal is written to both frontmatter (for `reflect`) and an
    ## Outcome body section (so it round-trips into the graph on re-extraction)."""
    out = save_query_result("q", "a", tmp_path / "memory", outcome="useful")
    content = out.read_text()
    assert 'outcome: "useful"' in content
    assert "## Outcome" in content
    assert "- Signal: useful" in content


def test_correction_in_frontmatter_and_body(tmp_path):
    out = save_query_result(
        "what hashes passwords?", "MD5", tmp_path / "memory",
        outcome="corrected", correction="It's bcrypt, see PasswordHasher",
    )
    content = out.read_text()
    assert 'correction: "It\'s bcrypt, see PasswordHasher"' in content
    assert "- Correction: It's bcrypt, see PasswordHasher" in content


def test_no_outcome_means_no_outcome_section(tmp_path):
    """Backward compatible: a result without an outcome looks exactly as before."""
    out = save_query_result("q", "a", tmp_path / "memory")
    content = out.read_text()
    assert "outcome:" not in content
    assert "## Outcome" not in content


def test_invalid_outcome_rejected(tmp_path):
    with pytest.raises(ValueError):
        save_query_result("q", "a", tmp_path / "memory", outcome="great")
