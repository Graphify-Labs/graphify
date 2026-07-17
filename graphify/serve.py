# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import math
import re
import sys
import weakref
from array import array
from pathlib import Path
from typing import Any, NamedTuple
from graphify.security import sanitize_label, validate_store_path
from graphify.build import edge_data, edge_datas
from graphify.helix.model import LoadedGraph, edge_attributes, graphify_attributes, node_attributes
from graphify.helix.persistence import DEFAULT_PROJECT_STORE, HelixGraphReader, load_graph

try:
    import jieba as _jieba  # type: ignore[import-untyped]
except ImportError:
    _jieba = None


def _load_graph(graph_path: str) -> LoadedGraph:
    try:
        return load_graph(validate_store_path(graph_path))
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except RuntimeError as exc:
        print(f"error: Helix store is corrupted ({exc}). Re-run /graphify to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: LoadedGraph) -> dict[int, list[str]]:
    """Read communities from the same durable Helix generation."""
    communities: dict[int, list[str]] = {}
    for record in G.state.get("communities", []):
        if isinstance(record, dict) and isinstance(record.get("id"), int):
            communities[record["id"]] = list(record.get("members", []))
    return communities


_RUNTIME_CACHES: weakref.WeakKeyDictionary[Any, dict[str, Any]] = weakref.WeakKeyDictionary()


def _runtime_cache(graph: Any) -> dict[str, Any]:
    """Generation-local derived indexes; never persisted or attached to topology."""
    return _RUNTIME_CACHES.setdefault(graph, {})


def _strip_diacritics(text: str | None) -> str:
    import unicodedata
    if not isinstance(text, str):
        text = "" if text is None else str(text)
    nfkd = unicodedata.normalize("NFKD", text)
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _search_tokens(text: str) -> list[str]:
    """Split text into word tokens, stripping punctuation and diacritics."""
    return re.findall(r"\w+", _strip_diacritics(str(text)).lower())


def _has_chinese(text: str) -> bool:
    return any("一" <= ch <= "鿿" for ch in text)


def _segment_chinese(text: str) -> list[str]:
    """Segment Chinese text and keep the original term for exact matching."""
    if _jieba is not None:
        segments = [w for w in _jieba.cut(text) if len(w.strip()) > 0]
    else:
        segments = [text[i:i + 2] for i in range(len(text) - 1)] or [text]
    if len(text) > 1 and text not in segments:
        segments.append(text)
    return segments


def _is_searchable(term: str) -> bool:
    """True if term is Chinese, non-English, or an English word longer than 2 chars."""
    if all("a" <= ch <= "z" for ch in term):
        return len(term) > 2
    return True


# Question/filler words dropped from query terms so content words drive BFS
# seeding. Without this, "how does the frontier cache work" seeds on "how"/
# "the"/"work" (which prefix-match prose labels like "Working Principles" at 100x)
# instead of "frontier"/"cache", and lands in the wrong part of the graph. Applied
# to query terms only — node text is never filtered, so a symbol literally named
# `work` stays findable via explain/path. `work`/`works`/`working` are included
# because "how does X work" / "how X works" is the most common question phrasing.
#
# Non-English question words are just as damaging (#1900): in a mostly-English
# code corpus, German "wie"/"funktioniert" are rare, so they get HIGH IDF weight
# and out-seed the actual content noun by orders of magnitude. So this also
# carries a curated German set plus a trimmed French/Spanish/Portuguese/Italian
# set of question/filler words. Diacritics are kept intact (the query tokenizer
# does not NFKD-strip).
#
# Collision tradeoff: a few foreign stopwords are also English content words.
# We include high-German-value ones like "die"/"hat" (the all-stopword fallback
# in _query_terms and the unfiltered find_node path keep an English "die"/"hat"
# query workable), but deliberately OMIT "war"/"bald" (German was/soon) so
# English queries about "war" or "bald" are not clobbered. On the Romance side
# we likewise omit "comment" (FR how), "come" (IT how), "son"/"sin"/"con" (ES),
# and "pour"/"des" (FR) — all too common as English/code terms.
_QUERY_STOPWORDS = frozenset({
    # English
    "how", "what", "why", "when", "where", "which", "who", "whom", "whose",
    "does", "did", "is", "are", "was", "were", "be", "been", "being",
    "can", "could", "should", "would", "will", "shall", "may", "might", "must",
    "has", "have", "had", "the", "and", "but", "not", "for", "from", "with",
    "without", "into", "onto", "off", "that", "this", "these", "those", "there",
    "here", "its", "their", "them", "they", "about", "any", "all", "some",
    "work", "works", "working",
    # German (articles/conjunctions/question words/auxiliaries/prepositions)
    "der", "die", "das", "den", "dem", "ein", "eine", "und", "oder", "nicht",
    "wie", "wer", "wann", "wo", "warum", "wieso",
    "welche", "welcher", "welches",
    "ist", "sind", "wird", "wurde", "hat", "haben",
    "kann", "koennen", "können", "soll", "muss", "sich",
    "bei", "mit", "von", "fuer", "für", "ueber", "über", "nach", "aus",
    "gibt", "es",
    "funktioniert", "geaendert", "geändert", "aendert", "ändert",
    # French
    "pourquoi", "quand", "quel", "quelle", "quels", "quelles", "quoi",
    "qui", "que", "est", "sont", "fonctionne", "cette", "dans", "avec", "où",
    # Spanish
    "cómo", "como", "qué", "cuál", "cuáles", "cuándo", "dónde", "donde",
    "porque", "por", "para", "funciona", "está", "están", "hay",
    # Portuguese
    "qual", "quais", "quando", "onde", "são", "estão", "tem", "uma", "não",
    # Italian
    "perché", "cosa", "quale", "quali", "dove", "funziona", "sono", "che",
    "della",
})


def _query_terms(question: str) -> list[str]:
    """Split a query into searchable terms, segmenting Chinese text, then drop
    question/filler words (`_QUERY_STOPWORDS`, English plus common German/
    Romance-language fillers) so content words drive seeding. Falls back to the
    unfiltered terms if the query is all stopwords, so a question like "how does
    it work" or "wie funktioniert das" still seeds on something."""
    terms: list[str] = []
    for raw in question.split():
        if _has_chinese(raw):
            for seg in _segment_chinese(raw.lower().strip()):
                seg = seg.strip()
                if seg and _is_searchable(seg):
                    terms.append(seg)
        else:
            # Strip punctuation without touching Unicode characters (avoid NFKD mangling non-Latin scripts)
            for tok in re.findall(r"\w+", raw.lower()):
                if _is_searchable(tok):
                    terms.append(tok)
    content = [t for t in terms if t not in _QUERY_STOPWORDS]
    return content or terms


_EXACT_MATCH_BONUS = 1000.0
_PREFIX_MATCH_BONUS = 100.0
_SUBSTRING_MATCH_BONUS = 1.0
_SOURCE_MATCH_BONUS = 0.5


def _compute_idf(G: Any, terms: list[str]) -> dict[str, float]:
    """IDF weights for query terms, cached for this native snapshot.

    Common terms like 'error' or 'exception' that match hundreds of nodes get
    low weights; rare identifiers like 'FooBarService' get high weights.
    Cache is stored on the graph object itself so it auto-invalidates when
    a hot-reload replaces G with a new object.
    """
    cache: dict[str, float] = _runtime_cache(G).setdefault("idf", {})
    N = G.node_count or 1
    uncached = [t for t in terms if t not in cache]
    if uncached:
        df: dict[str, int] = {t: 0 for t in uncached}
        for node in G.nodes():
            data = graphify_attributes(node.attributes)
            norm_label = (
                data.get("norm_label") or _strip_diacritics(data.get("label") or "")
            ).lower()
            for t in uncached:
                if t in norm_label:
                    df[t] += 1
        for t in uncached:
            cache[t] = math.log(1 + N / (1 + df[t]))
    return {t: cache.get(t, math.log(1 + N)) for t in terms}


def _trigrams(text: str) -> set[str]:
    """Character trigrams of `text`; for <3-char text the whole string is the key."""
    if len(text) < 3:
        return {text} if text else set()
    return {text[i:i + 3] for i in range(len(text) - 2)}


def _node_search_text(data: dict, nid: str) -> str:
    """Concatenate every field _score_nodes / _find_node match a query against, so
    one trigram index over this text is a complete candidate generator for both.

    - `norm_label` and `source_file` feed _score_nodes' per-term substring tiers.
    - `label_tokens` (the space-joined token form) feeds _find_node's
      `term in label_tokens` branch, where a multi-word `term` can span a token
      boundary that punctuation hides in `norm_label` (e.g. query "foo bar" matches
      label "foo.bar" only via its tokenized form).
    - `source_tokens` feeds _find_node's exact source-file path lookup, where a
      query like "app/api/example/route.ts" tokenizes to "app api example route ts".
    - `nid` feeds the whole-query `joined == nid_lower` tier.

    NUL separators stop a trigram from spanning two fields (a query never contains
    NUL, so a cross-field trigram can never be a real match).
    """
    norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
    label_tokens = " ".join(_search_tokens(data.get("label") or ""))
    source = (data.get("source_file") or "").lower()
    source_tokens = " ".join(_search_tokens(data.get("source_file") or ""))
    return "\x00".join((norm_label, label_tokens, str(nid).lower(), source, source_tokens))


def _get_trigram_index(G: Any) -> dict:
    """Lazily build and cache a trigram -> node-position postings map on the graph.

    Cached per native snapshot so it auto-invalidates when hot reload swaps in a
    fresh graph object, exactly like `_idf_cache`. `set_cache` memoizes per-trigram
    id-sets across queries within one graph generation.
    """
    cache = _runtime_cache(G)
    idx = cache.get("trigram_index")
    if idx is not None:
        return idx
    ids = [node.id for node in G.nodes()]
    postings: dict[str, array] = {}
    for i, nid in enumerate(ids):
        for g in _trigrams(_node_search_text(node_attributes(G, nid), str(nid))):
            bucket = postings.get(g)
            if bucket is None:
                bucket = array("i")
                postings[g] = bucket
            bucket.append(i)
    idx = {"ids": ids, "postings": postings, "set_cache": {}}
    cache["trigram_index"] = idx
    return idx


def _trigram_candidates(G: Any, needles: list[str], *, guard_frac: float = 0.10) -> list[str] | None:
    """Node IDs whose text could contain any `needle` as a substring, via the
    trigram index — a *superset* the caller then re-scores with the exact predicates.

    Returns candidates in graph-iteration order (so order-sensitive callers like
    _find_node stay byte-identical to a full scan), or **None** when the index isn't
    worth it — a needle is too short to trigram, or its rarest trigram is still
    common enough that the candidate set would approach the whole graph. The caller
    falls back to the full scan, preserving the never-worse contract. The guard is
    cheap: postings-length lookups only, no set intersection.
    """
    idx = _get_trigram_index(G)
    ids, postings, set_cache = idx["ids"], idx["postings"], idx["set_cache"]
    n = len(ids)
    if n == 0:
        return []
    needles = [s for s in needles if s]
    thresh = int(n * guard_frac)
    for s in needles:
        tgs = _trigrams(s)
        if not tgs or any(len(g) < 3 for g in tgs):
            return None  # too short to trigram-filter
        present = [len(postings[g]) for g in tgs if g in postings]
        if not present:
            continue  # this needle matches nothing — contributes no candidates
        if min(present) > thresh:
            return None  # rarest trigram still too common -> not worth the index
    cand: set[int] = set()
    for s in needles:
        sets: list[set] | None = []
        for g in _trigrams(s):
            bucket = postings.get(g)
            if bucket is None:
                sets = None  # a trigram absent everywhere -> needle matches nothing
                break
            cached = set_cache.get(g)
            if cached is None:
                cached = set(bucket)
                set_cache[g] = cached
            sets.append(cached)
        if not sets:
            continue
        sets.sort(key=len)  # intersect smallest-first
        hit = set(sets[0])
        for other in sets[1:]:
            hit &= other
            if not hit:
                break
        cand |= hit
    return [ids[i] for i in sorted(cand)]


class _QueryScores(NamedTuple):
    """Per-query scoring result, returned by the private `_score_query` helper.

    `ranked` is the existing ordered `(score, node_id)` ranking produced by the
    combined query scorer (the value `_score_nodes` always returned). When the
    caller asks for it via `collect_per_term_seeds=True`, `best_seed_by_term`
    additionally carries the winning node id for each normalized search token —
    the seed `_pick_seeds` would have picked for that token via the now-retired
    per-token `_score_nodes([token])` rescoring pass — computed in the *same*
    per-node traversal so the query path makes exactly one graph scoring pass
    regardless of query length. Empty when `collect_per_term_seeds=False`.
    """
    ranked: list[tuple[float, str]]
    best_seed_by_term: dict[str, str]


def _score_nodes(G: Any, terms: list[str]) -> list[tuple[float, str]]:
    """Combined query scorer returning the existing ranked `(score, node_id)` list.

    Backwards-compatible thin wrapper around `_score_query` for path, explain,
    tests, and every other caller that only needs the combined ranking. The
    per-term seed metadata computed by `_score_query` (when requested) is
    discarded here so existing callers see no API or runtime-cost change.
    """
    return _score_query(G, terms, collect_per_term_seeds=False).ranked


def _score_query(
    G: Any, terms: list[str], *, collect_per_term_seeds: bool
) -> _QueryScores:
    """Single-pass combined scorer that optionally also records the best seed
    for each normalized query token.

    The combined ranking is byte-identical to what `_score_nodes` produced
    before the refactor; `_score_nodes` is now a thin wrapper that asks for
    `collect_per_term_seeds=False` and returns only `.ranked`.

    When `collect_per_term_seeds=True`, the per-token singleton winner is
    computed alongside the combined score in the *same* per-node visit (it
    reuses the same `norm_label` / `label_tokens` / `source` already evaluated
    for the combined tier), so `_query_graph_text` can feed `best_seed_by_term`
    straight into `_pick_seeds` and skip the T additional whole-graph rescoring
    passes the old per-token `_score_nodes([token])` loop ran.

    Singleton-winner semantics match the legacy per-token path exactly. The
    score itself mirrors `_score_nodes([token])` with `n_terms == 1` (so the
    coverage term is 1 and the per-token tier is unscaled) plus the broader
    joined-singlet tier (which also checks `label_tokens` and `nid_lower`).
    Tie-break order is (1) highest singleton score, (2) highest graph degree,
    (3) shortest displayed label, (4) lexicographically smallest node id —
    exactly what `max(tied, key=degree)` over a sort by `(-score, label_len,
    nid)` produced in the legacy `_pick_seeds` per-token loop. The combined
    trigram candidate set (needles `norm_terms + [joined]`) is a superset of
    each per-token `[t]` candidate set, so iterating combined candidates
    discovers every non-zero singleton-score node for every term.
    """
    scored: list[tuple[float, str]] = []
    # Dedupe tokens, order-preserving (as _pick_seeds already does): a repeated
    # query word must not double-count every tier, and with coverage scaling
    # below it would also inflate the matched-term ratio (#1602).
    norm_terms = list(dict.fromkeys(tok for t in terms for tok in _search_tokens(t)))
    n_terms = len(norm_terms)
    idf = _compute_idf(G, norm_terms)
    # Whole-query string for full-label matching (mirrors _find_node's `term`).
    joined = " ".join(norm_terms)
    # Weight the full-query bonus by the rarest constituent term so a specific
    # multi-word label still outweighs common-token noise; floor at 1.0.
    joined_w = max((idf.get(t, 1.0) for t in norm_terms), default=1.0)
    # Trigram prefilter: score only nodes whose text could match a term, falling
    # back to the whole graph when the index isn't selective. The result is
    # identical either way — the per-node scoring below is unchanged and a
    # non-candidate node always scores 0. (IDF above stays a whole-graph statistic.)
    candidate_ids = _trigram_candidates(G, norm_terms + ([joined] if joined else []))
    node_iter = (
        ((node.id, graphify_attributes(node.attributes)) for node in G.nodes())
        if candidate_ids is None
        else ((nid, node_attributes(G, nid)) for nid in candidate_ids)
    )
    # Per-token best tracking, only when the caller (the query path) wants the
    # seed metadata. The key tuple is the full multi-key tie-break
    # (`(-singleton_score, -degree, label_len, nid)`), so `min` over the
    # stored key mirrors the legacy `max(tied, key=degree)` over a
    # (-score, label_len, nid)-sorted term_scored list. `None` is comparable
    # as "smaller" than every tuple, so the first non-zero candidate seeds the
    # entry without a separate `if t not in best_by_term` branch.
    best_by_term: dict[str, tuple[tuple, str]] | None = (
        {} if collect_per_term_seeds else None
    )
    for nid, data in node_iter:
        norm_label = data.get("norm_label") or _strip_diacritics(data.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        # Tokenized form of the label (punctuation stripped, same transform as the
        # query). norm_label may still carry punctuation like ':' or '-', which a
        # tokenized query can never equal; comparing token-joined forms on both
        # sides makes "uoce: dehumidifier driver" match query "uoce dehumidifier
        # driver".
        label_tokens = " ".join(_search_tokens(data.get("label") or ""))
        source = (data.get("source_file") or "").lower()
        # `nid_lower` is needed both by the full-query tier (`if joined`) and by
        # the per-token singleton tier (joined-singlet exact-match check). When
        # neither runs (`joined` empty AND not collecting seeds) skip the call;
        # this preserves the single-query-time perf where nid_lower was lazy.
        nid_lower = str(nid).lower() if (joined or collect_per_term_seeds) else ""
        score = 0.0
        # Full-query tier: a multi-word query that equals (or prefixes) the whole
        # label must dominate the per-token bag-of-words sums below, so `path`/
        # `query` resolve the same node `explain` does (via _find_node). Without
        # this, no single token equals a multi-word label, the per-token exact
        # tier never fires, and every node sharing the token set ties -> arbitrary
        # node-id sort -> wrong/disconnected endpoint -> false "No path found".
        if joined:
            if joined in (norm_label, bare_label, label_tokens, nid_lower):
                score += _EXACT_MATCH_BONUS * 10 * joined_w
            elif (
                norm_label.startswith(joined)
                or bare_label.startswith(joined)
                or label_tokens.startswith(joined)
            ):
                score += _PREFIX_MATCH_BONUS * 10 * joined_w
        # Term coverage (#1602): scale the per-term exact/prefix tiers by the
        # squared fraction of query terms the node's LABEL matches, so a lone
        # generic word that happens to equal a short label (query term "home"
        # vs. a home() leaf) cannot bury nodes that match several of the
        # query's terms. Squaring matters because the exact tier is 10x the
        # prefix tier: at linear coverage a 1-of-10-terms exact match still
        # outscores a 3-of-10 prefix+substring match. Single-term and
        # full-coverage queries are unchanged (coverage == 1), so identifier
        # lookups keep exact-match dominance. Source-file hits score but do
        # not count as coverage: a colliding leaf whose directory shares
        # tokens with the query (common near the intended target) must not
        # win back its exact tier via path fragments. The substring/source
        # bonuses and the full-query tier above stay unscaled.
        matched = 0
        tiered = 0.0
        for t in norm_terms:
            w = idf.get(t, 1.0)
            # Per-tier contributions for this token, kept separate so the
            # singleton tracking below can reuse them without re-evaluating
            # the same predicates. Three-tier precedence: exact > prefix >
            # substring (take the strongest tier per term so a single term
            # cannot double-count).
            tier_value = 0.0
            substr_value = 0.0
            source_value = 0.0
            if t == norm_label or t == bare_label:
                tier_value = _EXACT_MATCH_BONUS * w
                matched += 1
            elif norm_label.startswith(t) or bare_label.startswith(t):
                tier_value = _PREFIX_MATCH_BONUS * w
                matched += 1
            elif t in norm_label:
                substr_value = _SUBSTRING_MATCH_BONUS * w
                score += substr_value
                matched += 1
            if t in source:
                source_value = _SOURCE_MATCH_BONUS * w
                score += source_value
            tiered += tier_value
            if collect_per_term_seeds and best_by_term is not None:
                # Singleton score for [t] on this node, mirroring
                # `_score_nodes(G, [t])` exactly (n_terms == 1, no coverage
                # scaling). The joined-singlet tier is broader than the per-
                # token tier: it also checks `label_tokens` and `nid_lower`,
                # matching the legacy single-token `_score_nodes([t])` call
                # (where `joined == t`).
                if t in (norm_label, bare_label, label_tokens, nid_lower):
                    singleton = _EXACT_MATCH_BONUS * 10 * w
                elif (
                    norm_label.startswith(t)
                    or bare_label.startswith(t)
                    or label_tokens.startswith(t)
                ):
                    singleton = _PREFIX_MATCH_BONUS * 10 * w
                else:
                    singleton = 0.0
                singleton += tier_value + substr_value + source_value
                if singleton > 0:
                    # Tie-break key mirrors the legacy sort+max(degree):
                    # (-singleton, -degree, label_len, nid) — the minimum
                    # tuple wins, exactly matching max(tied, key=degree)
                    # over (label_len asc, nid asc)-sorted ties.
                    key = (-singleton, -G.degree(nid).degree, len(data.get("label") or str(nid)), str(nid))
                    cur = best_by_term.get(t)
                    if cur is None or key < cur[0]:
                        best_by_term[t] = (key, nid)
        if tiered:
            score += tiered * (matched / n_terms) ** 2
        if score > 0:
            scored.append((score, nid))
    # Sort by score desc; break ties toward the shorter label so a concise exact
    # match beats a longer superset that happens to share the same score.
    scored.sort(key=lambda s: (-s[0], len(node_attributes(G, s[1]).get("label") or str(s[1])), str(s[1])))
    best_seed_by_term: dict[str, str] = {}
    if collect_per_term_seeds and best_by_term:
        best_seed_by_term = {t: nid for t, (_key, nid) in best_by_term.items()}
    return _QueryScores(ranked=scored, best_seed_by_term=best_seed_by_term)


def _pick_scored_endpoint(G: Any, scored: list[tuple[float, str]], query: str) -> str:
    """Pick a path endpoint from a _score_nodes result, preferring full-token matches.

    The full-query tier in _score_nodes only fires when the query equals or
    prefixes a label, so a query that is a token *subset* of the intended label
    (query "Reject-everything judge" vs. label "Degenerate Reject-Everything
    Judge") gets no bonus, and a node prefix-matching one rare token (label
    "Rejection Summary") can out-score it on IDF alone. Committing to scored[0]
    then anchors the path on an unrelated — often disconnected — node and yields
    a false "No path found". Scan the score-ordered list and take the first
    candidate whose label contains EVERY query token; when the top candidate
    already full-matches, or no candidate does, this is exactly scored[0].

    `scored` must be non-empty (both callers return early on no match).
    """
    qtokens = set(_search_tokens(query))
    if not qtokens:
        return scored[0][1]
    for _score, nid in scored:
        if qtokens <= set(_search_tokens(node_attributes(G, nid).get("label") or str(nid))):
            return nid
    return scored[0][1]


def _pick_seeds(
    scored: list[tuple[float, str]],
    max_k: int = 3,
    gap_ratio: float = 0.2,
    *,
    G: Any | None = None,
    best_seed_by_term: dict[str, str] | None = None,
) -> list[str]:
    """Select BFS seed nodes, stopping when score drops too far below the top.

    Prevents high-frequency noise terms (error, exception) from stealing seed
    slots from a dominant identifier match. When FooBarService scores 1000 and
    error nodes score 1.0, only FooBarService is seeded — the score gap is 99.9%
    which is well above the 20% threshold that would allow additional seeds.

    That same gap_ratio cutoff has a failure mode on multi-term natural-language
    queries: if one term happens to hit an EXACT label match on a node that is
    otherwise unrelated to the query's intent (e.g. a common word that is also
    used as an unrelated identifier or field name elsewhere in the corpus), it
    can outscore every SUBSTRING match on the query's other, actually-relevant
    terms by ~1000x (see `_EXACT_MATCH_BONUS` vs. `_SUBSTRING_MATCH_BONUS`).
    The 20%-gap cutoff then silently discards all of those substring-tier
    seeds, so the BFS traversal only ever explores the neighborhood of the one
    unrelated exact match — see #1445.

    When `G` and `best_seed_by_term` are supplied, this guarantees at least one
    seed per distinct query term that has any match at all, so one term's
    incidental collision cannot starve out the others. The per-token winners
    in `best_seed_by_term` are precomputed by `_score_query` (during the same
    traversal that produced `scored`) so this function no longer rescores the
    graph per term — see #1445 and the `_score_query` docstring.

    Coverage scaling in _score_nodes (#1602) now dampens a lone collision's
    exact tier on multi-term queries, which brings label-matching relevant
    nodes back inside the gap window; this per-term guarantee remains
    load-bearing for relevant nodes matched only via substrings, whose flat
    scores a dampened collision can still exceed.
    """
    if not scored:
        return []

    # Deduplicate seeds by (normalized) label so a generic, homonymous symbol —
    # e.g. dozens of route handlers all labelled `GET`/`POST`, or a `handler`
    # repeated across a framework — contributes at most one seed instead of
    # consuming every slot and flooding the BFS with near-identical neighborhoods
    # (#1766). The key mirrors _score_nodes' normalization so `GET`/`Get`/`get`
    # collapse together. When G is absent we can't read labels, so fall back to
    # the (unique) node id, which is a no-op — preserving the old behavior.
    def _seed_label_key(nid: str) -> str:
        if G is None:
            return nid
        data = node_attributes(G, nid)
        return (data.get("norm_label")
                or _strip_diacritics(data.get("label") or "").lower()) or nid

    top_score = scored[0][0]
    seeds: list[str] = []
    seen_labels: set[str] = set()
    for score, nid in scored:
        if len(seeds) >= max_k:
            break
        if seeds and score < top_score * gap_ratio:
            break
        key = _seed_label_key(nid)
        if key in seen_labels:
            continue
        seen_labels.add(key)
        seeds.append(nid)

    if G is not None and best_seed_by_term:
        # Guarantee one seed per distinct query term that has any match at all,
        # so an incidental exact match on one term cannot starve matches on
        # other terms (#1445). Iterate tokens in a deterministic sorted order
        # so seeds added by this loop have a stable order independent of dict
        # iteration — preserving the legacy `_pick_seeds(terms=...)` behavior
        # which iterated `sorted({tok ...})`. Per-token winners arrive
        # precomputed in `best_seed_by_term` from `_score_query`'s single
        # traversal, so `_pick_seeds` no longer rescoring the graph per term.
        # The per-label dedup cap also gates these additions, so the guarantee
        # cannot reintroduce a second copy of an already-seeded generic label
        # (#1766).
        for term in sorted(best_seed_by_term):
            best_nid = best_seed_by_term[term]
            # Honor the same per-label cap so the per-term guarantee can't
            # reintroduce a second copy of an already-seeded generic label.
            key = _seed_label_key(best_nid)
            if best_nid not in seeds and key not in seen_labels:
                seen_labels.add(key)
                seeds.append(best_nid)
    return seeds


_CONTEXT_HINTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("call", ("call", "calls", "called", "invoke", "invokes", "invoked")),
    ("import", ("import", "imports", "imported", "module", "modules")),
    ("field", ("field", "fields", "member", "members", "property", "properties")),
    ("parameter_type", ("parameter", "parameters", "param", "params", "argument", "arguments")),
    ("return_type", ("return", "returns", "returned")),
    ("generic_arg", ("generic", "generics", "template", "templates")),
)


_CONTEXT_FILTER_ALIASES: dict[str, str] = {
    "param": "parameter_type",
    "params": "parameter_type",
    "parameter": "parameter_type",
    "parameters": "parameter_type",
    "argument": "parameter_type",
    "arguments": "parameter_type",
    "arg": "parameter_type",
    "args": "parameter_type",
    "return": "return_type",
    "returns": "return_type",
    "returned": "return_type",
    "generic": "generic_arg",
    "generics": "generic_arg",
    "template": "generic_arg",
    "templates": "generic_arg",
    "annotation": "attribute",
    "annotations": "attribute",
    "decorator": "attribute",
    "decorators": "attribute",
    "calls": "call",
    "called": "call",
    "invoke": "call",
    "invocation": "call",
    "fields": "field",
    "property": "field",
    "properties": "field",
    "member": "field",
    "members": "field",
    "imports": "import",
    "imported": "import",
    "module": "import",
    "modules": "import",
    "exports": "export",
    "exported": "export",
}


def _normalize_context_filters(filters: list[str] | None) -> list[str]:
    if not filters:
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in filters:
        key = _strip_diacritics(str(value)).strip().lower()
        if not key:
            continue
        key = _CONTEXT_FILTER_ALIASES.get(key, key)
        if key not in seen:
            seen.add(key)
            normalized.append(key)
    return normalized


def _infer_context_filters(question: str) -> list[str]:
    lowered = {
        _strip_diacritics(token).lower()
        for token in question.replace("?", " ").replace(",", " ").split()
    }
    inferred: list[str] = []
    for context, hints in _CONTEXT_HINTS:
        if any(hint in lowered for hint in hints):
            inferred.append(context)
    return inferred


def _resolve_context_filters(question: str, explicit_filters: list[str] | None = None) -> tuple[list[str], str | None]:
    normalized = _normalize_context_filters(explicit_filters)
    if normalized:
        return normalized, "explicit"
    inferred = _infer_context_filters(question)
    if inferred:
        return inferred, "heuristic"
    return [], None


def _filter_graph_by_context(G: Any, context_filters: list[str] | None) -> tuple[Any, set[str]]:
    """Return the native snapshot plus normalized traversal edge filters."""
    return G, set(_normalize_context_filters(context_filters))


def _traverse(
    G: Any,
    start_nodes: list[str],
    depth: int,
    *,
    strategy: str,
    context_filters: set[str] | None = None,
) -> tuple[set[str], list[Any]]:
    # Compute hub threshold: nodes above this degree are not expanded as transit.
    # p99 of degree distribution, floored at 50 to avoid over-blocking small graphs.
    degrees = [int(row.degree) for row in G.degrees()]
    if degrees:
        degrees_sorted = sorted(degrees)
        p99_idx = int(len(degrees_sorted) * 0.99)
        hub_threshold = max(50, degrees_sorted[p99_idx])
    else:
        hub_threshold = 50
    if not context_filters:
        from helixdb import TraversalOptions

        result = G.traverse(TraversalOptions(
            seeds=tuple(start_nodes),
            max_depth=depth,
            strategy=strategy,
            direction="both",
            stop_non_seed_at_or_above_degree=hub_threshold,
        ))
        return (
            {visit.node_id for visit in result.visits},
            [G.edge(item.edge_id) for item in result.discovery_edges if G.edge(item.edge_id) is not None],
        )

    seeds = set(start_nodes)
    visited: set[Any] = set()
    edges_seen: list[Any] = []
    pending = [(node, 0) for node in start_nodes]
    while pending:
        node, level = pending.pop(0 if strategy == "breadth_first" else -1)
        if node in visited or level > depth:
            continue
        visited.add(node)
        if level == depth or (node not in seeds and G.degree(node).degree >= hub_threshold):
            continue
        for edge_id in G.incident_edge_ids(node):
            edge = G.edge(edge_id)
            if edge is None or edge_attributes(edge).get("context") not in context_filters:
                continue
            neighbor = edge.target if edge.source == node else edge.source
            if neighbor not in visited:
                edges_seen.append(edge)
                pending.append((neighbor, level + 1))
    return visited, edges_seen


def _bfs(G: Any, start_nodes: list[str], depth: int, context_filters: set[str] | None = None):
    return _traverse(G, start_nodes, depth, strategy="breadth_first", context_filters=context_filters)


def _dfs(G: Any, start_nodes: list[str], depth: int, context_filters: set[str] | None = None):
    return _traverse(G, start_nodes, depth, strategy="depth_first", context_filters=context_filters)


def _subgraph_to_text(G: Any, nodes: set[str], edges: list[Any], token_budget: int = 2000, *, seeds: list[str] | None = None) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token).

    seeds: exact-match nodes rendered first before the degree-sorted expansion,
    so the queried symbol always appears at the top of the output.
    """
    char_budget = token_budget * 3
    lines = []
    # Work-memory overlay (derived sidecar) stashed on the graph at load time.
    # Empty when no sidecar exists, so un-annotated output stays byte-identical.
    overlay = _runtime_cache(G).get("learning_overlay", {}) or {}
    seed_set = set(seeds or [])
    seed_hits = [n for n in (seeds or []) if n in nodes]
    # Rank non-seed nodes by hop distance from the seeds so the node that answers
    # the query (a direct hit or its close neighbors) survives the budget cut
    # instead of being pushed past it by incidental high-degree hubs (#BUG2). BFS
    # discovery order was discarded upstream (_bfs returns a set), so recompute
    # layers here over BOTH edge directions. Deterministic: neighbor iteration is
    # insertion-ordered and the sort key ends in str(n) (no hash-order).
    def _adj(n):
        if G.directed:
            yield from G.successors(n)
            yield from G.predecessors(n)
        else:
            yield from G.neighbors(n)
    dist: dict[str, int] = {n: 0 for n in seed_hits}
    frontier, hop = seed_hits, 0
    while frontier:
        hop += 1
        nxt = []
        for n in frontier:
            for nb in _adj(n):
                if nb in nodes and nb not in dist:
                    dist[nb] = hop
                    nxt.append(nb)
        frontier = nxt
    ordered = seed_hits + sorted(
        nodes - seed_set,
        key=lambda n: (dist.get(n, 1 << 30), -G.degree(n).degree, str(n)),
    )
    for nid in ordered:
        d = node_attributes(G, nid)
        # Every LLM-derived field passes through sanitize_label before being
        # concatenated into MCP tool output (F-010): an attacker who controls a
        # corpus document can otherwise inject ANSI escapes, fake graphify-out
        # log lines, or prompt-injection markup into the model's context via
        # source_file / source_location / community.
        # The learning= suffix is appended INSIDE the bracket and BEFORE the
        # budget check below, so it counts in char_budget accounting.
        entry = overlay.get(str(nid))
        learning_suffix = ""
        if entry:
            status = sanitize_label(str(entry.get("status", "")))
            if status:
                learning_suffix = f" learning={status}{':stale' if entry.get('stale') else ''}"
        line = (
            f"NODE {sanitize_label(d.get('label', nid))} "
            f"[src={sanitize_label(str(d.get('source_file', '')))} "
            f"loc={sanitize_label(str(d.get('source_location', '')))} "
            f"community={sanitize_label(str(d.get('community_name') or d.get('community', '')))}"
            f"{learning_suffix}]"
        )
        lines.append(line)
    for traversed in edges:
        u, v = traversed.source, traversed.target
        if u in nodes and v in nodes:
            d = edge_attributes(traversed)
            context = d.get("context")
            context_suffix = f" context={sanitize_label(str(context))}" if context else ""
            # The relation SITE (call/import/reference line in the source's
            # file), not a def line — so "who calls X" cites a clickable call
            # location, not the caller's def (#BUG1).
            _loc = str(d.get("source_location") or "")
            at_suffix = (
                f" at={sanitize_label(str(d.get('source_file') or ''))}:{sanitize_label(_loc)}"
                if _loc else ""
            )
            line = (
                f"EDGE {sanitize_label(node_attributes(G, u).get('label', u))} "
                f"--{sanitize_label(str(d.get('relation', '')))} "
                f"[{sanitize_label(str(d.get('confidence', '')))}{context_suffix}]--> "
                f"{sanitize_label(node_attributes(G, v).get('label', v))}{at_suffix}"
            )
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        cut_at = output[:char_budget].rfind("\n")
        cut_at = cut_at if cut_at > 0 else char_budget
        # Never cut the seed nodes: they render first, so if the budget lands
        # inside the seed block, extend the cut to cover it. The symbol the
        # question named must always be in the answer (#BUG2). Seeds are bounded
        # (_pick_seeds max_k + one per term), so the overshoot is a few lines.
        if seed_hits:
            seed_block_end = sum(len(lines[i]) + 1 for i in range(len(seed_hits))) - 1
            cut_at = max(cut_at, min(seed_block_end, len(output)))
        total_nodes = sum(1 for l in lines if l.startswith("NODE "))
        shown_nodes = output[:cut_at].count("\nNODE ") + (1 if output.startswith("NODE ") else 0)
        cut_count = total_nodes - shown_nodes
        # Prominent notice at the TOP so a truncated answer can never be mistaken
        # for a complete one — silence used to read as absence (#BUG2). The
        # notice + end marker sit OUTSIDE char_budget by design (two bounded
        # wrapper lines, like the existing end marker).
        output = (
            f"[!] TRUNCATED: showing {shown_nodes} of {total_nodes} nodes "
            f"(~{token_budget}-token budget). The answer may be among the "
            f"{cut_count} cut nodes — raise the token budget (CLI: --budget) or "
            f"narrow the query (e.g. context_filter=['call'], or get_node for a "
            f"specific symbol).\n\n"
            + output[:cut_at]
            + f"\n... (truncated — {cut_count} more nodes cut by ~{token_budget}-token budget."
            f" Narrow with context_filter=['call'] or use get_node for a specific symbol)"
        )
    return output


def _cut_lines_to_budget(lines: list[str], token_budget: int, narrow_hint: str) -> str:
    """Render pre-built lines under the same ~3-chars/token budget rule as
    _subgraph_to_text; over-budget output is cut at a line boundary with a count and a
    narrowing hint instead of flooding the caller's context window."""
    output = "\n".join(lines)
    char_budget = token_budget * 3
    if len(output) <= char_budget:
        return output
    cut_at = output[:char_budget].rfind("\n")
    cut_at = cut_at if cut_at > 0 else char_budget
    kept = output[:cut_at]
    shown = kept.count("\n") + 1
    cut_count = len(lines) - shown
    # Announce truncation at the TOP as well, matching _subgraph_to_text — a
    # bottom-only marker reads as silence/absence (the BUG-2 fix rationale). The
    # notice sits outside char_budget by design (one bounded wrapper line).
    return (
        f"[!] TRUNCATED: showing {shown} of {len(lines)} lines "
        f"(~{token_budget}-token budget). {narrow_hint}\n\n"
        + kept
        + f"\n... (truncated — {cut_count} more lines cut by ~{token_budget}-token budget. "
        + narrow_hint
        + ")"
    )


def _query_graph_text(
    G: Any,
    question: str,
    *,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
    context_filters: list[str] | None = None,
) -> str:
    terms = _query_terms(question)
    # One graph scoring pass produces both the combined ranking (used to drive
    # the gap-based seed selection below) and the per-token singleton winners
    # (used by _pick_seeds' per-term guarantee). Previously this was T+1 passes
    # — one combined + one per query token — re-walking the whole graph each
    # time; on a 100k-node, three-term benchmark ~71% of scoring time was
    # spent in those redundant per-term passes.
    qs = _score_query(G, terms, collect_per_term_seeds=True)
    start_nodes = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    if not start_nodes:
        return "No matching nodes found."
    resolved_filters, filter_source = _resolve_context_filters(question, context_filters)
    traversal_graph, edge_filters = _filter_graph_by_context(G, resolved_filters)
    nodes, edges = (
        _dfs(traversal_graph, start_nodes, depth, edge_filters)
        if mode == "dfs"
        else _bfs(traversal_graph, start_nodes, depth, edge_filters)
    )
    header_parts = [
        f"Traversal: {mode.upper()} depth={depth}",
        f"Start: {[node_attributes(G, n).get('label', n) for n in start_nodes]}",
    ]
    if resolved_filters:
        header_parts.append(f"Context: {', '.join(resolved_filters)} ({filter_source})")
    header_parts.append(f"{len(nodes)} nodes found")
    header = " | ".join(header_parts) + "\n\n"
    # Pass the seeds so the queried symbol renders first and survives truncation
    # (#BUG2): a branch merge had silently dropped this argument, leaving the
    # seed-first ordering as dead code.
    return header + _subgraph_to_text(traversal_graph, nodes, edges, token_budget, seeds=start_nodes)


def _find_node(G: Any, label: str) -> list[str]:
    """Return node IDs whose label or ID matches the search term (diacritic-insensitive).

    Results are ordered by precedence: exact source-file path match first, then
    exact (label/ID) match, then prefix match, then substring match. Node-ID exact
    matches are grouped with label exact matches.
    """
    term = " ".join(_search_tokens(label))
    if not term:
        return []
    # Punctuation-preserving normalized query. `term` tokenizes on \w+ (so
    # "blockStream.ts" -> "blockstream ts", space where the '.' was), but a node's
    # stored `norm_label` keeps punctuation ("blockstream.ts"). Matching only via
    # `term`/`label_tokens` works when the node label tokenizes the same way, but is
    # fragile if `label` and `norm_label` diverge. `norm_query` matches `norm_label`
    # symmetrically so an exactly-typed punctuated label always resolves (#1704).
    norm_query = _strip_diacritics(str(label)).lower().strip()
    source_exact: list[str] = []
    exact: list[str] = []
    prefix: list[str] = []
    substring: list[str] = []
    # Trigram prefilter (graph-iteration order preserved so exact/prefix/substring
    # ordering — and thus matches[0] — is byte-identical to the full scan).
    candidate_ids = _trigram_candidates(G, [term, norm_query])
    node_iter = (
        ((node.id, graphify_attributes(node.attributes)) for node in G.nodes())
        if candidate_ids is None
        else ((nid, node_attributes(G, nid)) for nid in candidate_ids)
    )
    for nid, d in node_iter:
        norm_label = d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        label_tokens = " ".join(_search_tokens(d.get("label") or ""))
        source_tokens = " ".join(_search_tokens(d.get("source_file") or ""))
        nid_lower = str(nid).lower()
        if term == source_tokens:
            source_exact.append(nid)
        elif (
            term == norm_label or term == bare_label or term == label_tokens or term == nid_lower
            or norm_query == norm_label or norm_query == bare_label
        ):
            exact.append(nid)
        elif (
            norm_label.startswith(term)
            or bare_label.startswith(term)
            or label_tokens.startswith(term)
            or nid_lower.startswith(term)
            or norm_label.startswith(norm_query)
            or bare_label.startswith(norm_query)
        ):
            prefix.append(nid)
        elif term in norm_label or term in label_tokens or norm_query in norm_label:
            substring.append(nid)

    if source_exact:
        query_basename = _strip_diacritics(Path(label).name).lower()
        preferred = []
        for nid in source_exact:
            attrs = node_attributes(G, nid)
            if str(attrs.get("source_location", "")) != "L1":
                continue
            # File-node label is the bare basename OR a directory-qualified form
            # from the #2032 disambiguation pass (e.g. "process-order/index.ts").
            lbl = _strip_diacritics(str(attrs.get("label") or "")).lower()
            if lbl == query_basename or lbl.endswith("/" + query_basename):
                preferred.append(nid)
        if len(preferred) == 1:
            source_exact = preferred + [nid for nid in source_exact if nid != preferred[0]]

    return source_exact + exact + prefix + substring


def _filter_blank_stdin() -> None:
    """Filter blank lines from stdin before MCP reads it.

    Some MCP clients (Claude Desktop, etc.) send blank lines between JSON
    messages. The MCP stdio transport tries to parse every line as a
    JSONRPCMessage, so a bare newline triggers a Pydantic ValidationError.
    This installs an OS-level pipe that relays stdin while dropping blanks.
    """
    import os
    import threading

    r_fd, w_fd = os.pipe()
    saved_fd = os.dup(sys.stdin.fileno())

    def _relay() -> None:
        try:
            with open(saved_fd, "rb") as src, open(w_fd, "wb") as dst:
                for line in src:
                    if line.strip():
                        dst.write(line)
                        dst.flush()
        except Exception:
            pass

    threading.Thread(target=_relay, daemon=True).start()
    os.dup2(r_fd, sys.stdin.fileno())
    os.close(r_fd)
    sys.stdin = open(0, "r", closefd=False)


def _community_header(cid: int, community_name) -> str:
    # Header for get_community: "Community N — Name", matching get_node / query
    # output which reads community names from native generation state.
    # Skip the name when it is just the "Community N" placeholder (written for
    # unnamed communities) so the header never reads "Community 12 — Community 12";
    # also falls back to the bare id when there is no name. Name is sanitised
    # (F-010) like every other LLM-derived field.
    base = f"Community {cid}"
    if community_name:
        clean = sanitize_label(str(community_name))
        if clean and clean != base:
            return f"{base} — {clean}"
    return base


def _build_server(graph_path: str):
    """Build the configured low-level MCP Server (shared by every transport).

    All graph query tools and resources are registered here over a single
    ``mcp.server.Server`` instance; the caller picks the transport (stdio or
    Streamable HTTP) and runs it. Helix generation hot reload works the same way
    regardless of transport, since reloads happen inside the tool handlers.
    """
    import threading

    try:
        from mcp.server import Server
        from mcp import types
        from mcp.types import AnyUrl
    except ImportError as e:
        raise ImportError('mcp not installed. Run: pip install "graphifyy[mcp]"') from e

    from graphify import paths as _paths

    # Per-store context cache: resolved store path -> reader and active generation.
    # The server's default graph is just the first entry; a tool call carrying a
    # project_path adds its own. Routing every graph through one cache means the
    # eager trigram index and the mtime+size hot-reload behave identically for
    # the default graph and for any project graph.
    _default_graph_path = graph_path
    _ctx_lock = threading.Lock()
    _tool_lock = threading.Lock()
    _ctx_cache: dict[str, dict] = {}

    def _load_ctx(path: str):
        """Return the current native graph and communities for a Helix store."""
        with _ctx_lock:
            ent = _ctx_cache.get(path)
            if ent is None:
                ent = {"reader": HelixGraphReader(validate_store_path(path))}
                _ctx_cache[path] = ent
            loaded = ent["reader"].get()
            if ent.get("generation") == loaded.generation:
                return ent["G"], ent["communities"]
            new_G = loaded.graph
            # Warm the trigram index before exposing the graph so the first query
            # against it is fast (same rationale as the original startup warm-up).
            _get_trigram_index(new_G)
            learning = loaded.state.get("learning", {})
            _runtime_cache(new_G)["learning_overlay"] = (
                dict(learning.get("nodes", {})) if isinstance(learning, dict) else {}
            )
            _runtime_cache(new_G)["community_labels"] = {
                int(record["id"]): str(record.get("name") or f"Community {record['id']}")
                for record in loaded.state.get("communities", [])
                if isinstance(record, dict) and isinstance(record.get("id"), int)
            }
            comm = _communities_from_graph(loaded)
            ent.update({"generation": loaded.generation, "G": new_G, "communities": comm})
            return new_G, comm

    def _resolve_graph_path(project_path) -> str:
        """Map an optional project_path to a concrete Helix store. ``None``
        keeps the server's default graph (backward-compatible); a project_path
        resolves to ``<project_path>/<GRAPHIFY_OUT>/graph.helix``, honouring the
        GRAPHIFY_OUT override so worktree/shared-output setups keep working."""
        if not project_path:
            return _default_graph_path
        candidate = Path(project_path)
        if candidate.name == "graph.helix":
            return str(candidate)
        return str(candidate / _paths.GRAPHIFY_OUT / "graph.helix")

    # Active per-request context, rebound by _select_graph() and read by the tool
    # handlers below. No lock needed on the hot path: _select_graph and the
    # handler run in one synchronous stretch of each call_tool coroutine (no
    # await between them), so a concurrent call never observes a half-applied
    # swap.
    active_graph_path = _default_graph_path
    try:
        G, communities = _load_ctx(_default_graph_path)
    except (FileNotFoundError, RuntimeError):
        # No default graph at startup → run as a pure multi-project server. Tools
        # then require project_path; a call without one gets a clear error rather
        # than the process refusing to start (which is what _load_graph would do).
        G, communities = None, {}

    def _select_graph(project_path) -> None:
        nonlocal G, communities, active_graph_path
        path = _resolve_graph_path(project_path)
        G, communities = _load_ctx(path)
        active_graph_path = path

    server = Server("graphify")

    @server.list_tools()
    async def list_tools() -> list[types.Tool]:
        _tools = [
            types.Tool(
                name="query_graph",
                description="Search the knowledge graph using BFS or DFS. Returns relevant nodes and edges as text context.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "question": {"type": "string", "description": "Natural language question or keyword search"},
                        "mode": {"type": "string", "enum": ["bfs", "dfs"], "default": "bfs",
                                 "description": "bfs=broad context, dfs=trace a specific path"},
                        "depth": {"type": "integer", "default": 3, "description": "Traversal depth (1-6)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                        "context_filter": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Optional explicit edge-context filter, e.g. ['call', 'field']",
                        },
                    },
                    "required": ["question"],
                },
            ),
            types.Tool(
                name="get_node",
                description="Get full details for a specific node by label or ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"label": {"type": "string", "description": "Node label or ID to look up"}},
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_neighbors",
                description="Get all direct neighbors of a node with edge details.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "label": {"type": "string"},
                        "relation_filter": {"type": "string", "description": "Optional: filter by relation type"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"},
                        "token_budget": {"type": "integer", "default": 2000, "description": "Max output tokens"},
                    },
                    "required": ["community_id"],
                },
            ),
            types.Tool(
                name="god_nodes",
                description="Return the most connected nodes - the core abstractions of the knowledge graph.",
                inputSchema={"type": "object", "properties": {"top_n": {"type": "integer", "default": 10}}},
            ),
            types.Tool(
                name="graph_stats",
                description="Return summary statistics: node count, edge count, communities, confidence breakdown.",
                inputSchema={"type": "object", "properties": {}},
            ),
            types.Tool(
                name="shortest_path",
                description="Find the shortest path between two concepts in the knowledge graph.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "source": {"type": "string", "description": "Source concept label or keyword"},
                        "target": {"type": "string", "description": "Target concept label or keyword"},
                        "max_hops": {"type": "integer", "default": 8, "description": "Maximum hops to consider"},
                    },
                    "required": ["source", "target"],
                },
            ),
            types.Tool(
                name="list_prs",
                description=(
                    "List open GitHub PRs with CI status, review state, and graph impact "
                    "(which communities each PR touches, blast radius). Use this before starting "
                    "work to check if a PR already covers the area you're about to change."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "base": {"type": "string", "description": "Base branch to filter PRs by (auto-detected if omitted)"},
                        "repo": {"type": "string", "description": "GitHub repo (owner/repo). Defaults to current repo."},
                    },
                },
            ),
            types.Tool(
                name="get_pr_impact",
                description=(
                    "Get detailed graph impact for a specific PR: which files it changes, "
                    "which knowledge-graph communities are affected, and how many nodes are touched. "
                    "Use this to assess merge risk or check for overlap with your current work."
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "pr_number": {"type": "integer", "description": "PR number to analyse"},
                        "repo": {"type": "string", "description": "GitHub repo (owner/repo). Defaults to current repo."},
                    },
                    "required": ["pr_number"],
                },
            ),
            types.Tool(
                name="triage_prs",
                description=(
                    "Return all actionable open PRs (correct base, not stale) with full graph impact data "
                    "so you can reason about review priority, merge order, and conflict risk. "
                    "Call this when the user asks 'what PRs should I review?' or 'what's ready to merge?'"
                ),
                inputSchema={
                    "type": "object",
                    "properties": {
                        "base": {"type": "string", "description": "Base branch to filter PRs by (auto-detected if omitted)"},
                        "repo": {"type": "string", "description": "GitHub repo (owner/repo). Defaults to current repo."},
                    },
                },
            ),
        ]
        # Multi-project support: every tool accepts an optional project_path.
        # Injected here (rather than repeated in 11 literal schemas) so the set
        # stays in lockstep as tools are added. Omitting it keeps the historical
        # single-graph behaviour, so this is purely additive for existing callers.
        for _t in _tools:
            _t.inputSchema.setdefault("properties", {})["project_path"] = {
                "type": "string",
                "description": (
                    "Absolute path to a project directory containing "
                    "graphify-out/graph.helix. Optional — defaults to the graph "
                    "this server was started with."
                ),
            }
        return _tools

    def _tool_query_graph(arguments: dict) -> str:
        import time as _time
        from graphify import querylog
        question = arguments["question"]
        mode = arguments.get("mode", "bfs")
        depth = min(int(arguments.get("depth", 3)), 6)
        budget = int(arguments.get("token_budget", 2000))
        context_filter = arguments.get("context_filter")
        _t0 = _time.perf_counter()
        result = _query_graph_text(
            G,
            question,
            mode=mode,
            depth=depth,
            token_budget=budget,
            context_filters=context_filter,
        )
        querylog.log_query(
            kind="mcp_query",
            question=question,
            corpus=str(active_graph_path),
            result=result,
            mode=mode,
            depth=depth,
            token_budget=budget,
            duration_ms=(_time.perf_counter() - _t0) * 1000,
        )
        return result

    def _tool_get_node(arguments: dict) -> str:
        label = arguments["label"].lower()
        matches = [
            (node.id, graphify_attributes(node.attributes)) for node in G.nodes()
            if label in str(graphify_attributes(node.attributes).get("label") or "").lower()
            or label == str(node.id).lower()
        ]
        if not matches:
            return f"No node matching '{label}' found."
        nid, d = matches[0]
        # Sanitise every LLM-derived field before concatenation (F-010).
        return "\n".join([
            f"Node: {sanitize_label(d.get('label', nid))}",
            f"  ID: {sanitize_label(str(nid))}",
            f"  Source: {sanitize_label(str(d.get('source_file', '')))} {sanitize_label(str(d.get('source_location', '')))}",
            f"  Type: {sanitize_label(str(d.get('file_type', '')))}",
            f"  Community: {sanitize_label(str(d.get('community_name') or d.get('community', '')))}",
            f"  Degree: {G.degree(nid).degree}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"].lower()
        rel_filter = arguments.get("relation_filter", "").lower()
        matches = _find_node(G, label)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {sanitize_label(node_attributes(G, nid).get('label', nid))}:"]
        def _edge_at(d: dict) -> str:
            # Edge location = the relation SITE (call/import line) in the source
            # node's file, not a def line (#BUG1).
            loc = str(d.get("source_location") or "")
            return (
                f" at={sanitize_label(str(d.get('source_file') or ''))}:{sanitize_label(loc)}"
                if loc else ""
            )
        for nb in G.successors(nid):
            d = edge_data(G, nid, nb)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in str(rel).lower():
                continue
            lines.append(
                f"  --> {sanitize_label(node_attributes(G, nb).get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]{_edge_at(d)}"
            )
        for nb in G.predecessors(nid):
            d = edge_data(G, nb, nid)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(
                f"  <-- {sanitize_label(node_attributes(G, nb).get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]{_edge_at(d)}"
            )
        budget = int(arguments.get("token_budget", 2000))
        return _cut_lines_to_budget(
            lines, budget, "Narrow with relation_filter or use get_node for a specific symbol"
        )

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        header = _community_header(cid, node_attributes(G, nodes[0]).get("community_name"))
        lines = [f"{header} ({len(nodes)} nodes):"]
        for n in nodes:
            d = node_attributes(G, n)
            # Sanitise label and source_file (F-010).
            lines.append(
                f"  {sanitize_label(d.get('label', n))} "
                f"[{sanitize_label(str(d.get('source_file', '')))}]"
            )
        budget = int(arguments.get("token_budget", 2000))
        return _cut_lines_to_budget(
            lines, budget, "Raise token_budget or use get_node for specific members"
        )

    def _tool_god_nodes(arguments: dict) -> str:
        from graphify.analyze import god_nodes as _god_nodes
        nodes = _god_nodes(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['degree']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        confs = [
            graphify_attributes(edge.attributes).get("confidence", "EXTRACTED")
            for edge in G.edges()
        ]
        total = len(confs) or 1
        return (
            f"Nodes: {G.node_count}\n"
            f"Edges: {G.edge_count}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(G, [t.lower() for t in arguments["source"].split()])
        tgt_scored = _score_nodes(G, [t.lower() for t in arguments["target"].split()])
        if not src_scored:
            return f"No node matching source '{arguments['source']}' found."
        if not tgt_scored:
            return f"No node matching target '{arguments['target']}' found."
        src_nid = _pick_scored_endpoint(G, src_scored, arguments["source"])
        tgt_nid = _pick_scored_endpoint(G, tgt_scored, arguments["target"])
        # Ambiguity guard: when both queries resolve to the same node, the
        # shortest path is trivially zero hops, which is almost never what the
        # caller wanted (see bug #828).
        if src_nid == tgt_nid:
            return (
                f"'{arguments['source']}' and '{arguments['target']}' both resolved to "
                f"the same node '{src_nid}'. Use a more specific label or the exact node ID."
            )
        warnings: list[str] = []
        for name, scored, nid in (
            ("source", src_scored, src_nid),
            ("target", tgt_scored, tgt_nid),
        ):
            # Only meaningful when the raw score head is what got picked — a
            # full-token override was chosen on token coverage, not score.
            if len(scored) >= 2 and nid == scored[0][1]:
                top, runner = scored[0][0], scored[1][0]
                if top > 0 and (top - runner) / top < 0.10:
                    warnings.append(
                        f"warning: {name} match was ambiguous "
                        f"(top score {top:g}, runner-up {runner:g})"
                    )
        max_hops = int(arguments.get("max_hops", 8))
        try:
            # Use undirected view for path-finding (works regardless of query src/tgt order)
            path_result = G.shortest_path(src_nid, tgt_nid, direction="both")
            path_nodes = list(path_result.node_ids)
            if not path_nodes:
                raise ValueError("no path")
        except (KeyError, ValueError, RuntimeError):
            return f"No path found between '{node_attributes(G, src_nid).get('label', src_nid)}' and '{node_attributes(G, tgt_nid).get('label', tgt_nid)}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            # Report the actual stored relation(s), never a fabricated `calls`;
            # fall back to an honest "related" when the edge has no relation (#2074).
            if G.has_edge_between(u, v):
                datas = edge_datas(G, u, v)
                forward = True
            else:
                datas = edge_datas(G, v, u)
                forward = False
            rels = sorted({d.get("relation") for d in datas if d.get("relation")})
            rel = "/".join(rels) if rels else "related"
            confs = sorted({d.get("confidence") for d in datas if d.get("confidence")})
            conf_str = f" [{'/'.join(confs)}]" if confs else ""
            if i == 0:
                segments.append(node_attributes(G, u).get("label", u))
            if forward:
                segments.append(f"--{rel}{conf_str}--> {node_attributes(G, v).get('label', v)}")
            else:
                segments.append(f"<--{rel}{conf_str}-- {node_attributes(G, v).get('label', v)}")
        prefix = ("\n".join(warnings) + "\n") if warnings else ""
        return prefix + f"Shortest path ({hops} hops):\n  " + " ".join(segments)

    def _tool_list_prs(arguments: dict) -> str:
        from graphify.prs import fetch_prs, fetch_worktrees, format_prs_text, _detect_default_branch
        repo = arguments.get("repo") or None
        base = arguments.get("base") or _detect_default_branch(repo)
        try:
            prs = fetch_prs(repo=repo, base=base)
        except RuntimeError as e:
            return f"Error: {e}"
        worktrees = fetch_worktrees()
        for pr in prs:
            pr.worktree_path = worktrees.get(pr.branch)
        return format_prs_text(prs, base)

    def _tool_get_pr_impact(arguments: dict) -> str:
        from graphify.prs import fetch_pr_files, compute_pr_impact, _gh, _parse_ci
        number = int(arguments["pr_number"])
        repo = arguments.get("repo") or None
        # Use gh pr view directly — works for any base branch, not just the default
        view_args = ["pr", "view", str(number), "--json",
                     "title,headRefName,baseRefName,author,isDraft,reviewDecision,statusCheckRollup,updatedAt"]
        if repo:
            view_args += ["--repo", repo]
        pr_data = _gh(*view_args)
        if pr_data is None:
            return f"PR #{number} not found or gh not authenticated."
        files = fetch_pr_files(number, repo)
        if not files:
            return f"PR #{number}: no changed files found (may require gh auth)."
        comms, nodes = compute_pr_impact(files, G, communities)
        ci = _parse_ci(pr_data.get("statusCheckRollup") or [])
        lines = [
            f"PR #{number}: {pr_data['title']}",
            f"CI: {ci}  Review: {pr_data.get('reviewDecision') or 'none'}",
            f"Base: {pr_data['baseRefName']}  Author: {(pr_data.get('author') or {}).get('login', '?')}",
            f"\nGraph impact: {nodes} nodes across {len(comms)} communities",
            f"Communities touched: {comms}",
            f"Files changed ({len(files)}):",
        ]
        lines += [f"  {f}" for f in files[:20]]
        if len(files) > 20:
            lines.append(f"  … and {len(files) - 20} more")
        return "\n".join(lines)

    def _tool_triage_prs(arguments: dict) -> str:
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from graphify.prs import fetch_prs, fetch_worktrees, fetch_pr_files, compute_pr_impact, _STATUS_ORDER, _detect_default_branch
        repo = arguments.get("repo") or None
        base = arguments.get("base") or _detect_default_branch(repo)
        try:
            prs = fetch_prs(repo=repo, base=base)
        except RuntimeError as e:
            return f"Error: {e}"
        worktrees = fetch_worktrees()
        for pr in prs:
            pr.worktree_path = worktrees.get(pr.branch)
        actionable = [p for p in prs if p.base_branch == base and p.status not in ("WRONG-BASE", "STALE")]
        if not actionable:
            return f"No actionable PRs targeting {base}."
        # Fetch diffs concurrently then compute graph impact using in-memory G
        workers = min(8, len(actionable))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            future_to_pr = {pool.submit(fetch_pr_files, pr.number, repo): pr for pr in actionable}
            for fut in as_completed(future_to_pr):
                pr = future_to_pr[fut]
                try:
                    files = fut.result()
                except Exception:
                    files = []
                if files:
                    pr.files_changed = files
                    pr.communities_touched, pr.nodes_affected = compute_pr_impact(files, G, communities)
        header = (
            f"Actionable PRs targeting {base}: {len(actionable)}\n"
            "Rank these by review priority. Higher blast_radius = more graph communities affected = higher merge risk.\n"
        )
        lines = [header]
        for p in sorted(actionable, key=lambda x: (_STATUS_ORDER.index(x.status) if x.status in _STATUS_ORDER else 99)):
            impact = f"  blast_radius={p.blast_radius}" if p.blast_radius else ""
            wt = f"  worktree={p.worktree_path}" if p.worktree_path else ""
            lines.append(
                f"PR #{p.number} [{p.status}] CI={p.ci_status} review={p.review_decision or 'none'} "
                f"age={p.days_old}d author={p.author}{impact}{wt}\n  title: {p.title}"
            )
        return "\n\n".join(lines)

    _handlers = {
        "query_graph": _tool_query_graph,
        "get_node": _tool_get_node,
        "get_neighbors": _tool_get_neighbors,
        "get_community": _tool_get_community,
        "god_nodes": _tool_god_nodes,
        "graph_stats": _tool_graph_stats,
        "shortest_path": _tool_shortest_path,
        "list_prs": _tool_list_prs,
        "get_pr_impact": _tool_get_pr_impact,
        "triage_prs": _tool_triage_prs,
    }

    def _load_community_labels() -> dict[int, str]:
        labels = _runtime_cache(G).get("community_labels", {}) if G is not None else {}
        return dict(labels) or {cid: f"Community {cid}" for cid in communities}

    @server.list_resources()
    async def list_resources() -> list[types.Resource]:
        return [
            types.Resource(uri=AnyUrl("graphify://report"), name="Graph Report", description="Full GRAPH_REPORT.md", mimeType="text/markdown"),
            types.Resource(uri=AnyUrl("graphify://stats"), name="Graph Stats", description="Node/edge/community counts and confidence breakdown", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://god-nodes"), name="God Nodes", description="Top 10 most-connected nodes", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://surprises"), name="Surprising Connections", description="Cross-community surprising connections", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://audit"), name="Confidence Audit", description="EXTRACTED/INFERRED/AMBIGUOUS edge breakdown", mimeType="text/plain"),
            types.Resource(uri=AnyUrl("graphify://questions"), name="Suggested Questions", description="Suggested questions for this codebase", mimeType="text/plain"),
        ]

    @server.read_resource()
    async def read_resource(uri: AnyUrl) -> str:
        _select_graph(None)  # resources read the server's default graph
        uri_str = str(uri)
        if uri_str == "graphify://report":
            report_path = Path(active_graph_path).parent / "GRAPH_REPORT.md"
            if report_path.exists():
                return report_path.read_text(encoding="utf-8")
            return "GRAPH_REPORT.md not found. Run graphify extract first."
        if uri_str == "graphify://stats":
            return _tool_graph_stats({})
        if uri_str == "graphify://god-nodes":
            return _tool_god_nodes({"top_n": 10})
        if uri_str == "graphify://surprises":
            try:
                from graphify.analyze import surprising_connections
                surprises = surprising_connections(G, communities, top_n=10)
                if not surprises:
                    return "No surprising connections found."
                lines = ["Surprising cross-community connections:"]
                for s in surprises:
                    lines.append(f"  {s.get('source', '')} <-> {s.get('target', '')} [{s.get('relation', '')}]")
                return "\n".join(lines)
            except Exception as exc:
                return f"Could not compute surprising connections: {exc}"
        if uri_str == "graphify://audit":
            confs = [edge_attributes(edge).get("confidence", "EXTRACTED") for edge in G.edges()]
            total = len(confs) or 1
            return (
                f"Total edges: {total}\n"
                f"EXTRACTED: {confs.count('EXTRACTED')} ({round(confs.count('EXTRACTED')/total*100)}%)\n"
                f"INFERRED: {confs.count('INFERRED')} ({round(confs.count('INFERRED')/total*100)}%)\n"
                f"AMBIGUOUS: {confs.count('AMBIGUOUS')} ({round(confs.count('AMBIGUOUS')/total*100)}%)\n"
            )
        if uri_str == "graphify://questions":
            try:
                from graphify.analyze import suggest_questions
                community_labels = _load_community_labels()
                questions = suggest_questions(G, communities, community_labels, top_n=10)
                if not questions:
                    return "No suggested questions available."
                lines = ["Suggested questions:"]
                for q in questions:
                    if isinstance(q, dict):
                        lines.append(f"  - {q.get('question', '')}")
                    else:
                        lines.append(f"  - {q}")
                return "\n".join(lines)
            except Exception as exc:
                return f"Could not generate questions: {exc}"
        raise ValueError(f"Unknown resource: {uri_str}")

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[types.TextContent]:
        import asyncio

        arguments = dict(arguments or {})
        project_path = arguments.pop("project_path", None)
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]

        def _execute() -> str:
            # Helix's embedded client is synchronous. Run selection and the tool
            # as one serialized worker-thread operation so HTTP event loops are
            # never blocked and closure-scoped active context cannot cross calls.
            with _tool_lock:
                _select_graph(project_path)
                return handler(arguments)

        try:
            result = await asyncio.to_thread(_execute)
            return [types.TextContent(type="text", text=result)]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]

    return server


def serve(graph_path: str | None = None) -> None:
    """Start the MCP server over stdio (the default, per-developer transport)."""
    graph_path = graph_path or str(DEFAULT_PROJECT_STORE)
    try:
        from mcp.server.stdio import stdio_server
    except ImportError as e:
        raise ImportError('mcp not installed. Run: pip install "graphifyy[mcp]"') from e
    import asyncio

    server = _build_server(graph_path)

    async def main() -> None:
        async with stdio_server() as streams:
            await server.run(streams[0], streams[1], server.create_initialization_options())

    _filter_blank_stdin()
    asyncio.run(main())


class _MCPASGIApp:
    """Raw-ASGI wrapper around the Streamable HTTP session manager.

    Passed to a Starlette ``Route`` as a class instance (not a function) so
    Starlette treats it as an ASGI app: it serves the exact mount path for all
    methods (GET/POST/DELETE) with no request/response wrapping and no
    trailing-slash redirect — mirroring how FastMCP mounts the same manager.
    """

    def __init__(self, manager) -> None:
        self._manager = manager

    async def __call__(self, scope, receive, send) -> None:
        await self._manager.handle_request(scope, receive, send)


class _ApiKeyMiddleware:
    """Pure-ASGI API-key gate for the HTTP transport.

    Implemented as raw ASGI (not Starlette's BaseHTTPMiddleware) on purpose:
    BaseHTTPMiddleware buffers responses and breaks the Streamable HTTP SSE
    stream. This short-circuits with 401 before the request ever reaches the
    session manager, leaving the streaming path untouched for authorized calls.
    """

    def __init__(self, app, api_key: str) -> None:
        self.app = app
        self._expected = api_key.encode("utf-8")

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        import hmac
        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"x-api-key")
        if provided is None:
            # RFC 6750: the auth scheme token is case-insensitive.
            scheme, _, token = headers.get(b"authorization", b"").partition(b" ")
            if scheme.lower() == b"bearer" and token:
                provided = token.strip()
        # Constant-time compare; reject when no key was supplied at all.
        if provided is None or not hmac.compare_digest(provided, self._expected):
            body = b'{"error": "unauthorized"}'
            await send({
                "type": "http.response.start",
                "status": 401,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode("ascii")),
                ],
            })
            await send({"type": "http.response.body", "body": body})
            return
        await self.app(scope, receive, send)


def _build_http_app(
    graph_path: str,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    api_key: str | None = None,
    path: str = "/mcp",
    json_response: bool = False,
    stateless: bool = False,
    session_timeout: float | None = 3600.0,
):
    """Build the Starlette ASGI app for the Streamable HTTP transport.

    Split out from :func:`serve_http` (which blocks on uvicorn) so the wiring
    can be exercised with an in-process ASGI test client.

    ``session_timeout`` reaps stateful sessions idle for that many seconds so a
    long-running shared server does not leak memory when IDE clients disconnect
    without sending a DELETE. ``None`` (or <= 0) disables reaping; it is forced
    to ``None`` in stateless mode, which has no sessions to reap.
    """
    try:
        import contextlib

        from starlette.applications import Starlette
        from starlette.middleware import Middleware
        from starlette.routing import Route

        from mcp.server.streamable_http_manager import StreamableHTTPSessionManager
        from mcp.server.transport_security import TransportSecuritySettings
    except ImportError as e:
        raise ImportError(
            'HTTP transport needs the mcp extra (mcp + starlette + uvicorn). '
            'Run: pip install "graphifyy[mcp]"'
        ) from e

    # A blank key (e.g. --api-key "" or an empty GRAPHIFY_API_KEY) must not be
    # mistaken for "auth on" — normalize it to None so the gate is unambiguous.
    api_key = (api_key or "").strip() or None

    server = _build_server(graph_path)

    # DNS-rebinding protection. When the operator binds a wildcard address they
    # are intentionally exposing the server, so accept any Host header; for a
    # loopback/specific bind, restrict Host to that address (with and without
    # the port) plus the localhost aliases.
    if host in ("0.0.0.0", "::", ""):  # nosec B104 - explicit operator-selected bind
        security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    else:
        allowed = {host, "localhost", "127.0.0.1"}
        allowed |= {f"{h}:{port}" for h in list(allowed)}
        security = TransportSecuritySettings(allowed_hosts=sorted(allowed))

    # The SDK rejects a non-positive timeout and forbids one in stateless mode.
    idle_timeout = None if (stateless or not session_timeout or session_timeout <= 0) else session_timeout

    manager = StreamableHTTPSessionManager(
        app=server,
        json_response=json_response,
        stateless=stateless,
        security_settings=security,
        session_idle_timeout=idle_timeout,
    )

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        # The session manager owns an anyio task group that must wrap the whole
        # server lifetime, so enter it here rather than per-request.
        async with manager.run():
            yield

    middleware = []
    if api_key:
        middleware.append(Middleware(_ApiKeyMiddleware, api_key=api_key))

    return Starlette(
        routes=[Route(path, endpoint=_MCPASGIApp(manager))],
        middleware=middleware,
        lifespan=lifespan,
    )


def serve_http(
    graph_path: str | None = None,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    api_key: str | None = None,
    path: str = "/mcp",
    json_response: bool = False,
    stateless: bool = False,
    session_timeout: float | None = 3600.0,
) -> None:
    """Start the MCP server over Streamable HTTP (MCP spec 2025-03-26).

    Serves the same tools/resources as the stdio transport, so a single shared
    process can host the graph for a whole team. Clients point their IDE MCP
    config at ``http://<host>:<port><path>`` (default ``/mcp``).

    ``api_key`` (or the ``GRAPHIFY_API_KEY`` env var) enables a simple header
    check (``Authorization: Bearer <key>`` or ``X-API-Key: <key>``). OAuth is a
    deliberate follow-up. Binding ``0.0.0.0`` exposes the server beyond
    localhost — set an api_key when you do.
    """
    graph_path = graph_path or str(DEFAULT_PROJECT_STORE)
    try:
        import uvicorn
    except ImportError as e:
        raise ImportError(
            'HTTP transport needs the mcp extra (mcp + starlette + uvicorn). '
            'Run: pip install "graphifyy[mcp]"'
        ) from e

    api_key = (api_key or "").strip() or None

    app = _build_http_app(
        graph_path,
        host=host,
        port=port,
        api_key=api_key,
        path=path,
        json_response=json_response,
        stateless=stateless,
        session_timeout=session_timeout,
    )

    auth_note = "api-key required" if api_key else "no auth (set --api-key to require one)"
    print(
        f"graphify MCP server (streamable-http) on http://{host}:{port}{path} - {auth_note}",
        file=sys.stderr,
    )
    if host in ("0.0.0.0", "::", "") and not api_key:  # nosec B104 - emits warning
        print(
            f"WARNING: binding {host or '0.0.0.0'} with no api-key exposes the graph "  # nosec B104
            "unauthenticated on the network. Set --api-key (or GRAPHIFY_API_KEY).",
            file=sys.stderr,
        )
    uvicorn.run(app, host=host, port=port)


def _main(argv: list[str] | None = None) -> None:
    import argparse
    import os

    parser = argparse.ArgumentParser(
        prog="python -m graphify.serve",
        description="Serve a graphify knowledge graph over MCP (stdio or Streamable HTTP).",
    )
    parser.add_argument(
        "graph_path",
        nargs="?",
        default=None,
        help="Path to graph.helix store (default: graphify-out/graph.helix)",
    )
    parser.add_argument(
        "--graph",
        dest="graph_flag",
        default=None,
        metavar="PATH",
        help="Path to graph.helix — alias for the positional argument",
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport to serve on (default: stdio)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="HTTP bind host (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8080, help="HTTP bind port (default: 8080)")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("GRAPHIFY_API_KEY"),
        help="Require this key on the HTTP transport (env: GRAPHIFY_API_KEY)",
    )
    parser.add_argument("--path", default="/mcp", help="HTTP mount path (default: /mcp)")
    parser.add_argument(
        "--json-response",
        action="store_true",
        help="Return plain JSON responses instead of SSE streams",
    )
    parser.add_argument(
        "--stateless",
        action="store_true",
        help="Run without per-session state (for load-balanced / CI deployments)",
    )
    parser.add_argument(
        "--session-timeout",
        type=float,
        default=3600.0,
        help="Reap stateful sessions idle this many seconds (default: 3600; 0 disables)",
    )
    args = parser.parse_args(argv)
    graph_path = args.graph_flag or args.graph_path or str(DEFAULT_PROJECT_STORE)

    if args.transport == "http":
        serve_http(
            graph_path,
            host=args.host,
            port=args.port,
            api_key=args.api_key,
            path=args.path,
            json_response=args.json_response,
            stateless=args.stateless,
            session_timeout=args.session_timeout,
        )
    else:
        serve(graph_path)


if __name__ == "__main__":
    _main()
