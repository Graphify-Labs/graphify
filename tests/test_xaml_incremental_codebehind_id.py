"""Re-extracting only a XAML file must not put the scan path into node ids.

The XAML extractor embeds the code-behind class it reads from Foo.xaml.cs. That
node's id is minted from the path the extractor saw, and extract() rewrites it
to the repo-relative form only for files it knows about. On a full scan
Foo.xaml.cs is in the batch. On an update that edits only Foo.xaml it was not,
so the class node kept an id built from the absolute path and the graph no
longer matched a full build.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

_LLM_ENV_KEYS = (
    "ANTHROPIC_API_KEY", "OPENAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY", "OLLAMA_BASE_URL",
    "AWS_PROFILE", "AWS_REGION", "AWS_DEFAULT_REGION", "AWS_ACCESS_KEY_ID",
)

_XAML = (
    '<Window x:Class="GraphifyDemo.MainWindow"\n'
    '        xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"\n'
    '        xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"\n'
    '        Loaded="Window_Loaded">\n'
    '    <Button x:Name="SaveButton" Content="Save" Click="Save_Click" />\n'
    "</Window>\n"
)
_CODEBEHIND = (
    "namespace GraphifyDemo {\n"
    "  public partial class MainWindow {\n"
    "    void Window_Loaded(object s, object e) {}\n"
    "    void Save_Click(object s, object e) {}\n"
    "  }\n"
    "}\n"
)


def _update(project: Path) -> None:
    env = {k: v for k, v in os.environ.items() if k not in _LLM_ENV_KEYS}
    env["GRAPHIFY_BACKEND"] = "none"
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "update", "."],
        cwd=project, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr


def _graph(project: Path) -> dict:
    return json.loads((project / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _write(project: Path) -> None:
    project.mkdir()
    (project / "MainWindow.xaml").write_text(_XAML, encoding="utf-8")
    (project / "MainWindow.xaml.cs").write_text(_CODEBEHIND, encoding="utf-8")


def test_editing_only_the_xaml_keeps_codebehind_ids_relative(tmp_path):
    incremental = tmp_path / "incremental"
    _write(incremental)
    _update(incremental)
    with (incremental / "MainWindow.xaml").open("a", encoding="utf-8") as handle:
        handle.write("<!-- touched -->\n")
    _update(incremental)

    graph = _graph(incremental)
    scan_slug = str(incremental.resolve()).strip("/").replace("/", "_").replace("-", "_").lower()
    leaked = [node["id"] for node in graph["nodes"] if scan_slug[:20] in node["id"]]
    assert not leaked

    full = tmp_path / "full"
    _write(full)
    (full / "MainWindow.xaml").write_text(
        (incremental / "MainWindow.xaml").read_text(encoding="utf-8"), encoding="utf-8"
    )
    _update(full)
    full_graph = _graph(full)
    assert {n["id"] for n in graph["nodes"]} == {n["id"] for n in full_graph["nodes"]}
    assert {
        (e["source"], e["target"], e["relation"]) for e in graph["links"]
    } == {
        (e["source"], e["target"], e["relation"]) for e in full_graph["links"]
    }
