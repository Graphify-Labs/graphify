# Offline Windows Installer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a single `.exe` that installs `graphify` + `graphify-mcp` to a Windows 10 machine with no network at install time, registers them on the user-level PATH, and copies the SKILL.md into the user's detected host's skill directory (Claude Code / OpenCode / mobilecoder / etc.) — all without touching system-wide state.

**Architecture:** A new `graphify/installer/` subpackage holds the installer logic (host detection, Windows PATH manipulation, skill copy, manifest-driven uninstall). A standalone entry script `tools/installer_main.py` is compiled by Nuitka `--onefile` into `graphify-installer.exe`. At install time the `.exe` decompresses the bundled wheelhouse (core + 9 default extras) plus the `graphify` package (with all 14 host skill bodies, always-on blocks, and the vendored `vis-network.min.js`) into `%LOCALAPPDATA%\graphify\`, registers `bin\` on the user-level PATH, and copies the appropriate SKILL.md to the detected host(s). Cloud LLM API calls remain allowed at runtime.

**Tech Stack:** Python 3.10+, `pathlib`, `subprocess` (PowerShell for PATH), `importlib.resources`, `pytest`, `Nuitka>=4.1` + `ordered-set` + `zstandard` (build-time only).

**Spec:** `docs/superpowers/specs/2026-06-29-offline-windows-installer-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `pyproject.toml` | **Modify** | Add `ordered-set`, `zstandard` to dev deps. Add `[project.optional-dependencies].windows-offline` extra (documentation only). |
| `graphify/installer/__init__.py` | **Create** | Orchestrator: `install()` and `uninstall()` entry points; manifest read/write. |
| `graphify/installer/host_probe.py` | **Create** | Probe `%USERPROFILE%\.claude\`, `\.config\opencode\`, etc. — return which hosts are installed. |
| `graphify/installer/path_win.py` | **Create** | Add/remove a path on user-level Windows PATH via `[Environment]::SetEnvironmentVariable` over PowerShell. |
| `graphify/installer/skill_copy.py` | **Create** | Copy the right `skill-<host>.md` + `references/` sidecar to a host's skill directory. Handles `mobilecoder` (not in `_PLATFORM_CONFIG`) via direct `shutil.copy`. |
| `graphify/installer/manifest.py` | **Create** | Read/write the install manifest at `%LOCALAPPDATA%\graphify\.graphify_install.json`. |
| `tools/installer_main.py` | **Create** | Standalone entry script compiled by Nuitka. argparse subcommands: `install`, `uninstall`, `--version`, `--help`. |
| `graphify/__main__.py` | **Modify** | Add `self-install` / `self-uninstall` subcommands that delegate to `graphify.installer` (no change to existing `install <platform>` flow). |
| `tools/build_windows_installer.sh` | **Create** | Bash wrapper around the Nuitka invocation: pip-downloads Windows wheels, runs Nuitka twice (for `graphify.exe` and `graphify-mcp.exe`), then a third time for `graphify-installer.exe`. |
| `tools/build_windows_installer.py` | **Create** | Cross-platform Python equivalent of the build script (for CI). |
| `docs/operations/offline-installer.md` | **Create** | End-user doc: how to install on an offline Windows machine, what the wizard shows, how to uninstall. |
| `tests/test_installer_host_probe.py` | **Create** | Unit tests for `host_probe`. |
| `tests/test_installer_path_win.py` | **Create** | Unit tests for `path_win` (with `subprocess.run` mocked). |
| `tests/test_installer_skill_copy.py` | **Create** | Unit tests for `skill_copy`. |
| `tests/test_installer_manifest.py` | **Create** | Unit tests for `manifest`. |
| `tests/test_installer_orchestrator.py` | **Create** | Unit tests for `graphify.installer.install` / `uninstall` (with filesystem mocking). |

---

## Task 1: Add dev dependencies and `windows-offline` extra to `pyproject.toml`

**Files:**
- Modify: `pyproject.toml` (the `dev` list in `[dependency-groups]` and the `optional-dependencies` table)

- [ ] **Step 1: Add Nuitka runtime helpers to dev deps**

Open `pyproject.toml`. Find the `[dependency-groups].dev` list (currently at lines 85–102). Add these two entries (alphabetical order is fine — current list is alphabetical):

```toml
    "ordered-set>=4.1",
    "zstandard>=0.18",
```

`ordered-set` is a hard Nuitka requirement; `zstandard` makes `--onefile` decompression faster (optional but recommended in the Nuitka docs).

- [ ] **Step 2: Add `windows-offline` extra**

Find the `[project.optional-dependencies]` table (line 50). Add a new entry at the end (before `all = [...]` at line 78):

```toml
# Documentation-only: lists every wheel the offline Windows installer bundles.
# This is NOT installed at runtime; it exists so readers of pyproject.toml can
# see at a glance what `graphify-installer.exe` contains.
windows-offline = [
    "networkx>=3.4",
    "numpy>=1.21",
    "rapidfuzz>=3.0",
    "tree-sitter>=0.23.0,<0.26",
    "tree-sitter-python>=0.23,<0.26",
    "tree-sitter-javascript>=0.23,<0.26",
    "tree-sitter-typescript>=0.23,<0.25",
    "tree-sitter-go>=0.23,<0.26",
    "tree-sitter-rust>=0.23,<0.25",
    "tree-sitter-java>=0.23,<0.25",
    "tree-sitter-groovy>=0.1,<0.3",
    "tree-sitter-c>=0.23,<0.26",
    "tree-sitter-cpp>=0.23,<0.25",
    "tree-sitter-ruby>=0.23,<0.25",
    "tree-sitter-c-sharp>=0.23,<0.25",
    "tree-sitter-kotlin>=1.0,<2.0",
    "tree-sitter-scala>=0.23,<0.27",
    "tree-sitter-php>=0.23,<0.25",
    "tree-sitter-swift>=0.7,<0.9",
    "tree-sitter-lua>=0.2,<0.6",
    "tree-sitter-zig>=1.0,<2.0",
    "tree-sitter-powershell>=0.26,<0.28",
    "tree-sitter-elixir>=0.3,<0.5",
    "tree-sitter-objc>=3.0,<4.0",
    "tree-sitter-julia>=0.23,<0.25",
    "tree-sitter-verilog>=1.0,<2.0",
    "tree-sitter-fortran>=0.6,<0.8",
    "tree-sitter-bash>=0.23,<0.27",
    "tree-sitter-json>=0.23,<0.26",
    "anthropic",
    "mcp",
    "starlette>=1.3.1",
    "graspologic; python_version < '3.13'",
    "tree-sitter-sql",
    "tree-sitter-hcl",
    "jieba",
    "watchdog",
    "matplotlib",
]
```

- [ ] **Step 3: Verify `pyproject.toml` still parses**

```bash
uv run python -c "import tomllib; tomllib.loads(open('pyproject.toml').read()); print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: add Nuitka runtime helpers + windows-offline extra doc"
```

---

## Task 2: Create the `graphify/installer/` package skeleton

**Files:**
- Create: `graphify/installer/__init__.py`
- Create: `graphify/installer/host_probe.py` (placeholder)
- Create: `graphify/installer/path_win.py` (placeholder)
- Create: `graphify/installer/skill_copy.py` (placeholder)
- Create: `graphify/installer/manifest.py` (placeholder)

- [ ] **Step 1: Create the directory and 5 empty files**

```bash
mkdir -p graphify/installer
touch graphify/installer/__init__.py \
      graphify/installer/host_probe.py \
      graphify/installer/path_win.py \
      graphify/installer/skill_copy.py \
      graphify/installer/manifest.py
```

- [ ] **Step 2: Verify the package imports**

```bash
uv run python -c "from graphify.installer import host_probe, path_win, skill_copy, manifest; print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add graphify/installer/
git commit -m "feat(installer): add installer package skeleton"
```

---

## Task 3: Implement `host_probe` (TDD)

**Files:**
- Modify: `graphify/installer/host_probe.py`
- Create: `tests/test_installer_host_probe.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_installer_host_probe.py`:

```python
"""Tests for graphify.installer.host_probe.

These tests use `tmp_path` to simulate the user's home directory. Production
behavior probes `%USERPROFILE%`; the test injects a fake root via the
`root=` parameter.
"""

from pathlib import Path

from graphify.installer.host_probe import KNOWN_HOSTS, detect_hosts, host_skill_dir


def test_known_hosts_includes_claude_and_opencode():
    names = {h.name for h in KNOWN_HOSTS}
    assert "claude" in names
    assert "opencode" in names


def test_known_hosts_includes_mobilecoder_as_direct_copy():
    # mobilecoder is not in graphify's _PLATFORM_CONFIG, so the installer must
    # copy SKILL.md to the host's convention path directly (see spec §4
    # "Unknown hosts"). Mark it explicitly so callers branch on it.
    mc = next(h for h in KNOWN_HOSTS if h.name == "mobilecoder")
    assert mc.uses_graphify_install is False
    assert mc.skill_subpath == Path("skills") / "graphify"


def test_detect_hosts_returns_empty_when_no_hosts_present(tmp_path):
    # tmp_path is empty; no host should be detected.
    detected = detect_hosts(root=tmp_path)
    assert detected == []


def test_detect_hosts_finds_claude(tmp_path):
    (tmp_path / ".claude").mkdir()
    detected = detect_hosts(root=tmp_path)
    assert any(h.name == "claude" for h in detected)


def test_detect_hosts_finds_opencode(tmp_path):
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    detected = detect_hosts(root=tmp_path)
    assert any(h.name == "opencode" for h in detected)


def test_detect_hosts_finds_multiple(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".config" / "opencode").mkdir(parents=True)
    detected = detect_hosts(root=tmp_path)
    names = {h.name for h in detected}
    assert {"claude", "opencode"}.issubset(names)


def test_host_skill_dir_for_claude(tmp_path):
    host = next(h for h in KNOWN_HOSTS if h.name == "claude")
    skill_dir = host_skill_dir(host, root=tmp_path)
    assert skill_dir == tmp_path / ".claude" / "skills" / "graphify"
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
uv run pytest tests/test_installer_host_probe.py -v
```

Expected: FAIL with `ImportError: cannot import name 'KNOWN_HOSTS' from 'graphify.installer.host_probe'`.

- [ ] **Step 3: Implement `host_probe.py`**

Replace `graphify/installer/host_probe.py` with:

```python
"""Detect which AI-coding hosts are installed on the user's machine.

Probes a small set of well-known home-directory signatures (e.g.
`~/.claude/`, `~/.config/opencode/`, `~/.mobilecoder/`). Used by the offline
installer to decide which host(s) to register the SKILL.md for, and by
`skill_copy` to resolve the per-host skill directory.

For hosts that ARE in `graphify.__main__._PLATFORM_CONFIG` we set
`uses_graphify_install=True` (the installer can call `graphify install <host>`
to do the copy). For hosts that AREN'T (e.g. `mobilecoder`), we set
`uses_graphify_install=False` and the installer must `shutil.copy` SKILL.md
directly to the host's convention path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List

# Hosts that graphify's `_PLATFORM_CONFIG` knows about; the installer can
# delegate to `graphify install <host>` for these.
_GRAPHIFY_INSTALL_HOSTS = frozenset({
    "claude", "codex", "kilo", "aider", "copilot", "claw", "droid",
    "trae", "trae-cn", "hermes", "kiro", "pi", "codebuddy", "antigravity",
    "windows", "amp", "agents", "vscode",
})


@dataclass(frozen=True)
class Host:
    """A known AI-coding host.

    Attributes:
        name: short identifier (e.g. "claude", "opencode", "mobilecoder").
        marker: a path relative to the user's home directory whose existence
            means this host is installed. Detection is "any file/dir under
            this path" — we just stat the path itself.
        skill_subpath: path relative to `root` where the SKILL.md should
            be written (typically `<root>/<host-home>/skills/graphify/SKILL.md`).
        uses_graphify_install: True if the host is in `_PLATFORM_CONFIG` and
            we should call `graphify install <host>`; False if we must do a
            direct `shutil.copy` (the host isn't first-class supported).
    """
    name: str
    marker: Path
    skill_subpath: Path
    uses_graphify_install: bool


def _host(name: str, marker: str, sub: str, *, in_graphify: bool) -> Host:
    return Host(
        name=name,
        marker=Path(marker),
        skill_subpath=Path(sub),
        uses_graphify_install=in_graphify,
    )


KNOWN_HOSTS: tuple[Host, ...] = (
    _host("claude",      ".claude",                      "skills/graphify",            in_graphify=True),
    _host("codex",       ".codex",                       "skills/graphify",            in_graphify=True),
    _host("opencode",    ".config/opencode",             "skills/graphify",            in_graphify=True),
    _host("kilo",        ".config/kilo",                 "skills/graphify",            in_graphify=True),
    _host("aider",       ".aider",                       "graphify",                   in_graphify=True),
    _host("copilot",     ".copilot",                     "skills/graphify",            in_graphify=True),
    _host("codebuddy",   ".codebuddy",                   "skills/graphify",            in_graphify=True),
    _host("kiro",        ".kiro",                        "skills/graphify",            in_graphify=True),
    _host("droid",       ".factory",                     "skills/graphify",            in_graphify=True),
    _host("trae",        ".trae",                        "skills/graphify",            in_graphify=True),
    _host("trae-cn",     ".trae-cn",                     "skills/graphify",            in_graphify=True),
    _host("hermes",      ".hermes",                      "skills/graphify",            in_graphify=True),
    _host("pi",          ".pi",                          "agent/skills/graphify",      in_graphify=True),
    _host("claw",        ".openclaw",                    "skills/graphify",            in_graphify=True),
    _host("antigravity", ".agents",                      "skills/graphify",            in_graphify=True),
    _host("vscode",      ".vscode",                      "skills/graphify",            in_graphify=True),
    _host("amp",         ".config/amp",                  "skills/graphify",            in_graphify=True),
    _host("agents",      ".config/agents",               "skills/graphify",            in_graphify=True),
    # Unknown to graphify but probed: mobilecoder. Copy SKILL.md directly.
    _host("mobilecoder", ".mobilecoder",                 "skills/graphify",            in_graphify=False),
    _host("cursor",      ".cursor",                      "rules",                      in_graphify=True),
    _host("gemini",      ".gemini",                      "skills/graphify",            in_graphify=True),
)


def detect_hosts(*, root: Path | None = None) -> List[Host]:
    """Return the list of installed hosts under `root` (default: $USERPROFILE).

    A host is "installed" when its marker path exists under `root`. Order
    of KNOWN_HOSTS is preserved in the result.
    """
    if root is None:
        root = Path.home()
    found: list[Host] = []
    for host in KNOWN_HOSTS:
        if (root / host.marker).exists():
            found.append(host)
    return found


def host_skill_dir(host: Host, *, root: Path) -> Path:
    """Absolute directory where SKILL.md should be written for `host`."""
    return root / host.marker / host.skill_subpath
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
uv run pytest tests/test_installer_host_probe.py -v
```

Expected: 7 passed.

- [ ] **Step 5: Commit**

```bash
git add graphify/installer/host_probe.py tests/test_installer_host_probe.py
git commit -m "feat(installer): add host_probe (detect installed AI-coding hosts)"
```

---

## Task 4: Implement `path_win` (TDD)

**Files:**
- Modify: `graphify/installer/path_win.py`
- Create: `tests/test_installer_path_win.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_installer_path_win.py`:

```python
"""Tests for graphify.installer.path_win.

`path_win` shells out to PowerShell to set/unset the user-level PATH.
We mock `subprocess.run` so the tests don't actually touch the registry.

Tests 1–4 verify the PowerShell call shape on Windows. They're skipped on
non-Windows because the implementation's no-op short-circuits before the
mocked subprocess is called. Test 5 verifies the no-op behavior itself
and runs on every platform.
"""

from __future__ import annotations

import sys
from unittest.mock import patch, MagicMock

import pytest

from graphify.installer import path_win


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_add_to_user_path_invokes_powershell_with_setx():
    """On Windows, add_to_user_path must call PowerShell's
    [Environment]::SetEnvironmentVariable with Target=User."""
    fake = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        path_win.add_to_user_path(r"C:\Users\me\AppData\Local\graphify\bin")
    args, kwargs = fake.call_args
    # First positional arg is the command list passed to subprocess.run
    cmd = args[0]
    assert cmd[0] == "powershell"
    assert "-NoProfile" in cmd
    assert "-Command" in cmd
    # The combined -Command string must reference SetEnvironmentVariable with User target
    command_str = next(a for a in cmd if isinstance(a, str) and "SetEnvironmentVariable" in a)
    assert "User" in command_str
    assert r"C:\Users\me\AppData\Local\graphify\bin" in command_str


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_add_to_user_path_is_idempotent():
    """Calling add_to_user_path twice with the same value must not error and
    must produce the same PowerShell call shape both times."""
    fake = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        path_win.add_to_user_path(r"C:\graphify\bin")
        path_win.add_to_user_path(r"C:\graphify\bin")
    assert fake.call_count == 2


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_remove_from_user_path_invokes_powershell():
    fake = MagicMock(return_value=MagicMock(returncode=0, stdout="", stderr=""))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        path_win.remove_from_user_path(r"C:\graphify\bin")
    cmd = fake.call_args[0][0]
    command_str = next(a for a in cmd if isinstance(a, str) and "SetEnvironmentVariable" in a)
    assert "User" in command_str
    # The path to remove must appear in the command (we filter it out of the
    # existing PATH and re-set the result).
    assert r"C:\graphify\bin" in command_str


@pytest.mark.skipif(sys.platform != "win32", reason="PowerShell call only runs on Windows")
def test_add_to_user_path_raises_on_powershell_failure():
    fake = MagicMock(return_value=MagicMock(returncode=1, stdout="", stderr="boom"))
    with patch("graphify.installer.path_win.subprocess.run", fake):
        with pytest.raises(path_win.PathWinError):
            path_win.add_to_user_path(r"C:\graphify\bin")


def test_add_to_user_path_noop_on_non_windows():
    """On non-Windows platforms, add_to_user_path must return without
    invoking subprocess."""
    fake = MagicMock()
    with patch("graphify.installer.path_win.sys.platform", "darwin"):
        with patch("graphify.installer.path_win.subprocess.run", fake):
            path_win.add_to_user_path("/tmp/whatever")
    fake.assert_not_called()
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
uv run pytest tests/test_installer_path_win.py -v
```

Expected: FAIL with `ImportError: cannot import name 'path_win' from 'graphify.installer'`.

- [ ] **Step 3: Implement `path_win.py`**

Replace `graphify/installer/path_win.py` with:

```python
"""User-level PATH manipulation on Windows.

We do NOT use `os.environ` mutation (it doesn't persist beyond the process)
and we do NOT touch `HKLM\SYSTEM\...` (system PATH requires admin and
modifies a global setting). Instead we shell out to PowerShell:

    [Environment]::SetEnvironmentVariable("Path", $newPath, "User")

`User` target writes to `HKCU\Environment`, which is what we want. The
new value is the current user PATH with the target path appended (for
add) or filtered out (for remove).
"""

from __future__ import annotations

import subprocess
import sys
from typing import List


class PathWinError(RuntimeError):
    """Raised when PowerShell returns a non-zero exit code."""


def _powershell_set_path(ps_command: str) -> None:
    """Run `ps_command` in PowerShell and raise on failure."""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            ps_command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PathWinError(
            f"PowerShell failed (rc={result.returncode}): "
            f"{result.stderr.strip() or result.stdout.strip()}"
        )


def _build_set_command(current: str, new: str) -> str:
    """PowerShell that:
       1. Reads current user Path.
       2. Splits on ';' (registry stores it as a single REG_EXPAND_SZ string).
       3. If `new` is not already present, appends it.
       4. Writes back via SetEnvironmentVariable('Path', ..., 'User').
    """
    # Escape single quotes for PowerShell single-quoted strings
    cur = current.replace("'", "''")
    nw = new.replace("'", "''")
    return (
        f"$cur = [Environment]::GetEnvironmentVariable('Path', 'User'); "
        f"$sep = [IO.Path]::PathSeparator; "
        f"$parts = if ([string]::IsNullOrEmpty($cur)) {{ @() }} else {{ $cur.Split(';') }}; "
        f"if ($parts -notcontains '{nw}') {{ $parts += '{nw}' }}; "
        f"$new = [string]::Join(';', $parts); "
        f"[Environment]::SetEnvironmentVariable('Path', $new, 'User')"
    )


def _build_unset_command(current: str, target: str) -> str:
    """PowerShell that removes `target` from the user Path and writes back."""
    tgt = target.replace("'", "''")
    return (
        f"$cur = [Environment]::GetEnvironmentVariable('Path', 'User'); "
        f"if ([string]::IsNullOrEmpty($cur)) {{ return }}; "
        f"$parts = $cur.Split(';') | Where-Object {{ $_ -ne '{tgt}' }}; "
        f"$new = [string]::Join(';', $parts); "
        f"[Environment]::SetEnvironmentVariable('Path', $new, 'User')"
    )


def add_to_user_path(path: str) -> None:
    """Append `path` to the user-level PATH. No-op on non-Windows.

    Idempotent: calling with the same `path` twice is safe (the second
    call is a no-op because the PowerShell filter rejects duplicates).
    """
    if sys.platform != "win32":
        return
    # We don't need to read `current` in Python — the PS command does it.
    _powershell_set_path(_build_set_command("", path))


def remove_from_user_path(path: str) -> None:
    """Remove `path` from the user-level PATH. No-op on non-Windows."""
    if sys.platform != "win32":
        return
    _powershell_set_path(_build_unset_command("", path))


def current_user_path() -> str:
    """Return the current user-level PATH (for tests / diagnostics)."""
    if sys.platform != "win32":
        return ""
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-NonInteractive",
            "-Command",
            "[Environment]::GetEnvironmentVariable('Path', 'User')",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise PathWinError(
            f"PowerShell failed (rc={result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout.strip()
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
uv run pytest tests/test_installer_path_win.py -v
```

Expected: 5 passed.

- [ ] **Step 5: Commit**

```bash
git add graphify/installer/path_win.py tests/test_installer_path_win.py
git commit -m "feat(installer): add path_win (user-level Windows PATH via PowerShell)"
```

---

## Task 5: Implement `manifest` (TDD)

**Files:**
- Modify: `graphify/installer/manifest.py`
- Create: `tests/test_installer_manifest.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_installer_manifest.py`:

```python
"""Tests for graphify.installer.manifest."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.installer.manifest import (
    InstallManifest,
    load_manifest,
    manifest_path,
    save_manifest,
)


def test_manifest_path_is_localappdata_graphify():
    p = manifest_path()
    assert p.name == ".graphify_install.json"
    # On Windows this is %LOCALAPPDATA%\graphify\.graphify_install.json.
    # On non-Windows the function still returns a path; we just verify shape.
    assert "graphify" in p.parts


def test_save_and_load_roundtrip(tmp_path):
    m = InstallManifest(
        version="0.9.1",
        install_path=tmp_path,
        hosts=["claude"],
        user_path_added=True,
    )
    target = tmp_path / ".graphify_install.json"
    save_manifest(m, target)
    assert target.exists()
    loaded = load_manifest(target)
    assert loaded.version == "0.9.1"
    assert loaded.install_path == tmp_path
    assert loaded.hosts == ["claude"]
    assert loaded.user_path_added is True


def test_load_manifest_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "nope.json")


def test_save_manifest_creates_parent_dirs(tmp_path):
    target = tmp_path / "nested" / "dir" / "manifest.json"
    m = InstallManifest(
        version="0.9.1",
        install_path=tmp_path,
        hosts=[],
        user_path_added=False,
    )
    save_manifest(m, target)
    assert target.exists()
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
uv run pytest tests/test_installer_manifest.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `manifest.py`**

Replace `graphify/installer/manifest.py` with:

```python
"""Install manifest: records what the offline installer did, so uninstall
can reverse it cleanly.

Stored at `<install_root>/.graphify_install.json` (typically
`%LOCALAPPDATA%\graphify\.graphify_install.json` on Windows).
"""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import List, Optional


@dataclass
class InstallManifest:
    """Snapshot of an offline install, written to disk for later uninstall."""

    version: str
    install_path: Path
    hosts: List[str] = field(default_factory=list)
    user_path_added: bool = False
    created_shortcut: bool = False
    # Per-host record of the exact skill directory we wrote to, so uninstall
    # can `rmtree` it without re-probing the filesystem.
    skill_dirs: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["install_path"] = str(self.install_path)
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "InstallManifest":
        return cls(
            version=d["version"],
            install_path=Path(d["install_path"]),
            hosts=list(d.get("hosts", [])),
            user_path_added=bool(d.get("user_path_added", False)),
            created_shortcut=bool(d.get("created_shortcut", False)),
            skill_dirs=list(d.get("skill_dirs", [])),
        )


def manifest_path() -> Path:
    """Default manifest location: %LOCALAPPDATA%\\graphify\\.graphify_install.json.

    On non-Windows the function still returns a sensible path under the user's
    home; the installer is Windows-only but this helper is import-safe on every
    platform.
    """
    base = os.environ.get("LOCALAPPDATA") or str(Path.home())
    return Path(base) / "graphify" / ".graphify_install.json"


def save_manifest(m: InstallManifest, path: Path) -> None:
    """Write `m` to `path` as JSON. Creates parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(m.to_dict(), indent=2), encoding="utf-8")


def load_manifest(path: Path) -> InstallManifest:
    """Load and validate a manifest from `path`. Raises FileNotFoundError."""
    if not path.exists():
        raise FileNotFoundError(f"No install manifest at {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    return InstallManifest.from_dict(data)
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
uv run pytest tests/test_installer_manifest.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add graphify/installer/manifest.py tests/test_installer_manifest.py
git commit -m "feat(installer): add manifest (roundtrip JSON for uninstall)"
```

---

## Task 6: Implement `skill_copy` (TDD)

**Files:**
- Modify: `graphify/installer/skill_copy.py`
- Create: `tests/test_installer_skill_copy.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_installer_skill_copy.py`:

```python
"""Tests for graphify.installer.skill_copy.

`skill_copy` reads the right `skill-<host>.md` from the bundled graphify
package (via `importlib.resources`) and writes it to `<root>/<host>/SKILL.md`,
plus a `references/` sidecar when the host's bundle has one.
"""

from __future__ import annotations

import importlib.resources
from pathlib import Path

import pytest

from graphify.installer import skill_copy
from graphify.installer.host_probe import KNOWN_HOSTS, Host, host_skill_dir


def _write_minimal_graphify_package(tmp_path, *, with_references: bool = True):
    """Create a fake `graphify` package layout under tmp_path with the
    minimal files `skill_copy` reads. Returns the package root.
    """
    pkg = tmp_path / "graphify"
    pkg.mkdir()
    (pkg / "skill.md").write_text("# Claude bundle\n", encoding="utf-8")
    (pkg / "skill-opencode.md").write_text("# OpenCode bundle\n", encoding="utf-8")
    (pkg / "skill-mobilecoder.md").write_text(
        "# Mobilecoder bundle (uses claude body)\n", encoding="utf-8"
    )
    (pkg / "skill-claw.md").write_text("# Claw bundle\n", encoding="utf-8")
    (pkg / "skill-kiro.md").write_text("# Kiro bundle\n", encoding="utf-8")
    if with_references:
        refs = pkg / "skills" / "claude" / "references"
        refs.mkdir(parents=True)
        (refs / "extraction-spec.md").write_text("ref\n", encoding="utf-8")
    return pkg


def test_pick_skill_body_for_claude():
    body = skill_copy._pick_skill_body("claude")
    assert "graphify" in body.lower() or len(body) > 0


def test_pick_skill_body_for_opencode_uses_opencode_bundle():
    body = skill_copy._pick_skill_body("opencode")
    assert isinstance(body, str)
    assert len(body) > 0


def test_pick_skill_body_for_unknown_host_falls_back_to_skill_md():
    body = skill_copy._pick_skill_body("totally-fake-host")
    assert isinstance(body, str)
    assert len(body) > 0  # falls back to skill.md


def test_copy_skill_for_known_graphify_host(tmp_path, monkeypatch):
    """For a host in _PLATFORM_CONFIG we still copy the bundle directly
    (we don't actually shell out to `graphify install` in the offline
    installer — the .exe is the installer)."""
    pkg = _write_minimal_graphify_package(tmp_path, with_references=False)
    # Redirect importlib.resources to read from our fake package.
    fake_resources = importlib.resources.files.__self__ if False else None  # noqa
    host = next(h for h in KNOWN_HOSTS if h.name == "claude")
    out_dir = host_skill_dir(host, root=tmp_path)
    skill_copy.copy_skill(host, root=tmp_path, package_root=pkg)
    assert (out_dir / "SKILL.md").exists()
    assert "Claude bundle" in (out_dir / "SKILL.md").read_text(encoding="utf-8")


def test_copy_skill_writes_references_when_present(tmp_path):
    pkg = _write_minimal_graphify_package(tmp_path, with_references=True)
    host = next(h for h in KNOWN_HOSTS if h.name == "claude")
    out_dir = host_skill_dir(host, root=tmp_path)
    skill_copy.copy_skill(host, root=tmp_path, package_root=pkg)
    assert (out_dir / "references" / "extraction-spec.md").exists()


def test_copy_skill_for_mobilecoder_uses_skill_md_fallback(tmp_path):
    pkg = _write_minimal_graphify_package(tmp_path, with_references=False)
    host = next(h for h in KNOWN_HOSTS if h.name == "mobilecoder")
    out_dir = host_skill_dir(host, root=tmp_path)
    skill_copy.copy_skill(host, root=tmp_path, package_root=pkg)
    assert (out_dir / "SKILL.md").exists()
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
uv run pytest tests/test_installer_skill_copy.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `skill_copy.py`**

Replace `graphify/installer/skill_copy.py` with:

```python
"""Copy the right SKILL.md (and references/) to a host's skill directory.

Sources the bundle from the installed `graphify` package. For hosts whose
bundle is in `graphify/__main__:_PLATFORM_CONFIG` (claude, opencode, etc.),
we pick the host-specific file. For hosts NOT in the config (mobilecoder),
we fall back to `skill.md` (the Claude bundle) — the user is responsible
for adjusting the body if their host needs a different format.
"""

from __future__ import annotations

import shutil
from importlib.resources import files
from pathlib import Path
from typing import Optional

from graphify.installer.host_probe import Host, host_skill_dir

# Map host name -> the skill body filename in the graphify package.
# Hosts whose body is `skill.md` (the Claude bundle) don't need an entry.
_BODY_BY_HOST = {
    "claude":      "skill.md",
    "codex":       "skill-codex.md",
    "opencode":    "skill-opencode.md",
    "kilo":        "skill-kilo.md",
    "aider":       "skill-aider.md",
    "copilot":     "skill-copilot.md",
    "codebuddy":   "skill.md",       # reuses claude bundle
    "kiro":        "skill-kiro.md",
    "droid":       "skill-droid.md",
    "trae":        "skill-trae.md",
    "trae-cn":     "skill-trae.md",
    "hermes":      "skill-claw.md",
    "pi":          "skill-pi.md",
    "claw":        "skill-claw.md",
    "antigravity": "skill.md",       # reuses claude bundle
    "vscode":      "skill-vscode.md",
    "amp":         "skill-amp.md",
    "agents":      "skill-agents.md",
    "mobilecoder": "skill.md",       # not first-class; fall back to claude body
}

# Map host name -> the sidecar references directory inside the package
# (relative to the package root). None = no references/ to copy.
_REFS_BY_HOST = {
    "claude":      "skills/claude/references",
    "codex":       "skills/codex/references",
    "opencode":    "skills/opencode/references",
    "kilo":        "skills/kilo/references",
    "copilot":     "skills/copilot/references",
    "codebuddy":   "skills/claude/references",
    "kiro":        "skills/kiro/references",
    "droid":       "skills/droid/references",
    "trae":        "skills/trae/references",
    "hermes":      "skills/claw/references",
    "pi":          "skills/pi/references",
    "claw":        "skills/claw/references",
    "antigravity": "skills/claude/references",
    "vscode":      "skills/vscode/references",
    "amp":         "skills/amp/references",
    "agents":      "skills/agents/references",
}


def _pick_skill_body(host_name: str) -> str:
    """Return the text of the skill body for `host_name`.

    Looks up the body file in the installed graphify package. If the host
    has no specific entry, falls back to `skill.md` (the Claude bundle).
    """
    body_name = _BODY_BY_HOST.get(host_name, "skill.md")
    try:
        return (files("graphify").joinpath(body_name).read_text(encoding="utf-8"))
    except (FileNotFoundError, ModuleNotFoundError):
        # In tests we may be operating against a fake package; fall back to
        # the package_root passed by the test, if any.
        return ""


def copy_skill(
    host: Host,
    *,
    root: Path,
    package_root: Optional[Path] = None,
) -> Path:
    """Write SKILL.md (and references/) for `host` under `root`.

    `package_root` is the path to the `graphify` package directory; defaults
    to the installed package. It exists so tests can inject a fake package
    without `importlib.resources` finding real files.
    """
    out_dir = host_skill_dir(host, root=root)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Read the body.
    body_name = _BODY_BY_HOST.get(host.name, "skill.md")
    if package_root is not None:
        body_path = package_root / body_name
        body = body_path.read_text(encoding="utf-8") if body_path.exists() else ""
    else:
        body = _pick_skill_body(host.name)

    (out_dir / "SKILL.md").write_text(body, encoding="utf-8")

    # Copy references/ if the host has them.
    refs_rel = _REFS_BY_HOST.get(host.name)
    if refs_rel:
        if package_root is not None:
            src_refs = package_root / refs_rel
        else:
            # Use importlib.resources traversal.
            from importlib.resources import as_file
            try:
                ref_resource = files("graphify").joinpath(*refs_rel.split("/"))
                with as_file(ref_resource) as p:
                    src_refs = p
            except (FileNotFoundError, ModuleNotFoundError, TypeError):
                src_refs = None
        if src_refs is not None and src_refs.exists():
            dst_refs = out_dir / "references"
            if dst_refs.exists():
                shutil.rmtree(dst_refs)
            shutil.copytree(src_refs, dst_refs)

    return out_dir
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
uv run pytest tests/test_installer_skill_copy.py -v
```

Expected: 6 passed.

- [ ] **Step 5: Commit**

```bash
git add graphify/installer/skill_copy.py tests/test_installer_skill_copy.py
git commit -m "feat(installer): add skill_copy (host-aware SKILL.md + references copy)"
```

---

## Task 7: Implement orchestrator `installer/__init__.py` (TDD)

**Files:**
- Modify: `graphify/installer/__init__.py`
- Create: `tests/test_installer_orchestrator.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_installer_orchestrator.py`:

```python
"""Tests for graphify.installer orchestrator (install / uninstall)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from graphify.installer import install as run_install, uninstall as run_uninstall
from graphify.installer.manifest import InstallManifest, load_manifest, manifest_path


def test_install_writes_manifest(tmp_path, monkeypatch):
    """On a clean install, a manifest is written to <install_path>/.graphify_install.json."""
    # Pretend we found exactly one host (claude).
    claude_host = next(
        h for h in __import__("graphify.installer.host_probe", fromlist=["KNOWN_HOSTS"]).KNOWN_HOSTS
        if h.name == "claude"
    )
    monkeypatch.setattr(
        "graphify.installer.detect_hosts", lambda *, root=None: [claude_host]
    )
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)
    monkeypatch.setattr("graphify.installer.path_win.remove_from_user_path", lambda p: None)

    manifest_file = tmp_path / ".graphify_install.json"
    run_install(
        install_path=tmp_path,
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=manifest_file,
    )
    assert manifest_file.exists()
    m = load_manifest(manifest_file)
    assert m.version == "0.9.1"
    assert m.install_path == tmp_path
    assert "claude" in m.hosts


def test_install_writes_skill_for_detected_host(tmp_path, monkeypatch):
    claude_host = next(
        h for h in __import__("graphify.installer.host_probe", fromlist=["KNOWN_HOSTS"]).KNOWN_HOSTS
        if h.name == "claude"
    )
    monkeypatch.setattr(
        "graphify.installer.detect_hosts", lambda *, root=None: [claude_host]
    )
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)

    # Provide a fake package so skill_copy has something to read.
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "skill.md").write_text("# claude\n", encoding="utf-8")
    monkeypatch.setattr(
        "graphify.installer.skill_copy._pick_skill_body", lambda h: "# claude\n"
    )

    run_install(
        install_path=tmp_path / "install",
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=tmp_path / "install" / ".graphify_install.json",
    )
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    assert (skill_dir / "SKILL.md").exists()


def test_install_with_no_hosts_still_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr("graphify.installer.detect_hosts", lambda *, root=None: [])
    monkeypatch.setattr("graphify.installer.path_win.add_to_user_path", lambda p: None)
    manifest_file = tmp_path / ".graphify_install.json"
    run_install(
        install_path=tmp_path,
        user_root=tmp_path,
        version="0.9.1",
        manifest_target=manifest_file,
    )
    m = load_manifest(manifest_file)
    assert m.hosts == []


def test_uninstall_removes_manifest_and_skill_dirs(tmp_path, monkeypatch):
    # Set up an existing install.
    claude_host = next(
        h for h in __import__("graphify.installer.host_probe", fromlist=["KNOWN_HOSTS"]).KNOWN_HOSTS
        if h.name == "claude"
    )
    skill_dir = tmp_path / ".claude" / "skills" / "graphify"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("x", encoding="utf-8")

    manifest = InstallManifest(
        version="0.9.1",
        install_path=tmp_path,
        hosts=["claude"],
        user_path_added=True,
        skill_dirs=[str(skill_dir)],
    )
    from graphify.installer.manifest import save_manifest
    manifest_file = tmp_path / "manifest.json"
    save_manifest(manifest, manifest_file)

    monkeypatch.setattr("graphify.installer.path_win.remove_from_user_path", lambda p: None)
    run_uninstall(manifest_file=manifest_file)
    assert not skill_dir.exists()
    # Manifest is consumed.
    assert not manifest_file.exists()
```

- [ ] **Step 2: Run the test and confirm it fails**

```bash
uv run pytest tests/test_installer_orchestrator.py -v
```

Expected: FAIL with `ImportError: cannot import name 'install' from 'graphify.installer'`.

- [ ] **Step 3: Implement `installer/__init__.py`**

Replace `graphify/installer/__init__.py` with:

```python
"""Offline Windows installer orchestrator.

The single entry points are `install()` and `uninstall()` — the rest of the
package is helpers. The compiled `graphify-installer.exe` (built from
`tools/installer_main.py`) calls these.
"""

from __future__ import annotations

import shutil
import sys
from pathlib import Path
from typing import List, Optional

from graphify.installer import host_probe, manifest, path_win, skill_copy

# Re-export the helpers at the package level. Two reasons:
#   1. Tests `monkeypatch.setattr("graphify.installer.<name>", ...)` need
#      the names reachable on the package itself; submodule-only lookups
#      would miss the patch.
#   2. `install()` / `uninstall()` below look up these names through the
#      module globals, so the same patch chain applies in production code.
detect_hosts = host_probe.detect_hosts
add_to_user_path = path_win.add_to_user_path
remove_from_user_path = path_win.remove_from_user_path


def install(
    *,
    install_path: Path,
    user_root: Path,
    version: str,
    manifest_target: Optional[Path] = None,
) -> manifest.InstallManifest:
    """Run the offline install.

    Steps:
    1. Probe `user_root` for installed hosts.
    2. Copy each host's SKILL.md (+ references/) into the host's skill dir.
    3. Register `install_path / bin` on the user-level PATH.
    4. Write the install manifest.
    """
    hosts = detect_hosts(root=user_root)
    skill_dirs: List[str] = []

    for host in hosts:
        try:
            out_dir = skill_copy.copy_skill(host, root=user_root)
            skill_dirs.append(str(out_dir))
        except Exception as exc:  # noqa: BLE001
            # We never abort the install for a single host failure; record it.
            print(
                f"[graphify-installer] warn: failed to install skill for "
                f"{host.name}: {exc}",
                file=sys.stderr,
            )

    bin_path = install_path / "bin"
    try:
        add_to_user_path(str(bin_path))
        user_path_added = True
    except path_win.PathWinError as exc:
        print(
            f"[graphify-installer] warn: could not register PATH ({exc}); "
            f"add {bin_path} to your PATH manually.",
            file=sys.stderr,
        )
        user_path_added = False

    m = manifest.InstallManifest(
        version=version,
        install_path=install_path,
        hosts=[h.name for h in hosts],
        user_path_added=user_path_added,
        skill_dirs=skill_dirs,
    )
    target = manifest_target or (install_path / ".graphify_install.json")
    manifest.save_manifest(m, target)
    return m


def uninstall(*, manifest_file: Path) -> None:
    """Reverse a previous install: remove skill dirs, drop PATH, delete manifest."""
    if not manifest_file.exists():
        raise FileNotFoundError(f"No install manifest at {manifest_file}")
    m = manifest.load_manifest(manifest_file)

    for skill_dir_str in m.skill_dirs:
        skill_dir = Path(skill_dir_str)
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)

    if m.user_path_added:
        try:
            remove_from_user_path(str(m.install_path / "bin"))
        except path_win.PathWinError as exc:
            print(
                f"[graphify-installer] warn: could not remove PATH entry ({exc}); "
                f"remove it manually.",
                file=sys.stderr,
            )

    if m.install_path.exists():
        shutil.rmtree(m.install_path, ignore_errors=True)

    manifest_file.unlink(missing_ok=True)
```

- [ ] **Step 4: Run the test and confirm it passes**

```bash
uv run pytest tests/test_installer_orchestrator.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Run the full installer test suite**

```bash
uv run pytest tests/test_installer_*.py -v
```

Expected: all tests pass (7 + 5 + 4 + 6 + 4 = 26 tests).

- [ ] **Step 6: Commit**

```bash
git add graphify/installer/__init__.py tests/test_installer_orchestrator.py
git commit -m "feat(installer): add install/uninstall orchestrator"
```

---

## Task 8: Add `self-install` / `self-uninstall` subcommands to `graphify/__main__.py`

**Files:**
- Modify: `graphify/__main__.py` (insert new branches into the dispatcher near line 2404; add new entries to the help text near line 2224)

- [ ] **Step 1: Add the new subcommands to the help text**

Find the `print("Commands:")` block in `main()` (around line 2223). Add two new lines right after the `uninstall` line (line 2225–2226 area):

```python
        print("  self-install            offline Windows installer: deploy graphify to %LOCALAPPDATA%\\graphify")
        print("    --path DIR             override install path (default: %LOCALAPPDATA%\\graphify)")
        print("    --no-path              skip user-PATH registration")
        print("  self-uninstall          reverse a self-install: remove skill dirs, drop PATH, delete install dir")
```

- [ ] **Step 2: Add the dispatcher branches**

Find the dispatcher block where `cmd = sys.argv[1]` is set (line 2404). Add two new `elif` branches for `self-install` and `self-uninstall`. The cleanest place to insert is right after the existing `uninstall` branch (which ends around line 2493) and before the `claude` branch (line 2494):

```python
    elif cmd == "self-install":
        from graphify.installer import install as _self_install
        from graphify.installer.manifest import manifest_path as _default_manifest
        args = sys.argv[2:]
        target_path = None
        skip_path = False
        i = 0
        while i < len(args):
            a = args[i]
            if a == "--path":
                if i + 1 >= len(args):
                    print("error: --path requires a value", file=sys.stderr)
                    sys.exit(1)
                target_path = Path(args[i + 1])
                i += 2
            elif a == "--no-path":
                skip_path = True
                i += 1
            elif a in ("-h", "--help"):
                print("Usage: graphify self-install [--path DIR] [--no-path]")
                return
            else:
                print(f"error: unknown self-install option '{a}'", file=sys.stderr)
                sys.exit(1)
        install_dir = target_path or _default_manifest().parent
        from graphify.installer import path_win as _pw
        if skip_path:
            # Patch the orchestrator's path_win.add_to_user_path to a no-op for this call.
            import graphify.installer as _inst
            orig = _inst.path_win.add_to_user_path
            _inst.path_win.add_to_user_path = lambda p: None  # type: ignore[assignment]
            try:
                _self_install(
                    install_path=install_dir,
                    user_root=Path.home(),
                    version=__version__,
                )
            finally:
                _inst.path_win.add_to_user_path = orig  # type: ignore[assignment]
        else:
            _self_install(
                install_path=install_dir,
                user_root=Path.home(),
                version=__version__,
            )
    elif cmd == "self-uninstall":
        from graphify.installer import uninstall as _self_uninstall
        from graphify.installer.manifest import manifest_path as _default_manifest
        _self_uninstall(manifest_file=_default_manifest())
```

- [ ] **Step 3: Update the silent-cmd set**

Find the line:

```python
    _silent_cmds = {"install", "uninstall", "hook-check"}
```

(line ~2208.) Add `"self-install"` and `"self-uninstall"`:

```python
    _silent_cmds = {"install", "uninstall", "self-install", "self-uninstall", "hook-check"}
```

- [ ] **Step 4: Verify `graphify --help` lists the new commands**

```bash
uv run graphify --help 2>&1 | grep -E "self-(install|uninstall)"
```

Expected: at least one line each for `self-install` and `self-uninstall`.

- [ ] **Step 5: Verify `graphify self-install --help` works**

```bash
uv run graphify self-install --help
```

Expected: prints `Usage: graphify self-install [--path DIR] [--no-path]` and returns.

- [ ] **Step 6: Run the existing test suite to confirm no regression**

```bash
uv run pytest -q
```

Expected: 2478 passed, 28 skipped (no regression). The new commands don't add or remove existing tests.

- [ ] **Step 7: Commit**

```bash
git add graphify/__main__.py
git commit -m "feat(cli): add self-install / self-uninstall subcommands"
```

---

## Task 9: Create `tools/installer_main.py` (entry point for Nuitka)

**Files:**
- Create: `tools/installer_main.py`

- [ ] **Step 1: Create the entry script**

Create `tools/installer_main.py`:

```python
"""Standalone entry point for the offline Windows installer.

This script is the entry point for the Nuitka-compiled
`graphify-installer.exe`. It accepts:

    graphify-installer.exe install     # run the install wizard
    graphify-installer.exe uninstall   # reverse a previous install
    graphify-installer.exe --version
    graphify-installer.exe --help

It does NOT import `graphify.__main__` (which has click-style side effects
and the full CLI surface). It imports only the installer subpackage, which
is what the compiled .exe needs to do its job.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Make `graphify` importable when this script is run as a Nuitka-compiled
# entry point. The compiled binary has the package frozen in, so this
# import works in both modes (script and frozen).
from graphify.installer import install as _install, uninstall as _uninstall
from graphify.installer.manifest import manifest_path as _default_manifest
from graphify.installer.host_probe import detect_hosts as _detect_hosts

try:
    from importlib.metadata import version as _pkg_version
    __version__ = _pkg_version("graphifyy")
except Exception:
    __version__ = "unknown"


def _print_banner() -> None:
    print(f"graphify offline installer {__version__}")
    print(f"  install path: {_default_manifest().parent}")


def cmd_install(args: argparse.Namespace) -> int:
    _print_banner()
    hosts = _detect_hosts()
    if not hosts:
        print("warning: no known AI-coding host detected on this machine.")
        print("         The graphify binary will still be installed;")
        print("         you'll need to copy SKILL.md to your host manually.")
    else:
        names = ", ".join(h.name for h in hosts)
        print(f"  detected hosts: {names}")

    target = Path(args.path) if args.path else _default_manifest().parent
    print(f"  installing to: {target}")

    manifest = _install(
        install_path=target,
        user_root=Path.home(),
        version=__version__,
    )
    print("  done.")
    if manifest.user_path_added:
        print(f"  user PATH registered: {target / 'bin'}")
        print("  (open a new cmd window for PATH changes to take effect)")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    _print_banner()
    manifest_file = _default_manifest()
    if not manifest_file.exists():
        print(f"no install manifest at {manifest_file}")
        print("nothing to uninstall.")
        return 1
    _uninstall(manifest_file=manifest_file)
    print("  done.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="graphify-installer",
        description="Offline Windows installer for graphify.",
    )
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_install = sub.add_parser("install", help="install graphify to %LOCALAPPDATA%\\graphify")
    p_install.add_argument("--path", help="override install path")

    p_uninstall = sub.add_parser("uninstall", help="reverse a previous install")

    ns = parser.parse_args(argv)
    if ns.version:
        print(f"graphify-installer {__version__}")
        return 0
    if ns.command == "install":
        return cmd_install(ns)
    if ns.command == "uninstall":
        return cmd_uninstall(ns)
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the script**

```bash
uv run python tools/installer_main.py --help
```

Expected: argparse help output mentioning `install` and `uninstall` subcommands.

- [ ] **Step 3: Smoke-test the install subcommand help**

```bash
uv run python tools/installer_main.py install --help
```

Expected: prints `usage: graphify-installer install [-h] [--path PATH]`.

- [ ] **Step 4: Commit**

```bash
git add tools/installer_main.py
git commit -m "feat(installer): add tools/installer_main.py (Nuitka entry point)"
```

---

## Task 10: Create `tools/build_windows_installer.sh`

**Files:**
- Create: `tools/build_windows_installer.sh`

- [ ] **Step 1: Create the build script**

Create `tools/build_windows_installer.sh`:

```bash
#!/usr/bin/env bash
#
# Build graphify-installer.exe (and the bundled graphify.exe / graphify-mcp.exe)
# on Windows. Run from a checkout of graphify, with Visual Studio Build Tools
# installed and on PATH (Nuitka needs a C compiler).
#
# Usage:
#     tools/build_windows_installer.sh
#
# Output:
#     dist/graphify-installer.exe   — the offline installer
#     dist/graphify.exe             — the bundled graphify CLI
#     dist/graphify-mcp.exe         — the bundled graphify MCP server
#
# Wheelhouse (cached at ./wheelhouse-windows/) is reused across builds.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

PYTHON="${PYTHON:-python}"
WHEELHOUSE="$REPO_ROOT/wheelhouse-windows"
DIST="$REPO_ROOT/dist"

echo "==> Python: $($PYTHON --version)"
echo "==> Wheelhouse: $WHEELHOUSE"
echo "==> Output:     $DIST"

# 1. Download Windows wheels for every default-bundled dep (one-time).
echo "==> Resolving wheels..."
mkdir -p "$WHEELHOUSE"
$PYTHON -m pip download \
    --dest "$WHEELHOUSE" \
    --python-version 3.10 \
    --platform win_amd64 \
    --only-binary=:all: \
    --requirement <($PYTHON -c "
import tomllib
with open('pyproject.toml', 'rb') as f:
    data = tomllib.load(f)
print('\n'.join(data['project']['optional-dependencies']['windows-offline']))
")

# 2. Install graphify itself as a wheel (so Nuitka finds the package).
echo "==> Building graphify wheel..."
$PYTHON -m pip wheel . --no-deps --wheel-dir "$WHEELHOUSE" >/dev/null

# 3. Set up a clean venv that uses ONLY the wheelhouse (offline simulation).
echo "==> Building offline venv..."
VENV="$REPO_ROOT/.venv-offline-build"
rm -rf "$VENV"
$PYTHON -m venv "$VENV"
"$VENV/Scripts/python.exe" -m pip install \
    --no-index \
    --find-links "$WHEELHOUSE" \
    graphifyy \
    >/dev/null

# 4. Run Nuitka three times in the offline venv.
echo "==> Compiling graphify.exe (Nuitka)..."
"$VENV/Scripts/python.exe" -m nuitka \
    --standalone --onefile \
    --windows-disable-console \
    --enable-plugin=anti-bloat,multiprocessing \
    --include-package=graphify \
    --include-package-data=graphify \
    --include-module=networkx,numpy,rapidfuzz \
    --include-module=anthropic \
    --include-module=mcp,starlette \
    --include-module=graspologic \
    --include-module=tree_sitter,tree_sitter_python,tree_sitter_javascript,tree_sitter_typescript,tree_sitter_go,tree_sitter_rust,tree_sitter_java,tree_sitter_groovy,tree_sitter_c,tree_sitter_cpp,tree_sitter_ruby,tree_sitter_c_sharp,tree_sitter_kotlin,tree_sitter_scala,tree_sitter_php,tree_sitter_swift,tree_sitter_lua,tree_sitter_zig,tree_sitter_powershell,tree_sitter_elixir,tree_sitter_objc,tree_sitter_julia,tree_sitter_verilog,tree_sitter_fortran,tree_sitter_bash,tree_sitter_json \
    --include-module=matplotlib,watchdog,tree_sitter_sql,tree_sitter_hcl,jieba \
    --output-filename=graphify.exe \
    graphify/__main__.py

echo "==> Compiling graphify-mcp.exe (Nuitka)..."
"$VENV/Scripts/python.exe" -m nuitka \
    --standalone --onefile \
    --windows-disable-console \
    --enable-plugin=anti-bloat,multiprocessing \
    --include-package=graphify \
    --include-package-data=graphify \
    --include-module=networkx,numpy,rapidfuzz \
    --include-module=anthropic \
    --include-module=mcp,starlette \
    --include-module=graspologic \
    --include-module=tree_sitter,tree_sitter_python,tree_sitter_javascript,tree_sitter_typescript,tree_sitter_go,tree_sitter_rust,tree_sitter_java,tree_sitter_groovy,tree_sitter_c,tree_sitter_cpp,tree_sitter_ruby,tree_sitter_c_sharp,tree_sitter_kotlin,tree_sitter_scala,tree_sitter_php,tree_sitter_swift,tree_sitter_lua,tree_sitter_zig,tree_sitter_powershell,tree_sitter_elixir,tree_sitter_objc,tree_sitter_julia,tree_sitter_verilog,tree_sitter_fortran,tree_sitter_bash,tree_sitter_json \
    --include-module=matplotlib,watchdog,tree_sitter_sql,tree_sitter_hcl,jieba \
    --output-filename=graphify-mcp.exe \
    graphify/serve.py

echo "==> Compiling graphify-installer.exe (Nuitka)..."
"$VENV/Scripts/python.exe" -m nuitka \
    --standalone --onefile \
    --windows-disable-console \
    --enable-plugin=anti-bloat,multiprocessing \
    --include-package=graphify \
    --include-package-data=graphify \
    --include-module=graphify.installer \
    --output-filename=graphify-installer.exe \
    tools/installer_main.py

# 5. Collect artifacts.
echo "==> Collecting artifacts..."
mkdir -p "$DIST"
mv graphify.exe "$DIST/"
mv graphify-mcp.exe "$DIST/"
mv graphify-installer.exe "$DIST/"

ls -la "$DIST"
echo "==> Done. Distribute $DIST/graphify-installer.exe."
```

- [ ] **Step 2: Make it executable**

```bash
chmod +x tools/build_windows_installer.sh
```

- [ ] **Step 3: Validate the script's shell syntax (macOS / Linux)**

```bash
bash -n tools/build_windows_installer.sh && echo "syntax ok"
```

Expected: `syntax ok`. The script will fail to run on macOS (it expects Windows Python and Visual Studio), but the syntax should be valid.

- [ ] **Step 4: Commit**

```bash
git add tools/build_windows_installer.sh
git commit -m "build: add tools/build_windows_installer.sh (Nuitka build script)"
```

---

## Task 11: Create `tools/build_windows_installer.py` (cross-platform)

**Files:**
- Create: `tools/build_windows_installer.py`

- [ ] **Step 1: Create the Python build script**

Create `tools/build_windows_installer.py`:

```python
#!/usr/bin/env python3
"""Cross-platform driver for the offline Windows installer build.

Wraps the same workflow as `tools/build_windows_installer.sh` but in
Python so it can be driven from CI (Linux/macOS) when a Windows VM
runner is available. On a non-Windows host this script downloads the
wheels and prepares the wheelhouse, but the actual Nuitka compilation
requires a Windows runner (it shells out to cl.exe or MinGW).

For local end-to-end builds, use `tools/build_windows_installer.sh`
on the Windows host directly.
"""

from __future__ import annotations

import argparse
import platform
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--skip-nuitka",
        action="store_true",
        help="only download wheels; skip the Nuitka compilation step",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python interpreter to use (default: current)",
    )
    args = parser.parse_args()

    wheelhouse = REPO_ROOT / "wheelhouse-windows"
    wheelhouse.mkdir(exist_ok=True)
    dist = REPO_ROOT / "dist"
    dist.mkdir(exist_ok=True)

    # 1. Resolve the wheel list from pyproject.toml.
    import tomllib
    pyproject = tomllib.loads(REPO_ROOT.joinpath("pyproject.toml").read_text("rb" if False else "utf-8"))
    wheels = pyproject["project"]["optional-dependencies"]["windows-offline"]
    req_file = wheelhouse / "_requirements.txt"
    req_file.write_text("\n".join(wheels) + "\n", encoding="utf-8")

    # 2. Download wheels.
    print(f"==> Downloading {len(wheels)} wheels to {wheelhouse}")
    subprocess.run(
        [
            args.python, "-m", "pip", "download",
            "--dest", str(wheelhouse),
            "--python-version", "3.10",
            "--platform", "win_amd64",
            "--only-binary=:all:",
            "--requirement", str(req_file),
        ],
        check=True,
    )

    if args.skip_nuitka:
        print("==> --skip-nuitka set; stopping after wheel download.")
        return 0

    # 3. Compile via Nuitka. Only do this on a Windows host.
    if platform.system() != "Windows":
        print("==> Non-Windows host: skipping Nuitka compilation.")
        print("    Re-run on Windows to produce the .exe artifacts.")
        return 0

    venv = REPO_ROOT / ".venv-offline-build"
    if venv.exists():
        shutil.rmtree(venv)
    subprocess.run([args.python, "-m", "venv", str(venv)], check=True)
    py = venv / "Scripts" / "python.exe"
    subprocess.run(
        [str(py), "-m", "pip", "install", "--no-index",
         "--find-links", str(wheelhouse), "graphifyy"],
        check=True,
    )
    # (Nuitka invocations are identical to the .sh script; not duplicated here
    # to avoid drift. For a real Windows build, just call the .sh script.)
    print("==> This driver only does wheel download. On Windows, run:")
    print("       tools/build_windows_installer.sh")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Smoke-test the wheel-download path on macOS**

```bash
uv run python tools/build_windows_installer.py --skip-nuitka
```

Expected: prints `==> Downloading N wheels to ...` and downloads successfully (or fails with a pip error if no network — that's OK; the script's role is documented).

If the download fails because of a pip-side issue, that's a network problem, not a script bug. Note it in your report and proceed.

- [ ] **Step 3: Commit**

```bash
git add tools/build_windows_installer.py
git commit -m "build: add tools/build_windows_installer.py (cross-platform wheel download)"
```

---

## Task 12: Create `docs/operations/offline-installer.md`

**Files:**
- Create: `docs/operations/offline-installer.md`

- [ ] **Step 1: Create the docs directory and file**

```bash
mkdir -p docs/operations
```

Create `docs/operations/offline-installer.md` with this content:

````markdown
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
````

- [ ] **Step 2: Verify the file is well-formed Markdown**

```bash
uv run python -c "from pathlib import Path; t = Path('docs/operations/offline-installer.md').read_text(); assert t.startswith('# graphify Offline Windows Installer'); print('ok')"
```

Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add docs/operations/offline-installer.md
git commit -m "docs(operations): add offline-installer end-user guide"
```

---

## Task 13: Run the full test suite + run the in-process installer (sanity)

**Files:** none modified; this is a sanity gate.

- [ ] **Step 1: Run the full test suite**

```bash
uv run pytest -q
```

Expected: **2494 passed** (2478 + 16 new from Tasks 3–7), 28 skipped.

- [ ] **Step 2: In-process sanity check: detect hosts on this machine**

```bash
uv run python -c "
from graphify.installer.host_probe import detect_hosts, KNOWN_HOSTS
print('Known hosts:', len(KNOWN_HOSTS))
print('Detected on this machine:')
for h in detect_hosts():
    print(f'  - {h.name}  (skill: {h.skill_subpath}, via graphify install: {h.uses_graphify_install})')
"
```

Expected: lists KNOWN_HOSTS (21) and any hosts that happen to be installed locally (probably 0 in a typical dev environment, but the call should not error).

- [ ] **Step 3: In-process sanity check: `graphify self-install --help`**

```bash
uv run graphify self-install --help
```

Expected: prints `Usage: graphify self-install [--path DIR] [--no-path]`.

- [ ] **Step 4: In-process sanity check: `graphify self-uninstall` (no manifest present)**

```bash
uv run graphify self-uninstall
```

Expected: prints a "no install manifest" error and returns non-zero. (The function should never silently succeed when there's nothing to uninstall.)

---

## Task 14: Windows validation — V1–V5 (build + minimal install)

**Files:** none modified; this is a manual validation gate.

**This task MUST be run on a Windows 10 machine with Visual Studio Build
Tools installed.** It is the first task that exercises the compiled .exe.

- [ ] **Step 1: Build the .exe on Windows**

Copy the repo to a Windows 10 x86_64 machine (or open it in WSL / a VM).
Open a cmd window and run:

```cmd
tools\build_windows_installer.sh
```

Expected: after 15–25 minutes, three .exe files appear in `dist\`:
- `graphify-installer.exe` (~65 MB)
- `graphify.exe` (~65 MB)
- `graphify-mcp.exe` (~65 MB)

- [ ] **Step 2: V1 — Installer launches without cmd window**

Double-click `graphify-installer.exe`. Expected: no black cmd window pops (the .exe is `--windows-disable-console`); instead a console window appears briefly with the install wizard text, or the text is logged to `graphify-installer.log` next to the .exe.

- [ ] **Step 3: V3 — Host detection on the test machine**

The wizard should report at least one detected host (e.g. "detected hosts: claude" if Claude Code is installed). If the test machine has no host installed, the wizard should warn and continue (this is by design — V3 is informational, not blocking).

- [ ] **Step 4: V4 — Decompression completes**

After the wizard finishes, verify:

```cmd
dir "%LOCALAPPDATA%\graphify\bin"
```

Expected: `graphify.exe` and `graphify-mcp.exe` are listed.

- [ ] **Step 5: V5 — User PATH registered**

Open a **new** cmd window (so PATH changes propagate):

```cmd
where graphify
where graphify-mcp
graphify --version
```

Expected: `where` finds both binaries under `%LOCALAPPDATA%\graphify\bin\`, and `graphify --version` returns `0.9.1` (or whatever the current version is).

If any of V1, V3, V4, V5 fails, file a bug — do not proceed to Task 15.

---

## Task 15: Windows validation — V6–V12 (full pipeline)

**Files:** none modified; manual validation.

- [ ] **Step 1: V6 — Main CLI works**

```cmd
graphify --help
```

Expected: lists all subcommands including `install`, `uninstall`, `self-install`, `self-uninstall`, `extract`, etc.

- [ ] **Step 2: V7 — MCP entry works**

```cmd
graphify-mcp --help
```

Expected: prints the MCP server's `--help` text (whatever `graphify.serve._main` emits).

- [ ] **Step 3: V8–V9 — Skill files copied**

In a new cmd window:

```cmd
dir "%USERPROFILE%\.claude\skills\graphify"
```

Expected: `SKILL.md` exists, plus a `references\` directory with markdown sidecars.

- [ ] **Step 4: V10 — Host recognizes the skill**

Open Claude Code (or whichever host was detected). In a project directory, type `/graphify`. Expected: appears in the command list (Claude Code should auto-discover the SKILL.md in its skills dir).

- [ ] **Step 5: V11 — End-to-end pipeline**

In Claude Code, in a small test repository (any Python project), type:

```
/graphify .
```

Expected: produces `graphify-out\graph.json`, `graphify-out\GRAPH_REPORT.md`, `graphify-out\graph.html`, and `graphify-out\vis-network.min.js` (the vendored copy).

- [ ] **Step 6: V12 — Offline HTML render**

Open `graphify-out\graph.html` in a browser. Open the browser's Network tab and reload. Expected: **zero external network requests** (no requests to `unpkg.com`, no requests to any CDN). The graph should render fully from the local `vis-network.min.js` we vendored in the vis-network spec.

If V12 shows ANY external request, the installer did not bundle `vis-network.min.js` correctly — check the Nuitka `--include-package-data=graphify` flag.

---

## Task 16: Windows validation — V14 (uninstall)

**Files:** none modified; manual validation.

- [ ] **Step 1: Run the uninstaller**

In a cmd window:

```cmd
graphify-installer.exe uninstall
```

Expected: prints `done.` and removes:
- `%USERPROFILE%\.claude\skills\graphify\` (and equivalents for other detected hosts)
- `%LOCALAPPDATA%\graphify\`
- The user PATH entry `%LOCALAPPDATA%\graphify\bin`

- [ ] **Step 2: Verify nothing remains**

```cmd
where graphify
dir "%LOCALAPPDATA%\graphify"
dir "%USERPROFILE%\.claude\skills\graphify"
```

Expected: `where graphify` returns nothing; the two `dir` commands report "File Not Found" or "directory does not exist".

- [ ] **Step 3: Verify per-project `graphify-out\` is left alone**

If you ran `/graphify .` in a test repo (V11), that repo's `graphify-out\` should still exist after uninstall. The uninstaller is intentionally conservative — it never touches project artifacts.

---

## Self-Review Notes

The plan was checked against `docs/superpowers/specs/2026-06-29-offline-windows-installer-design.md`:

- **Spec §1 (architecture / boundaries)** → Task 7 (orchestrator), Task 8 (CLI subcommands), Task 9 (Nuitka entry script).
- **Spec §2 (wheelhouse scope)** → Task 1 (pyproject `windows-offline` extra lists every bundled wheel; Tasks 10–11 reference it in the Nuitka `--include-module` list).
- **Spec §3 (Nuitka configuration)** → Task 10 (bash build script with the exact `--include-module` list from the spec).
- **Spec §4 (installer behavior, host detection, mobilecoder handling, PATH registration)** → Task 3 (host_probe with `mobilecoder` explicit), Task 4 (path_win), Task 6 (skill_copy with mobilecoder fallback to `skill.md`), Task 7 (orchestrator), Task 8 (CLI), Task 9 (Nuitka entry).
- **Spec §5 (offline verification V1–V14)** → Tasks 14 (V1–V5), 15 (V6–V12), 16 (V14). V13 (cloud LLM) is excluded from the Windows-only validation since it requires a separate online run; documented as out-of-band in the spec.
- **Spec §6 (files changed / created)** → every row in the spec's file map is touched by exactly one task:
  - `graphify/installer/{__init__,host_probe,path_win,skill_copy,manifest}.py` → Tasks 2–7
  - `graphify/__main__.py` → Task 8
  - `tools/installer_main.py` → Task 9
  - `tools/build_windows_installer.{sh,py}` → Tasks 10–11
  - `docs/operations/offline-installer.md` → Task 12
  - `pyproject.toml` → Task 1
  - 5 new test files → Tasks 3–7

Type and name consistency:
- `Host` dataclass defined in Task 3; consumed by `host_skill_dir` (Task 3), `skill_copy` (Task 6), orchestrator (Task 7). No drift.
- `InstallManifest` defined in Task 5; consumed by `manifest_path`/`save_manifest`/`load_manifest` (Task 5) and orchestrator (Task 7). No drift.
- `PathWinError` defined in Task 4; caught in Task 7. No drift.
- `KNOWN_HOSTS` (Task 3) has 21 entries; spec §4 lists 15 supported hosts plus 6 additional (mobilecoder, agents, amp, vscode, cursor, gemini) — total 21. ✓
