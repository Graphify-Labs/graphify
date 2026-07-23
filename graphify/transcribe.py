# Video transcription using faster-whisper
# Converts video/audio files to text transcripts for graph extraction
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from pathlib import Path

from graphify.paths import out_path as _out_path


VIDEO_EXTENSIONS = {'.mp4', '.mov', '.webm', '.mkv', '.avi', '.m4v', '.mp3', '.wav', '.m4a', '.ogg'}
URL_PREFIXES = ('http://', 'https://', 'www.')

_DEFAULT_MODEL = "base"
_TRANSCRIPTS_DIR = str(_out_path("transcripts"))
_FALLBACK_PROMPT = "Use proper punctuation and paragraph breaks."
_TRANSCRIPTION_OPTIONS = {
    "beam_size": 5,
    "compute_type": "int8",
    "device": "cpu",
    "schema": 1,
}


def _model_name() -> str:
    return os.environ.get("GRAPHIFY_WHISPER_MODEL", _DEFAULT_MODEL)


def _get_whisper():
    try:
        from faster_whisper import WhisperModel
        return WhisperModel
    except ImportError as exc:
        raise ImportError(
            "Video transcription requires faster-whisper "
            "(Python 3.11+; graphifyy[video] installs it only on 3.11+). "
            "Run: pip install 'graphifyy[video]' on Python 3.11 or newer"
        ) from exc


def _get_yt_dlp():
    try:
        import yt_dlp
        return yt_dlp
    except ImportError as exc:
        raise ImportError(
            "YouTube/URL download requires yt-dlp. "
            "Run: pip install 'graphifyy[video]'"
        ) from exc


def is_url(path: str) -> bool:
    """Return True if the string looks like a URL rather than a file path."""
    return any(path.startswith(p) for p in URL_PREFIXES)


def download_audio(url: str, output_dir: Path) -> Path:
    """Download audio-only stream from a URL using yt-dlp.

    Returns the path to the downloaded audio file (.m4a or .opus).
    Uses cached file if already downloaded.
    """
    from graphify.security import validate_url
    validate_url(url)  # blocks private IPs, bad schemes before yt-dlp runs
    yt_dlp = _get_yt_dlp()
    output_dir.mkdir(parents=True, exist_ok=True)

    # yt-dlp uses %(title)s which can be long/weird — use a stable name based on URL hash
    import hashlib
    url_hash = hashlib.sha1(url.encode(), usedforsecurity=False).hexdigest()[:12]
    out_template = str(output_dir / f"yt_{url_hash}.%(ext)s")

    # Check for already-downloaded file
    for ext in ('.m4a', '.opus', '.mp3', '.ogg', '.wav', '.webm'):
        candidate = output_dir / f"yt_{url_hash}{ext}"
        if candidate.exists():
            print(f"  cached audio: {candidate.name}")
            return candidate

    ydl_opts = {
        'format': 'bestaudio[ext=m4a]/bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'noplaylist': True,
        'postprocessors': [],  # no ffmpeg needed — use native audio
    }

    print(f"  downloading audio: {url[:80]} ...", flush=True)
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        ext = info.get('ext', 'm4a')
        downloaded = output_dir / f"yt_{url_hash}.{ext}"
        if not downloaded.exists():
            # yt-dlp may have picked a different extension
            for p in output_dir.glob(f"yt_{url_hash}.*"):
                downloaded = p
                break
        return downloaded


def build_whisper_prompt(god_nodes: list[dict]) -> str:
    """Build a domain hint for Whisper from god nodes extracted from the corpus.

    Formats the top god node labels into a topic string for Whisper.
    The coding agent (Claude Code, Codex, etc.) generates the actual one-sentence
    domain hint from these labels and passes it via GRAPHIFY_WHISPER_PROMPT or
    as initial_prompt — no separate API call needed here.
    """
    override = os.environ.get("GRAPHIFY_WHISPER_PROMPT")
    if override:
        return override

    if not god_nodes:
        return _FALLBACK_PROMPT

    labels = [n.get("label", "") for n in god_nodes[:10] if n.get("label")]
    if not labels:
        return _FALLBACK_PROMPT

    topics = ", ".join(labels[:5])
    return f"Technical discussion about {topics}. Use proper punctuation and paragraph breaks."


def _effective_prompt(initial_prompt: str | None) -> str:
    return initial_prompt or os.environ.get("GRAPHIFY_WHISPER_PROMPT") or _FALLBACK_PROMPT


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def transcript_path_for(
    video_path: Path | str,
    output_dir: Path | None = None,
    initial_prompt: str | None = None,
    *,
    media_path: Path | None = None,
) -> Path:
    """Return the content/config-addressed transcript path for a media source."""
    out_dir = Path(output_dir) if output_dir else Path(_TRANSCRIPTS_DIR)
    source = str(video_path)
    if is_url(source):
        source_identity = source
        content_sha256 = _sha256_file(media_path) if media_path is not None else hashlib.sha256(
            source.encode("utf-8")
        ).hexdigest()
        stem_source = media_path.stem if media_path is not None else "remote-media"
    else:
        local = Path(video_path)
        source_identity = local.resolve().as_posix()
        content_sha256 = _sha256_file(local)
        stem_source = local.stem
    cache_key = {
        "content_sha256": content_sha256,
        "model": _model_name(),
        "options": _TRANSCRIPTION_OPTIONS,
        "prompt": _effective_prompt(initial_prompt),
        "source": unicodedata.normalize("NFC", source_identity),
    }
    digest = hashlib.sha256(
        json.dumps(cache_key, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()[:16]
    stem = re.sub(
        r"[^A-Za-z0-9._-]+", "_", unicodedata.normalize("NFC", stem_source)
    ).strip("._-")
    return out_dir / f"{(stem[:80] or 'media')}-{digest}.txt"


def transcribe(
    video_path: Path | str,
    output_dir: Path | None = None,
    initial_prompt: str | None = None,
    force: bool = False,
) -> Path:
    """Transcribe a video/audio file or URL to a .txt transcript.

    If video_path is a URL, audio is downloaded first via yt-dlp.
    Returns the path to the saved transcript file.
    Uses cached transcript if it exists unless force=True.

    initial_prompt: domain hint for Whisper (built from corpus god nodes).
    force: re-transcribe even if transcript already exists.
    """
    out_dir = Path(output_dir) if output_dir else Path(_TRANSCRIPTS_DIR)
    out_dir.mkdir(parents=True, exist_ok=True)

    if is_url(str(video_path)):
        audio_path = download_audio(str(video_path), out_dir / "downloads")
    else:
        audio_path = Path(video_path)

    prompt = _effective_prompt(initial_prompt)
    transcript_path = transcript_path_for(
        video_path,
        out_dir,
        initial_prompt=prompt,
        media_path=audio_path,
    )
    if transcript_path.exists() and not force:
        return transcript_path

    WhisperModel = _get_whisper()
    model_name = _model_name()

    print(f"  transcribing {audio_path.name} (model={model_name}) ...", flush=True)
    model = WhisperModel(
        model_name,
        device=_TRANSCRIPTION_OPTIONS["device"],
        compute_type=_TRANSCRIPTION_OPTIONS["compute_type"],
    )
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=_TRANSCRIPTION_OPTIONS["beam_size"],
        initial_prompt=prompt,
    )

    lines = [segment.text.strip() for segment in segments if segment.text.strip()]
    transcript = "\n".join(lines)

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=out_dir,
        prefix=f".{transcript_path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(transcript)
        temporary = Path(handle.name)
    try:
        os.replace(temporary, transcript_path)
    finally:
        temporary.unlink(missing_ok=True)
    lang = info.language if hasattr(info, "language") else "unknown"
    print(f"  transcript saved -> {transcript_path} (lang={lang}, {len(lines)} segments)")
    return transcript_path


def transcribe_all(
    video_files: list[Path | str],
    output_dir: Path | None = None,
    initial_prompt: str | None = None,
    force: bool = False,
) -> list[Path]:
    """Transcribe a list of video/audio files or URLs, return paths to transcript .txt files.

    Already-transcribed files are returned from cache instantly.
    initial_prompt is shared across all files — built once from corpus god nodes.
    """
    if not video_files:
        return []

    transcript_paths = []
    for vf in video_files:
        try:
            t = transcribe(vf, output_dir, initial_prompt=initial_prompt, force=force)
            transcript_paths.append(t)
        except Exception as exc:
            print(f"  warning: could not transcribe {vf}: {exc}")
    return transcript_paths
