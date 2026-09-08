"""The query answer is ranked, scored, explained — and honest about a miss (#RANK1).

Before this, `_score_query` ranked every node and only `_pick_seeds` ever read the
ranking: the renderer ordered by graph topology and printed no score, so a caller
saw a flat list of equally-weighted lines with the answer somewhere inside it. The
tests here pin the four properties that changed — a leading ANSWER block, a
relevance figure on every node line, support files ranked under the source they
support, and a truncation notice that only cries loss when something relevant was
actually lost.
"""
import networkx as nx
import pytest

from graphify.build import graph_has_legacy_ids, legacy_id_collisions
from graphify.serve import (
    _ANSWER_BLOCK_MAX,
    _answer_block,
    _fold_plural,
    _match_reason,
    _matched_terms,
    _query_graph_text,
    _relevance_weight,
    _score_nodes,
    _source_snippet,
    _subgraph_to_text,
    _subword_tokens,
)


# --------------------------------------------------------------------------
# file-kind weighting
# --------------------------------------------------------------------------

@pytest.mark.parametrize("path,expected", [
    ("src/lib/SectionLanguagesCard.tsx", 1.0),
    ("src/lib/LanguagesCard.test.tsx", 0.30),
    ("src/lib/langLadder.spec.ts", 0.30),
    ("pkg/thing_test.go", 0.30),
    ("tests/helpers.py", 0.30),
    ("apps/builder-e2e/project.json", 0.50),
    ("a/__mocks__/client.ts", 0.50),
    ("openspec/changes/archive/2026-05-10-admin-ui/tasks.md", 0.50),
    ("node_modules/left-pad/index.js", 0.50),
    ("", 1.0),
])
def test_relevance_weight_classifies_by_file_kind(path, expected):
    assert _relevance_weight(path) == pytest.approx(expected)


@pytest.mark.parametrize("path", [
    "src/latest/thing.ts",       # "latest" is not "test"
    "src/contest.py",            # substring, not a segment
    "src/greatest/x.py",
    "lib/distribution/pack.ts",  # "distribution" is not "dist"
])
def test_relevance_weight_never_matches_a_substring(path):
    assert _relevance_weight(path) == 1.0


def test_a_test_file_does_not_outrank_the_source_it_tests():
    """The single clearest symptom: `*.test.tsx` above the component it exercises.

    Same label, same tier, so the two nodes scored identically and the winner was
    decided by node id — the test file whenever its id happened to sort first.
    """
    G = nx.Graph()
    G.add_node("a_test", label="LanguagesCard", source_file="ui/LanguagesCard.test.tsx",
               source_location="L15", community=0)
    G.add_node("z_src", label="LanguagesCard", source_file="ui/LanguagesCard.tsx",
               source_location="L4", community=0)
    G.add_edge("a_test", "z_src", relation="imports")
    assert [nid for _score, nid in _score_nodes(G, ["languagescard"])] == ["z_src", "a_test"]


def test_the_rendered_answer_leads_with_the_source_not_the_test():
    """End to end, because the inversion a reader actually saw was in the render:
    seeds printed in seed order, so a test-file node that won one term's seed slot
    took the top line whatever the combined ranking said."""
    G = nx.Graph()
    G.add_node("a_test", label="LanguagesCard", source_file="ui/LanguagesCard.test.tsx",
               source_location="L15", community=0)
    G.add_node("z_src", label="LanguagesCard", source_file="ui/LanguagesCard.tsx",
               source_location="L4", community=0)
    G.add_edge("a_test", "z_src", relation="imports")
    out = _query_graph_text(G, "languagescard", depth=2, token_budget=2000)
    first_node_line = next(l for l in out.splitlines() if l.startswith("NODE "))
    assert "ui/LanguagesCard.tsx" in first_node_line
    assert ".test.tsx" not in first_node_line


# --------------------------------------------------------------------------
# identifier sub-words
# --------------------------------------------------------------------------

@pytest.mark.parametrize("text,expected", [
    ("handleTeamConfigWrite", ["handle", "team", "config", "write"]),
    ("SectionLanguagesCard", ["section", "languages", "card"]),
    ("PLATFORM_SOURCE_LANG", ["platform", "source", "lang"]),
    ("HTTPServer", ["http", "server"]),
    ("matchWriteRoute.ts", ["match", "write", "route", "ts"]),
    ("plain", ["plain"]),
    ("", []),
])
def test_subword_tokens_splits_identifier_conventions(text, expected):
    assert _subword_tokens(text) == expected


@pytest.mark.parametrize("word,folded", [
    ("writes", "write"), ("languages", "language"), ("validates", "validate"),
    ("class", "class"), ("address", "address"),   # -ss is left alone
    ("its", "its"), ("has", "has"),               # too short to fold
    ("config", "config"),
])
def test_fold_plural_is_a_consistent_fold_not_a_stemmer(word, folded):
    assert _fold_plural(word) == folded


def test_an_identifier_naming_three_query_words_beats_a_one_word_collision():
    """The measured inversion: a bare `worker` variable scored 126 and
    `handleTeamConfigWrite` — which names three of the six terms — scored 15."""
    G = nx.Graph()
    G.add_node("noise", label="worker", source_file="app/sw/main.ts",
               source_location="L50", community=0)
    G.add_node("real", label="handleTeamConfigWrite()",
               source_file="worker/src/routes/handleTeamConfigWrite.ts",
               source_location="L109", community=0)
    G.add_edge("noise", "real", relation="calls")
    terms = ["worker", "route", "validates", "team", "config", "writes"]
    order = [nid for _score, nid in _score_nodes(G, terms)]
    assert order[0] == "real"


def test_a_single_identifier_lookup_still_wins_outright():
    """The sub-word tier must not cost the exact-match dominance identifier
    lookups depend on."""
    G = nx.Graph()
    G.add_node("exact", label="langLadder()", source_file="lib/langLadder.ts",
               source_location="L45", community=0)
    G.add_node("part", label="langLadderCache", source_file="lib/cache.ts",
               source_location="L3", community=0)
    G.add_edge("exact", "part", relation="calls")
    assert _score_nodes(G, ["langLadder"])[0][1] == "exact"


# --------------------------------------------------------------------------
# the ANSWER block
# --------------------------------------------------------------------------

def _answer_graph() -> nx.Graph:
    G = nx.Graph()
    G.add_node("card", label="SectionLanguagesCard()",
               source_file="builder/feature-content/SectionLanguagesCard.tsx",
               source_location="L32", community=0)
    G.add_node("test", label="LANGUAGES", source_file="builder/ui/LanguagesCard.test.tsx",
               source_location="L15", community=0)
    G.add_node("far", label="unrelatedHelper", source_file="other/helper.ts",
               source_location="L2", community=1)
    G.add_edge("card", "test", relation="imports")
    G.add_edge("card", "far", relation="calls")
    return G


def test_query_output_leads_with_a_ranked_answer_block():
    G = _answer_graph()
    out = _query_graph_text(G, "languages card section", depth=2, token_budget=2000)
    assert "ANSWER" in out
    answer, _, nodes = out.partition("NODE ")
    assert "SectionLanguagesCard()" in answer
    # the answer names the file and the line, so the reader's next move is an open
    assert "builder/feature-content/SectionLanguagesCard.tsx:L32" in answer
    # ...and says why
    assert "why:" in answer
    # the ANSWER block precedes every raw NODE line
    assert answer.index("ANSWER") < len(answer)
    assert nodes


def test_every_node_line_carries_its_relevance():
    G = _answer_graph()
    out = _query_graph_text(G, "languages card section", depth=2, token_budget=2000)
    node_lines = [l for l in out.splitlines() if l.startswith("NODE ")]
    assert node_lines and all("rel=" in l for l in node_lines)
    # the best hit is 100 and it comes first
    assert "rel=100" in node_lines[0]


def test_relevance_orders_nodes_within_a_hop_layer():
    """Hop distance stays the primary key (#BUG2 keeps the answer's neighbourhood);
    relevance decides inside a layer, and the ANSWER block above is the
    relevance-only view. Every node here is one hop from the seed, so the whole
    list is a single layer and must descend."""
    G = _answer_graph()
    out = _query_graph_text(G, "languages card section", depth=2, token_budget=2000)
    rels = [int(l.split("rel=")[1].split()[0].rstrip("]"))
            for l in out.splitlines() if l.startswith("NODE ") and "rel=" in l]
    assert rels == sorted(rels, reverse=True)


def test_relevance_outranks_hop_distance():
    """Relevance is the PRIMARY key. A weak match two hops out still leads a node
    one hop away that matched nothing — a reader scanning top-down must meet the
    nodes that answer the question first, wherever the traversal reached them."""
    G = nx.Graph()
    G.add_node("seed", label="alphaGate", source_file="src/alphaGate.ts",
               source_location="L1", community=0)
    # six strong hop-1 matches, enough to fill the answer block so the weak match
    # below is ordered on merit rather than pinned into it
    for i in range(6):
        G.add_node(f"hit{i}", label=f"alphaGateHandler{i}",
                   source_file=f"src/alphaGateHandler{i}.ts", source_location="L1",
                   community=0)
        G.add_edge("seed", f"hit{i}", relation="calls")
    G.add_node("near", label="unrelatedNeighbour", source_file="src/near.ts",
               source_location="L1", community=0)
    G.add_edge("seed", "near", relation="calls")
    G.add_node("far", label="betaAlphaGateGamma", source_file="src/far.ts",
               source_location="L1", community=0)
    G.add_edge("near", "far", relation="calls")

    out = _query_graph_text(G, "alphaGate", depth=2, token_budget=8000)
    lines = [l for l in out.splitlines() if l.startswith("NODE ")]
    assert "src/far.ts" not in out.split("ANSWER")[1].split("NODE ")[0], "must be ordered, not pinned"
    near_at = next(i for i, l in enumerate(lines) if "src/near.ts" in l)
    far_at = next(i for i, l in enumerate(lines) if "src/far.ts" in l)
    assert far_at < near_at, "a hop-2 match must lead a hop-0/1 non-match"


def test_hop_distance_breaks_ties_between_equally_relevant_nodes():
    """Hop is the tie-break, so a seed's own neighbourhood still holds together
    among nodes the query cannot separate."""
    G = nx.Graph()
    G.add_node("seed", label="alpha", source_file="src/alpha.ts",
               source_location="L1", community=0)
    G.add_node("near", label="zzzNear", source_file="src/near.ts",
               source_location="L1", community=0)
    G.add_node("far", label="aaaFar", source_file="src/far.ts",
               source_location="L1", community=0)
    G.add_edge("seed", "near", relation="calls")
    G.add_edge("near", "far", relation="calls")
    out = _query_graph_text(G, "alpha", depth=2, token_budget=4000)
    lines = [l for l in out.splitlines() if l.startswith("NODE ")]
    near_at = next(i for i, l in enumerate(lines) if "src/near.ts" in l)
    far_at = next(i for i, l in enumerate(lines) if "src/far.ts" in l)
    # both score 0; `aaaFar` sorts first alphabetically, so only hop can order them
    assert near_at < far_at


def test_the_answer_block_nodes_are_pinned_whatever_their_distance():
    G = nx.Graph()
    G.add_node("seed", label="alpha", source_file="src/alpha.ts",
               source_location="L1", community=0)
    G.add_node("near", label="unrelatedNeighbour", source_file="src/near.ts",
               source_location="L1", community=0)
    G.add_node("far", label="betaAlphaGamma", source_file="src/far.ts",
               source_location="L1", community=0)
    G.add_edge("seed", "near", relation="calls")
    G.add_edge("near", "far", relation="calls")
    out = _query_graph_text(G, "alpha", depth=2, token_budget=2000)
    lines = [l for l in out.splitlines() if l.startswith("NODE ")]
    assert "src/far.ts" in lines[1]
    assert "src/near.ts" in lines[2]


# --------------------------------------------------------------------------
# the budget buys answer, not filler
# --------------------------------------------------------------------------

def _hub_with_context(n_context: int) -> nx.Graph:
    G = nx.Graph()
    G.add_node("seed", label="alphaGate", source_file="src/alphaGate.ts",
               source_location="L1", community=0)
    for i in range(n_context):
        G.add_node(f"n{i}", label=f"unrelated{i:03d}",
                   source_file=f"src/u{i:03d}.ts", source_location="L1", community=0)
        G.add_edge("seed", f"n{i}", relation="calls")
    return G


def test_rel_zero_means_matched_nothing_and_nothing_else():
    """A weak-but-real match used to round down to rel=0, making it
    indistinguishable from pure traversal context — and contradicting the
    trimming note, which says rel=0 nodes are exactly the ones dropped.
    `weak` matches only through its path, worth 0.5x a term against the top
    hit's several thousand, so it rounds to zero and must be floored at 1."""
    G = nx.Graph()
    G.add_node("top", label="alphaGateHandler",
               source_file="src/alphaGateHandler.ts", source_location="L1", community=0)
    G.add_node("weak", label="zzz", source_file="src/alpha/zzz.ts",
               source_location="L1", community=0)
    G.add_node("none", label="unrelated", source_file="src/other/none.ts",
               source_location="L1", community=0)
    G.add_edge("top", "weak", relation="calls")
    G.add_edge("top", "none", relation="calls")

    out = _query_graph_text(G, "alpha gate handler", depth=2, token_budget=8000)
    by_file = {}
    for line in out.splitlines():
        if line.startswith("NODE ") and "rel=" in line:
            src = line.split("src=", 1)[1].split(" ", 1)[0]
            by_file[src] = int(line.split("rel=", 1)[1].split()[0].rstrip("]"))
    assert by_file["src/other/none.ts"] == 0, "a true non-match must read rel=0"
    assert by_file["src/alpha/zzz.ts"] >= 1, "a real match must never read rel=0"
    assert by_file["src/alphaGateHandler.ts"] == 100


def test_a_raised_budget_does_not_buy_unmatched_context():
    """The measured complaint: at --budget 20000 one query rendered 122 matched
    nodes and 266 with rel=0. A bigger budget bought filler."""
    G = _hub_with_context(200)
    out = _query_graph_text(G, "alphaGate", depth=2, token_budget=50000)
    zero = [l for l in out.splitlines() if l.startswith("NODE ") and "rel=0" in l]
    assert len(zero) <= 15


def test_trimmed_context_is_announced_never_dropped_silently():
    G = _hub_with_context(200)
    out = _query_graph_text(G, "alphaGate", depth=2, token_budget=50000)
    assert "matched none of your query terms and are not shown" in out
    assert "185 further node(s)" in out


def test_trimming_leaves_no_dangling_edge():
    G = _hub_with_context(60)
    out = _query_graph_text(G, "alphaGate", depth=2, token_budget=50000)
    shown = {l.split("NODE ", 1)[1].split(" [")[0]
             for l in out.splitlines() if l.startswith("NODE ")}
    for line in out.splitlines():
        if not line.startswith("EDGE "):
            continue
        body = line[5:]
        src = body.split(" --", 1)[0]
        tgt = body.split("]--> ", 1)[1].split(" at=")[0]
        assert src in shown and tgt in shown, line


def test_the_context_cap_leaves_non_query_callers_alone():
    """With no relevance map every node is 'unmatched'; capping there would
    silently truncate a subgraph `path`/`explain` asked for in full."""
    G = _hub_with_context(60)
    out = _subgraph_to_text(G, set(G.nodes()), list(G.edges()), 50000)
    assert len([l for l in out.splitlines() if l.startswith("NODE ")]) == 61
    assert "are not shown" not in out


def test_a_non_query_caller_keeps_the_unscored_node_line():
    """`_subgraph_to_text` with no ranking is byte-identical to its old output."""
    G = _answer_graph()
    nodes = {"card", "test"}
    out = _subgraph_to_text(G, nodes, [("card", "test")], 2000)
    assert "rel=" not in out


def test_the_reason_never_claims_a_tier_the_score_did_not_credit():
    data = {"label": "handleTeamConfigWrite()", "norm_label": "handleteamconfigwrite()",
            "source_file": "worker/src/routes/handleTeamConfigWrite.ts"}
    terms = ["worker", "route", "validates", "team", "config", "writes"]
    reason = _match_reason(data, "n", terms)
    assert "name has part team, config, writes" in reason
    assert "path has worker, route" in reason
    # `validates` matches nothing here and must not be claimed
    assert "validates" not in reason
    assert _matched_terms(data, terms) == {"worker", "route", "team", "config", "writes"}


def test_low_confidence_is_stated_when_the_vocabulary_does_not_overlap():
    """A lexical graph cannot find a node that shares no word with the question;
    it can say so rather than present five near-misses as an answer."""
    G = nx.Graph()
    G.add_node("a", label="terminate()", source_file="scripts/seed.mjs",
               source_location="L166", community=0)
    G.add_node("b", label="fallback", source_file="lib/source.ts",
               source_location="L28", community=0)
    G.add_edge("a", "b", relation="calls")
    out = _query_graph_text(G, "chrome string fallback chain terminate",
                            depth=2, token_budget=2000)
    assert "LOW CONFIDENCE" in out
    # names the words nothing in the corpus matched, which is the actionable part
    assert "'chrome'" in out and "'string'" in out and "'chain'" in out


def test_low_confidence_stays_quiet_on_a_good_answer():
    G = _answer_graph()
    out = _query_graph_text(G, "languages card section", depth=2, token_budget=2000)
    assert "LOW CONFIDENCE" not in out


def test_answer_block_is_empty_when_nothing_matched_the_text():
    G = _answer_graph()
    assert _answer_block(G, [], ["nothing"]) == ("", [])


# --------------------------------------------------------------------------
# honest truncation
# --------------------------------------------------------------------------

def _wide_graph(n: int) -> nx.Graph:
    G = nx.Graph()
    G.add_node("hub", label="teamConfigWriter", source_file="src/teamConfigWriter.ts",
               source_location="L1", community=0)
    for i in range(n):
        G.add_node(f"f{i}", label=f"unrelatedThing{i}",
                   source_file=f"src/unrelated{i}.ts", source_location="L1", community=0)
        G.add_edge("hub", f"f{i}", relation="calls")
    return G


def test_truncation_does_not_claim_loss_when_only_context_was_cut():
    """The old banner always read "The answer may be among the N cut nodes". With
    the list ordered by relevance the cut falls on the tail, so when every cut
    node scored zero that sentence was false and cost the reader a --budget retry."""
    G = _wide_graph(400)
    out = _query_graph_text(G, "team config writer", depth=2, token_budget=300)
    assert "TRUNCATED" not in out
    assert "matched none of your terms" in out
    assert "Raising --budget returns more context, not a better answer." in out


def test_truncation_still_warns_when_a_matching_node_was_cut():
    G = nx.Graph()
    for i in range(200):
        G.add_node(f"m{i}", label=f"teamConfigWriter{i}",
                   source_file=f"src/teamConfigWriter{i}.ts", source_location="L1",
                   community=0)
        if i:
            G.add_edge("m0", f"m{i}", relation="calls")
    out = _query_graph_text(G, "team config writer", depth=2, token_budget=300)
    assert "TRUNCATED" in out
    assert "matched your query" in out


def test_the_named_answer_survives_the_budget_cut():
    G = _wide_graph(400)
    out = _query_graph_text(G, "team config writer", depth=2, token_budget=300)
    body = out.split("ANSWER")[1]
    assert "teamConfigWriter" in body.split("NODE ")[0]
    assert "NODE teamConfigWriter" in out


# --------------------------------------------------------------------------
# snippets
# --------------------------------------------------------------------------

def test_source_snippet_reads_the_line_the_node_points_at(tmp_path):
    (tmp_path / "a.ts").write_text("one\ntwo\nexport const three = 3;\n")
    assert _source_snippet("a.ts", "L3", tmp_path) == "export const three = 3;"


@pytest.mark.parametrize("src,loc", [
    ("missing.ts", "L3"),      # no such file
    ("a.ts", "L99"),           # past the end
    ("a.ts", "nonsense"),      # unparseable location
    ("a.ts", ""),              # no location
    ("", "L1"),                # no file
])
def test_source_snippet_is_silent_rather_than_fatal(tmp_path, src, loc):
    (tmp_path / "a.ts").write_text("one\n")
    assert _source_snippet(src, loc, tmp_path) == ""


def test_source_snippet_truncates_a_generated_megaline(tmp_path):
    (tmp_path / "big.js").write_text("x" * 5000 + "\n")
    out = _source_snippet("big.js", "L1", tmp_path)
    assert 0 < len(out) <= 200


# --------------------------------------------------------------------------
# the legacy-id nudge only fires on real harm
# --------------------------------------------------------------------------

def test_legacy_ids_that_collide_are_reported():
    nodes = [
        {"id": "spec", "source_file": "a/spec.md", "source_location": "L1"},
        {"id": "spec", "source_file": "b/spec.md", "source_location": "L1"},
    ]
    assert graph_has_legacy_ids(nodes, root=".") is True
    assert legacy_id_collisions(nodes, root=".") == 1


def test_legacy_ids_that_collide_with_nothing_are_not_reported():
    """Measured on a 51k-node graph: 591 legacy ids, zero collisions — and a
    rebuild nudge on every single query."""
    nodes = [
        {"id": "alpha_spec", "source_file": "a/alpha/spec.md", "source_location": "L1"},
        {"id": "beta_spec", "source_file": "b/beta/spec.md", "source_location": "L1"},
    ]
    assert graph_has_legacy_ids(nodes, root=".") is True
    assert legacy_id_collisions(nodes, root=".") == 0


def test_path_qualified_ids_are_never_collisions():
    nodes = [{"id": "a_alpha_spec", "source_file": "a/alpha/spec.md", "source_location": "L1"}]
    assert legacy_id_collisions(nodes, root=".") == 0
