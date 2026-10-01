"""Contract tests for the graph-only ``_GraphContextCache`` in ``graphify.serve``.

These exercise the cache's file-identity revalidation contract entirely in
process against a temporary directory of tiny node-link graphs: cold misses,
warm hits, atomic equal-length/restored-mtime replacements, churn bounds, LRU
eviction, pinned isolation and the parse/absence error mappings. No HTTP, MCP
or network path is touched, so the module needs no optional extras.
"""

import collections
import json
import os
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from graphify import serve as mod

# Genuine loader captured before any patch, used as the independent oracle.
REAL_LOAD = mod._load_graph


def _graph_json(seed_id: str = "eeee", seed_kind: str = "seed") -> str:
    """A tiny node_link graph. ``seed_id``/``seed_kind`` are 4-char tokens so all
    variants serialize to an identical byte length (enables equal-length swaps)."""
    data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": seed_id, "community": 0, "kind": seed_kind},
            {"id": "aaaa", "community": 1, "kind": "peer"},
        ],
        "links": [{"source": seed_id, "target": "aaaa"}],
    }
    return json.dumps(data)


def _graph_json_bigger(seed_id: str = "eeee") -> str:
    """A valid but DIFFERENT-BYTE-SIZE graph (extra node/edge). Used for the
    size-only positive control that is visible even to a (mtime_ns, size) key."""
    data = {
        "directed": False,
        "multigraph": False,
        "graph": {},
        "nodes": [
            {"id": seed_id, "community": 0, "kind": "seed"},
            {"id": "aaaa", "community": 1, "kind": "peer"},
            {"id": "bbbb", "community": 2, "kind": "peer"},
        ],
        "links": [
            {"source": seed_id, "target": "aaaa"},
            {"source": "aaaa", "target": "bbbb"},
        ],
    }
    return json.dumps(data)


def atomic_swap(path: Path, new_text: str, *, restore_mtime: bool):
    """``os.replace`` the file with EQUAL byte length; optionally restore the
    exact mtime. Returns the pre-swap stat.

    Contract asserted here (F8): a same-directory replace normally KEEPS
    ``st_dev`` and does not force every timestamp to change. What we can and do
    prove is (a) equal size, (b) exact restored mtime when requested, and (c) an
    OBSERVED IDENTITY change (``st_ino``) from the fresh temp inode. That is the
    property the candidate's five-field key must react to and the baseline
    (mtime_ns, size) key cannot see.
    """
    old = path.stat()
    encoded = new_text.encode("utf-8")
    assert len(encoded) == old.st_size, "swap must preserve byte length"
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".json")
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(encoded)
        os.replace(tmp, path)
    except BaseException:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    if restore_mtime:
        os.utime(path, ns=(old.st_atime_ns, old.st_mtime_ns))
    new = path.stat()
    assert new.st_size == old.st_size, "size preserved across swap"
    if restore_mtime:
        assert new.st_mtime_ns == old.st_mtime_ns, "mtime exactly restored"
    assert new.st_ino != old.st_ino, "observed identity (st_ino) change"
    return old


def _bump_mtime(path: Path):
    """Advance mtime deterministically (no sleep) so a legitimate change is
    visible even to the baseline (mtime_ns, size) key."""
    st = path.stat()
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns + 1_000_000_000))


class GraphCacheContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dir = Path(self._tmp.name)
        self.cache_cls = mod._GraphContextCache

    def write(self, name: str, text: str) -> str:
        p = self.dir / name
        p.write_text(text, encoding="utf-8")
        return str(p)

    @staticmethod
    def _snapshot_cache(cache):
        """Capture entry/key/nested references before a failing load, not after."""
        snapshots = []
        for name in ("_entries", "_pinned"):
            mapping = getattr(cache, name)
            rows = []
            for path, entry in mapping.items():
                graph = entry["G"]
                rows.append((path, entry, entry["key"], graph,
                             entry["communities"], graph.graph["_trigram_index"],
                             graph.graph["_learning_overlay"]))
            snapshots.append((name, mapping, rows))
        return snapshots

    def _assert_cache_unchanged(self, cache, snapshots):
        for name, original_mapping, rows in snapshots:
            mapping = getattr(cache, name)
            self.assertIs(mapping, original_mapping)
            self.assertEqual(list(mapping), [row[0] for row in rows])
            for path, original_entry, key, graph, communities, index, overlay in rows:
                entry = mapping[path]
                self.assertIs(entry, original_entry)
                self.assertEqual(entry["key"], key)
                self.assertIs(entry["G"], graph)
                self.assertIs(entry["communities"], communities)
                self.assertIs(graph.graph["_trigram_index"], index)
                self.assertIs(graph.graph["_learning_overlay"], overlay)

    # ---- RED on baseline -------------------------------------------------

    def test_t1_during_load_race_returns_current_not_stale(self):
        """Cold miss: the file mutates *after* the read but *before* publish.
        Baseline retains and returns the pre-swap graph; the candidate must
        revalidate, discard it, load a second time and return current content."""
        A = self.write("graph.json", _graph_json("eeee"))
        Apath = Path(A)
        cache = self.cache_cls(4)
        calls = {"n": 0}

        def wrap(p):
            calls["n"] += 1
            assert calls["n"] <= 2, "at most two successful load attempts"
            g = REAL_LOAD(p)
            if calls["n"] == 1:
                # equal length + restored mtime -> invisible to a (mtime,size) key
                atomic_swap(Apath, _graph_json("ffff"), restore_mtime=True)
            return g

        with patch.object(mod, "_load_graph", wrap):
            g, comm = cache.load(A)

        current = set(REAL_LOAD(A).nodes())
        self.assertEqual(current, {"ffff", "aaaa"})
        self.assertEqual(set(g.nodes()), current)  # RED baseline: returns {eeee,aaaa}
        self.assertEqual({v for ids in comm.values() for v in ids}, current)
        self.assertEqual(calls["n"], 2)  # F1: exactly two constructions (revalidate once)

    def test_t2_churn_raises_runtime_error_bounded(self):
        """Cold miss whose identity mutates after *every* successful read: never
        stabilises. Candidate performs exactly two loads then raises the exact
        churn RuntimeError, leaving a full unrelated LRU AND the pinned map
        untouched. The third-call guard raises AssertionError (NOT RuntimeError)
        so an unbounded-retry mutant is not swallowed as the churn error."""
        P = self.write("p.json", _graph_json("pppp"))
        A = self.write("a.json", _graph_json("eeee"))
        B = self.write("b.json", _graph_json("bbbb"))
        C = self.write("c.json", _graph_json("cccc"))
        Cpath = Path(C)
        cache = self.cache_cls(2)
        gP0, cP0 = cache.load(P, pinned=True)
        gA, cA = cache.load(A)
        gB, cB = cache.load(B)  # LRU now full: [A, B]

        # Snapshot references BEFORE the churn (F2/F3): entry objects, keys,
        # graphs, communities and nested peer maps -- not aliases of a later read.
        order_before = list(cache._entries)
        pin_before = list(cache._pinned)
        entryA = cache._entries[A]
        entryB = cache._entries[B]
        keyA, keyB = entryA["key"], entryB["key"]
        idxA0, ovA0 = gA.graph["_trigram_index"], gA.graph["_learning_overlay"]
        idxB0, ovB0 = gB.graph["_trigram_index"], gB.graph["_learning_overlay"]
        idxP0, ovP0 = gP0.graph["_trigram_index"], gP0.graph["_learning_overlay"]
        calls = {"n": 0}

        def churn(p):
            calls["n"] += 1
            assert calls["n"] <= 2, "unbounded retry: third load attempt"
            g = REAL_LOAD(p)
            atomic_swap(Cpath, _graph_json("cccc"), restore_mtime=True)  # churn ino/ctime
            return g

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", churn):
            with self.assertRaises(RuntimeError) as ctx:
                cache.load(C)

        # F1: exact type and message, not a subclass / unanchored regex.
        self.assertIs(type(ctx.exception), RuntimeError)
        self.assertEqual(str(ctx.exception), "graph.json changed while loading")
        self.assertEqual(calls["n"], 2)  # exactly two loads

        # No early insertion / eviction / promotion on the failed cold miss.
        self.assertNotIn(C, cache._entries)
        self.assertEqual(list(cache._entries), order_before)  # membership + order
        self.assertIs(cache._entries[A], entryA)
        self.assertIs(cache._entries[B], entryB)
        self.assertIs(entryA["G"], gA)
        self.assertIs(entryB["G"], gB)
        self.assertIs(entryA["communities"], cA)
        self.assertIs(entryB["communities"], cB)
        self.assertEqual(entryA["key"], keyA)
        self.assertEqual(entryB["key"], keyB)
        self.assertIs(gA.graph["_trigram_index"], idxA0)
        self.assertIs(gA.graph["_learning_overlay"], ovA0)
        self.assertIs(gB.graph["_trigram_index"], idxB0)
        self.assertIs(gB.graph["_learning_overlay"], ovB0)
        # Pinned map fully undisturbed by an unrelated cold-miss churn.
        self.assertEqual(list(cache._pinned), pin_before)
        self.assertIs(cache._pinned[P]["G"], gP0)
        self.assertIs(cache._pinned[P]["communities"], cP0)
        self.assertIs(gP0.graph["_trigram_index"], idxP0)
        self.assertIs(gP0.graph["_learning_overlay"], ovP0)
        self._assert_cache_unchanged(cache, before_failure)

    def test_t3_replace_after_matching_poststat_refreshes_next_call(self):
        """T3 (frozen V2 row omitted from the compressed authoring request).

        Event ordering (deterministic, no sleeps):
          1. cache.load(A) begins -> cache PRE-stat of A (real, original file).
          2. loader runs REAL_LOAD -> first successful construction completes
             (state['constructed'] = True).
          3. cache POST-stat of A: this is the first cache stat AFTER a completed
             construction. We CAPTURE the real pre-replacement stat, atomically
             replace A with equal-size/different-content/restored-mtime, then
             RETURN THE CAPTURED pre-replacement stat.
          4. Because the returned post-stat MATCHES the pre-stat, the load does
             NOT see a change and publishes the OLD graph (allowed to be stale).
          5. The injection is asserted to have fired before load() returns.
          6. cache.load(A) again: pre-stat now returns the REAL new-file stat;
             the key differs from the stored one, forcing a refresh that loads
             the CURRENT graph. Total loader constructions == 2.

        This exercises replacement AFTER a matching post-stat observation (not
        before it). The interceptor guards against re-entry so atomic_swap's own
        internal stats do not recurse into the injection branch.
        """
        A = self.write("g.json", _graph_json("eeee"))
        Apath = Path(A)
        cache = self.cache_cls(4)

        orig_stat = mod.Path.stat
        state = {"constructed": False, "injected": False, "loads": 0}

        def wrapped_load(p):
            state["loads"] += 1
            g = REAL_LOAD(p)
            state["constructed"] = True  # first successful construction complete
            return g

        def scripted_stat(self, *, follow_symlinks=True):
            real = orig_stat(self, follow_symlinks=follow_symlinks)
            try:
                is_target = os.path.samefile(str(self), A)  # os.stat, not this patch
            except OSError:
                is_target = False
            if is_target and state["constructed"] and not state["injected"]:
                state["injected"] = True  # set FIRST -> atomic_swap's stats delegate
                captured = real  # pre-replacement stat
                atomic_swap(Apath, _graph_json("ffff"), restore_mtime=True)
                return captured
            return real

        with patch.object(mod, "_load_graph", wrapped_load):
            with patch.object(mod.Path, "stat", scripted_stat):
                g_first, _ = cache.load(A)
                self.assertTrue(state["injected"], "replacement fired before load returned")
                g_next, _ = cache.load(A)

        current = set(REAL_LOAD(A).nodes())
        self.assertEqual(current, {"ffff", "aaaa"})
        # The first returned graph MAY be old (post-stat matched); the next call
        # must observe the real new stat and return the current graph.
        self.assertEqual(set(g_next.nodes()), current)  # RED baseline: stale {eeee,aaaa}
        self.assertEqual(state["loads"], 2)             # exactly two constructions

    def test_warm_replace_equal_len_restored_mtime_node_set(self):
        """Warm entry, then atomic replace with a different node set at equal
        byte length and restored mtime. The baseline key cannot see it and
        serves a stale hit; the candidate's identity-aware key detects it."""
        A = self.write("g.json", _graph_json("eeee"))
        Apath = Path(A)
        cache = self.cache_cls(4)
        g0, _ = cache.load(A)
        self.assertEqual(set(g0.nodes()), {"eeee", "aaaa"})

        old = atomic_swap(Apath, _graph_json("ffff"), restore_mtime=True)
        new = Apath.stat()
        self.assertEqual(new.st_mtime_ns, old.st_mtime_ns)  # restored
        self.assertEqual(new.st_size, old.st_size)          # equal length
        self.assertNotEqual(new.st_ino, old.st_ino)         # real identity differs
        self.assertEqual(new.st_dev, old.st_dev)            # same dir -> st_dev unchanged

        g1, _ = cache.load(A)
        current = set(REAL_LOAD(A).nodes())
        self.assertEqual(current, {"ffff", "aaaa"})
        self.assertEqual(set(g1.nodes()), current)  # RED baseline: stale {eeee,aaaa}

    def test_warm_replace_attr_change_same_node_set(self):
        """Same node set, one attribute flipped at equal byte length / restored
        mtime. Kills the reverse-key mutant via the same direct-load oracle."""
        A = self.write("g.json", _graph_json("eeee", "seed"))
        Apath = Path(A)
        cache = self.cache_cls(4)
        g0, _ = cache.load(A)
        self.assertEqual(g0.nodes["eeee"]["kind"], "seed")

        old = atomic_swap(Apath, _graph_json("eeee", "leaf"), restore_mtime=True)
        self.assertNotEqual(Apath.stat().st_ino, old.st_ino)

        g1, _ = cache.load(A)
        self.assertEqual(REAL_LOAD(A).nodes["eeee"]["kind"], "leaf")
        self.assertEqual(g1.nodes["eeee"]["kind"], "leaf")   # RED baseline: "seed"
        self.assertEqual(set(g1.nodes()), {"eeee", "aaaa"})  # node set unchanged

    def test_warm_churn_with_peers_and_pinned(self):
        """Warm target with multiple project peers plus a pinned entry (F3).

        A baseline-visible bump first makes the next load take the refresh path;
        the refresh then churns (equal-size/restored-mtime swap after every read)
        so the target identity never stabilises. Candidate: exactly two
        constructions then the exact churn RuntimeError; peers, pinned map,
        project order and the OLD target objects are all preserved. Baseline
        (mtime_ns, size) never sees the churn -> no RuntimeError -> RED."""
        P = self.write("p.json", _graph_json("pppp"))
        A = self.write("a.json", _graph_json("eeee"))
        B = self.write("b.json", _graph_json("bbbb"))
        T = self.write("t.json", _graph_json("tttt"))
        Tpath = Path(T)
        cache = self.cache_cls(4)
        gP0, cP0 = cache.load(P, pinned=True)
        gT0, cT0 = cache.load(T)
        gA0, cA0 = cache.load(A)
        gB0, cB0 = cache.load(B)

        # Force the refresh path with a baseline-visible mtime bump.
        _bump_mtime(Tpath)

        order_before = list(cache._entries)
        pin_before = list(cache._pinned)
        entryA = cache._entries[A]
        entryB = cache._entries[B]
        entryT = cache._entries[T]
        keyA, keyB = entryA["key"], entryB["key"]
        idxA0, ovA0 = gA0.graph["_trigram_index"], gA0.graph["_learning_overlay"]
        idxB0, ovB0 = gB0.graph["_trigram_index"], gB0.graph["_learning_overlay"]
        idxP0, ovP0 = gP0.graph["_trigram_index"], gP0.graph["_learning_overlay"]
        calls = {"n": 0}

        def churn(p):
            calls["n"] += 1
            assert calls["n"] <= 2, "unbounded retry: third load attempt"
            g = REAL_LOAD(p)
            atomic_swap(Tpath, _graph_json("uuuu"), restore_mtime=True)
            return g

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", churn):
            with self.assertRaises(RuntimeError) as ctx:
                cache.load(T)

        self.assertIs(type(ctx.exception), RuntimeError)
        self.assertEqual(str(ctx.exception), "graph.json changed while loading")
        self.assertEqual(calls["n"], 2)  # exactly two successful constructions

        # No premature promotion; failed refresh keeps the OLD target objects.
        self.assertEqual(list(cache._entries), order_before)
        self.assertIs(cache._entries[T], entryT)
        self.assertIs(entryT["G"], gT0)
        self.assertIs(entryT["communities"], cT0)
        # Peers untouched (objects, keys, nested maps).
        self.assertIs(cache._entries[A], entryA)
        self.assertIs(cache._entries[B], entryB)
        self.assertIs(entryA["G"], gA0)
        self.assertIs(entryB["G"], gB0)
        self.assertIs(entryA["communities"], cA0)
        self.assertIs(entryB["communities"], cB0)
        self.assertEqual(entryA["key"], keyA)
        self.assertEqual(entryB["key"], keyB)
        self.assertIs(gA0.graph["_trigram_index"], idxA0)
        self.assertIs(gA0.graph["_learning_overlay"], ovA0)
        self.assertIs(gB0.graph["_trigram_index"], idxB0)
        self.assertIs(gB0.graph["_learning_overlay"], ovB0)
        # Pinned map preserved.
        self.assertEqual(list(cache._pinned), pin_before)
        self.assertIs(cache._pinned[P]["G"], gP0)
        self.assertIs(gP0.graph["_trigram_index"], idxP0)
        self.assertIs(gP0.graph["_learning_overlay"], ovP0)
        self._assert_cache_unchanged(cache, before_failure)

    def test_r2_pinned_atomic_replacement_with_peers(self):
        """R2: a pinned entry gets an equal-size/restored-mtime atomic
        replacement while project peers are present. Candidate refreshes the
        pinned graph (reload count == 2 for P) and returns current content;
        project membership/order are untouched. Baseline can't see it -> RED."""
        P = self.write("p.json", _graph_json("eeee"))
        Ppath = Path(P)
        A = self.write("a.json", _graph_json("aaaa"))
        B = self.write("b.json", _graph_json("bbbb"))
        cache = self.cache_cls(4)
        counts = collections.defaultdict(int)

        def counting(p):
            counts[p] += 1
            return REAL_LOAD(p)

        with patch.object(mod, "_load_graph", counting):
            gP0, cP0 = cache.load(P, pinned=True)
            cache.load(A)
            cache.load(B)
            proj_before = list(cache._entries)

            old = atomic_swap(Ppath, _graph_json("ffff"), restore_mtime=True)
            self.assertNotEqual(Ppath.stat().st_ino, old.st_ino)
            self.assertEqual(Ppath.stat().st_mtime_ns, old.st_mtime_ns)
            self.assertEqual(Ppath.stat().st_size, old.st_size)

            gP1, _ = cache.load(P, pinned=True)

        current = set(REAL_LOAD(P).nodes())
        self.assertEqual(current, {"ffff", "aaaa"})
        self.assertEqual(set(gP1.nodes()), current)  # RED baseline: stale {eeee,aaaa}
        self.assertIn(P, cache._pinned)
        self.assertNotIn(P, cache._entries)              # pinned stays out of project map
        self.assertEqual(list(cache._entries), proj_before)  # peers order/membership intact
        self.assertEqual(counts[P], 2)  # RED baseline: 1 (no detected change)
        self.assertEqual(counts[A], 1)
        self.assertEqual(counts[B], 1)

    def test_entry_key_is_full_stat_tuple(self):
        """Five-field key value/shape (F6). Intended baseline RED: the baseline
        stores (mtime_ns, size). This checks construction of the composed key,
        not the independent necessity of each field."""
        A = self.write("a.json", _graph_json("eeee"))
        cache = self.cache_cls(4)
        cache.load(A)
        st = Path(A).stat()
        expected = (st.st_dev, st.st_ino, st.st_ctime_ns, st.st_mtime_ns, st.st_size)
        self.assertEqual(cache._entries[A]["key"], expected)  # RED baseline: (mtime_ns, size)

    def test_disappearance_after_load_cold_maps_filenotfound(self):
        """Cold miss whose file vanishes AFTER the read but BEFORE the post-stat.
        Candidate's post-stat raises the mapped FileNotFoundError; exactly one
        load, and nothing is inserted. Baseline performs no post-stat -> RED."""
        A = self.write("a.json", _graph_json("eeee"))
        cache = self.cache_cls(4)
        calls = {"n": 0}

        def del_after(p):
            calls["n"] += 1
            g = REAL_LOAD(p)
            os.unlink(A)  # gone before the post-stat
            return g

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", del_after):
            with self.assertRaises(FileNotFoundError) as ctx:
                cache.load(A)

        self.assertEqual(calls["n"], 1)
        self.assertIs(type(ctx.exception), FileNotFoundError)
        self.assertEqual(str(ctx.exception), f"graph.json not found: {A}")
        self.assertNotIn(A, cache._entries)
        self._assert_cache_unchanged(cache, before_failure)

    def test_disappearance_after_load_warm_retains_entry(self):
        """Warm refresh whose file vanishes after the read but before the
        post-stat. Candidate raises the mapped FileNotFoundError and RETAINS the
        old entry objects; exactly one load. Baseline has no post-stat -> RED."""
        A = self.write("a.json", _graph_json("eeee"))
        cache = self.cache_cls(4)
        gA0, cA0 = cache.load(A)
        B = self.write("b.json", _graph_json("bbbb"))
        cache.load(B)  # A is oldest: premature failure-path promotion is visible.
        _bump_mtime(Path(A))  # force refresh path
        calls = {"n": 0}

        def del_after(p):
            calls["n"] += 1
            g = REAL_LOAD(p)
            os.unlink(A)
            return g

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", del_after):
            with self.assertRaises(FileNotFoundError) as ctx:
                cache.load(A)

        self.assertEqual(calls["n"], 1)
        self.assertIs(type(ctx.exception), FileNotFoundError)
        self.assertEqual(str(ctx.exception), f"graph.json not found: {A}")
        self.assertIs(cache._entries[A]["G"], gA0)          # old entry retained
        self.assertIs(cache._entries[A]["communities"], cA0)
        self._assert_cache_unchanged(cache, before_failure)

    # ---- GREEN regression guards (baseline AND candidate) ----------------

    def test_unchanged_hit_preserves_identities_and_loader_count(self):
        A = self.write("a.json", _graph_json("eeee"))
        B = self.write("b.json", _graph_json("bbbb"))
        cache = self.cache_cls(4)
        counts = collections.defaultdict(int)

        def counting(p):
            counts[p] += 1
            return REAL_LOAD(p)

        with patch.object(mod, "_load_graph", counting):
            gA0, cA0 = cache.load(A)
            # Capture nested objects BEFORE the later hit (F2: not a tautology).
            idx0 = gA0.graph["_trigram_index"]
            ov0 = gA0.graph["_learning_overlay"]
            cache.load(B)
            gA1, cA1 = cache.load(A)  # warm hit, nothing changed on disk

        self.assertIs(gA1, gA0)
        self.assertIs(cA1, cA0)
        self.assertIs(gA1.graph["_trigram_index"], idx0)
        self.assertIs(gA1.graph["_learning_overlay"], ov0)
        self.assertEqual(counts[A], 1)             # per-target build count
        self.assertEqual(sum(counts.values()), 2)  # distinct from total across two contexts

    def test_capacity_two_eviction_and_pinned_isolation(self):
        P = self.write("p.json", _graph_json("pppp"))
        A = self.write("a.json", _graph_json("eeee"))
        B = self.write("b.json", _graph_json("bbbb"))
        C = self.write("c.json", _graph_json("cccc"))
        cache = self.cache_cls(2)
        counts = collections.defaultdict(int)

        def counting(p):
            counts[p] += 1
            return REAL_LOAD(p)

        with patch.object(mod, "_load_graph", counting):
            gP0, cP0 = cache.load(P, pinned=True)
            idxP0 = gP0.graph["_trigram_index"]
            ovP0 = gP0.graph["_learning_overlay"]
            cache.load(A)
            cache.load(B)
            self.assertEqual(list(cache._entries), [A, B])
            cache.load(A)  # hit -> promote
            self.assertEqual(list(cache._entries), [B, A])
            cache.load(C)  # miss -> evict oldest (B)
            self.assertEqual(list(cache._entries), [A, C])
            self.assertNotIn(B, cache._entries)
            self.assertIn(P, cache._pinned)
            self.assertNotIn(P, cache._entries)
            gP1, cP1 = cache.load(P, pinned=True)  # pinned hit, nothing changed

        self.assertEqual(list(cache._entries), [A, C])  # project order undisturbed
        self.assertIs(gP1, gP0)                         # F2: same object, not two aliases
        self.assertIs(cP1, cP0)
        self.assertIs(gP1.graph["_trigram_index"], idxP0)
        self.assertIs(gP1.graph["_learning_overlay"], ovP0)
        self.assertEqual(counts[P], 1)  # pinned hit performed no reload
        self.assertEqual(counts[A], 1)
        self.assertEqual(counts[C], 1)

    def test_warm_refresh_on_real_change_with_peers(self):
        A = self.write("a.json", _graph_json("eeee"))
        B = self.write("b.json", _graph_json("bbbb"))
        C = self.write("c.json", _graph_json("cccc"))
        cache = self.cache_cls(4)
        gA0, _ = cache.load(A)
        cache.load(B)
        cache.load(C)
        Path(A).write_text(_graph_json("ffff"), encoding="utf-8")
        _bump_mtime(Path(A))
        gA1, _ = cache.load(A)
        self.assertIsNot(gA1, gA0)
        self.assertEqual(set(gA1.nodes()), {"ffff", "aaaa"})
        self.assertIn(B, cache._entries)
        self.assertIn(C, cache._entries)
        self.assertEqual(list(cache._entries)[-1], A)  # refreshed target promoted

    def test_warm_refresh_on_size_change_restored_mtime(self):
        """Size-only positive control (F6): different byte size with the OLD
        mtime restored. Visible to both keys (size differs) -> GREEN on both,
        exactly one reload."""
        A = self.write("a.json", _graph_json("eeee"))
        Apath = Path(A)
        cache = self.cache_cls(4)
        counts = collections.defaultdict(int)

        def counting(p):
            counts[p] += 1
            return REAL_LOAD(p)

        with patch.object(mod, "_load_graph", counting):
            g0, _ = cache.load(A)
            self.assertEqual(set(g0.nodes()), {"eeee", "aaaa"})
            old = Apath.stat()
            Apath.write_text(_graph_json_bigger("eeee"), encoding="utf-8")
            os.utime(Apath, ns=(old.st_atime_ns, old.st_mtime_ns))  # restore mtime
            new = Apath.stat()
            self.assertNotEqual(new.st_size, old.st_size)   # size changed
            self.assertEqual(new.st_mtime_ns, old.st_mtime_ns)  # mtime restored
            g1, _ = cache.load(A)

        current = set(REAL_LOAD(A).nodes())
        self.assertEqual(current, {"eeee", "aaaa", "bbbb"})
        self.assertEqual(set(g1.nodes()), current)
        self.assertEqual(counts[A], 2)  # size change forced exactly one reload

    def test_failed_cold_miss_no_insertion_or_eviction(self):
        A = self.write("a.json", _graph_json("eeee"))
        B = self.write("b.json", _graph_json("bbbb"))
        cache = self.cache_cls(2)
        cache.load(A)
        cache.load(B)
        before = list(cache._entries)
        N = self.write("n.json", _graph_json("nnnn"))

        def boom(p):
            raise SystemExit(1)

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", boom):
            with self.assertRaises(RuntimeError):
                cache.load(N)

        self.assertNotIn(N, cache._entries)
        self.assertEqual(list(cache._entries), before)  # full LRU untouched
        self._assert_cache_unchanged(cache, before_failure)

    def test_failed_refresh_retains_old_entry_and_objects(self):
        A = self.write("a.json", _graph_json("eeee"))
        cache = self.cache_cls(4)
        gA0, cA0 = cache.load(A)
        B = self.write("b.json", _graph_json("bbbb"))
        cache.load(B)  # A is oldest: premature failure-path promotion is visible.
        idx0 = gA0.graph["_trigram_index"]
        ov0 = gA0.graph["_learning_overlay"]
        Path(A).write_text(_graph_json("ffff"), encoding="utf-8")
        _bump_mtime(Path(A))

        def boom(p):
            raise SystemExit(1)

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", boom):
            with self.assertRaises(RuntimeError):
                cache.load(A)

        self.assertIs(cache._entries[A]["G"], gA0)
        self.assertIs(cache._entries[A]["communities"], cA0)
        self.assertIs(cache._entries[A]["G"].graph["_trigram_index"], idx0)
        self.assertIs(cache._entries[A]["G"].graph["_learning_overlay"], ov0)
        self._assert_cache_unchanged(cache, before_failure)

    def test_initial_absence_maps_filenotfound_zero_loads(self):
        cache = self.cache_cls(4)
        missing = str(self.dir / "gone.json")
        calls = {"n": 0}

        def counting(p):
            calls["n"] += 1
            return REAL_LOAD(p)

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", counting):
            with self.assertRaises(FileNotFoundError) as ctx:
                cache.load(missing)

        self.assertEqual(calls["n"], 0)  # never attempted a build
        self.assertIs(type(ctx.exception), FileNotFoundError)
        self.assertEqual(str(ctx.exception), f"graph.json not found: {missing}")
        self._assert_cache_unchanged(cache, before_failure)

    def test_invalid_json_cold_wraps_runtime_with_cause_no_retry(self):
        """Genuine parse failure through the REAL loader (counting wrapper). The
        cache maps the loader's SystemExit to RuntimeError with the SystemExit
        cause, does not retry, and does not insert. The exact outer RuntimeError message is grounded in frozen serve.py;
        parser-specific stderr is not treated as the cache API."""
        bad = self.write("bad.json", "{ this is not valid json")
        cache = self.cache_cls(4)
        calls = {"n": 0}

        def counting(p):
            calls["n"] += 1
            return REAL_LOAD(p)

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", counting):
            with self.assertRaises(RuntimeError) as ctx:
                cache.load(bad)

        self.assertIs(type(ctx.exception), RuntimeError)
        self.assertEqual(str(ctx.exception), f"could not load graph.json at {bad}")
        self.assertIsInstance(ctx.exception.__cause__, SystemExit)
        self.assertEqual(calls["n"], 1)  # parse failure is not a key change -> no retry
        self.assertNotIn(bad, cache._entries)
        self._assert_cache_unchanged(cache, before_failure)

    def test_invalid_json_warm_retains_old_entry_no_retry(self):
        A = self.write("a.json", _graph_json("eeee"))
        cache = self.cache_cls(4)
        gA0, cA0 = cache.load(A)
        B = self.write("b.json", _graph_json("bbbb"))
        cache.load(B)  # A is oldest: premature failure-path promotion is visible.
        Path(A).write_text("{ broken json", encoding="utf-8")
        _bump_mtime(Path(A))  # force refresh path
        calls = {"n": 0}

        def counting(p):
            calls["n"] += 1
            return REAL_LOAD(p)

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", counting):
            with self.assertRaises(RuntimeError) as ctx:
                cache.load(A)

        self.assertIs(type(ctx.exception), RuntimeError)
        self.assertEqual(str(ctx.exception), f"could not load graph.json at {A}")
        self.assertIsInstance(ctx.exception.__cause__, SystemExit)
        self.assertEqual(calls["n"], 1)
        self.assertIs(cache._entries[A]["G"], gA0)          # old entry retained
        self.assertIs(cache._entries[A]["communities"], cA0)
        self._assert_cache_unchanged(cache, before_failure)

    def test_systemexit_wrapped_with_cause_no_retry(self):
        """Structural mock control only -- NOT real parse coverage."""
        A = self.write("a.json", _graph_json("eeee"))
        cache = self.cache_cls(4)
        calls = {"n": 0}

        def boom(p):
            calls["n"] += 1
            raise SystemExit(2)

        before_failure = self._snapshot_cache(cache)
        with patch.object(mod, "_load_graph", boom):
            with self.assertRaises(RuntimeError) as ctx:
                cache.load(A)

        self.assertIsInstance(ctx.exception.__cause__, SystemExit)
        self.assertEqual(calls["n"], 1)  # failure is not a key change -> no retry
        self._assert_cache_unchanged(cache, before_failure)

    # ---- Control (documentation, passes on both) -------------------------

    def test_fake_identical_stat_documents_stale_hit_boundary(self):
        """Claim boundary: when stat is *truly* identical across a change, BOTH
        implementations correctly serve a hit. We cannot restore ctime for real,
        so we fake an identical stat for the target only. This documents the
        cache's visibility contract; it is not a discriminator."""
        A = self.write("g.json", _graph_json("eeee"))
        Apath = Path(A)
        snap = Apath.stat()
        frozen = types.SimpleNamespace(
            **{k: getattr(snap, k) for k in dir(snap) if k.startswith("st_")}
        )
        orig_stat = mod.Path.stat

        def fake_stat(self, *, follow_symlinks=True):
            try:
                if os.path.samefile(str(self), A):
                    return frozen
            except OSError:
                pass
            return orig_stat(self, follow_symlinks=follow_symlinks)

        cache = self.cache_cls(4)
        g0, _ = cache.load(A)
        atomic_swap(Apath, _graph_json("ffff"), restore_mtime=True)
        with patch.object(mod.Path, "stat", fake_stat):
            g1, _ = cache.load(A)

        self.assertIs(g1, g0)  # identical (fake) stat -> hit on baseline and candidate
        self.assertEqual(set(g1.nodes()), {"eeee", "aaaa"})


if __name__ == "__main__":
    unittest.main()
