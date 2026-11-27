# graphify reference: add a URL and watch a folder

Load this when the user ran `/graphify add <url>` or passed `--watch`. Neither is part of the default build.

## For /graphify add

Fetch a URL and add it to the corpus, then update the graph.

```bash
$(cat graphify-out/.graphify_python) -c "
import sys
from graphify.ingest import ingest
from pathlib import Path

def _opt(name):
    p = Path('graphify-out') / name
    if not p.exists():
        return None
    return p.read_text(encoding='utf-8-sig').strip() or None

try:
    out = ingest(Path('graphify-out/.graphify_add_url').read_text(encoding='utf-8-sig').strip(),
        Path('./raw'), author=_opt('.graphify_add_author'),
        contributor=_opt('.graphify_add_contributor'))
    print(f'Saved to {out}')
except FileNotFoundError:
    print('error: graphify-out/.graphify_add_url was not written - write the URL to that file first', file=sys.stderr)
    sys.exit(1)
except ValueError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
except RuntimeError as e:
    print(f'error: {e}', file=sys.stderr)
    sys.exit(1)
finally:
    for _f in ('.graphify_add_url', '.graphify_add_author', '.graphify_add_contributor'):
        (Path('graphify-out') / _f).unlink(missing_ok=True)
"
```

Write the URL to `graphify-out/.graphify_add_url` before running the block — never paste it into the Python, since a URL containing a quote would break out of the literal. When the user gave a name, write it to `graphify-out/.graphify_add_author` or `graphify-out/.graphify_add_contributor`; a file that does not exist means the option was not given. If the command exits with an error, tell the user what went wrong - do not silently continue. After a successful save, automatically run the `--update` pipeline on `./raw` to merge the new file into the existing graph.

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
$(cat graphify-out/.graphify_python) -m graphify.watch "$(cat graphify-out/.graphify_root)" --debounce 3
```

This watches the same folder graphify extracted, read from the trusted `graphify-out/.graphify_root` that Step 1 resolved - there is no path to substitute, so a scan root containing shell metacharacters can never be re-interpreted here. Behavior depends on what changed:

- **Code files only (.py, .ts, .go, etc.):** re-runs AST extraction + rebuild + cluster immediately, no LLM needed. `graph.json` and `GRAPH_REPORT.md` are updated automatically.
- **Docs, papers, or images:** writes a `graphify-out/needs_update` flag and prints a notification to run `/graphify --update` (LLM semantic re-extraction required).

Debounce (default 3s): waits until file activity stops before triggering, so a wave of parallel agent writes doesn't trigger a rebuild per file.

Press Ctrl+C to stop.

For agentic workflows: run `--watch` in a background terminal. Code changes from agent waves are picked up automatically between waves. If agents are also writing docs or notes, you'll need a manual `/graphify --update` after those waves.
