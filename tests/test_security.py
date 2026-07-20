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
