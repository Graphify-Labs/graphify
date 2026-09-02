"""Helpers in graphify.parallel and end-to-end parallel vs sequential identity."""
from __future__ import annotations

from pathlib import Path

from graphify.parallel import (
    PARALLEL_THRESHOLD,
    chunk_size_for,
    chunked,
    map_in_process_pool,
    map_in_thread_pool,
    resolve_max_workers,
)


def _double(x: int) -> int:
    """Module-level so a spawn-start process pool can pickle it."""
    return x * 2


def _fingerprint(result: dict) -> tuple[tuple[str, ...], tuple[tuple[str, str, str, str], ...]]:
    nodes = tuple(sorted(str(n["id"]) for n in result["nodes"]))
    edges = tuple(sorted(
        (
            str(e["source"]),
            str(e["target"]),
            str(e["relation"]),
            str(e.get("context") or ""),
        )
        for e in result["edges"]
    ))
    return nodes, edges


def test_chunk_size_for_aims_for_four_chunks_per_worker():
    assert chunk_size_for(25, 2) == 4
    assert chunk_size_for(1, 8) == 1
    assert chunk_size_for(10_000, 8) == 32
    assert chunk_size_for(0, 4) == 1


def test_chunked_splits_and_keeps_a_short_tail():
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert chunked([], 4) == []


def test_resolve_max_workers_env_capped_by_item_count(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "8")
    assert resolve_max_workers(3, None) == 3
    assert resolve_max_workers(25, None) == 8


def test_resolve_max_workers_explicit_is_not_capped_by_item_count(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_MAX_WORKERS", raising=False)
    assert resolve_max_workers(1, 2) == 2


def test_map_in_process_pool_declines_small_jobs():
    assert map_in_process_pool(_double, list(range(5))) is None


def test_map_in_process_pool_declines_one_worker(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "1")
    assert map_in_process_pool(_double, list(range(PARALLEL_THRESHOLD + 5))) is None


def test_map_in_process_pool_preserves_order(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    items = list(range(PARALLEL_THRESHOLD + 5))
    got = map_in_process_pool(_double, items)
    assert got == [_double(x) for x in items]


def test_map_in_process_pool_bpp_returns_none(monkeypatch):
    from concurrent.futures.process import BrokenProcessPool
    import concurrent.futures

    class FakePool:
        def __init__(self, *a, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def submit(self, *a, **kw):
            raise BrokenProcessPool("simulated spawn failure")

    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", FakePool)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    assert map_in_process_pool(_double, list(range(25))) is None


def test_map_in_thread_pool_preserves_order(monkeypatch):
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    items = list(range(PARALLEL_THRESHOLD + 5))
    got = map_in_thread_pool(_double, items)
    assert got == [_double(x) for x in items]


def test_detect_parallel_word_count_matches_sequential(tmp_path, monkeypatch):
    from graphify import detect as det

    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    src = tmp_path / "src"
    src.mkdir()
    for i in range(25):
        (src / f"doc{i}.md").write_text(f"alpha beta gamma {i}\n" * 3)

    real = det.map_in_thread_pool
    used_pool = {"yes": False}

    def tracking(*args, **kwargs):
        result = real(*args, **kwargs)
        if result is not None:
            used_pool["yes"] = True
        return result

    monkeypatch.setattr(det, "map_in_thread_pool", lambda *a, **k: None)
    sequential = det.detect(src, cache_root=tmp_path / "c_seq")
    monkeypatch.setattr(det, "map_in_thread_pool", tracking)
    parallel = det.detect(src, cache_root=tmp_path / "c_par")

    assert used_pool["yes"], "25 files must take the thread-pool word-count path"
    assert sequential["total_words"] == parallel["total_words"]
    assert sequential["files"] == parallel["files"]
    assert sequential["total_files"] == 25


def test_detect_parallel_walk_matches_sequential(tmp_path, monkeypatch):
    """Sibling trees + nested gitignores must match a sequential walk."""
    from graphify import detect as det

    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "4")
    src = tmp_path / "src"
    src.mkdir()
    for i in range(25):
        d = src / f"pkg{i}"
        d.mkdir()
        (d / ".gitignore").write_text("*.log\n", encoding="utf-8")
        (d / f"mod{i}.py").write_text(f"x = {i}\n", encoding="utf-8")
        (d / f"noise{i}.log").write_text("nope\n", encoding="utf-8")

    real = det.map_in_thread_pool
    monkeypatch.setattr(det, "map_in_thread_pool", lambda *a, **k: None)
    sequential = det.detect(src, cache_root=tmp_path / "c_seq")
    monkeypatch.setattr(det, "map_in_thread_pool", real)
    parallel = det.detect(src, cache_root=tmp_path / "c_par")

    assert sequential["files"] == parallel["files"]
    assert sequential["ignored"] == parallel["ignored"]
    assert sequential["unclassified"] == parallel["unclassified"]
    assert sequential["total_words"] == parallel["total_words"]
    assert sequential["total_files"] == 25
    assert sequential["graphifyignore_patterns"] == parallel["graphifyignore_patterns"]


def test_extract_python_parallel_matches_sequential(tmp_path, monkeypatch):
    from graphify.extract import extract

    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    pkg = tmp_path / "pkg"
    pkg.mkdir()
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    paths = [pkg / "__init__.py"]
    for i in range(25):
        p = pkg / f"m{i}.py"
        if i == 0:
            p.write_text("def f0():\n    return 0\n", encoding="utf-8")
        else:
            p.write_text(
                f"from .m{i - 1} import f{i - 1}\n\n"
                f"def f{i}():\n    return f{i - 1}()\n",
                encoding="utf-8",
            )
        paths.append(p)

    sequential = extract(
        paths, cache_root=tmp_path / "seq", root=tmp_path, parallel=False,
    )
    parallel = extract(
        paths, cache_root=tmp_path / "par", root=tmp_path,
        parallel=True, max_workers=2,
    )
    assert _fingerprint(parallel) == _fingerprint(sequential)
    assert any(e["relation"] == "imports" for e in sequential["edges"])


def test_extract_js_parallel_matches_sequential(tmp_path, monkeypatch):
    from graphify.extract import extract

    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    paths: list[Path] = []
    for i in range(25):
        p = tmp_path / f"m{i}.js"
        if i == 0:
            p.write_text("export function f0() { return 0 }\n", encoding="utf-8")
        else:
            p.write_text(
                f"import {{ f{i - 1} }} from './m{i - 1}.js'\n"
                f"export function f{i}() {{ return f{i - 1}() }}\n",
                encoding="utf-8",
            )
        paths.append(p)

    sequential = extract(
        paths, cache_root=tmp_path / "seq", root=tmp_path, parallel=False,
    )
    parallel = extract(
        paths, cache_root=tmp_path / "par", root=tmp_path,
        parallel=True, max_workers=2,
    )
    assert _fingerprint(parallel) == _fingerprint(sequential)
    assert any(e["relation"] == "imports" for e in sequential["edges"])


def test_extract_warm_cache_skips_ast_pool(tmp_path, monkeypatch):
    from graphify import extract as extract_mod

    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "2")
    paths = []
    for i in range(25):
        p = tmp_path / f"m{i}.py"
        p.write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
        paths.append(p)

    extract_mod.extract(
        paths, cache_root=tmp_path / "c", root=tmp_path,
        parallel=True, max_workers=2,
    )

    spawned = {"n": 0}
    real = extract_mod._extract_parallel

    def wrapped(*args, **kwargs):
        spawned["n"] += 1
        return real(*args, **kwargs)

    monkeypatch.setattr(extract_mod, "_extract_parallel", wrapped)
    extract_mod.extract(
        paths, cache_root=tmp_path / "c", root=tmp_path,
        parallel=True, max_workers=2,
    )
    assert spawned["n"] == 0, "a warm AST cache must not re-enter the process pool"
