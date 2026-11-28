"""Hook install/uninstall must remove only graphify's own hook entries (#4359).

Install and uninstall used to identify graphify's hooks with
``"graphify" in str(group)`` over the whole group dict. That removed:

- a user's own command sharing graphify's ``hooks`` array, along with the group;
- an unrelated group whose command path merely contained the word ``graphify``
  (e.g. a script under a folder named ``graphify-notes``);
- and, on uninstall, wrote the settings file back with no backup while
  ``_strip_graphify_hook`` raised ``AttributeError`` on a non-dict entry.

These tests pin the entry-scoped contract: only entries graphify installed go,
a group is dropped only when nothing is left in it, other tools' commands
survive, and uninstall keeps a rolling backup.
"""
from __future__ import annotations

import json

import pytest

from graphify import install as install_mod

# id -> (install, uninstall, settings file relative to project, section key)
_INSTALLERS = {
    "claude": (
        lambda project: install_mod._install_claude_hook(project),
        lambda project: install_mod._uninstall_claude_hook(project),
        ".claude/settings.json",
        "PreToolUse",
    ),
    "codebuddy": (
        lambda project: install_mod._install_codebuddy_hook(project),
        lambda project: install_mod._uninstall_codebuddy_hook(project),
        ".codebuddy/settings.json",
        "PreToolUse",
    ),
    "codex": (
        lambda project: install_mod._install_codex_hook(project),
        lambda project: install_mod._uninstall_codex_hook(project),
        ".codex/hooks.json",
        "PreToolUse",
    ),
    "gemini": (
        lambda project: install_mod._install_gemini_hook(project),
        lambda project: install_mod._uninstall_gemini_hook(project),
        ".gemini/settings.json",
        "BeforeTool",
    ),
}


def _groups(settings: dict, section: str) -> list:
    return settings["hooks"][section]


def _has_graphify(entry: object) -> bool:
    return install_mod._is_graphify_hook_entry(entry)


@pytest.mark.parametrize("name", sorted(_INSTALLERS))
def test_uninstall_keeps_user_commands_and_unrelated_groups(tmp_path, name):
    install, uninstall, rel, section = _INSTALLERS[name]
    project = tmp_path / "proj"
    project.mkdir()

    install(project)
    settings_path = project / rel
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    groups = _groups(settings, section)
    assert any(
        _has_graphify(e) for g in groups if isinstance(g, dict) for e in g.get("hooks", [])
    ), f"{name} install registered no graphify hook"

    # 1) the user adds their own command to graphify's own group;
    # 2) an unrelated guard group whose command path contains "graphify".
    for group in groups:
        if isinstance(group, dict) and any(_has_graphify(e) for e in group.get("hooks", [])):
            group["hooks"].append({"type": "command", "command": "python /tools/my-linter.py"})
            break
    groups.append(
        {
            "matcher": "Bash",
            "hooks": [{"type": "command", "command": "python /tools/graphify-notes/check.py"}],
        }
    )
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    uninstall(project)

    after = settings_path.read_text(encoding="utf-8")
    assert "my-linter" in after, f"{name}: the user's command in graphify's group was removed"
    assert "graphify-notes" in after, f"{name}: the unrelated group was removed"
    assert "hook-guard" not in after and "hook-check" not in after, (
        f"{name}: graphify's own hook commands were not removed"
    )
    backup = settings_path.with_name(settings_path.name + ".graphify-bak")
    assert backup.exists(), f"{name}: uninstall wrote no backup"


@pytest.mark.parametrize("name", sorted(_INSTALLERS))
def test_uninstall_survives_a_non_dict_entry(tmp_path, name):
    """#4359: a plain string in the hook array must not crash uninstall, and must
    be preserved (it is not graphify's)."""
    install, uninstall, rel, section = _INSTALLERS[name]
    project = tmp_path / "proj"
    project.mkdir()

    install(project)
    settings_path = project / rel
    settings = json.loads(settings_path.read_text(encoding="utf-8"))
    _groups(settings, section).append("a-legacy-string-entry")
    settings_path.write_text(json.dumps(settings, indent=2), encoding="utf-8")

    uninstall(project)  # must not raise

    after = json.loads(settings_path.read_text(encoding="utf-8"))
    assert "a-legacy-string-entry" in _groups(after, section)


def test_install_removes_legacy_bash_hook_and_stays_idempotent(tmp_path):
    """The pre-#522 inline bash guard is still replaced, without duplicating
    graphify's groups on a re-run."""
    project = tmp_path / "proj"
    settings_path = project / ".claude" / "settings.json"
    settings_path.parent.mkdir(parents=True)
    settings_path.write_text(
        json.dumps(
            {
                "hooks": {
                    "PreToolUse": [
                        {
                            "matcher": "Bash",
                            "hooks": [
                                {
                                    "type": "command",
                                    "command": "[ -f graphify-out/graph.json ] && echo x || true",
                                }
                            ],
                        }
                    ]
                }
            }
        ),
        encoding="utf-8",
    )

    install_mod._install_claude_hook(project)
    install_mod._install_claude_hook(project)

    groups = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "graphify-out/graph.json" not in json.dumps(groups), "legacy bash guard survived"
    assert len([g for g in groups if "graphify" in json.dumps(g)]) == 2, "not idempotent"


@pytest.mark.parametrize(
    "command",
    [
        "graphify hook-guard search",
        '"C:/tools/graphify.EXE" hook-guard read --strict',
        "graphify hook-guard gemini",
        "graphify hook-check",
        "[ -f graphify-out/graph.json ] && echo x || true",
    ],
)
def test_graphify_commands_are_recognised(command):
    assert install_mod._is_graphify_hook_command(command)


@pytest.mark.parametrize(
    "command",
    [
        "python /tools/graphify-notes/check.py",
        "python /tools/check.py",
        "eslint .",
        "",
    ],
)
def test_other_commands_are_not_recognised(command):
    assert not install_mod._is_graphify_hook_command(command)


def test_strip_drops_only_emptied_groups_and_passes_malformed_through():
    groups = [
        {
            "matcher": "Bash|Grep",
            "hooks": [
                {"type": "command", "command": "graphify hook-guard search"},
                {"type": "command", "command": "my-own-command"},
            ],
        },
        {"matcher": "Read|Glob", "hooks": [{"type": "command", "command": "graphify hook-guard read"}]},
        "not-a-dict",
        {"matcher": "Bash", "hooks": "not-a-list"},
    ]

    out = install_mod._strip_graphify_hooks(groups)

    assert out == [
        {"matcher": "Bash|Grep", "hooks": [{"type": "command", "command": "my-own-command"}]},
        "not-a-dict",
        {"matcher": "Bash", "hooks": "not-a-list"},
    ]
