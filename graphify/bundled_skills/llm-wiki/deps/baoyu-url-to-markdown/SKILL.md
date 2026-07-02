---
name: baoyu-url-to-markdown
description: Fetch any URL and convert to markdown using Chrome CDP. Saves the rendered HTML snapshot alongside the markdown, uses an upgraded Defuddle pipeline with better web-component handling and YouTube transcript extraction, and automatically falls back to the pre-Defuddle HTML-to-Markdown pipeline when needed. If local browser capture fails entirely, it can fall back to the hosted defuddle.md API. Supports two modes - auto-capture on page load, or wait for user signal (for pages requiring login). Use when user wants to save a webpage as markdown.
version: 1.58.1
metadata:
  openclaw:
    homepage: https://github.com/JimLiu/baoyu-skills#baoyu-url-to-markdown
    requires:
      anyBins:
        - bun
        - npx
---

# URL to Markdown

Fetches any URL via Chrome CDP, saves the rendered HTML snapshot, and converts it to clean markdown.

## Script Directory

**Important**: All scripts are located in the `scripts/` subdirectory of this skill.

**Agent Execution Instructions**:
1. Determine this SKILL.md file's directory path as `{baseDir}`
2. Script path = `{baseDir}/scripts/<script-name>.ts`
3. Resolve `${BUN_X}` runtime: if `bun` installed → `bun`; if `npx` available → `npx -y bun`; else suggest installing bun
4. Replace all `{baseDir}` and `${BUN_X}` in this document with actual values

**Script Reference**:
| Script | Purpose |
|--------|---------|
| `scripts/main.ts` | CLI entry point for URL fetching |
| `scripts/html-to-markdown.ts` | Markdown conversion entry point and converter selection |
| `scripts/defuddle-converter.ts` | Defuddle-based conversion |
| `scripts/legacy-converter.ts` | Pre-Defuddle legacy extraction and markdown conversion |
| `scripts/markdown-conversion-shared.ts` | Shared metadata parsing and markdown document helpers |

## Preferences (EXTEND.md)

Check EXTEND.md existence (priority order):

```bash
# macOS, Linux, WSL, Git Bash
test -f .baoyu-skills/baoyu-url-to-markdown/EXTEND.md && echo "project"
test -f "${XDG_CONFIG_HOME:-$HOME/.config}/baoyu-skills/baoyu-url-to-markdown/EXTEND.md" && echo "xdg"
test -f "$HOME/.baoyu-skills/baoyu-url-to-markdown/EXTEND.md" && echo "user"
```

```powershell
# PowerShell (Windows)
if (Test-Path .baoyu-skills/baoyu-url-to-markdown/EXTEND.md) { "project" }
$xdg = if ($env:XDG_CONFIG_HOME) { $env:XDG_CONFIG_HOME } else { "$HOME/.config" }
if (Test-Path "$xdg/baoyu-skills/baoyu-url-to-markdown/EXTEND.md") { "xdg" }
if (Test-Path "$HOME/.baoyu-skills/baoyu-url-to-markdown/EXTEND.md") { "user" }
```

┌────────────────────────────────────────────────────────┬───────────────────┐
│                          Path                          │     Location      │
├────────────────────────────────────────────────────────┼───────────────────┤
│ .baoyu-skills/baoyu-url-to-markdown/EXTEND.md          │ Project directory │
├────────────────────────────────────────────────────────┼───────────────────┤
│ $HOME/.baoyu-skills/baoyu-url-to-markdown/EXTEND.md    │ User home         │
└────────────────────────────────────────────────────────┴───────────────────┘

┌───────────┬───────────────────────────────────────────────────────────────────────────┐
│  Result   │                                  Action                                   │
├───────────┼───────────────────────────────────────────────────────────────────────────┤
│ Found     │ Read, parse, apply settings                                               │
├───────────┼───────────────────────────────────────────────────────────────────────────┤
│ Not found │ **MUST** run first-time setup (see below) — do NOT silently create defaults │
└───────────┴───────────────────────────────────────────────────────────────────────────┘

**EXTEND.md Supports**: Download media by default | Default output directory | Default capture mode | Timeout settings

### First-Time Setup (BLOCKING)

**CRITICAL**: When EXTEND.md is not found, you **MUST use `AskUserQuestion`** to ask the user for their preferences before creating EXTEND.md. **NEVER** create EXTEND.md with defaults without asking. This is a **BLOCKING** operation — do NOT proceed with any conversion until setup is complete.

Use `AskUserQuestion` with ALL questions in ONE call:

**Question 1** — header: "Media", question: "How to handle images and videos in pages?"
- "Ask each time (Recommended)" — After saving markdown, ask whether to download media
- "Always download" — Always download media to local imgs/ and videos/ directories
- "Never download" — Keep original remote URLs in markdown

**Question 2** — header: "Output", question: "Default output directory?"
- "url-to-markdown (Recommended)" — Save to ./url-to-markdown/{domain}/{slug}.md
- (User may choose "Other" to type a custom path)

**Question 3** — header: "Save", question: "Where to save preferences?"
- "User (Recommended)" — ~/.baoyu-skills/ (all projects)
- "Project" — .baoyu-skills/ (this project only)

After user answers, create EXTEND.md at the chosen location, confirm "Preferences saved to [path]", then continue.

Full reference: [references/config/first-time-setup.md](references/config/first-time-setup.md)

### Supported Keys

| Key | Default | Values | Description |
|-----|---------|--------|-------------|
| `download_media` | `ask` | `ask` / `1` / `0` | `ask` = prompt each time, `1` = always download, `0` = never |
| `default_output_dir` | empty | path or empty | Default output directory (empty = `./url-to-markdown/`) |

**EXTEND.md → CLI mapping**:
| EXTEND.md key | CLI argument | Notes |
|---------------|-------------|-------|
| `download_media: 1` | `--download-media` | |
| `default_output_dir: ./posts/` | `--output-dir ./posts/` | Directory path. Do NOT pass to `-o` (which expects a file path) |

**Value priority**:
1. CLI arguments (`--download-media`, `-o`, `--output-dir`)
2. EXTEND.md
3. Skill defaults

## Features

- Chrome CDP for full JavaScript rendering
- Two capture modes: auto or wait-for-user
- Save rendered HTML as a sibling `-captured.html` file
- Clean markdown output with metadata
- Upgraded Defuddle-first markdown conversion with automatic fallback to the pre-Defuddle extractor from git history
- Materializes shadow DOM content before conversion so web-component pages survive serialization better
- YouTube pages can include transcript/caption text in the markdown when YouTube exposes a caption track
- If local browser capture fails completely, can fall back to `defuddle.md/<url>` and still save markdown
- Handles login-required pages via wait mode
- Download images and videos to local directories

## Usage

```bash
# Auto mode (default) - capture when page loads
${BUN_X} {baseDir}/scripts/main.ts <url>

# Wait mode - wait for user signal before capture
${BUN_X} {baseDir}/scripts/main.ts <url> --wait

# Save to specific file
${BUN_X} {baseDir}/scripts/main.ts <url> -o output.md

# Save to a custom output directory (auto-generates filename)
${BUN_X} {baseDir}/scripts/main.ts <url> --output-dir ./posts/

# Download images and videos to local directories
${BUN_X} {baseDir}/scripts/main.ts <url> --download-media
```

## Options

| Option | Description |
|--------|-------------|
| `<url>` | URL to fetch |
| `-o <path>` | Output file path — must be a **file** path, not directory (default: auto-generated) |
| `--output-dir <dir>` | Base output directory — auto-generates `{dir}/{domain}/{slug}.md` (default: `./url-to-markdown/`) |
| `--wait` | Wait for user signal before capturing |
| `--timeout <ms>` | Page load timeout (default: 30000) |
| `--download-media` | Download image/video assets to local `imgs/` and `videos/`, and rewrite markdown links to local relative paths |

## Capture Modes

| Mode | Behavior | Use When |
|------|----------|----------|
| Auto (default) | Capture on network idle | Public pages, static content |
| Wait (`--wait`) | User signals when ready | Login-required, lazy loading, paywalls |

**Wait mode workflow**:
1. Run with `--wait` → script outputs "Press Enter when ready"
2. Ask user to confirm page is ready
3. Send newline to stdin to trigger capture

## Output Format

Each run saves two files side by side:

- Markdown: YAML front matter with `url`, `title`, `description`, `author`, `published`, optional `coverImage`, and `captured_at`, followed by converted markdown content
- HTML snapshot: `*-captured.html`, containing the rendered page HTML captured from Chrome

When Defuddle or page metadata provides a language hint, the markdown front matter also includes `language`.

The HTML snapshot is saved before any markdown media localization, so it stays a faithful capture of the page DOM used for conversion.
If the hosted `defuddle.md` API fallback is used, markdown is still saved, but there is no local `-captured.html` snapshot for that run.

## Output Directory

Default: `url-to-markdown/<domain>/<slug>.md`
With `--output-dir ./posts/`: `./posts/<domain>/<slug>.md`

HTML snapshot path uses the same basename:

- `url-to-markdown/<domain>/<slug>-captured.html`
- `./posts/<domain>/<slug>-captured.html`

- `<slug>`: From page title or URL path (kebab-case, 2-6 words)
- Conflict resolution: Append timestamp `<slug>-YYYYMMDD-HHMMSS.md`

When `--download-media` is enabled:
- Images are saved to `imgs/` next to the markdown file
- Videos are saved to `videos/` next to the markdown file
- Markdown media links are rewritten to local relative paths

## Conversion Fallback

Conversion order:

1. Try Defuddle first
2. For rich pages such as YouTube, prefer Defuddle's extractor-specific output (including transcripts when available) instead of replacing it with the legacy pipeline
3. If Defuddle throws, cannot load, returns obviously incomplete markdown, or captures lower-quality content than the legacy pipeline, automatically fall back to the pre-Defuddle extractor
4. If the entire local browser capture flow fails before markdown can be produced, try the hosted `https://defuddle.md/<url>` API and save its markdown output directly
5. The legacy fallback path uses the older Readability/selector/Next.js-data based HTML-to-Markdown implementation recovered from git history

CLI output will show:

- `Converter: defuddle` when Defuddle succeeds
- `Converter: legacy:...` plus `Fallback used: ...` when fallback was needed
- `Converter: defuddle-api` when local browser capture failed and the hosted API was used instead

## Media Download Workflow

Based on `download_media` setting in EXTEND.md:

| Setting | Behavior |
|---------|----------|
| `1` (always) | Run script with `--download-media` flag |
| `0` (never) | Run script without `--download-media` flag |
| `ask` (default) | Follow the ask-each-time flow below |

### Ask-Each-Time Flow

1. Run script **without** `--download-media` → markdown saved
2. Check saved markdown for remote media URLs (`https://` in image/video links)
3. **If no remote media found** → done, no prompt needed
4. **If remote media found** → use `AskUserQuestion`:
   - header: "Media", question: "Download N images/videos to local files?"
   - "Yes" — Download to local directories
   - "No" — Keep remote URLs
5. If user confirms → run script **again** with `--download-media` (overwrites markdown with localized links)

## Environment Variables

| Variable | Description |
|----------|-------------|
| `URL_CHROME_PATH` | Custom Chrome executable path |
| `URL_DATA_DIR` | Custom data directory |
| `URL_CHROME_PROFILE_DIR` | Custom Chrome profile directory |

**Troubleshooting**: Chrome not found → set `URL_CHROME_PATH`. Timeout → increase `--timeout`. Complex pages → try `--wait` mode. If markdown quality is poor, inspect the saved `-captured.html` and check whether the run logged a legacy fallback.

### YouTube Notes

- The upgraded Defuddle path uses async extractors, so YouTube pages can include transcript text directly in the markdown body.
- Transcript availability depends on YouTube exposing a caption track. Videos with captions disabled, restricted playback, or blocked regional access may still produce description-only output.
- If the page needs time to finish loading descriptions, chapters, or player metadata, prefer `--wait` and capture after the watch page is fully hydrated.

### Hosted API Fallback

- The hosted fallback endpoint is `https://defuddle.md/<url>`. In shell form: `curl https://defuddle.md/stephango.com`
- Use it only when the local Chrome/CDP capture path fails outright. The local path still has higher fidelity because it can save the captured HTML and handle authenticated pages.
- The hosted API already returns Markdown with YAML frontmatter, so save that response as-is and then apply the normal media-localization step if requested.

## Extension Support

Custom configurations via EXTEND.md. See **Preferences** section for paths and supported options.
