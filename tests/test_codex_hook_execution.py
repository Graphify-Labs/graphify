"""Execute serialized Codex hooks through the native host command shell.

REQ-CORE-001-AC01 protects the absolute user-scope launcher when its installation
directory has spaces and shell operators. POSIX additionally admits literal quote
and substitution characters; Windows filenames cannot contain a double quote.
The launcher forwards to the real CLI, so a parse-only assertion cannot mask a
shell dispatch failure.
"""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

import graphify.install as installmod


def test_req_core001_ac01_codex_hook_dispatches_spaced_native_launcher(tmp_path, monkeypatch):
    """Install a hook at a literal spaced path and run its persisted command."""
    # Exercise native cmd on Windows and /bin/sh on POSIX, with an operator that
    # would start another command if the installed executable were unquoted.
    directory = "installed tools & literal"
    if os.name != "nt":
        directory += " ' $(touch INJECTED)"
    tools = tmp_path / directory
    tools.mkdir()
    if os.name == "nt":
        launcher = tools / "graphify.exe"
        source = Path(sys.executable).parent / "graphify.exe"
        assert source.is_file(), "editable installation must include its CLI launcher"
        shutil.copyfile(source, launcher)
    else:
        launcher = tools / "graphify"
        launcher.write_text(
            f"#!/bin/sh\nexec {shlex.quote(sys.executable)} -m graphify \"$@\"\n",
            encoding="utf-8",
        )
        launcher.chmod(0o755)
    # A bare PATH lookup must fail observably, so the passing hook cannot be a
    # different globally installed graphify command that happens to be quiet.
    decoy_dir = tmp_path / "decoy-bin"
    decoy_dir.mkdir()
    decoy = decoy_dir / ("graphify.cmd" if os.name == "nt" else "graphify")
    decoy.write_text("@exit /b 79\n" if os.name == "nt" else "#!/bin/sh\nexit 79\n", encoding="utf-8")
    if os.name != "nt":
        decoy.chmod(0o755)
    environment = {
        **os.environ, "PATH": str(decoy_dir) + os.pathsep + os.environ.get("PATH", ""),
        "GRAPHIFY_NO_AUTO_REFRESH": "1", "GRAPHIFY_NO_TIPS": "1",
    }
    monkeypatch.setattr(installmod.shutil, "which", lambda _name: str(launcher))
    project = tmp_path / "project"
    project.mkdir()

    installmod._install_codex_hook(project)

    settings = json.loads((project / ".codex" / "hooks.json").read_text(encoding="utf-8"))
    command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    def dispatch(command_line):
        return subprocess.run(
            command_line, shell=True, cwd=project, input="{}", capture_output=True,
            text=True, timeout=30, env=environment,
        )

    assert dispatch("graphify hook-check").returncode == 79
    # This control preserves the exact selected path and proves the original
    # missing quotation fails through this same command consumer and fixture.
    assert dispatch(f"{launcher.as_posix()} hook-check").returncode != 0
    completed = dispatch(command)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert not (project / "INJECTED").exists()
