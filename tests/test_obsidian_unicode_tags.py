"""Regression tests for issue #2862: community tags must survive non-ASCII labels,
and the graph-view colour groups must query the tag the notes actually carry."""
import json

import networkx as nx

from graphify.export import _obsidian_tag, to_obsidian


def _graph(labels: list[str]) -> tuple[nx.Graph, dict[int, list[str]], dict[int, str]]:
    """One node per community, so each community label reaches exactly one note."""
    G = nx.Graph()
    comms: dict[int, list[str]] = {}
    names: dict[int, str] = {}
    for cid, label in enumerate(labels):
        nid = f"n{cid}"
        G.add_node(nid, label=f"node {cid}", file_type="document",
                   source_file="doc.md", community=cid)
        comms[cid] = [nid]
        names[cid] = label
    return G, comms, names


def _tags(out_dir) -> set[str]:
    found = set()
    for md in out_dir.glob("*.md"):
        for line in md.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith("- community/"):
                found.add(line[len("- "):])
    return found


def test_non_latin_labels_keep_their_letters():
    assert _obsidian_tag("참여기업 로고 자산") == "참여기업_로고_자산"   # Hangul
    assert _obsidian_tag("データ 抽出") == "データ_抽出"                # Japanese
    assert _obsidian_tag("Träning Pipeline") == "Träning_Pipeline"     # accented Latin
    assert _obsidian_tag("Attention Mechanism") == "Attention_Mechanism"


def test_punctuation_is_still_stripped():
    assert _obsidian_tag("Auth · Session") == "Auth__Session"   # · dropped, spaces kept
    assert _obsidian_tag("a#b c") == "ab_c"
    assert _obsidian_tag("Auth/Session") == "Auth/Session"      # slashes are nesting


def test_degenerate_labels_stay_valid_tags():
    assert _obsidian_tag("···") == "unnamed"        # nothing left after stripping
    assert _obsidian_tag("2026") == "c2026"         # Obsidian ignores digits-only tags


def test_distinct_non_latin_communities_get_distinct_tags(tmp_path):
    """Before the fix every non-Latin label collapsed to '_'/'__', so all notes
    shared one tag and community navigation stopped working."""
    G, comms, names = _graph(["참여기업 로고 자산", "발주처 체계", "データ 抽出"])
    to_obsidian(G, comms, str(tmp_path), community_labels=names)
    tags = _tags(tmp_path)
    assert len(tags) == 3, tags
    assert "community/참여기업_로고_자산" in tags


def test_graph_view_colour_group_matches_the_note_tag(tmp_path):
    """`.obsidian/graph.json` colour groups were built from the raw label, so on a
    non-ASCII label they queried a tag no note carries."""
    G, comms, names = _graph(["참여기업 로고 자산", "발주처 체계"])
    to_obsidian(G, comms, str(tmp_path), community_labels=names)

    config = json.loads((tmp_path / ".obsidian" / "graph.json").read_text(encoding="utf-8"))
    queried = {
        group["query"].split("tag:#", 1)[1]
        for group in config.get("colorGroups", [])
        if "tag:#" in group.get("query", "")
    }
    assert queried, "no colour-group queries were written"
    assert queried <= _tags(tmp_path), (queried, _tags(tmp_path))
