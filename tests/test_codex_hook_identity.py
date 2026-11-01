"""REQ-CORE-001-AC05: entry-scoped cleanup recognizes only owned native hooks."""
from __future__ import annotations

import base64
import copy
import json

import pytest

import graphify.codex_hook_command as commandmod
import graphify.install as installmod


@pytest.fixture
def encoded_entry(monkeypatch):
    """Serialize the production transport without executing an OS shell."""
    monkeypatch.setattr(commandmod, "_windows_powershell_exe", lambda:
                        "C:/Windows/System32/WindowsPowerShell/v1.0/powershell.exe")
    return {"type": "command", "statusMessage": "graphify hook-check", "command":
            commandmod.codex_hook_command("C:/tools & literal ' %value%/graphify.exe", windows=True)}


@pytest.mark.parametrize("trailing", ["", " ", "\t", " \t "])
def test_req_core001_ac05_cleanup_recognizes_exact_encoded_transport(encoded_entry, trailing):
    """Owned native transport permits harmless trailing horizontal token whitespace."""
    encoded_entry["command"] += trailing
    assert installmod._is_graphify_hook_entry(encoded_entry)


@pytest.mark.parametrize("change", ["marker", "no-marker", "newline", "leading",
                                    "options", "base64", "unicode", "script", "type", "limit"])
def test_req_core001_ac05_cleanup_preserves_foreign_encoded_entries(encoded_entry, change):
    """An ownership label cannot authorize modified, malformed or foreign commands."""
    entry = copy.deepcopy(encoded_entry)
    if change == "marker":
        entry["statusMessage"] = "another tool"
    elif change == "no-marker":
        del entry["statusMessage"]
    elif change == "newline":
        entry["command"] += "\n"
    elif change == "leading":
        entry["command"] = " " + entry["command"]
    elif change == "options":
        entry["command"] = entry["command"].replace("-NoProfile", "-Profile")
    elif change == "type":
        entry["type"] = "prompt"
    elif change == "limit":
        entry["command"] += "A" * 8001
    else:
        head, _ = entry["command"].rsplit(" ", 1)
        payload = {"base64": "!bad!", "unicode": base64.b64encode(b"x").decode(),
                   "script": base64.b64encode("Write-Output 'graphify hook-check'".encode("utf-16-le")).decode()}[change]
        entry["command"] = head + " " + payload
    assert not installmod._is_graphify_hook_entry(entry)
    groups = [{"matcher": "Bash", "hooks": [entry]}]
    assert installmod._strip_graphify_hooks(groups) == groups


@pytest.mark.parametrize("foreign", ["script", "marker"])
def test_req_core001_ac05_encoded_ownership_cannot_borrow_outer_path_words(encoded_entry, foreign):
    """An OS directory spelling cannot bypass strict encoded-entry recognition."""
    entry = copy.deepcopy(encoded_entry)
    entry["command"] = entry["command"].replace("C:/Windows/", "C:/graphify-hook-check/")
    if foreign == "script":
        head, _ = entry["command"].rsplit(" ", 1)
        entry["command"] = head + " " + base64.b64encode("Write-Output 'foreign'".encode("utf-16-le")).decode()
    else:
        entry["statusMessage"] = "another tool"
    assert not installmod._is_graphify_hook_entry(entry)


def test_req_core001_ac05_encoded_reinstall_uninstall_keeps_neighbor_commands(tmp_path, monkeypatch, encoded_entry):
    """Actual persisted install/remove preserves sibling commands and rolling backups."""
    monkeypatch.setattr(installmod, "codex_hook_command", lambda *_args, **_kw: encoded_entry["command"])
    target = tmp_path / ".codex/hooks.json"
    sibling = {"type": "command", "command": "python /tools/graphify-notes/check.py"}
    groups = [{"matcher": "Bash", "hooks": [encoded_entry, sibling]}]
    target.parent.mkdir()
    original = json.dumps({"hooks": {"PreToolUse": groups}, "retained": True})
    target.write_text(original, encoding="utf-8")

    installmod._install_codex_hook(tmp_path)
    first = target.read_bytes()
    assert target.with_name("hooks.json.graphify-bak").read_text(encoding="utf-8") == original
    assert json.loads(first)["hooks"]["PreToolUse"] == [
        {"matcher": "Bash", "hooks": [sibling]},
        {"matcher": "Bash", "hooks": [encoded_entry]},
    ]
    installmod._install_codex_hook(tmp_path)
    assert target.read_bytes() == first
    installmod._uninstall_codex_hook(tmp_path)
    after = json.loads(target.read_bytes())
    assert after == {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [sibling]}]}, "retained": True}
