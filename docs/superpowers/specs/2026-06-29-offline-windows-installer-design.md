# Design: Offline Windows Installer for graphify

**Date:** 2026-06-29
**Branch:** v8
**Scope:** build infrastructure, installer, dependency manifest, dev tooling

---

## Problem

The user wants to run graphify in a **Windows 10 desktop cloud environment that has no public network access at install time**. Today, the install path is `pip install graphifyy` (or `uv tool install graphifyy`), which requires pip / uv to reach PyPI — impossible in an air-gapped or offline machine.

Goal: produce a **single `.exe` offline installer** that:

- Embeds the Python 3.10+ runtime
- Embeds the full wheelhouse for the user's "code-only" use case (no PDF/video/Office)
- Embeds the graphify package itself (with all 14 host skill bodies, always-on blocks, the vendored `vis-network.min.js`, and the `references/` sidecars)
- Registers `graphify.exe` and `graphify-mcp.exe` on the user PATH (user-level only — never system)
- Installs the SKILL.md into the right host's skill directory (Claude Code / OpenCode / etc.)
- Uninstalls cleanly (no orphans, no system-wide damage)

Cloud LLM API calls (Anthropic / OpenAI / Gemini) remain allowed at **runtime** — only the install is offline. Whisper model downloads and PDF / Office / video / Neo4j extras are out of scope.

---

## Decisions (locked)

| Question | Decision |
|---|---|
| Offline scope | Install offline; runtime allowed to call cloud LLMs. |
| Content scope | Code-only corpus; skip `pdf`, `office`, `google`, `postgres`, `video`, `neo4j`, `falkordb`, `kimi`, `gemini`, `openai`, `bedrock`, `dm` extras. |
| Target platform | Windows 10 desktop cloud (x86_64). |
| Package format | Single `.exe`. |
| Bundling tech | Nuitka `--onefile` (project already lists `nuitka>=4.1` in dev deps). |
| Wheelhouse variants | One flavor, all defaults bundled (option A). |
| Default extras bundled | `core` + `anthropic` + `mcp` + `leiden` + `sql` + `watch` + `svg` + `chinese` + `terraform`. |
| PATH registration | User-level (`HKCU\Environment\Path`), never system. |
| Host selection | Detect installed hosts at install time; if multiple found, prompt; if zero, warn but still install graphify. |
| Unknown hosts (e.g. mobilecoder) | Installer copies SKILL.md to the host's convention path (`~/.mobilecoder/skills/graphify/SKILL.md`) directly, bypassing `graphify install` since that command has no entry for it. |
| Verification | Run on a clean Windows 10 VM with network disabled, check V1–V14. |

---

## 1. Architecture

```
Windows 10 桌面云电脑 (target machine, no internet at install time)
                    │
                    │ double-click graphify-installer.exe
                    ▼
        ┌──────────────────────────────────────────┐
        │  graphify-installer.exe  (Nuitka --onefile)
        │  ├─ Python 3.10 stdlib frozen into the binary
        │  ├─ core wheelhouse (25 wheels)          │
        │  ├─ selected extras (9 extras)            │
        │  ├─ graphify package (incl.              │
        │  │   skill.md, skill-<host>.md × 14,     │
        │  │   always_on/*.md,                     │
        │  │   skills/<host>/references/*.md,      │
        │  │   assets/vis-network.min.js)          │
        │  └─ installer entry point logic          │
        └──────────────────┬───────────────────────┘
                           │
            installs to: %LOCALAPPDATA%\graphify\
                           │
                           ├─ bin\graphify.exe         (added to user PATH)
                           ├─ bin\graphify-mcp.exe
                           ├─ lib\...                  (wheelhouse)
                           └─ share\graphify\...      (skill resources)
                           │
                           │ invokes: shutil.copy to target host's skill dir
                           ▼
        ┌──────────────────────────────────────────┐
        │  C:\Users\<user>\.claude\                │
        │  skills\graphify\SKILL.md               │
        │  skills\graphify\references\...         │
        └──────────────────────────────────────────┘
                           │
                           │ user types /graphify . in Claude Code
                           ▼
                cloud LLM API (allowed at runtime)
```

### Boundary table

| Concern | Treatment |
|---|---|
| Install medium (Python + wheels + skill files) | **Offline**, frozen in `.exe`. |
| Python interpreter | **Frozen** (Nuitka-compiled to native code). |
| Runtime cloud LLM API | **Allowed** (user configures API key separately). |
| Whisper model | **Not bundled** (code-only). |
| Video / PDF / Office processing | **Not bundled** (out of scope). |
| User-level PATH | Modified (auto-removed on uninstall). |
| System-level PATH | **Never touched**. |
| System registry | **Never touched** (only `HKCU\Environment\Path`). |

---

## 2. Wheelhouse scope

### Bundled by default

| Source | Wheels | Why |
|---|---|---|
| Core | `networkx>=3.4`, `numpy>=1.21`, `rapidfuzz>=3.0`, `tree-sitter>=0.23,<0.26`, plus 22 `tree-sitter-<lang>` wheels | AST extraction — required for any code analysis. |
| `anthropic` | `anthropic` | Default LLM provider. |
| `mcp` | `mcp`, `starlette>=1.3.1` | MCP server (`graphify-mcp`) entry point — required for Claude Code to talk to graphify. |
| `leiden` | `graspologic` (Py<3.13) | Community detection algorithm. |
| `sql` | `tree-sitter-sql` | Parse `.sql` files. |
| `terraform` | `tree-sitter-hcl` | Parse `.tf` files. |
| `chinese` | `jieba` | Chinese tokenization. |
| `watch` | `watchdog` | `--watch` mode auto-rebuild. |
| `svg` | `matplotlib` | `to_svg` export. |

### Not bundled (out of scope)

- `pdf` (`pypdf`, `markdownify`) — code-only corpus.
- `office` (`python-docx`, `openpyxl`) — code-only.
- `google` (`openpyxl`) — code-only.
- `postgres` (`psycopg[binary]`) — no DB integration needed.
- `video` (`faster-whisper`, `yt-dlp`) — no video in scope; also pulls a 150 MB model download.
- `neo4j` / `falkordb` — no DB integration needed.
- `kimi` / `gemini` / `openai` — `anthropic` covers the default LLM path; the others can be installed separately if the user switches provider.
- `bedrock` — AWS-specific.
- `dm` (`tree-sitter-dm`) — BYOND language, niche.

### Pyproject changes

The `all` extra in `pyproject.toml` already lists everything. **No change needed to `dependencies` or `project.optional-dependencies`.** The bundling is purely a build-time decision: when invoking Nuitka, include only the modules listed above via `--include-module` / `--include-package`.

A new optional extra `windows-offline` may be added to pyproject as documentation (pointing to the Nuitka build recipe) — see §6.

---

## 3. Nuitka build configuration

### Build command skeleton

```bash
python -m nuitka \
  --standalone \
  --onefile \
  --windows-disable-console \
  --windows-icon=assets/graphify.ico \
  --enable-plugin=anti-bloat,multiprocessing \
  --include-package=graphify \
  --include-package-data=graphify \
  --include-module=networkx,numpy,rapidfuzz \
  --include-module=anthropic \
  --include-module=mcp,starlette \
  --include-module=graspologic \
  --include-module=tree_sitter,tree_sitter_python,tree_sitter_javascript,\
tree_sitter_typescript,tree_sitter_go,tree_sitter_rust,tree_sitter_java,\
tree_sitter_groovy,tree_sitter_c,tree_sitter_cpp,tree_sitter_ruby,\
tree_sitter_c_sharp,tree_sitter_kotlin,tree_sitter_scala,tree_sitter_php,\
tree_sitter_swift,tree_sitter_lua,tree_sitter_zig,tree_sitter_powershell,\
tree_sitter_elixir,tree_sitter_objc,tree_sitter_julia,tree_sitter_verilog,\
tree_sitter_fortran,tree_sitter_bash,tree_sitter_json \
  --include-module=matplotlib,watchdog,tree_sitter_sql,tree_sitter_hcl,jieba \
  --output-filename=graphify-installer.exe \
  graphify/__main__.py
```

`graphify-mcp` is compiled separately with `graphify/serve.py` as the entry point and `--output-filename=graphify-mcp.exe`.

### Key decisions

1. **`--onefile` vs `--standalone`** — `--onefile` produces a single `.exe` that decompresses to `%TEMP%\onefile_<pid>_<random>\` at launch and cleans up on exit. Required for the "double-click install" UX. `--standalone` (folder output) is rejected.
2. **`--windows-disable-console`** — double-clicking the `.exe` must not pop a black cmd window. stdout/stderr still go to a log file (`graphify.log`) next to the `.exe`. When run from cmd, normal behavior applies.
3. **`anti-bloat`, `multiprocessing` plugins** — `anti-bloat` drops stdlib (test, unittest, pydoc, etc.) to shrink the binary. `multiprocessing` is required on Windows for fork-spawn handling. **Do not** enable `numpy` or `matplotlib` plugins — their Windows wheels are precompiled C extensions, Nuitka handles them correctly via `--include-module`.
4. **`tree-sitter` and language packs** — each `tree_sitter_*` package is an independent wheel with its own `.pyd` C extension. All 23 must be listed explicitly via `--include-module` (or a single `--include-module=tree_sitter_*` glob — verify in build log).
5. **`--include-package-data=graphify`** — critical: this is what pulls `graphify/skill.md`, the 14 `skill-<host>.md` files, the `skills/<host>/references/*.md` sidecars, the `always_on/*.md` blocks, and the vendored `graphify/assets/vis-network.min.js` into the binary. The pyproject `package-data` glob (already updated in the vis-network spec) ensures these files are in the wheel at build time; this Nuitka flag ensures Nuitka pulls them out of the wheel into the frozen binary.
6. **Two binaries, not one** — `graphify.exe` (entry: `graphify.__main__:main`) and `graphify-mcp.exe` (entry: `graphify.serve:_main`). Both compiled in the same build run, output to `bin\` of the install dir. A single dispatcher binary is rejected — it complicates the install layout and adds a shebang-style indirection.
7. **Onefile size estimate** — ~65 MB on disk (numpy 15 MB + matplotlib 12 MB + networkx 3 MB + tree-sitter stack 8 MB + Anthropic + MCP + Leiden 10 MB + Python stdlib frozen 10 MB + skill files + vis-network 2 MB + Nuitka runtime overhead 5 MB).
8. **Build time** — first build 15–25 minutes on Windows + Visual Studio Build Tools; incremental 2–5 minutes.

### Dev tooling additions

In `pyproject.toml` `[dependency-groups]` dev, add (only if not present):

```toml
"ordered-set>=4.1",   # Nuitka dependency
"zstandard>=0.18",    # faster onefile decompression
```

---

## 4. Windows installer behavior

### Install flow (triggered by double-clicking the `.exe`)

```
1. Check if already installed
     │
     ├─ Yes → prompt: Upgrade / Reinstall / Uninstall
     │
     └─ No ↓
2. Choose install path
     (default: %LOCALAPPDATA%\graphify\)
3. Host detection
     (probe host home dirs — see Host Selection below)
4. Choose host(s) to register skill for
     (auto-select if 1 detected; prompt if multiple; warn if 0)
5. Decompress wheelhouse + skill resources to install dir
6. Register user-level PATH
     (append %LOCALAPPDATA%\graphify\bin to HKCU\Environment\Path;
      NOT touching HKLM\SYSTEM\...)
7. Copy SKILL.md + references/ to the chosen host's skill dir(s)
8. Optionally create Start Menu shortcut
9. Print success summary, show next-steps hint
```

### Host detection logic

```
At install time, probe the following paths under %USERPROFILE%:
    .claude\             → Claude Code
    .codex\              → Codex CLI
    .config\opencode\    → OpenCode
    .config\kilo\        → Kilo Code
    .aider\              → Aider
    .copilot\            → GitHub Copilot
    .codebuddy\          → CodeBuddy
    .kiro\               → AWS Kiro
    .factory\            → Factory Droid
    .trae\ / .trae-cn\   → Trae / Trae-CN
    .hermes\             → Hermes
    .pi\                 → Pi
    .openclaw\           → OpenClaw
    .agents\             → Generic AGENTS.md (fallback)
    .mobilecoder\        → mobilecoder (NOT in graphify's _PLATFORM_CONFIG;
                            see "Unknown hosts" below)
    .cursor\             → Cursor
    .gemini\             → Gemini CLI
```

Resolution rules:
- **1 detected** → install skill for it automatically.
- **Multiple detected** → list them, ask user to pick one (or more, comma-separated).
- **0 detected** → warn: "No known host found. The graphify binary will still be installed and on your PATH; you'll need to manually copy SKILL.md to your host's skill directory later." Continue the rest of the install.

### Unknown hosts (mobilecoder case)

`mobilecoder` is **not** in `graphify/__main__.py:_PLATFORM_CONFIG`. The standard `graphify install <host>` command will reject it. The installer must therefore handle it directly:

1. **Detection** — probe `%USERPROFILE%\.mobilecoder\` (or any path the user names).
2. **Skill copy** — `shutil.copy` the chosen `skill-<host>.md` (default: `skill.md`, the Claude bundle, since mobilecoder is not in the project) to `<host-home>\skills\graphify\SKILL.md`. Also copy `references/` sidecar if the chosen bundle has one.
3. **No CLAUDE.md registration** — don't try to call the project's CLAUDE.md registration path; it's host-specific.

This logic is added to the installer as a small block, **not** by extending `_PLATFORM_CONFIG` in the graphify project (we don't ship first-class mobilecoder support in the open-source project — that's a separate decision).

### Installer UI

- **No GUI dependencies.** The installer runs as a console app even though the launched binary itself is `--windows-disable-console`. The installer shows a text-based wizard (welcome → install path → host selection → confirm → progress → done). It's invoked explicitly via `graphify-installer.exe install` (or as the default action on double-click).
- **Tkinter is not used.** It would require shipping an additional Python stdlib GUI module, blow the binary size, and complicate cross-frozen-exe behavior. Text wizard is sufficient for an internal/offline tool.

### Uninstall

```
graphify-installer.exe uninstall
    │
    ├─ Remove %LOCALAPPDATA%\graphify\
    ├─ Remove %LOCALAPPDATA%\graphify\bin from user PATH
    ├─ Remove installed skill dirs (per host, if recorded at install time)
    ├─ Remove Start Menu shortcut
    └─ Report any leftover files (e.g., user-created graphify-out/)
```

A machine-readable manifest at `%LOCALAPPDATA%\graphify\.graphify_install.json` records what was installed where so uninstall can reverse cleanly.

---

## 5. Offline verification

### Goal

End-to-end validate the installer in a **fully offline** Windows 10 VM.

### Verification environment

```
Dev machine (macOS, online)
    │
    │ build graphify-installer.exe
    ▼
Windows 10 x86_64 VM (Parallels / Hyper-V / VirtualBox)
    network adapter disabled
    Claude Code (or OpenCode / mobilecoder) pre-installed
    │
    │ copy graphify-installer.exe in via host-shared folder
    ▼
double-click → run /graphify . on a small test repo
```

### Validation checklist

| # | Item | Pass condition |
|---|------|----------------|
| V1 | Installer launches | Double-click `.exe` → no cmd window pops (graphify.exe is `--windows-disable-console`); installer wizard text appears in a separate console / log file. |
| V2 | Path selection | Default `%LOCALAPPDATA%\graphify\` is accepted. |
| V3 | Host detection | Installed Claude Code / OpenCode / etc. is correctly identified. |
| V4 | Decompression | `bin\graphify.exe` exists after install. |
| V5 | User PATH | New cmd window: `graphify --version` returns `0.9.1` without re-specifying path. |
| V6 | Main CLI | `graphify --help` lists all subcommands. |
| V7 | MCP entry | `graphify-mcp --help` works. |
| V8 | Skill install | Chosen host's `skills/graphify/SKILL.md` exists. |
| V9 | Skill references | `skills/graphify/references/*.md` all copied. |
| V10 | Host recognizes skill | In a test repo, type `/graphify` — appears in host's command list. |
| V11 | End-to-end pipeline | `/graphify .` on a test repo produces `graph.json`, `GRAPH_REPORT.md`, `graph.html`. |
| V12 | Offline HTML render | Open `graph.html` in browser; Network tab shows **zero external requests** (no unpkg, no anything). |
| V13 | Cloud LLM (separate run) | With API key configured, semantic extraction runs. (This one needs network — run on a separate, online verification round.) |
| V14 | Uninstall | `graphify-installer.exe uninstall` removes everything recorded in the manifest; `where graphify` returns nothing. |

### Automated test script (skeleton)

`tools/test_offline_install.py`:

```python
def test_offline_install(vm_host, vm_user, installer_path, host_name):
    """Connect to a clean offline Windows 10 VM, install, verify V1-V14."""
    ...
```

The script is best-effort: it can run from a macOS dev box with `pywinrm` / `paramiko`, but VM orchestration (snapshot/rollback, network adapter toggling) varies by hypervisor. For this iteration, **manual execution on the user's Windows desktop cloud machine is acceptable** — the validation matrix is the artifact, not the script.

### Minimum viable verification (no VM)

If no Windows VM is available:

1. **Run the `.exe` under Wine on macOS** to confirm basic executability.
2. **Run the full install on the user's actual Windows 10 desktop cloud machine** as the manual acceptance test.
3. **Capture logs from each V-item run** as the regression baseline for future rebuilds.

---

## 6. Files changed / created

| File | Action | Responsibility |
|---|---|---|
| `tools/build_windows_installer.sh` | **Create** | Wraps the Nuitka invocation; downloads Windows wheels via `pip download` into a local wheelhouse; runs Nuitka twice (for `graphify.exe` and `graphify-mcp.exe`); outputs to `dist/`. |
| `tools/build_windows_installer.py` | **Create** | Cross-platform equivalent (for CI / macOS dev boxes with a Windows VM runner). |
| `graphify/installer/__init__.py` | **Create** | The installer logic (host detection, PATH registration, skill copy, uninstall). Imported by `graphify/__main__.py` so the same `graphify.exe install` / `graphify.exe uninstall` commands work in both online and offline contexts. |
| `graphify/installer/host_probe.py` | **Create** | Probe which host skill dirs exist on the user's machine. |
| `graphify/installer/path_win.py` | **Create** | User-level PATH manipulation via PowerShell (`[Environment]::SetEnvironmentVariable`). |
| `graphify/__main__.py` | **Modify** | Add `install` / `uninstall` subcommands that delegate to `graphify.installer` (no behavior change for the existing `graphify install <host>` flow). |
| `pyproject.toml` | **Modify** | Add `ordered-set`, `zstandard` to dev deps. Optionally add `[project.optional-dependencies].windows-offline = [...]` listing every default-bundled wheel as documentation; this doesn't trigger anything at install time but tells readers what the offline installer covers. |
| `docs/operations/offline-installer.md` | **Create** | End-user doc: how to install on an offline Windows machine, what to expect during the wizard, how to uninstall. |

No changes to graphify's core pipeline modules (`detect.py`, `extract.py`, `build.py`, `cluster.py`, `analyze.py`, `report.py`, `export.py`).

---

## 7. Risks and boundaries

1. **Nuitka compilation failures are package-version sensitive.** A future bump to `numpy` or `tree-sitter` may require a `--include-module` adjustment. Mitigation: pin versions in `pyproject.toml`, document the wheel versions the build was last validated against.
2. **Cross-version Python.** Nuitka compiles against one specific Python (3.10 in our case). The `requires-python = ">=3.10"` in pyproject allows 3.10–3.13 installs online; the offline binary is **only Python 3.10**. Users on 3.11+ who want a Python-version-matched binary need a separate build. Out of scope for this spec; can be addressed later with a build matrix.
3. **First-build time on Windows.** 15–25 minutes with Visual Studio Build Tools installed; longer if the toolchain needs installation. Document the prereqs in the build script.
4. **mobilecoder is not first-class.** The installer copies a generic SKILL.md there; the user's mobilecoder may or may not honor it. If it doesn't, the user must manually adjust. This is a known limitation; documenting it is sufficient.
5. **Antigravity on Windows.** `graphify/__main__.py:709` already special-cases `antigravity` → `antigravity-windows` on `sys.platform == 'win32'`. The installer benefits from this — picking "antigravity" as the host on Windows correctly routes to the PowerShell bundle.
6. **Code-signing not in scope.** The `.exe` will be unsigned; Windows SmartScreen will warn on first launch. Out of scope for this iteration; document as a known wart. Mitigation for the user: click "More info → Run anyway" once, or pin the certificate if/when one is obtained.
7. **No automatic update mechanism.** The user must re-download and re-run the installer to upgrade. Acceptable for an offline-only distribution.
8. **`graphify-out/` from prior runs is not touched by uninstall.** Each user's project-local `graphify-out/` directory is independent of the install location and persists. Document this in the uninstall output.
9. **Wheel-size may exceed initial 65 MB estimate** — matplotlib + numpy together can be 25–30 MB on Windows. Final size will be measured on the first build; if it exceeds ~80 MB we re-evaluate whether matplotlib is worth bundling by default.

---

## 8. Summary of touched files

| File | Action |
|---|---|
| `tools/build_windows_installer.sh` | **Create** — Nuitka invocation. |
| `tools/build_windows_installer.py` | **Create** — CI-friendly equivalent. |
| `graphify/installer/__init__.py` | **Create** — installer logic. |
| `graphify/installer/host_probe.py` | **Create** — host detection. |
| `graphify/installer/path_win.py` | **Create** — Windows PATH manipulation. |
| `graphify/__main__.py` | **Modify** — wire `install`/`uninstall` subcommands. |
| `pyproject.toml` | **Modify** — dev deps (`ordered-set`, `zstandard`), optional `windows-offline` extra for documentation. |
| `docs/operations/offline-installer.md` | **Create** — user-facing doc. |

No changes to: pipeline modules, the `graphify-out/` layout, the 14 host skill bodies, or any of the runtime graph-generation code.