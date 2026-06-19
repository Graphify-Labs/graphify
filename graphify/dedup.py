"""Entity deduplication pipeline for graphify knowledge graphs.

Pipeline: exact normalization → entropy gate → MinHash/LSH blocking →
Jaro-Winkler verification → same-community boost → union-find merge.
"""
from __future__ import annotations
import math
import re
import unicodedata
from collections import defaultdict

from graphify._minhash import MinHash, MinHashLSH
from rapidfuzz.distance import Jaro, JaroWinkler


# ── helpers ───────────────────────────────────────────────────────────────────

def _norm(label: str | None) -> str:
    """Lowercase + collapse non-alphanumeric runs to space (Unicode-aware)."""
    if not isinstance(label, str):
        label = "" if label is None else str(label)
    label = unicodedata.normalize("NFKC", label)
    return re.sub(r"[\W_]+", " ", label.casefold(), flags=re.UNICODE).strip()


def _entropy(label: str) -> float:
    """Shannon entropy in bits/char of the normalised label."""
    s = _norm(label)
    if not s:
        return 0.0
    freq: dict[str, int] = defaultdict(int)
    for ch in s:
        freq[ch] += 1
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in freq.values())


def _shingles(text: str, k: int = 3) -> set[str]:
    """Return k-gram character shingles of text."""
    if len(text) < k:
        return {text}
    return {text[i : i + k] for i in range(len(text) - k + 1)}


def _make_minhash(text: str, num_perm: int = 128) -> MinHash:
    # Strip spaces so "graph extractor" and "graphextractor" share shingles
    m = MinHash(num_perm=num_perm)
    for shingle in _shingles(text.replace(" ", "")):
        m.update(shingle.encode("utf-8"))
    return m


# Matches labels whose trailing token is a version/variant suffix:
# digits optionally followed by letters (chip SKUs: ASR1603, M1, Cortex-A55)
# or 2+ letters (codename revisions: cranelr vs cranel).
# Requires the stem to end in a letter so plain words don't accidentally match.
_VARIANT_SUFFIX = re.compile(r"^(.*[a-z])([0-9]+[a-z]*|[a-z]{2,})$")


def _is_variant_pair(a: str, b: str) -> bool:
    """True if a and b are sibling model/SKU variants (same stem, different suffix).

    Only applied to short labels (< 12 chars); long labels go through JW normally.
    """
    if a == b:
        return False
    if max(len(a), len(b)) >= 12:
        return False
    ma, mb = _VARIANT_SUFFIX.match(a), _VARIANT_SUFFIX.match(b)
    if not (ma and mb):
        return False
    return ma.group(1) == mb.group(1) and ma.group(2) != mb.group(2)


def _short_label_blocked(a: str, b: str, jw_score: float) -> bool:
    """Block fuzzy merge for short labels unless it's a same-length single-char substitution.

    Insertions/deletions on short strings (cranel/cranelr, M1/M1 Pro) produce
    high Jaro-Winkler scores due to the prefix bonus but are almost never true
    duplicates — they're abbreviations or variants.
    """
    if max(len(a), len(b)) >= 12:
        return False
    from rapidfuzz.distance import DamerauLevenshtein
    # Allow only same-length single-char substitutions (true typos like "Extractor"/"Extractar").
    # Block length-differing pairs regardless of score.
    if jw_score >= 97.0 and len(a) == len(b) and DamerauLevenshtein.distance(a, b) <= 1:
        return False
    return True


_DIGIT_RUN = re.compile(r"\d+")


def _numeric_tokens_differ(a: str, b: str) -> bool:
    """True when two labels carry different embedded numbers (#1284).

    Long labels that differ only in their digit runs ("ADR 0011 §D5" vs
    "ADR 0013 D4", "3.1 Product Goals" vs "1.1 Product Goals", "block3" vs
    "block13", "40%+ retention" vs "<20% retention") are numbered/versioned
    siblings, not duplicates -- but the long shared boilerplate keeps
    Jaro-Winkler above _MERGE_THRESHOLD, and _is_variant_pair only covers
    short trailing suffixes. Digit runs are compared as multisets with
    leading zeros stripped, so zero-padding ("09" vs "9") does not count as
    a difference. (String comparison, not int(): a pathological label with a
    >4300-digit run would crash int() on Python's conversion limit.) Labels
    with identical numbers, or none at all, are unaffected.
    """
    if a == b:
        return False
    return sorted(t.lstrip("0") or "0" for t in _DIGIT_RUN.findall(a)) != \
        sorted(t.lstrip("0") or "0" for t in _DIGIT_RUN.findall(b))


# file_type values whose identity is anchored to their source location, not
# their label text. Like code (#1205), these must not be label-merged across
# files: rationale = module/class docstrings, document = headings/positional
# content. `concept` is intentionally excluded -- it is the type meant to unify
# across files (protected from over-merge by the numeric/Jaro guards instead).
_FILE_ANCHORED_NONCODE = frozenset({"rationale", "document"})


def _crossfile_fileanchored_blocked(node: dict, neighbor: dict) -> bool:
    """Block label-based merging of file-anchored non-code nodes across files (#1284).

    rationale/document nodes are docstring- and heading-derived and as
    file-anchored as the code they describe (#1205's reasoning, one layer up):
    parallel modules carry near-identical boilerplate ("Django app config for
    apps.<name>. No business logic here...") that differs by one word and sails
    past the JW threshold. Same-file duplicates of these types may still merge.
    """
    if (node.get("file_type") not in _FILE_ANCHORED_NONCODE
            and neighbor.get("file_type") not in _FILE_ANCHORED_NONCODE):
        return False
    return (node.get("source_file") or "") != (neighbor.get("source_file") or "")


# ── union-find ────────────────────────────────────────────────────────────────

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


# ── constants ─────────────────────────────────────────────────────────────────

_ENTROPY_THRESHOLD = 2.5
_LSH_THRESHOLD = 0.7
_MERGE_THRESHOLD = 92.0     # rapidfuzz normalized_similarity * 100
_COMMUNITY_BOOST = 5.0      # score bonus when both nodes share community
_NUM_PERM = 128
_CHUNK_SUFFIX = re.compile(r"_c\d+$")


def _is_code(node: dict) -> bool:
    """True for AST-extracted code symbols.

    Code-node identity is the node ID (which already encodes the fully
    qualified path: module/class/symbol). The label is only a display name
    (e.g. a bare ``.draw()`` method name, or a function name shared by two
    parallel backends), so label-based merging conflates distinct symbols
    (#1205). Genuine duplicates — the same symbol re-extracted — share an ID
    and are already collapsed by the exact-ID ``seen_ids`` pre-dedup above,
    so code never needs label-based merging.
    """
    return node.get("file_type") == "code"


# ── main entry point ──────────────────────────────────────────────────────────

def deduplicate_entities(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
    dedup_llm_backend: str | None = None,
) -> tuple[list[dict], list[dict]]:
    """Deduplicate near-identical entities in a knowledge graph.

    Args:
        nodes: list of node dicts with at minimum {"id": str, "label": str}
        edges: list of edge dicts with {"source": str, "target": str, ...}
        communities: mapping of node_id -> community_id (from cluster())
        dedup_llm_backend: if set, use LLM to resolve ambiguous pairs

    Returns:
        (deduped_nodes, deduped_edges) with edges rewired to survivors
    """
    # Guard: cross-project dedup is not supported — nodes from different repos
    # share label names by coincidence and must never be merged by string similarity.
    # If you need to dedup a global graph, run deduplicate_entities per-repo first.
    repos_seen = {n.get("repo") for n in nodes if n.get("repo")}
    if len(repos_seen) > 1:
        raise ValueError(
            f"deduplicate_entities: nodes span multiple repos {sorted(repos_seen)!r}. "
            f"Cross-project dedup is disabled — run dedup per-repo before merging."
        )

    if len(nodes) <= 1:
        return nodes, edges

    # Pre-deduplicate: keep first occurrence of each id
    seen_ids: dict[str, dict] = {}
    for node in nodes:
        nid = node.get("id", "")
        if nid and nid not in seen_ids:
            seen_ids[nid] = node
    unique_nodes = list(seen_ids.values())

    if len(unique_nodes) <= 1:
        return unique_nodes, edges

    # ── pass 1: exact normalization ───────────────────────────────────────────
    norm_to_nodes: dict[str, list[dict]] = defaultdict(list)
    for node in unique_nodes:
        # Code symbols are keyed by ID, never by label — skip them entirely so
        # distinct same-named symbols are never merged by string similarity (#1205).
        if _is_code(node):
            continue
        key = _norm(node.get("label", node.get("id", "")))
        if key:
            norm_to_nodes[key].append(node)

    uf = _UF()
    exact_merges = 0
    for key, group in norm_to_nodes.items():
        if len(group) <= 1:
            continue
        # Partition by source_file — only merge within the same file in Pass 1.
        # Cross-file matches fall through to Pass 2 fuzzy matching.
        by_file: dict[str, list[dict]] = defaultdict(list)
        for node in group:
            sf = node.get("source_file") or ""
            by_file[sf].append(node)
        for sf, file_group in by_file.items():
            if not sf:
                # No source_file — cannot prove same symbol; skip to avoid
                # collapsing distinct nodes that happen to share a label (#1178).
                continue
            if len(file_group) > 1:
                winner = _pick_winner(file_group)
                for node in file_group:
                    uf.union(winner["id"], node["id"])
                exact_merges += len(file_group) - 1

    # ── pass 2: MinHash/LSH + Jaro-Winkler (high-entropy nodes only) ─────────
    candidates: list[dict] = []
    seen_norms: set[str] = set()
    for node in unique_nodes:
        # Code symbols are excluded from fuzzy matching too: two functions with
        # similar long names in different files (parallel backends, sibling
        # classes) must not be fuzzy-merged, and a code↔concept fuzzy match must
        # not transitively union two distinct code symbols via a concept (#1205).
        if _is_code(node):
            continue
        key = _norm(node.get("label", node.get("id", "")))
        if key and key not in seen_norms:
            seen_norms.add(key)
            if _entropy(node.get("label", "")) >= _ENTROPY_THRESHOLD:
                candidates.append(node)

    fuzzy_merges = 0
    if len(candidates) >= 2:
        lsh = MinHashLSH(threshold=_LSH_THRESHOLD, num_perm=_NUM_PERM)
        minhashes: dict[str, MinHash] = {}
        # Pre-build O(1) lookup structures so the query loop below doesn't scan
        # the candidates list linearly for every LSH neighbor (was O(n²×B)).
        candidates_by_id: dict[str, dict] = {}
        norm_cache: dict[str, str] = {}

        for node in candidates:
            node_id = node["id"]
            candidates_by_id[node_id] = node
            nl = _norm(node.get("label", node.get("id", "")))
            norm_cache[node_id] = nl
            m = _make_minhash(nl)
            minhashes[node_id] = m
            try:
                lsh.insert(node_id, m)
            except ValueError:
                pass  # duplicate key in LSH — already inserted

        for node in candidates:
            node_id = node["id"]
            norm_label = norm_cache[node_id]
            neighbors = lsh.query(minhashes[node_id])

            for neighbor_id in neighbors:
                if neighbor_id == node_id:
                    continue
                if uf.find(node_id) == uf.find(neighbor_id):
                    continue

                neighbor = candidates_by_id.get(neighbor_id)
                if neighbor is None:
                    continue

                neighbor_norm = norm_cache.get(neighbor_id) or _norm(neighbor.get("label", neighbor.get("id", "")))
                # Cross-file long labels score on plain Jaro (no prefix bonus).
                # Jaro-Winkler's leading-prefix bonus lifts pairs that share a
                # prefix but diverge in a distinguishing token ("testing-library
                # jest-native" vs "react-native") past threshold, fabricating
                # destructive cross-file merges; on Jaro alone they fall short
                # while true cross-file duplicates still clear it (#1243). Same-file
                # near-duplicates keep Jaro-Winkler (low-risk, and a mid-string
                # stopword insertion needs the prefix bonus to merge); short labels
                # keep Jaro-Winkler too (gated by _short_label_blocked).
                _xfile = (node.get("source_file") or "") != (neighbor.get("source_file") or "")
                if _xfile and max(len(norm_label), len(neighbor_norm)) >= 12:
                    score = Jaro.normalized_similarity(norm_label, neighbor_norm) * 100
                else:
                    score = JaroWinkler.normalized_similarity(norm_label, neighbor_norm) * 100

                if _is_variant_pair(norm_label, neighbor_norm):
                    continue
                if _short_label_blocked(norm_label, neighbor_norm, score):
                    continue
                # Prefix-extension pairs (getActiveSession / getActiveSessions,
                # parseConfig / parseConfigFile) are almost never duplicates —
                # one is a strict suffix-extension of the other. Block the merge
                # regardless of JW score (#1201).
                _lo, _hi = sorted((norm_label, neighbor_norm), key=len)
                if _hi.startswith(_lo) and _hi != _lo:
                    continue
                # Numbered/versioned siblings and cross-file file-anchored
                # boilerplate (rationale/document) are decisively distinct
                # regardless of score (#1284).
                if _numeric_tokens_differ(norm_label, neighbor_norm):
                    continue
                if _crossfile_fileanchored_blocked(node, neighbor):
                    continue

                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if (c1 is not None and c2 is not None and c1 == c2
                        and min(len(norm_label), len(neighbor_norm)) >= 12):
                    score += _COMMUNITY_BOOST

                if score >= _MERGE_THRESHOLD:
                    # Identical labels across different source files almost always
                    # means same-named-but-different symbols (trait impls, wrapper
                    # methods, common type names). Mirror Pass 1's source_file
                    # partition for this sub-case. (#1046, leaks #895's fix)
                    if norm_label == neighbor_norm:
                        sf_a = node.get("source_file") or ""
                        sf_b = neighbor.get("source_file") or ""
                        if sf_a != sf_b:
                            continue
                    # Pick the winner from the verified pair only. Selecting it
                    # from the union of both normalized-label groups pulls
                    # never-compared nodes (same label, different source_file)
                    # into the merge, bypassing the #1046/#1178 guards.
                    winner = _pick_winner([node, neighbor])
                    uf.union(winner["id"], node_id)
                    uf.union(winner["id"], neighbor_id)
                    fuzzy_merges += 1

    # ── pass 3: LLM tiebreaker for ambiguous pairs (opt-in) ──────────────────
    if dedup_llm_backend is not None:
        _llm_tiebreak(candidates, uf, communities, backend=dedup_llm_backend)

    # ── build remap table from union-find components ──────────────────────────
    components = uf.components()
    remap: dict[str, str] = {}

    for root, members in components.items():
        if len(members) == 1:
            continue
        group_nodes = [n for n in unique_nodes if n["id"] in members]
        winner = _pick_winner(group_nodes) if group_nodes else {"id": root}
        winner_id = winner["id"]
        for member in members:
            if member != winner_id:
                remap[member] = winner_id

    # ── apply remap ───────────────────────────────────────────────────────────
    if not remap:
        return unique_nodes, edges

    total = len(remap)
    msg = f"[graphify] Deduplicated {total} node(s)"
    if exact_merges:
        msg += f" ({exact_merges} exact"
        if fuzzy_merges:
            msg += f", {fuzzy_merges} fuzzy"
        msg += ")"
    print(msg + ".", flush=True)

    deduped_nodes = [n for n in unique_nodes if n["id"] not in remap]
    deduped_edges = []
    for edge in edges:
        e = dict(edge)
        # Tolerate "from"/"to" keys from LLM backends that don't follow the
        # schema exactly — build_from_json normalises later but dedup runs
        # first so bracket access would KeyError here (#803).
        # Use explicit key presence check (not `or`) so empty-string src/tgt
        # aren't silently replaced by the fallback key.
        src = e["source"] if "source" in e else e.get("from")
        tgt = e["target"] if "target" in e else e.get("to")
        if src is None or tgt is None:
            continue
        e["source"] = remap.get(src, src)
        e["target"] = remap.get(tgt, tgt)
        # Remove legacy keys so they don't leak into edge attrs in graph.json.
        e.pop("from", None)
        e.pop("to", None)
        if e["source"] != e["target"]:
            deduped_edges.append(e)

    return deduped_nodes, deduped_edges


def _pick_winner(nodes: list[dict]) -> dict:
    """Pick the canonical survivor: prefer no chunk suffix, then shorter ID."""
    if not nodes:
        raise ValueError("Cannot pick winner from empty list")

    def _score(n: dict) -> tuple[int, int]:
        has_suffix = bool(_CHUNK_SUFFIX.search(n["id"]))
        return (1 if has_suffix else 0, len(n["id"]))

    return min(nodes, key=_score)


def _llm_tiebreak(
    candidates: list[dict],
    uf: _UF,
    communities: dict[str, int],
    *,
    backend: str,
    batch_size: int = 30,
    low: float = 75.0,
    high: float = 92.0,
) -> None:
    """Batch-resolve ambiguous pairs (score in [low, high)) via LLM."""
    try:
        from graphify.llm import BACKENDS, _format_backend_env_keys, _get_backend_api_key
        if backend not in BACKENDS:
            print(f"[graphify] --dedup-llm: unknown backend {backend!r}, skipping LLM tiebreaker.", flush=True)
            return
        if not _get_backend_api_key(backend):
            env_keys = _format_backend_env_keys(backend)
            print(f"[graphify] --dedup-llm: {env_keys} not set, skipping LLM tiebreaker.", flush=True)
            return
    except ImportError:
        return

    ambiguous: list[tuple[dict, dict, float]] = []
    for i, node in enumerate(candidates):
        norm_i = _norm(node.get("label", node.get("id", "")))
        for j in range(i + 1, len(candidates)):
            neighbor = candidates[j]
            if uf.find(node["id"]) == uf.find(neighbor["id"]):
                continue
            norm_j = _norm(neighbor.get("label", neighbor.get("id", "")))
            # Mirror pass 2: plain Jaro for cross-file long labels (#1243).
            _xfile = (node.get("source_file") or "") != (neighbor.get("source_file") or "")
            if _xfile and max(len(norm_i), len(norm_j)) >= 12:
                score = Jaro.normalized_similarity(norm_i, norm_j) * 100
            else:
                score = JaroWinkler.normalized_similarity(norm_i, norm_j) * 100
            if _is_variant_pair(norm_i, norm_j):
                continue
            if _short_label_blocked(norm_i, norm_j, score):
                continue
            _lo, _hi = sorted((norm_i, norm_j), key=len)
            if _hi.startswith(_lo) and _hi != _lo:
                continue
            # Mirror pass 2: decisively-distinct pairs never reach the LLM (#1284).
            if _numeric_tokens_differ(norm_i, norm_j):
                continue
            if _crossfile_fileanchored_blocked(node, neighbor):
                continue
            c1 = communities.get(node["id"])
            c2 = communities.get(neighbor["id"])
            if (c1 is not None and c2 is not None and c1 == c2
                    and min(len(norm_i), len(norm_j)) >= 12):
                score += _COMMUNITY_BOOST
            if low <= score < high:
                ambiguous.append((node, neighbor, score))

    if not ambiguous:
        return

    try:
        from graphify.llm import _call_llm
    except ImportError as exc:
        # F-038: previously this silent fallback hid the fact that `_call_llm`
        # didn't exist in `graphify.llm` at all, so `--dedup-llm` was a no-op.
        # Surface the import failure so future regressions are visible.
        print(
            f"[graphify] --dedup-llm: cannot import _call_llm ({exc}); skipping LLM tiebreaker.",
            flush=True,
        )
        return

    for batch_start in range(0, len(ambiguous), batch_size):
        batch = ambiguous[batch_start : batch_start + batch_size]
        pairs_text = "\n".join(
            f"{i+1}. \"{a['label']}\" vs \"{b['label']}\""
            for i, (a, b, _) in enumerate(batch)
        )
        prompt = (
            "For each pair below, answer only 'yes' or 'no': are they the same real-world concept?\n\n"
            f"{pairs_text}\n\n"
            "Reply with one line per pair: '1. yes', '2. no', etc."
        )
        try:
            response = _call_llm(prompt, backend=backend, max_tokens=200)
            lines = response.strip().splitlines()
            for line in lines:
                line = line.strip()
                if not line:
                    continue
                parts = line.split(".", 1)
                if len(parts) != 2:
                    continue
                try:
                    idx = int(parts[0].strip()) - 1
                except ValueError:
                    continue
                if 0 <= idx < len(batch):
                    answer = parts[1].strip().lower()
                    if answer.startswith("yes"):
                        a, b, _ = batch[idx]
                        winner = _pick_winner([a, b])
                        uf.union(winner["id"], a["id"])
                        uf.union(winner["id"], b["id"])
        except Exception as exc:
            print(f"[graphify] --dedup-llm batch failed: {exc}", flush=True)
