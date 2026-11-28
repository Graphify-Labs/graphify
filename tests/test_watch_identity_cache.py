"""`_StoredSourcePaths.identity` is asked for every node, edge and hyperedge's
file, several times per item, during an update's reconcile pass. A graph has
far fewer distinct source files than items (graphify's own repo: ~1k files,
~18.7k nodes, ~38k edges, ~150k identity calls), and the answer depends only on
the stored path and roots fixed in __init__. It is computed once per file.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import _norm_source_file
from graphify.watch import _StoredSourcePaths


def _paths(tmp_path: Path, normalize=_norm_source_file) -> _StoredSourcePaths:
    out = tmp_path / "graphify-out"
    out.mkdir()
    return _StoredSourcePaths(
        {"nodes": [], "links": []},
        out=out,
        project_root=tmp_path,
        watch_root=tmp_path,
        normalize_source=normalize,
    )


def test_identity_is_computed_once_per_source_file(tmp_path):
    calls: list[str | None] = []

    def counting_normalize(p, root=None):
        calls.append(p)
        return _norm_source_file(p, root)

    paths = _paths(tmp_path, counting_normalize)
    files = ["src/a.py", "src/b.py", "lib\\c.py"]
    for f in files:
        paths.identity(f)
        paths.in_watch_root(f)
    first_pass = len(calls)
    assert first_pass > 0
    for _ in range(50):
        for f in files:
            paths.identity(f)
            paths.in_watch_root(f)
    assert len(calls) == first_pass, f"{len(calls)} normalizations for {len(files)} files"


def test_cached_answers_match_a_fresh_computation(tmp_path):
    paths = _paths(tmp_path)
    outside = (tmp_path.parent / "elsewhere" / "x.py").as_posix()
    cases = ["src/a.py", "./src/../src/a.py", "lib\\c.py", outside, "", None]
    for f in cases:
        for _ in range(2):  # first call fills the cache, second reads it
            assert paths.identity(f) == paths._identity_uncached(f)
            identity = paths._identity_uncached(f)
            expected = bool(identity) and Path(identity).is_relative_to(paths.watch_root)
            assert paths.in_watch_root(f) is expected
    assert paths.in_watch_root("src/a.py") is True
    assert paths.in_watch_root(outside) is False


def test_rebase_and_absolute_identity_are_computed_once_per_source_file(tmp_path, monkeypatch):
    # rebase_preserved runs for every preserved node, edge and hyperedge, and
    # absolute_identity for every stored node and edge of an incremental update.
    import graphify.watch as watch

    calls: list[str | None] = []

    def counting_normalize(p, root=None):
        calls.append(p)
        return _norm_source_file(p, root)

    containment_checks: list[Path] = []
    real_is_relative_to = watch._is_relative_to

    def counting_is_relative_to(path, root):
        containment_checks.append(path)
        return real_is_relative_to(path, root)

    monkeypatch.setattr(watch, "_is_relative_to", counting_is_relative_to)
    paths = _paths(tmp_path, counting_normalize)
    outside = (tmp_path.parent / "elsewhere" / "x.py").as_posix()
    files = ["src/a.py", "lib\\c.py", outside]

    def one_pass():
        for f in files:
            paths.rebase_preserved({"source_file": f})
            paths.absolute_identity(f, tmp_path)

    one_pass()
    first_pass = (len(calls), len(containment_checks))
    assert first_pass[0] > 0 and first_pass[1] > 0
    for _ in range(50):
        one_pass()
    assert (len(calls), len(containment_checks)) == first_pass


def test_rebase_preserved_rewrites_each_case_as_before(tmp_path):
    project = tmp_path / "proj"
    other = tmp_path / "other"
    out = project / "graphify-out"
    out.mkdir(parents=True)
    other.mkdir()
    outside = (tmp_path / "elsewhere" / "x.py").as_posix()
    in_other = (other / "y.py").as_posix()
    for watch_root, cases in (
        (project, [
            ("src/a.py", "src/a.py"),
            ("./src/../src/a.py", "src/a.py"),
            ("lib\\c.py", "lib/c.py"),
            (outside, outside),
            ("", ""),
            (None, None),
        ]),
        # A watched root outside the project root keeps its absolute path.
        (other, [(in_other, in_other), ("src/a.py", "src/a.py")]),
    ):
        paths = _StoredSourcePaths(
            {"nodes": [], "links": []},
            out=out,
            project_root=project,
            watch_root=watch_root,
            normalize_source=_norm_source_file,
        )
        for _ in range(2):  # first call fills the cache, second reads it
            for stored, expected in cases:
                item = {"source_file": stored}
                paths.rebase_preserved(item)
                assert item["source_file"] == expected, (watch_root, stored)
                assert paths.absolute_identity(stored, project) == paths._absolute_identity_uncached(stored, project)
