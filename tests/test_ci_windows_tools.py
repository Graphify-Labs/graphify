"""REQ-CORE-004: execute hosted Windows tool selection through real PowerShell."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess

import pytest


pytestmark = pytest.mark.skipif(os.name != "nt", reason="Native Windows PowerShell application discovery")
WORKFLOW = Path(__file__).resolve().parents[1] / ".github/workflows/ci.yml"


def assignment(tool):
    """The workflow owns the executable selector; tests execute its actual RHS."""
    matches = re.findall(rf"^\s*\$proof{tool.capitalize()}\s*=\s*(.+)$",
                         WORKFLOW.read_text(encoding="utf-8"), re.MULTILINE)
    assert len(matches) == 1, f"Expected one workflow-owned {tool} selector"
    return matches[0]


def node_version_guard():
    lines = [line.strip() for line in WORKFLOW.read_text(encoding="utf-8").splitlines()
             if line.strip().startswith("if ((& $proofNode --version)")]
    assert len(lines) == 1, "Expected one workflow-owned Node admission guard"
    return lines[0]


@pytest.fixture
def powershell():
    """Use the real native shell even when validation excludes installers from PATH."""
    shell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    assert shell.is_file(), "Required native Windows PowerShell is unavailable"
    return shell


def real_binary(tool):
    """uv is an explicit proof dependency, retained off the corpus consumer PATH."""
    selected = os.environ.get("GRAPHIFY_TEST_UV") if tool == "uv" else None
    selected = selected or shutil.which(tool)
    if not selected:
        pytest.skip(f"Real {tool} executable unavailable; hosted proof must admit its test dependency")
    path = Path(selected).resolve()
    assert path.is_file(), f"Selected {tool} executable is missing"
    return path


def execute(shell, body, directories):
    """Restrict only the child process PATH; no installer or machine setting changes."""
    environment = dict(os.environ)
    system = Path(os.environ["SystemRoot"]) / "System32"
    environment["PATH"] = os.pathsep.join(str(path) for path in (*directories, system))
    script = "$ErrorActionPreference = 'Stop'\n"
    script += "[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)\n" + body
    return subprocess.run([str(shell), "-NoProfile", "-NonInteractive", "-Command", script],
                          env=environment, capture_output=True, text=True, encoding="utf-8", timeout=30)


@pytest.mark.parametrize("tool", ["node", "uv"])
def test_req_core004_ac02_workflow_executes_first_real_path_application(
        tmp_path, powershell, tool):
    """Two actual binaries reproduce hosted discovery; one scalar first path executes."""
    original = real_binary(tool)
    preferred = tmp_path / "preferred application directory" / (tool + ".exe")
    preferred.parent.mkdir()
    shutil.copy2(original, preferred)
    variable = "$proof" + tool.capitalize()
    body = variable + " = " + assignment(tool) + "\n"
    body += "$version = (& " + variable + " --version)\n"
    body += "if ($LASTEXITCODE -ne 0) { throw 'Selected real application cannot execute' }\n"
    body += "$candidates = @((Get-Command " + tool + " -CommandType Application).Source)\n"
    body += "[ordered]@{selected=" + variable + ";version=$version;candidates=$candidates} | ConvertTo-Json -Compress\n"
    result = execute(powershell, body, (preferred.parent, original.parent))
    assert result.returncode == 0, result.stderr
    evidence = json.loads(result.stdout)
    assert isinstance(evidence["selected"], str) and Path(evidence["selected"]) == preferred
    assert [Path(path) for path in evidence["candidates"]] == [preferred, original]
    assert evidence["version"], "Actual selected executable must complete its version command"
    if tool == "node":
        identity = execute(powershell, variable + " = " + assignment(tool)
                           + "\n& " + variable + " -p process.execPath", (preferred.parent, original.parent))
        assert identity.returncode == 0 and Path(identity.stdout.strip()) == preferred


@pytest.mark.parametrize("tool", ["node", "uv"])
def test_req_core004_ac03_missing_workflow_application_has_no_fallback(powershell, tool):
    """The actual selector rejects absent PATH authority before invoking any application."""
    result = execute(powershell, "$proof" + tool.capitalize() + " = " + assignment(tool), ())
    assert result.returncode != 0
    assert "CommandNotFoundException" in result.stderr and f"'{tool}'" in result.stderr


def test_req_core004_ac03_node_guard_rejects_real_incompatible_application(
        tmp_path, powershell):
    """A real uv binary named node cannot bypass the workflow's exact Node version gate."""
    original = real_binary("uv")
    incompatible = tmp_path / "incompatible application directory" / "node.exe"
    incompatible.parent.mkdir()
    shutil.copy2(original, incompatible)
    body = "$proofNode = " + assignment("node") + "\n"
    body += "& $proofNode --version\n" + node_version_guard()
    result = execute(powershell, body, (incompatible.parent,))
    assert result.returncode != 0
    assert result.stdout.startswith("uv "), "The real incompatible executable must run"
    assert "The reviewed Node.js test interpreter was not selected" in result.stderr
