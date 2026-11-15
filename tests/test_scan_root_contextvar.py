"""The ambient scan root save/restore pair must be thread-isolated.

Regression test for #4602: `_ACTIVE_SCAN_ROOT` was a module global, so
overlapping extractions on different threads interleaved their
save/restore pairs — the second call saved the first one's root and
restored it last, leaving the ambient root set after `extract()`
returned. Nine tests downstream failed in any non-default order.

A module global cannot be made race-free without a lock around every
read; a `contextvars.ContextVar` gives each thread its own value and
makes the pairs nest correctly by construction.
"""
from __future__ import annotations

import threading

from graphify.extractors import base as base_mod


def test_concurrent_save_restore_pairs_do_not_leak():
    """Two threads doing overlapping set/restore cycles must each see their
    own root at the peak and return to the outer value (None) after
    restore. The old module global failed both assertions: the peak read
    was contaminated by the other thread's root, and the loser of the
    save/restore race leaked the winner's root past extract()."""
    barrier = threading.Barrier(2)
    seen = {}

    def worker(name: str, root_value: str) -> None:
        previous = base_mod.set_active_scan_root(root_value)
        barrier.wait()  # both roots are set at this point — the race window
        seen[name] = (base_mod.active_scan_root(), previous)
        base_mod.set_active_scan_root(previous)
        barrier.wait()  # both restores have run
        seen[name + ":after"] = base_mod.active_scan_root()

    t1 = threading.Thread(target=worker, args=("A", "/root-a"))
    t2 = threading.Thread(target=worker, args=("B", "/root-b"))
    t1.start()
    t2.start()
    t1.join()
    t2.join()

    # Each thread sees ITS OWN root at the peak (a shared global would
    # show the last setter's value in both).
    assert seen["A"] == ("/root-a", None)
    assert seen["B"] == ("/root-b", None)
    # And after restore, each thread is back to the outer value — no
    # leakage in either direction, whatever the interleaving.
    assert seen["A:after"] is None
    assert seen["B:after"] is None

def test_concurrent_workers_see_their_own_root():
    """Two threads setting different roots concurrently must each read
    their own root back — the ContextVar isolates them."""
    import concurrent.futures

    observed = {}

    def worker(name: str, root_value: str) -> None:
        base_mod.set_active_scan_root(root_value)
        observed[name] = base_mod.active_scan_root()

    base_mod.set_active_scan_root(None)
    threads = [
        threading.Thread(target=worker, args=(name, value))
        for name, value in [("t1", "/one"), ("t2", "/two")]
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert observed["t1"] == "/one"
    assert observed["t2"] == "/two"
