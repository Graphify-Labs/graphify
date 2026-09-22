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


def test_edges_rewire_to_the_rich_survivor():
    edges = [{"source": "sources_notes_widget_x", "target": "other",
              "relation": "references", "source_file": "sources/notes.md"}]
    dn, de = deduplicate_entities(
        [_rich(), _shallow(), {"id": "other", "label": "Other page",
                               "file_type": "concept",
                               "source_file": "docs/other.md"}],
        edges, communities={})
    assert de[0]["source"] == "topics_networking_widget_x_widget_x"
