"""Vibe install lays down its full three-artifact always-on layer.

Mistral Vibe (github.com/mistralai/mistral-vibe) is Agent Skills-compliant and
has a first-class pre_tool hook system in `.vibe/hooks.toml`, so `graphify vibe
install` needs Claude Code parity: skill (with `user-invocable: true` for
`/graphify` slash-command autocomplete), AGENTS.md always-on section, AND
hooks.toml pre_tool entries that nudge grep/read toward `graphify query`.

Every test scopes HOME to `tmp_path/home` so a bare (non-project) install
lands in an isolated ~/.vibe rather than the developer's real home.
"""
import pytest

import graphify.__main__ as m


@pytest.fixture
def home(tmp_path, monkeypatch):
    """Redirect ~/.vibe to tmp_path/home/.vibe for the duration of the test."""
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: fake_home)
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


def test_project_install_writes_skill_agents_md_and_hooks(tmp_path, home):
    m._vibe_install(tmp_path, project=True)

    skill = tmp_path / ".vibe" / "skills" / "graphify" / "SKILL.md"
    references = tmp_path / ".vibe" / "skills" / "graphify" / "references"
    agents_md = tmp_path / "AGENTS.md"
    hooks_toml = tmp_path / ".vibe" / "hooks.toml"

    assert skill.exists(), "SKILL.md must be installed under .vibe/skills/"
    assert references.is_dir(), "shared agents references bundle must be copied"
    assert agents_md.exists(), "AGENTS.md always-on section must be written"
    assert hooks_toml.exists(), "pre_tool hooks must be registered"


def test_skill_frontmatter_is_user_invocable(tmp_path, home):
    """`user-invocable: true` is what makes /graphify show in vibe autocomplete."""
    m._vibe_install(tmp_path, project=True)
    body = (tmp_path / ".vibe" / "skills" / "graphify" / "SKILL.md").read_text(encoding="utf-8")
    assert body.startswith("---\n"), "SKILL.md must have YAML frontmatter"
    assert "user-invocable: true" in body, "vibe needs this to expose /graphify"
    assert "name: graphify" in body


def test_hooks_toml_shape_matches_vibe_pre_tool_schema(tmp_path, home):
    """Vibe's HookConfig requires: name (str), type (HookType), command (str).

    Optional/defaulted: match, timeout, strict, description. This test locks
    the full required contract so a regression that drops `name` (which Vibe
    would reject at parse time) doesn't silently pass CI.
    """
    import tomlkit

    m._vibe_install(tmp_path, project=True)
    doc = tomlkit.parse((tmp_path / ".vibe" / "hooks.toml").read_text(encoding="utf-8"))
    hooks = list(doc["hooks"])
    assert len(hooks) == 2, "one entry per matcher (grep, read_file)"

    matchers = {h["match"] for h in hooks}
    assert matchers == {"grep", "read_file"}, (
        f"unexpected matchers: {matchers}; vibe registers the read tool as `read_file` "
        f"and uses fnmatch — `read` alone never matches"
    )

    names = {h["name"] for h in hooks}
    assert names == {"graphify-nudge-search", "graphify-nudge-read"}, (
        f"vibe HookConfig requires `name`; got {names}"
    )

    for h in hooks:
        assert isinstance(h["name"], str) and h["name"], "name must be non-empty str"
        assert h["type"] == "pre_tool"
        assert isinstance(h["command"], str) and "graphify" in h["command"]
        assert "hook-guard" in h["command"]
        assert isinstance(h["timeout"], float)
        assert h["strict"] is False


def test_strict_flag_flows_only_to_read_hook(tmp_path, home):
    """--strict escalates read-guard blocking; grep-guard stays a nudge (matches claude)."""
    import tomlkit

    m._vibe_install(tmp_path, project=True, strict=True)
    doc = tomlkit.parse((tmp_path / ".vibe" / "hooks.toml").read_text(encoding="utf-8"))
    hooks = {h["match"]: h["command"] for h in doc["hooks"]}
    assert "--strict" in hooks["read_file"], "read guard must carry --strict when requested"
    assert "--strict" not in hooks["grep"], "search guard must not block; nudge only"


def test_install_is_idempotent_no_backup_churn(tmp_path, home):
    """Second install with same inputs must not rewrite files or drop .graphify-bak."""
    m._vibe_install(tmp_path, project=True)
    before = (tmp_path / ".vibe" / "hooks.toml").read_bytes()
    m._vibe_install(tmp_path, project=True)
    after = (tmp_path / ".vibe" / "hooks.toml").read_bytes()
    assert before == after, "hooks.toml must be byte-identical after re-install"
    backups = list((tmp_path / ".vibe").glob("*.graphify-bak"))
    assert backups == [], f"idempotent re-install must not create backups: {backups}"


def test_strict_flip_creates_backup_and_updates_command(tmp_path, home):
    """When the effective hook command changes, backup the old file (matches gemini/claude)."""
    m._vibe_install(tmp_path, project=True, strict=False)
    m._vibe_install(tmp_path, project=True, strict=True)
    backup = tmp_path / ".vibe" / "hooks.toml.graphify-bak"
    assert backup.exists(), "flipping strict must preserve the previous hooks.toml"
    body = (tmp_path / ".vibe" / "hooks.toml").read_text(encoding="utf-8")
    assert "hook-guard read --strict" in body


def test_install_preserves_user_authored_hooks_and_comments(tmp_path, home):
    """This is why we picked tomlkit over stdlib TOML writers."""
    (tmp_path / ".vibe").mkdir()
    existing = (
        '# my custom hooks - keep these\n'
        '[[hooks]]\n'
        'name = "my-guard"\n'
        'type = "pre_tool"\n'
        'match = "bash"\n'
        'command = "my-guard.sh"\n'
        'timeout = 10.0\n'
        'strict = true\n'
        'description = "user hook"\n'
    )
    (tmp_path / ".vibe" / "hooks.toml").write_text(existing, encoding="utf-8")

    m._vibe_install(tmp_path, project=True)

    body = (tmp_path / ".vibe" / "hooks.toml").read_text(encoding="utf-8")
    assert "# my custom hooks - keep these" in body, "user comment must survive"
    assert 'name = "my-guard"' in body, "user hook must survive"
    assert "hook-guard search" in body, "graphify hooks must be added"
    assert "hook-guard read" in body


def test_uninstall_strips_only_graphify_entries(tmp_path, home):
    """User's own [[hooks]] entries must remain after `vibe uninstall --project`."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text(
        '[[hooks]]\n'
        'name = "my-guard"\n'
        'type = "pre_tool"\n'
        'match = "bash"\n'
        'command = "my-guard.sh"\n'
        'timeout = 10.0\n'
        'strict = true\n'
        'description = "user hook"\n',
        encoding="utf-8",
    )
    m._vibe_install(tmp_path, project=True)
    m._vibe_uninstall(tmp_path, project=True)

    hooks_toml = tmp_path / ".vibe" / "hooks.toml"
    assert hooks_toml.exists(), "must leave user-authored hooks.toml behind"
    body = hooks_toml.read_text(encoding="utf-8")
    assert 'name = "my-guard"' in body, "user hook must survive uninstall"
    assert "graphify" not in body, "no graphify entries may remain"


def test_uninstall_removes_empty_hooks_toml(tmp_path, home):
    """If graphify was the only source of [[hooks]], uninstall must clean the empty file."""
    m._vibe_install(tmp_path, project=True)
    m._vibe_uninstall(tmp_path, project=True)
    assert not (tmp_path / ".vibe" / "hooks.toml").exists()
    assert not (tmp_path / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_agents_md_section_uses_shared_marker(tmp_path, home):
    """The AGENTS.md section must use the same `## graphify` marker as codex/opencode/aider
    so the shared uninstall path (`_remove_marker_section`) matches and cleans it."""
    m._vibe_install(tmp_path, project=True)
    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert body.startswith("## graphify"), "must open with the shared marker heading"
    assert "graphify query" in body, "must nudge toward the query-first path"


def test_agents_md_section_replaced_in_place_not_duplicated(tmp_path, home):
    """Re-install must not double-append the graphify section (regression #580 / #1688)."""
    (tmp_path / "AGENTS.md").write_text(
        "# project prelude\n\nsome existing content.\n\n"
        "## graphify\n\nstale graphify block from an older version.\n",
        encoding="utf-8",
    )
    m._vibe_install(tmp_path, project=True)
    body = (tmp_path / "AGENTS.md").read_text(encoding="utf-8")
    assert body.count("## graphify") == 1, "must replace, not duplicate"
    assert "stale graphify block from an older version" not in body, "old block must be replaced"
    assert "# project prelude" in body, "user's prelude must survive"


def test_global_install_targets_home_dot_vibe(tmp_path, home):
    """Bare `graphify vibe install` (no --project) must land under ~/.vibe."""
    m._vibe_install(project=False)
    assert (home / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert (home / ".vibe" / "hooks.toml").exists()
    assert (home / ".vibe" / "AGENTS.md").exists()


def test_platform_config_registers_vibe():
    """Vibe must be discoverable through the shared platform-config surface.

    Behavior-based: don't lock the internal `skill_refs` value (reusing the
    agents bundle is an implementation choice that could change). Just verify
    the platform is registered and that after install the expected reference
    files land beside SKILL.md.
    """
    from graphify.install import _PLATFORM_CONFIG, _CLI_INSTALL_COMMANDS
    assert "vibe" in _PLATFORM_CONFIG
    assert "vibe" in _CLI_INSTALL_COMMANDS


def test_install_lands_references_sidecar_alongside_skill(tmp_path, home):
    """The references/ progressive-disclosure sidecar must ship with SKILL.md.

    Bundle-source coupling (which references bundle) is an internal choice; the
    user-visible contract is that references exist and SKILL.md can point at
    them. Regressions where the sidecar goes missing (packaging bug, wrong
    skill_refs key) break the skill body's `references/hooks.md`-style links.
    """
    m._vibe_install(tmp_path, project=True)
    refs = tmp_path / ".vibe" / "skills" / "graphify" / "references"
    assert refs.is_dir(), "references/ sidecar must land next to SKILL.md"
    assert any(refs.glob("*.md")), "references/ must contain at least one .md"


def test_dispatch_cli_recognizes_vibe_subcommand(tmp_path, home, monkeypatch):
    """`graphify vibe install --project` must reach `_vibe_install`."""
    import sys
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "vibe", "install", "--project"])
    handled = m.dispatch_install_cli("vibe")
    assert handled is True, "vibe dispatch must claim the command"
    assert (tmp_path / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert (tmp_path / ".vibe" / "hooks.toml").exists()


def test_dispatch_bare_vibe_uninstall_removes_global_install(tmp_path, home, monkeypatch):
    """Regression: `graphify vibe uninstall` (no --project) must clean ~/.vibe.

    The dispatch branch previously passed an explicit `project_dir` even for
    bare uninstall, which forced `explicit_dir=True` in `_vibe_uninstall` and
    resolved `remove_user_skill=False` -> project-only cleanup, leaving the
    entire global install intact. This test locks the fix.
    """
    import sys
    monkeypatch.chdir(tmp_path)

    monkeypatch.setattr(sys, "argv", ["graphify", "vibe", "install"])
    m.dispatch_install_cli("vibe")
    assert (home / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert (home / ".vibe" / "hooks.toml").exists()
    assert (home / ".vibe" / "AGENTS.md").exists()

    monkeypatch.setattr(sys, "argv", ["graphify", "vibe", "uninstall"])
    m.dispatch_install_cli("vibe")
    assert not (home / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (home / ".vibe" / "hooks.toml").exists()
    assert not (home / ".vibe" / "AGENTS.md").exists()


def test_dispatch_platform_vibe_alias_goes_through_full_install(tmp_path, home, monkeypatch):
    """`graphify install --platform vibe` must invoke the full-parity installer.

    The bare `install()` function had a skill-only default path; vibe needs the
    three-artifact orchestrator (skill + AGENTS.md + hooks.toml). Regressions
    here would ship a skill without hooks or AGENTS.md when users pick the
    `--platform vibe` invocation form.
    """
    monkeypatch.chdir(tmp_path)
    m.install(platform="vibe", project=True, project_dir=tmp_path)
    assert (tmp_path / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert (tmp_path / ".vibe" / "hooks.toml").exists()
    assert (tmp_path / "AGENTS.md").exists()


def test_install_platform_vibe_propagates_strict_flag(tmp_path, home, monkeypatch):
    """`graphify install --platform vibe --strict` (bare global) must propagate --strict.

    Regression: the top-level `install()` used to drop the strict kwarg for the
    vibe branch, so bare-global install silently produced a non-strict read hook
    while --project --strict worked. Unlike Claude Code (where --strict requires
    a project hook), vibe's global hooks.toml at ~/.vibe/hooks.toml legitimately
    accepts --strict, so the flag must flow through.
    """
    import sys
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", "install", "--platform", "vibe", "--strict"])
    m.dispatch_install_cli("install")

    hooks_toml = home / ".vibe" / "hooks.toml"
    assert hooks_toml.exists(), "bare global install must create hooks.toml"
    body = hooks_toml.read_text(encoding="utf-8")
    assert "hook-guard read --strict" in body, "read hook must carry --strict"
    assert "hook-guard search --strict" not in body, "search hook must stay a nudge"


def test_uninstall_all_sweeps_vibe_global(tmp_path, home, monkeypatch):
    """`graphify uninstall` (uninstall_all) must clean the global vibe install.

    Otherwise vibe hooks keep firing after the user removes graphify from all
    other platforms. Regression lock: private helpers looked healthy but
    `uninstall_all` was missing the vibe cleanup call.
    """
    monkeypatch.chdir(tmp_path)
    m._vibe_install(project=False)
    assert (home / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert (home / ".vibe" / "hooks.toml").exists()
    assert (home / ".vibe" / "AGENTS.md").exists()

    m.uninstall_all(project_dir=tmp_path, purge=False)

    assert not (home / ".vibe" / "skills" / "graphify" / "SKILL.md").exists()
    assert not (home / ".vibe" / "hooks.toml").exists()
    assert not (home / ".vibe" / "AGENTS.md").exists()


def test_vibe_home_env_var_redirects_global_install(tmp_path, monkeypatch):
    """Global install must honor VIBE_HOME so users on non-default vibe setups don't get orphaned installs.

    Vibe's own harness_files/_harness_manager.py reads VIBE_HOME/skills,
    VIBE_HOME/hooks.toml, and VIBE_HOME/AGENTS.md. Hardcoding ~/.vibe silently
    breaks users who set VIBE_HOME=/opt/vibe-shared.
    """
    custom_vibe_home = tmp_path / "custom-vibe-root"
    real_home = tmp_path / "home"
    real_home.mkdir()

    monkeypatch.setattr("pathlib.Path.home", lambda: real_home)
    monkeypatch.setenv("HOME", str(real_home))
    monkeypatch.setenv("VIBE_HOME", str(custom_vibe_home))

    m._vibe_install(project=False)

    assert (custom_vibe_home / "skills" / "graphify" / "SKILL.md").exists()
    assert (custom_vibe_home / "hooks.toml").exists()
    assert (custom_vibe_home / "AGENTS.md").exists()
    assert not (real_home / ".vibe").exists()


def test_vibe_home_env_var_symmetric_uninstall(tmp_path, monkeypatch):
    """Uninstall must honor VIBE_HOME too, or install/uninstall drift and hooks stay behind."""
    custom_vibe_home = tmp_path / "custom-vibe-root"
    real_home = tmp_path / "home"
    real_home.mkdir()
    monkeypatch.setattr("pathlib.Path.home", lambda: real_home)
    monkeypatch.setenv("HOME", str(real_home))
    monkeypatch.setenv("VIBE_HOME", str(custom_vibe_home))

    m._vibe_install(project=False)
    m._vibe_uninstall()

    assert not (custom_vibe_home / "skills" / "graphify" / "SKILL.md").exists()
    assert not (custom_vibe_home / "hooks.toml").exists()
    assert not (custom_vibe_home / "AGENTS.md").exists()


def test_install_preserves_user_hook_whose_command_mentions_graphify(tmp_path, home):
    """A user hook that calls graphify for their own reason must survive install.

    Regression: the old filter was `"graphify" not in str(h.get("command"))`,
    which deleted ANY hook whose command contained 'graphify' - including the
    user's own tooling. The fix filters by hook `name` in a fixed set.
    """
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text(
        '[[hooks]]\n'
        'name = "my-graphify-metrics"\n'
        'type = "post_tool"\n'
        'match = "*"\n'
        'command = "graphify metrics --log"\n'
        'timeout = 5.0\n'
        'strict = false\n'
        'description = "my own thing that happens to call graphify"\n',
        encoding="utf-8",
    )
    m._vibe_install(tmp_path, project=True)
    body = (tmp_path / ".vibe" / "hooks.toml").read_text(encoding="utf-8")
    assert 'name = "my-graphify-metrics"' in body, (
        "user hook whose command mentions 'graphify' must NOT be deleted"
    )
    assert "hook-guard search" in body, "graphify hooks must still be added"


def test_uninstall_preserves_user_hook_whose_command_mentions_graphify(tmp_path, home):
    """Same regression on the uninstall side: only remove graphify-owned entries by name."""
    m._vibe_install(tmp_path, project=True)
    import tomlkit
    from tomlkit.items import AoT
    hooks_path = tmp_path / ".vibe" / "hooks.toml"
    doc = tomlkit.parse(hooks_path.read_text(encoding="utf-8"))
    user_hook = tomlkit.table()
    user_hook["name"] = "my-graphify-log"
    user_hook["type"] = "post_tool"
    user_hook["match"] = "*"
    user_hook["command"] = "graphify metrics --log"
    user_hook["timeout"] = 5.0
    user_hook["strict"] = False
    user_hook["description"] = "user thing"
    assert isinstance(doc["hooks"], AoT)
    doc["hooks"].append(user_hook)
    hooks_path.write_text(tomlkit.dumps(doc), encoding="utf-8")

    m._vibe_uninstall(tmp_path, project=True)

    remaining = hooks_path.read_text(encoding="utf-8")
    assert 'name = "my-graphify-log"' in remaining, "user hook must survive uninstall"
    assert "hook-guard search" not in remaining, "graphify hooks must be removed"


def test_hook_command_shell_quotes_paths_with_metacharacters(monkeypatch):
    """Hook commands must survive shell-metachar paths (macOS home with `(`, `$`, `;`).

    Vibe runs hooks via asyncio.create_subprocess_shell, so metachars in the
    graphify exe path parse as shell operators. The previous "quote only if
    the path has a space" heuristic left injection open for paths like
    `/tmp/g;touch /tmp/pwned/graphify` or `~/Library/Application Support/...`.
    shlex.join produces a shell-safe single-token quoting on POSIX.
    """
    hostile_paths = [
        "/tmp/g;touch /tmp/pwned/graphify",
        "/tmp/g$(whoami)/graphify",
        "/tmp/g`whoami`/graphify",
        "/Users/me/App (2)/bin/graphify",
        "/tmp/with spaces/graphify",
        "/tmp/g&background/graphify",
        "/tmp/g|pipe/graphify",
        '/tmp/g"quote/graphify',
        "/tmp/g'squote/graphify",
    ]
    import shlex
    import graphify.install as install_mod
    for path in hostile_paths:
        monkeypatch.setattr(install_mod, "_resolve_graphify_exe", lambda p=path: p)
        entries = install_mod._vibe_hook_entries()
        for e in entries:
            tokens = shlex.split(e["command"])
            assert tokens[0] == path, (
                f"path {path!r} was not shell-quoted correctly; "
                f"got tokens {tokens!r} from command {e['command']!r}"
            )
            assert tokens[1] == "hook-guard"
            assert tokens[2] in ("search", "read")


def test_install_refuses_when_hooks_is_plain_array_not_aot(tmp_path, home):
    """`hooks = []` (plain Array) must be refused, not corrupted with appended tables.

    Regression: the old `isinstance(existing, list)` check accepted tomlkit's
    Array (which passes the list-like check). Appending tables into a plain
    array produced unparsable TOML that broke vibe on next load.
    """
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text('hooks = []\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        m._vibe_install(tmp_path, project=True)


def test_install_refuses_when_hooks_is_inline_table(tmp_path, home):
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text(
        'hooks = { name = "bad", type = "pre_tool", command = "x" }\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        m._vibe_install(tmp_path, project=True)


def test_install_refuses_when_hooks_is_scalar(tmp_path, home):
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text('hooks = "bad"\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        m._vibe_install(tmp_path, project=True)


def test_install_refuses_when_hooks_element_is_not_table(tmp_path, home):
    """`hooks = ["bad"]` must refuse rather than AttributeError on `.get()`.

    A `hooks = ["bad"]` file parses as an AoT-ish container to some tomlkit
    versions but each element is a scalar. The pre-fix code called `.get()`
    unconditionally on every element, which would AttributeError mid-write.
    Now: element shape is checked and _refuse_to_modify is called on the first
    non-mapping element.
    """
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text('hooks = ["bad"]\n', encoding="utf-8")
    with pytest.raises(SystemExit):
        m._vibe_install(tmp_path, project=True)


def test_install_refuses_when_toml_is_malformed(tmp_path, home):
    """Malformed TOML must _refuse_to_modify, not silently reset the file."""
    (tmp_path / ".vibe").mkdir()
    (tmp_path / ".vibe" / "hooks.toml").write_text(
        '[[hooks\nunterminated table header\n',
        encoding="utf-8",
    )
    with pytest.raises(SystemExit):
        m._vibe_install(tmp_path, project=True)
