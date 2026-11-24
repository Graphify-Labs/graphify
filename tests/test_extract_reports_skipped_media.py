"""#5076: headless `extract` silently omitted audio/video files returned by
`detect()` (bucketed under the "video" file-type key). A media-only corpus
produced an empty graph and exited 0 with no indication anything had been
found and skipped, unlike every other skip path in this command (--code-only,
GRAPHIFY_BACKEND=none, unclassified files, sensitive files), which all report
what they drop.
"""
from __future__ import annotations

import os
import subprocess
import sys
import wave
from pathlib import Path

PYTHON = sys.executable
_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def _write_silence_wav(path: Path) -> None:
    with wave.open(str(path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(16000)
        f.writeframes(b"\0\0" * 16000)


def _run(repo: Path, *extra: str):
    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    env["GRAPHIFY_BACKEND"] = "none"
    return subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", *extra],
        cwd=repo, capture_output=True, text=True, env=env,
    )


def test_media_only_corpus_reports_skipped_audio_file(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _write_silence_wav(repo / "silence.wav")

    r = _run(repo, "--no-cluster")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "found 0 code, 0 docs, 0 papers, 0 images" in out
    assert "1 audio/video file(s) detected but not extracted" in out, (
        "a detected but unextracted audio file must be reported, not silently "
        f"dropped (#5076); got: {out}"
    )


def test_mixed_repo_reports_media_alongside_code(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")
    _write_silence_wav(repo / "clip.wav")
    _write_silence_wav(repo / "clip2.mp3")

    r = _run(repo, "--code-only", "--no-cluster")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "2 audio/video file(s) detected but not extracted" in out
    graph = repo / "graphify-out" / "graph.json"
    assert graph.exists()


def test_no_media_prints_no_media_notice(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def hello():\n    return 1\n")

    r = _run(repo, "--code-only", "--no-cluster")
    assert r.returncode == 0, r.stderr
    out = r.stdout + r.stderr
    assert "audio/video file(s) detected" not in out
