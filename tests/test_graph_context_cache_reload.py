"""`_GraphContextCache.load` under concurrent access (#5177).

The whole rebuild used to run inside the cache's single lock, so a slow
reload of one graph stalled every request on the server, including requests
for a different graph and requests that could have been answered from the
graph already in memory. The rebuild now runs outside the lock, is
single-flighted per path, and a caller that already has a (stale) entry gets
it back immediately instead of queuing behind someone else's reload.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from graphify.serve import _GraphContextCache

GRAPH = {
    "directed": True,
    "nodes": [{"id": "a", "label": "A", "community": 0}, {"id": "b", "label": "B", "community": 0}],
    "edges": [{"source": "a", "target": "b", "relation": "calls", "confidence": "EXTRACTED"}],
}


def _write_graph(path: Path) -> None:
    path.write_text(json.dumps(GRAPH))


def _gate(cache: _GraphContextCache, delay: float, slow_for=None):
    """Make `cache._load_entry` sleep `delay`s, counting every call.

    `slow_for` restricts the delay to paths whose resolved string contains it;
    every other path still uses the real (fast) loader.
    """
    original = cache._load_entry
    calls: list[tuple[str, tuple[int, int]]] = []

    def gated(resolved_path, key):
        calls.append((resolved_path, key))
        if slow_for is None or slow_for in resolved_path:
            time.sleep(delay)
        return original(resolved_path, key)

    cache._load_entry = gated
    return calls


def test_stale_entry_served_while_a_reload_is_in_flight(tmp_path):
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path)
    path = str(graph_path)

    cache = _GraphContextCache(8)
    cache.load(path)  # warm, unpatched

    calls = _gate(cache, delay=0.3)
    os.utime(path, (time.time() + 10, time.time() + 10))  # make the warm entry stale

    results: dict[int, float] = {}

    def caller(i):
        t0 = time.time()
        cache.load(path)
        results[i] = time.time() - t0

    threads = [threading.Thread(target=caller, args=(i,)) for i in range(3)]
    for t in threads:
        t.start()
        time.sleep(0.05)
    for t in threads:
        t.join()

    # Exactly one caller pays the rebuild cost; the others, which still had
    # the old entry, return almost immediately with it rather than blocking.
    slow = [dt for dt in results.values() if dt > 0.2]
    fast = [dt for dt in results.values() if dt <= 0.2]
    assert len(slow) == 1, results
    assert len(fast) == 2, results
    assert len(calls) == 1, "a second, redundant reload was started while one was already in flight"


def test_concurrent_first_load_of_new_path_builds_once(tmp_path):
    """Control: with no stale entry to fall back to, concurrent first-time
    loads of the same brand-new path must still single-flight to one build,
    not each start (and redundantly pay for) their own."""
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path)
    path = str(graph_path)

    cache = _GraphContextCache(8)
    calls = _gate(cache, delay=0.3)

    results: dict[int, float] = {}

    def caller(i):
        t0 = time.time()
        cache.load(path)
        results[i] = time.time() - t0

    threads = [threading.Thread(target=caller, args=(i,)) for i in range(4)]
    for t in threads:
        t.start()
        time.sleep(0.02)
    for t in threads:
        t.join()

    assert len(calls) == 1, "every concurrent first-time caller triggered its own rebuild"
    assert all(dt > 0.2 for dt in results.values()), results


def test_reload_of_one_path_does_not_block_another_path(tmp_path):
    p1 = tmp_path / "p1" / "graph.json"
    p2 = tmp_path / "p2" / "graph.json"
    p1.parent.mkdir()
    p2.parent.mkdir()
    _write_graph(p1)
    _write_graph(p2)

    cache = _GraphContextCache(8)
    _gate(cache, delay=0.5, slow_for="p1")

    results: dict[str, float] = {}

    def load_p1():
        t0 = time.time()
        cache.load(str(p1))
        results["p1"] = time.time() - t0

    def load_p2():
        time.sleep(0.05)
        t0 = time.time()
        cache.load(str(p2))
        results["p2"] = time.time() - t0

    t1 = threading.Thread(target=load_p1)
    t2 = threading.Thread(target=load_p2)
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    assert results["p1"] > 0.4, results
    assert results["p2"] < 0.2, "an unrelated path's load was blocked by another path's slow rebuild"


def test_reload_eventually_serves_the_new_graph(tmp_path):
    """Sanity: once an in-flight rebuild finishes, a later call sees the new
    data, not the stale one forever."""
    graph_path = tmp_path / "graph.json"
    _write_graph(graph_path)
    path = str(graph_path)

    cache = _GraphContextCache(8)
    G, _ = cache.load(path)
    assert G.number_of_nodes() == 2

    bigger = {
        "directed": True,
        "nodes": [{"id": n, "label": n, "community": 0} for n in "abc"],
        "edges": [],
    }
    graph_path.write_text(json.dumps(bigger))
    os.utime(path, (time.time() + 10, time.time() + 10))

    G2, _ = cache.load(path)
    assert G2.number_of_nodes() == 3
