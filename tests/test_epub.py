"""Basic tests for the new EPUB semantic ingestion module."""

from pathlib import Path

import pytest

from graphify.epub import EpubLimits, convert_epub_file, EpubError


def test_epub_limits_default():
    limits = EpubLimits()
    assert limits.max_chapters > 0
    assert limits.max_raw_bytes > 0
    policy = limits.as_policy()
    assert "max_chapters" in policy


def test_epub_convert_nonexistent_raises():
    with pytest.raises((EpubError, FileNotFoundError)):
        convert_epub_file(Path("/nonexistent/test.epub"), Path("/tmp"))


def test_epub_module_has_expected_symbols():
    from graphify import epub
    assert hasattr(epub, "convert_epub_file")
    assert hasattr(epub, "EpubArtifacts")
    assert hasattr(epub, "EpubLimits")
