"""REQ-CORE-004: execute hosted Windows tool selection through real PowerShell."""
from __future__ import annotations

import ast
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import textwrap
import xml.etree.ElementTree as ET

import pytest


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
    if os.name != "nt":
        pytest.skip("Native Windows PowerShell application discovery")
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


# These full modules own native behavior omitted by the QML prefix-only lane.
REQUIRED_NATIVE_MODULES = (
    "tests/test_atomic_writes.py", "tests/test_atomic_replace_retention.py",
    "tests/test_owned_readonly_replacement.py", "tests/test_graphml_owned_replacement.py",
    "tests/test_skillgen_interpreter_identity.py", "tests/test_native_newline_cli.py",
)


def windows_job():
    """Read the actual owning job, not a filename mentioned elsewhere in YAML."""
    matches = re.findall(r"(?ms)^  windows-compatibility:\n(.*?)(?=^  [\w-]+:|\Z)",
                         WORKFLOW.read_text(encoding="utf-8"))
    assert len(matches) == 1, "Expected one native compatibility job"
    return matches[0]


def selection_assignment():
    """Return the sole workflow-owned array assignment unchanged for execution."""
    matches = re.findall(r"(?ms)^          (\$selection = @\(\n.*?^          \))", windows_job())
    assert len(matches) == 1, "Expected one workflow-owned native selection"
    return matches[0]


def selection_inventory(assignment):
    """Admit only literal existing test tokens; comments cannot fake inclusion."""
    assert assignment.startswith("$selection = @(\n") and assignment.endswith(")")
    body = "\n".join(line for line in assignment[len("$selection = @("):-1].splitlines()
                     if not line.lstrip().startswith("#"))
    items = re.findall(r"'([^'\r\n]*)'", body)
    assert not re.sub(r"[\s,]", "", re.sub(r"'[^'\r\n]*'", "", body)), "Nonliteral selection"
    assert len(items) == len(set(items)), "Duplicate selection"
    assert set((*REQUIRED_NATIVE_MODULES, "tests/test_ci_windows_tools.py")) <= set(items), "Required native modules missing"
    for item in items:
        assert re.fullmatch(r"tests/test_\w+\.py(?:::\w+)?", item), "Malformed test token"
        path, _, function = item.partition("::")
        source = WORKFLOW.parents[2] / path
        assert source.is_file(), "Unknown test module"
        if function:
            assert any(isinstance(node, ast.FunctionDef) and node.name == function
                       for node in ast.parse(source.read_text(encoding="utf-8")).body), "Unknown test node"
    return items


def native_case_program():
    """The workflow owns required-case validation; tests execute its actual program."""
    matches = re.findall(r"(?ms)^\s*\$nativeCaseProof = @'\n(.*?)^          '@", windows_job())
    assert len(matches) == 1, "Expected one workflow-owned native JUnit proof"
    return textwrap.dedent(matches[0])


def required_cases():
    """Keep the workflow's exact critical identities bound to source declarations."""
    program = ast.parse(native_case_program())
    (value,) = [node.value for node in program.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == "required" for target in node.targets)]
    required = ast.literal_eval(value)
    assert set(required) == {path[:-3].replace("/", ".") for path in REQUIRED_NATIVE_MODULES}
    assert sum(map(len, required.values())) == 29
    for module, names in required.items():
        assert names == sorted(set(names))
        wanted = {name.split("[", 1)[0] for name in names}
        source = WORKFLOW.parents[2] / (module.replace(".", "/") + ".py")
        declared = set()
        for node in ast.parse(source.read_text(encoding="utf-8")).body:
            if not isinstance(node, ast.FunctionDef) or node.name not in wanted:
                continue
            marks = [mark for mark in node.decorator_list if isinstance(mark, ast.Call)
                     and isinstance(mark.func, ast.Attribute) and mark.func.attr == "parametrize"]
            assert len(marks) <= 1
            if marks:
                declared.update(f"{node.name}[{item}]" for item in ast.literal_eval(marks[0].args[1]))
            else:
                declared.add(node.name)
        assert set(names) <= declared, "Critical JUnit identity no longer matches its source"
    return required


def native_audit_block():
    """Execute only the real case-audit/artifact tail, never setup or corpus hooks."""
    matches = re.findall(r"(?ms)^            \$nativeCaseProof = @'.*?(?=^          \} catch \{)", windows_job())
    assert len(matches) == 1
    return textwrap.dedent(matches[0])


def test_req_core004_ac02_actual_windows_inventory_covers_native_regressions():
    """Portable inventory cannot pass because a filename appears in a comment or another job."""
    assert selection_inventory(selection_assignment())
    assert required_cases()


@pytest.mark.parametrize("mutation", ["omit", "omit_guard", "duplicate", "expression", "unknown_file", "unknown_node"])
def test_req_core004_ac03_selection_rejects_omissions_and_nonliteral_tokens(mutation):
    """Omitted names remain as comment decoys in a private copy of the actual array."""
    assignment = selection_assignment()
    if mutation in {"omit", "omit_guard"}:
        omitted = REQUIRED_NATIVE_MODULES[0] if mutation == "omit" else "tests/test_ci_windows_tools.py"
        assignment = assignment.replace("'" + omitted + "'", "", 1)
        assignment = assignment[:-1] + "\n# '" + omitted + "'\n)"
    else:
        token = {"duplicate": "'" + REQUIRED_NATIVE_MODULES[0] + "'",
                 "expression": "$(Get-Date)", "unknown_file": "'tests/test_not_present.py'",
                 "unknown_node": "'tests/test_atomic_writes.py::not_declared'"}[mutation]
        assignment = assignment[:-1] + "\n" + token + "\n)"
    with pytest.raises(AssertionError):
        selection_inventory(assignment)


def test_req_core004_ac02_native_array_execution_matches_portable_inventory(powershell):
    """Real PowerShell receives the exact array, including established newline separators."""
    assignment = selection_assignment()
    expected = selection_inventory(assignment)
    result = execute(powershell, assignment + "\nConvertTo-Json -InputObject @($selection) -Compress", ())
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == expected


def public_junit(directory, failure):
    """Build public observations; the actual workflow remains the validation owner."""
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite")
    for module, names in required_cases().items():
        for name in names:
            ET.SubElement(suite, "testcase", classname=module, name=name)
    case = suite[0]
    if failure == "missing":
        suite.remove(case)
    elif failure == "duplicate":
        ET.SubElement(suite, "testcase", attrib=dict(case.attrib))
    elif failure in {"skipped", "failure", "error"}:
        ET.SubElement(case, failure)
    # Existing unrelated platform skips are not silently promoted to acceptance
    # or rejected as if they were one of the assigned native critical cases.
    ET.SubElement(ET.SubElement(suite, "testcase", classname="unrelated", name="other"), "skipped")
    path = directory / "public junit.xml"
    if failure == "malformed":
        path.write_bytes(b"<")
    elif failure != "absent":
        ET.ElementTree(root).write(path, encoding="utf-8")
    return path


@pytest.mark.parametrize("failure", [None, "missing", "duplicate", "skipped", "failure", "error", "malformed", "absent"])
def test_req_core004_ac03_actual_junit_proof_requires_each_native_case(tmp_path, failure):
    """Execute the workflow's real proof against public valid/failed/missing JUnit records."""
    path = public_junit(tmp_path, failure)
    result = subprocess.run([sys.executable, "-c", native_case_program(), str(path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == (0 if failure is None else 1)
    evidence = json.loads(result.stdout)
    assert evidence["required_native_cases"] == 29
    assert evidence["required_native_cases_passed"] is (failure is None)
    assert not result.stderr



@pytest.mark.parametrize("failure", [None, "skipped"])
def test_req_core004_ac03_native_audit_retains_integrity_when_case_proof_rejects(tmp_path, powershell, failure):
    """Real audit writes both artifacts before rejecting failed native acceptance."""
    directory = tmp_path / "native evidence"
    directory.mkdir()
    public_junit(directory, failure).rename(directory / "tests.xml")
    quote = lambda value: "'" + str(value).replace("'", "''") + "'"
    body = "\n".join(("$proofPython = " + quote(sys.executable), "$proofDirectory = " + quote(directory),
                       "$dependencyRetained = $true", "$headRetained = $true", "$inputsRetained = $true"))
    result = execute(powershell, body + "\n" + native_audit_block(), ())
    assert (result.returncode == 0) is (failure is None)
    evidence = json.loads((directory / "native-cases.json").read_text(encoding="utf-8-sig"))
    integrity = json.loads((directory / "integrity.json").read_text(encoding="utf-8-sig"))
    assert evidence["required_native_cases_passed"] is (failure is None)
    assert integrity == {"dependencies_unchanged": True, "checkout_unchanged": True,
                         "tracked_inputs_unchanged": True, "required_native_cases_passed": failure is None}
