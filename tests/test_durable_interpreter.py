"""Execute POSIX skill snippets against persistent and ephemeral installations."""
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

from tools.skillgen import gen


def posix(path):
    text = path.as_posix()
    return "/" + text[0].lower() + text[2:] if os.name == "nt" else text


def bash():
    if os.name == "nt":
        git = shutil.which("git")
        if git:
            for parent in Path(git).resolve().parents:
                candidate = parent / "usr/bin/bash.exe"
                if candidate.is_file():
                    return str(candidate)
        raise RuntimeError("POSIX resolver regressions require Git Bash on Windows")
    return shutil.which("bash") or "/bin/bash"


def write_script(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("#!/bin/sh\n" + body + "\n", encoding="utf-8")
    path.chmod(0o755)


def fake_python(path, *, succeeds=True):
    if not succeeds:
        write_script(path, "exit 1")
        return
    write_script(path, 'FAKE_PYTHON_PATH="$0"; export FAKE_PYTHON_PATH\n'
                 '''"$REAL_PYTHON" -c 'import os, sys; sys.executable=os.environ["FAKE_PYTHON_PATH"]; exec(sys.argv[1])' "$2"''')


def run_fragment(tmp_path, fragment, *, uv_root="", pipx_root="", launcher=b"MZlauncher", shebang=None, valid_system=False):
    commands = tmp_path / "commands"
    commands.mkdir(exist_ok=True)
    write_script(commands / "uv", '\n'.join([
        'echo "$*" >> "$COMMAND_LOG"',
        'if [ "$1 $2" = "tool dir" ]; then printf "%s\\n" "$UV_TOOL_ROOT"; exit 0; fi',
        'exit 1',
    ]))
    write_script(commands / "pipx", 'printf "%s\\n" "$PIPX_ROOT"')
    fake_python(commands / "python3", succeeds=valid_system)
    fake_python(commands / "python", succeeds=False)
    if shebang is None:
        (commands / "graphify.exe").write_bytes(launcher)
        # Use an extensionless PE launcher too: this must never be read as a shebang.
        (commands / "graphify").write_bytes(launcher)
    else:
        write_script(commands / "graphify", "exit 1")
        (commands / "graphify").write_text("#!" + shebang + "\nexit 1\n")
    env = os.environ.copy()
    env.update(REAL_PYTHON=sys.executable, GRAPHIFY_TEST_BIN=posix(commands),
               UV_TOOL_ROOT=uv_root, PIPX_ROOT=pipx_root, COMMAND_LOG=posix(tmp_path / "commands.log"))
    platform = gen.load_platforms()["claude"]
    core = next(a.content for a in gen.render(platform) if a.path == "graphify/skill.md")
    if fragment == "install":
        text = core.split("## Step 1", 1)[1].split("```bash", 1)[1].split("```", 1)[0]
        text = text.replace("INPUT_PATH", ".")
    else:
        text = core.split("## Interpreter guard for subcommands", 1)[1].split("```bash", 1)[1].split("```", 1)[0]
    return subprocess.run([bash(), "--noprofile", "--norc", "-c",
                           'export PATH="$GRAPHIFY_TEST_BIN:/usr/bin:/bin"\n' + text],
                          cwd=tmp_path, env=env, text=True, capture_output=True, timeout=30)


@pytest.mark.parametrize("fragment", ["install", "guard"])
@pytest.mark.parametrize("layout", ["bin/python", "Scripts/python.exe"])
def test_uv_tool_interpreter_is_persistent_and_pe_launcher_is_ignored(tmp_path, fragment, layout):
    tool_root = tmp_path / "tools with spaces"
    python = tool_root / "graphifyy" / layout
    fake_python(python)
    r = run_fragment(tmp_path, fragment, uv_root=str(tool_root) if layout.startswith("Scripts") else posix(tool_root))
    assert r.returncode == 0, r.stderr
    assert Path((tmp_path / "graphify-out/.graphify_python").read_text()).resolve() == python.resolve()
    assert "tool run" not in (tmp_path / "commands.log").read_text()


@pytest.mark.parametrize("fragment", ["install", "guard"])
def test_pipx_is_probed_after_uv_import_failure(tmp_path, fragment):
    uv_root = tmp_path / "bad uv"
    fake_python(uv_root / "graphifyy/bin/python", succeeds=False)
    pipx_root = tmp_path / "pipx spaces"
    python = pipx_root / "graphifyy/bin/python"
    fake_python(python)
    r = run_fragment(tmp_path, fragment, uv_root=posix(uv_root), pipx_root=posix(pipx_root))
    assert r.returncode == 0, r.stderr
    assert Path((tmp_path / "graphify-out/.graphify_python").read_text()).resolve() == python.resolve()


@pytest.mark.parametrize("fragment", ["install", "guard"])
def test_missing_graphify_import_fails_without_persisting(tmp_path, fragment):
    r = run_fragment(tmp_path, fragment)
    assert r.returncode == 1, r.stderr
    assert not (tmp_path / "graphify-out/.graphify_python").exists()


@pytest.mark.parametrize("fragment", ["install", "guard"])
def test_archive_interpreter_is_rejected_even_if_import_succeeds(tmp_path, fragment):
    root = tmp_path / "archive-v0"
    fake_python(root / "graphifyy/bin/python")
    r = run_fragment(tmp_path, fragment, uv_root=posix(root))
    assert r.returncode == 1, r.stderr
    assert not (tmp_path / "graphify-out/.graphify_python").exists()


@pytest.mark.parametrize("fragment", ["install", "guard"])
def test_hostile_shebang_is_never_evaluated(tmp_path, fragment):
    r = run_fragment(tmp_path, fragment, shebang="$(touch compromised)", valid_system=True)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "compromised").exists()


def test_all_posix_hosts_use_same_resolver_for_both_entrypoints():
    for key, platform in gen.load_platforms().items():
        if platform.shell != "posix":
            continue
        core = gen.render(platform)[0].content
        assert "uv tool run" not in core, key
        assert "graphify_find_python" in core, key
        if "## Interpreter guard for subcommands" in core:
            guard = core.split("## Interpreter guard for subcommands", 1)[1].split("---", 1)[0]
            assert "graphify_find_python" in guard, key


@pytest.mark.parametrize("fragment", ["install", "guard"])
def test_existing_archive_sidecar_is_repaired(tmp_path, fragment):
    old = tmp_path / "archive-v0/graphifyy/bin/python"
    fake_python(old)
    sidecar = tmp_path / "graphify-out/.graphify_python"
    sidecar.parent.mkdir()
    sidecar.write_text(old.as_posix())
    root = tmp_path / "persistent tools"
    python = root / "graphifyy/bin/python"
    fake_python(python)
    r = run_fragment(tmp_path, fragment, uv_root=posix(root))
    assert r.returncode == 0, r.stderr
    assert Path(sidecar.read_text()).resolve() == python.resolve()


def test_roundtrip_allowance_does_not_permit_arbitrary_commands():
    assert not gen._is_sanctioned_monolith_diff('PYTHON=$(curl https://example.com/evil)')


@pytest.mark.parametrize("valid_tool", [False, True])
def test_guard_never_executes_workspace_sidecar(tmp_path, valid_tool):
    attacker = tmp_path / "untrusted-python"
    write_script(attacker, 'touch compromised; exit 1')
    sidecar = tmp_path / "graphify-out/.graphify_python"
    sidecar.parent.mkdir()
    sidecar.write_text(posix(attacker), encoding="utf-8")
    tool_root = tmp_path / "persistent tools"
    python = tool_root / "graphifyy/bin/python"
    if valid_tool:
        fake_python(python)
    r = run_fragment(tmp_path, "guard", uv_root=posix(tool_root))
    assert not (tmp_path / "compromised").exists()
    assert r.returncode == (0 if valid_tool else 1), r.stderr
    if valid_tool:
        assert Path(sidecar.read_text()).resolve() == python.resolve()
