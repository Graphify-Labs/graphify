"""A --no-cluster graph.json must not carry extract()'s run-only keys.

extract() returns ``extracted_sources`` (#3411) and ``failed_sources`` (#2543)
next to nodes/edges. They steer the current run and hold the absolute paths of
its inputs. The raw --no-cluster writers dumped the extraction as graph.json, so
the first ``graphify update --no-cluster`` and every ``graphify extract
--no-cluster`` wrote the checkout path and OS username into the graph, and a
first build differed from a rebuild of the same tree.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from graphify.extract import RUN_ONLY_EXTRACTION_KEYS

PYTHON = sys.executable


def _corpus(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "app.py").write_text("import os\n\n\ndef home():\n    return os.getcwd()\n", encoding="utf-8")
    (root / "util.py").write_text("from app import home\n\n\ndef where():\n    return home()\n", encoding="utf-8")
    return root


def _run(root: Path, *args: str) -> dict:
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PYTHON, "-m", "graphify", *args], cwd=root, env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr[-2000:]
    text = (root / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    assert "alice_home" not in text, "graph.json embeds the checkout path"
    return json.loads(text)


def test_run_only_keys_are_the_ones_extract_returns(tmp_path: Path):
    from graphify.extract import extract

    root = _corpus(tmp_path / "proj")
    result = extract([root / "app.py", root / "util.py"], root=root, cache_root=tmp_path / "cache")
    assert RUN_ONLY_EXTRACTION_KEYS <= set(result)


def test_update_no_cluster_first_build_matches_a_rebuild(tmp_path: Path):
    root = _corpus(tmp_path / "alice_home" / "proj")
    first = _run(root, "update", ".", "--no-cluster")
    assert not RUN_ONLY_EXTRACTION_KEYS & set(first)
    rebuilt = _run(root, "update", ".", "--no-cluster", "--force")
    assert set(first) == set(rebuilt)


def test_extract_no_cluster_omits_run_only_keys(tmp_path: Path):
    root = _corpus(tmp_path / "alice_home" / "proj")
    graph = _run(root, "extract", ".", "--code-only", "--no-cluster")
    assert not RUN_ONLY_EXTRACTION_KEYS & set(graph)
    graph = _run(root, "extract", ".", "--code-only", "--no-cluster", "--force")
    assert not RUN_ONLY_EXTRACTION_KEYS & set(graph)
