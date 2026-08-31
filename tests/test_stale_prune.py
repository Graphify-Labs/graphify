"""#2210: incremental extract's graph-layer prune must not evict ALIVE files.

_stale_graph_sources compared stored graph source_file spellings against the
current scan with a raw string membership test: (a) no NFC/NFD normalization,
so a macOS NFD on-disk path never matched an NFC graph entry; (b) no liveness
check, so any membership miss was declared "deleted" and pruned even though
the file exists on disk and is in the scan. These tests exercise the NFC
normalization, the fail-closed liveness guard, and that genuinely-deleted
sources are still pruned.
"""
from __future__ import annotations
import json
import unicodedata

from graphify.cli import _stale_graph_sources
from graphify.detect import detect

NFC_NAME = unicodedata.normalize("NFC", "café.md")          # café.md, composed
NFD_NAME = unicodedata.normalize("NFD", "café.md")          # cafe + combining accent


def _write_graph(tmp_path, source_files: list[str]):
    out = tmp_path / "graphify-out"
    out.mkdir(exist_ok=True)
    graph_path = out / "graph.json"
    nodes = [
        {"id": f"n{i}", "label": f"node {i}", "source_file": sf}
        for i, sf in enumerate(source_files)
    ]
    graph_path.write_text(
        json.dumps({"nodes": nodes, "links": []}), encoding="utf-8"
    )
    return graph_path


def _scan(tmp_path):
    detection = detect(tmp_path)
    seen = {f for flist in detection["files"].values() for f in flist}
    seen.update(detection.get("unclassified", []))
    return detection, seen


def test_nfd_disk_nfc_graph_source_not_pruned(tmp_path):
    """(a) NFD spelling on disk vs NFC spelling in the graph: NOT stale."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / NFD_NAME).write_text("# cafe notes\n\nhello\n", encoding="utf-8")

    graph_path = _write_graph(tmp_path, ["docs/" + NFC_NAME])
    detection, seen = _scan(tmp_path)

    stale = _stale_graph_sources(graph_path, tmp_path, seen, detection=detection)
    assert stale == []


def test_bare_basename_alive_elsewhere_not_pruned(tmp_path, capsys):
    """(b) fail-closed: a legacy bare-basename source_file whose file is
    alive at docs/café.md cannot be proven deleted — keep it."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / NFD_NAME).write_text("# cafe notes\n\nhello\n", encoding="utf-8")

    graph_path = _write_graph(tmp_path, [NFC_NAME])  # bare legacy spelling
    detection, seen = _scan(tmp_path)

    stale = _stale_graph_sources(graph_path, tmp_path, seen, detection=detection)
    assert stale == []


def test_genuinely_deleted_source_still_pruned(tmp_path):
    """(c) a source_file with no file on disk anywhere IS pruned."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "keep.md").write_text("# keep\n\nstill here\n", encoding="utf-8")

    graph_path = _write_graph(tmp_path, ["docs/keep.md", "docs/gone.md"])
    detection, seen = _scan(tmp_path)

    stale = _stale_graph_sources(graph_path, tmp_path, seen, detection=detection)
    assert stale == ["docs/gone.md"]


def test_alive_but_ignored_source_is_pruned(tmp_path):
    """#1909 must keep working: an alive file excluded by ignore rules is
    provably excluded, so its nodes ARE pruned."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "keep.md").write_text("# keep\n\nstill here\n", encoding="utf-8")
    (docs / "secret.md").write_text("# secret\n\nexcluded\n", encoding="utf-8")
    (tmp_path / ".graphifyignore").write_text("docs/secret.md\n", encoding="utf-8")

    graph_path = _write_graph(tmp_path, ["docs/keep.md", "docs/secret.md"])
    detection, seen = _scan(tmp_path)

    stale = _stale_graph_sources(graph_path, tmp_path, seen, detection=detection)
    assert stale == ["docs/secret.md"]


def test_alive_unproven_exclusion_kept_with_warning(tmp_path, capsys):
    """Fail-closed: an alive in-root file missing from the corpus without
    provable exclusion evidence is kept, and the keep is reported."""
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "keep.md").write_text("# keep\n\nstill here\n", encoding="utf-8")
    (docs / "other.md").write_text("# other\n\nalive\n", encoding="utf-8")

    graph_path = _write_graph(tmp_path, ["docs/keep.md", "docs/other.md"])
    detection, seen = _scan(tmp_path)
    # Simulate a scan that lost docs/other.md for a reason that is NOT a
    # provable exclusion (e.g. a walk error): drop it from seen and from
    # the detection evidence.
    seen = {s for s in seen if not s.endswith("other.md")}
    detection = dict(detection, ignored=[], pruned_noise_dirs=[], skipped_sensitive=[])

    stale = _stale_graph_sources(graph_path, tmp_path, seen, detection=detection)
    assert stale == []
    err = capsys.readouterr().err
    assert "fail-closed" in err
