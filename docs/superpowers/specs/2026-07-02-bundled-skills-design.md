# Design: Bundle community skills with graphify (gf- namespace)

**Date:** 2026-07-02
**Branch:** v8
**Scope:** installer, package data, build pipeline, offline installer

---

## Problem

The offline Windows installer (shipped in `graphify-installer.exe`) currently copies **only** graphify's own `SKILL.md` to the detected host's skill directory. On the target machine — a Windows desktop with no public network access at install time — the user gets graphify working but **no other AI-coding skills**.

Concretely: superpowers (`brainstorming`, `writing-plans`, `test-driven-development`, …) and the user's own `llm-wiki` skill are unreachable on an air-gapped machine, because:

- superpowers ships as a Claude Code plugin installed via the plugin marketplace (requires network at install time).
- `llm-wiki` lives at `~/.claude/skills/llm-wiki/` and would have to be hand-copied per machine.

We want the offline installer to deliver these skills too, so a freshly installed offline machine is immediately productive with the full brainstorming → design → plan → code → graph → wiki workflow the user is designing.

---

## Decisions (locked)

| Question | Decision |
|---|---|
| Which skills to bundle | 14 superpowers + 1 llm-wiki = **15 skills total** |
| Source strategy | **Static snapshot + LICENSE preserved**. No submodule, no upstream fetch. |
| Host coverage | All 14 hosts that `host_probe.KNOWN_HOSTS` supports except `cursor` / `gemini` (those need format adapters — v2). |
| Per-host body strategy | **One body, host-agnostic.** Each skill has a single `SKILL.md` in the repo; the installer copies it to every supported host's `<skills/<name>/` directory. No `skill-<host>-<skill>.md` proliferation. |
| Naming | **All bundled skills are prefixed `gf-`** (graphify family) → `gf-brainstorming`, `gf-writing-plans`, …, `gf-llm-wiki`. Source-of-truth lives at `graphify/bundled_skills/<upstream>/<skill>/SKILL.md`; final install name is the `gf-` form. |
| Conflict semantics | **Always overwrite.** Because of the `gf-` namespace, no real-world conflict exists; the installer never has to detect "user already has this skill". |
| `--force` flag | **Not added.** Default behavior is overwrite; no opt-out. |
| Manifest tracking | **None.** Uninstall behavior unchanged: `graphify-installer.exe uninstall` removes graphify's own skill only. Bundled skills, once installed, are owned by the user and not tracked by graphify. |
| Workflow orchestrator | **Out of scope.** This spec only delivers *discoverable* skills. The chained `/gf-brainstorming → /gf-writing-plans → …` workflow skill is built separately. |
| Repository location | `graphify/bundled_skills/` — inside the Python package, so `importlib.resources` finds it natively and `pip wheel` picks it up via `package-data`. |
| Cursor / Gemini | **Skip with info message**, same handling as today's `copy_skill()` for graphify's own SKILL.md. Print hint to run `graphify install cursor` / `graphify install gemini` after the offline installer. |
| Frontmatter `name:` | Must match the directory basename (`name: gf-brainstorming` for the file at `bundled_skills/superpowers/brainstorming/SKILL.md`). Renamed in the snapshot, not at install time. |
| Third-party licenses | Kept in place (`bundled_skills/superpowers/LICENSE`, `bundled_skills/llm-wiki/LICENSE`) plus a top-level `NOTICE` listing bundled projects. |

---

## Goals

1. After `graphify-installer.exe install` finishes, the host's skill directory contains `gf-*` skills for `brainstorming`, `writing-plans`, `subagent-driven-development`, `test-driven-development`, `systematic-debugging`, `using-git-worktrees`, `requesting-code-review`, `receiving-code-review`, `executing-plans`, `finishing-a-development-branch`, `dispatching-parallel-agents`, `using-superpowers`, `verification-before-completion`, `writing-skills`, and `llm-wiki` — discoverable by the AI Agent host.
2. The same 15 skills are installed when a user runs `graphify install <host>` directly (e.g. from a non-air-gapped machine).
3. Re-running install is **idempotent**: the `gf-*` files are always overwritten with the latest snapshot bundled in the package.
4. No conflict with the user's separately installed superpowers plugin (which uses non-`gf-` names like `brainstorming`, `writing-plans`, …).
5. Wheel size grows by < 5% (estimated ~1–2.5 MB).

## Non-goals

- Building the workflow orchestrator skill that chains these.
- Cursor / Gemini format adapters (`.mdc`, `GEMINI.md` injection).
- Auto-syncing with upstream superpowers. Updates happen manually by re-copying the snapshot.
- A UI for selecting which bundled skills to install.
- Per-user skill overrides (e.g. "let me customize `gf-brainstorming` after install" — the always-overwrite semantics prevent this by design).

---

## 1. Naming convention (the central design choice)

The `gf-` prefix is the single most important decision. It transforms the problem:

| | Without prefix (original names) | With `gf-` prefix |
|---|---|---|
| Conflict with user's installed superpowers | High — both would write to `~/.claude/skills/brainstorming/` | **None** — names don't overlap |
| Install semantics | Must check "does file exist?" → skip or overwrite | Always overwrite, no check |
| User's customizations preserved | Yes (skip preserves) | No (always overwritten) — but this only affects `gf-*` files which user never edited anyway |
| Uninstall behavior | Skip-if-exists makes uninstall ambiguous | Installed `gf-*` files are unambiguous to clean up later |

The cost is verbosity: `/gf-brainstorming` instead of `/brainstorming`. The workflow orchestrator (built separately) will use the `gf-` names, so the verbosity is contained to that skill.

---

## 2. Repository layout

```
graphify/
├── __init__.py
├── skills/<host>/references/...           ← existing (graphify's own references)
├── bundled_skills/                        ← NEW
│   ├── superpowers/
│   │   ├── brainstorming/SKILL.md         ← frontmatter: name: gf-brainstorming
│   │   ├── writing-plans/SKILL.md         ← frontmatter: name: gf-writing-plans
│   │   ├── subagent-driven-development/SKILL.md
│   │   ├── test-driven-development/SKILL.md
│   │   ├── systematic-debugging/SKILL.md
│   │   ├── using-git-worktrees/SKILL.md
│   │   ├── requesting-code-review/SKILL.md
│   │   ├── receiving-code-review/SKILL.md
│   │   ├── executing-plans/SKILL.md
│   │   ├── finishing-a-development-branch/SKILL.md
│   │   ├── dispatching-parallel-agents/SKILL.md
│   │   ├── using-superpowers/SKILL.md
│   │   ├── verification-before-completion/SKILL.md
│   │   ├── writing-skills/SKILL.md
│   │   ├── LICENSE                        ← superpowers MIT, preserved verbatim
│   │   └── NOTICE                         ← upstream attribution
│   └── llm-wiki/
│       ├── SKILL.md                       ← frontmatter: name: gf-llm-wiki
│       ├── AGENTS.md, CHANGELOG.md, CLAUDE.md, HERMES.md, README.md
│       ├── templates/, scripts/, platforms/, deps/
│       ├── install.sh, install.ps1, setup.sh
│       └── LICENSE
├── installer/
│   ├── skill_copy.py                      ← modified: add copy_bundled_skills() call
│   ├── bundled_skills.py                  ← NEW: registry + path derivation
│   ├── host_probe.py                      ← unchanged
│   └── ...
└── ...
```

**Critical:** the source-of-truth directory names (`brainstorming`, `writing-plans`, …) retain the upstream names so we can mechanically re-sync from superpowers by copying `<upstream>/skills/<skill>/SKILL.md` → `bundled_skills/superpowers/<skill>/SKILL.md` and only edit the frontmatter `name:` field. The `gf-` prefix is **applied only in frontmatter and in the registry**, not in the source directory structure.

---

## 3. Package data (`pyproject.toml`)

Append five globs to `[tool.setuptools.package-data].graphify`:

```toml
graphify = [
    "skill.md", "skill-codex.md", "skill-opencode.md", "skill-kilo.md", "command-kilo.md",
    "skill-aider.md", "skill-amp.md", "skill-agents.md", "skill-copilot.md", "skill-claw.md",
    "skill-windows.md", "skill-droid.md", "skill-trae.md", "skill-kiro.md", "skill-vscode.md",
    "skill-pi.md", "skill-devin.md",
    "skills/*/references/*.md",
    "always_on/*.md",
    "assets/vis-network.min.js",
    # NEW:
    "bundled_skills/**/*.md",          # SKILL.md, LICENSE, NOTICE, README, templates
    "bundled_skills/**/*.txt",         # LICENSE/NOTICE occasionally .txt
    "bundled_skills/**/*.sh",          # llm-wiki scripts + install.sh + setup.sh
    "bundled_skills/**/*.ps1",         # llm-wiki install.ps1
    "bundled_skills/**/*.js",          # llm-wiki graph scripts
    "bundled_skills/**/*.tsv",         # llm-wiki source registry
]
```

Explicit globs (vs. `bundled_skills/**/*`): protects against accidentally bundling random future files (`.gitignore`, debug dumps) without an explicit decision.

No new glob is needed for llm-wiki's `deps/` directory — that one will be added if and when `deps/` actually contains files; today it's empty in the upstream snapshot.

---

## 4. Installer logic

### 4.1 New module: `graphify/installer/bundled_skills.py`

```python
"""Registry of skills bundled with graphify for offline installation."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

@dataclass(frozen=True)
class BundledSkill:
    name: str                       # final install name (gf-prefixed)
    source_subpath: str             # path relative to package root
    has_references: bool            # whether to copy a references/ sidecar

_BUNDLED: tuple[BundledSkill, ...] = (
    BundledSkill("gf-brainstorming",                  "bundled_skills/superpowers/brainstorming/SKILL.md",                  False),
    BundledSkill("gf-writing-plans",                  "bundled_skills/superpowers/writing-plans/SKILL.md",                  False),
    BundledSkill("gf-subagent-driven-development",    "bundled_skills/superpowers/subagent-driven-development/SKILL.md",    False),
    BundledSkill("gf-test-driven-development",        "bundled_skills/superpowers/test-driven-development/SKILL.md",        False),
    BundledSkill("gf-systematic-debugging",           "bundled_skills/superpowers/systematic-debugging/SKILL.md",           False),
    BundledSkill("gf-using-git-worktrees",            "bundled_skills/superpowers/using-git-worktrees/SKILL.md",            False),
    BundledSkill("gf-requesting-code-review",         "bundled_skills/superpowers/requesting-code-review/SKILL.md",         False),
    BundledSkill("gf-receiving-code-review",          "bundled_skills/superpowers/receiving-code-review/SKILL.md",          False),
    BundledSkill("gf-executing-plans",                "bundled_skills/superpowers/executing-plans/SKILL.md",                False),
    BundledSkill("gf-finishing-a-development-branch", "bundled_skills/superpowers/finishing-a-development-branch/SKILL.md", False),
    BundledSkill("gf-dispatching-parallel-agents",    "bundled_skills/superpowers/dispatching-parallel-agents/SKILL.md",    False),
    BundledSkill("gf-using-superpowers",              "bundled_skills/superpowers/using-superpowers/SKILL.md",              False),
    BundledSkill("gf-verification-before-completion", "bundled_skills/superpowers/verification-before-completion/SKILL.md", False),
    BundledSkill("gf-writing-skills",                 "bundled_skills/superpowers/writing-skills/SKILL.md",                 False),
    BundledSkill("gf-llm-wiki",                       "bundled_skills/llm-wiki/SKILL.md",                                   True),
)

_UNSUPPORTED_HOSTS = frozenset({"cursor", "gemini"})


def all_bundled() -> tuple[BundledSkill, ...]:
    return _BUNDLED


def supports_host(host_name: str) -> bool:
    return host_name not in _UNSUPPORTED_HOSTS


def bundled_skill_dir(host, skill_name: str, *, root: Path) -> Path:
    """Target directory: root/<host.marker>/<up-to-skills>/<skill_name>/

    Replaces the trailing 'graphify' segment of host.skill_subpath with
    skill_name. Falls back to root/<host.marker>/skills/<skill_name>/ if the
    host's subpath doesn't end in 'graphify' (defensive — none currently).
    """
    parts = host.skill_subpath.parts
    if parts[-1] == "graphify":
        new_subpath = Path(*parts[:-1]) / skill_name
    else:
        new_subpath = Path("skills") / skill_name
    return root / host.marker / new_subpath
```

### 4.2 Extension to `graphify/installer/skill_copy.py`

Add `copy_bundled_skills(host, *, root, package_root=None)` symmetric to `copy_skill()`. Behavior:

1. If `host.name in _UNSUPPORTED_HOSTS`, return early (no-op).
2. For each `BundledSkill`:
   - `target = bundled_skill_dir(host, skill.name, root=root) / "SKILL.md"`
   - Read body from `package_root / skill.source_subpath` (or `importlib.resources` if `package_root` is None).
   - `target.parent.mkdir(parents=True, exist_ok=True)`
   - `target.write_text(body, encoding="utf-8")`
   - If `skill.has_references`, copy `references/` next to it.
3. Print `[installer] installed N bundled skills for <host>: ...`

**No existence check, no skip logic, no `--force`, no manifest.** The whole function is ~25 lines including logging.

### 4.3 Caller change in `graphify/installer/__init__.py`

One line added after the existing `copy_skill(host, ...)` call:

```python
copy_skill(host, root=root, package_root=package_root)
copy_bundled_skills(host, root=root, package_root=package_root)   # NEW
```

### 4.4 `bundled_skill_dir()` worked examples

| host | `host.skill_subpath` | target for `gf-brainstorming` |
|---|---|---|
| `claude` | `skills/graphify` | `~/.claude/skills/gf-brainstorming/` |
| `codex` | `skills/graphify` | `~/.codex/skills/gf-brainstorming/` |
| `aider` | `graphify` (no `skills/` parent) | `~/.aider/gf-brainstorming/` |
| `pi` | `agent/skills/graphify` | `~/.pi/agent/skills/gf-brainstorming/` |
| `mobilecoder` | `skills/graphify` | `~/.mobilecoder/skills/gf-brainstorming/` |
| `cursor` | `rules` (skipped entirely) | n/a |
| `gemini` | `skills/graphify` (skipped entirely) | n/a |

---

## 5. Build / Nuitka

**Zero changes** to `tools/build_windows_installer.sh` or `docs/ci/build-windows-installer.yml`.

The three Nuitka invocations already include `--include-package-data=graphify`, which pulls in everything `pyproject.toml`'s `package-data` lists. Adding the five `bundled_skills/**/*` globs is sufficient.

A 30-line pre-flight check is inserted after `pip wheel .` and before the Nuitka runs, to fail the build loudly if the snapshot is missing files:

```python
from importlib.resources import files
n = sum(1 for _ in (files("graphify") / "bundled_skills" / "superpowers").iterdir() if _.name != "LICENSE" and _.name != "NOTICE")
assert n == 14, f"expected 14 superpowers skills, got {n}"
```

---

## 6. Tests

### 6.1 New file: `tests/installer/test_bundled_skills.py`

Four test classes:

| Class | Tests |
|---|---|
| `TestBundledSkillsRegistry` | `count == 15`, names unique, 14 superpowers + 1 llm-wiki, all `source_subpath` files exist in repo, superpowers LICENSE exists. |
| `TestBundledSkillsFrontmatter` | Each SKILL.md has valid YAML frontmatter; `name:` field matches `BundledSkill.name`. |
| `TestBundledSkillInstall` | Per-host (parametrized over `claude`/`codex`/`opencode`/`kilo`/`aider`/`pi`): `copy_bundled_skills()` writes SKILL.md to expected path. `cursor`/`gemini` are no-ops. Existing target is overwritten (not skipped). |
| `TestBundledSkillsInWheel` | `importlib.resources.files("graphify") / "bundled_skills"` contains exactly 15 skill directories. Catches `package-data` misconfiguration. |

Uses the existing `package_root` fixture pattern already in `tests/installer/test_install*.py`.

### 6.2 Existing test enhancement: `tests/installer/test_install.py`

The `test_install_roundtrip`-style tests get one extra assertion verifying that after `install_for_host("claude", …)`, `gf-brainstorming/SKILL.md` and `gf-llm-wiki/SKILL.md` exist alongside `graphify/SKILL.md`.

---

## 7. Documentation

### 7.1 `CHANGELOG.md`

Append to `## Unreleased` (above the existing offline-installer entry's bottom):

```
- Feat: offline installer now also bundles 15 community skills under the
  `gf-` namespace (14 superpowers skills + `gf-llm-wiki`). After
  `graphify-installer.exe` runs, the host's skill directory contains
  `gf-brainstorming/`, `gf-writing-plans/`, `gf-subagent-driven-development/`,
  `gf-test-driven-development/`, `gf-systematic-debugging/`,
  `gf-using-git-worktrees/`, `gf-requesting-code-review/`,
  `gf-receiving-code-review/`, `gf-executing-plans/`,
  `gf-finishing-a-development-branch/`, `gf-dispatching-parallel-agents/`,
  `gf-using-superpowers/`, `gf-verification-before-completion/`,
  `gf-writing-skills/`, and `gf-llm-wiki/`. Namespaced to make always-
  overwrite safe. See `graphify/bundled_skills/README.md`.
```

### 7.2 `docs/operations/offline-installer.md`

In the "What's inside the .exe" section, append a paragraph:

> The installer also ships 15 community skills under the `gf-` namespace. They are placed in the host's skill directory alongside `graphify/` and are immediately discoverable. Trigger them via `/gf-brainstorming`, `/gf-writing-plans`, etc.

### 7.3 `NOTICE` (repo root, new file)

Lists bundled third-party projects, copyright, license, and source link. Currently:

```
graphify
Copyright ...

This product includes software developed by third parties:

────────────────────────────────────────────────────────────
superpowers-dev (bundled under graphify/bundled_skills/superpowers/)
Copyright 2025 Jesse Vincent
License:  MIT (see graphify/bundled_skills/superpowers/LICENSE)
Source:   https://github.com/superpowers-dev/superpowers-dev
────────────────────────────────────────────────────────────
llm-wiki (bundled under graphify/bundled_skills/llm-wiki/)
Copyright ...
License:  see graphify/bundled_skills/llm-wiki/LICENSE
────────────────────────────────────────────────────────────
```

### 7.4 `graphify/bundled_skills/README.md` (new file)

~40 lines explaining: what this directory is, the `gf-` rename convention, how to sync from upstream (manual, not automated), what changes when adding a new bundled skill.

---

## 8. Migration / backward compatibility

- **No data loss.** Users who already have `~/.claude/skills/brainstorming/` (from the superpowers plugin) keep it untouched. The installer writes `gf-brainstorming` next to it, so both are available.
- **No breaking change to existing flows.** `graphify install <host>` and `graphify-installer.exe install` continue to install graphify's own skill exactly as before; they additionally install the 15 bundled skills.
- **Uninstall unchanged.** `graphify-installer.exe uninstall` removes graphify's own skill. `gf-*` skills remain in place (the user can remove them by hand if desired). This is documented in `bundled_skills/README.md`.
- **PyPI install (`pip install graphifyy`)** picks up the bundled skills automatically because the wheel contains them. Users who installed graphify via PyPI and then run `graphify install <host>` will also get the `gf-*` skills.

---

## 9. Open questions

None. All key decisions are locked:

| Decision | Choice |
|---|---|
| Source strategy | static snapshot + LICENSE |
| Naming | `gf-` prefix |
| Host coverage | all KNOWN_HOSTS minus cursor/gemini |
| Conflict policy | always overwrite |
| Manifest | none |
| Repository location | `graphify/bundled_skills/` |
| Build pipeline | pyproject.toml only, Nuitka unchanged |
| Cursor/Gemini | skipped, v2 |

---

## 10. Verification (post-implementation)

After implementation lands:

1. **Wheel inspection**: `python -m zipfile -l dist/graphifyy-*.whl | grep bundled_skills` shows 15 skill paths.
2. **Wheel install in clean venv**: `pip install dist/graphifyy-*.whl`, then `python -c "from importlib.resources import files; print(sorted(p.name for p in (files('graphify') / 'bundled_skills' / 'superpowers').iterdir()))"` lists 14 + LICENSE + NOTICE.
3. **`graphify install` smoke**: in a clean tmp dir, `graphify install claude` produces 16 directories under `~/.claude/skills/` (graphify + 15 gf-*).
4. **Idempotency**: re-running `graphify install claude` produces byte-identical files (modulo mtime).
5. **Nuitka build**: `tools/build_windows_installer.sh` completes; the resulting `.exe` contains the bundled skills (extract and verify with `7z l graphify-installer.exe`).

---

## 11. Out-of-scope follow-ups (for later)

- Cursor / Gemini format adapters (`cursor` needs `.mdc`, `gemini` needs `GEMINI.md` + hook).
- The workflow orchestrator skill (chains `/gf-brainstorming → /gf-writing-plans → …`).
- Automated upstream sync (a CI job that periodically diffs against superpowers and opens a PR if anything changed).
- User-facing "select which bundled skills to install" flag (probably not needed — the always-overwrite default is fine and disk cost is < 3 MB).