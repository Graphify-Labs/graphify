"""INC-QML-44: physical equality cannot override watch admission or semantic ownership."""
from __future__ import annotations

import json
import os

import graphify.extract as extraction
from graphify.watch import _rebuild_code
from tests.test_qt_final_incremental_parity import normalized
from tests.test_watch_physical_coowners import published


def observed_inputs(monkeypatch, root):
    """Observe real facade work while leaving parsing and publication intact."""
    observed, real_extract = [], extraction.extract

    def inputs(paths, *args, **kwargs):
        paths = list(paths)
        observed.append({path.relative_to(root).as_posix() for path in paths})
        return real_extract(paths, *args, **kwargs)

    monkeypatch.setattr(extraction, "extract", inputs)
    return observed


def test_req_qml011_ac01_semantic_backed_hardlink_keeps_its_own_tier(monkeypatch, tmp_path):
    """One physical edit refreshes the AST owner and preserves a semantic sibling verbatim."""
    root = tmp_path / "repo"
    root.mkdir()
    target, alias = root / "plain.md", root / "semantic.md"
    target.write_text("# Previous\n\nText.\n", encoding="utf-8")
    os.link(target, alias)
    assert target.stat().st_ino == alias.stat().st_ino
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False)
    path = root / "graphify-out/graph.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    # Seed only an external semantic result, as the existing semantic watch
    # fixtures do. Selection, AST reconciliation and persistence remain real.
    data["nodes"].append({"id": "semantic_concept", "label": "Retained concept",
                          "file_type": "concept", "source_file": "semantic.md"})
    path.write_text(json.dumps(data), encoding="utf-8")
    before, _ = normalized(published(root))
    sibling = {identity: value for identity, value in before.items()
               if published(root).nodes[identity].get("source_file") == "semantic.md"}
    observed = observed_inputs(monkeypatch, root)
    target.write_text("# Updated\n\nChanged.\n", encoding="utf-8")
    assert _rebuild_code(root, changed_paths=[target], no_cluster=True, acquire_lock=False)
    actual = published(root)
    after, _ = normalized(actual)
    assert observed == [{"plain.md"}]
    assert sibling == {identity: value for identity, value in after.items()
                       if actual.nodes[identity].get("source_file") == "semantic.md"}
    assert any(node.get("label") == "Updated" for _, node in actual.nodes(data=True)
               if node.get("source_file") == "plain.md")


def test_req_qml011_ac01_excluded_hardlink_cannot_reenter_the_corpus(monkeypatch, tmp_path):
    """A physically equal excluded source is absent from work and durable output."""
    root = tmp_path / "repo"
    root.mkdir()
    target, alias = root / "accepted.py", root / "excluded.py"
    target.write_text("def previous():\n    return 1\n", encoding="utf-8")
    os.link(target, alias)
    (root / ".graphifyignore").write_text("excluded.py\n", encoding="utf-8")
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False)
    observed = observed_inputs(monkeypatch, root)
    target.write_text("def updated():\n    return 2\n", encoding="utf-8")
    assert _rebuild_code(root, changed_paths=[target], no_cluster=True, acquire_lock=False)
    assert observed == [{"accepted.py"}]
    assert all(node.get("source_file") != "excluded.py" for _, node in published(root).nodes(data=True))
