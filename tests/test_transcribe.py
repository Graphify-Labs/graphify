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
    transcript_path_for,
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


def test_build_whisper_prompt_env_override_without_nodes(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_WHISPER_PROMPT", "Custom domain hint.")
    assert build_whisper_prompt([]) == "Custom domain hint."


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
# transcribe
# ---------------------------------------------------------------------------

def test_transcribe_uses_cache(tmp_path):
    """If transcript already exists, transcribe() returns cached path without running Whisper."""
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    cached = transcript_path_for(video, output_dir=out_dir)
    cached.write_text("Cached transcript content.")

    result = transcribe(video, output_dir=out_dir)
    assert result == cached


def test_transcribe_force_reruns(tmp_path):
    """force=True re-transcribes even when cache exists."""
    video = tmp_path / "talk.mp4"
    video.write_bytes(b"fake")
    out_dir = tmp_path / "transcripts"
    out_dir.mkdir()
    transcript_path_for(video, output_dir=out_dir).write_text("Old transcript.")

    fake_segment = MagicMock()
    fake_segment.text = "New transcript segment."
    fake_info = MagicMock()
    fake_info.language = "en"

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([fake_segment], fake_info)

    with patch("graphify.transcribe._get_whisper", return_value=lambda *a, **kw: fake_model):
        result = transcribe(video, output_dir=out_dir, force=True)

    assert result.read_text() == "New transcript segment."


def test_transcript_cache_key_separates_same_basename_paths(tmp_path):
    first = tmp_path / "one" / "lecture.mp4"
    second = tmp_path / "two" / "lecture.mp4"
    first.parent.mkdir()
    second.parent.mkdir()
    first.write_bytes(b"same payload")
    second.write_bytes(b"same payload")

    assert transcript_path_for(first, tmp_path / "out") != transcript_path_for(
        second, tmp_path / "out"
    )


def test_transcript_cache_key_tracks_content_with_same_mtime(tmp_path):
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"first payload")
    original_times = (video.stat().st_atime, video.stat().st_mtime)
    first = transcript_path_for(video, tmp_path / "out")
    video.write_bytes(b"second payload")
    os.utime(video, original_times)

    assert transcript_path_for(video, tmp_path / "out") != first


def test_transcript_cache_key_tracks_model_and_prompt(monkeypatch, tmp_path):
    video = tmp_path / "lecture.mp4"
    video.write_bytes(b"payload")
    monkeypatch.setenv("GRAPHIFY_WHISPER_MODEL", "base")
    base = transcript_path_for(video, tmp_path / "out", initial_prompt="finance")
    monkeypatch.setenv("GRAPHIFY_WHISPER_MODEL", "medium")
    medium = transcript_path_for(video, tmp_path / "out", initial_prompt="finance")
    other_prompt = transcript_path_for(video, tmp_path / "out", initial_prompt="medicine")

    assert len({base, medium, other_prompt}) == 3


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
    cached = transcript_path_for(video, output_dir=out_dir)
    cached.write_text("Cached.")

    results = transcribe_all([str(video)], output_dir=out_dir)
    assert len(results) == 1
    assert cached in results


def test_transcribe_all_skips_failed(tmp_path):
    """transcribe_all() warns and skips files that fail to transcribe."""
    video = tmp_path / "broken.mp4"
    video.write_bytes(b"fake")

    def raise_import(*args, **kwargs):
        raise ImportError("faster_whisper not installed")

    with patch("graphify.transcribe.transcribe", side_effect=RuntimeError("boom")):
        results = transcribe_all([str(video)], output_dir=tmp_path / "out")

    assert results == []


def test_transcribe_all_propagates_force(tmp_path):
    video = tmp_path / "force.mp4"
    video.write_bytes(b"fake")
    transcript = tmp_path / "force-keyed.txt"
    with patch("graphify.transcribe.transcribe", return_value=transcript) as mocked:
        assert transcribe_all([video], output_dir=tmp_path, force=True) == [transcript]
    mocked.assert_called_once_with(video, tmp_path, initial_prompt=None, force=True)
