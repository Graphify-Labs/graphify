import pytest
import subprocess
import sys
from pathlib import Path
import json

def test_cli_global_add_single(tmp_path):
    d = tmp_path / "repoA" / "out"
    d.mkdir(parents=True)
    g = d / "graph.json"
    g.write_text('{"nodes": [], "links": []}')
    
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", str(g)], capture_output=True, text=True)
    assert res.returncode == 0
    assert "repoA" in res.stdout
    assert "global graph" in res.stdout

def test_cli_global_add_explicit_tag(tmp_path):
    g = tmp_path / "graph.json"
    g.write_text('{"nodes": [], "links": []}')
    
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", str(g), "--as", "myrepo"], capture_output=True, text=True)
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
    
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", str(g1), str(g2)], capture_output=True, text=True)
    assert res.returncode == 0
    assert "repoA" in res.stdout
    assert "repoB" in res.stdout

def test_cli_global_add_keep_going(tmp_path):
    d1 = tmp_path / "repoA" / "out"
    d1.mkdir(parents=True)
    g1 = d1 / "graph.json"
    g1.write_text('{"nodes": [], "links": []}')
    
    d2 = tmp_path / "repoB" / "out"
    d2.mkdir(parents=True)
    g2 = d2 / "graph.json"
    g2.write_text('invalid json')
    
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", str(g1), str(g2), "--keep-going"], capture_output=True, text=True)
    assert res.returncode == 0
    assert "repoA" in res.stdout
    assert "failed to add 'repoB'" in res.stderr

def test_cli_global_add_invalid_as_multiple(tmp_path):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    g1.write_text('{"nodes": [], "links": []}')
    g2.write_text('{"nodes": [], "links": []}')
    
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", str(g1), str(g2), "--as", "myrepo"], capture_output=True, text=True)
    assert res.returncode == 1
    assert "--as can only be used with a single graph path" in res.stderr

def test_cli_global_add_empty_inferred_tag(tmp_path):
    # Pass a path that resolves to an empty parent.parent.name
    # Note: subprocess in tests runs in a specific CWD usually, but providing a pure filename means parent is empty
    import os
    g = tmp_path / "graph.json"
    g.write_text('{"nodes": [], "links": []}')
    
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path.cwd())
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", "graph.json"], cwd=tmp_path, env=env, capture_output=True, text=True)
    assert res.returncode == 1
    assert "error: could not infer repository tag for graph.json. Please specify it explicitly using --as <tag>." in res.stderr
