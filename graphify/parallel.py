"""Process/thread-pool helpers for extraction and corpus scans.

Worker counts honour ``GRAPHIFY_MAX_WORKERS`` the same way AST extraction does,
and Windows is clamped at 61 (CPython ``WaitForMultipleObjects`` limit). Callers
that cannot spawn a pool (one worker, small batches, ``BrokenProcessPool``)
fall back to in-process sequential work.
"""
from __future__ import annotations

import os
import sys
from collections.abc import Callable, Sequence
from typing import TypeVar

T = TypeVar("T")
R = TypeVar("R")

# Same gate as extract._PARALLEL_THRESHOLD: below this a process pool's spawn
# cost dominates, and tests that mock ProcessPoolExecutor still exercise the
# sequential path on small fixtures.
PARALLEL_THRESHOLD = 20


def resolve_max_workers(n_items: int, max_workers: int | None = None) -> int:
    """Return a positive worker count for ``n_items`` pieces of work.

    ``max_workers`` (CLI ``--max-workers``) wins when given and is not
    silently shrunk to ``n_items`` (extract() tests and the 1-file spawn
    path pass an explicit count that must reach the pool). Otherwise
    ``GRAPHIFY_MAX_WORKERS``, otherwise ``os.cpu_count()``, capped by
    ``n_items`` so a 3-file job never starts 32 idle workers.
    """
    if max_workers is not None:
        # Caller-supplied count (CLI ``--max-workers``) is not silently shrunk
        # to ``n_items``: extract() tests and the Windows 1-file spawn path
        # pass an explicit value that must reach the pool.
        workers = max(int(max_workers), 1)
    else:
        env_raw = os.environ.get("GRAPHIFY_MAX_WORKERS", "").strip()
        env_cap = None
        if env_raw:
            try:
                v = int(env_raw)
                if v > 0:
                    env_cap = v
            except ValueError:
                pass
        workers = env_cap if env_cap is not None else (os.cpu_count() or 4)
        workers = min(max(int(workers), 1), n_items if n_items else 1)
    if sys.platform == "win32":
        workers = min(workers, 61)
    return max(workers, 1)


def chunk_size_for(n_items: int, max_workers: int) -> int:
    """Files (or items) per submitted task.

    Aims for about four chunks per worker so a slow file does not stall a
    worker that already drained a giant one-shot batch, without submitting
    one Future per file on a 50k-file corpus.
    """
    if n_items <= 0 or max_workers <= 0:
        return 1
    per_worker = max_workers * 4
    return max(1, min(32, (n_items + per_worker - 1) // per_worker))


def chunked(items: Sequence[T], size: int) -> list[list[T]]:
    size = max(int(size), 1)
    return [list(items[i:i + size]) for i in range(0, len(items), size)]


def _run_batch(fn: Callable[[T], R], batch: list[T]) -> list[R]:
    """Module-level so ProcessPoolExecutor can pickle it (Windows spawn)."""
    return [fn(item) for item in batch]


def map_in_process_pool(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    max_workers: int | None = None,
    threshold: int = PARALLEL_THRESHOLD,
) -> list[R] | None:
    """Map ``fn`` over ``items`` in a process pool, preserving order.

    Returns ``None`` when the caller should run sequentially instead: fewer
    than ``threshold`` items, a resolved worker count of 1, or a
    ``BrokenProcessPool`` (Windows spawn without an ``if __name__`` guard).
    A non-BPP failure in one batch is retried in-process for that batch only.
    """
    n = len(items)
    if n == 0:
        return []
    if n < threshold:
        return None
    workers = resolve_max_workers(n, max_workers)
    if workers == 1:
        return None

    import concurrent.futures

    batches = chunked(items, chunk_size_for(n, workers))
    results: list[R | None] = [None] * n
    try:
        with concurrent.futures.ProcessPoolExecutor(max_workers=workers) as pool:
            futures: dict = {}
            offset = 0
            for batch in batches:
                fut = pool.submit(_run_batch, fn, batch)
                futures[fut] = (offset, batch)
                offset += len(batch)
            for fut in concurrent.futures.as_completed(futures):
                offset, batch = futures[fut]
                try:
                    part = fut.result()
                except concurrent.futures.process.BrokenProcessPool:
                    raise
                except Exception:
                    part = _run_batch(fn, list(batch))
                results[offset:offset + len(part)] = part
    except concurrent.futures.process.BrokenProcessPool:
        return None
    return results  # type: ignore[return-value]


def map_in_thread_pool(
    fn: Callable[[T], R],
    items: Sequence[T],
    *,
    max_workers: int | None = None,
    threshold: int = PARALLEL_THRESHOLD,
) -> list[R] | None:
    """Map ``fn`` over ``items`` in a thread pool, preserving order.

    Same ``None``-means-run-sequentially contract as :func:`map_in_process_pool`.
    Nested functions are fine here (threads, not pickling).
    """
    n = len(items)
    if n == 0:
        return []
    if n < threshold:
        return None
    workers = resolve_max_workers(n, max_workers)
    if workers == 1:
        return None

    from concurrent.futures import ThreadPoolExecutor

    cs = chunk_size_for(n, workers)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(fn, items, chunksize=cs))
