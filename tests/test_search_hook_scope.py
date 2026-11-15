"""Only searches known to target files outside the graph should lose the hint."""
import io
import json
import os
import sys

import pytest

from graphify.cli import _run_hook_guard, _search_is_outside_project


def _invoke(monkeypatch, project, tool_input):
    monkeypatch.chdir(project)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    monkeypatch.delenv("GRAPHIFY_OUT", raising=False)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(json.dumps({
        "session_id": "scope-test", "tool_input": tool_input,
    }).encode())))
    output = io.StringIO()
    monkeypatch.setattr(sys, "stdout", output)
    _run_hook_guard("search")
    return output.getvalue()


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    (root / "graphify-out").mkdir(parents=True)
    (root / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")
    return root


@pytest.mark.parametrize("command", [
    "grep -rn Findings '{outside}'",
    "rg Findings '{outside}'",
    "grep -n -e Findings '{outside}'",
    "rg --glob '*.txt' -e Findings '{outside}'",
    "grep -A 2 Findings '{outside}'",
    "grep -f patterns.txt '{outside}'",
    "rg --regexp=Findings '{outside}'",
    "rg --glob=*.txt Findings '{outside}'",
    "grep -- Findings '{outside}'",
    "grep Findings ../external.txt",
])
def test_shell_external_search_is_silent(monkeypatch, project, command):
    outside = (project.parent / "external log.txt").as_posix()
    assert not _invoke(monkeypatch, project, {"command": command.format(outside=outside)})
    assert not (project / "graphify-out/cache/hook_sessions/scope-test.nudges").exists()


@pytest.mark.parametrize("relative", [False, True])
def test_grep_tool_external_search_is_silent(monkeypatch, project, relative):
    outside = "../external.txt" if relative else str(project.parent / "external.txt")
    assert not _invoke(monkeypatch, project, {"pattern": "Findings", "path": outside})


@pytest.mark.parametrize("tool_input", [
    {"pattern": "Findings"},
    {"pattern": "Findings", "path": "."},
    {"pattern": "Findings", "path": "src"},
    {"command": "grep Findings src.txt ../external.txt"},
    {"command": "rg Findings"},
    {"command": "grep Findings ../external.txt && rg Findings ."},
    {"command": "grep Findings $TARGET"},
    {"command": "grep Findings ../*.txt"},
    {"command": "grep --unknown-option ../external.txt"},
    {"command": "grep -e Findings"},
    {"command": "grep -A"},
    {"command": "grep -e"},
    {"command": "grep Findings 'unterminated"},
    {"command": "sudo grep Findings ../external.txt"},
    {"command": "find ../external -name '*.txt'"},
    {"command": "rg Findings -"},
])
def test_project_or_uncertain_search_keeps_nudge(monkeypatch, project, tool_input):
    assert "graphify query" in _invoke(monkeypatch, project, tool_input)


def test_project_absolute_path_keeps_nudge(monkeypatch, project):
    assert "graphify query" in _invoke(monkeypatch, project, {
        "pattern": "Findings", "path": str(project / "source.txt"),
    })


def test_sibling_with_project_prefix_is_external(monkeypatch, project):
    assert not _invoke(monkeypatch, project, {
        "pattern": "Findings", "path": str(project.parent / "project-other"),
    })


def test_relative_path_is_resolved_from_working_directory(monkeypatch, project):
    nested = project / "nested"
    nested.mkdir()
    monkeypatch.chdir(nested)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(project))
    assert not _search_is_outside_project({"command": "rg Findings ../src"})
    assert _search_is_outside_project({"command": "rg Findings ../../external"})


@pytest.mark.skipif(os.name != "nt", reason="Windows shell drive mappings")
@pytest.mark.parametrize("path", ["/c/project", "/mnt/c/project"])
def test_unmapped_shell_drive_path_keeps_nudge(monkeypatch, project, path):
    assert "graphify query" in _invoke(monkeypatch, project, {"command": f"rg Findings {path}"})


def test_in_project_symlink_to_external_is_silent(monkeypatch, project, requires_symlinks):
    target = project.parent / "external"
    target.mkdir()
    link = project / "linked"
    link.symlink_to(target, target_is_directory=True)
    assert not _invoke(monkeypatch, project, {"pattern": "Findings", "path": str(link)})
