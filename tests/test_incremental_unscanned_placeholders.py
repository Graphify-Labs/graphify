"""A changed-files rebuild must keep nodes minted for files that never existed.

An unresolved dynamic import (``import('./queue.js')``) or a project a ``.sln``
lists but the checkout lacks makes the REFERRING file emit a node whose
``source_file`` is the missing path. The corpus sweep of an incremental
rebuild read that missing path as a deleted source and evicted the node, so the
unchanged referrer's edge to it dangled and was dropped; a full rebuild of the
same tree keeps both. The previous scan (manifest.json) is the deletion
evidence (#1795): a path it never listed cannot have been deleted.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.watch import _rebuild_code


def _graph(corpus: Path) -> dict:
    return json.loads((corpus / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _shape(graph: dict) -> tuple[set, set]:
    drop = ("community", "community_name")
    nodes = {json.dumps({k: v for k, v in n.items() if k not in drop}, sort_keys=True) for n in graph["nodes"]}
    edges = {json.dumps({k: v for k, v in e.items() if k not in drop}, sort_keys=True)
             for e in graph.get("links", graph.get("edges", []))}
    return nodes, edges


def _corpus(tmp_path: Path) -> Path:
    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "app.ts").write_text(
        "export async function load() {\n  return import('./queue.js');\n}\n", encoding="utf-8")
    (corpus / "other.ts").write_text("export function other() {\n  return 1;\n}\n", encoding="utf-8")
    return corpus


def _rebuild(corpus: Path, changed: list[str] | None = None) -> None:
    assert _rebuild_code(
        corpus,
        changed_paths=[Path(p) for p in changed] if changed is not None else None,
        no_cluster=True,
        acquire_lock=False,
        force=True,
    ) is True


def _placeholder_ids(graph: dict) -> set[str]:
    return {n["id"] for n in graph["nodes"] if n.get("source_file", "").endswith("queue.js")}


def test_placeholder_for_a_missing_import_target_survives_an_unrelated_change(tmp_path):
    corpus = _corpus(tmp_path)
    _rebuild(corpus)
    placeholder = _placeholder_ids(_graph(corpus))
    assert placeholder, "fixture no longer mints a placeholder for ./queue.js"

    (corpus / "other.ts").write_text("export function other() {\n  return 2;\n}\n", encoding="utf-8")
    _rebuild(corpus, ["other.ts"])
    incremental = _graph(corpus)

    assert _placeholder_ids(incremental) == placeholder
    assert any(e["target"] in placeholder for e in incremental["links"])

    _rebuild(corpus)
    assert _shape(incremental) == _shape(_graph(corpus)), "incremental graph differs from a full rebuild"


def test_a_scanned_file_that_was_deleted_is_still_evicted(tmp_path):
    corpus = _corpus(tmp_path)
    _rebuild(corpus)
    assert any(n.get("source_file", "").endswith("other.ts") for n in _graph(corpus)["nodes"])

    (corpus / "other.ts").unlink()
    _rebuild(corpus, ["other.ts"])

    assert not [n for n in _graph(corpus)["nodes"] if n.get("source_file", "").endswith("other.ts")]


def test_without_a_manifest_the_old_eviction_is_kept(tmp_path):
    corpus = _corpus(tmp_path)
    _rebuild(corpus)
    (corpus / "graphify-out" / "manifest.json").unlink()

    (corpus / "other.ts").write_text("export function other() {\n  return 2;\n}\n", encoding="utf-8")
    _rebuild(corpus, ["other.ts"])

    assert not _placeholder_ids(_graph(corpus))


def test_a_manifest_anchored_elsewhere_is_no_evidence(tmp_path):
    corpus = _corpus(tmp_path)
    _rebuild(corpus)
    manifest = corpus / "graphify-out" / "manifest.json"
    manifest.write_text(json.dumps({"some/other/root/x.ts": 1}), encoding="utf-8")

    (corpus / "other.ts").write_text("export function other() {\n  return 2;\n}\n", encoding="utf-8")
    _rebuild(corpus, ["other.ts"])

    assert not _placeholder_ids(_graph(corpus))


def test_a_deleted_real_file_is_evicted_even_if_the_manifest_lost_it(tmp_path):
    """A stale manifest must not turn a deleted, extracted file into a kept
    placeholder: its own file node and edges prove it was scanned."""
    corpus = _corpus(tmp_path)
    (corpus / "lib.ts").write_text("export function helper() {\n  return 1;\n}\n", encoding="utf-8")
    (corpus / "user.ts").write_text(
        "import { helper } from './lib';\nexport function use() {\n  return helper();\n}\n",
        encoding="utf-8")
    _rebuild(corpus)
    assert any(n.get("source_file", "").endswith("lib.ts") for n in _graph(corpus)["nodes"])

    manifest = corpus / "graphify-out" / "manifest.json"
    scanned = json.loads(manifest.read_text(encoding="utf-8"))
    stale = {k: v for k, v in scanned.items() if not k.endswith("lib.ts")}
    assert len(stale) < len(scanned)
    manifest.write_text(json.dumps(stale), encoding="utf-8")

    (corpus / "lib.ts").unlink()  # deleted outside the change set
    (corpus / "other.ts").write_text("export function other() {\n  return 2;\n}\n", encoding="utf-8")
    _rebuild(corpus, ["other.ts"])

    assert not [n for n in _graph(corpus)["nodes"] if n.get("source_file", "").endswith("lib.ts")]
