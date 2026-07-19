# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import math
import re
import sys
from pathlib import Path
from typing import Any, NamedTuple
from graphify.security import sanitize_label, validate_store_path
from graphify.build import edge_data
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


def _compute_idf(G: Any, terms: list[str], native_query: Any) -> dict[str, float]:
    """Compute exact label document frequencies with public Helix predicates."""
    frequencies = native_query.document_frequencies(terms)
    node_count = G.node_count or 1
    return {
        term: math.log(1 + node_count / (1 + frequencies.get(term, 0)))
        for term in terms
    }


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


def _score_nodes(
    G: Any, terms: list[str], *, native_query: Any
) -> list[tuple[float, str]]:
    """Combined query scorer returning the existing ranked `(score, node_id)` list.

    Backwards-compatible thin wrapper around `_score_query` for path, explain,
    tests, and every other caller that only needs the combined ranking. The
    per-term seed metadata computed by `_score_query` (when requested) is
    discarded here so existing callers see no API or runtime-cost change.
    """
    return _score_query(
        G, terms, collect_per_term_seeds=False, native_query=native_query
    ).ranked


def _score_query(
    G: Any,
    terms: list[str],
    *,
    collect_per_term_seeds: bool,
    native_query: Any,
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
    idf = _compute_idf(G, norm_terms, native_query)
    # Whole-query string for full-label matching (mirrors _find_node's `term`).
    joined = " ".join(norm_terms)
    # Weight the full-query bonus by the rarest constituent term so a specific
    # multi-word label still outweighs common-token noise; floor at 1.0.
    joined_w = max((idf.get(t, 1.0) for t in norm_terms), default=1.0)
    candidate_ids = native_query.candidate_ids(
        norm_terms + ([joined] if joined else [])
    )
    node_iter = ((nid, node_attributes(G, nid)) for nid in candidate_ids)
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
    native_query: Any | None = None,
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

    if native_query is None:
        raise RuntimeError("context-filtered traversal requires a native Helix query")
    visited = set(native_query.traverse_ids(
        start_nodes, depth, contexts=context_filters
    ))
    edges_seen: list[Any] = []
    seen_edge_ids: set[Any] = set()
    for node in visited:
        for edge_id in G.incident_edge_ids(node):
            if edge_id in seen_edge_ids:
                continue
            edge = G.edge(edge_id)
            if (
                edge is None
                or edge.source not in visited
                or edge.target not in visited
                or edge_attributes(edge).get("context") not in context_filters
            ):
                continue
            seen_edge_ids.add(edge_id)
            edges_seen.append(edge)
    return visited, edges_seen


def _bfs(
    G: Any,
    start_nodes: list[str],
    depth: int,
    context_filters: set[str] | None = None,
    *,
    native_query: Any | None = None,
):
    return _traverse(
        G,
        start_nodes,
        depth,
        strategy="breadth_first",
        context_filters=context_filters,
        native_query=native_query,
    )


def _dfs(
    G: Any,
    start_nodes: list[str],
    depth: int,
    context_filters: set[str] | None = None,
    *,
    native_query: Any | None = None,
):
    return _traverse(
        G,
        start_nodes,
        depth,
        strategy="depth_first",
        context_filters=context_filters,
        native_query=native_query,
    )


def _subgraph_to_text(
    G: Any,
    nodes: set[str],
    edges: list[Any],
    token_budget: int = 2000,
    *,
    seeds: list[str] | None = None,
    learning_overlay: dict[str, Any] | None = None,
) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token).

    seeds: exact-match nodes rendered first before the degree-sorted expansion,
    so the queried symbol always appears at the top of the output.
    """
    char_budget = token_budget * 3
    lines = []
    overlay = learning_overlay or {}
    seed_set = set(seeds or [])
    ordered = [n for n in (seeds or []) if n in nodes] + \
              sorted(nodes - seed_set, key=lambda n: G.degree(n).degree, reverse=True)
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
            line = (
                f"EDGE {sanitize_label(node_attributes(G, u).get('label', u))} "
                f"--{sanitize_label(str(d.get('relation', '')))} "
                f"[{sanitize_label(str(d.get('confidence', '')))}{context_suffix}]--> "
                f"{sanitize_label(node_attributes(G, v).get('label', v))}"
            )
            lines.append(line)
    output = "\n".join(lines)
    if len(output) > char_budget:
        cut_at = output[:char_budget].rfind("\n")
        cut_at = cut_at if cut_at > 0 else char_budget
        total_nodes = sum(1 for l in lines if l.startswith("NODE "))
        shown_nodes = output[:cut_at].count("\nNODE ") + (1 if output.startswith("NODE ") else 0)
        cut_count = total_nodes - shown_nodes
        output = (
            output[:cut_at]
            + f"\n... (truncated — {cut_count} more nodes cut by ~{token_budget}-token budget."
            f" Narrow with context_filter=['call'] or use get_node for a specific symbol)"
        )
    return output


def _query_graph_text(
    G: Any,
    question: str,
    *,
    native_query: Any,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
    context_filters: list[str] | None = None,
    learning_overlay: dict[str, Any] | None = None,
) -> str:
    terms = _query_terms(question)
    # One graph scoring pass produces both the combined ranking (used to drive
    # the gap-based seed selection below) and the per-token singleton winners
    # (used by _pick_seeds' per-term guarantee). Previously this was T+1 passes
    # — one combined + one per query token — re-walking the whole graph each
    # time; on a 100k-node, three-term benchmark ~71% of scoring time was
    # spent in those redundant per-term passes.
    qs = _score_query(
        G,
        terms,
        collect_per_term_seeds=True,
        native_query=native_query,
    )
    start_nodes = _pick_seeds(qs.ranked, G=G, best_seed_by_term=qs.best_seed_by_term)
    if not start_nodes:
        return "No matching nodes found."
    resolved_filters, filter_source = _resolve_context_filters(question, context_filters)
    traversal_graph, edge_filters = _filter_graph_by_context(G, resolved_filters)
    nodes, edges = (
        _dfs(
            traversal_graph,
            start_nodes,
            depth,
            edge_filters,
            native_query=native_query,
        )
        if mode == "dfs"
        else _bfs(
            traversal_graph,
            start_nodes,
            depth,
            edge_filters,
            native_query=native_query,
        )
    )
    header_parts = [
        f"Traversal: {mode.upper()} depth={depth}",
        f"Start: {[node_attributes(G, n).get('label', n) for n in start_nodes]}",
    ]
    if resolved_filters:
        header_parts.append(f"Context: {', '.join(resolved_filters)} ({filter_source})")
    header_parts.append(f"{len(nodes)} nodes found")
    header = " | ".join(header_parts) + "\n\n"
    return header + _subgraph_to_text(
        traversal_graph,
        nodes,
        edges,
        token_budget,
        learning_overlay=learning_overlay,
    )


def _find_node(G: Any, label: str, *, native_query: Any) -> list[str]:
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
    candidate_ids = native_query.candidate_ids([term, norm_query])
    node_iter = ((nid, node_attributes(G, nid)) for nid in candidate_ids)
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
        preferred = [
            nid
            for nid in source_exact
            if str(node_attributes(G, nid).get("source_location", "")) == "L1"
            and _strip_diacritics(str(node_attributes(G, nid).get("label") or "")).lower()
            == query_basename
        ]
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

    # Per-store context: each reader retains one immutable native snapshot and
    # its long-lived public predicate client until the generation changes.
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
                return (
                    ent["G"],
                    ent["native_query"],
                    ent["communities"],
                    ent["community_labels"],
                    ent["learning_overlay"],
                    ent["confidence_counts"],
                )
            new_G = loaded.graph
            learning = loaded.state.get("learning", {})
            learning_overlay = (
                dict(learning.get("nodes", {})) if isinstance(learning, dict) else {}
            )
            community_labels = {
                int(record["id"]): str(record.get("name") or f"Community {record['id']}")
                for record in loaded.state.get("communities", [])
                if isinstance(record, dict) and isinstance(record.get("id"), int)
            }
            comm = _communities_from_graph(loaded)
            analysis = loaded.state.get("analysis", {})
            raw_counts = analysis.get("confidence_counts", {}) if isinstance(analysis, dict) else {}
            confidence_counts = {
                name: int(raw_counts.get(name, 0))
                for name in ("EXTRACTED", "INFERRED", "AMBIGUOUS")
            } if isinstance(raw_counts, dict) else {}
            if not confidence_counts or sum(confidence_counts.values()) != new_G.edge_count:
                confidence_counts = {
                    "EXTRACTED": new_G.edge_count,
                    "INFERRED": 0,
                    "AMBIGUOUS": 0,
                }
            ent.update({
                "generation": loaded.generation,
                "G": new_G,
                "native_query": loaded.query,
                "communities": comm,
                "community_labels": community_labels,
                "learning_overlay": learning_overlay,
                "confidence_counts": confidence_counts,
            })
            return (
                new_G,
                loaded.query,
                comm,
                community_labels,
                learning_overlay,
                confidence_counts,
            )

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
        (
            G,
            native_query,
            communities,
            community_labels,
            learning_overlay,
            confidence_counts,
        ) = _load_ctx(_default_graph_path)
    except (FileNotFoundError, RuntimeError):
        # No default graph at startup → run as a pure multi-project server. Tools
        # then require project_path; a call without one gets a clear error rather
        # than the process refusing to start (which is what _load_graph would do).
        G, native_query, communities, community_labels, learning_overlay, confidence_counts = (
            None, None, {}, {}, {}, {}
        )

    def _select_graph(project_path) -> None:
        nonlocal G, native_query, communities, community_labels, learning_overlay
        nonlocal confidence_counts
        nonlocal active_graph_path
        path = _resolve_graph_path(project_path)
        (
            G,
            native_query,
            communities,
            community_labels,
            learning_overlay,
            confidence_counts,
        ) = _load_ctx(path)
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
                    },
                    "required": ["label"],
                },
            ),
            types.Tool(
                name="get_community",
                description="Get all nodes in a community by community ID.",
                inputSchema={
                    "type": "object",
                    "properties": {"community_id": {"type": "integer", "description": "Community ID (0-indexed by size)"}},
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
            native_query=native_query,
            mode=mode,
            depth=depth,
            token_budget=budget,
            context_filters=context_filter,
            learning_overlay=learning_overlay,
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
        matches = _find_node(G, label, native_query=native_query)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        d = node_attributes(G, nid)
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
        matches = _find_node(G, label, native_query=native_query)
        if not matches:
            return f"No node matching '{label}' found."
        nid = matches[0]
        lines = [f"Neighbors of {sanitize_label(node_attributes(G, nid).get('label', nid))}:"]
        for nb in G.successors(nid):
            d = edge_data(G, nid, nb)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in str(rel).lower():
                continue
            lines.append(
                f"  --> {sanitize_label(node_attributes(G, nb).get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]"
            )
        for nb in G.predecessors(nid):
            d = edge_data(G, nb, nid)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(
                f"  <-- {sanitize_label(node_attributes(G, nb).get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]"
            )
        return "\n".join(lines)

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
        return "\n".join(lines)

    def _tool_god_nodes(arguments: dict) -> str:
        from graphify.analyze import god_nodes as _god_nodes
        nodes = _god_nodes(G, top_n=int(arguments.get("top_n", 10)))
        lines = ["God nodes (most connected):"]
        lines += [f"  {i}. {n['label']} - {n['degree']} edges" for i, n in enumerate(nodes, 1)]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        total = G.edge_count or 1
        return (
            f"Nodes: {G.node_count}\n"
            f"Edges: {G.edge_count}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confidence_counts['EXTRACTED']/total*100)}%\n"
            f"INFERRED: {round(confidence_counts['INFERRED']/total*100)}%\n"
            f"AMBIGUOUS: {round(confidence_counts['AMBIGUOUS']/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_scored = _score_nodes(
            G,
            [t.lower() for t in arguments["source"].split()],
            native_query=native_query,
        )
        tgt_scored = _score_nodes(
            G,
            [t.lower() for t in arguments["target"].split()],
            native_query=native_query,
        )
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
            if G.has_edge_between(u, v):
                edata = edge_data(G, u, v)
                forward = True
            else:
                edata = edge_data(G, v, u)
                forward = False
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            conf_str = f" [{conf}]" if conf else ""
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
        comms, nodes = compute_pr_impact(
            files, G, communities, native_query=native_query
        )
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
                    pr.communities_touched, pr.nodes_affected = compute_pr_impact(
                        files, G, communities, native_query=native_query
                    )
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
        return dict(community_labels) or {
            cid: f"Community {cid}" for cid in communities
        }

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
        import asyncio

        def read() -> str:
            with _tool_lock:
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
                        for item in surprises:
                            lines.append(
                                f"  {item.get('source', '')} <-> "
                                f"{item.get('target', '')} [{item.get('relation', '')}]"
                            )
                        return "\n".join(lines)
                    except Exception as exc:
                        return f"Could not compute surprising connections: {exc}"
                if uri_str == "graphify://audit":
                    total = G.edge_count or 1
                    return (
                        f"Total edges: {total}\n"
                        f"EXTRACTED: {confidence_counts['EXTRACTED']} "
                        f"({round(confidence_counts['EXTRACTED'] / total * 100)}%)\n"
                        f"INFERRED: {confidence_counts['INFERRED']} "
                        f"({round(confidence_counts['INFERRED'] / total * 100)}%)\n"
                        f"AMBIGUOUS: {confidence_counts['AMBIGUOUS']} "
                        f"({round(confidence_counts['AMBIGUOUS'] / total * 100)}%)\n"
                    )
                if uri_str == "graphify://questions":
                    try:
                        from graphify.analyze import suggest_questions

                        labels = _load_community_labels()
                        questions = suggest_questions(
                            G, communities, labels, top_n=10
                        )
                        if not questions:
                            return "No suggested questions available."
                        lines = ["Suggested questions:"]
                        for question in questions:
                            if isinstance(question, dict):
                                lines.append(f"  - {question.get('question', '')}")
                            else:
                                lines.append(f"  - {question}")
                        return "\n".join(lines)
                    except Exception as exc:
                        return f"Could not generate questions: {exc}"
                raise ValueError(f"Unknown resource: {uri_str}")

        return await asyncio.to_thread(read)

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
