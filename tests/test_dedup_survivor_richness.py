"""Dedup survivor selection prefers content over ID shape (#3372).

`_pick_winner` scored purely on chunk-suffix + ID length, so a passing
one-line mention on a shallow page (short id) beat the dedicated, enriched
page for the same entity, and the losers were dropped wholesale — the
established node's attributes, description, confidence and merge history
were discarded every time the pattern occurred. Richness now decides first
(ID shape breaks ties), and the survivor is back-filled with any fields only
a loser carried.
"""

from graphify.dedup import _pick_winner, deduplicate_entities


def _rich(**over):
    node = {
        "id": "topics_networking_widget_x_widget_x",
        "label": "Widget X",
        "file_type": "concept",
        "source_file": "topics/networking/widget-x.md",
        "source_location": "L1",
        "description": "The flagship telemetry relay used by every edge deployment.",
        "attributes": {"protocol": "mqtt", "version": "3.2", "owner": "platform"},
        "confidence": "EXTRACTED",
        "_merged_from": ["widget_x_old"],
    }
    node.update(over)
    return node


def _shallow(**over):
    node = {
        "id": "sources_notes_widget_x",
        "label": "Widget X",
        "file_type": "concept",
        "source_file": "sources/notes.md",
        "source_location": "L14",
    }
    node.update(over)
    return node


def test_richer_node_survives_despite_longer_id():
    """The issue's exact shape: dedicated nested page vs shallow mention."""
    dn, _ = deduplicate_entities([_rich(), _shallow()], [], communities={})
    labels = [n for n in dn if n["label"] == "Widget X"]
    assert len(labels) == 1
    surv = labels[0]
    assert surv["id"] == "topics_networking_widget_x_widget_x"
    assert surv["attributes"] == {"protocol": "mqtt", "version": "3.2",
                                  "owner": "platform"}
    assert surv["_merged_from"] == ["widget_x_old"]


def test_loser_only_fields_are_folded_into_the_survivor():
    """Even the right winner must not lose what only a loser carried."""
    rich = _rich()
    shallow = _shallow(summary="Mentioned during the Q3 review.")
    dn, _ = deduplicate_entities([rich, shallow], [], communities={})
    surv = next(n for n in dn if n["label"] == "Widget X")
    assert surv["id"] == rich["id"]
    assert surv.get("summary") == "Mentioned during the Q3 review."
    # Never-override: the survivor's own fields stay its own.
    assert surv["description"].startswith("The flagship")


def test_equally_bare_nodes_keep_the_shorter_id_tiebreak():
    """Old deterministic ordering survives for content-equal candidates."""
    a = _shallow(id="a_widget_x", source_file="a/notes.md")
    b = _shallow(id="longer_b_widget_x", source_file="b/notes.md")
    assert _pick_winner([a, b])["id"] == "a_widget_x"
    assert _pick_winner([b, a])["id"] == "a_widget_x"


def test_chunk_suffix_still_dominates_richness():
    """A chunk-suffixed id never beats a clean one, however rich."""
    chunked = _rich(id="topics_widget_x_c3")
    clean = _shallow()
    assert _pick_winner([chunked, clean])["id"] == "sources_notes_widget_x"


def test_richness_counts_content_not_placement():
    from graphify.dedup import _content_richness

    assert _content_richness(_shallow()) == 0
    assert _content_richness(_rich()) > _content_richness(
        _rich(attributes={"protocol": "mqtt"}))


def test_provenance_beats_a_richer_sourceless_stub():
    """#3775: source_file/source_location are in _RICHNESS_IGNORED_KEYS, so
    a stub with no real location could out-score and replace a genuine,
    located declaration purely on incidental field count. The issue's own
    exact repro."""
    real = {
        "id": "docs_guide_setup", "label": "Setup", "file_type": "concept",
        "source_file": "docs/guide.md", "source_location": "L12",
        "attributes": {"kind": "section"},
    }
    stub = {
        "id": "setup", "label": "Setup", "file_type": "concept",
        "source_file": "", "type": "external", "external": True,
        "_origin": "semantic",
    }
    from graphify.dedup import _content_richness
    assert _content_richness(stub) > _content_richness(real), (
        "test fixture: the stub must out-score the real node on pure "
        "field count for this to exercise the bug"
    )
    assert _pick_winner([real, stub])["id"] == "docs_guide_setup"
    assert _pick_winner([stub, real])["id"] == "docs_guide_setup"


def test_richness_still_decides_when_both_sides_have_provenance():
    """The provenance tiebreak must only activate when the two sides
    disagree on having a source_file -- when both (or neither) have one,
    the existing #3372 richness-then-length ordering is unchanged."""
    rich = _rich()
    shallow = _shallow()
    assert rich["source_file"] and shallow["source_file"], (
        "test fixture: both candidates must carry a source_file so the "
        "provenance tiebreak cannot distinguish them"
    )
    assert _pick_winner([rich, shallow])["id"] == rich["id"]
    assert _pick_winner([shallow, rich])["id"] == rich["id"]


def test_located_record_beats_a_richer_source_file_only_stub():
    """Review finding on #3775: source_location is richness-ignored too, so
    two source-bearing candidates could still be ordered by field count
    alone, letting a record with a source_file but no source_location (the
    codebase genuinely emits source_location: None, see
    _merge_missing_attributes) out-score one that also knows exactly where
    in the file it lives."""
    located = {
        "id": "docs_guide_setup", "label": "Setup", "file_type": "concept",
        "source_file": "docs/guide.md", "source_location": "L12",
    }
    unlocated_but_richer = {
        "id": "setup", "label": "Setup", "file_type": "concept",
        "source_file": "docs/guide.md", "source_location": None,
        "attributes": {"kind": "section"}, "description": "extra content",
    }
    from graphify.dedup import _content_richness
    assert _content_richness(unlocated_but_richer) > _content_richness(located), (
        "test fixture: the unlocated stub must out-score the located node "
        "on pure field count for this to exercise the bug"
    )
    assert _pick_winner([located, unlocated_but_richer])["id"] == "docs_guide_setup"
    assert _pick_winner([unlocated_but_richer, located])["id"] == "docs_guide_setup"


def test_richness_still_decides_when_both_sides_have_a_location():
    """The source_location tiebreak must only activate when the two sides
    disagree on having one -- when both have a real location, richness (then
    length) still decides, same as before this fix."""
    rich = _rich()
    shallow = _shallow()
    assert rich["source_location"] and shallow["source_location"], (
        "test fixture: both candidates must carry a source_location so the "
        "location tiebreak cannot distinguish them"
    )
    assert _pick_winner([rich, shallow])["id"] == rich["id"]
    assert _pick_winner([shallow, rich])["id"] == rich["id"]


def test_a_stray_source_location_without_a_source_file_grants_no_edge():
    """Review finding on PR 3786: a source_location with no source_file (a
    location pointing at an unstated file -- possible if a survivor's own
    source_file is an empty string rather than None when
    _merge_missing_attributes backfills only source_location) is not a real
    provenance signal and must not out-rank a fully bare candidate that
    happens to be richer. Richness decides here, same as if neither side
    had any provenance field at all."""
    stray_location = {
        "id": "b_setup", "label": "Setup", "file_type": "concept",
        "source_file": "", "source_location": "L9",
    }
    richer_bare = {
        "id": "a_setup", "label": "Setup", "file_type": "concept",
        "source_file": "", "attributes": {"kind": "section"},
        "description": "more content",
    }
    from graphify.dedup import _content_richness
    assert _content_richness(richer_bare) > _content_richness(stray_location), (
        "test fixture: the bare candidate must out-score the stray-location "
        "one on richness for this to exercise the gate"
    )
    assert _pick_winner([stray_location, richer_bare])["id"] == "a_setup"
    assert _pick_winner([richer_bare, stray_location])["id"] == "a_setup"


def test_edges_rewire_to_the_rich_survivor():
    edges = [{"source": "sources_notes_widget_x", "target": "other",
              "relation": "references", "source_file": "sources/notes.md"}]
    dn, de = deduplicate_entities(
        [_rich(), _shallow(), {"id": "other", "label": "Other page",
                               "file_type": "concept",
                               "source_file": "docs/other.md"}],
        edges, communities={})
    assert de[0]["source"] == "topics_networking_widget_x_widget_x"
