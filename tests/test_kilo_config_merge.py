"""The Kilo installer must merge into an existing .kilo config, never clobber it.

Same invariant as #2167 for the Claude/CodeBuddy/Gemini/Codex hook installers:
an existing config file that cannot be parsed as a JSON object aborts the
install and is left byte-identical on disk. Before this fix the Kilo path read
the config through ``_load_json_like``, which returns ``{}`` on any parse error,
so a single trailing comma in ``.kilo/kilo.json`` made the installer rewrite the
file as ``{"plugin": [...]}`` and drop every other key the user had.
"""

from __future__ import annotations

import json

import pytest

from graphify.install import _install_kilo_plugin, _uninstall_kilo_plugin

_USER_CONFIG = (
    b'{\n  "model": "anthropic/claude-haiku",\n'
    b'  "permission": {"edit": "ask"},\n}\n'  # trailing comma: not valid JSON
)


def _plugin_uri(project_dir):
    return (project_dir / ".kilo" / "plugins" / "graphify.js").resolve().as_uri()


def _seed(project_dir, name, content: bytes):
    path = project_dir / ".kilo" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return path


def test_unparseable_kilo_json_aborts_without_clobbering(tmp_path, capsys):
    config = _seed(tmp_path, "kilo.json", _USER_CONFIG)

    with pytest.raises(SystemExit) as excinfo:
        _install_kilo_plugin(tmp_path)

    assert excinfo.value.code == 1
    assert str(config) in capsys.readouterr().err
    assert config.read_bytes() == _USER_CONFIG
    # Nothing half-installed: the plugin is not written when registration is refused.
    assert not (tmp_path / ".kilo" / "plugins" / "graphify.js").exists()


def test_non_object_kilo_json_aborts_without_clobbering(tmp_path, capsys):
    original = b'["not", "an", "object"]'
    config = _seed(tmp_path, "kilo.json", original)

    with pytest.raises(SystemExit) as excinfo:
        _install_kilo_plugin(tmp_path)

    assert excinfo.value.code == 1
    assert config.read_bytes() == original


def test_unparseable_kilo_jsonc_does_not_spawn_a_partial_kilo_json(tmp_path):
    """A broken kilo.jsonc must not be shadowed by a fresh plugin-only kilo.json."""
    original = b'// comment\n{\n  "model": "x"\n  "plugin": []\n}\n'  # missing comma
    jsonc = _seed(tmp_path, "kilo.jsonc", original)

    with pytest.raises(SystemExit):
        _install_kilo_plugin(tmp_path)

    assert jsonc.read_bytes() == original
    assert not (tmp_path / ".kilo" / "kilo.json").exists()


def test_bom_prefixed_kilo_json_is_merged_not_clobbered(tmp_path):
    """A UTF-8 BOM is tolerated (utf-8-sig), as in #2167, and user keys survive."""
    config = _seed(
        tmp_path,
        "kilo.json",
        b"\xef\xbb\xbf" + json.dumps({"model": "anthropic/claude-haiku"}).encode(),
    )

    _install_kilo_plugin(tmp_path)

    merged = json.loads(config.read_text(encoding="utf-8"))
    assert merged["model"] == "anthropic/claude-haiku"
    assert _plugin_uri(tmp_path) in merged["plugin"]


def test_valid_kilo_json_still_merges(tmp_path):
    config = _seed(
        tmp_path,
        "kilo.json",
        json.dumps({"model": "anthropic/claude-haiku", "plugin": ["other.js"]}).encode(),
    )

    _install_kilo_plugin(tmp_path)

    merged = json.loads(config.read_text(encoding="utf-8"))
    assert merged["model"] == "anthropic/claude-haiku"
    assert merged["plugin"] == ["other.js", _plugin_uri(tmp_path)]


def test_uninstall_leaves_unparseable_kilo_json_untouched(tmp_path):
    """Uninstall keeps its existing lenient read: nothing to deregister, no write, no exit."""
    config = _seed(tmp_path, "kilo.json", _USER_CONFIG)

    _uninstall_kilo_plugin(tmp_path)

    assert config.read_bytes() == _USER_CONFIG
