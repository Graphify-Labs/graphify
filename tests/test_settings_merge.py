"""Regression tests for issue #2167: hook installers must merge into existing
settings/hooks JSON files, never clobber them.

The old behavior fell back to ``settings = {}`` on any parse error (a UTF-8 BOM
was enough, same class as #2163) and then rewrote the whole file, destroying the
user's mcpServers/enabledPlugins/theme/hooks. The fix:

- read with utf-8-sig (BOM-tolerant),
- refuse to touch an existing file that is not a JSON object (stderr + exit 1),
- back up to <name>.graphify-bak before any modifying write,
- skip the write entirely when nothing changed (idempotent re-install),
- never crash on (and always preserve) non-dict hook entries.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.install import (
    _install_claude_hook,
    _install_codebuddy_hook,
    _install_codex_hook,
    _install_gemini_hook,
)

# installer key -> (function, settings file relative to project dir, hooks section)
_INSTALLERS = {
    "claude": (_install_claude_hook, Path(".claude") / "settings.json", "PreToolUse"),
    "codebuddy": (_install_codebuddy_hook, Path(".codebuddy") / "settings.json", "PreToolUse"),
    "codex": (_install_codex_hook, Path(".codex") / "hooks.json", "PreToolUse"),
    "gemini": (_install_gemini_hook, Path(".gemini") / "settings.json", "BeforeTool"),
}

ALL_INSTALLERS = pytest.mark.parametrize("installer", sorted(_INSTALLERS), ids=sorted(_INSTALLERS))


def _seed(tmp_path: Path, installer: str, payload) -> Path:
    _, rel, _ = _INSTALLERS[installer]
    settings_path = tmp_path / rel
    settings_path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, bytes):
        settings_path.write_bytes(payload)
    else:
        settings_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return settings_path


def _run(tmp_path: Path, installer: str, **kwargs) -> Path:
    fn, rel, _ = _INSTALLERS[installer]
    fn(tmp_path, **kwargs)
    return tmp_path / rel


# ---------------------------------------------------------------- merge


def test_claude_install_preserves_existing_settings(tmp_path):
    """#2167 core case: every key graphify does not own must survive install."""
    seeded = {
        "mcpServers": {"context7": {"command": "npx", "args": ["context7"]}},
        "enabledPlugins": ["my-plugin@marketplace"],
        "theme": "dark",
        "hooks": {
            "PostToolUse": [
                {"matcher": "Bash", "hooks": [{"type": "command", "command": "my-formatter"}]}
            ],
            "PreToolUse": [
                {"matcher": "Write", "hooks": [{"type": "command", "command": "my-write-guard"}]}
            ],
        },
    }
    settings_path = _seed(tmp_path, "claude", seeded)

    _run(tmp_path, "claude", strict=True)

    result = json.loads(settings_path.read_text(encoding="utf-8"))
    # top-level keys graphify does not own are untouched
    assert result["mcpServers"] == seeded["mcpServers"]
    assert result["enabledPlugins"] == seeded["enabledPlugins"]
    assert result["theme"] == "dark"
    # hooks sections graphify does not manage are untouched
    assert result["hooks"]["PostToolUse"] == seeded["hooks"]["PostToolUse"]
    # the user's own PreToolUse entry survives alongside graphify's
    pre_tool = result["hooks"]["PreToolUse"]
    assert seeded["hooks"]["PreToolUse"][0] in pre_tool
    graphify_hooks = [h for h in pre_tool if "graphify" in str(h)]
    assert len(graphify_hooks) == 2
    # strict=True lands on the read guard
    assert any(h["hooks"][0]["command"].endswith("--strict") for h in graphify_hooks)


# ---------------------------------------------------------------- BOM


@ALL_INSTALLERS
def test_bom_settings_are_merged_not_clobbered(tmp_path, installer):
    """A UTF-8 BOM must not trigger the parse-error path that used to clobber."""
    seeded = {"mcpServers": {"keep": {"command": "keep-me"}}, "theme": "dark"}
    body = json.dumps(seeded, indent=2).encode("utf-8")
    settings_path = _seed(tmp_path, installer, b"\xef\xbb\xbf" + body)

    _run(tmp_path, installer)

    result = json.loads(settings_path.read_text(encoding="utf-8"))
    assert result["mcpServers"] == seeded["mcpServers"]
    assert result["theme"] == "dark"
    section = _INSTALLERS[installer][2]
    assert any("graphify" in str(h) for h in result["hooks"][section])


# ---------------------------------------------------------------- invalid JSON


@ALL_INSTALLERS
def test_invalid_json_aborts_without_clobbering(tmp_path, installer, capsys):
    """An unparseable existing file must abort the install, byte-identical on disk."""
    settings_path = _seed(tmp_path, installer, b"{ not json")
    original = settings_path.read_bytes()

    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path, installer)

    assert excinfo.value.code == 1
    assert str(settings_path) in capsys.readouterr().err
    assert settings_path.read_bytes() == original
    assert not settings_path.with_name(settings_path.name + ".graphify-bak").exists()


@ALL_INSTALLERS
def test_non_object_top_level_aborts_without_clobbering(tmp_path, installer, capsys):
    """Valid JSON that is not an object (e.g. a list) must also refuse, not crash."""
    settings_path = _seed(tmp_path, installer, b'["not", "an", "object"]')
    original = settings_path.read_bytes()

    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path, installer)

    assert excinfo.value.code == 1
    assert str(settings_path) in capsys.readouterr().err
    assert settings_path.read_bytes() == original


def test_non_dict_hooks_section_aborts(tmp_path, capsys):
    """A malformed hooks value (not a dict) refuses instead of raising/clobbering."""
    settings_path = _seed(tmp_path, "claude", {"hooks": "oops", "theme": "dark"})
    original = settings_path.read_bytes()

    with pytest.raises(SystemExit) as excinfo:
        _run(tmp_path, "claude")

    assert excinfo.value.code == 1
    assert str(settings_path) in capsys.readouterr().err
    assert settings_path.read_bytes() == original


# ---------------------------------------------------------------- backup


@ALL_INSTALLERS
def test_backup_written_before_modify_and_stable_on_reinstall(tmp_path, installer):
    seeded = {"theme": "dark", "mcpServers": {"keep": {}}}
    settings_path = _seed(tmp_path, installer, seeded)
    pre_write = settings_path.read_text(encoding="utf-8")
    backup = settings_path.with_name(settings_path.name + ".graphify-bak")

    _run(tmp_path, installer)

    assert backup.exists()
    assert backup.read_text(encoding="utf-8") == pre_write
    merged = settings_path.read_text(encoding="utf-8")
    assert merged != pre_write  # sanity: the run was a modifying one

    # Idempotent second run: output is unchanged, so neither the settings file
    # nor the backup may be rewritten (the backup keeps the pre-graphify content).
    _run(tmp_path, installer)
    assert settings_path.read_text(encoding="utf-8") == merged
    assert backup.read_text(encoding="utf-8") == pre_write


def test_no_backup_on_fresh_install(tmp_path):
    settings_path = _run(tmp_path, "claude")
    assert settings_path.exists()
    assert not settings_path.with_name(settings_path.name + ".graphify-bak").exists()


# ---------------------------------------------------------------- non-dict entries


@ALL_INSTALLERS
def test_non_dict_hook_entry_is_preserved_not_fatal(tmp_path, installer):
    """A legacy non-dict entry in the managed section must not crash the filter
    (the old claude/codebuddy filter called h.get() unconditionally) and must
    survive the merge."""
    section = _INSTALLERS[installer][2]
    settings_path = _seed(tmp_path, installer, {"hooks": {section: ["legacy-string"]}})

    _run(tmp_path, installer)

    entries = json.loads(settings_path.read_text(encoding="utf-8"))["hooks"][section]
    assert "legacy-string" in entries
    assert any("graphify" in str(h) for h in entries)
