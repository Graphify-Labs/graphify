# graphify Offline Windows Installer

A single `.exe` that installs `graphify` on a Windows 10 machine with **no
network access at install time**. Bundles the Python runtime, the wheelhouse
for code-only analysis, and the `graphify` package itself (with all 14 host
skill bodies, always-on blocks, and the vendored vis-network bundle).

Cloud LLM API calls (Anthropic / OpenAI / Gemini) remain allowed at
**runtime** — only the install is offline. Whisper model downloads and PDF
/ Office / video / Neo4j extras are not bundled; this installer targets
**code-only** corpora.

## Install

1. Copy `graphify-installer.exe` to the target Windows machine (USB,
   shared folder, etc.).
2. Double-click it. A console window will show:
   - Detected AI-coding hosts (Claude Code / OpenCode / etc.).
   - The install path (default `%LOCALAPPDATA%\graphify\`).
3. Press Enter to confirm. The installer:
   - Decompresses `graphify.exe` and `graphify-mcp.exe` into
     `%LOCALAPPDATA%\graphify\bin\`.
   - Copies the appropriate `SKILL.md` to the detected host's skill
     directory (`%USERPROFILE%\.claude\skills\graphify\SKILL.md` for
     Claude Code, `~/.config/opencode/skills/graphify/SKILL.md` for
     OpenCode, etc.).
   - Registers `%LOCALAPPDATA%\graphify\bin` on the user-level PATH
     (does **not** modify system PATH).
4. **Open a new** cmd / PowerShell window so the PATH change takes effect.

## Use

```
> graphify --version
graphify 0.9.1

> graphify-mcp --help
...

> cd C:\path\to\your\code
> graphify extract .
... builds graphify-out\graph.html, graph.json, GRAPH_REPORT.md
```

In your AI-coding host (Claude Code / OpenCode / etc.), type:

```
/graphify .
```

## Uninstall

```
> graphify-installer.exe uninstall
```

This will:
- Remove the SKILL.md and `references/` from each host's skill directory.
- Remove `%LOCALAPPDATA%\graphify\bin` from the user PATH.
- Delete `%LOCALAPPDATA%\graphify\`.

It will **not** touch any `graphify-out\` directory in your project repos —
those are per-project artifacts and you can delete them yourself if desired.

## What's inside the .exe

- Python 3.10 stdlib (frozen).
- `graphifyy` package (all submodules).
- 9 default extras: `anthropic`, `mcp`, `leiden`, `sql`, `watch`, `svg`,
  `chinese`, `terraform`, and the `tree-sitter` language stack (23 languages).
- The vendored `vis-network.min.js` (the script the HTML viewer needs).
- All 14 host skill bodies and `references/` sidecars (Claude, Codex,
  OpenCode, Kilo, Aider, Copilot, CodeBuddy, Kiro, Droid, Trae, Hermes,
  Pi, OpenClaw, Antigravity, etc.).
- **15 community skills under the `gf-` namespace** (14 superpowers + `gf-llm-wiki`).
  Installed alongside `graphify/` in each host's skill directory and
  immediately discoverable — trigger via `/gf-brainstorming`,
  `/gf-writing-plans`, etc. The `gf-` prefix guarantees no collision with a
  user's separately installed superpowers plugin. See `graphify/bundled_skills/README.md`.

**Not bundled** (you'll get a clear error if you try to use them): PDF
extraction, Office files, video transcription, Neo4j / FalkorDB direct
connect, AWS Bedrock, BYOND (`tree-sitter-dm`).

## Limitations

- **Windows SmartScreen warning.** The `.exe` is not code-signed; on
  first launch, click "More info → Run anyway".
- **No auto-update.** Re-download the latest `graphify-installer.exe`
  to upgrade.
- **Per-project `graphify-out\` is not removed by uninstall.**
- **`mobilecoder` is best-effort.** graphify doesn't ship first-class
  support for mobilecoder; the installer copies a generic `SKILL.md`
  there. If mobilecoder doesn't recognize it, file an issue.
- **Cursor and Gemini hosts need a follow-up.** The offline installer
  detects them and prints a note, but it does **not** write a `SKILL.md`
  into their directories (their install format is different — `.mdc`
  for Cursor, a `GEMINI.md` section + `settings.json` hook for Gemini).
  After the offline installer finishes, run:
  ```
  > graphify install cursor
  > graphify install gemini
  ```
  to complete the setup for those two hosts.

## Re-building the installer

The build script (`tools/build_windows_installer.sh`) requires:
- Python 3.10+
- Visual Studio Build Tools (or MinGW) on `PATH`
- `nuitka`, `ordered-set`, `zstandard` in the build venv

```bash
# On a Windows checkout of graphify:
tools\build_windows_installer.sh
```

The artifacts land in `dist\`:
- `graphify-installer.exe` — the offline installer
- `graphify.exe` — the bundled graphify CLI
- `graphify-mcp.exe` — the bundled graphify MCP server

## Reporting issues

File at <https://github.com/safishamsi/graphify/issues> with the output of
`graphify-installer.exe install` (or `uninstall`) in verbose mode.
