# graphify reference: transcribe video and audio

Load this only when `detect` reported one or more `video` files. A corpus with no video never reads this.

### Step 2.5 - Transcribe video / audio files (only if video files detected)

Skip this step entirely if `detect` returned zero `video` files.

Video and audio files cannot be read directly. Transcribe them to text first, then include successful transcripts in the document inventory before Step B0 builds the semantic cache and extraction inputs.

**Strategy:** `graphify-out/.graphify_detect.json` contains only a file inventory; it has no god-node labels. Build a one-sentence domain hint only from context that is actually available, such as readable corpus documents or a README. You may use labels from the `gods` array in `graphify-out/.graphify_analysis.json` only when that file exists and belongs to this corpus. On a first build, the analysis file has not been produced yet; do not wait for it. Never fabricate god-node labels. If there is no reliable domain context, use the generic fallback prompt below. No separate API call is needed.

Use this generic fallback whenever there is no reliable domain context, including a first build with only video files: `"Use proper punctuation and paragraph breaks."`

**Step 1 - Write the Whisper prompt yourself.**

If genuine corpus context is available, compose a short domain hint sentence from it, for example:

- Labels: `transformer, attention, encoder, decoder` → `"Machine learning research on transformer architectures and attention mechanisms. Use proper punctuation and paragraph breaks."`
- Labels: `kubernetes, deployment, pod, helm` → `"DevOps discussion about Kubernetes deployments and Helm charts. Use proper punctuation and paragraph breaks."`

**Export** it as `GRAPHIFY_WHISPER_PROMPT` (the exact name the transcriber reads — and it must be `export`ed so the child Python process sees it) for the next command.

**Step 2 - Transcribe:**

```bash
export GRAPHIFY_WHISPER_MODEL=base  # or whatever --whisper-model the user passed (must be exported)
export GRAPHIFY_WHISPER_PROMPT="<the one-sentence domain hint you composed in Step 1>"
$(cat graphify-out/.graphify_python) -c "
import json, os, sys
from pathlib import Path
from graphify.transcribe import transcribe_all, update_detect_with_transcripts

detect = json.loads(Path('graphify-out/.graphify_detect.json').read_text(encoding=\"utf-8\"))
video_files = detect.get('files', {}).get('video', [])
prompt = os.environ.get('GRAPHIFY_WHISPER_PROMPT', 'Use proper punctuation and paragraph breaks.')

transcript_paths = transcribe_all(video_files, initial_prompt=prompt)
transcript_paths = update_detect_with_transcripts(
    Path('graphify-out/.graphify_detect.json'),
    Path('graphify-out/.graphify_transcripts.json'),
    transcript_paths,
)
print(f'Transcribed {len(transcript_paths)} file(s)', file=sys.stderr)
"
```

After transcription:
- `update_detect_with_transcripts()` replaces `graphify-out/.graphify_transcripts.json` with this run's successful transcript paths and adds those paths to `files.document` in `graphify-out/.graphify_detect.json`.
- This detection update must happen before Step B0. B0 rereads `files.document`, `files.paper`, and `files.image` to build the semantic cache and extraction input list; keeping transcript paths only in memory or adding them after B0 would omit them.
- If either sidecar cannot be updated, stop and report the error; do not run B0 with a stale or incomplete inventory.
- Print how many transcripts were created: `Transcribed N video file(s) -> treating as docs`
- `transcribe_all()` warns and continues when an individual file fails. Nonexistent or invalid transcript paths are excluded, and a failed file is never added to the B0 inventory.

**Whisper model:** Default is `base`. If the user passed `--whisper-model <name>`, `export GRAPHIFY_WHISPER_MODEL=<name>` (it must be exported, not just assigned) before running the command above.
