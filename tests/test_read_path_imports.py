"""Read-only commands do not import the language extractors.

`query` (and the MCP server's graph load) call build.graph_has_legacy_ids,
which needs only the 3-line `_file_stem`. Importing it from
graphify.extractors.base ran graphify/extractors/__init__.py, which imports
every language extractor: about 55 ms on each cold `graphify query` and MCP
start, for nothing. `_file_stem` now lives in graphify.ids (re-exported from
extractors.base), and these commands must never pull graphify.extractors in.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]

_GRAPH = {
    "directed": False,
    "multigraph": False,
    "graph": {},
    "nodes": [
        {"id": "pkg_models", "label": "models.py", "file_type": "code",
         "source_file": "pkg/models.py", "source_location": "L1", "community": 0},
        {"id": "pkg_models_user", "label": "User", "file_type": "code",
         "source_file": "pkg/models.py", "source_location": "L3", "community": 0},
        {"id": "pkg_service", "label": "service.py", "file_type": "code",
         "source_file": "pkg/service.py", "source_location": "L1", "community": 1},
        {"id": "pkg_service_run", "label": "run()", "file_type": "code",
         "source_file": "pkg/service.py", "source_location": "L5", "community": 1},
    ],
    "links": [
        {"source": "pkg_models", "target": "pkg_models_user", "relation": "contains",
         "confidence": "EXTRACTED", "source_file": "pkg/models.py"},
        {"source": "pkg_service", "target": "pkg_service_run", "relation": "contains",
         "confidence": "EXTRACTED", "source_file": "pkg/service.py"},
        {"source": "pkg_service_run", "target": "pkg_models_user", "relation": "calls",
         "confidence": "EXTRACTED", "source_file": "pkg/service.py"},
    ],
}

# Run one CLI command in a fresh interpreter, then report which heavy
# modules it imported. The command's own output goes to /dev/null.
_PROBE = """
import io, json, os, runpy, sys
sys.argv = ["graphify", *json.loads(sys.argv[1])]
real_stdout = sys.stdout
sys.stdout = io.StringIO()
try:
    runpy.run_module("graphify", run_name="__main__")
except SystemExit:
    pass
sys.stdout = real_stdout
print(json.dumps(sorted(m for m in sys.modules if m == "graphify.extractors"
                        or m.startswith("graphify.extractors."))))
"""

_COMMANDS = {
    "query": ["query", "how does run use User"],
    "explain": ["explain", "User"],
    "path": ["path", "run()", "User"],
    "affected": ["affected", "User"],
}


@pytest.fixture
def graph_dir(tmp_path):
    out = tmp_path / "graphify-out"
    out.mkdir()
    (out / "graph.json").write_text(json.dumps(_GRAPH), encoding="utf-8")
    return tmp_path


@pytest.mark.parametrize("name", sorted(_COMMANDS))
def test_read_command_does_not_import_extractors(graph_dir, name):
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE, json.dumps(_COMMANDS[name])],
        cwd=graph_dir,
        env={**os.environ, "PYTHONPATH": str(_REPO)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    loaded = json.loads(proc.stdout.strip().splitlines()[-1])
    assert loaded == [], f"`graphify {name}` imported {loaded}"


def test_mcp_graph_load_does_not_import_extractors(graph_dir):
    probe = (
        "import json, sys\n"
        "from graphify.serve import _load_graph\n"
        f"_load_graph({str(graph_dir / 'graphify-out' / 'graph.json')!r})\n"
        "print(json.dumps(sorted(m for m in sys.modules if m.startswith('graphify.extractors'))))\n"
    )
    proc = subprocess.run(
        [sys.executable, "-c", probe],
        cwd=graph_dir,
        env={**os.environ, "PYTHONPATH": str(_REPO)},
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert proc.returncode == 0, proc.stderr
    assert json.loads(proc.stdout.strip().splitlines()[-1]) == []


def test_file_stem_is_one_function():
    """extractors.base still exports the same function the read path uses."""
    from graphify.extractors.base import _file_stem as from_base
    from graphify.ids import _file_stem as from_ids

    assert from_base is from_ids
    assert from_ids(Path("docs/v1/api/README.md")) == "docs/v1/api/README"
    assert from_ids(Path("setup.py")) == "setup"
    assert from_ids(Path(".")) == ""


def test_legacy_id_note_still_fires():
    from graphify.build import graph_has_legacy_ids

    legacy = [{"id": "models", "source_file": "pkg/models.py", "source_location": "L1"}]
    current = [{"id": "pkg_models", "source_file": "pkg/models.py", "source_location": "L1"}]
    assert graph_has_legacy_ids(legacy) is True
    assert graph_has_legacy_ids(current) is False
