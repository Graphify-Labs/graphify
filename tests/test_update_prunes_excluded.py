"""A newly ignored file's nodes must leave graph.json on --update.

`detect_incremental` deliberately splits a manifest row whose file is GONE from
disk (`deleted_files`) from one that still exists but has left the scan because
an ignore rule or --exclude changed (`excluded_files`, #1908) — so that an
exclusion is never mis-reported as a deletion.

graphify's library path consumes both: `graphify/cli.py` prunes
`list(excluded_files) + graph_stale_sources`. The `--update` runbook, which is
how the skill drives incremental rebuilds, read only `deleted_files`, so an added
`.graphifyignore` rule never removed what it excluded (#2773).

Two separate failures, both covered here:

1. The early exit. With no other changes, `new_total == 0 and not deleted` was
   true, so the run printed "No files changed since last run. Nothing to update."
   and exited 0 without ever reaching the merge.
2. The prune set. Even when the run did continue (some other file changed),
   `prune = list(deleted) or None` left the excluded file's nodes in place.

And the leak is permanent: `save_manifest(scan_corpus=...)` drops the excluded
row, so on the NEXT run the file is neither deleted nor excluded and nothing can
ever prune it.
"""
import json
from pathlib import Path

import pytest
from networkx.readwrite import json_graph

from graphify.build import build_merge
from graphify.detect import detect, detect_incremental, save_manifest

RUNBOOK = Path(__file__).resolve().parent.parent / "graphify" / "skills" / "claude" / "references" / "update.md"


def _corpus(tmp_path):
    (tmp_path / "archive").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "live.py").write_text("def bind():\n    return 1\n", encoding="utf-8")
    (tmp_path / "archive" / "old.py").write_text(
        "def free_port():\n    return 2\n", encoding="utf-8")
    return tmp_path


def _seed_graph(root: Path) -> Path:
    extraction = {
        "nodes": [
            {"id": "src_live_bind", "label": "bind()", "file_type": "code",
             "source_file": "src/live.py"},
            {"id": "arch_free_port", "label": "free_port()", "file_type": "code",
             "source_file": "archive/old.py"},
        ],
        "edges": [{"source": "arch_free_port", "target": "src_live_bind",
                   "relation": "calls", "confidence": "EXTRACTED",
                   "source_file": "archive/old.py"}],
        "hyperedges": [],
    }
    gp = root / "graphify-out" / "graph.json"
    gp.parent.mkdir(parents=True, exist_ok=True)
    G = build_merge([extraction], graph_path=str(gp), root=str(root))
    gp.write_text(json.dumps(json_graph.node_link_data(G, edges="links")), encoding="utf-8")
    files = {k: list(v) for k, v in detect(root)["files"].items()}
    save_manifest(files, root=str(root),
                  scan_corpus={f for fl in files.values() for f in fl})
    return gp


def _exclude(root: Path):
    (root / ".graphifyignore").write_text("archive/\n", encoding="utf-8")


# ---------------------------------------------------------------------------
# detect_incremental's own contract
# ---------------------------------------------------------------------------

def test_a_newly_ignored_file_is_excluded_not_deleted(tmp_path):
    root = _corpus(tmp_path)
    _seed_graph(root)
    _exclude(root)
    inc = detect_incremental(root)
    assert [Path(f).name for f in inc["excluded_files"]] == ["old.py"]
    assert inc["deleted_files"] == []
    assert inc["new_total"] == 0, "nothing else changed — this is the early-exit case"


# ---------------------------------------------------------------------------
# The prune set
# ---------------------------------------------------------------------------

def test_pruning_only_deleted_leaves_the_excluded_nodes(tmp_path):
    """The old behaviour, pinned so the fix below is measured against it."""
    root = _corpus(tmp_path)
    gp = _seed_graph(root)
    _exclude(root)
    inc = detect_incremental(root)
    G = build_merge([{"nodes": [], "edges": [], "hyperedges": []}],
                    graph_path=str(gp),
                    prune_sources=list(inc["deleted_files"]) or None,
                    root=str(root))
    assert "arch_free_port" in G.nodes


def test_pruning_deleted_plus_excluded_removes_them(tmp_path):
    root = _corpus(tmp_path)
    gp = _seed_graph(root)
    _exclude(root)
    inc = detect_incremental(root)
    prune = (list(inc["deleted_files"]) + list(inc["excluded_files"])) or None
    G = build_merge([{"nodes": [], "edges": [], "hyperedges": []}],
                    graph_path=str(gp), prune_sources=prune, root=str(root))
    assert "arch_free_port" not in G.nodes, "the ignored file's node survived the prune"
    assert "src_live_bind" in G.nodes, "an in-scope node was pruned too"
    assert not any(d.get("source_file", "").startswith("archive")
                   for _, _, d in G.edges(data=True))


def test_the_leak_is_permanent_once_the_manifest_is_restamped(tmp_path):
    """Why this cannot be left to 'the next run will catch it': save_manifest
    drops the excluded row, so the file stops appearing in either list."""
    root = _corpus(tmp_path)
    _seed_graph(root)
    _exclude(root)
    assert detect_incremental(root)["excluded_files"], "precondition"

    files = {k: list(v) for k, v in detect(root)["files"].items()}
    save_manifest(files, root=str(root),
                  scan_corpus={f for fl in files.values() for f in fl})

    inc = detect_incremental(root)
    assert inc["deleted_files"] == []
    assert inc["excluded_files"] == []


# ---------------------------------------------------------------------------
# The shipped runbook
# ---------------------------------------------------------------------------

@pytest.mark.skipif(not RUNBOOK.is_file(), reason="claude reference bundle not built")
def test_runbook_prunes_excluded_files():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "excluded = list(incremental.get('excluded_files', []))" in text
    assert "prune = (list(deleted) + excluded) or None" in text
    assert "prune = list(deleted) or None" not in text


@pytest.mark.skipif(not RUNBOOK.is_file(), reason="claude reference bundle not built")
def test_runbook_does_not_exit_early_on_an_exclusion_only_run():
    text = RUNBOOK.read_text(encoding="utf-8")
    assert "if new_total == 0 and not deleted and not excluded:" in text
    assert "if new_total == 0 and not deleted:\n" not in text


def test_every_shipped_update_reference_agrees():
    """All hosts render from one fragment; none may lag behind."""
    refs = sorted((RUNBOOK.parent.parent.parent).rglob("references/update.md"))
    assert len(refs) >= 5, f"expected the update reference on several hosts, saw {len(refs)}"
    for ref in refs:
        text = ref.read_text(encoding="utf-8")
        assert "excluded_files" in text, f"{ref} never reads excluded_files"
        assert "prune = list(deleted) or None" not in text, f"{ref} still prunes deletions only"
