# graphify reference: transcribe video and audio

Load this only when `detect` reported one or more `video` files. A corpus with no video never reads this.

### Step 2.5 - Transcribe video / audio files (only if video files detected)

Skip this step entirely if `detect` returned zero `video` files.

Video and audio files cannot be read directly. Transcribe them to text first, then treat the transcripts as doc files in Step 3.

**Strategy:** Read the god nodes from `graphify-out/.graphify_detect.json` (or the analysis file if it exists from a previous run). You are already a language model — write a one-sentence domain hint yourself from those labels. Then pass it to Whisper as the initial prompt. No separate API call needed.

**However**, if the corpus has *only* video files and no other docs/code, use the generic fallback prompt: `"Use proper punctuation and paragraph breaks."`

**Step 1 - Write the Whisper prompt yourself.**

Read the top god node labels from detect output or analysis, then compose a short domain hint sentence, for example:

- Labels: `transformer, attention, encoder, decoder` → `"Machine learning research on transformer architectures and attention mechanisms. Use proper punctuation and paragraph breaks."`
- Labels: `kubernetes, deployment, pod, helm` → `"DevOps discussion about Kubernetes deployments and Helm charts. Use proper punctuation and paragraph breaks."`

**Export** it as `GRAPHIFY_WHISPER_PROMPT` (the exact name the transcriber reads — and it must be `export`ed so the child Python process sees it) for the next command.

**Step 2 - Transcribe:**

Transcripts are content/model/prompt-addressed under `graphify-out/transcripts/`. Changing media bytes, `--whisper-model`, or the Whisper prompt automatically selects a new path. Pass `force=True` only when the user explicitly asked to re-transcribe despite an identical cache key. Requires Python 3.11+ with `graphifyy[video]` (faster-whisper).

```bash
export GRAPHIFY_WHISPER_MODEL=base  # or whatever --whisper-model the user passed (must be exported)
export GRAPHIFY_WHISPER_PROMPT="<the one-sentence domain hint you composed in Step 1>"
$(cat graphify-out/.graphify_python) -c "
import json, os, sys
from pathlib import Path
from graphify.transcribe import transcribe_all

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding=\"utf-8\"))
video_files = detect.get('files', {}).get('video', [])
prompt = os.environ.get('GRAPHIFY_WHISPER_PROMPT', 'Use proper punctuation and paragraph breaks.')
force = os.environ.get('GRAPHIFY_FORCE', '').lower() in {'1', 'true', 'yes'}
out_dir = Path('graphify-out') / 'transcripts'

transcript_paths = transcribe_all(
    video_files,
    output_dir=out_dir,
    initial_prompt=prompt,
    force=force,
)
# Persist Path objects as strings. Write JSON from Python (NOT a shell '>' redirect):
# transcribe_all/Whisper print progress to stdout, which would otherwise corrupt
# the JSON file (#1392).
Path('graphify-out/.graphify_transcripts.json').write_text(
    json.dumps([str(p) for p in transcript_paths], ensure_ascii=False),
    encoding=\"utf-8\",
)
print(f'Transcribed {len(transcript_paths)} file(s)', file=sys.stderr)
if len(transcript_paths) < len(video_files):
    print(
        f'warning: {len(video_files) - len(transcript_paths)} media file(s) failed transcription',
        file=sys.stderr,
    )
"
```

After transcription:
- Read the transcript paths from `graphify-out/.graphify_transcripts.json`
- Add them to the docs list before dispatching semantic subagents in Step 3B
- Print how many transcripts were created: `Transcribed N video file(s) -> treating as docs`
- If transcription fails for a file, print a warning and continue with the rest — do not treat the source media as successfully processed until its transcript is present

**Whisper model:** Default is `base`. If the user passed `--whisper-model <name>`, `export GRAPHIFY_WHISPER_MODEL=<name>` (it must be exported, not just assigned) before running the command above. If the user passed `--force`, also `export GRAPHIFY_FORCE=1`.
