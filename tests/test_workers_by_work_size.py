"""The extraction pool sizes itself by the amount of uncached work.

With no --max-workers / GRAPHIFY_MAX_WORKERS, v8 started min(cpu_count, files)
workers, so a small repo on a 12-core laptop started 12 processes that each
loaded graphify and the grammars (click: 701 MB peak vs 183 MB in one
process, at the same speed). Now one worker is started per
_BYTES_PER_WORKER of uncached source, capped at the CPU count, so a big job
still gets every core (#792). An explicit number still wins.
"""

import concurrent.futures

import pytest

import graphify.extract as extract_mod
from graphify.extract import _BYTES_PER_WORKER, _default_max_workers


def _work(tmp_path, sizes):
    work = []
    for i, size in enumerate(sizes):
        f = tmp_path / f"f{i}.py"
        f.write_bytes(b"#" * size)
        work.append((i, f))
    return work


@pytest.fixture
def twelve_cores(monkeypatch):
    monkeypatch.delenv("GRAPHIFY_MAX_WORKERS", raising=False)
    monkeypatch.setattr(extract_mod.os, "cpu_count", lambda: 12)


def test_small_job_gets_one_worker(tmp_path, twelve_cores):
    # 40 files, well under one worker's share in total.
    work = _work(tmp_path, [_BYTES_PER_WORKER // 100] * 40)
    assert _default_max_workers(work) == 1


def test_workers_grow_with_bytes(tmp_path, twelve_cores):
    work = _work(tmp_path, [_BYTES_PER_WORKER // 4] * 12)  # 3 shares
    assert _default_max_workers(work) == 3


def test_big_job_gets_every_core(tmp_path, twelve_cores):
    work = _work(tmp_path, [_BYTES_PER_WORKER] * 30)
    assert _default_max_workers(work) == 12


def test_never_more_workers_than_files(tmp_path, twelve_cores):
    work = _work(tmp_path, [_BYTES_PER_WORKER * 5] * 2)
    assert _default_max_workers(work) == 2


def test_unreadable_file_counts_as_empty(tmp_path, twelve_cores):
    work = _work(tmp_path, [10] * 3) + [(3, tmp_path / "gone.py")]
    assert _default_max_workers(work) == 1


@pytest.mark.parametrize("env, expected", [("3", 3), ("12", 12), ("100", 40)])
def test_env_override_wins(tmp_path, monkeypatch, env, expected):
    monkeypatch.setattr(extract_mod.os, "cpu_count", lambda: 4)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", env)
    work = _work(tmp_path, [10] * 40)  # tiny job: the size rule alone says 1
    assert _default_max_workers(work) == expected


@pytest.mark.parametrize("env", ["0", "-2", "lots", ""])
def test_invalid_env_falls_back_to_size(tmp_path, monkeypatch, env):
    monkeypatch.setattr(extract_mod.os, "cpu_count", lambda: 12)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", env)
    assert _default_max_workers(_work(tmp_path, [10] * 40)) == 1


class _SpyPool:
    """Records the pool size and refuses to start, so extract() falls back."""

    sizes: list = []

    def __init__(self, *args, max_workers=None, **kwargs):
        _SpyPool.sizes.append(max_workers)
        raise OSError("spy: no pool in this test")


def _corpus(tmp_path, n=30):
    paths = []
    for i in range(n):
        f = tmp_path / f"m{i}.py"
        f.write_text(f"def f{i}():\n    return {i}\n", encoding="utf-8")
        paths.append(f)
    return paths


def _run_extract(tmp_path, monkeypatch, **kwargs):
    _SpyPool.sizes = []
    monkeypatch.setattr(concurrent.futures, "ProcessPoolExecutor", _SpyPool)
    result = extract_mod.extract(
        _corpus(tmp_path), cache_root=tmp_path / "out", root=tmp_path, **kwargs
    )
    assert len(result["nodes"]) >= 30
    return _SpyPool.sizes


def test_extract_starts_no_pool_for_a_small_repo(tmp_path, monkeypatch, twelve_cores):
    # 30 tiny files on a 12-core box: v8 started a 12-process pool here.
    assert _run_extract(tmp_path, monkeypatch) == []


def test_extract_honours_max_workers_argument(tmp_path, monkeypatch, twelve_cores):
    assert _run_extract(tmp_path, monkeypatch, max_workers=5) == [5]


def test_extract_honours_env(tmp_path, monkeypatch):
    monkeypatch.setattr(extract_mod.os, "cpu_count", lambda: 12)
    monkeypatch.setenv("GRAPHIFY_MAX_WORKERS", "6")
    assert _run_extract(tmp_path, monkeypatch) == [6]
