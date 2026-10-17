"""Tests for graphify.transcribe — video/audio transcription support."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from graphify.transcribe import (
    VIDEO_EXTENSIONS,
    build_whisper_prompt,
    transcribe,
    transcribe_all,
    update_detect_with_transcripts,
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


def _transcribe_fragment() -> str:
    return (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "skillgen"
        / "fragments"
        / "references"
        / "shared"
        / "transcribe.md"
    ).read_text(encoding="utf-8")


def test_transcribe_reference_does_not_require_first_build_analysis() -> None:
    fragment = _transcribe_fragment()

    assert ".graphify_detect.json` contains only a file inventory" in fragment
    assert "only when that file exists and belongs to this corpus" in fragment
    assert "On a first build, the analysis file has not been produced yet" in fragment
    assert "Never fabricate god-node labels" in fragment
    assert "Use proper punctuation and paragraph breaks." in fragment
    assert "Skip this step entirely if `detect` returned zero `video` files." in fragment


def test_transcribe_reference_updates_inventory_before_semantic_cache_check() -> None:
    fragment = _transcribe_fragment()
    core = (
        Path(__file__).resolve().parents[1]
        / "tools"
        / "skillgen"
        / "fragments"
        / "core"
        / "core.md"
    ).read_text(encoding="utf-8")

    assert "update_detect_with_transcripts(" in fragment
    assert "graphify-out/.graphify_detect.json" in fragment
    assert "This detection update must happen before Step B0" in fragment
    assert "do not run B0 with a stale or incomplete inventory" in fragment
    assert "all_files = [f for cat in ('document', 'paper', 'image')" in core


def test_transcripts_are_added_to_the_inventory_consumed_by_b0(tmp_path: Path) -> None:
    project = tmp_path / "project with spaces"
    output = project / "graphify-out"
    transcript_dir = output / "transcripts"
    transcript_dir.mkdir(parents=True)

    document = project / "meeting notes.md"
    paper = project / "paper.pdf"
    image = project / "diagram.png"
    video = project / "talk.mp4"
    stale_transcript = transcript_dir / "old talk.txt"
    for path in (document, paper, image, video, stale_transcript):
        path.write_text("fixture", encoding="utf-8")

    detect_path = output / ".graphify_detect.json"
    manifest_path = output / ".graphify_transcripts.json"
    detection = {
        "scan_root": str(project),
        "total_files": 4,
        "other_metadata": {"preserve": True},
        "files": {
            "document": [str(document), str(stale_transcript)],
            "paper": [str(paper)],
            "image": [str(image)],
            "video": [str(video)],
            "code": [],
        },
    }
    detect_path.write_text(json.dumps(detection), encoding="utf-8")
    manifest_path.write_text(json.dumps([str(stale_transcript)]), encoding="utf-8")

    first = transcript_dir / "successful talk.txt"
    second = transcript_dir / "interview with spaces.txt"
    outside = project / "outside.txt"
    first.write_text("first transcript", encoding="utf-8")
    second.write_text("second transcript", encoding="utf-8")
    outside.write_text("not a generated transcript", encoding="utf-8")
    missing = transcript_dir / "failed video.txt"

    recorded = update_detect_with_transcripts(
        detect_path,
        manifest_path,
        [str(first), str(missing), str(outside), str(second), str(first)],
        transcripts_dir=transcript_dir,
    )

    expected_transcripts = [str(first.resolve()), str(second.resolve())]
    updated = json.loads(detect_path.read_text(encoding="utf-8"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    semantic_inputs = [
        path
        for category in ("document", "paper", "image")
        for path in updated["files"].get(category, [])
    ]

    assert recorded == expected_transcripts
    assert manifest == expected_transcripts
    assert updated["files"]["document"] == [str(document), *expected_transcripts]
    assert str(stale_transcript) not in semantic_inputs
    assert all(path in semantic_inputs for path in expected_transcripts)
    assert updated["files"]["paper"] == [str(paper)]
    assert updated["files"]["image"] == [str(image)]
    assert updated["files"]["video"] == [str(video)]
    assert updated["other_metadata"] == {"preserve": True}
    assert updated["total_files"] == 4


def test_failed_transcription_clears_old_manifest_and_inventory_entries(tmp_path: Path) -> None:
    project = tmp_path / "project"
    output = project / "graphify-out"
    transcript_dir = output / "transcripts"
    transcript_dir.mkdir(parents=True)

    document = project / "notes.md"
    old_transcript = transcript_dir / "previous run.txt"
    document.write_text("notes", encoding="utf-8")
    old_transcript.write_text("old transcript", encoding="utf-8")

    detect_path = output / ".graphify_detect.json"
    manifest_path = output / ".graphify_transcripts.json"
    detect_path.write_text(
        json.dumps({
            "scan_root": str(project),
            "files": {"document": [str(document), str(old_transcript)]},
        }),
        encoding="utf-8",
    )
    manifest_path.write_text(json.dumps([str(old_transcript)]), encoding="utf-8")

    recorded = update_detect_with_transcripts(
        detect_path,
        manifest_path,
        [str(transcript_dir / "failed transcript.txt")],
        transcripts_dir=transcript_dir,
    )

    updated = json.loads(detect_path.read_text(encoding="utf-8"))
    assert recorded == []
    assert json.loads(manifest_path.read_text(encoding="utf-8")) == []
    assert updated["files"]["document"] == [str(document)]
