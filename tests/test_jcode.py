"""Native Jcode integration tests.

Jcode exposes a global skill directory and a blocking ``pre_tool`` hook.  The
Graphify integration installs both and uses the hook to redirect the first raw
code search/read in a session to the existing knowledge graph.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from unittest.mock import patch


PYTHON = sys.executable


def _run_jcode_hook(
    cwd: Path,
    *,
    tool_name: str,
    tool_input: dict,
    session_id: str,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "JCODE_HOOK_EVENT": "pre_tool",
            "JCODE_HOOK_TOOL_NAME": tool_name,
            "JCODE_HOOK_SESSION_ID": session_id,
            "JCODE_HOOK_CWD": str(cwd),
        }
    )
    return subprocess.run(
        [PYTHON, "-m", "graphify", "jcode-hook"],
        cwd=cwd,
        env=env,
        input=json.dumps(tool_input),
        capture_output=True,
        text=True,
    )


def test_jcode_hook_redirects_first_raw_search_then_fails_open(tmp_path: Path) -> None:
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text("{}", encoding="utf-8")

    first = _run_jcode_hook(
        tmp_path,
        tool_name="agentgrep",
        tool_input={"query": "MemoryManager", "path": "src"},
        session_id="ses-jcode-search",
    )
    second = _run_jcode_hook(
        tmp_path,
        tool_name="agentgrep",
        tool_input={"query": "MemoryManager", "path": "src"},
        session_id="ses-jcode-search",
    )

    assert first.returncode == 2
    assert "graphify query" in first.stderr
    assert second.returncode == 0
    assert second.stderr == ""


def test_jcode_hook_allows_graphify_queries_and_unrelated_tools(tmp_path: Path) -> None:
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text("{}", encoding="utf-8")

    graphify_query = _run_jcode_hook(
        tmp_path,
        tool_name="bash",
        tool_input={"command": "graphify query 'memory architecture'"},
        session_id="ses-jcode-query",
    )
    unrelated = _run_jcode_hook(
        tmp_path,
        tool_name="write",
        tool_input={"file_path": "notes.txt", "content": "hello"},
        session_id="ses-jcode-write",
    )

    assert graphify_query.returncode == 0
    assert unrelated.returncode == 0


def test_jcode_install_registers_skill_and_pre_tool_hook_idempotently(
    tmp_path: Path, monkeypatch,
) -> None:
    from graphify.__main__ import main

    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    config = home / ".jcode" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "[agents]\nmemory_sidecar_enabled = true\n\n"
        "[hooks]\npre_tool = \"keep-existing-policy\"\n",
        encoding="utf-8",
    )

    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "jcode", "install"])
        main()
        main()

    skill = home / ".jcode" / "skills" / "graphify" / "SKILL.md"
    text = config.read_text(encoding="utf-8")
    assert skill.exists()
    assert "keep-existing-policy" in text
    assert text.count("jcode-hook") == 1


def test_jcode_uninstall_removes_only_graphify_owned_entries(
    tmp_path: Path, monkeypatch,
) -> None:
    from graphify.__main__ import main

    home = tmp_path / "home"
    project = tmp_path / "project"
    project.mkdir()
    config = home / ".jcode" / "config.toml"
    config.parent.mkdir(parents=True)
    config.write_text(
        "[hooks]\n"
        "pre_tool = [\"keep-existing-policy\", \"/usr/bin/graphify jcode-hook\"]\n",
        encoding="utf-8",
    )
    skill = home / ".jcode" / "skills" / "graphify" / "SKILL.md"
    skill.parent.mkdir(parents=True)
    skill.write_text("graphify", encoding="utf-8")

    monkeypatch.chdir(project)
    with patch("graphify.__main__.Path.home", return_value=home):
        monkeypatch.setattr(sys, "argv", ["graphify", "jcode", "uninstall"])
        main()

    text = config.read_text(encoding="utf-8")
    assert "keep-existing-policy" in text
    assert "jcode-hook" not in text
    assert not skill.exists()
