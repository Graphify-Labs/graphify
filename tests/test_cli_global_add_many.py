import pytest
import subprocess
import sys
from pathlib import Path

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

def test_cli_global_add_invalid_as_multiple(tmp_path):
    g1 = tmp_path / "graph1.json"
    g2 = tmp_path / "graph2.json"
    g1.write_text('{"nodes": [], "links": []}')
    g2.write_text('{"nodes": [], "links": []}')
    
    res = subprocess.run([sys.executable, "-m", "graphify", "global", "add", str(g1), str(g2), "--as", "myrepo"], capture_output=True, text=True)
    assert res.returncode == 1
    assert "--as can only be used with a single graph path" in res.stderr
