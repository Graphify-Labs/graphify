"""Regression tests for issue #1094: to_obsidian / to_canvas must cap filenames
to stay under the 255-byte filesystem limit, instead of crashing with
OSError ENAMETOOLONG on long node labels."""
import networkx as nx

from graphify.export import to_obsidian, to_canvas


def _graph(labels: list[str]) -> tuple[nx.Graph, dict[int, list[str]]]:
    G = nx.Graph()
    ids = []
    for i, lab in enumerate(labels):
        nid = f"n{i}"
        G.add_node(nid, label=lab, file_type="code", source_file="x.py", community=0)
        ids.append(nid)
    # chain them so each note has at least one wikilink
    for a, b in zip(ids, ids[1:]):
        G.add_edge(a, b, relation="calls", confidence="EXTRACTED")
    return G, {0: ids}


def _max_name_bytes(out_dir) -> int:
    return max(len(p.name.encode("utf-8")) for p in out_dir.glob("*.md"))


def test_obsidian_long_ascii_label_does_not_crash(tmp_path):
    G, comms = _graph(["a" * 300, "short"])
    to_obsidian(G, comms, str(tmp_path))
    assert _max_name_bytes(tmp_path) <= 255


def test_obsidian_long_cjk_label_byte_cap(tmp_path):
    # 200 CJK chars = 600 bytes in UTF-8: a char cap would still overflow.
    G, comms = _graph(["中" * 300, "ok"])
    to_obsidian(G, comms, str(tmp_path))
    assert _max_name_bytes(tmp_path) <= 255


def test_obsidian_distinct_long_labels_sharing_prefix_do_not_collide(tmp_path):
    prefix = "z" * 250
    G, comms = _graph([prefix + "_ALPHA", prefix + "_BETA"])
    to_obsidian(G, comms, str(tmp_path))
    md_files = [p for p in tmp_path.glob("*.md") if not p.name.startswith("_COMMUNITY_")]
    # Two distinct nodes must produce two distinct files (no overwrite).
    assert len(md_files) == 2, [p.name for p in md_files]
    assert _max_name_bytes(tmp_path) <= 255


def test_obsidian_wikilink_resolves_after_truncation(tmp_path):
    long_label = "w" * 300
    G, comms = _graph([long_label, "neighbor"])
    to_obsidian(G, comms, str(tmp_path))

    # The note for "neighbor" should link to the truncated filename of long_label.
    neighbor_note = (tmp_path / "neighbor.md").read_text()
    # Extract the [[target]] from the neighbor's Connections section.
    import re
    targets = re.findall(r"\[\[([^\]]+)\]\]", neighbor_note)
    assert targets, "no wikilink found in neighbor note"
    # Every linked target must correspond to a real .md file on disk.
    for t in targets:
        assert (tmp_path / f"{t}.md").exists(), f"dangling wikilink: {t}"


def test_canvas_long_label_file_ref_capped(tmp_path):
    import json
    G, comms = _graph(["c" * 300, "ok"])
    out = tmp_path / "graph.canvas"
    to_canvas(G, comms, str(out))
    data = json.loads(out.read_text())
    for node in data.get("nodes", []):
        if node.get("type") == "file":
            assert len(node["file"].encode("utf-8")) <= 255, node["file"]


# ---------------------------------------------------------------------------
# #1409 — all-punctuation labels must not produce punctuation-only filenames
# ---------------------------------------------------------------------------

def test_obsidian_all_punctuation_label_falls_back_to_unnamed(tmp_path):
    """A label like '@/*' becomes 'unnamed.md', not '@.md' (#1409)."""
    G, comms = _graph(["@/*", "normal"])
    to_obsidian(G, comms, str(tmp_path))
    md_files = {p.name for p in tmp_path.glob("*.md") if not p.name.startswith("_COMMUNITY_")}
    assert "@.md" not in md_files, "punctuation-only filename was emitted"
    assert "unnamed.md" in md_files or any(f.startswith("unnamed") for f in md_files)


def test_obsidian_at_sign_only_label_falls_back_to_unnamed(tmp_path):
    """A label '@' (already bare punctuation) maps to 'unnamed.md', not '@.md'."""
    G, comms = _graph(["@", "ok"])
    to_obsidian(G, comms, str(tmp_path))
    md_files = {p.name for p in tmp_path.glob("*.md") if not p.name.startswith("_COMMUNITY_")}
    assert "@.md" not in md_files
    assert any(f.startswith("unnamed") for f in md_files)


def test_obsidian_label_with_word_chars_not_affected(tmp_path):
    """Labels like '@types/node' still produce a word-char-containing filename."""
    G, comms = _graph(["@types/node", "ok"])
    to_obsidian(G, comms, str(tmp_path))
    md_files = {p.name for p in tmp_path.glob("*.md") if not p.name.startswith("_COMMUNITY_")}
    # '@types/node' → strip '/' → '@typesnode' → '@typesnode.md'
    assert any("types" in f or "node" in f for f in md_files), md_files


def test_canvas_all_punctuation_label_falls_back_to_unnamed(tmp_path):
    """to_canvas safe_name also maps all-punctuation labels to 'unnamed' (#1409)."""
    import json
    G, comms = _graph(["@/*", "ok"])
    out = tmp_path / "graph.canvas"
    to_canvas(G, comms, str(out))
    data = json.loads(out.read_text())
    for node in data.get("nodes", []):
        if node.get("type") == "file":
            stem = node["file"].rstrip("/").split("/")[-1].replace(".md", "")
            assert stem != "@", f"punctuation-only canvas file ref: {node['file']}"
