#!/usr/bin/env python3
"""Deterministic benchmark for deduplicate_entities optimizations.

Three optimizations under test:
  1. MinHash.bulk_update()  — one numpy broadcast per node vs a per-shingle loop
  2. In-place np.minimum    — eliminates one array allocation per shingle
  3. id_to_node dict        — O(1) lookup per remap group vs O(N) list scan

Usage:
    python benchmarks/benchmark_dedup.py
"""
from __future__ import annotations

import copy
import functools
import hashlib
import math
import random
import re
import struct
import time
import unicodedata
from collections import defaultdict

import numpy as np
from rapidfuzz.distance import JaroWinkler

# ── shared constants ──────────────────────────────────────────────────────────

_ENTROPY_THRESHOLD = 2.5
_LSH_THRESHOLD     = 0.7
_MERGE_THRESHOLD   = 92.0
_COMMUNITY_BOOST   = 5.0
_NUM_PERM          = 128
_CHUNK_SUFFIX      = re.compile(r"_c\d+$")

_MP = np.uint64((1 << 61) - 1)  # Mersenne prime
_MH = np.uint64(0xFFFF_FFFF)    # 32-bit mask

_MH_COEFFS_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _mh_coeffs(num_perm: int) -> tuple[np.ndarray, np.ndarray]:
    if num_perm not in _MH_COEFFS_CACHE:
        rng = np.random.RandomState(1)  # fixed seed → same coefficients every run
        a = rng.randint(1, int(_MP), num_perm, dtype=np.uint64)
        b = rng.randint(0, int(_MP), num_perm, dtype=np.uint64)
        _MH_COEFFS_CACHE[num_perm] = (a, b)
    return _MH_COEFFS_CACHE[num_perm]


# ── shared helpers (identical in both variants) ───────────────────────────────

@functools.lru_cache(maxsize=None)
def _norm(label: str | None) -> str:
    if not isinstance(label, str):
        label = "" if label is None else str(label)
    label = unicodedata.normalize("NFKC", label)
    return re.sub(r"[\W_]+", " ", label.casefold(), flags=re.UNICODE).strip()


def _entropy(label: str) -> float:
    s = _norm(label)
    if not s:
        return 0.0
    freq: dict[str, int] = defaultdict(int)
    for ch in s:
        freq[ch] += 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _shingles(text: str, k: int = 3) -> set[str]:
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


_VARIANT_SUFFIX = re.compile(r"^(.*[a-z])([0-9]+[a-z]*|[a-z]{2,})$")


def _is_variant_pair(a: str, b: str) -> bool:
    if a == b:
        return False
    if max(len(a), len(b)) >= 12:
        return False
    ma, mb = _VARIANT_SUFFIX.match(a), _VARIANT_SUFFIX.match(b)
    if not (ma and mb):
        return False
    return ma.group(1) == mb.group(1) and ma.group(2) != mb.group(2)


def _short_label_blocked(a: str, b: str, jw_score: float) -> bool:
    if max(len(a), len(b)) >= 12:
        return False
    from rapidfuzz.distance import DamerauLevenshtein
    if jw_score >= 97.0 and len(a) == len(b) and DamerauLevenshtein.distance(a, b) <= 1:
        return False
    return True


class _UF:
    def __init__(self) -> None:
        self._parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self._parent.setdefault(x, x)
        while self._parent[x] != x:
            self._parent[x] = self._parent[self._parent[x]]
            x = self._parent[x]
        return x

    def union(self, x: str, y: str) -> None:
        self._parent.setdefault(x, x)
        self._parent.setdefault(y, y)
        rx, ry = self.find(x), self.find(y)
        if rx != ry:
            self._parent[ry] = rx

    def components(self) -> dict[str, list[str]]:
        groups: dict[str, list[str]] = defaultdict(list)
        for x in self._parent:
            groups[self.find(x)].append(x)
        return dict(groups)


def _pick_winner(nodes: list[dict]) -> dict:
    if not nodes:
        raise ValueError("Cannot pick winner from empty list")

    def _score(n: dict) -> tuple[int, int, str]:
        return (1 if _CHUNK_SUFFIX.search(n["id"]) else 0, len(n["id"]), n["id"])

    return min(nodes, key=_score)


def _lsh_integrate(f, lo: float, hi: float, n: int = 128) -> float:
    h = (hi - lo) / n
    return h * sum(f(lo + i * h) for i in range(n))


_LSH_PARAMS_CACHE: dict[tuple[float, int], tuple[int, int]] = {}


def _optimal_lsh_params(threshold: float, num_perm: int) -> tuple[int, int]:
    key = (threshold, num_perm)
    if key in _LSH_PARAMS_CACHE:
        return _LSH_PARAMS_CACHE[key]
    best_err, best = float("inf"), (1, 1)
    for b in range(1, num_perm + 1):
        for r in range(1, num_perm // b + 1):
            fp = _lsh_integrate(
                lambda s, _b=float(b), _r=float(r): 1 - (1 - s ** _r) ** _b,
                0.0, threshold,
            )
            fn = _lsh_integrate(
                lambda s, _b=float(b), _r=float(r): 1 - (1 - (1 - s ** _r) ** _b),
                threshold, 1.0,
            )
            err = 0.5 * fp + 0.5 * fn
            if err < best_err:
                best_err, best = err, (b, r)
    _LSH_PARAMS_CACHE[key] = best
    return best


class MinHashLSH:
    def __init__(self, threshold: float = 0.5, num_perm: int = 128) -> None:
        self.b, self.r = _optimal_lsh_params(threshold, num_perm)
        self._tables: list[dict[bytes, list[str]]] = [{} for _ in range(self.b)]
        self._keys: set[str] = set()

    def insert(self, key: str, minhash) -> None:
        if key in self._keys:
            raise ValueError(f"Key {key!r} already exists in MinHashLSH")
        self._keys.add(key)
        hv = minhash.hashvalues
        for i, table in enumerate(self._tables):
            band = hv[i * self.r : (i + 1) * self.r].tobytes()
            table.setdefault(band, []).append(key)

    def query(self, minhash) -> list[str]:
        hv = minhash.hashvalues
        candidates: set[str] = set()
        for i, table in enumerate(self._tables):
            band = hv[i * self.r : (i + 1) * self.r].tobytes()
            candidates.update(table.get(band, []))
        return list(candidates)


# ═════════════════════════════════════════════════════════════════════════════
# BEFORE — allocating np.minimum · per-shingle update loop · O(N) list scan
# ═════════════════════════════════════════════════════════════════════════════

class _MinHash_Before:
    __slots__ = ("num_perm", "hashvalues", "_a", "_b")

    def __init__(self, num_perm: int = 128) -> None:
        self.num_perm = num_perm
        self.hashvalues = np.full(num_perm, int(_MH), dtype=np.uint64)
        self._a, self._b = _mh_coeffs(num_perm)

    def update(self, v: bytes) -> None:
        hv  = np.uint64(struct.unpack("<I", hashlib.sha1(v).digest()[:4])[0])
        phv = np.bitwise_and((self._a * hv + self._b) % _MP, _MH)
        self.hashvalues = np.minimum(self.hashvalues, phv)  # allocates a new array


def _make_minhash_before(text: str, num_perm: int = _NUM_PERM) -> _MinHash_Before:
    m = _MinHash_Before(num_perm=num_perm)
    for shingle in _shingles(text.replace(" ", "")):
        m.update(shingle.encode("utf-8"))
    return m


def deduplicate_entities_before(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
) -> tuple[list[dict], list[dict]]:
    if len(nodes) <= 1:
        return nodes, edges

    seen_ids: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id", "")
        if nid and nid not in seen_ids:
            seen_ids[nid] = node
    unique_nodes = list(seen_ids.values())

    if len(unique_nodes) <= 1:
        return unique_nodes, edges

    norm_to_nodes: dict[str, list[dict]] = defaultdict(list)
    for node in unique_nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key:
            norm_to_nodes[key].append(node)

    uf = _UF()
    for key, group in norm_to_nodes.items():
        if len(group) <= 1:
            continue
        by_file: dict[str, list[dict]] = defaultdict(list)
        for node in group:
            by_file[node.get("source_file") or ""].append(node)
        for sf, file_group in by_file.items():
            if not sf:
                continue
            if len(file_group) > 1:
                winner = _pick_winner(file_group)
                for node in file_group:
                    uf.union(winner["id"], node["id"])

    candidates: list[dict] = []
    seen_norms: set[str] = set()
    for node in unique_nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key and key not in seen_norms:
            seen_norms.add(key)
            if (_entropy(node.get("label", "")) >= _ENTROPY_THRESHOLD
                    and not node.get("source_location")):
                candidates.append(node)

    if len(candidates) >= 2:
        lsh = MinHashLSH(threshold=_LSH_THRESHOLD, num_perm=_NUM_PERM)
        minhashes:     dict[str, _MinHash_Before] = {}
        candidates_by_id: dict[str, dict]         = {}
        norm_cache:    dict[str, str]              = {}

        for node in candidates:
            node_id = node["id"]
            candidates_by_id[node_id] = node
            nl = _norm(node.get("label", node.get("id", "")))
            norm_cache[node_id] = nl
            m = _make_minhash_before(nl)
            minhashes[node_id] = m
            try:
                lsh.insert(node_id, m)
            except ValueError:
                pass

        for node in candidates:
            node_id    = node["id"]
            norm_label = norm_cache[node_id]
            for neighbor_id in lsh.query(minhashes[node_id]):
                if neighbor_id == node_id:
                    continue
                if uf.find(node_id) == uf.find(neighbor_id):
                    continue
                neighbor = candidates_by_id.get(neighbor_id)
                if neighbor is None:
                    continue
                neighbor_norm = norm_cache.get(neighbor_id) or _norm(
                    neighbor.get("label", neighbor.get("id", ""))
                )
                score = JaroWinkler.normalized_similarity(norm_label, neighbor_norm) * 100
                if _is_variant_pair(norm_label, neighbor_norm):
                    continue
                if _short_label_blocked(norm_label, neighbor_norm, score):
                    continue
                _lo, _hi = sorted((norm_label, neighbor_norm), key=len)
                if _hi.startswith(_lo) and _hi != _lo:
                    continue
                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if (c1 is not None and c2 is not None and c1 == c2
                        and min(len(norm_label), len(neighbor_norm)) >= 12):
                    score += _COMMUNITY_BOOST
                if score >= _MERGE_THRESHOLD:
                    if norm_label == neighbor_norm:
                        if (node.get("source_file") or "") != (neighbor.get("source_file") or ""):
                            continue
                    all_group = (norm_to_nodes.get(norm_label, [node])
                                 + norm_to_nodes.get(neighbor_norm, [neighbor]))
                    winner = _pick_winner(all_group)
                    uf.union(winner["id"], node_id)
                    uf.union(winner["id"], neighbor_id)

    # BEFORE: O(N × K) — scans all unique_nodes for every merge group
    components = uf.components()
    remap: dict[str, str] = {}
    for root, members in components.items():
        if len(members) == 1:
            continue
        group_nodes = [n for n in unique_nodes if n["id"] in members]
        winner    = _pick_winner(group_nodes) if group_nodes else {"id": root}
        winner_id = winner["id"]
        for member in members:
            if member != winner_id:
                remap[member] = winner_id

    if not remap:
        return unique_nodes, edges

    deduped_nodes = [n for n in unique_nodes if n["id"] not in remap]
    deduped_edges = []
    for edge in edges:
        e   = dict(edge)
        src = e["source"] if "source" in e else e.get("from")
        tgt = e["target"] if "target" in e else e.get("to")
        if src is None or tgt is None:
            continue
        e["source"] = remap.get(src, src)
        e["target"] = remap.get(tgt, tgt)
        e.pop("from", None)
        e.pop("to",   None)
        if e["source"] != e["target"]:
            deduped_edges.append(e)

    return deduped_nodes, deduped_edges


# ═════════════════════════════════════════════════════════════════════════════
# AFTER — in-place np.minimum · bulk_update broadcast · id_to_node dict
# ═════════════════════════════════════════════════════════════════════════════

class _MinHash_After:
    __slots__ = ("num_perm", "hashvalues", "_a", "_b")

    def __init__(self, num_perm: int = 128) -> None:
        self.num_perm = num_perm
        self.hashvalues = np.full(num_perm, int(_MH), dtype=np.uint64)
        self._a, self._b = _mh_coeffs(num_perm)

    def update(self, v: bytes) -> None:
        hv  = np.uint64(struct.unpack("<I", hashlib.sha1(v).digest()[:4])[0])
        phv = np.bitwise_and((self._a * hv + self._b) % _MP, _MH)
        np.minimum(self.hashvalues, phv, out=self.hashvalues)  # in-place

    def bulk_update(self, values: list) -> None:
        """Hash all shingles in one broadcast: (num_perm × len(values)) matrix."""
        if not values:
            return
        hvs = np.array(
            [struct.unpack("<I", hashlib.sha1(v).digest()[:4])[0] for v in values],
            dtype=np.uint64,
        )
        phvs = np.bitwise_and((self._a[:, None] * hvs[None, :] + self._b[:, None]) % _MP, _MH)
        np.minimum(self.hashvalues, phvs.min(axis=1), out=self.hashvalues)


def _make_minhash_after(text: str, num_perm: int = _NUM_PERM) -> _MinHash_After:
    m = _MinHash_After(num_perm=num_perm)
    m.bulk_update([s.encode("utf-8") for s in _shingles(text.replace(" ", ""))])
    return m


def deduplicate_entities_after(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
) -> tuple[list[dict], list[dict]]:
    if len(nodes) <= 1:
        return nodes, edges

    seen_ids: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id", "")
        if nid and nid not in seen_ids:
            seen_ids[nid] = node
    unique_nodes = list(seen_ids.values())

    if len(unique_nodes) <= 1:
        return unique_nodes, edges

    norm_to_nodes: dict[str, list[dict]] = defaultdict(list)
    for node in unique_nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key:
            norm_to_nodes[key].append(node)

    uf = _UF()
    for key, group in norm_to_nodes.items():
        if len(group) <= 1:
            continue
        by_file: dict[str, list[dict]] = defaultdict(list)
        for node in group:
            by_file[node.get("source_file") or ""].append(node)
        for sf, file_group in by_file.items():
            if not sf:
                continue
            if len(file_group) > 1:
                winner = _pick_winner(file_group)
                for node in file_group:
                    uf.union(winner["id"], node["id"])

    candidates: list[dict] = []
    seen_norms: set[str] = set()
    for node in unique_nodes:
        key = _norm(node.get("label", node.get("id", "")))
        if key and key not in seen_norms:
            seen_norms.add(key)
            if (_entropy(node.get("label", "")) >= _ENTROPY_THRESHOLD
                    and not node.get("source_location")):
                candidates.append(node)

    if len(candidates) >= 2:
        lsh = MinHashLSH(threshold=_LSH_THRESHOLD, num_perm=_NUM_PERM)
        minhashes:     dict[str, _MinHash_After] = {}
        candidates_by_id: dict[str, dict]        = {}
        norm_cache:    dict[str, str]             = {}

        for node in candidates:
            node_id = node["id"]
            candidates_by_id[node_id] = node
            nl = _norm(node.get("label", node.get("id", "")))
            norm_cache[node_id] = nl
            m = _make_minhash_after(nl)
            minhashes[node_id] = m
            try:
                lsh.insert(node_id, m)
            except ValueError:
                pass

        for node in candidates:
            node_id    = node["id"]
            norm_label = norm_cache[node_id]
            for neighbor_id in lsh.query(minhashes[node_id]):
                if neighbor_id == node_id:
                    continue
                if uf.find(node_id) == uf.find(neighbor_id):
                    continue
                neighbor = candidates_by_id.get(neighbor_id)
                if neighbor is None:
                    continue
                neighbor_norm = norm_cache.get(neighbor_id) or _norm(
                    neighbor.get("label", neighbor.get("id", ""))
                )
                score = JaroWinkler.normalized_similarity(norm_label, neighbor_norm) * 100
                if _is_variant_pair(norm_label, neighbor_norm):
                    continue
                if _short_label_blocked(norm_label, neighbor_norm, score):
                    continue
                _lo, _hi = sorted((norm_label, neighbor_norm), key=len)
                if _hi.startswith(_lo) and _hi != _lo:
                    continue
                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if (c1 is not None and c2 is not None and c1 == c2
                        and min(len(norm_label), len(neighbor_norm)) >= 12):
                    score += _COMMUNITY_BOOST
                if score >= _MERGE_THRESHOLD:
                    if norm_label == neighbor_norm:
                        if (node.get("source_file") or "") != (neighbor.get("source_file") or ""):
                            continue
                    all_group = (norm_to_nodes.get(norm_label, [node])
                                 + norm_to_nodes.get(neighbor_norm, [neighbor]))
                    winner = _pick_winner(all_group)
                    uf.union(winner["id"], node_id)
                    uf.union(winner["id"], neighbor_id)

    # AFTER: O(N + total_members) — one dict lookup per member
    components = uf.components()
    remap: dict[str, str] = {}
    id_to_node: dict[str, dict] = {n["id"]: n for n in unique_nodes}
    for root, members in components.items():
        if len(members) == 1:
            continue
        group_nodes = [id_to_node[mid] for mid in members if mid in id_to_node]
        winner    = _pick_winner(group_nodes) if group_nodes else {"id": root}
        winner_id = winner["id"]
        for member in members:
            if member != winner_id:
                remap[member] = winner_id

    if not remap:
        return unique_nodes, edges

    deduped_nodes = [n for n in unique_nodes if n["id"] not in remap]
    deduped_edges = []
    for edge in edges:
        e   = dict(edge)
        src = e["source"] if "source" in e else e.get("from")
        tgt = e["target"] if "target" in e else e.get("to")
        if src is None or tgt is None:
            continue
        e["source"] = remap.get(src, src)
        e["target"] = remap.get(tgt, tgt)
        e.pop("from", None)
        e.pop("to",   None)
        if e["source"] != e["target"]:
            deduped_edges.append(e)

    return deduped_nodes, deduped_edges


# ═════════════════════════════════════════════════════════════════════════════
# Data generation  (fixed seed → fully deterministic)
# ═════════════════════════════════════════════════════════════════════════════

# Compound vocabulary: every word has high Shannon entropy when used as a label
_VOCAB = [
    "Authentication", "Authorization", "UserManagement", "ProfileSettings",
    "DataManager",    "DataHandler",   "ServiceProvider", "FactoryRegistry",
    "ServiceBuilder", "RepositoryManager", "ControllerHandler", "ProcessorFactory",
    "ValidatorRegistry", "DataLoader", "ConfigurationManager", "ConnectionFactory",
    "ContextBuilder", "ModuleRegistry", "InterfaceProvider", "ImplementationHandler",
    "ExtensionManager", "PluginRegistry", "ComponentFactory", "AdapterHandler",
    "WrapperProvider", "DecoratorFactory", "ObserverRegistry", "StrategyManager",
    "CommandHandler", "QueryProcessor", "EventDispatcher", "ListenerRegistry",
    "ParserFactory",  "SerializerManager", "TransformerProvider", "ConverterHandler",
    "CacheManager",   "StoreProvider", "QueueProcessor", "BufferHandler",
    "PipelineFactory", "NetworkManager", "SocketProvider", "ProtocolHandler",
    "EndpointRegistry", "GatewayFactory", "SchedulerManager", "ExecutorProvider",
    "WorkerHandler",  "ThreadManager",
]


def generate_data(
    n_base:         int = 40_000,
    n_exact_dupes:  int = 7_500,
    n_ast:          int = 1_500,
    n_low_entropy:  int = 1_000,
    seed:           int = 42,
) -> tuple[list[dict], list[dict], dict[str, int]]:
    """Generate synthetic dedup inputs. All randomness drawn from seed=42."""
    rng   = random.Random(seed)
    nodes: list[dict]         = []
    communities: dict[str, int] = {}
    files = [f"src/module_{i:03d}.py" for i in range(80)]

    # Semantic nodes — high entropy, no source_location → full MinHash path
    for i in range(n_base):
        label   = "".join(rng.sample(_VOCAB, rng.randint(1, 2)))
        node_id = f"sem_{i:05d}"
        nodes.append({"id": node_id, "label": label, "source_file": rng.choice(files)})
        communities[node_id] = rng.randint(0, 99)

    # Exact duplicates — same label + same source_file → guaranteed Pass 1 merges
    # (exercises the remap building loop with n_exact_dupes merge groups)
    dupe_targets = rng.sample(range(n_base), n_exact_dupes)
    for i, target_idx in enumerate(dupe_targets):
        base    = nodes[target_idx]
        node_id = f"dup_{i:05d}"
        nodes.append({
            "id":          node_id,
            "label":       base["label"],
            "source_file": base["source_file"],
        })
        communities[node_id] = communities[base["id"]]

    # AST nodes — source_location present → excluded from MinHash candidate pool
    for i in range(n_ast):
        label   = "".join(rng.sample(_VOCAB, rng.randint(1, 2)))
        node_id = f"ast_{i:04d}"
        nodes.append({
            "id":              node_id,
            "label":           label,
            "source_file":     rng.choice(files),
            "source_location": f"L{rng.randint(1, 500)}",
        })
        communities[node_id] = rng.randint(0, 99)

    # Low-entropy nodes — filtered by _entropy gate, never reach MinHash
    low_ent_labels = ["a", "id", "x", "ok", "no", "go", "do", "to", "is", "as"]
    for i in range(n_low_entropy):
        node_id = f"low_{i:04d}"
        nodes.append({
            "id":          node_id,
            "label":       rng.choice(low_ent_labels),
            "source_file": rng.choice(files),
        })
        communities[node_id] = rng.randint(0, 99)

    rng.shuffle(nodes)  # remove any accidental insertion-order bias

    all_ids = [n["id"] for n in nodes]
    n_edges = min(len(nodes) * 3, 30_000)
    edges: list[dict] = [
        {"source": s, "target": t, "relation": "uses"}
        for s, t in (rng.sample(all_ids, 2) for _ in range(n_edges))
    ]

    return nodes, edges, communities


# ═════════════════════════════════════════════════════════════════════════════
# Benchmark runner
# ═════════════════════════════════════════════════════════════════════════════

def _canonical(nodes: list[dict], edges: list[dict]) -> tuple[frozenset, frozenset]:
    return (
        frozenset(n["id"] for n in nodes),
        frozenset((e["source"], e["target"]) for e in edges),
    )


def main() -> None:
    SEP = "=" * 62

    print(SEP)
    print("  deduplicate_entities — before vs after benchmark")
    print(SEP)

    # ── data ──────────────────────────────────────────────────────────────────
    print("\nGenerating data (seed=42)...", end=" ", flush=True)
    nodes, edges, communities = generate_data()
    n_total = len(nodes)
    n_dupes = sum(1 for n in nodes if n["id"].startswith("dup_"))
    n_ast   = sum(1 for n in nodes if n.get("source_location"))
    n_low   = sum(1 for n in nodes if n["id"].startswith("low_"))
    print("done.")
    print(f"  {n_total:,} nodes total")
    print(f"    {n_total - n_dupes - n_ast - n_low:,} semantic (MinHash candidates)")
    print(f"    {n_dupes:,} exact duplicates (Pass 1 merge targets)")
    print(f"    {n_ast:,}  AST-located (skipped by source_location guard)")
    print(f"    {n_low:,}  low-entropy (skipped by entropy gate)")
    print(f"  {len(edges):,} edges")

    # ── pre-warm shared caches (not part of either variant's hot path) ────────
    print("\nPre-warming shared caches...", end=" ", flush=True)
    t0 = time.perf_counter()
    _optimal_lsh_params(_LSH_THRESHOLD, _NUM_PERM)  # LSH band/row params
    _mh_coeffs(_NUM_PERM)                           # MinHash coefficient arrays
    print(f"done ({time.perf_counter() - t0:.2f}s)")

    # ── warmup run — populates _norm lru_cache, CPython code caches ──────────
    print("\nDry run (both variants, results discarded)...", end=" ", flush=True)
    t0 = time.perf_counter()
    deduplicate_entities_before(copy.deepcopy(nodes), copy.deepcopy(edges), communities=communities)
    deduplicate_entities_after( copy.deepcopy(nodes), copy.deepcopy(edges), communities=communities)
    print(f"done ({time.perf_counter() - t0:.2f}s)")

    # ── timed run: BEFORE ─────────────────────────────────────────────────────
    print(f"\nTimed run — BEFORE ... ", end="", flush=True)
    t0 = time.perf_counter()
    out_before = deduplicate_entities_before(
        copy.deepcopy(nodes), copy.deepcopy(edges), communities=communities
    )
    t_before = time.perf_counter() - t0
    print(f"{t_before:.3f}s")

    # ── timed run: AFTER ──────────────────────────────────────────────────────
    print(f"Timed run — AFTER  ... ", end="", flush=True)
    t0 = time.perf_counter()
    out_after = deduplicate_entities_after(
        copy.deepcopy(nodes), copy.deepcopy(edges), communities=communities
    )
    t_after = time.perf_counter() - t0
    print(f"{t_after:.3f}s")

    # ── verify outputs match ──────────────────────────────────────────────────
    print("\nVerifying outputs match ... ", end="", flush=True)
    canon_before = _canonical(*out_before)
    canon_after  = _canonical(*out_after)

    if canon_before == canon_after:
        n_surviving = len(out_before[0])
        n_merged    = n_total - n_surviving
        print(f"PASS  ({n_surviving:,} surviving nodes, {n_merged:,} merged)")
    else:
        print("FAIL")
        node_ids_b, edge_set_b = canon_before
        node_ids_a, edge_set_a = canon_after
        if node_ids_b != node_ids_a:
            only_b = sorted(node_ids_b - node_ids_a)[:8]
            only_a = sorted(node_ids_a - node_ids_b)[:8]
            print(f"  only in before ({len(node_ids_b - node_ids_a)}): {only_b}")
            print(f"  only in after  ({len(node_ids_a - node_ids_b)}): {only_a}")
        if edge_set_b != edge_set_a:
            print(f"  edge count  before={len(edge_set_b):,}  after={len(edge_set_a):,}")

    # ── summary ───────────────────────────────────────────────────────────────
    print()
    print(SEP)
    print(f"  before : {t_before:.3f}s")
    print(f"  after  : {t_after:.3f}s")
    speedup = t_before / t_after if t_after > 0 else float("inf")
    print(f"  speedup: {speedup:.2f}x")
    print(SEP)


if __name__ == "__main__":
    main()
