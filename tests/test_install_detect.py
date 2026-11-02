"""Tests for `graphify install --detect` interactive multi-platform install."""
import io
import sys
from pathlib import Path

import pytest

import graphify.install as install_mod
from graphify.__main__ import main


class _TTYBuf(io.StringIO):
    def isatty(self):
        return True


class _PipeBuf(io.StringIO):
    def isatty(self):
        return False


def _input_forbidden(prompt=""):
    raise AssertionError("input() should not be called during this test")


def _run_detect(monkeypatch, tmp_path, argv, *, responses=None, tty=True):
    out = _TTYBuf() if tty else _PipeBuf()
    inp = _TTYBuf() if tty else _PipeBuf()
    monkeypatch.setattr(sys, "stdout", out)
    monkeypatch.setattr(sys, "stdin", inp)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", ["graphify", *argv])
    if responses is not None:
        monkeypatch.setattr("builtins.input", lambda prompt="": responses.pop(0))
    else:
        monkeypatch.setattr("builtins.input", _input_forbidden)
    main()
    return out.getvalue()


def test_bare_install_unchanged(monkeypatch, tmp_path):
    home = Path.home()
    out = _run_detect(monkeypatch, tmp_path, ["install"], tty=False)
    assert (home / ".claude" / "skills" / "graphify" / "SKILL.md").exists()
    assert "--detect" not in out
    assert "summary" not in out


def test_detect_installs_mocked_platforms(monkeypatch, tmp_path):
    home = Path.home()
    for name in ("codex", "aider"):
        install_mod._platform_marker_dir(name).mkdir(parents=True, exist_ok=True)
    out = _run_detect(monkeypatch, tmp_path, ["install", "--detect"], responses=["", ""], tty=True)
    assert install_mod._platform_skill_destination("codex").exists()
    assert install_mod._platform_skill_destination("aider").exists()
    assert "installed: codex" in out
    assert "installed: aider" in out


def test_detect_accept_and_reject(monkeypatch, tmp_path):
    for name in ("codex", "aider"):
        install_mod._platform_marker_dir(name).mkdir(parents=True, exist_ok=True)
    out = _run_detect(monkeypatch, tmp_path, ["install", "--detect"], responses=["", "n"], tty=True)
    assert install_mod._platform_skill_destination("codex").exists()
    assert not install_mod._platform_skill_destination("aider").exists()
    assert "installed: codex" in out
    assert "skipped:   aider" in out


def test_detect_no_platforms_detected(monkeypatch, tmp_path):
    home = Path.home()
    out = _run_detect(monkeypatch, tmp_path, ["install", "--detect"], tty=True)
    assert "Nothing to install" in out
    assert not (home / ".claude" / "skills").exists()


def test_detect_non_tty_does_not_hang_or_install(monkeypatch, tmp_path):
    install_mod._platform_marker_dir("codex").mkdir(parents=True, exist_ok=True)
    out = _run_detect(monkeypatch, tmp_path, ["install", "--detect"], tty=False)
    assert "- codex" in out
    assert "No installs performed" in out
    assert not install_mod._platform_skill_destination("codex").exists()
    assert not (tmp_path / "AGENTS.md").exists()


def test_detect_project_scope(monkeypatch, tmp_path):
    home = Path.home()
    project = tmp_path
    (project / ".codex").mkdir()
    (project / ".cursor").mkdir()
    out = _run_detect(
        monkeypatch, project, ["install", "--detect", "--project"], responses=["", ""], tty=True
    )
    assert (project / ".codex" / "skills" / "graphify" / "SKILL.md").exists()
    assert (project / "AGENTS.md").exists()
    assert (project / ".codex" / "hooks.json").exists()
    assert (project / ".cursor" / "rules" / "graphify.mdc").exists()
    assert not (home / ".codex" / "skills").exists()


def test_detect_respects_claude_config_dir(monkeypatch, tmp_path):
    home = Path.home()
    cfg = tmp_path / "cfg"
    cfg.mkdir()
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(cfg))
    out = _run_detect(monkeypatch, tmp_path, ["install", "--detect"], responses=[""], tty=True)
    assert (cfg / "skills" / "graphify" / "SKILL.md").exists()
    assert (cfg / "CLAUDE.md").exists()
    assert not (home / ".claude" / "skills").exists()


def test_detect_installs_gemini(monkeypatch, tmp_path):
    install_mod._platform_marker_dir("gemini").mkdir(parents=True, exist_ok=True)
    out = _run_detect(monkeypatch, tmp_path, ["install", "--detect"], responses=[""], tty=True)
    assert install_mod._platform_skill_destination("gemini").exists()
    assert (tmp_path / "GEMINI.md").exists()
    assert "installed: gemini" in out


def test_detect_usage_mentions_flag(capsys):
    install_mod._print_install_usage()
    assert "--detect" in capsys.readouterr().out


def test_platform_marker_dir_rules(tmp_path):
    home = Path.home()
    proj = tmp_path / "proj"
    assert install_mod._platform_marker_dir("opencode") == home / ".config" / "opencode"
    assert install_mod._platform_marker_dir("kilo") == home / ".config" / "kilo"
    assert install_mod._platform_marker_dir("devin") == home / ".config" / "devin"
    assert install_mod._platform_marker_dir("amp") == home / ".config" / "agents"
    assert install_mod._platform_marker_dir("claude") == home / ".claude"
    assert install_mod._platform_marker_dir("aider") == home / ".aider"
    assert install_mod._platform_marker_dir("cursor") == home / ".cursor"
    assert install_mod._platform_marker_dir("gemini") == home / ".gemini"
    assert install_mod._platform_marker_dir("antigravity") == home / ".gemini" / "antigravity"
    assert install_mod._platform_marker_dir("opencode", project=True, project_dir=proj) == proj / ".opencode"
