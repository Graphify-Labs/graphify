# Bundled Skills (gf- namespace) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship 15 community skills (14 superpowers + 1 llm-wiki) under the `gf-` namespace inside the offline Windows installer so air-gapped machines have the full brainstorming → design → plan → code → graph → wiki workflow available without network access.

**Architecture:** Static snapshot of upstream skills lives under `graphify/bundled_skills/{superpowers,llm-wiki}/`. A new `graphify/installer/bundled_skills.py` registry exposes them with `gf-` prefixed names. `graphify/installer/skill_copy.py` gains a `copy_bundled_skills()` function that the installer orchestrator calls after `copy_skill()`. The build pipeline needs only a 5-glob addition to `pyproject.toml`; Nuitka already passes `--include-package-data=graphify`.

**Tech Stack:** Python 3.10+, dataclasses, `importlib.resources`, existing `graphify.installer.host_probe.KNOWN_HOSTS`, pytest (TDD), sed for one-time frontmatter rename, Nuitka `--include-package-data`.

**Spec:** `docs/superpowers/specs/2026-07-02-bundled-skills-design.md`

---

## File Structure

| Path | Status | Purpose |
|---|---|---|
| `graphify/bundled_skills/superpowers/<skill>/SKILL.md` | Create | 14 SKILL.md files copied from superpowers-dev, frontmatter `name:` renamed to `gf-<skill>` |
| `graphify/bundled_skills/superpowers/LICENSE` | Create | MIT license verbatim from upstream |
| `graphify/bundled_skills/superpowers/NOTICE` | Create | Upstream attribution |
| `graphify/bundled_skills/llm-wiki/SKILL.md` | Create | SKILL.md copied, frontmatter renamed to `name: gf-llm-wiki` |
| `graphify/bundled_skills/llm-wiki/<templates,scripts,platforms,deps>` | Create | Whole directory tree copied from `~/.claude/skills/llm-wiki/` |
| `graphify/bundled_skills/llm-wiki/LICENSE` | Create | llm-wiki license |
| `graphify/bundled_skills/README.md` | Create | Explain this directory and the `gf-` rename convention |
| `graphify/installer/bundled_skills.py` | Create | `BundledSkill` dataclass + `_BUNDLED` tuple + `bundled_skill_dir()` |
| `graphify/installer/skill_copy.py` | Modify | Add `copy_bundled_skills()` (~25 lines) |
| `graphify/installer/__init__.py` | Modify | One-line addition: call `copy_bundled_skills()` after `copy_skill()` |
| `pyproject.toml` | Modify | Append 5 globs to `[tool.setuptools.package-data].graphify` |
| `tools/build_windows_installer.sh` | Modify | Insert 6-line pre-flight check after `pip wheel .` |
| `tests/test_bundled_skills.py` | Create | Registry + frontmatter + install logic tests |
| `tests/test_install_roundtrip.py` | Modify | Add 1 assertion per host for `gf-*` skills |
| `NOTICE` (repo root) | Create | Bundled third-party projects + licenses |
| `CHANGELOG.md` | Modify | Append entry to `## Unreleased` |
| `docs/operations/offline-installer.md` | Modify | Add paragraph to "What's inside the .exe" |

Each task below produces a self-contained commit. TDD tasks follow the strict "red → green → commit" pattern.

---

## Phase 1: Snapshot upstream skills

### Task 1.1: Copy 14 superpowers SKILL.md files with frontmatter rename

**Files:**
- Create: `graphify/bundled_skills/superpowers/<skill>/SKILL.md` (14 files)

- [ ] **Step 1: Create the directory layout and copy files**

Run from the graphify repo root:

```bash
mkdir -p graphify/bundled_skills/superpowers
for skill in brainstorming writing-plans subagent-driven-development test-driven-development systematic-debugging using-git-worktrees requesting-code-review receiving-code-review executing-plans finishing-a-development-branch dispatching-parallel-agents using-superpowers verification-before-completion writing-skills; do
    mkdir -p "graphify/bundled_skills/superpowers/$skill"
    cp "~/.claude/plugins/marketplaces/superpowers-dev/skills/$skill/SKILL.md" \
       "graphify/bundled_skills/superpowers/$skill/SKILL.md"
done
```

Expected: 14 new files under `graphify/bundled_skills/superpowers/<skill>/SKILL.md`.

- [ ] **Step 2: Rename frontmatter `name:` field in each file**

```bash
for skill in brainstorming writing-plans subagent-driven-development test-driven-development systematic-debugging using-git-worktrees requesting-code-review receiving-code-review executing-plans finishing-a-development-branch dispatching-parallel-agents using-superpowers verification-before-completion writing-skills; do
    sed -i '' "s/^name: ${skill}$/name: gf-${skill}/" \
       "graphify/bundled_skills/superpowers/$skill/SKILL.md"
done
```

(Empty string after `-i ''` is macOS sed syntax — leave as-is on macOS. On Linux change to `sed -i`.)

Expected: every file's first frontmatter field is now `name: gf-<skill>`.

- [ ] **Step 3: Verify**

```bash
for skill in brainstorming writing-plans subagent-driven-development test-driven-development systematic-debugging using-git-worktrees requesting-code-review receiving-code-review executing-plans finishing-a-development-branch dispatching-parallel-agents using-superpowers verification-before-completion writing-skills; do
    head -1 "graphify/bundled_skills/superpowers/$skill/SKILL.md"
    grep -E "^name: gf-${skill}$" "graphify/bundled_skills/superpowers/$skill/SKILL.md"
done
```

Expected: 14 lines of `---` (YAML delimiter) followed by 14 lines matching `name: gf-<skill>`.

- [ ] **Step 4: Commit**

```bash
git add graphify/bundled_skills/superpowers/
git commit -m "feat(bundled-skills): snapshot 14 superpowers SKILL.md files with gf- rename"
```

---

### Task 1.2: Add superpowers LICENSE and NOTICE

**Files:**
- Create: `graphify/bundled_skills/superpowers/LICENSE`
- Create: `graphify/bundled_skills/superpowers/NOTICE`

- [ ] **Step 1: Copy LICENSE**

```bash
cp ~/.claude/plugins/marketplaces/superpowers-dev/LICENSE \
   graphify/bundled_skills/superpowers/LICENSE
```

Expected: `graphify/bundled_skills/superpowers/LICENSE` exists and starts with `MIT License`.

- [ ] **Step 2: Write NOTICE**

Create `graphify/bundled_skills/superpowers/NOTICE` with this exact content:

```
Bundled under graphify (graphify/bundled_skills/superpowers/)

Upstream:    superpowers-dev
Copyright:   2025 Jesse Vincent
License:     MIT (see ./LICENSE)
Source:      https://github.com/superpowers-dev/superpowers-dev

Renamed for the graphify offline installer:
  brainstorming                  -> gf-brainstorming
  writing-plans                  -> gf-writing-plans
  subagent-driven-development    -> gf-subagent-driven-development
  test-driven-development        -> gf-test-driven-development
  systematic-debugging           -> gf-systematic-debugging
  using-git-worktrees            -> gf-using-git-worktrees
  requesting-code-review         -> gf-requesting-code-review
  receiving-code-review          -> gf-receiving-code-review
  executing-plans                -> gf-executing-plans
  finishing-a-development-branch -> gf-finishing-a-development-branch
  dispatching-parallel-agents    -> gf-dispatching-parallel-agents
  using-superpowers              -> gf-using-superpowers
  verification-before-completion -> gf-verification-before-completion
  writing-skills                 -> gf-writing-skills
```

- [ ] **Step 3: Commit**

```bash
git add graphify/bundled_skills/superpowers/LICENSE graphify/bundled_skills/superpowers/NOTICE
git commit -m "feat(bundled-skills): add superpowers LICENSE and NOTICE"
```

---

### Task 1.3: Snapshot llm-wiki into bundled_skills/

**Files:**
- Create: `graphify/bundled_skills/llm-wiki/` (whole directory tree)

- [ ] **Step 1: Copy llm-wiki and rename frontmatter**

```bash
mkdir -p graphify/bundled_skills
cp -R ~/.claude/skills/llm-wiki graphify/bundled_skills/llm-wiki
sed -i '' 's/^name: llm-wiki$/name: gf-llm-wiki/' \
    graphify/bundled_skills/llm-wiki/SKILL.md
```

Expected: `graphify/bundled_skills/llm-wiki/` contains SKILL.md + templates/ + scripts/ + platforms/ + deps/ + AGENTS.md + CHANGELOG.md + CLAUDE.md + HERMES.md + README.md + install.sh + install.ps1 + setup.sh + LICENSE.

- [ ] **Step 2: Verify the rename**

```bash
head -3 graphify/bundled_skills/llm-wiki/SKILL.md
grep -E "^name: gf-llm-wiki$" graphify/bundled_skills/llm-wiki/SKILL.md
```

Expected: first 3 lines include `---`, `name: gf-llm-wiki`, `description: ...`.

- [ ] **Step 3: Verify directory tree**

```bash
ls graphify/bundled_skills/llm-wiki/
ls graphify/bundled_skills/llm-wiki/templates/ | head -5
ls graphify/bundled_skills/llm-wiki/scripts/ | head -5
```

Expected: top-level has SKILL.md, templates/, scripts/, platforms/, deps/, LICENSE; templates/ has .md files; scripts/ has .sh and .js files.

- [ ] **Step 4: Commit**

```bash
git add graphify/bundled_skills/llm-wiki/
git commit -m "feat(bundled-skills): snapshot llm-wiki with gf-llm-wiki rename"
```

---

### Task 1.4: Create bundled_skills/README.md

**Files:**
- Create: `graphify/bundled_skills/README.md`

- [ ] **Step 1: Write the README**

Create `graphify/bundled_skills/README.md` with this content:

````markdown
# graphify/bundled_skills/

Skills bundled inside the `graphify` package so the offline Windows installer
ships a working skill set without needing network access at install time.

## What's here

| Directory | Source | Count |
|---|---|---|
| `superpowers/` | [superpowers-dev](https://github.com/superpowers-dev/superpowers-dev) (MIT, Jesse Vincent) | 14 skills |
| `llm-wiki/` | llm-wiki (project-local) | 1 skill + templates/scripts/platforms |

## The `gf-` rename

Every bundled skill is installed under a `gf-` prefix:

- `brainstorming` → `gf-brainstorming`
- `writing-plans` → `writing-plans` (typo in example, see superpowers)

The renaming is intentional:

1. Avoids collisions with user-installed superpowers plugin (which uses bare
   names like `brainstorming`).
2. Makes always-overwrite install semantics safe: we never overwrite a file the
   user might have customized, because by construction nothing else uses the
   `gf-` namespace.
3. Marks these as "from the graphify family" so the user knows uninstalling
   graphify also removes them.

The frontmatter `name:` field is renamed in the snapshot (not at install time),
so the slash-command is `/gf-brainstorming`, not `/brainstorming`.

## Adding a new bundled skill

1. Create the directory under `graphify/bundled_skills/<upstream>/<skill>/`.
2. Drop `SKILL.md` (with `name:` renamed to `gf-<skill>`).
3. Add the entry to `_BUNDLED` in `graphify/installer/bundled_skills.py`.
4. Add a `tests/test_bundled_skills.py` case asserting the new entry's
   `source_subpath` resolves.
5. Update the LICENSE / NOTICE attribution if the upstream requires it.

## Syncing from upstream superpowers

This is **manual** (no automation). When superpowers-dev ships a new version:

```bash
for skill in brainstorming writing-plans ...; do
    cp ~/.claude/plugins/marketplaces/superpowers-dev/skills/$skill/SKILL.md \
       graphify/bundled_skills/superpowers/$skill/SKILL.md
    sed -i '' "s/^name: ${skill}$/name: gf-${skill}/" \
       graphify/bundled_skills/superpowers/$skill/SKILL.md
done
```

(Correct the skill list — see `tests/test_bundled_skills.py::test_superpowers_count_is_14`.)

## Uninstall behavior

`graphify-installer.exe uninstall` does **not** remove `gf-*` skills. Once
installed they belong to the user. Delete them by hand if desired.
````

- [ ] **Step 2: Commit**

```bash
git add graphify/bundled_skills/README.md
git commit -m "docs(bundled-skills): README explaining gf- rename convention"
```

---

## Phase 2: Registry module (TDD)

### Task 2.1: Failing test for registry structure

**Files:**
- Create: `tests/test_bundled_skills.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_bundled_skills.py` with this content:

```python
"""Tests for graphify.installer.bundled_skills.

Covers registry structure (count, names, uniqueness), frontmatter validity,
and per-host install path derivation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from graphify.installer import bundled_skills
from graphify.installer.bundled_skills import (
    BundledSkill,
    all_bundled,
    bundled_skill_dir,
    supports_host,
)
from graphify.installer.host_probe import KNOWN_HOSTS, host_skill_dir


class TestBundledSkillsRegistry:
    """Structural checks on the _BUNDLED tuple — fast, catches regressions."""

    def test_count_is_15(self):
        assert len(all_bundled()) == 15

    def test_names_unique(self):
        names = [s.name for s in all_bundled()]
        assert len(names) == len(set(names))

    def test_superpowers_count_is_14(self):
        sp = [s for s in all_bundled() if s.name != "gf-llm-wiki"]
        assert len(sp) == 14

    def test_every_entry_has_gf_prefix(self):
        for s in all_bundled():
            assert s.name.startswith("gf-"), f"{s.name} missing gf- prefix"

    def test_all_source_files_exist(self, package_root: Path):
        """Every source_subpath must resolve to a real file in the repo."""
        for s in all_bundled():
            assert (package_root / s.source_subpath).exists(), (
                f"{s.source_subpath} does not exist under package_root"
            )

    def test_superpowers_license_present(self, package_root: Path):
        assert (package_root / "bundled_skills" / "superpowers" / "LICENSE").exists()
```

Add a `package_root` fixture to `tests/conftest.py` (see Step 2 below).

- [ ] **Step 2: Add `package_root` fixture to tests/conftest.py**

Append to `tests/conftest.py`:

```python
@pytest.fixture
def package_root() -> Path:
    """Absolute path to the graphify package source root.

    Used by bundled_skills tests to assert that BundledSkill.source_subpath
    entries point at real files (independent of `importlib.resources` which
    only sees installed packages).
    """
    import graphify
    return Path(graphify.__file__).parent.resolve()
```

If `package_root` already exists in `tests/conftest.py`, do not duplicate; skip this step.

- [ ] **Step 3: Run the test, verify it fails**

Run: `pytest tests/test_bundled_skills.py -v`
Expected: `ImportError: cannot import name 'bundled_skills' from 'graphify.installer'` (or similar — module doesn't exist yet).

---

### Task 2.2: Implement the registry module

**Files:**
- Create: `graphify/installer/bundled_skills.py`

- [ ] **Step 1: Write the module**

Create `graphify/installer/bundled_skills.py` with this exact content:

```python
"""Registry of skills bundled with graphify for offline installation.

Each entry is a host-agnostic SKILL.md (plus optional references/) that
`copy_bundled_skills()` writes into `<host_skill_dir>/<name>/` on the
user's machine. Always-overwrite semantics: existing files are replaced
unconditionally. The `gf-` namespace prefix guarantees no collision with
user-installed plugins (e.g. the upstream superpowers plugin uses bare
names like `brainstorming`).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class BundledSkill:
    """A skill bundled with graphify.

    Attributes:
        name: Final install name (always `gf-` prefixed). Also the directory
            name created under the host's `skills/` parent.
        source_subpath: Path relative to the graphify package root where the
            SKILL.md file lives (e.g.
            `bundled_skills/superpowers/brainstorming/SKILL.md`).
        has_references: True if a `references/` sidecar should be copied
            alongside SKILL.md. Only `gf-llm-wiki` uses this today.
    """

    name: str
    source_subpath: str
    has_references: bool


_BUNDLED: tuple[BundledSkill, ...] = (
    # 14 superpowers skills (MIT, Jesse Vincent) — see ./superpowers/LICENSE
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
    # llm-wiki (project-local) — see ./llm-wiki/LICENSE
    BundledSkill("gf-llm-wiki",                       "bundled_skills/llm-wiki/SKILL.md",                                   True),
)


# Hosts that don't accept a plain SKILL.md — they need format adapters
# (.mdc for cursor, GEMINI.md injection for gemini). v2 work; skipped for now.
_UNSUPPORTED_HOSTS = frozenset({"cursor", "gemini"})


def all_bundled() -> tuple[BundledSkill, ...]:
    """Return the full tuple of bundled skills."""
    return _BUNDLED


def supports_host(host_name: str) -> bool:
    """True if bundled skills can be installed for this host."""
    return host_name not in _UNSUPPORTED_HOSTS


def bundled_skill_dir(host, skill_name: str, *, root: Path) -> Path:
    """Target directory for installing `skill_name` on `host`.

    Formula: `root/<host.marker>/<up-to-skills>/<skill_name>/`.

    Replaces the trailing `graphify` segment of `host.skill_subpath` with
    `skill_name`. Falls back to `root/<host.marker>/skills/<skill_name>/`
    if the host's subpath doesn't end in `graphify` (defensive — no current
    host falls through, but `cursor`'s `rules/` subpath does, and we skip
    cursor entirely via `supports_host`).

    Worked examples:
        claude:     ~/.claude/skills/gf-brainstorming/
        codex:      ~/.codex/skills/gf-brainstorming/
        aider:      ~/.aider/gf-brainstorming/         (no skills/ parent)
        pi:         ~/.pi/agent/skills/gf-brainstorming/  (extra agent/ prefix)
        mobilecoder: ~/.mobilecoder/skills/gf-brainstorming/
    """
    parts = host.skill_subpath.parts
    if parts and parts[-1] == "graphify":
        new_subpath = Path(*parts[:-1]) / skill_name
    else:
        new_subpath = Path("skills") / skill_name
    return root / host.marker / new_subpath
```

- [ ] **Step 2: Run the registry tests, verify they pass**

Run: `pytest tests/test_bundled_skills.py::TestBundledSkillsRegistry -v`
Expected: 6 passed.

- [ ] **Step 3: Commit**

```bash
git add graphify/installer/bundled_skills.py tests/test_bundled_skills.py tests/conftest.py
git commit -m "feat(installer): add bundled_skills registry with 15 gf- prefixed entries"
```

---

### Task 2.3: Failing test for `bundled_skill_dir()` path derivation

**Files:**
- Modify: `tests/test_bundled_skills.py` (append a new test class)

- [ ] **Step 1: Append the path-derivation test class**

Append to `tests/test_bundled_skills.py`:

```python
class TestBundledSkillDir:
    """`bundled_skill_dir()` must produce the right path per host."""

    @pytest.mark.parametrize("host_name,expected_suffix", [
        ("claude",      ".claude/skills/gf-brainstorming"),
        ("codex",       ".codex/skills/gf-brainstorming"),
        ("aider",       ".aider/gf-brainstorming"),                # no skills/ parent
        ("pi",          ".pi/agent/skills/gf-brainstorming"),     # extra agent/ prefix
        ("mobilecoder", ".mobilecoder/skills/gf-brainstorming"),
    ])
    def test_path_for_supported_hosts(self, tmp_path, host_name, expected_suffix):
        host = next(h for h in KNOWN_HOSTS if h.name == host_name)
        result = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path)
        assert str(result).endswith(expected_suffix), (
            f"got {result}, expected suffix {expected_suffix}"
        )

    def test_unknown_skill_name_still_works(self, tmp_path):
        """Function takes any name, not just registered ones."""
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        result = bundled_skill_dir(host, "gf-anything-future", root=tmp_path)
        assert result == tmp_path / ".claude" / "skills" / "gf-anything-future"

    def test_cursor_subpath_falls_back_to_skills_layout(self, tmp_path):
        """cursor has subpath `rules` (not ending in graphify) → defensive fallback."""
        host = next(h for h in KNOWN_HOSTS if h.name == "cursor")
        result = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path)
        assert result == tmp_path / ".cursor" / "skills" / "gf-brainstorming"
```

- [ ] **Step 2: Run the test, verify it passes (already implemented)**

Run: `pytest tests/test_bundled_skills.py::TestBundledSkillDir -v`
Expected: 7 passed (the implementation from Task 2.2 already covers these cases).

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundled_skills.py
git commit -m "test(bundled-skills): per-host path derivation tests"
```

---

### Task 2.4: Failing test for `supports_host()`

**Files:**
- Modify: `tests/test_bundled_skills.py`

- [ ] **Step 1: Append the supports_host test class**

```python
class TestSupportsHost:
    """`supports_host()` returns False for cursor/gemini, True otherwise."""

    @pytest.mark.parametrize("host_name", ["claude", "codex", "opencode", "kilo",
                                            "aider", "copilot", "claw", "droid",
                                            "trae", "kiro", "pi", "vscode", "amp",
                                            "agents", "antigravity", "windows",
                                            "codebuddy", "hermes", "trae-cn",
                                            "mobilecoder"])
    def test_supports_common_hosts(self, host_name):
        assert supports_host(host_name) is True

    @pytest.mark.parametrize("host_name", ["cursor", "gemini"])
    def test_skips_format_incompatible_hosts(self, host_name):
        assert supports_host(host_name) is False
```

- [ ] **Step 2: Run, verify passes**

Run: `pytest tests/test_bundled_skills.py::TestSupportsHost -v`
Expected: 21 passed (19 supported + 2 unsupported).

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundled_skills.py
git commit -m "test(bundled-skills): supports_host coverage"
```

---

### Task 2.5: Failing test for frontmatter `name:` correctness

**Files:**
- Modify: `tests/test_bundled_skills.py`

- [ ] **Step 1: Append the frontmatter test class**

```python
class TestBundledSkillsFrontmatter:
    """Each SKILL.md's frontmatter `name:` must equal BundledSkill.name."""

    def test_all_skills_have_valid_yaml_frontmatter(self, package_root: Path):
        import yaml
        for s in all_bundled():
            text = (package_root / s.source_subpath).read_text(encoding="utf-8")
            assert text.startswith("---\n"), f"{s.source_subpath}: no frontmatter"
            end = text.find("\n---", 4)
            assert end > 0, f"{s.source_subpath}: unterminated frontmatter"
            fm = yaml.safe_load(text[4:end])
            assert isinstance(fm, dict), f"{s.source_subpath}: frontmatter not a YAML mapping"
            assert "name" in fm, f"{s.source_subpath}: missing `name` field"
            assert "description" in fm, f"{s.source_subpath}: missing `description` field"

    def test_frontmatter_name_matches_registry(self, package_root: Path):
        import yaml
        for s in all_bundled():
            text = (package_root / s.source_subpath).read_text(encoding="utf-8")
            end = text.find("\n---", 4)
            fm = yaml.safe_load(text[4:end])
            assert fm["name"] == s.name, (
                f"{s.source_subpath}: frontmatter name `{fm['name']}` != registry `{s.name}`"
            )
```

- [ ] **Step 2: Run, verify passes**

Run: `pytest tests/test_bundled_skills.py::TestBundledSkillsFrontmatter -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundled_skills.py
git commit -m "test(bundled-skills): frontmatter name correctness"
```

---

## Phase 3: Installer logic (TDD)

### Task 3.1: Failing test for `copy_bundled_skills()` basic write

**Files:**
- Modify: `tests/test_bundled_skills.py`

- [ ] **Step 1: Append the install test class**

```python
class TestCopyBundledSkills:
    """`copy_bundled_skills()` writes SKILL.md for each supported host."""

    def _setup_fake_package(self, tmp_path: Path) -> Path:
        """Build a minimal graphify/ package dir under tmp_path with the
        15 bundled SKILL.md files. Mirrors the real layout.
        """
        pkg = tmp_path / "graphify"
        for s in all_bundled():
            f = pkg / s.source_subpath
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text(
                f"---\nname: {s.name}\ndescription: stub\n---\n# {s.name}\n",
                encoding="utf-8",
            )
        # Superpowers LICENSE for the registry's structural test
        (pkg / "bundled_skills" / "superpowers" / "LICENSE").write_text(
            "MIT\n", encoding="utf-8"
        )
        # llm-wiki references/ sidecar
        (pkg / "bundled_skills" / "llm-wiki" / "references").mkdir(parents=True, exist_ok=True)
        (pkg / "bundled_skills" / "llm-wiki" / "references" / "x.md").write_text(
            "ref\n", encoding="utf-8"
        )
        return pkg

    @pytest.mark.parametrize("host_name", ["claude", "codex", "opencode", "kilo",
                                            "aider", "pi", "windows", "vscode",
                                            "amp", "agents"])
    def test_writes_skills_for_supported_hosts(self, tmp_path, host_name):
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == host_name)
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        target = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path / "home")
        assert (target / "SKILL.md").exists(), f"missing {target}/SKILL.md"

    def test_writes_llm_wiki_references_sidecar(self, tmp_path):
        """gf-llm-wiki has has_references=True → references/ must be copied."""
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        target = bundled_skill_dir(host, "gf-llm-wiki", root=tmp_path / "home")
        assert (target / "SKILL.md").exists()
        assert (target / "references" / "x.md").exists()

    def test_does_not_write_references_for_superpowers(self, tmp_path):
        """gf-brainstorming has has_references=False → no references/ written."""
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        target = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path / "home")
        assert not (target / "references").exists()

    @pytest.mark.parametrize("host_name", ["cursor", "gemini"])
    def test_skips_unsupported_hosts(self, tmp_path, host_name):
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == host_name)
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        # Nothing under the host marker should have any SKILL.md
        marker = tmp_path / "home" / host.marker
        if marker.exists():
            assert not any(marker.rglob("SKILL.md"))

    def test_always_overwrites_existing(self, tmp_path):
        """Always-overwrite semantics: any pre-existing SKILL.md is replaced."""
        from graphify.installer.skill_copy import copy_bundled_skills
        pkg = self._setup_fake_package(tmp_path / "pkg")
        host = next(h for h in KNOWN_HOSTS if h.name == "claude")
        target_dir = bundled_skill_dir(host, "gf-brainstorming", root=tmp_path / "home")
        target_dir.mkdir(parents=True)
        (target_dir / "SKILL.md").write_text("# OLD USER CONTENT — should be replaced", encoding="utf-8")
        copy_bundled_skills(host, root=tmp_path / "home", package_root=pkg)
        assert "# OLD USER CONTENT" not in (target_dir / "SKILL.md").read_text(encoding="utf-8")
```

- [ ] **Step 2: Run, verify all FAIL (function doesn't exist yet)**

Run: `pytest tests/test_bundled_skills.py::TestCopyBundledSkills -v`
Expected: ALL tests fail with `ImportError` or `AttributeError` (no `copy_bundled_skills` in `skill_copy`).

---

### Task 3.2: Implement `copy_bundled_skills()`

**Files:**
- Modify: `graphify/installer/skill_copy.py`

- [ ] **Step 1: Add the import**

At the top of `graphify/installer/skill_copy.py`, after the existing imports, add:

```python
from graphify.installer.bundled_skills import (
    all_bundled,
    bundled_skill_dir,
    supports_host,
)
```

- [ ] **Step 2: Append the new function**

Append to `graphify/installer/skill_copy.py`:

```python
def copy_bundled_skills(
    host: Host,
    *,
    root: Path,
    package_root: Optional[Path] = None,
) -> list[Path]:
    """Install all bundled (gf-*) skills for `host` under `root`.

    For each `BundledSkill`:
      - Compute target dir via `bundled_skill_dir(host, skill.name, root=root)`.
      - Read SKILL.md body from `package_root / skill.source_subpath` (or
        `importlib.resources` if `package_root is None`).
      - `target_dir.mkdir(parents=True, exist_ok=True)` and write the body.
      - If `skill.has_references`, also copy a `references/` sidecar.

    Always-overwrite semantics: any pre-existing file is replaced. The
    `gf-` namespace prefix ensures this never collides with a user's
    separately-installed plugin.
    """
    if not supports_host(host.name):
        return []

    written: list[Path] = []
    for skill in all_bundled():
        target_dir = bundled_skill_dir(host, skill.name, root=root)
        target_dir.mkdir(parents=True, exist_ok=True)

        # Read body.
        if package_root is not None:
            src = package_root / skill.source_subpath
            body = src.read_text(encoding="utf-8") if src.exists() else ""
        else:
            try:
                body = files("graphify").joinpath(*skill.source_subpath.split("/")).read_text(encoding="utf-8")
            except (FileNotFoundError, ModuleNotFoundError, TypeError):
                body = ""

        if not body:
            import sys
            print(
                f"[graphify-installer] warn: bundled skill `{skill.name}` "
                f"body missing at `{skill.source_subpath}`; skipping",
                file=sys.stderr,
            )
            continue

        target = target_dir / "SKILL.md"
        target.write_text(body, encoding="utf-8")
        written.append(target)

        # Optional references/ sidecar.
        if skill.has_references:
            refs_rel = (Path(skill.source_subpath).parent / "references").as_posix()
            if package_root is not None:
                src_refs = package_root / refs_rel
            else:
                from importlib.resources import as_file
                try:
                    ref_resource = files("graphify").joinpath(*refs_rel.split("/"))
                    with as_file(ref_resource) as p:
                        src_refs = p
                except (FileNotFoundError, ModuleNotFoundError, TypeError):
                    src_refs = None
            if src_refs is not None and src_refs.exists():
                dst_refs = target_dir / "references"
                if dst_refs.exists():
                    shutil.rmtree(dst_refs)
                shutil.copytree(src_refs, dst_refs)

    if written:
        print(
            f"[graphify-installer] installed {len(written)} bundled skills for "
            f"{host.name}: {', '.join(p.parent.name for p in written)}",
            flush=True,
        )
    return written
```

- [ ] **Step 3: Run the install tests, verify they pass**

Run: `pytest tests/test_bundled_skills.py::TestCopyBundledSkills -v`
Expected: 14 passed (10 supported hosts + 1 references + 1 no-references + 2 unsupported + 1 overwrite).

- [ ] **Step 4: Commit**

```bash
git add graphify/installer/skill_copy.py
git commit -m "feat(installer): copy_bundled_skills writes 15 gf- skills per host"
```

---

## Phase 4: Wire into installer orchestrator

### Task 4.1: Call `copy_bundled_skills()` after `copy_skill()` in `__init__.py`

**Files:**
- Modify: `graphify/installer/__init__.py`

- [ ] **Step 1: Find the existing `copy_skill()` call**

In `graphify/installer/__init__.py`, locate the line that calls `copy_skill(...)` (search for `copy_skill(`). It is inside the per-host install loop.

- [ ] **Step 2: Add the `copy_bundled_skills()` call immediately after**

Right after the `copy_skill(...)` call (same indentation), add:

```python
        copy_bundled_skills(host, root=root, package_root=package_root)
```

If the existing line is wrapped in a `with` block or helper function, ensure the new call passes the same arguments.

- [ ] **Step 3: Run all installer tests, verify nothing breaks**

Run: `pytest tests/test_installer_skill_copy.py tests/test_install_roundtrip.py -v`
Expected: all pass.

- [ ] **Step 4: Commit**

```bash
git add graphify/installer/__init__.py
git commit -m "feat(installer): wire copy_bundled_skills into per-host install loop"
```

---

### Task 4.2: Failing round-trip test enhancement

**Files:**
- Modify: `tests/test_install_roundtrip.py`

- [ ] **Step 1: Locate the per-host round-trip loop**

Open `tests/test_install_roundtrip.py`. Find the function or loop that iterates over platforms and asserts a SKILL.md was installed.

- [ ] **Step 2: Append two `gf-*` assertions per host**

After the existing assertion that `graphify/SKILL.md` exists, append:

```python
        # New: bundled skills under the gf- namespace
        assert (dest / "gf-brainstorming" / "SKILL.md").exists()
        assert (dest / "gf-llm-wiki" / "SKILL.md").exists()
```

(Adjust `dest` to whatever local variable holds the host's skill directory.)

- [ ] **Step 3: Run the round-trip test, verify it FAILS**

Run: `pytest tests/test_install_roundtrip.py -v`
Expected: FAIL with `FileNotFoundError` for `gf-brainstorming/SKILL.md`.

If the test PASSES unexpectedly, the bundled skills are already being installed by the real package data path (no `package_root` override). In that case the test is verifying real behavior and skip Step 3 (no failure → it's a tautology). Note the result and proceed to Step 4 anyway.

- [ ] **Step 4: Commit**

```bash
git add tests/test_install_roundtrip.py
git commit -m "test(install): assert gf- skills installed per-host in round-trip"
```

---

## Phase 5: Package data + wheel verification

### Task 5.1: Update `pyproject.toml` package-data

**Files:**
- Modify: `pyproject.toml`

- [ ] **Step 1: Locate the `[tool.setuptools.package-data]` section**

Search for `[tool.setuptools.package-data]` in `pyproject.toml`. The `graphify = [...]` list already contains entries like `skill.md`, `skills/*/references/*.md`, `assets/vis-network.min.js`.

- [ ] **Step 2: Append five `bundled_skills` globs**

Add these entries to the `graphify = [...]` list (keep them adjacent to the existing `skills/*/references/*.md` line for clarity):

```toml
    "bundled_skills/**/*.md",
    "bundled_skills/**/*.txt",
    "bundled_skills/**/*.sh",
    "bundled_skills/**/*.ps1",
    "bundled_skills/**/*.js",
    "bundled_skills/**/*.tsv",
```

Final list snippet should look like:

```toml
graphify = [
    "skill.md", "skill-codex.md", ..., "skill-pi.md", "skill-devin.md",
    "skills/*/references/*.md",
    "always_on/*.md",
    "assets/vis-network.min.js",
    "bundled_skills/**/*.md",
    "bundled_skills/**/*.txt",
    "bundled_skills/**/*.sh",
    "bundled_skills/**/*.ps1",
    "bundled_skills/**/*.js",
    "bundled_skills/**/*.tsv",
]
```

- [ ] **Step 3: Build the wheel and verify it contains bundled skills**

```bash
$PYTHON -m pip wheel . --no-deps --wheel-dir dist/ 2>&1 | tail -3
$PYTHON -m zipfile -l dist/graphifyy-*.whl | grep bundled_skills | head -20
```

Expected: at least 14 lines containing `bundled_skills/superpowers/<skill>/SKILL.md` and 1 line for `bundled_skills/llm-wiki/SKILL.md`.

- [ ] **Step 4: Commit**

```bash
git add pyproject.toml
git commit -m "build: include bundled_skills in package-data globs"
```

---

### Task 5.2: Add wheel import test

**Files:**
- Modify: `tests/test_bundled_skills.py`

- [ ] **Step 1: Append the wheel-content test class**

```python
class TestBundledSkillsInInstalledPackage:
    """Verify bundled_skills is accessible via importlib.resources after install."""

    def test_superpowers_skills_listed(self):
        import importlib.resources
        root = importlib.resources.files("graphify") / "bundled_skills" / "superpowers"
        skill_dirs = sorted(
            p.name for p in root.iterdir()
            if p.is_dir() and p.name not in {"LICENSE", "NOTICE"}  # not files, treat NOTICE/LICENSE as files
        )
        # Note: LICENSE/NOTICE are FILES, not dirs — the iterdir() filter above is defensive
        assert len(skill_dirs) >= 14, f"got {len(skill_dirs)}: {skill_dirs}"

    def test_llm_wiki_present(self):
        import importlib.resources
        root = importlib.resources.files("graphify") / "bundled_skills" / "llm-wiki"
        assert (root / "SKILL.md").is_file()
```

- [ ] **Step 2: Run, verify passes**

Run: `pytest tests/test_bundled_skills.py::TestBundledSkillsInInstalledPackage -v`
Expected: 2 passed.

- [ ] **Step 3: Commit**

```bash
git add tests/test_bundled_skills.py
git commit -m "test(bundled-skills): importlib.resources reachability"
```

---

### Task 5.3: Add pre-flight check to `build_windows_installer.sh`

**Files:**
- Modify: `tools/build_windows_installer.sh`

- [ ] **Step 1: Locate the `pip wheel .` step**

In `tools/build_windows_installer.sh`, find the line `$PYTHON -m pip wheel . --no-deps --wheel-dir "$WHEELHOUSE" >/dev/null`. It appears around line 50.

- [ ] **Step 2: Insert the pre-flight check immediately after**

Add this block right after the `pip wheel` line:

```bash
# 2.5 Pre-flight: confirm bundled_skills made it into the installed package.
# If a snapshot file is missing, this fails the build loudly instead of
# shipping a graphify.exe that's silently missing skills.
echo "==> Pre-flight: verifying bundled_skills in installed package..."
"$VENV/Scripts/python.exe" -c "
from importlib.resources import files
sp = files('graphify') / 'bundled_skills' / 'superpowers'
n = sum(1 for p in sp.iterdir() if p.is_dir())
assert n == 14, f'expected 14 superpowers skill dirs, got {n}'
assert (files('graphify') / 'bundled_skills' / 'llm-wiki' / 'SKILL.md').is_file(), 'llm-wiki SKILL.md missing'
print(f'==> Pre-flight OK: {n} superpowers + llm-wiki present')
"
```

(Place this AFTER step 3 ("Building offline venv") so `$VENV` is defined. If the script's current structure has `pip wheel` before the venv, move the pre-flight to after step 3 instead.)

- [ ] **Step 3: Commit**

```bash
git add tools/build_windows_installer.sh
git commit -m "ci: pre-flight check that bundled_skills survived wheel install"
```

---

## Phase 6: Documentation

### Task 6.1: Create repo-root `NOTICE`

**Files:**
- Create: `NOTICE`

- [ ] **Step 1: Write NOTICE**

Create `NOTICE` with this content:

```
graphify
Copyright 2024-...

This product includes software developed by third parties:

────────────────────────────────────────────────────────────
superpowers-dev
Bundled under: graphify/bundled_skills/superpowers/
Copyright:     2025 Jesse Vincent
License:       MIT — see graphify/bundled_skills/superpowers/LICENSE
Source:        https://github.com/superpowers-dev/superpowers-dev

Renamed for graphify (frontmatter `name:` field, directory basename
unchanged). See graphify/bundled_skills/README.md.
────────────────────────────────────────────────────────────
llm-wiki
Bundled under: graphify/bundled_skills/llm-wiki/
Copyright:     ...
License:       see graphify/bundled_skills/llm-wiki/LICENSE
────────────────────────────────────────────────────────────
```

(Fill in the llm-wiki copyright line from `graphify/bundled_skills/llm-wiki/LICENSE`.)

- [ ] **Step 2: Commit**

```bash
git add NOTICE
git commit -m "docs: NOTICE listing bundled third-party projects"
```

---

### Task 6.2: Update `CHANGELOG.md`

**Files:**
- Modify: `CHANGELOG.md`

- [ ] **Step 1: Append a new entry to `## Unreleased`**

In `CHANGELOG.md`, find the `## Unreleased` section. Add this bullet just before the existing offline-installer entry (keep the offline-installer entry intact):

```markdown
- Feat: offline installer also bundles 15 community skills under the `gf-` namespace (14 superpowers + `gf-llm-wiki`). After `graphify-installer.exe` runs, the host's skill directory contains `gf-brainstorming/`, `gf-writing-plans/`, `gf-subagent-driven-development/`, `gf-test-driven-development/`, `gf-systematic-debugging/`, `gf-using-git-worktrees/`, `gf-requesting-code-review/`, `gf-receiving-code-review/`, `gf-executing-plans/`, `gf-finishing-a-development-branch/`, `gf-dispatching-parallel-agents/`, `gf-using-superpowers/`, `gf-verification-before-completion/`, `gf-writing-skills/`, and `gf-llm-wiki/`. Namespaced with `gf-` so always-overwrite install semantics can never collide with user-installed plugins. See `graphify/bundled_skills/README.md`.
```

- [ ] **Step 2: Commit**

```bash
git add CHANGELOG.md
git commit -m "docs(changelog): bundled skills under gf- namespace"
```

---

### Task 6.3: Update `docs/operations/offline-installer.md`

**Files:**
- Modify: `docs/operations/offline-installer.md`

- [ ] **Step 1: Locate the "What's inside the .exe" section**

In `docs/operations/offline-installer.md`, find the heading `## What's inside the .exe` (around line 65). Note the bullet list of bundled components.

- [ ] **Step 2: Append a paragraph about bundled skills**

After the last bullet (the "Not bundled" note), add this paragraph:

```markdown
The installer also ships 15 community skills under the `gf-` namespace
(14 superpowers + `gf-llm-wiki`). They are placed in the host's skill
directory alongside `graphify/` and are immediately discoverable by the
AI Agent host — trigger them via `/gf-brainstorming`, `/gf-writing-plans`,
etc. The `gf-` prefix guarantees no collision with a user's separately
installed superpowers plugin. See `graphify/bundled_skills/README.md`.
```

- [ ] **Step 3: Commit**

```bash
git add docs/operations/offline-installer.md
git commit -m "docs(offline-installer): bundled skills under gf- namespace"
```

---

## Phase 7: Final verification

### Task 7.1: Full test suite green

- [ ] **Step 1: Run all installer + bundled-skills tests**

Run: `pytest tests/test_bundled_skills.py tests/test_installer_skill_copy.py tests/test_install_roundtrip.py -v`
Expected: all pass.

- [ ] **Step 2: Run the full suite to catch unrelated regressions**

Run: `pytest tests/ -q --ignore=tests/test_analyze.py 2>&1 | tail -20`
Expected: zero failures attributable to this change. (Pre-existing failures unrelated to installer are acceptable; if any are new, investigate.)

---

## Self-Review (against spec)

**1. Spec coverage:**

| Spec section | Task(s) |
|---|---|
| §3 Decisions (15 skills, snapshot+LICENSE, 14 hosts, single body, gf- prefix, always overwrite, no manifest, no --force, v2 cursor/gemini) | 1.1–1.4, 2.1–2.5, 3.1–3.2 |
| §2 Repository layout (`graphify/bundled_skills/{superpowers,llm-wiki}/`) | 1.1–1.4 |
| §3 Package data (5 globs) | 5.1 |
| §4 Installer logic (`bundled_skills.py` + `copy_bundled_skills()` + caller) | 2.1–2.5, 3.1–3.2, 4.1 |
| §5 Build / Nuitka (zero changes, pre-flight check) | 5.3 |
| §6 Tests (4 test classes + round-trip enhancement) | 2.1, 2.3, 2.4, 2.5, 3.1, 4.2, 5.2 |
| §7 Documentation (CHANGELOG, offline-installer.md, NOTICE, README) | 1.4, 6.1, 6.2, 6.3 |
| §8 Migration / backward compat | No code change needed; covered by tests showing no regression |

**2. Placeholder scan:** No "TBD"/"TODO"/"implement later" in the plan. The "fill in llm-wiki copyright" instruction in Task 6.1 points to a specific file to read.

**3. Type consistency:**
- `BundledSkill.name`, `.source_subpath`, `.has_references` — defined Task 2.2, used Tasks 2.1, 3.1, 3.2 ✓
- `bundled_skill_dir(host, skill_name, *, root)` — defined Task 2.2, used Tasks 2.3, 3.1, 3.2 ✓
- `supports_host(host_name)` — defined Task 2.2, used Task 3.2 ✓
- `copy_bundled_skills(host, *, root, package_root=None)` — defined Task 3.2, used Tasks 3.1, 4.1 ✓
- `_UNSUPPORTED_HOSTS = {"cursor", "gemini"}` — defined Task 2.2, used Task 3.2 ✓

No type drift.