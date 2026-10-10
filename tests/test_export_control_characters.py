"""A control character in a label must not abort an export.

Labels reach the exporters unfiltered from the corpus. A markdown heading pasted
from a terminal capture carries ANSI escapes (`\\x1b`), and the form feed some
Python/Emacs sources use as a section separator is `\\x0c`. Both are ordinary
content, and detection, extraction and the graph build all accept them happily.

Two exporters then died on the whole graph:

* `to_graphml` -> `ValueError: All strings must be XML compatible: Unicode or
  ASCII, no NULL bytes or control characters` (XML 1.0 permits tab, LF and CR
  and no other C0 control);
* `to_obsidian` -> `OSError: [Errno 22] Invalid argument` on Windows, which
  rejects control characters in a path outright, so one bad label cost the
  entire vault rather than one note.

`to_cypher` already stripped them and `to_html` already routes labels through
`security.sanitize_label`, so the codebase knew the hazard — those two paths
just did not. (#2897)
"""
import json
import xml.etree.ElementTree as ET

import pytest

from graphify.build import build_from_json
from graphify.export import (
    _obsidian_safe_stem,
    to_cypher,
    to_graphml,
    to_json,
    to_obsidian,
    to_svg,
)

# Legal in XML and in a filename — these must survive untouched.
KEEP = ["\t", "\n", "\r"]
# Rejected by XML 1.0, and by Windows in a path.
BREAK = ["\x00", "\x07", "\x08", "\x0b", "\x0c", "\x1b", "\x1f"]


def _graph(label):
    return build_from_json({
        "nodes": [
            {"id": "a", "label": label, "file_type": "document", "source_file": "d.md"},
            {"id": "b", "label": "plain", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [{"source": "a", "target": "b", "relation": "references",
                   "confidence": "INFERRED", "confidence_score": 0.85,
                   "source_file": "d.md"}],
        "hyperedges": [],
    })


COMMUNITIES = {0: ["a", "b"]}


# ---------------------------------------------------------------------------
# GraphML
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch", BREAK)
def test_graphml_survives_a_control_character(tmp_path, ch):
    out = tmp_path / "g.graphml"
    to_graphml(_graph(f"Build {ch}log capture"), COMMUNITIES, str(out))
    ET.fromstring(out.read_text(encoding="utf-8"))  # must be well-formed XML


@pytest.mark.parametrize("ch", KEEP)
def test_graphml_keeps_the_whitespace_xml_allows(tmp_path, ch):
    """Tab, LF and CR are valid XML and carry meaning in a label; the fix must
    not sweep them up with the rest."""
    out = tmp_path / "g.graphml"
    to_graphml(_graph("a" + ch + "b"), COMMUNITIES, str(out))
    ET.fromstring(out.read_text(encoding="utf-8"))  # still well-formed
    # A writer may normalise CR to LF, so only the two that round-trip
    # literally are asserted to survive verbatim.
    if ch != "\r":
        assert ("a" + ch + "b") in out.read_text(encoding="utf-8")


def test_graphml_survives_a_control_character_in_a_node_id(tmp_path):
    """IDs become XML attributes too."""
    G = build_from_json({
        "nodes": [{"id": "we\x0bird", "label": "x", "file_type": "code",
                   "source_file": "a.py"}],
        "edges": [], "hyperedges": [],
    })
    out = tmp_path / "g.graphml"
    to_graphml(G, {0: ["we\x0bird"]}, str(out))
    ET.fromstring(out.read_text(encoding="utf-8"))


def test_graphml_still_carries_the_readable_part_of_the_label(tmp_path):
    out = tmp_path / "g.graphml"
    to_graphml(_graph("Build \x1b[31mlog\x1b[0m capture"), COMMUNITIES, str(out))
    text = out.read_text(encoding="utf-8")
    assert "log" in text and "capture" in text
    assert "\x1b" not in text


# ---------------------------------------------------------------------------
# Obsidian
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("ch", BREAK)
def test_obsidian_export_survives_a_control_character(tmp_path, ch):
    count = to_obsidian(_graph(f"Release {ch} Notes"), COMMUNITIES,
                        str(tmp_path / "vault"))
    assert count >= 2
    assert list((tmp_path / "vault").glob("*.md"))


@pytest.mark.parametrize("ch", BREAK + KEEP)
def test_no_stem_ever_contains_a_control_character(ch):
    stem = _obsidian_safe_stem(f"Release {ch} Notes")
    assert not any(ord(c) < 32 or ord(c) == 127 for c in stem), repr(stem)


def test_stem_keeps_the_words_around_the_control_character():
    assert _obsidian_safe_stem("Release \x0c Notes").startswith("Release")
    assert "Notes" in _obsidian_safe_stem("Release \x0c Notes")


def test_a_label_that_is_only_control_characters_still_yields_a_name():
    stem = _obsidian_safe_stem("\x00\x0b\x1b")
    assert stem and not any(ord(c) < 32 for c in stem)


# ---------------------------------------------------------------------------
# SVG
# ---------------------------------------------------------------------------

def _svg(tmp_path, G, community_labels=None, communities=COMMUNITIES):
    pytest.importorskip("matplotlib")
    out = tmp_path / "g.svg"
    to_svg(G, communities, str(out), community_labels=community_labels)
    return out.read_text(encoding="utf-8")


@pytest.mark.parametrize("ch", BREAK)
def test_svg_survives_a_control_character(tmp_path, ch):
    ET.fromstring(_svg(tmp_path, _graph(f"Build {ch}log capture")))  # must be well-formed XML


@pytest.mark.parametrize("ch", BREAK)
def test_svg_survives_a_control_character_in_a_community_label(tmp_path, ch):
    """The legend is a second path from a label to the file."""
    svg = _svg(tmp_path, _graph("plain"), {0: f"Core {ch}module"})
    ET.fromstring(svg)
    assert "Core" in svg and "module" in svg


@pytest.mark.parametrize("ch", KEEP)
def test_svg_keeps_the_whitespace_xml_allows(tmp_path, ch):
    """Tab, LF and CR are valid XML; the fix must not sweep them up with the rest."""
    svg = _svg(tmp_path, _graph(f"Release{ch}Notes"))
    ET.fromstring(svg)
    assert "Release" in svg and "Notes" in svg
    assert "ReleaseNotes" not in svg  # nothing was removed between the words


def test_svg_still_carries_the_readable_part_of_the_label(tmp_path):
    svg = _svg(tmp_path, _graph("Build \x1b[31mlog\x1b[0m capture"))
    assert "Build [31mlog[0m capture" in svg
    assert "\x1b" not in svg


def test_svg_clean_labels_are_unchanged(tmp_path):
    svg = _svg(tmp_path, _graph("Perfectly Ordinary Heading"), {0: "Ordinary Community"})
    assert "Perfectly Ordinary Heading" in svg
    assert "Ordinary Community (2)" in svg


@pytest.mark.parametrize("ch", BREAK)
def test_svg_survives_a_control_character_in_the_id_of_an_unlabelled_node(tmp_path, ch):
    """A node with no label is drawn under its id: a third path from text to the file."""
    G = build_from_json({
        "nodes": [{"id": f"we{ch}ird", "file_type": "code", "source_file": "a.py"}],
        "edges": [], "hyperedges": [],
    })
    svg = _svg(tmp_path, G, communities={0: [f"we{ch}ird"]})
    ET.fromstring(svg)
    assert "weird" in svg


def test_svg_draws_a_label_that_is_not_a_string(tmp_path):
    """nx.draw_networkx_labels str()s a non-string label on its own; the strip
    must not turn that into a TypeError, nor into an empty label."""
    G = _graph("x")
    G.nodes["a"]["label"] = 5
    del G.nodes["b"]["label"]  # falls back to the node id
    svg = _svg(tmp_path, G)
    ET.fromstring(svg)
    assert "<!-- 5 -->" in svg or ">5</text>" in svg  # svg.fonttype: path (default) or none


# ---------------------------------------------------------------------------
# The exporters that already coped must keep coping
# ---------------------------------------------------------------------------

def test_cypher_and_json_are_unaffected(tmp_path):
    G = _graph("Build \x1b[31mlog\x1b[0m capture")
    to_cypher(G, str(tmp_path / "g.cypher"))
    to_json(G, COMMUNITIES, str(tmp_path / "g.json"))
    json.loads((tmp_path / "g.json").read_text(encoding="utf-8"))
    assert "\x1b" not in (tmp_path / "g.cypher").read_text(encoding="utf-8")


def test_a_clean_label_round_trips_unchanged(tmp_path):
    """The fix must be invisible for ordinary labels."""
    G = _graph("Perfectly Ordinary Heading")
    out = tmp_path / "g.graphml"
    to_graphml(G, COMMUNITIES, str(out))
    assert "Perfectly Ordinary Heading" in out.read_text(encoding="utf-8")
    assert _obsidian_safe_stem("Perfectly Ordinary Heading") == "Perfectly Ordinary Heading"
