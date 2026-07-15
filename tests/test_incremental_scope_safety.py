"""Regression tests: a scoped ``--update <subfolder>`` must never report files
outside the scanned root as deleted.

Before this fix, ``detect_incremental`` computed deletions as
``[f for f in manifest if f not in current_files]`` where ``current_files`` only
contains paths under the scanned ``root``. Running an incremental update on a
subfolder of a larger corpus therefore flagged every out-of-scope manifest file
as deleted; the ``--update`` driver passes that list to
``build_merge(prune_sources=...)`` (whose anti-shrink guard is disabled while
pruning), silently wiping the rest of the graph.
"""
from __future__ import annotations

import os

from graphify.detect import detect_incremental, save_manifest


def _write(p, text="content"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"# {p.stem}\n{text}\n")
    return str(p)


def test_scoped_update_does_not_prune_out_of_scope_files(tmp_path, monkeypatch):
    """The core bug: updating a subfolder must not report the rest of the
    corpus as deleted."""
    corpus = tmp_path / "corpus"
    memtree = corpus / "memory"
    topics = corpus / "topics"
    mem = [_write(memtree / f"note_{i}.md") for i in range(3)]
    _write(topics / "old_topic.md")

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    manifest = "graphify-out/manifest.json"
    save_manifest({"document": mem + [str(topics / "old_topic.md")]},
                  manifest, kind="semantic")

    # Add a new topic, then incremental-detect ONLY the topics subfolder.
    _write(topics / "new_topic.md")
    res = detect_incremental(topics, manifest, kind="semantic")

    new = [f for v in res["new_files"].values() for f in v]
    assert res["deleted_files"] == [], (
        f"scoped update falsely reported deletions: {res['deleted_files']}"
    )
    assert any("new_topic" in f for f in new)
    assert not any("note_" in f for f in new), "out-of-scope files must not appear"


def test_genuine_in_scope_deletion_still_detected(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    topics = corpus / "topics"
    keep = _write(topics / "keep.md")
    gone = _write(topics / "gone.md")

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    manifest = "graphify-out/manifest.json"
    save_manifest({"document": [keep, gone]}, manifest, kind="semantic")

    os.remove(gone)
    res = detect_incremental(topics, manifest, kind="semantic")
    assert any("gone.md" in f for f in res["deleted_files"])
    assert not any("keep.md" in f for f in res["deleted_files"])


def test_full_root_update_prunes_genuinely_deleted(tmp_path, monkeypatch):
    corpus = tmp_path / "corpus"
    a = _write(corpus / "memory" / "a.md")
    b = _write(corpus / "topics" / "b.md")

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    manifest = "graphify-out/manifest.json"
    save_manifest({"document": [a, b]}, manifest, kind="semantic")

    os.remove(a)
    res = detect_incremental(corpus, manifest, kind="semantic")
    assert any("a.md" in f for f in res["deleted_files"])
    assert not any("b.md" in f for f in res["deleted_files"])


def test_on_disk_but_skipped_file_is_not_a_deletion(tmp_path, monkeypatch):
    """A manifest file still on disk but no longer returned by detect()
    (e.g. it became excluded/unsupported) must not be pruned."""
    corpus = tmp_path / "corpus"
    real = _write(corpus / "real.md")
    # An entry that exists on disk but detect() won't classify as a doc.
    skipped = corpus / "data.bin"
    skipped.parent.mkdir(parents=True, exist_ok=True)
    skipped.write_bytes(b"\x00\x01\x02")

    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    manifest = "graphify-out/manifest.json"
    save_manifest({"document": [real, str(skipped)]}, manifest, kind="semantic")

    res = detect_incremental(corpus, manifest, kind="semantic")
    assert not any("data.bin" in f for f in res["deleted_files"]), (
        "a file still present on disk must never be reported as deleted"
    )
