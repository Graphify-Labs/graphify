import pytest
import subprocess
import sys
import os
from pathlib import Path


def _run_cli(args, tmp_path):
    env = os.environ.copy()
    home = tmp_path / "home"
    home.mkdir()
    env["HOME"] = str(home)
    env["USERPROFILE"] = str(home)
    env["HOMEDRIVE"] = home.drive
    env["HOMEPATH"] = str(home)[len(home.drive):]
    env["PYTHONPATH"] = str(Path.cwd()) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        env=env,
        capture_output=True,
        text=True,
    )


def test_cli_global_add_single(tmp_path):
    d = tmp_path / "repoA" / "out"
    d.mkdir(parents=True)
    g = d / "graph.json"
    g.write_text('{"nodes": [], "links": []}')
    
    res = _run_cli(["global", "add", str(g)], tmp_path)
    assert res.returncode == 0
    assert "repoA" in res.stdout
    assert "global graph" in res.stdout

def test_cli_global_add_explicit_tag(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text('{"nodes": [], "links": []}')
    
    res = _run_cli(["global", "add", str(g), "--as", "myrepo"], tmp_path)
    assert res.returncode == 0
    assert "myrepo" in res.stdout

def test_cli_global_add_multiple(tmp_path):
    d1 = tmp_path / "repoA" / "out"
    d1.mkdir(parents=True)
    g1 = d1 / "graph.json"
    g1.write_text('{"nodes": [], "links": []}')
    
    d2 = tmp_path / "repoB" / "out"
    d2.mkdir(parents=True)
    g2 = d2 / "graph.json"
    g2.write_text('{"nodes": [], "links": []}')
    
    res = _run_cli(["global", "add", str(g1), str(g2)], tmp_path)
    assert res.returncode == 0
    assert "repoA" in res.stdout
    assert "repoB" in res.stdout

def test_cli_global_add_invalid_as_multiple(tmp_path):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    g1.write_text('{"nodes": [], "links": []}')
    g2.write_text('{"nodes": [], "links": []}')
    
    res = _run_cli(["global", "add", str(g1), str(g2), "--as", "myrepo"], tmp_path)
    assert res.returncode == 1
    assert "--as can only be used with a single graph path" in res.stderr
