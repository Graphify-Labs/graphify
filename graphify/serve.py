# MCP stdio server - exposes graph query tools to Claude and other agents
from __future__ import annotations
import json
import math
import re
import sys
from array import array
from collections import OrderedDict
from dataclasses import dataclass
from difflib import get_close_matches
from pathlib import Path
import networkx as nx
from networkx.readwrite import json_graph
from graphify.security import sanitize_label, check_graph_file_size_cap
from graphify.build import edge_data
from graphify.paths import default_graph_json as _default_graph_json

try:
    import jieba as _jieba  # type: ignore[import-untyped]
except ImportError:
    _jieba = None


_COMMUNITY_LABELS_FILENAME = ".graphify_labels.json"
_MAX_COMMUNITY_LABELS_BYTES = 1024 * 1024
_MAX_COMMUNITY_LABEL_ENTRIES = 4096
_MAX_COMMUNITY_LABEL_LENGTH = 1024


def _load_adjacent_community_labels(graph_path: str | Path) -> dict[int, str]:
    """Load the canonical label artifact beside graph.json, if it is usable."""
    labels_path = Path(graph_path).resolve().parent / _COMMUNITY_LABELS_FILENAME
    try:
        if labels_path.stat().st_size > _MAX_COMMUNITY_LABELS_BYTES:
            return {}
        with labels_path.open("rb") as stream:
            payload = stream.read(_MAX_COMMUNITY_LABELS_BYTES + 1)
        if len(payload) > _MAX_COMMUNITY_LABELS_BYTES:
            return {}
        data = json.loads(payload.decode("utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    wrappers = [key for key in ("labels", "communities") if key in data]
    if len(wrappers) > 1:
        return {}
    if wrappers:
        data = data[wrappers[0]]
        if not isinstance(data, dict):
            return {}
    if len(data) > _MAX_COMMUNITY_LABEL_ENTRIES:
        return {}
    labels: dict[int, str] = {}
    for raw_cid, raw_label in data.items():
        try:
            cid = int(raw_cid)
        except (TypeError, ValueError):
            return {}
        if cid < 0 or cid in labels:
            return {}
        if isinstance(raw_label, dict):
            raw_label = next(
                (
                    raw_label[key]
                    for key in ("label", "name", "title")
                    if raw_label.get(key) not in (None, "")
                ),
                "",
            )
        if not isinstance(raw_label, str) or len(raw_label) > _MAX_COMMUNITY_LABEL_LENGTH:
            return {}
        label = sanitize_label(raw_label).strip()
        if not label:
            return {}
        labels[cid] = label
    return labels


def _attach_adjacent_community_labels(G: nx.Graph, graph_path: str | Path) -> None:
    """Overlay canonical labels in memory without rewriting graph.json.

    The adjacent artifact wins over embedded ``community_name`` values for IDs
    present in the current graph. Missing, malformed, partial, or stale extra
    entries are ignored, preserving embedded names and numeric community lookup.
    """
    labels = _load_adjacent_community_labels(graph_path)
    present = set(_communities_from_graph(G))
    current = {cid: label for cid, label in labels.items() if cid in present}
    G.graph["_community_labels"] = current
    for _, data in G.nodes(data=True):
        try:
            cid = int(data.get("community"))
        except (TypeError, ValueError):
            continue
        if cid in current:
            data["community_name"] = current[cid]


def _query_context_key(
    graph_path: str | Path,
) -> tuple[int, int, int | None, int | None, int | None, int | None]:
    """Return a cache key that invalidates on graph or label artifact changes."""
    graph = Path(graph_path)
    stat = graph.stat()
    labels_path = graph.resolve().parent / _COMMUNITY_LABELS_FILENAME
    try:
        labels_stat = labels_path.stat()
        labels_key = (
            labels_stat.st_mtime_ns,
            labels_stat.st_size,
            labels_stat.st_ctime_ns,
            labels_stat.st_ino,
        )
    except OSError:
        labels_key = (None, None, None, None)
    return stat.st_mtime_ns, stat.st_size, *labels_key


def _load_graph(graph_path: str) -> nx.Graph:
    try:
        resolved = Path(graph_path).resolve()
        if resolved.suffix != ".json":
            raise ValueError(f"Graph path must be a .json file, got: {graph_path!r}")
        if not resolved.exists():
            raise FileNotFoundError(f"Graph file not found: {resolved}")
        check_graph_file_size_cap(resolved)
        safe = resolved
        data = json.loads(safe.read_text(encoding="utf-8"))
        if "links" not in data and "edges" in data:
            data = dict(data, links=data["edges"])
        data = {**data, "directed": True}
        try:
            from graphify.build import graph_has_legacy_ids as _legacy
            if _legacy(data.get("nodes", [])):
                print(
                    "[graphify] note: this graph uses the pre-#1504 node-ID scheme; "
                    "rebuild with `graphify extract --force` for path-qualified IDs.",
                    file=sys.stderr,
                )
        except Exception:
            pass
        try:
            G = json_graph.node_link_graph(data, edges="links")
        except TypeError:
            G = json_graph.node_link_graph(data)
        _attach_adjacent_community_labels(G, resolved)
        # Attach the work-memory overlay (derived sidecar next to graph.json) so
        # the query/MCP read surface can annotate NODE lines display-only. Empty
        # when no sidecar exists, leaving un-annotated output byte-identical.
        try:
            from graphify.reflect import load_learning_overlay as _llo
            G.graph["_learning_overlay"] = _llo(resolved)
        except Exception:
            G.graph["_learning_overlay"] = {}
        return G
    except (ValueError, FileNotFoundError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"error: graph.json is corrupted ({exc}). Re-run /graphify to rebuild.", file=sys.stderr)
        sys.exit(1)


def _communities_from_graph(G: nx.Graph) -> dict[int, list[str]]:
    """Reconstruct community dict from community property stored on nodes."""
    communities: dict[int, list[str]] = {}
    for node_id, data in G.nodes(data=True):
        cid = data.get("community")
        if cid is not None:
            communities.setdefault(int(cid), []).append(node_id)
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


# Bound untrusted query normalization and graph-local IDF state. These limits are
# well above normal natural-language/symbol queries while preventing one request
# or a stream of unique requests from retaining unbounded work or cache entries.
_MAX_QUERY_TERMS = 32
_MAX_QUERY_TERM_LENGTH = 128
_MAX_IDF_CACHE_ENTRIES = 512


def _bounded_normalized_terms(terms) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in terms:
        bounded = str(raw)[:_MAX_QUERY_TERM_LENGTH * 2]
        for match in re.finditer(r"\w+", _strip_diacritics(bounded).lower()):
            token = match.group(0)[:_MAX_QUERY_TERM_LENGTH]
            if token and token not in seen:
                seen.add(token)
                normalized.append(token)
                if len(normalized) >= _MAX_QUERY_TERMS:
                    return normalized
    return normalized


# English question/filler words dropped from query terms so content words drive
# BFS seeding. Without this, "how does the frontier cache work" seeds on "how"/
# "the"/"work" (which prefix-match prose labels like "Working Principles" at 100x)
# instead of "frontier"/"cache", and lands in the wrong part of the graph. Applied
# to query terms only — node text is never filtered, so a symbol literally named
# `work` stays findable via explain/path. `work`/`works`/`working` are included
# because "how does X work" / "how X works" is the most common question phrasing.
_QUERY_STOPWORDS = frozenset({
    "how", "what", "why", "when", "where", "which", "who", "whom", "whose",
    "does", "did", "is", "are", "was", "were", "be", "been", "being",
    "can", "could", "should", "would", "will", "shall", "may", "might", "must",
    "has", "have", "had", "the", "and", "but", "not", "for", "from", "with",
    "without", "into", "onto", "off", "that", "this", "these", "those", "there",
    "here", "its", "their", "them", "they", "about", "any", "all", "some",
    "work", "works", "working",
})


def _query_terms(question: str) -> list[str]:
    """Split a query into searchable terms, segmenting Chinese text, then drop
    English question/filler words (`_QUERY_STOPWORDS`) so content words drive
    seeding. Falls back to the unfiltered terms if the query is all stopwords, so
    a question like "how does it work" still seeds on something."""
    terms: list[str] = []
    for raw_match in re.finditer(r"\S+", str(question)):
        raw = raw_match.group(0)[:_MAX_QUERY_TERM_LENGTH]
        if _has_chinese(raw):
            for seg in _segment_chinese(raw.lower().strip()):
                seg = seg.strip()[:_MAX_QUERY_TERM_LENGTH]
                if seg and _is_searchable(seg):
                    terms.append(seg)
                    if len(terms) >= _MAX_QUERY_TERMS:
                        break
        else:
            # Strip punctuation without touching Unicode characters (avoid NFKD mangling non-Latin scripts)
            for match in re.finditer(r"\w+", raw.lower()):
                tok = match.group(0)[:_MAX_QUERY_TERM_LENGTH]
                if _is_searchable(tok):
                    terms.append(tok)
                    if len(terms) >= _MAX_QUERY_TERMS:
                        break
        if len(terms) >= _MAX_QUERY_TERMS:
            break
    content = [t for t in terms if t not in _QUERY_STOPWORDS]
    return content or terms


@dataclass(frozen=True)
class _QueryDirectives:
    text: str
    include_memory: bool = False
    community: str | None = None
    god: str | None = None


_QUERY_SCOPE_RE = re.compile(
    r"(?<!\w)(community|god):(?:\"([^\"]*)\"|'([^']*)'|([^\s]*))",
    re.IGNORECASE,
)


def _parse_query_directives(question: str) -> _QueryDirectives:
    """Remove search directives while preserving their values for scoping."""
    include_memory = bool(re.search(r"(?<!\w)include:memory\b", question, re.IGNORECASE))
    values: dict[str, str] = {}

    def capture(match: re.Match) -> str:
        values[match.group(1).lower()] = next(
            value for value in match.groups()[1:] if value is not None
        ).strip()
        return " "

    text = _QUERY_SCOPE_RE.sub(capture, question)
    text = re.sub(r"(?<!\w)include:memory\b", " ", text, flags=re.IGNORECASE)
    return _QueryDirectives(
        text=" ".join(text.split()),
        include_memory=include_memory,
        community=values.get("community"),
        god=values.get("god"),
    )


def _is_memory_node(data: dict) -> bool:
    source = str(data.get("source_file") or "").replace("\\", "/").lower()
    parts = [part for part in source.split("/") if part and part != "."]
    return any(
        parts[index:index + 2] == ["graphify-out", "memory"]
        for index in range(len(parts) - 1)
    )


def _node_scope(data: dict) -> str:
    if _is_memory_node(data):
        return "memory"
    source = str(data.get("source_file") or "").replace("\\", "/").lower()
    parts = [part for part in source.split("/") if part]
    name = parts[-1] if parts else ""
    if (
        any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in parts)
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    ):
        return "tests"
    file_type = str(data.get("file_type") or "").lower()
    if (
        file_type in {"document", "paper", "rationale"}
        or any(part in {"doc", "docs", "documentation"} for part in parts)
        or Path(name).suffix in {".md", ".mdx", ".rst", ".txt", ".adoc"}
    ):
        return "docs"
    return "code"


def _query_scope_order(question: str, include_memory: bool) -> list[str]:
    terms = set(_search_tokens(question))
    if include_memory:
        return ["memory", "code", "docs", "tests"]
    if terms & {"test", "tests", "testing", "spec", "specs", "fixture", "fixtures"}:
        return ["tests", "code", "docs"]
    if terms & {"doc", "docs", "documentation", "readme", "guide", "paper"}:
        return ["docs", "code", "tests"]
    return ["code", "docs", "tests"]


_EXACT_MATCH_BONUS = 1000.0
_PREFIX_MATCH_BONUS = 100.0
_SUBSTRING_MATCH_BONUS = 1.0
_SOURCE_MATCH_BONUS = 0.5


def _compute_idf(G: nx.Graph, terms: list[str]) -> dict[str, float]:
    """IDF weights in a deterministic graph-local least-recently-used cache.

    Common terms like 'error' or 'exception' that match hundreds of nodes get
    low weights; rare identifiers like 'FooBarService' get high weights.
    Cache is stored on the graph object itself so it auto-invalidates when
    a hot-reload replaces G with a new object.
    """
    terms = _bounded_normalized_terms(terms)
    existing = G.graph.get("_idf_cache")
    if not isinstance(existing, OrderedDict):
        existing = OrderedDict(existing or {})
        G.graph["_idf_cache"] = existing
    cache: OrderedDict[str, float] = existing
    while len(cache) > _MAX_IDF_CACHE_ENTRIES:
        cache.popitem(last=False)
    N = G.number_of_nodes() or 1
    uncached = [t for t in terms if t not in cache]
    for term in terms:
        if term in cache:
            cache.move_to_end(term)
    if uncached:
        df: dict[str, int] = {t: 0 for t in uncached}
        for _, data in G.nodes(data=True):
            norm_label = (
                data.get("norm_label") or _strip_diacritics(data.get("label") or "")
            ).lower()
            for t in uncached:
                if t in norm_label:
                    df[t] += 1
        for t in uncached:
            cache[t] = math.log(1 + N / (1 + df[t]))
            cache.move_to_end(t)
            while len(cache) > _MAX_IDF_CACHE_ENTRIES:
                cache.popitem(last=False)
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


def _get_trigram_index(G: nx.Graph) -> dict:
    """Lazily build and cache a trigram -> node-position postings map on the graph.

    Cached on `G.graph` so it auto-invalidates when a hot-reload swaps in a
    fresh graph object, exactly like `_idf_cache`. `set_cache` memoizes per-trigram
    id-sets across queries within one graph generation.
    """
    idx = G.graph.get("_trigram_index")
    if idx is not None:
        return idx
    ids = list(G.nodes())
    postings: dict[str, array] = {}
    scopes: dict[str, str] = {}
    memory_ids: set[str] = set()
    community_names: dict[object, str] = {}
    community_nodes: dict[object, set[str]] = {}
    for i, nid in enumerate(ids):
        data = G.nodes[nid]
        for g in _trigrams(_node_search_text(data, nid)):
            bucket = postings.get(g)
            if bucket is None:
                bucket = array("i")
                postings[g] = bucket
            bucket.append(i)
        scope = _node_scope(data)
        scopes[nid] = scope
        if scope == "memory":
            memory_ids.add(nid)
        cid = data.get("community")
        if cid is not None:
            community_names.setdefault(
                cid, str(data.get("community_name") or f"Community {cid}")
            )
            community_nodes.setdefault(cid, set()).add(nid)
    idx = {
        "ids": ids,
        "postings": postings,
        "set_cache": {},
        "scopes": scopes,
        "memory_ids": frozenset(memory_ids),
        "community_names": community_names,
        "community_nodes": community_nodes,
    }
    G.graph["_trigram_index"] = idx
    return idx


def _trigram_candidates(G: nx.Graph, needles: list[str], *, guard_frac: float = 0.10) -> list[str] | None:
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


def _score_nodes(G: nx.Graph, terms: list[str]) -> list[tuple[float, str]]:
    scored = []
    # Dedupe tokens, order-preserving (as _pick_seeds already does): a repeated
    # query word must not double-count every tier, and with coverage scaling
    # below it would also inflate the matched-term ratio (#1602).
    norm_terms = _bounded_normalized_terms(terms)
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
        G.nodes(data=True) if candidate_ids is None
        else ((nid, G.nodes[nid]) for nid in candidate_ids)
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
        score = 0.0
        # Full-query tier: a multi-word query that equals (or prefixes) the whole
        # label must dominate the per-token bag-of-words sums below, so `path`/
        # `query` resolve the same node `explain` does (via _find_node). Without
        # this, no single token equals a multi-word label, the per-token exact
        # tier never fires, and every node sharing the token set ties -> arbitrary
        # node-id sort -> wrong/disconnected endpoint -> false "No path found".
        if joined:
            nid_lower = nid.lower()
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
            # Three-tier precedence: exact > prefix > substring (take the
            # strongest tier per term so a single term cannot double-count).
            if t == norm_label or t == bare_label:
                tiered += _EXACT_MATCH_BONUS * w
                matched += 1
            elif norm_label.startswith(t) or bare_label.startswith(t):
                tiered += _PREFIX_MATCH_BONUS * w
                matched += 1
            elif t in norm_label:
                score += _SUBSTRING_MATCH_BONUS * w
                matched += 1
            if t in source:
                score += _SOURCE_MATCH_BONUS * w
        if tiered:
            score += tiered * (matched / n_terms) ** 2
        if score > 0:
            scored.append((score, nid))
    # Sort by score desc; break ties toward the shorter label so a concise exact
    # match beats a longer superset that happens to share the same score.
    scored.sort(key=lambda s: (-s[0], len(G.nodes[s[1]].get("label") or s[1]), s[1]))
    return scored


def _stage_candidates(
    G: nx.Graph,
    scored: list[tuple[float, str]],
    question: str,
    *,
    include_memory: bool = False,
    limit: int = 24,
    global_quota: int = 2,
) -> tuple[list[tuple[float, str]], dict]:
    """Retain global, per-scope, and likely-community candidates in score order."""
    if not scored:
        return [], {"scopes": [], "communities": [], "global": 0, "cross_community": 0}

    scope_order = _query_scope_order(question, include_memory)
    ranked_scopes = {scope: rank for rank, scope in enumerate(scope_order)}
    globally_ranked = sorted(
        scored,
        key=lambda item: (
            -item[0],
            len(str(G.nodes[item[1]].get("label") or item[1])),
            str(G.nodes[item[1]].get("source_file") or ""),
            str(item[1]),
        ),
    )
    scope_preferred = sorted(
        globally_ranked,
        key=lambda item: (
            ranked_scopes.get(_lookup_node_scope(G, item[1]), len(ranked_scopes)),
            -item[0],
            str(G.nodes[item[1]].get("source_file") or ""),
            str(item[1]),
        ),
    )

    likely_communities: list[object] = []
    for _, nid in globally_ranked:
        community = G.nodes[nid].get("community")
        if community is not None and community not in likely_communities:
            likely_communities.append(community)
        if len(likely_communities) == 2:
            break

    limit = max(0, limit)
    global_top = globally_ranked[:min(limit, max(0, global_quota))]
    selected_ids = {nid for _, nid in global_top}

    for scope in scope_order:
        head = next(
            (item for item in globally_ranked if _lookup_node_scope(G, item[1]) == scope),
            None,
        )
        if head is not None and head[1] not in selected_ids and len(selected_ids) < limit:
            selected_ids.add(head[1])

    cross_community = [
        item for item in globally_ranked
        if likely_communities and G.nodes[item[1]].get("community") not in likely_communities
    ][:max(0, global_quota)]
    for _, nid in cross_community:
        if len(selected_ids) >= limit:
            break
        selected_ids.add(nid)

    for _, nid in scope_preferred:
        if len(selected_ids) >= limit:
            break
        selected_ids.add(nid)

    staged = [item for item in globally_ranked if item[1] in selected_ids]
    scopes = list(dict.fromkeys(_lookup_node_scope(G, nid) for _, nid in staged))
    return staged, {
        "scopes": scopes,
        "communities": likely_communities,
        "global": len(global_top),
        "cross_community": sum(nid in selected_ids for _, nid in cross_community),
    }


def _pick_scored_endpoint(G: nx.Graph, scored: list[tuple[float, str]], query: str) -> str:
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
        if qtokens <= set(_search_tokens(G.nodes[nid].get("label") or nid)):
            return nid
    return scored[0][1]


def _pick_seeds(
    scored: list[tuple[float, str]],
    max_k: int = 3,
    gap_ratio: float = 0.2,
    *,
    G: "nx.Graph | None" = None,
    terms: list[str] | None = None,
    eligible_ids: set[str] | None = None,
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

    When `G` and `terms` are supplied, this guarantees at least one seed per
    distinct query term that has any match at all, so one term's incidental
    collision cannot starve out the others. Ties within a term are broken by
    graph degree (structural centrality), so an isolated incidental match
    doesn't out-rank a real, well-connected hub for that term.

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
        data = G.nodes[nid]
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

    if G is not None and terms:
        norm_terms = sorted({tok for t in terms for tok in _search_tokens(t)})
        for term in norm_terms:
            term_scored = _score_nodes(G, [term])
            if eligible_ids is not None:
                term_scored = [item for item in term_scored if item[1] in eligible_ids]
            if not term_scored:
                continue
            best_score = term_scored[0][0]
            tied = [nid for s, nid in term_scored if s == best_score]
            best_nid = max(tied, key=lambda n: G.degree(n)) if len(tied) > 1 else term_scored[0][1]
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


def _filter_graph_by_context(G: nx.Graph, context_filters: list[str] | None) -> nx.Graph:
    filters = set(_normalize_context_filters(context_filters))
    if not filters:
        return G
    H = G.__class__()
    H.graph.update(G.graph)
    H.add_nodes_from(G.nodes(data=True))
    if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)):
        for u, v, key, data in G.edges(keys=True, data=True):
            if data.get("context") in filters:
                H.add_edge(u, v, key=key, **data)
    else:
        for u, v, data in G.edges(data=True):
            if data.get("context") in filters:
                H.add_edge(u, v, **data)
    return H


def _traversal_node_key(G: nx.Graph, nid: str) -> tuple:
    data = G.nodes[nid]
    return (
        -G.degree(nid),
        _strip_diacritics(str(data.get("label") or nid)).lower(),
        str(data.get("source_file") or "").replace("\\", "/").lower(),
        str(nid),
    )


def _bfs(
    G: nx.Graph,
    start_nodes: list[str],
    depth: int,
    max_nodes: int | None = None,
    excluded_nodes: frozenset[str] | set[str] | None = None,
) -> tuple[set[str], list[tuple]]:
    # Compute hub threshold: nodes above this degree are not expanded as transit.
    # p99 of degree distribution, floored at 50 to avoid over-blocking small graphs.
    excluded = excluded_nodes or frozenset()
    degrees = [G.degree(n) for n in G.nodes() if n not in excluded]
    if degrees:
        degrees_sorted = sorted(degrees)
        p99_idx = int(len(degrees_sorted) * 0.99)
        hub_threshold = max(50, degrees_sorted[p99_idx])
    else:
        hub_threshold = 50
    seed_set = set(start_nodes)
    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    edge_keys: set[object] = set()
    node_limit = max(max_nodes or len(G), len(visited))
    edge_limit = max(node_limit * 2, len(start_nodes))
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in sorted(frontier, key=lambda nid: _traversal_node_key(G, nid)):
            # Don't expand through high-degree hubs (except seeds - a hub that
            # is the starting node should still be explored).
            if n not in seed_set and G.degree(n) >= hub_threshold:
                continue
            neighbors = sorted(G.neighbors(n), key=lambda nid: _traversal_node_key(G, nid))
            for neighbor in neighbors:
                if neighbor in excluded:
                    continue
                edge_key = (n, neighbor) if G.is_directed() else frozenset((n, neighbor))
                selected = neighbor in visited or neighbor in next_frontier
                if not selected and len(visited) + len(next_frontier) < node_limit:
                    next_frontier.add(neighbor)
                    selected = True
                if selected and edge_key not in edge_keys and len(edges_seen) < edge_limit:
                    edge_keys.add(edge_key)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier
        if not frontier:
            break
    return visited, edges_seen


def _dfs(
    G: nx.Graph,
    start_nodes: list[str],
    depth: int,
    max_nodes: int | None = None,
    excluded_nodes: frozenset[str] | set[str] | None = None,
) -> tuple[set[str], list[tuple]]:
    excluded = excluded_nodes or frozenset()
    degrees = [G.degree(n) for n in G.nodes() if n not in excluded]
    if degrees:
        degrees_sorted = sorted(degrees)
        p99_idx = int(len(degrees_sorted) * 0.99)
        hub_threshold = max(50, degrees_sorted[p99_idx])
    else:
        hub_threshold = 50
    seed_set = set(start_nodes)
    visited: set[str] = set()
    edges_seen: list[tuple] = []
    edge_keys: set[object] = set()
    stack = [(n, 0) for n in reversed(start_nodes)]
    node_limit = max(max_nodes or len(G), len(start_nodes))
    edge_limit = max(node_limit * 2, len(start_nodes))
    while stack:
        node, d = stack.pop()
        if node in visited or d > depth:
            continue
        if len(visited) >= node_limit:
            break
        visited.add(node)
        if node not in seed_set and G.degree(node) >= hub_threshold:
            continue
        neighbors = sorted(
            G.neighbors(node),
            key=lambda nid: _traversal_node_key(G, nid),
            reverse=True,
        )
        for neighbor in neighbors:
            if neighbor in excluded:
                continue
            if neighbor not in visited:
                stack.append((neighbor, d + 1))
                edge_key = (
                    (node, neighbor) if G.is_directed() else frozenset((node, neighbor))
                )
                if edge_key in edge_keys or len(edges_seen) >= edge_limit:
                    continue
                edge_keys.add(edge_key)
                edges_seen.append((node, neighbor))
    return visited, edges_seen


def _source_display(data: dict) -> str:
    source = str(data.get("source_file") or "")
    location = str(data.get("source_location") or "")
    if source:
        return f"{source} {location}" if location else f"{source} (file only)"
    origin = str(data.get("origin_file") or "")
    if origin:
        return f"external/reference (unowned; referenced from {origin})"
    return "unowned (no source)"


def _source_fields(data: dict) -> tuple[str, str]:
    source = str(data.get("source_file") or "")
    location = str(data.get("source_location") or "")
    if source:
        return source, location or "file-only"
    origin = str(data.get("origin_file") or "")
    if origin:
        return "external/reference", f"unowned; origin={origin}"
    return "unowned", "no-source"


def _subgraph_to_text(G: nx.Graph, nodes: set[str], edges: list[tuple], token_budget: int = 2000, *, seeds: list[str] | None = None) -> str:
    """Render subgraph as text, cutting at token_budget (approx 3 chars/token).

    seeds: exact-match nodes rendered first before the degree-sorted expansion,
    so the queried symbol always appears at the top of the output.
    """
    char_budget = token_budget * 3
    lines = []
    # Work-memory overlay (derived sidecar) stashed on the graph at load time.
    # Empty when no sidecar exists, so un-annotated output stays byte-identical.
    overlay = getattr(G, "graph", {}).get("_learning_overlay", {}) or {}
    seed_set = set(seeds or [])
    ordered = [n for n in (seeds or []) if n in nodes] + \
              sorted(nodes - seed_set, key=lambda nid: _traversal_node_key(G, nid))
    for nid in ordered:
        d = G.nodes[nid]
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
        source, location = _source_fields(d)
        line = (
            f"NODE {sanitize_label(d.get('label', nid))} "
            f"[src={sanitize_label(source)} "
            f"loc={sanitize_label(location)} "
            f"community={sanitize_label(str(d.get('community_name') or d.get('community', '')))}"
            f"{learning_suffix}]"
        )
        lines.append(line)
    for u, v in edges:
        if u in nodes and v in nodes:
            raw = G[u][v]
            d = next(iter(raw.values()), {}) if isinstance(G, (nx.MultiGraph, nx.MultiDiGraph)) else raw
            context = d.get("context")
            context_suffix = f" context={sanitize_label(str(context))}" if context else ""
            line = (
                f"EDGE {sanitize_label(G.nodes[u].get('label', u))} "
                f"--{sanitize_label(str(d.get('relation', '')))} "
                f"[{sanitize_label(str(d.get('confidence', '')))}{context_suffix}]--> "
                f"{sanitize_label(G.nodes[v].get('label', v))}"
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
    G: nx.Graph,
    question: str,
    *,
    mode: str = "bfs",
    depth: int = 3,
    token_budget: int = 2000,
    context_filters: list[str] | None = None,
) -> str:
    directives = _parse_query_directives(question)
    scoped_nodes, scope_labels, scope_error = _resolve_query_scope(G, directives)
    if scope_error:
        return f"Error: {scope_error}"

    search_text = directives.text or directives.god or ""
    terms = _query_terms(search_text)
    if not terms:
        return "No searchable terms found after applying query filters."
    scored = _score_nodes(G, terms)
    if scoped_nodes is not None:
        scored = [item for item in scored if item[1] in scoped_nodes]

    memory_mode = None
    exclude_memory = False
    memory_ids = _get_trigram_index(G)["memory_ids"]
    if directives.include_memory:
        memory_mode = "included"
    else:
        non_memory = [item for item in scored if item[1] not in memory_ids]
        if non_memory:
            scored = non_memory
            exclude_memory = True
        elif scored:
            memory_mode = "fallback"

    scored, stage = _stage_candidates(
        G,
        scored,
        search_text,
        include_memory=directives.include_memory,
        global_quota=0 if scope_labels else 2,
    )
    eligible_ids = {nid for _, nid in scored}
    start_nodes = _pick_seeds(
        scored,
        G=G,
        terms=terms,
        eligible_ids=eligible_ids,
    )
    if not start_nodes:
        return "No matching nodes found."
    resolved_filters, filter_source = _resolve_context_filters(question, context_filters)
    traversal_graph = G if scoped_nodes is None else G.subgraph(scoped_nodes).copy()
    traversal_graph = _filter_graph_by_context(traversal_graph, resolved_filters)
    node_budget = max(len(start_nodes), max(4, token_budget // 24))
    traversal = _dfs if mode == "dfs" else _bfs
    nodes, edges = traversal(
        traversal_graph,
        start_nodes,
        depth,
        max_nodes=node_budget,
        excluded_nodes=memory_ids if exclude_memory else None,
    )
    safe_starts = [sanitize_label(str(G.nodes[n].get("label") or n)) for n in start_nodes]
    header_parts = [
        f"Traversal: {sanitize_label(mode.upper())} depth={depth}",
        f"Start: {safe_starts}",
    ]
    if scope_labels:
        header_parts.append(f"Filter: {', '.join(scope_labels)}")
    if memory_mode:
        header_parts.append(f"Memory: {memory_mode}")
    if stage["scopes"]:
        header_parts.append(f"Scopes: {', '.join(stage['scopes'])}")
    if stage["communities"]:
        header_parts.append(
            "Candidate communities: "
            + ", ".join(sanitize_label(str(cid)) for cid in stage["communities"])
        )
    if stage["global"]:
        header_parts.append(f"Global candidates: {stage['global']}")
    if stage["cross_community"]:
        header_parts.append(f"Cross-community candidates: {stage['cross_community']}")
    if resolved_filters:
        header_parts.append(f"Context: {', '.join(resolved_filters)} ({filter_source})")
    header_parts.append(f"{len(nodes)} nodes found (budget cap {node_budget})")
    header = " | ".join(header_parts) + "\n\n"
    return header + _subgraph_to_text(
        traversal_graph,
        nodes,
        edges,
        token_budget,
        seeds=start_nodes,
    )


def _find_node(G: nx.Graph, label: str) -> list[str]:
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
        G.nodes(data=True) if candidate_ids is None
        else ((nid, G.nodes[nid]) for nid in candidate_ids)
    )
    for nid, d in node_iter:
        norm_label = d.get("norm_label") or _strip_diacritics(d.get("label") or "").lower()
        bare_label = norm_label.rstrip("()")
        label_tokens = " ".join(_search_tokens(d.get("label") or ""))
        source_tokens = " ".join(_search_tokens(d.get("source_file") or ""))
        nid_lower = nid.lower()
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
            if str(G.nodes[nid].get("source_location", "")) == "L1"
            and _strip_diacritics(str(G.nodes[nid].get("label") or "")).lower()
            == query_basename
        ]
        if len(preferred) == 1:
            source_exact = preferred + [nid for nid in source_exact if nid != preferred[0]]

    return source_exact + exact + prefix + substring


@dataclass(frozen=True)
class _NodeResolution:
    node_id: str | None
    candidates: tuple[str, ...] = ()


def _node_identity(G: nx.Graph, nid: str) -> str:
    data = G.nodes[nid]
    label = str(data.get("label") or nid)
    source = str(data.get("source_file") or "")
    return f"{source}::{label}" if source else label


_MAX_LOOKUP_PATH_LENGTH = 4096
_MAX_LOOKUP_PATH_COMPONENTS = 256
_MAX_LOOKUP_PATH_COMPONENT_LENGTH = 255


def _normalize_lookup_path(value) -> str | None:
    """Return a bounded, case-folded path for exact and suffix comparisons."""
    raw = str(value).replace("\\", "/").strip()
    if not raw or len(raw) > _MAX_LOOKUP_PATH_LENGTH:
        return None
    raw = _strip_diacritics(raw).lower()
    if len(raw) > _MAX_LOOKUP_PATH_LENGTH:
        return None
    parts: list[str] = []
    for part in raw.split("/"):
        if not part or part == ".":
            continue
        if len(part) > _MAX_LOOKUP_PATH_COMPONENT_LENGTH:
            return None
        parts.append(part)
        if len(parts) > _MAX_LOOKUP_PATH_COMPONENTS:
            return None
    return "/".join(parts) or None


def _bounded_source_basename(value) -> str | None:
    raw = str(value).replace("\\", "/").rstrip("/")
    basename = raw.rsplit("/", 1)[-1]
    if (
        not basename
        or basename in {".", ".."}
        or len(basename) > _MAX_LOOKUP_PATH_COMPONENT_LENGTH
    ):
        return None
    basename = _strip_diacritics(basename).lower()
    return (
        basename
        if len(basename) <= _MAX_LOOKUP_PATH_COMPONENT_LENGTH
        else None
    )


def _get_node_lookup_index(G: nx.Graph) -> dict:
    """Graph-scoped exact lookup tables, invalidated when the graph object is replaced."""
    cached = G.graph.get("_node_lookup_index")
    if cached is not None and cached.get("node_count") == len(G):
        return cached

    folded_ids: dict[str, list[str]] = {}
    source_exact: dict[str, list[str]] = {}
    source_basenames: dict[str, list[str]] = {}
    labels: dict[str, list[str]] = {}

    def add(index: dict, key: str, nid: str) -> None:
        if key:
            index.setdefault(key, []).append(nid)

    for nid, data in G.nodes(data=True):
        nid_text = str(nid)
        add(folded_ids, nid_text.lower(), nid)

        label = _strip_diacritics(str(data.get("label") or nid)).lower()
        for key in {label, label.rstrip("()"), " ".join(_search_tokens(label))}:
            add(labels, key, nid)

        source = data.get("source_file") or ""
        normalized_source = _normalize_lookup_path(source)
        if normalized_source:
            add(source_exact, normalized_source, nid)
        basename = _bounded_source_basename(source)
        if basename:
            add(source_basenames, basename, nid)

    result = {
        "node_count": len(G),
        "folded_ids": folded_ids,
        "source_exact": source_exact,
        "source_basenames": source_basenames,
        "labels": labels,
    }
    G.graph["_node_lookup_index"] = result
    return result


def _lookup_node_scope(G: nx.Graph, nid: str) -> str:
    return _get_trigram_index(G)["scopes"][nid]


def _eligible_candidates(candidates, eligible_ids: set[str] | None) -> list[str]:
    if eligible_ids is None:
        return list(candidates)
    return [nid for nid in candidates if nid in eligible_ids]


def _rank_resolution_candidates(G: nx.Graph, node_ids) -> tuple[str, ...]:
    return tuple(sorted(
        dict.fromkeys(node_ids),
        key=lambda nid: (
            str(G.nodes[nid].get("source_file") or ""),
            str(G.nodes[nid].get("source_location") or ""),
            str(nid),
        ),
    ))


def _resolve_node(
    G: nx.Graph,
    query: str,
    *,
    eligible_ids: set[str] | None = None,
) -> _NodeResolution:
    """Resolve an ID, path-qualified identity, or readable label without guessing."""
    raw = str(query).strip()
    if not raw:
        return _NodeResolution(None)

    if raw in G and (eligible_ids is None or raw in eligible_ids):
        return _NodeResolution(raw)
    lookup = _get_node_lookup_index(G)
    folded_ids = _eligible_candidates(lookup["folded_ids"].get(raw.lower(), ()), eligible_ids)
    if len(folded_ids) == 1:
        return _NodeResolution(folded_ids[0])
    if len(folded_ids) > 1:
        return _NodeResolution(None, _rank_resolution_candidates(G, folded_ids))

    if "::" in raw:
        source_query, label_query = raw.rsplit("::", 1)
        normalized_source = _normalize_lookup_path(source_query)
        if normalized_source is None:
            return _NodeResolution(None)
        normalized_label = _strip_diacritics(label_query).lower().strip()
        exact_source = lookup["source_exact"].get(normalized_source, ())
        source_candidates = exact_source or lookup["source_basenames"].get(
            normalized_source.rsplit("/", 1)[-1], ()
        )
        qualified = []
        for nid in _eligible_candidates(
            source_candidates, eligible_ids
        ):
            data = G.nodes[nid]
            candidate_source = _normalize_lookup_path(data.get("source_file") or "")
            if candidate_source is None or (
                candidate_source != normalized_source
                and not candidate_source.endswith(f"/{normalized_source}")
            ):
                continue
            label = _strip_diacritics(str(data.get("label") or nid)).lower()
            if normalized_label in {label, label.rstrip("()"), " ".join(_search_tokens(label))}:
                qualified.append(nid)
        if len(qualified) == 1:
            return _NodeResolution(qualified[0])
        return _NodeResolution(None, _rank_resolution_candidates(G, qualified))

    normalized_source = _normalize_lookup_path(raw)
    source_matches: list[str] = []
    if normalized_source:
        exact_source = lookup["source_exact"].get(normalized_source, ())
        source_candidates = exact_source or lookup["source_basenames"].get(
            normalized_source.rsplit("/", 1)[-1], ()
        )
        source_matches = [
            nid
            for nid in _eligible_candidates(source_candidates, eligible_ids)
            if (candidate_source := _normalize_lookup_path(
                G.nodes[nid].get("source_file") or ""
            )) is not None
            and (
                candidate_source == normalized_source
                or candidate_source.endswith(f"/{normalized_source}")
            )
        ]
    if source_matches:
        basename = _strip_diacritics(Path(raw).name).lower()
        file_nodes = [
            nid for nid in source_matches
            if str(G.nodes[nid].get("source_location") or "") == "L1"
            and _strip_diacritics(str(G.nodes[nid].get("label") or "")).lower() == basename
        ]
        if len(file_nodes) == 1:
            return _NodeResolution(file_nodes[0])
        if len(source_matches) == 1:
            return _NodeResolution(source_matches[0])
        return _NodeResolution(None, _rank_resolution_candidates(G, source_matches))

    normalized = _strip_diacritics(raw).lower()
    exact_labels = _eligible_candidates(lookup["labels"].get(normalized, ()), eligible_ids)
    if len(exact_labels) == 1:
        return _NodeResolution(exact_labels[0])
    if len(exact_labels) > 1:
        return _NodeResolution(None, _rank_resolution_candidates(G, exact_labels))

    scored = _score_nodes(G, _query_terms(raw))
    if eligible_ids is not None:
        scored = [item for item in scored if item[1] in eligible_ids]
    if not scored:
        return _NodeResolution(None)
    selected = _pick_scored_endpoint(G, scored, raw)
    query_tokens = set(_search_tokens(raw))
    full_token_matches = [
        nid for _, nid in scored
        if query_tokens <= set(_search_tokens(G.nodes[nid].get("label") or nid))
    ]
    if len(full_token_matches) == 1:
        return _NodeResolution(full_token_matches[0])
    if len(full_token_matches) > 1:
        return _NodeResolution(None, _rank_resolution_candidates(G, full_token_matches))
    tied = [nid for score, nid in scored if score == scored[0][0]]
    if len(tied) > 1:
        return _NodeResolution(None, _rank_resolution_candidates(G, tied))
    return _NodeResolution(selected)


def _format_resolution_error(
    G: nx.Graph,
    query: str,
    resolution: _NodeResolution,
    role: str = "node",
) -> str:
    safe_query = sanitize_label(str(query))
    safe_role = sanitize_label(str(role))
    if not resolution.candidates:
        return f"No node matching {safe_role} '{safe_query}' found."
    lines = [
        f"Ambiguous {safe_role} '{safe_query}'. Use a path-qualified identity or exact node ID:"
    ]
    for nid in resolution.candidates[:8]:
        identity = sanitize_label(_node_identity(G, nid))
        safe_nid = sanitize_label(str(nid))
        lines.append(f"  - {identity} [id={safe_nid}]")
    return "\n".join(lines)


def _filter_directive(kind: str, value: object) -> str | None:
    raw = str(value)
    clean = sanitize_label(raw)
    if not clean or clean != raw:
        return None
    if not re.search(r"[\s\"']", clean):
        return f"{kind}:{clean}"
    if '"' not in clean:
        return f'{kind}:"{clean}"'
    if "'" not in clean:
        return f"{kind}:'{clean}'"
    return None


def _filter_suggestions(value: str, choices: list[tuple[str, str | None]]) -> list[str]:
    if not choices:
        return []
    by_search = {search: directive for search, directive in choices if directive}
    matches = get_close_matches(value, list(by_search), n=5, cutoff=0.2)
    ranked = matches or list(by_search)[:5]
    return list(dict.fromkeys(by_search[match] for match in ranked))


def _get_god_records(G: nx.Graph) -> list[dict]:
    cached = G.graph.get("_god_filter_records")
    if cached is not None and cached.get("node_count") == len(G):
        return cached["records"]
    from graphify.analyze import god_nodes

    records = god_nodes(G, top_n=len(G))
    G.graph["_god_filter_records"] = {"node_count": len(G), "records": records}
    return records


def _resolve_query_scope(
    G: nx.Graph,
    directives: _QueryDirectives,
) -> tuple[set[str] | None, list[str], str | None]:
    if directives.community is None and directives.god is None:
        return None, [], None

    lookup = _get_trigram_index(G)
    allowed: set[str] | None = None
    labels: list[str] = []

    if directives.community is not None:
        communities = lookup["community_names"]
        value = directives.community.strip()
        if not value:
            return set(), [], (
                "Community filter value cannot be empty. "
                "Use community:<id|label>."
            )
        matched = [cid for cid, name in communities.items() if str(cid) == value]
        if not matched:
            folded = _strip_diacritics(value).lower()
            matched = [
                cid for cid, name in communities.items()
                if _strip_diacritics(name).lower() == folded
            ]
        if len(matched) != 1:
            choices = [
                (f"{cid} {name}", _filter_directive("community", cid))
                for cid, name in sorted(communities.items(), key=lambda item: str(item[0]))
            ]
            suggestions = _filter_suggestions(value, choices)
            suffix = f" Suggestions: {', '.join(suggestions)}." if suggestions else ""
            safe_value = sanitize_label(value)
            return set(), [], f"Unknown or ambiguous community filter '{safe_value}'.{suffix}"
        cid = matched[0]
        allowed = set(lookup["community_nodes"][cid])
        safe_cid = sanitize_label(str(cid))
        labels.append(f"community:{safe_cid} ({sanitize_label(communities[cid])})")

    if directives.god is not None:
        if not directives.god.strip():
            return set(), [], (
                "God filter value cannot be empty. Use god:<label|id>."
            )
        god_records = _get_god_records(G)
        god_ids = {record["id"] for record in god_records}
        resolution = _resolve_node(G, directives.god, eligible_ids=god_ids)
        if resolution.node_id is None:
            if resolution.candidates:
                suggestions = [
                    directive
                    for nid in resolution.candidates[:5]
                    if (directive := _filter_directive("god", nid)) is not None
                ]
                suffix = f" Suggestions: {', '.join(suggestions)}." if suggestions else ""
                safe_value = sanitize_label(directives.god)
                return set(), [], f"Ambiguous god filter '{safe_value}'.{suffix}"
            choices = [
                (
                    f"{record['id']} {record['label']}",
                    _filter_directive("god", record["id"]),
                )
                for record in god_records
            ]
            suggestions = _filter_suggestions(directives.god, choices)
            suffix = f" Suggestions: {', '.join(suggestions)}." if suggestions else ""
            safe_value = sanitize_label(directives.god)
            return set(), [], f"Unknown god filter '{safe_value}'.{suffix}"
        god_id = resolution.node_id
        neighborhood = {god_id, *G.to_undirected(as_view=True).neighbors(god_id)}
        allowed = neighborhood if allowed is None else allowed & neighborhood
        labels.append(f"god:{sanitize_label(str(G.nodes[god_id].get('label') or god_id))}")

    if allowed is not None and not allowed:
        return set(), labels, "The requested community/god filters have no nodes in common."
    return allowed, labels, None


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
    # output which read the community_name attribute to_json writes onto nodes.
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
    Streamable HTTP) and runs it. Hot-reload of graph.json works the same way
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

    # Per-graph context cache: resolved graph.json path -> {key, G, communities}.
    # The server's default graph is just the first entry; a tool call carrying a
    # project_path adds its own. Routing every graph through one cache means the
    # eager trigram index and the mtime+size hot-reload behave identically for
    # the default graph and for any project graph.
    _default_graph_path = graph_path
    _ctx_lock = threading.Lock()
    _ctx_cache: dict[str, dict] = {}

    def _load_ctx(path: str):
        """Return (G, communities) for a graph.json path, reusing a cached
        context until the file's (mtime, size) changes and then transparently
        rebuilding it. Unlike ``_load_graph`` it never exits the process on a
        missing/corrupt file — it raises, so a bad project_path surfaces as a
        tool error instead of killing a server that is happily serving other
        projects."""
        try:
            key = _query_context_key(path)
        except FileNotFoundError:
            raise FileNotFoundError(f"graph.json not found: {path}")
        ent = _ctx_cache.get(path)
        if ent is not None and ent["key"] == key:
            return ent["G"], ent["communities"]
        with _ctx_lock:
            ent = _ctx_cache.get(path)
            if ent is not None and ent["key"] == key:
                return ent["G"], ent["communities"]  # another thread built it
            try:
                new_G = _load_graph(path)
            except SystemExit as e:  # _load_graph exits on missing/corrupt file
                raise RuntimeError(f"could not load graph.json at {path}") from e
            # Warm the trigram index before exposing the graph so the first query
            # against it is fast (same rationale as the original startup warm-up).
            _get_trigram_index(new_G)
            _get_node_lookup_index(new_G)
            comm = _communities_from_graph(new_G)
            _ctx_cache[path] = {"key": key, "G": new_G, "communities": comm}
            return new_G, comm

    def _resolve_graph_path(project_path) -> str:
        """Map an optional project_path to a concrete graph.json path. ``None``
        keeps the server's default graph (backward-compatible); a project_path
        resolves to ``<project_path>/<GRAPHIFY_OUT>/graph.json``, honouring the
        GRAPHIFY_OUT override so worktree/shared-output setups keep working."""
        if not project_path:
            return _default_graph_path
        return str(Path(project_path) / _paths.GRAPHIFY_OUT / "graph.json")

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
                description=(
                    "Search the knowledge graph using staged BFS or DFS. Query filters: "
                    "include:memory, community:<id|label>, god:<label>."
                ),
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
                description="Get a node by label, exact ID, or path::label identity.",
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
                    "graphify-out/graph.json. Optional — defaults to the graph "
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
        label = arguments["label"]
        resolution = _resolve_node(G, label)
        if resolution.node_id is None:
            return _format_resolution_error(G, label, resolution)
        nid = resolution.node_id
        d = G.nodes[nid]
        # Sanitise every LLM-derived field before concatenation (F-010).
        return "\n".join([
            f"Node: {sanitize_label(d.get('label', nid))}",
            f"  ID: {sanitize_label(nid)}",
            f"  Source: {sanitize_label(_source_display(d))}",
            f"  Type: {sanitize_label(str(d.get('file_type', '')))}",
            f"  Community: {sanitize_label(str(d.get('community_name') or d.get('community', '')))}",
            f"  Degree: {G.degree(nid)}",
        ])

    def _tool_get_neighbors(arguments: dict) -> str:
        label = arguments["label"]
        rel_filter = arguments.get("relation_filter", "").lower()
        resolution = _resolve_node(G, label)
        if resolution.node_id is None:
            return _format_resolution_error(G, label, resolution)
        nid = resolution.node_id
        lines = [f"Neighbors of {sanitize_label(G.nodes[nid].get('label', nid))}:"]
        for nb in G.successors(nid):
            d = edge_data(G, nid, nb)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(
                f"  --> {sanitize_label(G.nodes[nb].get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]"
            )
        for nb in G.predecessors(nid):
            d = edge_data(G, nb, nid)
            rel = d.get("relation", "")
            if rel_filter and rel_filter not in rel.lower():
                continue
            lines.append(
                f"  <-- {sanitize_label(G.nodes[nb].get('label', nb))} "
                f"[{sanitize_label(str(rel))}] [{sanitize_label(str(d.get('confidence', '')))}]"
            )
        return "\n".join(lines)

    def _tool_get_community(arguments: dict) -> str:
        cid = int(arguments["community_id"])
        nodes = communities.get(cid, [])
        if not nodes:
            return f"Community {cid} not found."
        header = _community_header(cid, G.nodes[nodes[0]].get("community_name"))
        lines = [f"{header} ({len(nodes)} nodes):"]
        for n in nodes:
            d = G.nodes[n]
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
        lines += [
            f"  {i}. {sanitize_label(str(n['label']))} - {n['degree']} edges"
            for i, n in enumerate(nodes, 1)
        ]
        return "\n".join(lines)

    def _tool_graph_stats(_: dict) -> str:
        confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
        total = len(confs) or 1
        return (
            f"Nodes: {G.number_of_nodes()}\n"
            f"Edges: {G.number_of_edges()}\n"
            f"Communities: {len(communities)}\n"
            f"EXTRACTED: {round(confs.count('EXTRACTED')/total*100)}%\n"
            f"INFERRED: {round(confs.count('INFERRED')/total*100)}%\n"
            f"AMBIGUOUS: {round(confs.count('AMBIGUOUS')/total*100)}%\n"
        )

    def _tool_shortest_path(arguments: dict) -> str:
        src_resolution = _resolve_node(G, arguments["source"])
        tgt_resolution = _resolve_node(G, arguments["target"])
        if src_resolution.node_id is None:
            return _format_resolution_error(
                G, arguments["source"], src_resolution, role="source"
            )
        if tgt_resolution.node_id is None:
            return _format_resolution_error(
                G, arguments["target"], tgt_resolution, role="target"
            )
        src_nid = src_resolution.node_id
        tgt_nid = tgt_resolution.node_id
        # Ambiguity guard: when both queries resolve to the same node, the
        # shortest path is trivially zero hops, which is almost never what the
        # caller wanted (see bug #828).
        if src_nid == tgt_nid:
            return (
                f"'{sanitize_label(str(arguments['source']))}' and "
                f"'{sanitize_label(str(arguments['target']))}' both resolved to "
                f"the same node '{sanitize_label(str(src_nid))}'. "
                "Use a more specific label or the exact node ID."
            )
        max_hops = int(arguments.get("max_hops", 8))
        try:
            # Use undirected view for path-finding (works regardless of query src/tgt order)
            path_nodes = nx.shortest_path(G.to_undirected(as_view=True), src_nid, tgt_nid)
        except (nx.NetworkXNoPath, nx.NodeNotFound):
            source = sanitize_label(str(G.nodes[src_nid].get("label") or src_nid))
            target = sanitize_label(str(G.nodes[tgt_nid].get("label") or tgt_nid))
            return f"No path found between '{source}' and '{target}'."
        hops = len(path_nodes) - 1
        if hops > max_hops:
            return f"Path exceeds max_hops={max_hops} ({hops} hops found)."
        segments = []
        for i in range(len(path_nodes) - 1):
            u, v = path_nodes[i], path_nodes[i + 1]
            if G.has_edge(u, v):
                edata = edge_data(G, u, v)
                forward = True
            else:
                edata = edge_data(G, v, u)
                forward = False
            rel = edata.get("relation", "")
            conf = edata.get("confidence", "")
            safe_rel = sanitize_label(str(rel))
            conf_str = f" [{sanitize_label(str(conf))}]" if conf else ""
            if i == 0:
                segments.append(sanitize_label(str(G.nodes[u].get("label") or u)))
            neighbor = sanitize_label(str(G.nodes[v].get("label") or v))
            if forward:
                segments.append(f"--{safe_rel}{conf_str}--> {neighbor}")
            else:
                segments.append(f"<--{safe_rel}{conf_str}-- {neighbor}")
        return f"Shortest path ({hops} hops):\n  " + " ".join(segments)

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
        comms, nodes = compute_pr_impact(files, G)
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
                    pr.communities_touched, pr.nodes_affected = compute_pr_impact(files, G)
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
        labels_path = Path(active_graph_path).parent / ".graphify_labels.json"
        if labels_path.exists():
            try:
                return {int(k): v for k, v in json.loads(labels_path.read_text(encoding="utf-8")).items()}
            except Exception:
                pass
        return {cid: f"Community {cid}" for cid in communities}

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
            confs = [d.get("confidence", "EXTRACTED") for _, _, d in G.edges(data=True)]
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
        arguments = dict(arguments or {})
        project_path = arguments.pop("project_path", None)
        handler = _handlers.get(name)
        if not handler:
            return [types.TextContent(type="text", text=f"Unknown tool: {name}")]
        try:
            _select_graph(project_path)  # bind G/communities to the target graph
            return [types.TextContent(type="text", text=handler(arguments))]
        except Exception as exc:
            return [types.TextContent(type="text", text=f"Error executing {name}: {exc}")]

    return server


def serve(graph_path: str | None = None) -> None:
    """Start the MCP server over stdio (the default, per-developer transport)."""
    graph_path = graph_path or _default_graph_json()
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
    if host in ("0.0.0.0", "::", ""):
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
    graph_path = graph_path or _default_graph_json()
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
    if host in ("0.0.0.0", "::", "") and not api_key:
        print(
            f"WARNING: binding {host or '0.0.0.0'} with no api-key exposes the graph "
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
        help="Path to graph.json (default: graphify-out/graph.json)",
    )
    parser.add_argument(
        "--graph",
        dest="graph_flag",
        default=None,
        metavar="PATH",
        help="Path to graph.json — alias for the positional argument",
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
    graph_path = args.graph_flag or args.graph_path or _default_graph_json()

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
