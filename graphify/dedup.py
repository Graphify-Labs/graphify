"""Entity deduplication pipeline for graphify knowledge graphs.

Pipeline: exact normalization → entropy gate → MinHash/LSH blocking →
Jaro-Winkler verification → same-community boost → union-find merge.
"""
from __future__ import annotations
import math
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

from graphify._minhash import MinHash, MinHashLSH
from graphify.ids import normalize_id
from rapidfuzz.distance import DamerauLevenshtein, Jaro, JaroWinkler


# ── helpers ───────────────────────────────────────────────────────────────────

def _is_label_char(ch: str) -> bool:
    """True for a character that belongs to a word in a label.

    Letters and digits, plus combining marks (Unicode category M*). ``\\w`` does
    not match marks, so the old ``[\\W_]+`` separator class deleted every vowel
    sign and virama: ``हिंदी`` became ``ह द`` and ``कि``/``की``/``के`` all
    collapsed to ``क``, merging distinct words.
    """
    return ch.isalnum() or unicodedata.category(ch).startswith("M")


def _norm(label: str | None) -> str:
    """Lowercase + collapse non-word runs to space (Unicode-aware).

    Combining marks stay part of the word (see ``_is_label_char``); punctuation,
    underscores and whitespace collapse to a single space as before. Known gap:
    ZWJ/ZWNJ (category Cf) still count as separators.
    """
    if not isinstance(label, str):
        label = "" if label is None else str(label)
    label = unicodedata.normalize("NFKC", label).casefold()
    out: list[str] = []
    pending_sep = False
    for ch in label:
        if _is_label_char(ch):
            if pending_sep and out:
                out.append(" ")
            pending_sep = False
            out.append(ch)
        else:
            pending_sep = True
    return "".join(out)


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


# Function words. A restatement of one entity is what inserts or swaps these
# ("export a read-only ..." vs "export the read-only ..."); a content word
# carries the entity's identity and swapping one names something else.
_STOPWORDS = frozenset({
    "a", "an", "the", "and", "or", "of", "for", "to", "in", "on", "at", "by",
    "with", "from", "as", "is", "are", "be", "this", "that", "its",
})


def _same_word_variant(x: str, y: str) -> bool:
    """True when tokens x and y read as one word misspelt, not two words (#2576).

    A same-length pair within one substitution/transposition is a typo
    ("manager"/"nanager") -- the same rationale _short_label_blocked applies
    to whole short labels, and unlike Jaro-Winkler it holds at position 0,
    where the prefix bonus gives no help (JW scores "manager"/"nanager" at
    84.92, below threshold, yet it is as much a typo as "managr"). Below 6
    chars JW cannot separate two words from a typo ("pane"/"plane" scores
    94.0), so short length-differing pairs never read as variants. Longer
    pairs fall back to Jaro-Winkler on the merge threshold, so
    "manager"/"managr" (97.14) still reads as one word. Accepted trade, per
    the never-merge-two-distinct-entities bar: "colour"/"color" (5 chars,
    lengths differ) now reads as two words and stays unmerged -- a spelling
    variant kept separate beats a fabricated merge.
    """
    if len(x) == len(y) and DamerauLevenshtein.distance(x, y) <= 1:
        return True   # same-length 1-sub/transposition = typo, even at position 0
    if min(len(x), len(y)) < 6:
        return False  # short tokens: JW can't separate pane/plane (94.0) from a typo
    return JaroWinkler.normalized_similarity(x, y) * 100 >= _MERGE_THRESHOLD


def _content_token_swap(a: str, b: str) -> bool:
    """True when two equal-token-count labels differ in at least one swapped
    content word rather than only typos or function words (#2576, adopted
    from @wilyan09007's PR #2587 and generalized from exactly-one to any
    number of differing positions).

    Whole-string scoring cannot separate a legit restatement from a
    distinguishing-token swap: both edit one short run in the middle of a long
    shared string, so both land in the same Jaro band (#1243). Which token
    differs does separate them. Structured prose names sibling sections from a
    template ("Asset Contribution Flow" / "Asset Consumption Flow", four
    consecutive headings of one operations doc), and those siblings are densest
    inside a single file -- exactly where Jaro-Winkler's prefix bonus still
    applies, and where the shared affixes it rewards are boilerplate.

    Each same-position differing pair is judged on its own: a function word on
    either side is what a restatement swaps, a _same_word_variant pair is one
    word misspelt, and anything else is a distinct content word naming a
    different entity -- one such pair blocks the merge. A restatement differs
    only in stopwords/typos at every position; a template sibling differs in
    at least one distinct content word ("... Contribution Flow Handler" vs
    "... Consumption Flows Handler" blocks on either position). Pairs with
    different token counts are left to the prefix-extension guard (#1201) and
    whole-label scoring. Known gap, out of scope here: fused camelCase labels
    ("AssetContributionFlow" vs "AssetConsumptionFlow") normalize to single
    tokens whose only differing "position" is the whole label, so this guard
    reduces to whole-token _same_word_variant and long fused pairs can still
    clear the JW fallback.
    """
    tokens_a, tokens_b = a.split(), b.split()
    if len(tokens_a) != len(tokens_b):
        return False
    for x, y in zip(tokens_a, tokens_b):
        if x == y:
            continue
        if x in _STOPWORDS or y in _STOPWORDS:
            continue  # restatement: a function word swapped in or out
        if _same_word_variant(x, y):
            continue  # one word misspelt/inflected, not a different word
        return True
    return False


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


# ── ID collisions ─────────────────────────────────────────────────────────────

_EXTENSION = re.compile(r"\.[^./]+$")


def _id_prefixes(source_file: str) -> set[str]:
    """The ID prefixes a node extracted from ``source_file`` may legitimately mint.

    An ID is ``<path>_<entity>``, where the path is the extension-stripped source
    path, each segment slugified and joined with ``_``. Every trailing slice of the
    path counts as a prefix: the stored path may be absolute or repo-relative, and
    graphs built under the pre-#1504 scheme keyed off the bare filename stem.

    Each segment is slugified with ``normalize_id`` (#3352), the same
    Unicode-aware casefold-then-NFKC-then-``[^\\w]+`` recipe every real ID is
    minted with. An ASCII-only slug here silently dropped every non-Latin
    character (Korean, CJK, Cyrillic, ...) instead of preserving it, so a
    node's own defining file was never recognized as the file that ID
    encodes and the definer-wins collision rule (see ``_defines_id``,
    ``_collision_rank``) fell through to arrival-order for any such path.
    """
    stem = _EXTENSION.sub("", source_file.replace("\\", "/"))
    segments = [s for s in (normalize_id(p) for p in stem.split("/")) if s]
    return {"_".join(segments[i:]) for i in range(len(segments))}


def _defines_id(node: dict) -> bool:
    """True when the node's own source_file is the file its ID encodes.

    A doc that *references* an entity mints the ID of the entity's own file, not one
    derived from the doc's path — so the referencing node collides with the defining
    node by construction. This separates the two: the definer owns the ID.
    """
    nid = node.get("id") or ""
    source_file = node.get("source_file") or ""
    if not nid or not source_file:
        return False
    # `nid == prefix` covers a bare file-level node whose id is exactly the
    # slugified path with no `_entity` suffix (a semantic node for the file
    # itself); `startswith(prefix + "_")` covers the usual `<path>_<entity>` id.
    return any(nid == prefix or nid.startswith(f"{prefix}_")
               for prefix in _id_prefixes(source_file))


# `node_kind` values marking a node that is STRUCTURE of its source file rather
# than an entity mentioned inside it: `page` is the file's own node, `heading`
# one of its sections. The markdown extractor stamps these precisely because
# `file_type` cannot carry the distinction, and both are file-anchored in the
# #1284 sense — two files' `## Decisions` sections are two sections (#3094).
#
# PRODUCER CONTRACT: an extractor that mints a node standing for a *part* of its
# source file (a section, a sheet, a slide) must stamp one of these. The gate
# below reads an unstamped node as an entity, so an unstamped structural node is
# eligible to merge with its namesake in another file.
_FILE_STRUCTURE_NODE_KINDS = frozenset({"page", "heading"})


def _reads_as_file_entity(node: dict) -> bool:
    """True when the node reads as an entity found inside its file, rather than
    as the file itself or a stamped structural part of it (#296).

    Be precise about what is proven and what is assumed, because the two halves
    differ in strength:

    * PROVEN — it is not its file's OWN node. ``_id_prefixes`` enumerates the ID
      a node standing for ``source_file`` itself would carry, in every spelling
      a stored path may take (absolute, repo-relative, or the pre-#1504 bare
      stem). A file's own node IS one of those; an entity extracted from that
      file carries an ``_<entity>`` suffix, so it never equals one. This is a
      reconstruction, not a heuristic.
    * ASSUMED — it is not a section of the file. That rests on ``node_kind``,
      which only a producer that stamps it can attest. `heading`/`page` are
      honoured when present, but ABSENCE OF THE MARKER IS NOT PROOF OF
      ENTITY-NESS: a producer minting sub-file nodes without stamping
      `node_kind` (see the contract above) yields structural nodes that this
      returns True for, and two such nodes sharing a label in different files
      would merge. The conservative fix is on the producer side — stamp
      `node_kind` — not a guess here about what an unstamped node meant.

    A node that cannot be checked at all (no ID, no provenance) answers False
    and stays blocked.
    """
    nid = node.get("id") or ""
    source_file = node.get("source_file") or ""
    if not nid or not source_file:
        return False  # uncheckable — leave the file-anchored block in place
    if node.get("node_kind") in _FILE_STRUCTURE_NODE_KINDS:
        return False  # the extractor says this node is part of the file's structure
    return nid not in _id_prefixes(source_file)


# Path-segment lifecycle markers used by _collision_rank (#2532). Lower penalty
# wins. Without them, pure lexical source_file order makes ``plans/_done/…``
# beat ``plans/in-progress/…`` because "_" < "i" in ASCII. Active-vs-archived
# marker idea by @michaelxer (#2540); matched against ROOT-RELATIVE directory
# segments only, so a checkout directory that happens to be named ``wip`` or
# ``done`` never leaks into the ranking.
_ACTIVE_PATH_SEGMENTS = frozenset({
    "in-progress",
    "in_progress",
    "active",
    "current",
    "wip",
})
_ARCHIVED_PATH_SEGMENTS = frozenset({
    "_done",
    "done",
    "archive",
    "archived",
    "backup",
    "bak",
    "old",
    "attic",
    "graveyard",
    "completed",
})


def _lifecycle_penalty(rank_path: str) -> int:
    """0 for active/in-progress paths, 2 for archived/done paths, 1 otherwise.

    Judged on the DIRECTORY segments of the root-relative rank path — a file
    literally named ``done.md`` is not a marker. Among mixed markers the best
    (lowest) score wins so an active segment is not drowned out by an unrelated
    archive directory higher in the tree (#2532).
    """
    segments = [s for s in rank_path.casefold().split("/") if s]
    marked = [
        0 if s in _ACTIVE_PATH_SEGMENTS else 2
        for s in segments[:-1]  # directories only, never the basename
        if s in _ACTIVE_PATH_SEGMENTS or s in _ARCHIVED_PATH_SEGMENTS
    ]
    return min(marked) if marked else 1


def _rank_path(source_file: str, root: Path | None) -> str:
    """The root-relative form of ``source_file`` used for collision ranking.

    With a scan root, an absolute stored path and its repo-relative twin rank
    identically, and the checkout location's own segments never participate
    (#2532). A relative stored path is already root-relative and is used as-is;
    unlike ``_source_key`` in extractors/resolution.py, it is not resolved
    against the CWD, so a run from a subdirectory of the root keys it the same
    (#4281). Without a root (or when relativizing fails) the normalized stored
    path is used as-is.
    """
    normalized = source_file.replace("\\", "/")
    if root is not None and normalized and Path(normalized).is_absolute():
        try:
            return Path(normalized).resolve().relative_to(root).as_posix()
        except Exception:
            pass
    return normalized


def _collision_rank(node: dict, root: Path | None = None,
                    mentions: "frozenset | set" = frozenset(),
                    outranked: "frozenset | set" = frozenset()) -> tuple:
    """A total order for choosing the survivor of an ID collision, independent of
    the order the colliding nodes arrive in.

    The winner is the node with the SMALLEST rank. A node whose ``source_file``
    defines the ID always outranks a mere reference, and a definer listed in
    ``outranked`` ranks behind the other definers (#4859); among equally-(non-)defining
    nodes an active/in-progress path outranks an archived/done one (#2532); then
    it prefers the shorter, more canonical label over a longer qualified variant,
    then breaks any remaining tie lexically on label and finally on the REVERSED
    segments of the root-relative path. Basename-first comparison decides two
    in-repo colliders by segments present in both path forms, so absolute and
    repo-relative spellings of the same layout order identically — fully
    deterministic regardless of arrival order (#1851) or checkout location.

    Neither side of the first key is exempt from the second: when the ID is
    encoded by neither node's own file, both read as mere references and tie
    there too, so a node with no ``source_file`` at all used to win purely on
    an empty reversed path sorting before any real one — the sourced node was
    the one actually telling us where the entity lives, and it was the one
    getting dropped (#4492). A ``source_file`` beats none right after the
    first key, mirroring the same rule ``_pick_winner`` already applies one
    level up (#3775/#3786). It changes no collision between two sourced
    nodes, since both sides of that key agree there.

    ``outranked`` (see ``_outranked_by_ast``) holds the ``(id, file)`` of non-AST
    definers that another file's AST node also defines. A doc whose own path
    prefixes a code entity's id (``pkg.md`` beside ``pkg/test_x.py``) defines it
    too, and used to take it on a shorter label, so its next re-extract deleted the
    code node (#4859). Such a definer now ranks right behind the other definers;
    same-file pairs (#2091), same-stem twins, and collisions with one definer
    rank as before.

    ``mentions`` (see ``_mentions``) holds the ``(id, file)`` of nodes read as a
    mention of a document rather than the document itself. Such a node ranks as a
    reference even though its id is a path slice, so a real document outranks it
    whatever the label lengths are (#4281). The set only ever contains path-slice
    ids, so the survivor of every other collision is chosen exactly as before. It
    also holds a shorter path-slice id from a file that has its own page
    (``_slice_references``), so a bare ``protocol`` inside docs/protocol.md cannot
    outrank the real top-level protocol.md on label length.
    """
    label = node.get("label") or ""
    rank_path = _rank_path(node.get("source_file") or "", root)
    key = (node.get("id"), rank_path)
    return (
        not _defines_id(node) or key in mentions,
        key in outranked and node.get("_origin") != "ast",  # (#4859)
        not node.get("source_file"),  # a located node beats a source-less one (#4492)
        _lifecycle_penalty(rank_path),  # active paths beat archived ones (#2532)
        len(label),             # shorter, more canonical label first
        label,                  # lexical tiebreak
        tuple(reversed([s for s in rank_path.split("/") if s and s != "."])),
    )


def _outranked_by_ast(nodes: list[dict], root: Path | None,
                      mentions: "frozenset | set") -> set[tuple[str, str]]:
    """``(id, root-relative file)`` of non-AST definers that an AST node from
    another file also defines, while their own file has no AST definer (#4859).

    The AST node is extracted fact and the other is an inference about it, so the
    AST node keeps the id. The check is strict on ``_origin == "ast"``, as in the
    build ghost pass: fresh semantic chunks arrive unstamped. A file that has its
    own AST definer (#2091 enrichment) is never listed, and an AST node with the
    same full stem (an ``x.py``/``x.html`` twin, or a slug twin such as
    ``pkg/service.py`` and ``pkg_service.py``) never counts against it.
    """
    ast_defs: dict[str, list[tuple[str, str]]] = defaultdict(list)
    others: list[tuple[str, str, str]] = []
    for node in nodes:
        nid = node.get("id") or ""
        source_file = node.get("source_file") or ""
        rank_path = _rank_path(source_file, root)
        if not nid or not _defines_id(node) or (nid, rank_path) in mentions:
            continue
        entry = (rank_path, _full_stem(source_file))
        if node.get("_origin") == "ast":
            ast_defs[nid].append(entry)
        else:
            others.append((nid, *entry))
    outranked = set()
    for nid, rank_path, stem in others:
        defs = ast_defs.get(nid, [])
        if (defs and rank_path not in {rp for rp, _ in defs}
                and any(ast_stem != stem for _, ast_stem in defs)):
            outranked.add((nid, rank_path))
    return outranked


def _mentions(nodes: list[dict], edges: list[dict],
              root: Path | None) -> set[tuple[str, str]]:
    """``(id, root-relative file)`` of nodes read as a MENTION of a document (#4281).

    A semantic fragment sometimes mints the bare id of a file it only points at:
    ``protocol`` inside docs/firmware/protocol.md, standing for docs/protocol.md. A
    node is read as such a mention when both hold:

    - another node of its OWN file points at it with a ``references`` edge whose own
      source_file is that file, and
    - its id is itself a path slice of that file (``_id_prefixes``), so it names a
      document. An entity id such as ``x_intro`` is the target of ordinary intra-file
      ``references`` edges and never counts.

    ``_path_qualify_dropped_collisions`` and ``_collision_rank`` both read this one
    set, so a single definition decides whether a mention is renamed and whether it
    loses a survivor tie.

    Heuristic boundary: this is INFERRED from the edges an LLM chose to emit, not
    stated by the source. A missing or reversed edge gives no evidence, and the id is
    then renamed per file like any other. A real document whose own node is linked to
    its file-level id the same way (an entity named like its file, which
    ``_doc_twin_remap`` already treats as the file itself) reads as a mention, and
    that collision collapses exactly as it did before.
    """
    def key(sf):
        return _rank_path(sf, root) if sf and isinstance(sf, str) else ""

    own: dict[str, set[str]] = defaultdict(set)
    for node in nodes:
        nid = node.get("id")
        if nid and isinstance(nid, str):
            own[key(node.get("source_file"))].add(nid)
    found: set[tuple[str, str]] = set()
    for edge in edges:
        if not isinstance(edge, dict) or edge.get("relation") != "references":
            continue
        k = key(edge.get("source_file"))
        source, target = edge.get("source"), edge.get("target")
        if (k and isinstance(source, str) and isinstance(target, str)
                and source != target and source in own[k] and target in own[k]
                and target in _id_prefixes(k)):
            found.add((target, k))
    return found


def _own_page_files(nodes: list[dict], root: Path | None) -> set[str]:
    """Root-relative files that have a node spelled with their own full stem (#4281).

    Such a file already has its page, so a shorter path-slice id it also mints
    (``protocol`` inside docs/protocol.md, next to ``docs_protocol``) may be a
    reference to another file rather than that file's own page."""
    from graphify.build import _is_abs  # local: build imports dedup

    files: set[str] = set()
    for node in nodes:
        nid, sf = node.get("id"), node.get("source_file")
        if not nid or not isinstance(nid, str) or not sf or not isinstance(sf, str):
            continue
        k = _rank_path(sf, root)
        if _is_abs(k):
            continue
        full = _full_stem(k)
        if nid == full or nid.startswith(f"{full}_"):
            files.add(k)
    return files


def _slice_references(nodes: list[dict], root: Path | None) -> set[tuple[str, str]]:
    """``(id, file)`` of nodes whose id is a SHORTER path slice of a file that has its
    own page (#4281). They rank as references, like a ``_mentions`` entry."""
    own_page = _own_page_files(nodes, root)
    found: set[tuple[str, str]] = set()
    for node in nodes:
        nid, sf = node.get("id"), node.get("source_file")
        if not nid or not isinstance(nid, str) or not sf or not isinstance(sf, str):
            continue
        k = _rank_path(sf, root)
        if k in own_page and nid in _id_prefixes(k) and nid != _full_stem(k):
            found.add((nid, k))
    return found


def _same_source_entity(survivor: dict, duplicate: dict) -> bool:
    """True when exact-ID records came from the same source file.

    Exact IDs can also collide across files through references or slugged-path
    ambiguity (#1504).  Keep those records isolated rather than importing
    attributes whose provenance belongs to another file.
    """
    keep_file = survivor.get("source_file") or ""
    lose_file = duplicate.get("source_file") or ""
    # Require a non-empty source_file: two provenance-less records ("" == "")
    # are NOT proof of the same symbol (#1178), and merging their attributes
    # would be a cross-pollination bug in the opposite direction (#2091 review).
    return bool(keep_file) and keep_file == lose_file


def _merge_missing_attributes(survivor: dict, duplicate: dict) -> dict:
    """Fill the survivor's absent/None attributes from a same-source duplicate,
    without overriding values the survivor already has (#2091)."""
    merged = dict(survivor)
    for key, value in duplicate.items():
        # Never inherit a provenance tag from a dropped record: a false
        # _origin="ast" on an LLM survivor is read as an authority signal by the
        # ghost-merge (#2068) and watch deletion logic (#2091 review).
        if key == "_origin":
            continue
        if value is None:
            continue
        # Treat an explicit None on the survivor as absent — the codebase emits
        # `source_location: None`, and that is exactly the attribute #2091 loses.
        if merged.get(key) is None:
            merged[key] = value
    return merged


_SHARED_ID_TYPES = ("module", "namespace")


def _report_id_collision(nid: str, survivor: dict, losers: list[dict]) -> None:
    """Report an ID collision in proportion to what dropping the loser actually costs.

    Cross-reference to a defining node: the structural entity and its edges survive;
    foreign-file attributes stay isolated, so no collision warning is needed. Same
    file, different labels: the extractor emitted two labels for one entity and one is
    discarded — note it. Two files that both encode this ID: they are distinct entities
    and one is genuinely lost — warn, and point at the extraction split that keeps them
    apart (#1504).
    """
    # A module/namespace node (`import Foundation`) is one shared entity that every
    # importing file legitimately mints — the same rule the extractors apply when
    # they exempt these types from collision disambiguation. Only a group of one
    # such type under one label is that shared entity; a module colliding with a
    # namespace, or two differently named modules, is still a real collision.
    group = (survivor, *losers)
    if (
        survivor.get("type") in _SHARED_ID_TYPES
        and all(n.get("type") == survivor.get("type") for n in group)
        and all(n.get("label") == survivor.get("label") for n in group)
    ):
        return
    keep_file = survivor.get("source_file") or ""
    keep_label = survivor.get("label") or ""
    for loser in losers:
        lose_file = loser.get("source_file") or ""
        lose_label = loser.get("label") or ""
        if lose_file == keep_file:
            if _norm(lose_label) != _norm(keep_label):
                print(
                    f"[graphify] note: node '{nid}' was extracted twice from "
                    f"'{keep_file}' under different labels — keeping '{keep_label}', "
                    f"dropping '{lose_label}'.",
                    file=sys.stderr,
                )
        elif _defines_id(survivor) and not _defines_id(loser):
            continue  # the loser only references the entity the survivor defines
        else:
            print(
                f"[graphify] WARNING: node '{nid}' is minted by two different files — "
                f"keeping '{keep_label}' from '{keep_file}', dropping '{lose_label}' "
                f"from '{lose_file}'. An ID is derived from the source path plus the "
                f"entity name, so this one does not identify a single entity and the "
                f"dropped node is lost. To keep them distinct, run 'graphify extract' "
                f"per subfolder and merge with 'graphify merge-graphs'.",
                file=sys.stderr,
            )


def _full_stem(source_file: str) -> str:
    """The extension-stripped, slugified full-path stem a file's own IDs start with."""
    stem = _EXTENSION.sub("", source_file.replace("\\", "/"))
    return "_".join(s for s in (normalize_id(p) for p in stem.split("/")) if s)


def _extension_qualified_id(node: dict) -> str | None:
    """``x.html``'s own spelling of an ID it shares with ``x.py`` (#4281).

    Only applies when the ID is spelled with the node's FULL path stem, i.e.
    the ID collides because the extension was stripped. Returns None for an ID
    that only matches a trailing path slice (a bare ``protocol``): that is a
    reference to another file's entity, not a distinct entity, and is left to
    the collapse-and-warn path.
    """
    nid = node.get("id") or ""
    source_file = node.get("source_file") or ""
    ext_match = _EXTENSION.search(source_file.replace("\\", "/"))
    full = _full_stem(source_file)
    if not (nid and full and ext_match):
        return None
    if nid != full and not nid.startswith(f"{full}_"):
        return None
    return f"{full}_{normalize_id(ext_match.group(0))}{nid[len(full):]}"


def _disambiguate_defining_collisions(
    nodes: list[dict], edges: list[dict], hyperedges: list[dict] | None,
    root: Path | None,
) -> tuple[list[dict], list[dict]]:
    """Keep ``x.py`` and ``x.html`` apart when both derive the same ID (#4281).

    The ID is built from the extension-stripped path, so two files that differ
    only by extension mint the same ID. The best-ranked file keeps it; the
    others get an extension-qualified ID. Edges and hyperedges follow the
    renamed node by ``source_file``, compared in root-relative form because
    semantic edges can still carry an absolute path here while nodes were
    already made relative. Anything else (an ID no file derives from its own
    path, or a bare ID shared across different paths) is left to the existing
    collapse-and-warn path.
    """
    def key(sf):
        return _rank_path(sf, root) if sf else ""

    by_id: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        nid = node.get("id")
        if nid and node.get("source_file") and _extension_qualified_id(node):
            by_id[nid].append(node)
    taken = {n.get("id") for n in nodes if n.get("id")}
    renames: dict[tuple[str, str], str] = {}
    for nid, definers in by_id.items():
        if len({key(d["source_file"]) for d in definers}) < 2:
            continue
        winner = min(definers, key=lambda d: _collision_rank(d, root))
        for d in sorted(definers, key=lambda d: key(d["source_file"])):
            k = key(d["source_file"])
            if k == key(winner["source_file"]) or (nid, k) in renames:
                continue
            # Same full stem only: x.py vs x.html, never a/x vs b/x.
            if _full_stem(d["source_file"]) != _full_stem(winner["source_file"]):
                continue
            # The extension is what tells them apart; same-extension slug twins
            # (pkg/service.py vs pkg_service.py) stay on the collapse-and-warn path.
            if _EXTENSION.search(d["source_file"]) and _EXTENSION.search(winner["source_file"]) and                     _EXTENSION.search(d["source_file"]).group(0).lower() ==                     _EXTENSION.search(winner["source_file"]).group(0).lower():
                continue
            new_id = _extension_qualified_id(d)
            if new_id and new_id not in taken:
                taken.add(new_id)
                renames[(nid, k)] = new_id
    if not renames:
        return nodes, edges
    out_nodes = [
        dict(node, id=renames[(node.get("id"), key(node.get("source_file")))])
        if (node.get("id"), key(node.get("source_file"))) in renames else node
        for node in nodes
    ]
    for coll in (edges, hyperedges or []):
        for item in coll:
            if not isinstance(item, dict):
                continue
            k = key(item.get("source_file"))
            for end in ("source", "target"):
                new_id = renames.get((item.get(end), k))
                if new_id:
                    item[end] = new_id
            members = item.get("nodes")
            if isinstance(members, list):
                item["nodes"] = [renames.get((m, k), m) if isinstance(m, str) else m for m in members]
    return out_nodes, edges


def _path_qualify_dropped_collisions(
    nodes: list[dict], edges: list[dict], hyperedges: list[dict] | None,
    root: Path | None,
) -> tuple[list[dict], list[dict]]:
    """Path-qualify semantic ids that dropped the directory, per file (#4281).

    Semantic extraction sometimes mints an id from the bare filename stem, so
    ``a/x.md`` and ``b/x.md`` both emit ``x``. This is the sibling of
    ``_disambiguate_defining_collisions`` for different directories rather than
    different extensions. Every colliding node is renamed to
    ``<full path stem><rest of id>``, computed from the node's OWN source_file;
    no file keeps the bare id, because picking one would be a guess.

    Heuristic boundary:
    - only ids spelled with a SHORTER-than-full path stem of the node's own file
      are candidates (an id already carrying the full stem is left alone), and
      AST-tier nodes are never touched;
    - a source_file that is still absolute after rooting (no root, outside the
      root, or the other platform's form) is never qualified, so the checkout
      location cannot leak into an id;
    - a group acts only when its files have at least two distinct full stems; a
      lone candidate is left to ``build_from_json``'s semantic id remap;
    - a node read as a MENTION of a document (``_mentions``: a path-slice id that
      another node of its own file ``references``) is not a candidate, so it is not
      renamed onto the mentioning file's own page. That reading is inferred from LLM
      edges: with a missing or reversed edge the node is renamed like any other, and
      a collision with a real document whose own node is linked to its file-level id
      collapses as it did before. If two or more other files also mint the mention's
      id it cannot be pointed at any one of them, so it stays on the bare id and
      ``build_from_json`` then folds it into its own file's page;
    - a file whose full stem IS the id (``protocol.md`` for ``protocol``) defines it,
      keeps the bare id, and counts toward the collision, so ``docs/protocol.md``
      next to it is still renamed. A candidate whose bare id names another input
      file is renamed only if its own file has no other node spelled with its own
      full stem. If it has one (``docs_protocol`` next to ``protocol``), the bare id
      may be a reference, so it stays on the definer-wins collapse-and-warn path as
      before. Known boundary: when the LLM drops the folder AND also emits another
      node spelled with the file's full stem, the file counts as having its own page
      and falls back to the collapse it got before this change (#4281);
    - a reference to the bare id from ANOTHER file cannot be attributed to one
      file, so it is left unresolved (one warning per id) rather than guessed;
    - if the new id is already used by a node of a different file, or two files
      of a group map to the same new id, the first file in sorted order keeps it
      and the rest stay on the bare id and take the collapse-and-warn path.
    """
    from graphify.build import _is_abs, _is_ast_tier  # local: build imports dedup

    def key(sf):
        return _rank_path(sf, root) if sf and isinstance(sf, str) else ""

    def qualified_id(node: dict) -> tuple[str, str] | None:
        """``(new id, matched shorter prefix)`` for a candidate node, else None."""
        nid = node.get("id")
        sf = node.get("source_file")
        if not nid or not isinstance(nid, str) or not sf or not isinstance(sf, str):
            return None
        if _is_ast_tier(node):
            return None
        rel = key(sf)
        if _is_abs(rel):
            # No root to relativize against: never bake an on-disk path into an id.
            return None
        full = _full_stem(rel)
        matching = [p for p in _id_prefixes(rel) if nid == p or nid.startswith(f"{p}_")]
        if not full or not matching:
            return None
        longest = max(matching, key=len)
        if longest == full:
            return None
        return full + nid[len(longest):], longest

    named_files = {
        _full_stem(key(n["source_file"])) for n in nodes
        if isinstance(n.get("source_file"), str) and n["source_file"]
    }
    mentions = _mentions(nodes, edges, root)
    by_id: dict[str, list[dict]] = defaultdict(list)
    owners: dict[str, set[str]] = defaultdict(set)
    kept_bare: set[tuple[str, str]] = set()
    for node in nodes:
        nid = node.get("id")
        if not nid or not isinstance(nid, str):
            continue
        k = key(node.get("source_file"))
        owners[nid].add(k)
        if not qualified_id(node):
            continue
        if (nid, k) in mentions:
            kept_bare.add((nid, k))  # stays on the bare id; its own-file edges are fine
        else:
            by_id[nid].append(node)

    # Files with a node spelled with their own full stem: their page already exists,
    # so a shorter-prefix id from such a file may be a reference to another file.
    own_page = _own_page_files(nodes, root)

    renames: dict[tuple[str, str], str] = {}
    claimed: dict[str, str] = {}
    for nid in sorted(by_id):
        members = by_id[nid]
        # The file whose full stem IS the id defines it; it keeps the bare id and
        # counts toward the collision even though it is not a candidate.
        definers = {o for o in owners[nid] if o and not _is_abs(o) and _full_stem(o) == nid}
        files = {key(m["source_file"]) for m in members} | definers
        if len(files) < 2:
            continue
        if len({_full_stem(f) for f in files}) < 2:
            continue
        for m in sorted(members, key=lambda m: key(m["source_file"])):
            k = key(m["source_file"])
            if (nid, k) in renames or (nid, k) in kept_bare:
                continue
            # The bare id names another input file (``protocol`` while protocol.md
            # exists). It is this file's own page only if the file has no other
            # page node; otherwise it may be a reference, so leave it to collapse.
            if (qualified_id(m) or ("", ""))[1] in named_files and k in own_page:
                kept_bare.add((nid, k))
                continue
            qualified = qualified_id(m)
            new_id = qualified[0] if qualified else None
            if (new_id is None
                    or any(o != k for o in owners.get(new_id, ()))
                    or claimed.get(new_id, k) != k):
                kept_bare.add((nid, k))
                continue
            claimed[new_id] = k
            renames[(nid, k)] = new_id
    if not renames:
        return nodes, edges

    out_nodes = []
    for node in nodes:
        new_id = renames.get((str(node.get("id") or ""), key(node.get("source_file"))))
        out_nodes.append(dict(node, id=new_id) if new_id else node)
    renamed_ids = {nid for nid, _ in renames}
    unattributed: dict[str, int] = defaultdict(int)
    for coll in (edges, hyperedges or []):
        for item in coll:
            if not isinstance(item, dict):
                continue
            k = key(item.get("source_file"))
            refs = [item.get("source"), item.get("target")]
            members = item.get("nodes")
            if isinstance(members, list):
                refs += members
            for ref in refs:
                if (isinstance(ref, str) and ref in renamed_ids
                        and (ref, k) not in renames and (ref, k) not in kept_bare):
                    unattributed[ref] += 1
            for end in ("source", "target"):
                ref = item.get(end)
                new_id = renames.get((ref, k)) if isinstance(ref, str) else None
                if new_id:
                    item[end] = new_id
            if isinstance(members, list):
                item["nodes"] = [renames.get((m, k), m) if isinstance(m, str) else m
                                 for m in members]
    for nid in sorted(unattributed):
        print(
            f"[graphify] WARNING: node '{nid}' was minted by several files and "
            f"renamed per file; {unattributed[nid]} reference(s) from other files "
            f"could not be attributed and were left unresolved.",
            file=sys.stderr,
        )
    return out_nodes, edges


def _is_reference_stub(node: dict) -> bool:
    """Whether semantic extraction marked a node as a cross-document stub."""
    metadata = node.get("metadata")
    return isinstance(metadata, dict) and metadata.get("graphify_reference_stub") is True


def _namespace_reference_stub_collisions(
    nodes: list[dict], edges: list[dict], hyperedges: list[dict] | None,
    root: Path | None,
) -> tuple[list[dict], list[dict]]:
    """Keep marked cross-document reference stubs distinct (#4738).

    Semantic extraction marks a node it emitted solely for a referenced entity
    with ``metadata.graphify_reference_stub``. Preserve every marked node under
    ``<citing-file>__ref__<original-id>`` instead of silently dropping it when
    its target ID collides with another file's node. Edges from the citing file
    follow its namespaced endpoint.

    The marker distinguishes reference stubs from two independent documents
    that happen to share an ID. Path specificity cannot make that distinction:
    it regresses genuine nested-path definitions.
    """
    def key(source_file: object) -> str:
        return _rank_path(source_file, root) if isinstance(source_file, str) else ""

    by_id: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        nid = node.get("id")
        if isinstance(nid, str) and nid:
            by_id[nid].append(node)

    taken = {node.get("id") for node in nodes if node.get("id")}
    renames: dict[tuple[str, str], str] = {}
    for nid, members in by_id.items():
        if len({key(node.get("source_file")) for node in members}) < 2:
            continue
        stubs = [node for node in members if _is_reference_stub(node)]
        if not stubs:
            continue
        source_keys = {key(node.get("source_file")) for node in stubs}
        if "" in source_keys:
            continue
        candidates = {
            source_key: f"{_full_stem(source_key)}__ref__{nid}"
            for source_key in source_keys
            if _full_stem(source_key)
        }
        if len(candidates) != len(source_keys):
            continue
        if len(set(candidates.values())) != len(candidates):
            continue
        if any(candidate in taken for candidate in candidates.values()):
            continue
        renames.update(((nid, source_key), candidate)
                       for source_key, candidate in candidates.items())
        taken.update(candidates.values())

    if not renames:
        return nodes, edges

    out_nodes = [
        dict(node, id=renames[(node["id"], key(node.get("source_file")))])
        if (node.get("id"), key(node.get("source_file"))) in renames else node
        for node in nodes
    ]
    for collection in (edges, hyperedges or []):
        for item in collection:
            if not isinstance(item, dict):
                continue
            source_key = key(item.get("source_file"))
            for endpoint in ("source", "target"):
                value = item.get(endpoint)
                replacement = renames.get((value, source_key))
                if replacement:
                    item[endpoint] = replacement
            members = item.get("nodes")
            if isinstance(members, list):
                item["nodes"] = [renames.get((member, source_key), member)
                                 if isinstance(member, str) else member
                                 for member in members]
    return out_nodes, edges


# ── main entry point ──────────────────────────────────────────────────────────

def _remap_hyperedge_members(hyperedges: list[dict], remap: dict[str, str]) -> None:
    """Rewire hyperedge member ids onto dedup survivors, in place.

    Members come in both shapes the rest of the codebase tolerates — a bare id
    string, or an object carrying one — so both are handled;
    ``_normalize_hyperedge_members`` fixes the SHAPE but never resolves a member
    against surviving node ids, which is why this is needed as well.

    Two members that remap onto the same survivor collapse to one entry. That
    shrinks the group, but honestly: they were the same entity, and the previous
    behaviour dropped the loser without promoting it, which shrank the group
    *and* lost the participant. Order is preserved so a rebuilt graph does not
    churn.
    """
    for he in hyperedges:
        if not isinstance(he, dict):
            continue
        members = he.get("nodes")
        if not isinstance(members, list):
            continue
        seen: set = set()
        rewired: list = []
        for m in members:
            if isinstance(m, str):
                new_id = remap.get(m, m)
                entry = new_id
            elif isinstance(m, dict):
                raw = m.get("id")
                new_id = remap.get(raw, raw) if isinstance(raw, str) else raw
                entry = dict(m, id=new_id) if new_id != raw else m
            else:
                new_id, entry = None, m
            if isinstance(new_id, str):
                if new_id in seen:
                    continue
                seen.add(new_id)
            rewired.append(entry)
        he["nodes"] = rewired


def deduplicate_entities(
    nodes: list[dict],
    edges: list[dict],
    *,
    communities: dict[str, int],
    dedup_llm_backend: str | None = None,
    root: str | Path | None = None,
    hyperedges: "list[dict] | None" = None,
    protected_ids: "set[str] | None" = None,
) -> tuple[list[dict], list[dict]]:
    """Deduplicate near-identical entities in a knowledge graph.

    Args:
        nodes: list of node dicts with at minimum {"id": str, "label": str}
        edges: list of edge dicts with {"source": str, "target": str, ...}
        communities: mapping of node_id -> community_id (from cluster())
        dedup_llm_backend: if set, use LLM to resolve ambiguous pairs
        root: scan root; ID-collision ranking judges source paths relative to
            it so path form and checkout location cannot flip the survivor (#2532)
        hyperedges: when given, member ids are rewired to survivors IN PLACE,
            the same way edge endpoints are. Optional and mutating rather than
            returned so existing two-tuple callers are unaffected (#2805).

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

    # Resolve the scan root once: _collision_rank ranks each node's source_file
    # relative to it, so an absolute stored path and its repo-relative twin rank
    # identically and lifecycle markers in the checkout location's own segments
    # cannot flip the survivor (#2532).
    try:
        root_resolved: Path | None = Path(root).resolve() if root else None
    except Exception:
        root_resolved = None

    # Pre-deduplicate: one node per ID. The survivor is the node that *defines* the
    # ID (its source_file is the file the ID encodes), not merely the first seen —
    # otherwise chunk order decides whether an entity keeps its own attributes or a
    # passing cross-reference's. Missing attributes from same-source records are
    # retained so AST structure and semantic enrichment can coexist (#2091).
    # Genuine cross-file ID collisions stay isolated and are reported below (#1504).
    nodes, edges = _disambiguate_defining_collisions(nodes, edges, hyperedges, root_resolved)
    nodes, edges = _path_qualify_dropped_collisions(nodes, edges, hyperedges, root_resolved)
    nodes, edges = _namespace_reference_stub_collisions(
        nodes, edges, hyperedges, root_resolved,
    )
    mentions = _mentions(nodes, edges, root_resolved) | _slice_references(nodes, root_resolved)
    outranked = _outranked_by_ast(nodes, root_resolved, mentions)
    seen_ids: dict[str, dict] = {}
    dropped: dict[str, list[dict]] = defaultdict(list)
    for node in nodes:
        nid = node.get("id", "")
        if not nid:
            continue
        incumbent = seen_ids.get(nid)
        if incumbent is None:
            seen_ids[nid] = node
        elif (_collision_rank(node, root_resolved, mentions, outranked)
              < _collision_rank(incumbent, root_resolved, mentions, outranked)):
            # Smallest-ranked node wins; the min over a total order is independent
            # of the order nodes arrive in, so the survivor no longer depends on
            # chunk ordering (#1851).
            seen_ids[nid] = node
            dropped[nid].append(incumbent)
        else:
            dropped[nid].append(node)

    # Gap-fill each survivor from its SAME-SOURCE losers, applied in deterministic
    # _collision_rank order (best loser first). Merging here — not incrementally in
    # the loop above — keeps the merged attributes independent of chunk arrival
    # order with 3+ colliding records, preserving the #1851 order-independence
    # contract (#2091 review).
    for nid, losers in dropped.items():
        survivor = seen_ids[nid]
        same_source = sorted(
            (l for l in losers if _same_source_entity(survivor, l)),
            key=lambda l: _collision_rank(l, root_resolved, mentions, outranked),
        )
        for loser in same_source:
            survivor = _merge_missing_attributes(survivor, loser)
        seen_ids[nid] = survivor

    for nid, losers in dropped.items():
        _report_id_collision(nid, seen_ids[nid], losers)

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

    protected_set: set[str] = set(protected_ids) if protected_ids is not None else set()
    prot_by_root: dict[str, str] = {pid: pid for pid in protected_set}

    def _get_prot(nid: str) -> str | None:
        return prot_by_root.get(uf.find(nid))

    def _union_with_prot(x: str, y: str) -> None:
        px = _get_prot(x)
        py = _get_prot(y)
        uf.union(x, y)
        new_root = uf.find(x)
        prot = px or py
        if prot is not None:
            prot_by_root[new_root] = prot

    def _crossfile_union(left: dict, right: dict, *, with_prot: bool) -> None:
        nonlocal exact_merges
        if _crossfile_fileanchored_blocked(left, right):
            return
        left_id = left["id"]
        right_id = right["id"]
        if with_prot:
            px = _get_prot(left_id)
            py = _get_prot(right_id)
            if px is not None and py is not None and px != py:
                return
        if uf.find(left_id) == uf.find(right_id):
            return
        if with_prot:
            _union_with_prot(left_id, right_id)
        else:
            uf.union(left_id, right_id)
        exact_merges += 1

    def _crossfile_join(members: list[dict], *, with_prot: bool) -> None:
        for index, left in enumerate(members):
            for right in members[index + 1:]:
                _crossfile_union(left, right, with_prot=with_prot)

    for key, group in norm_to_nodes.items():
        if len(group) <= 1:
            continue
        # Partition by source_file — same-file exact matches always merge here.
        # Cross-file exact matches are handled just below, gated to `concept`
        # nodes only: Pass 2 cannot form them because its candidate list keeps a
        # single node per normalized label (#2182).
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
                if protected_set:
                    prot_file = [n for n in file_group if n.get("id") in protected_set]
                    inc_file = [n for n in file_group if n.get("id") not in protected_set]
                    if prot_file and not inc_file:
                        # All nodes belong exclusively to an untouched file — preserve all of them
                        continue
                    if prot_file and inc_file:
                        winner = _pick_winner(prot_file)
                        for node in inc_file:
                            px = _get_prot(winner["id"])
                            py = _get_prot(node["id"])
                            if px is not None and py is not None and px != py:
                                continue
                            if uf.find(winner["id"]) != uf.find(node["id"]):
                                _union_with_prot(winner["id"], node["id"])
                                exact_merges += 1
                    else:
                        winner = _pick_winner(file_group)
                        for node in file_group:
                            if uf.find(winner["id"]) != uf.find(node["id"]):
                                _union_with_prot(winner["id"], node["id"])
                                exact_merges += 1
                else:
                    winner = _pick_winner(file_group)
                    for node in file_group:
                        uf.union(winner["id"], node["id"])
                    exact_merges += len(file_group) - 1
        # Cross-file residue: union exact matches across files, but only where
        # it is provably safe (#2182). `concept` is the one file_type meant to
        # unify across files (#1284) — code is keyed by ID (#1205) and
        # image/paper labels are often shared basenames (logo.png), so both stay
        # blocked. A rationale or document node can still enter this list when
        # it reads as an entity (#296). Each union calls
        # `_crossfile_fileanchored_blocked`, so that node does not join a node
        # from another file (#3094). Concept nodes still join across files.
        # A file's own node and its headings never enter the list (#1284).
        # Provenance is required (#1178), and the entropy gate mirrors Pass 2 so
        # short generic labels ("API") stay distinct — both untouched here.
        # Pass 2 still calls the same block, so near-identical boilerplate stays
        # blocked (#1284). Sorting by id keeps the pair order stable.
        mergeable = sorted(
            (n for n in group
             if (n.get("file_type") == "concept"
                 or (n.get("file_type") in _FILE_ANCHORED_NONCODE
                     and _reads_as_file_entity(n)))
             and (n.get("source_file") or "")
             and _entropy(n.get("label", "")) >= _ENTROPY_THRESHOLD),
            key=lambda n: n["id"],
        )
        if len(mergeable) > 1:
            if protected_set:
                prot_members = [n for n in mergeable if n.get("id") in protected_set]
                inc_members = [n for n in mergeable if n.get("id") not in protected_set]
                if not inc_members:
                    # All participants belong exclusively to untouched files (#3477):
                    # NEVER collapse them during incremental merge.
                    continue
                if prot_members:
                    # Mixed: fold an incoming node into at most one protected
                    # survivor. Protected nodes stay separate from each other.
                    # Incoming nodes the block still allows are joined to each
                    # other, so a blocked winner does not leave them apart.
                    canonical_winner = _pick_winner(prot_members)
                    for inc in inc_members:
                        _crossfile_union(canonical_winner, inc, with_prot=True)
                    _crossfile_join(inc_members, with_prot=True)
                else:
                    _crossfile_join(inc_members, with_prot=True)
            else:
                _crossfile_join(mergeable, with_prot=False)

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

                if protected_set:
                    px = _get_prot(node_id)
                    py = _get_prot(neighbor_id)
                    if px is not None and py is not None and px != py:
                        # Prevent protected/protected unions and bridging across protected components
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
                # Template-named siblings differing in a content word are
                # distinct too, on either path: same-file pairs keep the prefix
                # bonus, and a cross-file pair can still reach threshold on the
                # community boost alone (#2576).
                if _content_token_swap(norm_label, neighbor_norm):
                    continue
                if _crossfile_fileanchored_blocked(node, neighbor):
                    continue

                c1 = communities.get(node_id)
                c2 = communities.get(neighbor_id)
                if (c1 is not None and c2 is not None and c1 == c2
                        and min(len(norm_label), len(neighbor_norm)) >= 12):
                    score += _COMMUNITY_BOOST

                if score >= _MERGE_THRESHOLD:
                    # Belt-and-braces (#1046, narrowed by #2182): candidates are
                    # norm-unique (`seen_norms` above), so two candidates can
                    # never share a normalized label and this branch is
                    # unreachable today. Retained in case candidate selection
                    # changes. Equal-norm cross-file pairs are handled in Pass 1
                    # instead, gated to `concept` nodes — the original #1046
                    # rationale (same-named code symbols) was obsoleted by code
                    # being excluded from label matching entirely (#1205, #1247).
                    if norm_label == neighbor_norm:
                        sf_a = node.get("source_file") or ""
                        sf_b = neighbor.get("source_file") or ""
                        if sf_a != sf_b:
                            continue
                    # Pick the winner from the verified pair only. Selecting it
                    # from the union of both normalized-label groups pulls
                    # never-compared nodes (same label, different source_file)
                    # into the merge, bypassing the #1046/#1178 guards.
                    if protected_set:
                        px = _get_prot(node_id)
                        py = _get_prot(neighbor_id)
                        if px is not None and py is not None and px != py:
                            continue
                        if node_id in protected_set:
                            winner = node
                        elif neighbor_id in protected_set:
                            winner = neighbor
                        else:
                            winner = _pick_winner([node, neighbor])
                        _union_with_prot(winner["id"], node_id)
                        _union_with_prot(winner["id"], neighbor_id)
                    else:
                        winner = _pick_winner([node, neighbor])
                        uf.union(winner["id"], node_id)
                        uf.union(winner["id"], neighbor_id)
                    fuzzy_merges += 1

    # ── pass 3: LLM tiebreaker for ambiguous pairs (opt-in) ──────────────────
    if dedup_llm_backend is not None:
        _llm_tiebreak(
            candidates, uf, communities, backend=dedup_llm_backend,
            protected_set=protected_set, get_prot=_get_prot, union_with_prot=_union_with_prot,
        )

    # ── build remap table from union-find components ──────────────────────────
    components = uf.components()
    remap: dict[str, str] = {}

    # id -> (position, node), built once. Previously each component re-scanned
    # the whole unique_nodes list, making remap construction O(nodes x
    # components) — 31% of dedup wall-clock on a 50k-node corpus.
    # The position is carried so group_nodes keeps unique_nodes order: _pick_winner
    # resolves ties (equal chunk-suffix status and equal id length) via min(),
    # which returns the first minimum, so reordering here would silently change
    # which node survives.
    nodes_by_id: dict[str, tuple[int, dict]] = {
        n["id"]: (i, n) for i, n in enumerate(unique_nodes)
    }

    # Survivors enriched with their losers' fields, substituted at the end.
    enriched_by_id: dict[str, dict] = {}
    for root, members in components.items():
        if len(members) == 1:
            continue
        group_nodes = [
            n for _, n in sorted(
                (nodes_by_id[m] for m in members if m in nodes_by_id),
                key=lambda pair: pair[0],
            )
        ]
        if protected_set:
            prot_in_group = [n for n in group_nodes if n.get("id") in protected_set]
            if prot_in_group:
                winner = _pick_winner(prot_in_group)
            else:
                winner = _pick_winner(group_nodes) if group_nodes else {"id": root}
        else:
            winner = _pick_winner(group_nodes) if group_nodes else {"id": root}
        winner_id = winner["id"]
        # Even with the right survivor, dropping the losers wholesale loses
        # whatever fields only they carried. Fill the survivor's absent
        # fields from each loser — the same never-override merge the
        # same-source collision path already applies (#2091/#3372); loser
        # order follows unique_nodes order, so the fill is deterministic.
        merged = winner
        for node in group_nodes:
            if node["id"] != winner_id:
                merged = _merge_missing_attributes(merged, node)
        if merged != winner:
            enriched_by_id[winner_id] = merged
        for member in members:
            if member != winner_id:
                remap[member] = winner_id

    # ── apply remap ───────────────────────────────────────────────────────────
    if not remap:
        return unique_nodes, edges

    total = len(remap)
    msg = f"[graphify] Deduplicated {total} node(s)"
    # Both counters are reported when non-zero. Previous form nested the fuzzy
    # branch inside `if exact_merges`, silently dropping the fuzzy count on
    # doc/semantic-heavy runs where Pass 1 finds nothing (#1857).
    parts: list[str] = []
    if exact_merges:
        parts.append(f"{exact_merges} exact")
    if fuzzy_merges:
        parts.append(f"{fuzzy_merges} fuzzy")
    if parts:
        msg += f" ({', '.join(parts)})"
    print(msg + ".", flush=True)

    # Hyperedge members are node references exactly like edge endpoints, and
    # must follow the survivor for the same reason. Without this the member
    # naming a merged-away id was simply absent from the rebuilt graph: the
    # group lost a participant silently, could fall under the 3-member threshold
    # that makes it a hyperedge at all, and left NO dangling reference, so a
    # referential-integrity check saw nothing wrong (#2805).
    if hyperedges:
        _remap_hyperedge_members(hyperedges, remap)

    deduped_nodes = [
        enriched_by_id.get(n["id"], n) for n in unique_nodes if n["id"] not in remap
    ]
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
        # Drop only self-loops created by the merge (an edge whose distinct
        # endpoints collapsed into one node); preserve pre-existing self-loops
        # (e.g. recursive calls, self-referencing foreign keys) (#3809).
        if e["source"] != e["target"] or src == tgt:
            deduped_edges.append(e)

    return deduped_nodes, deduped_edges


# Keys every node carries (or that describe placement rather than content).
# They say nothing about which duplicate is the better-established record, so
# the richness score below ignores them.
_RICHNESS_IGNORED_KEYS = frozenset({
    "id", "label", "norm_label", "file_type", "source_file", "source_location",
})


def _content_richness(n: dict) -> int:
    """How much actual content a node carries, for survivor selection (#3372).

    Counts populated fields beyond the identity/placement baseline, weighting
    ``attributes`` by entry count and ``_merged_from`` by its history length —
    a node that already absorbed prior merges is the established record.
    """
    score = 0
    for key, value in n.items():
        if key in _RICHNESS_IGNORED_KEYS:
            continue
        if value is None or value == "" or value == [] or value == {}:
            continue
        score += 1
        if key == "attributes" and isinstance(value, dict):
            score += len(value)
        elif key == "_merged_from" and isinstance(value, list):
            score += len(value)
    return score


def _pick_winner(nodes: list[dict]) -> dict:
    """Pick the canonical survivor: no chunk suffix, then real provenance,
    then richer content, then shorter ID.

    ID length used to be the primary signal after the chunk-suffix check,
    which made a passing one-line mention on a shallow page (short id, one
    fewer path segment) beat the dedicated, enriched page for the same entity
    — every time the pattern occurred, the established node's content was
    discarded (#3372). Content richness now decides first; ID shape only
    breaks ties between equally-rich candidates, preserving the old
    deterministic ordering there.

    ``source_file``/``source_location`` are in ``_RICHNESS_IGNORED_KEYS``, so
    richness alone cannot tell a real, located declaration apart from a
    source-less stub carrying a couple of incidental bookkeeping keys (e.g.
    ``external``/``type``/``_origin``) — the stub could out-score and replace
    the genuine record purely on field count (#3775). Provenance is checked
    ahead of richness, in two steps: a node with a ``source_file`` always
    beats one without, and among nodes that both have one, a node that also
    has a ``source_location`` beats one that doesn't (the codebase genuinely
    emits ``source_location: None`` on some records, so this is a real
    distinction, not a hypothetical one — richness ignores it too, the same
    gap #3775 closed one level up). The location step only counts a
    ``source_location`` when ``source_file`` is also present — a location
    with no file isn't a real provenance signal and must not out-rank a
    fully bare candidate on its own. Each step only changes the outcome
    when the two sides disagree; whenever they agree (both or neither have
    a source file, and both or neither have a counted location), the
    existing richness-then-length ordering decides as before.
    """
    if not nodes:
        raise ValueError("Cannot pick winner from empty list")

    def _score(n: dict) -> tuple[int, int, int, int, int]:
        has_suffix = bool(_CHUNK_SUFFIX.search(n["id"]))
        has_source = bool(n.get("source_file"))
        no_source = 0 if has_source else 1
        # A source_file with no source_location (the codebase genuinely emits
        # `source_location: None`, see _merge_missing_attributes above) is a
        # weaker provenance claim than a fully located record -- richness
        # ignores source_location too, so without this check a candidate that
        # merely knows which file it came from could still out-score, and
        # replace, one that also knows exactly where in it (#3775 review).
        # Gated on has_source too: a source_location with no source_file (a
        # location pointing at an unstated file, which _merge_missing_attributes
        # can produce by backfilling one field but not the other when a survivor's
        # own source_file is an empty string rather than None) isn't a real
        # provenance signal on its own, and must not out-rank a fully bare
        # candidate by richness's own rules (PR 3786 review).
        no_location = 0 if (has_source and n.get("source_location")) else 1
        return (1 if has_suffix else 0, no_source, no_location, -_content_richness(n), len(n["id"]))

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
    protected_set: set[str] | None = None,
    get_prot=None,
    union_with_prot=None,
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
            # Mirror pass 2: decisively-distinct pairs never reach the LLM
            # (#1284, #2576).
            if _numeric_tokens_differ(norm_i, norm_j):
                continue
            if _content_token_swap(norm_i, norm_j):
                continue
            if _crossfile_fileanchored_blocked(node, neighbor):
                continue
            c1 = communities.get(node["id"])
            c2 = communities.get(neighbor["id"])
            if (c1 is not None and c2 is not None and c1 == c2
                    and min(len(norm_i), len(norm_j)) >= 12):
                score += _COMMUNITY_BOOST
            if low <= score < high:
                if protected_set and get_prot is not None:
                    px = get_prot(node["id"])
                    py = get_prot(neighbor["id"])
                    if px is not None and py is not None and px != py:
                        continue
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
                        if protected_set and get_prot is not None and union_with_prot is not None:
                            px = get_prot(a["id"])
                            py = get_prot(b["id"])
                            if px is not None and py is not None and px != py:
                                continue
                            if a["id"] in protected_set:
                                winner = a
                            elif b["id"] in protected_set:
                                winner = b
                            else:
                                winner = _pick_winner([a, b])
                            union_with_prot(winner["id"], a["id"])
                            union_with_prot(winner["id"], b["id"])
                        else:
                            winner = _pick_winner([a, b])
                            uf.union(winner["id"], a["id"])
                            uf.union(winner["id"], b["id"])
        except Exception as exc:
            print(f"[graphify] --dedup-llm batch failed: {exc}", flush=True)
