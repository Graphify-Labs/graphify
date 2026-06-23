"""Tests for graphify.transcribe — video/audio transcription support."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graphify.transcribe import (
    VIDEO_EXTENSIONS,
    build_whisper_prompt,
    transcribe,
    transcribe_all,
)


# ---------------------------------------------------------------------------
# VIDEO_EXTENSIONS
# ---------------------------------------------------------------------------

def test_video_extensions_set():
    assert ".mp4" in VIDEO_EXTENSIONS
    assert ".mp3" in VIDEO_EXTENSIONS
    assert ".wav" in VIDEO_EXTENSIONS
    assert ".mov" in VIDEO_EXTENSIONS
    assert ".py" not in VIDEO_EXTENSIONS


# ---------------------------------------------------------------------------
# build_whisper_prompt
# ---------------------------------------------------------------------------

def test_build_whisper_prompt_no_nodes():
    """Empty god_nodes returns fallback prompt."""
    prompt = build_whisper_prompt([])
    assert "punctuation" in prompt.lower() or len(prompt) > 0


def test_build_whisper_prompt_env_override(monkeypatch):
    """GRAPHIFY_WHISPER_PROMPT env var short-circuits LLM call."""
    monkeypatch.setenv("GRAPHIFY_WHISPER_PROMPT", "Custom domain hint.")
    prompt = build_whisper_prompt([{"label": "Python"}, {"label": "FastAPI"}])
    assert prompt == "Custom domain hint."


def test_build_whisper_prompt_returns_topic_string():
    """Returns a topic-based prompt from god node labels — no LLM call."""
    god_nodes = [{"label": "neural networks"}, {"label": "transformers"}, {"label": "attention"}]
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("GRAPHIFY_WHISPER_PROMPT", None)
        prompt = build_whisper_prompt(god_nodes)
    assert "neural networks" in prompt.lower() or "transformers" in prompt.lower()
    assert "punctuation" in prompt.lower()


def test_build_whisper_prompt_nodes_without_labels():
    """Nodes missing 'label' keys are safely skipped."""
    god_nodes = [{"id": "1"}, {"id": "2", "label": ""}]
    prompt = build_whisper_prompt(god_nodes)
    assert len(prompt) > 0


# ---------------------------------------------------------------------------
# download_audio — resource/SSRF hardening
# ---------------------------------------------------------------------------

class _FakeYDL:
    """Context-manager stand-in for yt_dlp.YoutubeDL that captures its opts."""
    captured: dict = {}

    def __init__(self, opts):
        type(self).captured = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download):
        return {"ext": "m4a"}


def _patch_ytdlp(monkeypatch):
    fake_mod = MagicMock()
    fake_mod.YoutubeDL = _FakeYDL
    monkeypatch.setattr("graphify.transcribe._get_yt_dlp", lambda: fake_mod)
    # validate_url is imported inside download_audio from graphify.security
    monkeypatch.setattr("graphify.security.validate_url", lambda url: None)


def test_download_audio_caps_file_size(tmp_path, monkeypatch):
    """download_audio must pass a positive max_filesize cap to yt-dlp.

    Without a cap, a malicious or oversized media URL can exhaust disk/bandwidth
    even though validate_url() rejects private-IP/bad-scheme initial URLs.
    """
    from graphify.transcribe import download_audio
    _patch_ytdlp(monkeypatch)
    download_audio("https://example.com/video", tmp_path)
    opts = _FakeYDL.captured
    assert "max_filesize" in opts, "ydl_opts must set max_filesize"
    assert isinstance(opts["max_filesize"], int) and opts["max_filesize"] > 0
    assert opts.get("noplaylist") is True


def test_download_audio_max_filesize_env_override(tmp_path, monkeypatch):
    """GRAPHIFY_YTDLP_MAX_FILESIZE overrides the default cap."""
    from graphify.transcribe import download_audio
    _patch_ytdlp(monkeypatch)
    monkeypatch.setenv("GRAPHIFY_YTDLP_MAX_FILESIZE", "12345")
    download_audio("https://example.com/video", tmp_path)
    assert _FakeYDL.captured["max_filesize"] == 12345


# ---------------------------------------------------------------------------
# transcribe
# ---------------------------------------------------------------------------

def test_transcribe_uses_cache(tmp_path):
    """If transcript already exists, transcribe() returns cached path without running Whisper."""
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    cached = out_dir / "lecture.txt"
    cached.write_text("Cached transcript content.")

    result = transcribe(video, output_dir=out_dir)
    assert result == cached


def test_transcribe_force_reruns(tmp_path):
    """force=True re-transcribes even when cache exists."""
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    (out_dir / "talk.txt").write_text("Old transcript.")

    fake_segment = MagicMock()
    fake_segment.text = "New transcript segment."
    fake_info = MagicMock()
    fake_info.language = "en"

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], fake_info)

    with patch("graphify.transcribe._get_whisper", return_value=lambda *a, **kw: fake_model):
        result = transcribe(video, output_dir=out_dir, force=True)

    assert result.read_text() == "New transcript segment."


def test_transcribe_missing_faster_whisper(tmp_path):
    """ImportError propagates when faster_whisper is not installed."""
    video = tmp_path / "clip.mp4"
    video.write_bytes(b"fake")

    with patch("graphify.transcribe._get_whisper", side_effect=ImportError("faster-whisper not installed")):
        with pytest.raises(ImportError):
            transcribe(video, output_dir=tmp_path / "out")


# ---------------------------------------------------------------------------
# transcribe_all
# ---------------------------------------------------------------------------

def test_transcribe_all_empty():
    """Empty input returns empty list without error."""
    assert transcribe_all([]) == []


def test_transcribe_all_uses_cache(tmp_path):
    """transcribe_all() returns cached paths for already-transcribed files."""
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    cached = out_dir / "lecture.txt"
    cached.write_text("Cached.")

    results = transcribe_all([str(video)], output_dir=out_dir)
    assert len(results) == 1
    assert str(cached) in results[0]


def test_transcribe_all_skips_failed(tmp_path):
    """transcribe_all() warns and skips files that fail to transcribe."""
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"fake")

    def raise_import(*args, **kwargs):
        raise ImportError("faster_whisper not installed")

    with patch("graphify.transcribe.transcribe", side_effect=RuntimeError("boom")):
        results = transcribe_all([str(video)], output_dir=tmp_path / "out")

    assert results == []
