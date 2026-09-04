"""External package references must survive a no-change extraction."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.build import _sweep_raw_orphans


@pytest.mark.parametrize("specifier", ["external-package", "@scope/external-package"])
@pytest.mark.parametrize("no_cluster", [True, False])
def test_external_import_survives_incremental_extract(tmp_path, specifier, no_cluster):
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    loader = corpus / "loader.ts"
    loader.write_text(f"export async function load() {{ return import('{specifier}'); }}\n")
    other = corpus / "other.ts"
    other.write_text("export function other() { return 1; }\n")
    env = dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1]))

    def run():
        subprocess.run(
            [sys.executable, "-m", "graphify", "extract", "corpus", "--code-only",
             "--max-workers", "1", "--out", "result"]
            + (["--no-cluster"] if no_cluster else []),
            cwd=tmp_path, env=env, capture_output=True, text=True, timeout=30, check=True,
        )
        return json.loads((tmp_path / "result/graphify-out/graph.json").read_text())

    def imports(graph):
        ids = {n["id"] for n in graph["nodes"] if n.get("label") == specifier}
        return [e for e in graph.get("links", graph.get("edges", []))
                if e["target"] in ids and e.get("relation") == "dynamic_import"]

    fresh = run()
    assert imports(fresh), "fresh extraction must establish the dependency"
    unchanged = run()
    assert imports(unchanged) == imports(fresh)
    other.write_text("export function other() { return 2; }\n")
    assert imports(run()) == imports(fresh)
    second = corpus / "second.ts"
    second.write_text(f"export async function second() {{ return import('{specifier}'); }}\n")
    assert len(imports(run())) == 2
    loader.unlink()
    deleted = run()
    assert not any(n.get("source_file") == "loader.ts" for n in deleted["nodes"])
    assert len(imports(deleted)) == 1, "the surviving importer still needs this package"
    # An exclusion-only update also runs raw graph pruning before early exit.
    (corpus / ".graphifyignore").write_text("second.ts\n")
    excluded = run()
    assert not imports(excluded)
    assert not any(n.get("label") == specifier for n in excluded["nodes"])


def test_raw_orphan_sweep_preserves_standalone_and_hyperedge_nodes():
    previous = {"edges": [{"source": "file", "target": name}
                           for name in ("removed", "group-member", "still-used")]}
    current = {
        "nodes": [{"id": name, "source_file": ""}
                  for name in ("removed", "group-member", "still-used", "standalone")]
        + [{"id": "owned", "source_file": "keep.ts"}],
        "edges": [{"source": "other", "target": "still-used"}],
        "hyperedges": [{"nodes": ["group-member", "other", "owned"]}],
    }
    _sweep_raw_orphans(previous, current)
    assert {n["id"] for n in current["nodes"]} == {
        "group-member", "still-used", "standalone", "owned",
    }
