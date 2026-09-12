import json
from pathlib import Path
from unittest.mock import patch

from graphify.install import _install_opencode_plugin, _uninstall_opencode_plugin


def test_global_install_targets_xdg_config(tmp_path):
    """Global install must write to ~/.config/opencode/, not CWD/.opencode/ (#3398)."""
    with patch.object(Path, "home", return_value=tmp_path):
        _install_opencode_plugin(project=False)

    config_dir = tmp_path / ".config" / "opencode"
    assert (config_dir / "plugins" / "graphify.js").exists()
    config = json.loads((config_dir / "opencode.json").read_text())
    assert "plugins/graphify.js" in config["plugin"]
    # The extra .opencode/ segment must NOT appear for global installs
    assert not (tmp_path / ".opencode").exists()


def test_project_install_targets_project_dir(tmp_path):
    """Project install must write to <project_dir>/.opencode/ as before."""
    _install_opencode_plugin(project=True, project_dir=tmp_path)

    config_dir = tmp_path / ".opencode"
    assert (config_dir / "plugins" / "graphify.js").exists()
    config = json.loads((config_dir / "opencode.json").read_text())
    assert ".opencode/plugins/graphify.js" in config["plugin"]


def test_global_uninstall_targets_xdg_config(tmp_path):
    """Global uninstall must clean up ~/.config/opencode/, not CWD/.opencode/ (#3398)."""
    with patch.object(Path, "home", return_value=tmp_path):
        _install_opencode_plugin(project=False)
        _uninstall_opencode_plugin(project=False)

    plugin = tmp_path / ".config" / "opencode" / "plugins" / "graphify.js"
    assert not plugin.exists()
