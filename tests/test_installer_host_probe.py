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