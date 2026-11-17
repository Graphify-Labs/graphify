"""Tests for graphify claude install / uninstall commands."""
from pathlib import Path
import pytest
from graphify.__main__ import claude_install, claude_uninstall, _CLAUDE_MD_MARKER, _CLAUDE_MD_SECTION


# ---------------------------------------------------------------------------
# install
# ---------------------------------------------------------------------------

def test_install_creates_claude_md(tmp_path):
    """Creates CLAUDE.md when none exists."""
    claude_install(tmp_path)
    target = tmp_path / "CLAUDE.md"
    assert target.exists()
    assert _CLAUDE_MD_MARKER in target.read_text()


def test_install_contains_expected_rules(tmp_path):
    """Written section includes the three rules."""
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert "GRAPH_REPORT.md" in content
    assert "wiki/index.md" in content
    assert "graphify update" in content


def test_install_appends_to_existing_claude_md(tmp_path):
    """Appends to an existing CLAUDE.md without clobbering it."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Existing content\n\nSome rules here.\n")
    claude_install(tmp_path)
    content = target.read_text()
    assert "Existing content" in content
    assert _CLAUDE_MD_MARKER in content


def test_install_is_idempotent(tmp_path, capsys):
    """Running install twice does not duplicate the section."""
    claude_install(tmp_path)
    claude_install(tmp_path)
    content = (tmp_path / "CLAUDE.md").read_text()
    assert content.count(_CLAUDE_MD_MARKER) == 1
    captured = capsys.readouterr()
    assert "already configured" in captured.out


def test_install_idempotent_message(tmp_path, capsys):
    """Second install prints the 'already configured' message."""
    claude_install(tmp_path)
    capsys.readouterr()  # clear first call output
    claude_install(tmp_path)
    out = capsys.readouterr().out
    assert "already configured" in out


# ---------------------------------------------------------------------------
# uninstall
# ---------------------------------------------------------------------------

def test_uninstall_removes_section(tmp_path):
    """Removes the graphify section after it was installed."""
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    target = tmp_path / "CLAUDE.md"
    # File may or may not exist depending on whether it was empty
    if target.exists():
        assert _CLAUDE_MD_MARKER not in target.read_text()


def test_uninstall_preserves_other_content(tmp_path):
    """Uninstall keeps pre-existing content outside the graphify section."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# My Project\n\nSome rules.\n")
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    assert target.exists()
    content = target.read_text()
    assert "My Project" in content
    assert "Some rules" in content
    assert _CLAUDE_MD_MARKER not in content


def test_uninstall_no_op_when_not_installed(tmp_path, capsys):
    """Uninstall on a CLAUDE.md without graphify section prints a message and exits cleanly."""
    target = tmp_path / "CLAUDE.md"
    target.write_text("# Other stuff\n")
    claude_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "not found" in out or "nothing to do" in out


def test_uninstall_no_op_when_no_file(tmp_path, capsys):
    """Uninstall when no CLAUDE.md exists prints a message and exits cleanly."""
    claude_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "No CLAUDE.md" in out or "nothing to do" in out


# ---------------------------------------------------------------------------
# settings.json PreToolUse hook
# ---------------------------------------------------------------------------

def test_install_creates_settings_json(tmp_path):
    """claude_install also writes .claude/settings.json with PreToolUse hook."""
    import json
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    assert settings_path.exists()
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {}).get("PreToolUse", [])
    assert any(h.get("matcher") == "Bash|Grep" for h in hooks)


def test_install_settings_json_idempotent(tmp_path):
    """Running claude_install twice does not duplicate the PreToolUse hook."""
    import json
    claude_install(tmp_path)
    claude_install(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    settings = json.loads(settings_path.read_text())
    hooks = settings.get("hooks", {}).get("PreToolUse", [])
    bash_hooks = [h for h in hooks if h.get("matcher") == "Bash|Grep" and "graphify" in str(h)]
    assert len(bash_hooks) == 1


def test_uninstall_removes_settings_hook(tmp_path):
    """claude_uninstall removes the PreToolUse hook from settings.json."""
    import json
    claude_install(tmp_path)
    claude_uninstall(tmp_path)
    settings_path = tmp_path / ".claude" / "settings.json"
    if settings_path.exists():
        settings = json.loads(settings_path.read_text())
        hooks = settings.get("hooks", {}).get("PreToolUse", [])
        assert not any(h.get("matcher") == "Bash|Grep" and "graphify" in str(h) for h in hooks)


# ---------------------------------------------------------------------------
# local-only variants: settings.local.json / CLAUDE.local.md (#1731)
# ---------------------------------------------------------------------------

def test_uninstall_removes_hook_from_settings_local_json(tmp_path):
    """A hook relocated to .claude/settings.local.json is removed on uninstall."""
    import json
    claude_install(tmp_path)
    # User moved the hook out of the committed settings.json into the local-only file.
    (tmp_path / ".claude" / "settings.json").rename(tmp_path / ".claude" / "settings.local.json")
    claude_uninstall(tmp_path)
    local = tmp_path / ".claude" / "settings.local.json"
    hooks = json.loads(local.read_text()).get("hooks", {}).get("PreToolUse", [])
    assert not any("graphify" in str(h) for h in hooks)


def test_uninstall_removes_section_from_dot_claude_local_md(tmp_path):
    """Instructions relocated to .claude/CLAUDE.local.md are removed on uninstall."""
    claude_install(tmp_path)
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_text((tmp_path / "CLAUDE.md").read_text())
    (tmp_path / "CLAUDE.md").unlink()
    claude_uninstall(tmp_path)
    assert not local_md.exists() or _CLAUDE_MD_MARKER not in local_md.read_text()


def test_uninstall_removes_section_from_root_claude_local_md(tmp_path):
    """Instructions relocated to root CLAUDE.local.md are removed on uninstall."""
    claude_install(tmp_path)
    local_md = tmp_path / "CLAUDE.local.md"
    local_md.write_text((tmp_path / "CLAUDE.md").read_text())
    (tmp_path / "CLAUDE.md").unlink()
    claude_uninstall(tmp_path)
    assert not local_md.exists() or _CLAUDE_MD_MARKER not in local_md.read_text()


def test_uninstall_cleans_both_standard_and_local(tmp_path):
    """When the section lives in both CLAUDE.md and a local variant, both are cleaned."""
    claude_install(tmp_path)
    claude_md = tmp_path / "CLAUDE.md"
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_text(claude_md.read_text())  # duplicated into the local file too
    claude_uninstall(tmp_path)
    for f in (claude_md, local_md):
        assert not f.exists() or _CLAUDE_MD_MARKER not in f.read_text()


def test_uninstall_preserves_other_content_in_local_md(tmp_path):
    """Uninstall keeps non-graphify content in CLAUDE.local.md."""
    claude_install(tmp_path)
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_text("# Local notes\n\nkeep me\n\n" + (tmp_path / "CLAUDE.md").read_text())
    claude_uninstall(tmp_path)
    assert local_md.exists()
    content = local_md.read_text()
    assert "Local notes" in content
    assert "keep me" in content
    assert _CLAUDE_MD_MARKER not in content


def test_uninstall_tolerates_unreadable_local_md(tmp_path):
    """A non-UTF-8 CLAUDE.local.md must not abort uninstall (it has no marker to strip)."""
    claude_install(tmp_path)
    local_md = tmp_path / ".claude" / "CLAUDE.local.md"
    local_md.write_bytes(b"\xff\xfe not valid utf-8 \x80\x81")
    claude_uninstall(tmp_path)  # must not raise
    assert local_md.read_bytes() == b"\xff\xfe not valid utf-8 \x80\x81"  # left untouched


# ---------------------------------------------------------------------------
# install target: the file Claude Code actually reads (CLAUDE.md or AGENTS.md)
# ---------------------------------------------------------------------------
# Claude Code's default instructionFiles mode ("claude-md-or-agents-md") reads a
# project's AGENTS.md only when no CLAUDE.md exists in the project or any directory
# above it. Creating a CLAUDE.md beside an AGENTS.md therefore hides that AGENTS.md
# (and every ancestor AGENTS.md) from Claude Code.

def _isolated(tmp_path, monkeypatch=None):
    """A project directory whose ancestors hold no instruction files.

    The ancestor walk mirrors Claude Code and runs to the filesystem root, so a
    CLAUDE.md above tmp_path on the test machine would change the outcome: skip
    rather than pass or fail for the wrong reason. CLAUDE_CONFIG_DIR is pinned
    inside tmp_path so the tester's own Claude config never matters.
    """
    for d in tmp_path.resolve().parents:
        for name in ("CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"):
            if (d / name).is_file():
                pytest.skip(f"ambient {d / name} above tmp_path decides Claude Code's choice")
    if monkeypatch is not None:
        monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "config"))
    project = tmp_path / "home" / "repo"
    project.mkdir(parents=True)
    return project


def test_install_writes_agents_md_when_claude_reads_it(tmp_path, monkeypatch):
    """With only AGENTS.md, the section goes there and no CLAUDE.md is created."""
    project = _isolated(tmp_path, monkeypatch)
    agents = project / "AGENTS.md"
    agents.write_text("# Project rules\n\nKeep this.\n")
    claude_install(project)
    assert not (project / "CLAUDE.md").exists()
    content = agents.read_text()
    assert "Keep this." in content
    assert content.count(_CLAUDE_MD_MARKER) == 1
    # The AGENTS.md block (a superset of the CLAUDE.md one) is written, so a later
    # Claude install does not strip lines other AGENTS.md readers rely on.
    assert "When the user types `/graphify`" in content


def test_install_writes_dot_claude_agents_md(tmp_path, monkeypatch):
    """Claude Code also reads .claude/AGENTS.md; with only that file, write it."""
    project = _isolated(tmp_path, monkeypatch)
    agents = project / ".claude" / "AGENTS.md"
    agents.parent.mkdir()
    agents.write_text("# Rules\n")
    claude_install(project)
    assert not (project / "CLAUDE.md").exists()
    assert _CLAUDE_MD_MARKER in agents.read_text()


def test_install_prefers_existing_claude_md_over_agents_md(tmp_path, monkeypatch):
    """An existing CLAUDE.md is what Claude Code reads, so it gets the section."""
    project = _isolated(tmp_path, monkeypatch)
    (project / "AGENTS.md").write_text("# Agents\n")
    (project / "CLAUDE.md").write_text("# Claude\n")
    claude_install(project)
    assert _CLAUDE_MD_MARKER in (project / "CLAUDE.md").read_text()
    assert (project / "AGENTS.md").read_text() == "# Agents\n"


def test_install_writes_existing_dot_claude_claude_md(tmp_path, monkeypatch):
    """An existing .claude/CLAUDE.md gets the section; no root CLAUDE.md appears."""
    project = _isolated(tmp_path, monkeypatch)
    (project / "AGENTS.md").write_text("# Agents\n")
    target = project / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_text("# Claude\n")
    claude_install(project)
    assert not (project / "CLAUDE.md").exists()
    assert _CLAUDE_MD_MARKER in target.read_text()
    assert (project / "AGENTS.md").read_text() == "# Agents\n"


@pytest.mark.parametrize("ancestor_file", ["CLAUDE.md", ".claude/CLAUDE.md", "CLAUDE.local.md"])
def test_install_uses_claude_md_when_an_ancestor_has_one(tmp_path, monkeypatch, ancestor_file):
    """A CLAUDE.md above the project stops Claude Code reading the project's
    AGENTS.md, so the section goes to a new CLAUDE.md, as before."""
    project = _isolated(tmp_path, monkeypatch)
    marker = project.parent / ancestor_file
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text("# Ancestor\n")
    (project / "AGENTS.md").write_text("# Agents\n")
    claude_install(project)
    assert _CLAUDE_MD_MARKER in (project / "CLAUDE.md").read_text()
    assert (project / "AGENTS.md").read_text() == "# Agents\n"


def test_uninstall_removes_section_from_dot_claude_claude_md(tmp_path, monkeypatch):
    """Uninstall cleans .claude/CLAUDE.md, which install may now write."""
    project = _isolated(tmp_path, monkeypatch)
    target = project / ".claude" / "CLAUDE.md"
    target.parent.mkdir()
    target.write_text("# Claude\n")
    claude_install(project)
    claude_uninstall(project)
    assert _CLAUDE_MD_MARKER not in target.read_text()


def test_uninstall_leaves_agents_md_section(tmp_path, monkeypatch, capsys):
    """Other agents read the same AGENTS.md section, so Claude uninstall keeps it
    and says so instead of silently breaking them."""
    project = _isolated(tmp_path, monkeypatch)
    agents = project / "AGENTS.md"
    agents.write_text("# Rules\n")
    claude_install(project)
    capsys.readouterr()
    claude_uninstall(project)
    assert _CLAUDE_MD_MARKER in agents.read_text()
    assert "AGENTS.md" in capsys.readouterr().out


def test_install_ignores_user_level_claude_md(tmp_path, monkeypatch):
    """Claude Code's user-level CLAUDE.md ($CLAUDE_CONFIG_DIR/CLAUDE.md, default
    ~/.claude/CLAUDE.md) is user memory, not a project file: it does not stop
    Claude Code reading the project's AGENTS.md, even when it sits in an ancestor."""
    project = _isolated(tmp_path, monkeypatch)
    user_dir = project.parent / ".claude"
    user_dir.mkdir()
    (user_dir / "CLAUDE.md").write_text("# User memory\n")
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(user_dir))
    agents = project / "AGENTS.md"
    agents.write_text("# Agents\n")
    claude_install(project)
    assert not (project / "CLAUDE.md").exists()
    assert _CLAUDE_MD_MARKER in agents.read_text()


def test_install_agents_md_is_idempotent(tmp_path, monkeypatch, capsys):
    """A second install into AGENTS.md changes nothing and says so."""
    project = _isolated(tmp_path, monkeypatch)
    agents = project / "AGENTS.md"
    agents.write_text("# Agents\n")
    claude_install(project)
    first = agents.read_text()
    capsys.readouterr()
    claude_install(project)
    assert agents.read_text() == first
    assert first.count(_CLAUDE_MD_MARKER) == 1
    assert "already configured" in capsys.readouterr().out


def test_project_install_git_hint_names_written_agents_md(tmp_path, monkeypatch, capsys):
    """`claude install --project` tells the user to add the file it wrote."""
    from graphify.install import _project_install
    project = _isolated(tmp_path, monkeypatch)
    (project / "AGENTS.md").write_text("# Agents\n")
    _project_install("claude", project)
    out = capsys.readouterr().out
    hint = [line for line in out.splitlines() if "git add" in line]
    assert hint and "AGENTS.md" in hint[-1] and "CLAUDE.md" not in hint[-1]


def test_uninstall_tolerates_unreadable_agents_md(tmp_path, monkeypatch):
    """An AGENTS.md that cannot be read must not stop uninstall removing the hook."""
    project = _isolated(tmp_path, monkeypatch)
    (project / "CLAUDE.md").write_text("# Claude\n")
    claude_install(project)
    (project / "AGENTS.md").mkdir()  # a directory: is_file() is False
    bad = project / ".claude" / "AGENTS.md"
    bad.write_text("x")
    real_read_text = Path.read_text

    def read_text(self, *args, **kwargs):
        if self.name == "AGENTS.md":
            raise PermissionError(13, "Permission denied", str(self))
        return real_read_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", read_text)
    claude_uninstall(project)
    settings = real_read_text(project / ".claude" / "settings.json")
    assert "graphify" not in settings


def test_uninstall_agents_md_only_has_no_contradicting_message(tmp_path, monkeypatch, capsys):
    """With only the AGENTS.md section, uninstall does not also claim nothing was found."""
    project = _isolated(tmp_path, monkeypatch)
    (project / "AGENTS.md").write_text("# Agents\n")
    claude_install(project)
    capsys.readouterr()
    claude_uninstall(project)
    out = capsys.readouterr().out
    assert "left in place" in out
    assert "nothing to do" not in out


def test_project_install_registers_skill_in_agents_md(tmp_path, monkeypatch):
    """`claude install --project` must not create .claude/CLAUDE.md beside an
    AGENTS.md Claude Code reads: the skill registration goes to AGENTS.md too."""
    from graphify.install import _project_install, _SKILL_REGISTRATION_MARKER
    project = _isolated(tmp_path, monkeypatch)
    agents = project / "AGENTS.md"
    agents.write_text("# Agents\n")
    _project_install("claude", project)
    assert not (project / ".claude" / "CLAUDE.md").exists()
    assert not (project / "CLAUDE.md").exists()
    lines = agents.read_text().splitlines()
    # Whole lines: "# graphify" (registration) is a substring of "## graphify" (section).
    assert _SKILL_REGISTRATION_MARKER in lines
    assert _CLAUDE_MD_MARKER in lines


def test_project_install_keeps_dot_claude_registration_without_agents_md(tmp_path, monkeypatch):
    """Without an AGENTS.md, the registration stays in .claude/CLAUDE.md as before."""
    from graphify.install import _project_install, _SKILL_REGISTRATION_MARKER
    project = _isolated(tmp_path, monkeypatch)
    _project_install("claude", project)
    assert _SKILL_REGISTRATION_MARKER in (project / ".claude" / "CLAUDE.md").read_text()


def test_project_uninstall_removes_registration_from_agents_md(tmp_path, monkeypatch):
    """Project uninstall removes the skill registration it put in AGENTS.md and
    keeps the user's own content."""
    from graphify.install import _project_install, _SKILL_REGISTRATION_MARKER
    project = _isolated(tmp_path, monkeypatch)
    agents = project / "AGENTS.md"
    agents.write_text("# Agents\n\nKeep me.\n")
    _project_install("claude", project)
    claude_uninstall(project, project=True)
    lines = agents.read_text().splitlines()
    assert "Keep me." in lines
    assert _SKILL_REGISTRATION_MARKER not in lines
