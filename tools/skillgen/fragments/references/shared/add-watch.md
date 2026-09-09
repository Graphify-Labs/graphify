# graphify reference: add a URL and watch a folder

Load this when the user ran `/graphify add <url>` or passed `--watch`. Neither is part of the default build.

## For /graphify add

Fetch a URL and add it to the corpus, then update the graph.

The URL and any author/contributor name are free text you do not control the
content of - do not build a command or inline script by substituting them
into a string; an embedded quote or shell character corrupts or escapes it.
Reserve a unique file path first - a fixed, shared filename risks a
concurrent graphify session overwriting or reading a stale payload:

```bash
mktemp /tmp/graphify_add_payload.XXXXXX.json
```

Using your file-write tool (not a shell heredoc, which has the same
quoting problem one level down), write a JSON file with those values to
the path that command printed, then pass only that path - not its content
- to `graphify add`:

```json
{"url": "URL", "author": "AUTHOR", "contributor": "CONTRIBUTOR", "dir": "./raw"}
```

Replace `URL` with the actual URL, `AUTHOR` with the user's name if
provided (omit the key entirely if not), `CONTRIBUTOR` likewise, then run:

```bash
$(cat graphify-out/.graphify_python) -m graphify add --from-file PAYLOAD_PATH
```

Replace `PAYLOAD_PATH` with the path `mktemp` printed. If the command exits with an error, tell the user what went wrong - do not
silently continue. After a successful save, automatically run the `--update`
pipeline on `./raw` to merge the new file into the existing graph.

Supported URL types (auto-detected):
- YouTube / any video URL → audio downloaded via yt-dlp, transcribed to `.txt` on next run (requires `pip install 'graphifyy[video]'`)
- Twitter/X → fetched via oEmbed, saved as `.md` with tweet text and author
- arXiv → abstract + metadata saved as `.md`
- PDF → downloaded as `.pdf`
- Images (.png/.jpg/.webp) → downloaded, Claude vision extracts on next run
- Any webpage → converted to markdown via html2text

---

## For --watch

Start a background watcher that monitors a folder and auto-updates the graph when files change.

```bash
$(cat graphify-out/.graphify_python) -m graphify.watch INPUT_PATH --debounce 3
```

Replace INPUT_PATH with the folder to watch. Behavior depends on what changed:

- **Code files only (.py, .ts, .go, etc.):** re-runs AST extraction + rebuild + cluster immediately, no LLM needed. `graph.json` and `GRAPH_REPORT.md` are updated automatically.
- **Docs, papers, or images:** writes a `graphify-out/needs_update` flag and prints a notification to run `/graphify --update` (LLM semantic re-extraction required).

Debounce (default 3s): waits until file activity stops before triggering, so a wave of parallel agent writes doesn't trigger a rebuild per file.

Press Ctrl+C to stop.

For agentic workflows: run `--watch` in a background terminal. Code changes from agent waves are picked up automatically between waves. If agents are also writing docs or notes, you'll need a manual `/graphify --update` after those waves.
