"""_relativize_source_files_in memoizes per distinct source path (#perf).

Every node in a file's cache payload — and most of its edges/raw_calls — carries
the same one or two source-path strings, yet each item triggered an
os.path.abspath, an on-disk exists() stat, and an os.path.relpath. The result
is a pure function of (source string, root), so it is now computed once per
distinct string: same output, a fraction of the path work and stats.
"""

import os
from pathlib import Path

from graphify.cache import (
    _absolutize_source_files_in,
    _relativize_source_files_in,
)


def _reference(payload, root):
    """The pre-memo implementation, verbatim, as an equivalence oracle."""
    root_resolved = Path(root).resolve()
    for bucket in ("nodes", "edges", "hyperedges", "raw_calls"):
        for item in payload.get(bucket, []):
            if not isinstance(item, dict):
                continue
            for key in ("source_file", "definition_file"):
                source = item.get(key)
                if not source:
                    continue
                sp = Path(source)
                if not sp.is_absolute():
                    cwd_form = Path(os.path.abspath(sp))
                    try:
                        if cwd_form == root_resolved / sp or not cwd_form.exists():
                            continue
                    except OSError:
                        continue
                    sp = cwd_form
                try:
                    rel = os.path.relpath(sp, root_resolved)
                except (ValueError, OSError):
                    continue
                if rel == ".." or rel.startswith(".." + os.sep) or rel.startswith("../"):
                    continue
                item[key] = rel.replace(os.sep, "/")


def _corpus(root):
    (root / "src").mkdir(parents=True, exist_ok=True)
    (root / "src" / "m.py").write_text("x=1\n", encoding="utf-8")
    (root / "a.py").write_text("y=1\n", encoding="utf-8")
    outside = str(root.parent / "other.py")
    return {
        "nodes": [
            {"id": "1", "source_file": str(root / "src" / "m.py"),
             "definition_file": str(root / "a.py")},
            {"id": "2", "source_file": "src/m.py"},          # already relative
            {"id": "3", "source_file": outside},             # out-of-root
            {"id": "4", "source_file": str(root / "ghost.py")},  # missing (abs)
            {"id": "5"},                                     # no source_file
            {"id": "6", "source_file": str(root / "src" / "m.py")},  # dup
        ],
        "edges": [{"source": "1", "target": "2",
                   "source_file": str(root / "a.py")}],
        "hyperedges": [],
        "raw_calls": [{"caller_nid": "1",
                       "source_file": str(root / "src" / "m.py")}],
    }


def test_output_matches_the_unmemoized_reference(tmp_path):
    root = tmp_path.resolve()
    got = _corpus(root)
    _relativize_source_files_in(got, root)
    expected = _corpus(root)
    _reference(expected, root)
    assert got == expected


def test_stats_each_distinct_path_once(tmp_path, monkeypatch):
    """A file's hundreds of same-source nodes must not each stat the disk."""
    root = tmp_path.resolve()
    (root / "src").mkdir(parents=True)
    (root / "src" / "m.py").write_text("x=1\n", encoding="utf-8")
    # 500 nodes, all the SAME relative source string (the only path needing a
    # stat — an absolute in-root path skips the exists() check).
    payload = {"nodes": [{"id": str(i), "source_file": "src/m.py"}
                         for i in range(500)],
               "edges": [], "hyperedges": [], "raw_calls": []}

    calls = {"n": 0}
    real_exists = Path.exists

    def counting_exists(self):
        calls["n"] += 1
        return real_exists(self)

    monkeypatch.setattr(Path, "exists", counting_exists)
    _relativize_source_files_in(payload, root)
    # One distinct source string -> at most one exists() probe, not 500.
    assert calls["n"] <= 1, calls["n"]
    # And every node was still rewritten identically.
    assert all(n["source_file"] == "src/m.py" for n in payload["nodes"])


def test_duplicate_source_strings_all_rewritten(tmp_path):
    root = tmp_path.resolve()
    (root / "m.py").write_text("x=1\n", encoding="utf-8")
    abs_sf = str(root / "m.py")
    payload = {"nodes": [{"id": str(i), "source_file": abs_sf} for i in range(10)],
               "edges": [], "hyperedges": [], "raw_calls": []}
    _relativize_source_files_in(payload, root)
    assert all(n["source_file"] == "m.py" for n in payload["nodes"])


def test_absolutize_round_trips_relativize(tmp_path):
    """relativize then absolutize recovers the original absolute source_file,
    across many items sharing one string (the warm-load / update path)."""
    root = tmp_path.resolve()
    (root / "src").mkdir(parents=True)
    (root / "src" / "m.py").write_text("x=1\n", encoding="utf-8")
    orig = str(root / "src" / "m.py")
    payload = {"nodes": [{"id": str(i), "source_file": orig} for i in range(50)],
               "edges": [], "hyperedges": [], "raw_calls": []}
    _relativize_source_files_in(payload, root)
    assert all(n["source_file"] == "src/m.py" for n in payload["nodes"])
    _absolutize_source_files_in(payload, root)
    assert all(n["source_file"] == orig for n in payload["nodes"])


def test_absolutize_leaves_legacy_absolute_entries(tmp_path):
    """A legacy cache entry storing an absolute source_file is left unchanged."""
    root = tmp_path.resolve()
    abs_sf = str(root / "already" / "abs.py")
    payload = {"nodes": [{"id": "1", "source_file": abs_sf}],
               "edges": [], "hyperedges": [], "raw_calls": []}
    _absolutize_source_files_in(payload, root)
    assert payload["nodes"][0]["source_file"] == abs_sf
