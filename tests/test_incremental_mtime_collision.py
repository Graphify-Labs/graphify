"""An incremental run must not skip a file whose mtime did not move.

``detect_incremental`` treats "mtime unchanged" as proof the content is
unchanged. That holds only while the filesystem can separate the two writes: an
edit keeping the file the same length and landing inside one timestamp tick
moves neither size nor mtime, so the file is classified unchanged and never
re-extracted, while the graph keeps serving the old content.

The stat-only fastpath is the point of the gate and must survive: a settled
corpus with a manifest from an earlier run has to cost zero content hashes.
"""
import os
import tempfile
import time
from pathlib import Path

import pytest

from graphify import detect as det


@pytest.fixture()
def corpus(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    for i in range(3):
        (src / f"f{i}.md").write_text(f"# Doc {i}\n\nBody {i}.\n", encoding="utf-8")
    # manifest lives outside the scanned tree so it is never part of the corpus
    return src, str(tmp_path / "manifest.json")


def _queued(result):
    return [f for flist in result["new_files"].values() for f in flist]


def test_same_size_rewrite_in_one_tick_is_requeued(corpus):
    """The bug: a rewrite the filesystem cannot distinguish by stat alone.

    The mtime is pinned back to the manifest's recorded value so the collision
    is reproduced deterministically rather than depending on how fast the
    manifest write happened to be.
    """
    import json

    src, manifest = corpus
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")

    target = src / "f1.md"
    stat_before = target.stat()
    target.write_text("# Doc X\n\nBody Y.\n", encoding="utf-8")
    # same length, and stat now reports exactly what the manifest recorded
    os.utime(target, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))

    assert target.stat().st_size == stat_before.st_size
    assert target.stat().st_mtime_ns == stat_before.st_mtime_ns

    queued = _queued(det.detect_incremental(src, manifest, kind="semantic"))
    assert len(queued) == 1, "a rewritten file must be re-queued"
    assert queued[0].endswith("f1.md")


def test_a_settled_corpus_costs_no_content_hashes(corpus, monkeypatch):
    """The fastpath must survive: an untouched corpus does zero MD5 work."""
    src, manifest = corpus
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")

    old = time.time() - 3600
    for f in src.glob("*.md"):
        os.utime(f, (old, old))
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")

    calls = {"n": 0}
    real = det._md5_file

    def counting(p):
        calls["n"] += 1
        return real(p)

    monkeypatch.setattr(det, "_md5_file", counting)
    result = det.detect_incremental(src, manifest, kind="semantic")

    assert calls["n"] == 0, "an unchanged corpus must not be re-hashed"
    assert _queued(result) == []


def test_a_genuinely_edited_file_is_still_requeued(corpus):
    """Control: the ordinary size-change path is untouched."""
    src, manifest = corpus
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")

    (src / "f2.md").write_text(
        "# Doc 2\n\nA substantially longer body than before.\n", encoding="utf-8")

    queued = _queued(det.detect_incremental(src, manifest, kind="semantic"))
    assert len(queued) == 1 and queued[0].endswith("f2.md")


def test_an_untouched_file_is_not_requeued_after_a_neighbour_changes(corpus):
    """Only the edited file moves; its neighbours keep the fastpath."""
    src, manifest = corpus
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")

    old = time.time() - 3600
    for f in src.glob("*.md"):
        os.utime(f, (old, old))
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")

    (src / "f0.md").write_text("# Doc 0\n\nA different and longer body.\n",
                               encoding="utf-8")
    queued = _queued(det.detect_incremental(src, manifest, kind="semantic"))
    assert len(queued) == 1 and queued[0].endswith("f0.md")


def test_a_legacy_manifest_row_without_seen_still_works(corpus):
    """Rows predating the `seen` field come from an earlier run: trusted."""
    import json

    src, manifest = corpus
    det.save_manifest(det.detect(src)["files"], manifest, root=src, kind="semantic")
    data = json.loads(Path(manifest).read_text(encoding="utf-8"))
    for row in data.values():
        if isinstance(row, dict):
            row.pop("seen", None)
    Path(manifest).write_text(json.dumps(data), encoding="utf-8")

    assert _queued(det.detect_incremental(src, manifest, kind="semantic")) == []
