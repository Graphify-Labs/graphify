"""Tests for graphify/security.py - URL validation, safe fetch, path guards, label sanitisation."""
from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from graphify.security import (
    sanitize_label,
    sanitize_metadata,
    safe_fetch,
    safe_fetch_text,
    validate_store_path,
    validate_url,
    _MAX_FETCH_BYTES,
    _MAX_TEXT_BYTES,
    _METADATA_MAX_LIST_ITEMS,
    _METADATA_MAX_VALUE_LEN,
    _sanitize_metadata_string,
    _sanitize_metadata_value,
)


# ---------------------------------------------------------------------------
# validate_url
# ---------------------------------------------------------------------------

def test_validate_url_accepts_http():
    assert validate_url("http://example.com/page") == "http://example.com/page"

def test_validate_url_accepts_https():
    assert validate_url("https://arxiv.org/abs/1706.03762") == "https://arxiv.org/abs/1706.03762"

def test_validate_url_rejects_file():
    with pytest.raises(ValueError, match="file"):
        validate_url("file:///etc/passwd")

def test_validate_url_rejects_ftp():
    with pytest.raises(ValueError, match="ftp"):
        validate_url("ftp://files.example.com/data.zip")

def test_validate_url_rejects_data():
    with pytest.raises(ValueError, match="data"):
        validate_url("data:text/html,<script>alert(1)</script>")

def test_validate_url_rejects_empty_scheme():
    with pytest.raises(ValueError):
        validate_url("//no-scheme.example.com")


# ---------------------------------------------------------------------------
# safe_fetch - scheme and redirect guards (mocked network)
# ---------------------------------------------------------------------------

def _make_mock_response(content: bytes, status: int = 200):
    mock = MagicMock()
    mock.__enter__ = lambda s: s
    mock.__exit__ = MagicMock(return_value=False)
    mock.status = status
    mock.code = status
    chunks = [content[i:i+65536] for i in range(0, len(content), 65536)] + [b""]
    mock.read.side_effect = chunks
    return mock


def test_safe_fetch_rejects_file_url():
    with pytest.raises(ValueError, match="file"):
        safe_fetch("file:///etc/passwd")

def test_safe_fetch_rejects_ftp_url():
    with pytest.raises(ValueError, match="ftp"):
        safe_fetch("ftp://example.com/file.zip")

def test_safe_fetch_returns_bytes(tmp_path):
    mock_resp = _make_mock_response(b"hello world")
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        result = safe_fetch("https://example.com/")
    assert result == b"hello world"

def test_safe_fetch_raises_on_non_2xx():
    mock_resp = _make_mock_response(b"Not Found", status=404)
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        with pytest.raises(urllib.error.HTTPError):
            safe_fetch("https://example.com/missing")

def test_safe_fetch_raises_on_size_exceeded():
    # Build a response larger than max_bytes
    big_chunk = b"x" * 65_537
    mock_resp = MagicMock()
    mock_resp.__enter__ = lambda s: s
    mock_resp.__exit__ = MagicMock(return_value=False)
    mock_resp.status = 200
    mock_resp.code = 200
    # Return the chunk twice so total > max_bytes=65536
    mock_resp.read.side_effect = [big_chunk, big_chunk, b""]

    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        with pytest.raises(OSError, match="size limit"):
            safe_fetch("https://example.com/huge", max_bytes=65_536)


# ---------------------------------------------------------------------------
# safe_fetch_text
# ---------------------------------------------------------------------------

def test_safe_fetch_text_decodes_utf8():
    content = "héllo wörld".encode("utf-8")
    mock_resp = _make_mock_response(content)
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        result = safe_fetch_text("https://example.com/")
    assert result == "héllo wörld"

def test_safe_fetch_text_replaces_bad_bytes():
    bad = b"hello \xff world"
    mock_resp = _make_mock_response(bad)
    with patch("graphify.security._build_opener") as mock_opener_fn:
        mock_opener = MagicMock()
        mock_opener.open.return_value = mock_resp
        mock_opener_fn.return_value = mock_opener
        result = safe_fetch_text("https://example.com/")
    assert "hello" in result
    assert "world" in result
    assert "\xff" not in result


# ---------------------------------------------------------------------------
# validate_graph_path
# ---------------------------------------------------------------------------

def test_validate_graph_path_allows_inside_base(tmp_path):
    base = tmp_path / "graphify-out"
    base.mkdir()
    store = base / "graph.helix"
    store.mkdir()
    result = validate_store_path(str(store))
    assert result == store.resolve()

def test_validate_graph_path_blocks_traversal(tmp_path):
    base = tmp_path / "graphify-out"
    base.mkdir()
    legacy = tmp_path / "legacy.json"
    legacy.write_text("{}", encoding="utf-8")
    # Native stores may live outside graphify-out, but traversal must not turn a
    # legacy JSON path into an accepted store path after resolution.
    traversing_legacy = base / ".." / legacy.name
    with pytest.raises(ValueError, match="obsolete"):
        validate_store_path(str(traversing_legacy))

def test_validate_graph_path_requires_base_exists(tmp_path):
    base = tmp_path / "graphify-out"  # not created
    with pytest.raises(FileNotFoundError, match="Helix store not found"):
        validate_store_path(str(base / "graph.helix"))

def test_validate_graph_path_raises_if_file_missing(tmp_path):
    base = tmp_path / "graphify-out"
    base.mkdir()
    with pytest.raises(FileNotFoundError):
        validate_store_path(str(base / "missing.helix"))

def test_validate_graph_path_default_base_discovers_output_dir(tmp_path):
    """With base omitted, the output dir is discovered by walking the path's
    parents for the configured output-dir name (default 'graphify-out')."""
    base = tmp_path / "graphify-out"
    base.mkdir()
    store = base / "graph.helix"
    store.mkdir()
    assert validate_store_path(str(store)) == store.resolve()

def test_validate_graph_path_default_base_honours_graphify_out_override(tmp_path, monkeypatch):
    """The base=None discovery must honour GRAPHIFY_OUT, not the hardcoded
    'graphify-out' literal — otherwise a renamed output dir validates against the
    wrong base or raises spuriously (#1423)."""
    monkeypatch.setattr("graphify.security.GRAPHIFY_OUT_NAME", "custom-out")
    monkeypatch.setattr("graphify.security.GRAPHIFY_OUT", "custom-out")
    out = tmp_path / "custom-out"
    out.mkdir()
    graph = out / "graph.helix"
    graph.mkdir()
    # No base passed → must discover custom-out by name rather than graphify-out.
    assert validate_store_path(str(graph)) == graph.resolve()


# ---------------------------------------------------------------------------
# sanitize_label
# ---------------------------------------------------------------------------

def test_sanitize_label_passthrough_html_chars():
    # sanitize_label does NOT HTML-escape — callers that inject into HTML must
    # wrap with html.escape() themselves (e.g. the title in to_html())
    assert sanitize_label("<script>") == "<script>"
    assert sanitize_label("foo & bar") == "foo & bar"

def test_sanitize_label_strips_control_chars():
    result = sanitize_label("hello\x00\x1fworld")
    assert "\x00" not in result
    assert "\x1f" not in result
    assert "helloworld" in result

def test_sanitize_label_caps_at_256():
    long_label = "a" * 300
    assert len(sanitize_label(long_label)) <= 256

def test_sanitize_label_safe_passthrough():
    assert sanitize_label("MyClass") == "MyClass"
    assert sanitize_label("extract_python") == "extract_python"

def test_sanitize_label_none_returns_empty():
    # #1775: a node with source_file=None / label=None (synthetic/aggregate
    # nodes, or JSON `null`) must not raise — .get() returns None, not the
    # default, when the key is present-but-null.
    assert sanitize_label(None) == ""


# ---------------------------------------------------------------------------
# sanitize_metadata (recursive, bounded, HTML-safe)
# ---------------------------------------------------------------------------

def test_sanitize_metadata_string_strips_control_chars():
    result = _sanitize_metadata_string("hello\x00\x1fworld")
    assert "\x00" not in result
    assert "\x1f" not in result
    assert "helloworld" in result


def test_sanitize_metadata_string_escapes_html():
    result = _sanitize_metadata_string("<script>alert('x')</script>")
    assert "&lt;" in result
    assert "&gt;" in result
    assert "<script>" not in result


def test_sanitize_metadata_string_escapes_quotes():
    result = _sanitize_metadata_string('a"b\'c')
    # quote=True escapes both " and '
    assert "&quot;" in result
    assert "&#x27;" in result or "&apos;" in result


def test_sanitize_metadata_string_caps_length():
    long = "a" * (_METADATA_MAX_VALUE_LEN + 100)
    result = _sanitize_metadata_string(long)
    assert len(result) <= _METADATA_MAX_VALUE_LEN


def test_sanitize_metadata_string_coerces_non_string():
    # Non-str/dict/list/scalar inputs route through string sanitisation.
    class _Custom:
        def __str__(self) -> str:
            return "custom-repr"
    assert _sanitize_metadata_string(_Custom()) == "custom-repr"


def test_sanitize_metadata_value_preserves_simple_types():
    assert _sanitize_metadata_value(42) == 42
    assert _sanitize_metadata_value(3.14) == 3.14
    assert _sanitize_metadata_value(True) is True
    assert _sanitize_metadata_value(False) is False
    assert _sanitize_metadata_value(None) is None


def test_sanitize_metadata_value_recurses_into_dict():
    out = _sanitize_metadata_value({"k": "<script>x</script>"})
    assert isinstance(out, dict)
    assert "&lt;" in out["k"]


def test_sanitize_metadata_value_recurses_into_list():
    out = _sanitize_metadata_value(["<a>", "<b>", "<c>"])
    assert isinstance(out, list)
    assert all("&lt;" in s for s in out)


def test_sanitize_metadata_value_caps_list_length():
    huge = list(range(_METADATA_MAX_LIST_ITEMS * 3))
    out = _sanitize_metadata_value(huge)
    assert isinstance(out, list)
    assert len(out) == _METADATA_MAX_LIST_ITEMS


def test_sanitize_metadata_value_converts_tuple_to_list():
    out = _sanitize_metadata_value(("a", "b"))
    assert isinstance(out, list)
    assert out == ["a", "b"]


def test_sanitize_metadata_none_returns_empty_dict():
    assert sanitize_metadata(None) == {}


def test_sanitize_metadata_drops_empty_key():
    # Empty key (after control-char strip) is dropped.
    out = sanitize_metadata({"\x00": "v", "k": "v2"})
    assert "\x00" not in out
    assert out.get("k") == "v2"
    assert len(out) == 1


def test_sanitize_metadata_sanitizes_keys():
    out = sanitize_metadata({"<bad>": "v"})
    assert "<bad>" not in out
    assert any("&lt;" in k for k in out.keys())


def test_sanitize_metadata_recursive_nested():
    raw: dict[str, Any] = {
        "outer": {
            "inner": "<script>x</script>",
            "list": ["a", "<b>", 99, None, True],
        },
        "scalar": 42,
    }
    out = sanitize_metadata(raw)
    assert isinstance(out["outer"], dict)
    inner = out["outer"]
    assert isinstance(inner, dict)
    assert "&lt;" in inner["inner"]
    items = inner["list"]
    assert isinstance(items, list)
    assert items[0] == "a"
    assert "&lt;" in items[1]
    assert items[2] == 99
    assert items[3] is None
    assert items[4] is True
    assert out["scalar"] == 42


def test_sanitize_metadata_bool_not_coerced_to_int():
    # bool is an int subclass — order of isinstance checks must preserve bool.
    out = sanitize_metadata({"flag_t": True, "flag_f": False, "num": 1})
    assert out["flag_t"] is True
    assert out["flag_f"] is False
    assert out["num"] == 1

from unittest.mock import MagicMock, patch

import pytest

from graphify.security import sanitize_label, sanitize_metadata, safe_fetch, validate_store_path, validate_url


@pytest.mark.parametrize("url", ["file:///etc/passwd", "ftp://example.com/a", "data:text/plain,x"])
def test_url_rejects_non_http_schemes(url):
    with pytest.raises(ValueError):
        validate_url(url)


def test_safe_fetch_caps_streamed_response():
    response = MagicMock()
    response.__enter__ = lambda value: value
    response.__exit__ = MagicMock(return_value=False)
    response.status = 200
    response.read.side_effect = [b"x" * 9, b""]
    with patch("graphify.security.validate_url"), patch("graphify.security._build_opener") as factory:
        factory.return_value.open.return_value = response
        with pytest.raises(OSError, match="size limit"):
            safe_fetch("https://example.com", max_bytes=8)


def test_native_store_validation_and_legacy_rejection(tmp_path):
    store = tmp_path / "graph.helix"
    store.mkdir()
    assert validate_store_path(store) == store.resolve()
    legacy = tmp_path / "legacy.json"
    legacy.write_text("{}")
    with pytest.raises(ValueError, match="obsolete"):
        validate_store_path(legacy)
    with pytest.raises(FileNotFoundError):
        validate_store_path(tmp_path / "missing.helix")


def test_sanitizers_bound_untrusted_values():
    assert sanitize_label(None) == ""
    assert "\x00" not in sanitize_label("a\x00b")
    assert len(sanitize_label("x" * 1000)) <= 256
    cleaned = sanitize_metadata({"nested": {"value": "x" * 10000}})
    assert len(cleaned["nested"]["value"]) < 10000
