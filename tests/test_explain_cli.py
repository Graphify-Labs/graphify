"""Regression tests for `graphify explain` arrow direction (#853)."""
from __future__ import annotations
import json
import pytest
import graphify.__main__ as mainmod


def _write_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "validate", "label": "validateSanitySession()",
             "source_file": "server/sanity-validate-session.ts", "community": 0},
            {"id": "create_patch", "label": "createPatchHandler()",
             "source_file": "server/create-patch-handler.ts", "community": 0},
            {"id": "create_edit", "label": "createEditHandler()",
             "source_file": "server/create-edit-handler.ts", "community": 0},
            {"id": "stable_stringify", "label": "stableStringify()",
             "source_file": "shared/stringify.ts", "community": 0},
        ],
        "links": [
            {"source": "create_patch", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "create_edit", "target": "validate",
             "relation": "calls", "confidence": "EXTRACTED"},
            {"source": "validate", "target": "stable_stringify",
             "relation": "calls", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def _run(monkeypatch, graph_path, label, capsys):
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", label, "--graph", str(graph_path)])
    mainmod.main()
    return capsys.readouterr().out


def test_callee_shows_callers_as_inbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "<-- createPatchHandler() [calls]" in out
    assert "<-- createEditHandler() [calls]" in out
    assert "--> stableStringify() [calls]" in out
    assert "--> createPatchHandler() [calls]" not in out
    assert "--> createEditHandler() [calls]" not in out


def test_caller_shows_callee_as_outbound(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "createPatchHandler", capsys)
    assert "--> validateSanitySession() [calls]" in out
    assert "<-- " not in out


def test_explain_source_file_path_prefers_file_level_node(monkeypatch, tmp_path, capsys):
    source_file = "app/api/example/route.ts"
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "example_route_get", "label": "GET()",
             "source_file": source_file, "source_location": "L42", "community": 0},
            {"id": "example_route", "label": "route.ts",
             "source_file": source_file, "source_location": "L1", "community": 0},
        ],
        "links": [
            {"source": "example_route", "target": "example_route_get",
             "relation": "contains", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))

    out = _run(monkeypatch, p, source_file, capsys)

    assert "Node: route.ts" in out
    assert "ID:        example_route" in out
    assert f"Source:    {source_file} L1" in out
    assert "Node: GET()" not in out


# --- work-memory overlay Lesson line ------------------------------------------

def _write_sidecar(tmp_path, nodes):
    (tmp_path / ".graphify_learning.json").write_text(
        json.dumps({"version": 1, "generated_at": "2026-06-01T00:00:00+00:00",
                    "nodes": nodes}),
        encoding="utf-8",
    )


def test_explain_shows_preferred_lesson_line(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    _write_sidecar(tmp_path, {
        "validate": {"status": "preferred", "score": 2.4, "uses": 3,
                     "label": "validateSanitySession()", "source_file": "",
                     "code_fingerprint": "", "provenance": []},
    })
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Lesson: preferred source (start here) — 3 useful, score=2.4" in out
    assert "code changed" not in out


def test_explain_shows_contested_and_stale_lesson(monkeypatch, tmp_path, capsys):
    p = _write_graph(tmp_path)
    # source_file points at a path that does not exist -> loader marks it stale.
    _write_sidecar(tmp_path, {
        "validate": {"status": "contested", "score": -0.1, "uses": 2, "neg": 1,
                     "verdict": "dead end", "label": "validateSanitySession()",
                     "source_file": "server/sanity-validate-session.ts",
                     "code_fingerprint": "deadbeef", "provenance": []},
    })
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Lesson: contested (useful 2 / dead-end 1)" in out
    assert "[code changed since — re-verify]" in out


def test_explain_no_lesson_line_for_unannotated_node(monkeypatch, tmp_path, capsys):
    """No sidecar => no Lesson line; output identical to pre-feature."""
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Lesson:" not in out


# --- #1613: ambiguous exact-tier matches are surfaced, not silently guessed ---

def _write_ambiguous_graph(tmp_path):
    """Two distinct, unrelated nodes that both exact-match the label 'genres' —
    reproduces the real repro (`explain "genres"` silently resolving to an
    unrelated Storybook literal while the actually-relevant node sat one
    position later in the tied candidate list, discarded)."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "storybook_genres", "label": "genres",
             "source_file": "MediaFilterBar.stories.tsx", "community": 0},
            {"id": "lookups_genres_response", "label": "genres",
             "source_file": "useMediaLookups.ts", "community": 1},
        ],
        "links": [],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_explain_ambiguous_exact_match_lists_candidates_instead_of_guessing(monkeypatch, tmp_path, capsys):
    p = _write_ambiguous_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "genres", "--graph", str(p)])
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Ambiguous: 2 nodes match 'genres' equally closely." in out
    assert "1. genres [src=MediaFilterBar.stories.tsx" in out
    assert "2. genres [src=useMediaLookups.ts" in out
    # Must not silently commit to and fully render either one.
    assert "Node: genres" not in out
    assert "Connections" not in out


def test_explain_force_bypasses_ambiguity_guard(monkeypatch, tmp_path, capsys):
    """--force reproduces the old (pre-#1613) behavior: silently take matches[0]."""
    p = _write_ambiguous_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "genres", "--graph", str(p), "--force"])
    mainmod.main()
    out = capsys.readouterr().out
    assert "Ambiguous:" not in out
    assert out.startswith("Node: genres")


def test_explain_unambiguous_match_is_unaffected(monkeypatch, tmp_path, capsys):
    """A label with exactly one exact-tier match still resolves directly,
    with no ambiguity notice — the #853-era tests above already cover this for
    the general case; this test pins it explicitly against the new code path."""
    p = _write_graph(tmp_path)
    out = _run(monkeypatch, p, "validateSanitySession", capsys)
    assert "Ambiguous:" not in out
    assert out.startswith("Node: validateSanitySession()")


def test_explain_source_exact_preferred_resolution_is_not_flagged_ambiguous(monkeypatch, tmp_path, capsys):
    """The pre-existing file-level-node preference (#853-adjacent) already
    resolves a 2-candidate source_exact tier to one deliberate winner — this
    must NOT be treated as a #1613 ambiguity, even though the tier itself has
    more than one entry. Regression pin for the interaction bug caught while
    building #1613 (test_explain_source_file_path_prefers_file_level_node)."""
    p = tmp_path / "graph.json"
    source_file = "app/api/example/route.ts"
    p.write_text(json.dumps({
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "example_route_get", "label": "GET()",
             "source_file": source_file, "source_location": "L42", "community": 0},
            {"id": "example_route", "label": "route.ts",
             "source_file": source_file, "source_location": "L1", "community": 0},
        ],
        "links": [
            {"source": "example_route", "target": "example_route_get",
             "relation": "contains", "confidence": "EXTRACTED"},
        ],
    }))
    out = _run(monkeypatch, p, source_file, capsys)
    assert "Ambiguous:" not in out
    assert out.startswith("Node: route.ts")


def _write_precedence_collapse_graph(tmp_path):
    """A weakly-connected node whose label exact-matches the term, plus a
    strongly-relevant node one tier down (prefix match only) that the exact
    tier's precedence would otherwise fully hide. This is the real repro
    shape: `explain "genres"` resolved to an isolated Storybook literal
    (degree 1, exact tier) while `GenresResponse` in useMediaLookups.ts
    (degree 1, prefix tier only) sat one tier lower, fully discarded — same
    tier-precedence collapse, reproduced here with a connected neighbor added
    so the "actually relevant" candidate is distinguishable from noise."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "storybook_genres", "label": "genres",
             "source_file": "MediaFilterBar.stories.tsx", "community": 0},
            {"id": "genres_response", "label": "GenresResponse",
             "source_file": "useMediaLookups.ts", "community": 1},
            {"id": "use_media_lookups", "label": "useMediaLookups()",
             "source_file": "useMediaLookups.ts", "community": 1},
        ],
        "links": [
            {"source": "use_media_lookups", "target": "genres_response",
             "relation": "returns", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_explain_precedence_collapse_surfaces_lower_tier_candidate(monkeypatch, tmp_path, capsys):
    p = _write_precedence_collapse_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "genres", "--graph", str(p)])
    with pytest.raises(SystemExit) as exc:
        mainmod.main()
    assert exc.value.code == 0
    out = capsys.readouterr().out
    assert "Ambiguous: the closest match for 'genres' is weakly connected" in out
    assert "genres [src=MediaFilterBar.stories.tsx" in out
    assert "GenresResponse [src=useMediaLookups.ts" in out


def test_explain_precedence_collapse_does_not_fire_for_well_connected_exact_match(monkeypatch, tmp_path, capsys):
    """A well-connected exact match (degree > 1) must resolve exactly as
    before — the heuristic is deliberately narrow (Cradle-style positive case:
    a real, central symbol should never be second-guessed just because a
    same-file-prefix node also happens to exist)."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "cradle", "label": "Cradle", "source_file": "container.ts", "community": 0},
            {"id": "cradle_options", "label": "CradleOptions", "source_file": "container.ts", "community": 0},
            {"id": "consumer_a", "label": "consumerA", "source_file": "a.ts", "community": 1},
            {"id": "consumer_b", "label": "consumerB", "source_file": "b.ts", "community": 1},
        ],
        "links": [
            {"source": "consumer_a", "target": "cradle", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "consumer_b", "target": "cradle", "relation": "imports", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    out = _run(monkeypatch, p, "Cradle", capsys)
    assert "Ambiguous:" not in out
    assert out.startswith("Node: Cradle")


def test_explain_multiple_same_label_ties_resolve_to_degree_dominant_winner(monkeypatch, tmp_path, capsys):
    """Real-repo shape found while verifying #1613 live: a DI container type
    name ("Cradle") legitimately appears as 3 distinct exact-tier nodes — the
    real definition (high degree) plus 2 per-file parameter-type annotations
    in unrelated handlers (each low degree). These are NOT a genuine ambiguity
    the same way "genres" was: one candidate dominates by degree, so
    `explain` must resolve straight to it, not prompt — mirrors `path`'s
    existing top-vs-runner-up gap check, applied to degree here."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "cradle_real", "label": "Cradle", "source_file": "container.ts", "community": 0},
            {"id": "cradle_ref_a", "label": "Cradle", "source_file": "automations.handler.ts", "community": 1},
            {"id": "cradle_ref_b", "label": "Cradle", "source_file": "mediaQueries.handler.ts", "community": 2},
        ] + [{"id": f"consumer_{i}", "label": f"consumer{i}", "source_file": f"c{i}.ts", "community": 3}
             for i in range(6)],
        "links": (
            [{"source": f"consumer_{i}", "target": "cradle_real",
              "relation": "imports", "confidence": "EXTRACTED"} for i in range(6)]
            + [{"source": "consumer_0", "target": "cradle_ref_a",
                "relation": "imports", "confidence": "EXTRACTED"}]
            + [{"source": "consumer_1", "target": "cradle_ref_b",
                "relation": "imports", "confidence": "EXTRACTED"}]
        ),
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    out = _run(monkeypatch, p, "Cradle", capsys)
    assert "Ambiguous:" not in out
    assert out.startswith("Node: Cradle")
    assert "ID:        cradle_real" in out


def test_explain_close_degree_ties_still_flagged_ambiguous(monkeypatch, tmp_path, capsys):
    """Contrast case: same shape as the dominance test above, but the 3
    same-label candidates have comparable (not dominant) degree — a genuine
    tie must still be flagged, not silently resolved to whichever happens to
    iterate first."""
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "cradle_a", "label": "Cradle", "source_file": "a.ts", "community": 0},
            {"id": "cradle_b", "label": "Cradle", "source_file": "b.ts", "community": 1},
            {"id": "consumer_a", "label": "consumerA", "source_file": "ca.ts", "community": 2},
            {"id": "consumer_b", "label": "consumerB", "source_file": "cb.ts", "community": 2},
        ],
        "links": [
            {"source": "consumer_a", "target": "cradle_a", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "consumer_b", "target": "cradle_b", "relation": "imports", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "Cradle", "--graph", str(p)])
    with pytest.raises(SystemExit):
        mainmod.main()
    out = capsys.readouterr().out
    assert "Ambiguous: 2 nodes match 'Cradle' equally closely." in out


def _write_ratings_graph(tmp_path):
    graph_data = {
        "directed": False, "multigraph": False, "graph": {},
        "nodes": [
            {"id": "agg", "label": "AggregatedRatings",
             "source_file": "server/utils/ratingsAggregation.ts", "community": 0},
            {"id": "fmt", "label": "formatRating()",
             "source_file": "server/utils/ratingsAggregation.ts", "community": 0},
            {"id": "unrelated", "label": "Sidebar",
             "source_file": "src/components/Sidebar/index.tsx", "community": 1},
        ],
        "links": [
            {"source": "fmt", "target": "agg", "relation": "uses", "confidence": "EXTRACTED"},
        ],
    }
    p = tmp_path / "graph.json"
    p.write_text(json.dumps(graph_data))
    return p


def test_explain_multiword_phrase_falls_back_to_term_overlap_candidates(monkeypatch, tmp_path, capsys):
    """#1616: no node's label literally contains the whole phrase "critic score
    aggregation" as a substring (the tier-matching `explain` normally uses), but
    "aggregation"/"rating" individually overlap with real nodes — the fallback
    should surface them instead of a bare "No node matching" dead end."""
    p = _write_ratings_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "critic score aggregation", "--graph", str(p)])
    with pytest.raises(SystemExit):
        mainmod.main()
    out = capsys.readouterr().out
    assert "No exact node matching 'critic score aggregation' found" in out
    assert "AggregatedRatings" in out
    assert "Sidebar" not in out


def test_explain_multiword_phrase_with_no_overlap_still_says_no_match(monkeypatch, tmp_path, capsys):
    """No token in the phrase overlaps any node at all — the fallback must not
    fabricate candidates; the original honest message stays."""
    p = _write_ratings_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "quantum flux capacitor", "--graph", str(p)])
    with pytest.raises(SystemExit):
        mainmod.main()
    out = capsys.readouterr().out
    assert "No node matching 'quantum flux capacitor' found." in out
    assert "candidates" not in out


def test_explain_single_word_miss_is_unaffected(monkeypatch, tmp_path, capsys):
    """Gate on >1 token (#1616): a single-word miss must keep the exact
    pre-existing message, not attempt the multi-token fallback (which would
    score identically to the substring tier already tried and add nothing)."""
    p = _write_ratings_graph(tmp_path)
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setattr(mainmod.sys, "argv",
        ["graphify", "explain", "zzzznomatch", "--graph", str(p)])
    with pytest.raises(SystemExit):
        mainmod.main()
    out = capsys.readouterr().out
    assert out == "No node matching 'zzzznomatch' found.\n"
