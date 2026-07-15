import json
import math
import re
import tempfile
from pathlib import Path
from graphify.build import build_from_json
from graphify.cluster import cluster
from graphify.export import to_json, to_cypher, to_graphml, to_html, to_canvas, to_obsidian

FIXTURES = Path(__file__).parent / "fixtures"

def make_graph():
    return build_from_json(json.loads((FIXTURES / "extraction.json").read_text()))

def test_to_json_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        assert out.exists()

def test_to_json_valid_json():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        assert "nodes" in data
        assert "links" in data

def test_to_json_nodes_have_community():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.json"
        to_json(G, communities, str(out))
        data = json.loads(out.read_text())
        for node in data["nodes"]:
            assert "community" in node

def test_to_cypher_creates_file():
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        assert out.exists()

def test_to_cypher_contains_merge_statements():
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "cypher.txt"
        to_cypher(G, str(out))
        content = out.read_text()
        assert "MERGE" in content

def test_to_graphml_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        assert out.exists()

def test_to_graphml_valid_xml():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        content = out.read_text()
        assert "<graphml" in content
        assert "<node" in content

def test_to_graphml_has_community_attribute():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))
        content = out.read_text()
        assert "community" in content

def test_to_graphml_tolerates_none_attribute_values():
    """nx.write_graphml raises ValueError on a None attribute value; to_graphml
    must coerce None -> "" so a node/edge with a null field still exports (#1502)."""
    G = make_graph()
    communities = cluster(G)
    # Inject a None-valued attribute on one node and one edge.
    a_node = next(iter(G.nodes()))
    G.nodes[a_node]["nullable_field"] = None
    if G.number_of_edges():
        u, v = next(iter(G.edges()))
        G.edges[u, v]["nullable_field"] = None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))  # must not raise
        content = out.read_text()
        assert "<graphml" in content

def test_to_graphml_tolerates_dict_and_list_attribute_values():
    """nx.write_graphml only accepts scalars; a dict/list attribute (per-node
    metadata, or the graph-level hyperedges list) used to crash the whole export.
    to_graphml must JSON-serialize them across graph/node/edge scopes (#1831)."""
    import networkx as nx
    G = make_graph()
    communities = cluster(G)
    a_node = next(iter(G.nodes()))
    G.nodes[a_node]["metadata"] = {"kind": "file", "size": 12}
    G.nodes[a_node]["tags"] = ["x", "y"]
    if G.number_of_edges():
        u, v = next(iter(G.edges()))
        G.edges[u, v]["ctx"] = {"k": "v"}
    G.graph["hyperedges"] = [{"nodes": [a_node], "label": "h"}]
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.graphml"
        to_graphml(G, communities, str(out))  # must not raise
        H = nx.read_graphml(str(out))
        assert json.loads(H.nodes[a_node]["metadata"]) == {"kind": "file", "size": 12}
        assert json.loads(H.nodes[a_node]["tags"]) == ["x", "y"]
        assert json.loads(H.graph["hyperedges"]) == [{"nodes": [a_node], "label": "h"}]
        assert not (Path(tmp) / "graph.graphml.tmp").exists()


def test_to_graphml_preserves_native_scalar_types():
    """Coercion must leave GraphML-native scalars (int/float/bool/str) untouched,
    only stringifying non-scalars (#1831)."""
    import networkx as nx
    G = nx.Graph()
    G.add_node("a", count=3, ratio=0.5, flag=True, name="x")
    G.add_node("b")
    G.add_edge("a", "b")
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "g.graphml"
        to_graphml(G, {0: ["a", "b"]}, str(out))
        H = nx.read_graphml(str(out))
        assert H.nodes["a"]["count"] == 3
        assert H.nodes["a"]["ratio"] == 0.5
        assert H.nodes["a"]["flag"] is True
        assert H.nodes["a"]["name"] == "x"


def test_to_html_creates_file():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        assert out.exists()

def test_to_html_contains_visjs():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "vis-network" in content


def test_to_html_neighbor_links_have_no_inline_onclick_xss():
    """#1838: neighbor links dropped an unescaped JSON.stringify(nid) into a
    quoted inline onclick — which broke every link (the value's own quotes
    truncated the attribute) and let a node id/label containing a double-quote
    (from a document or a scraped `graphify add` URL) inject a live event handler
    into the local report (stored XSS). The template must instead carry the id in
    an escaped data attribute and dispatch via one delegated listener."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        html = out.read_text()
    # The vulnerable inline handler is gone entirely...
    assert 'onclick="focusNode(' not in html
    assert "JSON.stringify(nid)" not in html
    # ...replaced by an escaped data attribute + a single delegated listener.
    assert 'data-nid="${esc(nid)}"' in html
    assert "closest('.neighbor-link')" in html


def test_to_html_pins_visjs_version_with_sri():
    """vis-network script tag must use a pinned versioned URL with a sha384
    Subresource Integrity hash and crossorigin=anonymous. Without this,
    a compromised CDN could ship arbitrary JavaScript into every rendered
    graph viewer. The hash was verified against the upstream file at
    https://unpkg.com/vis-network@9.1.6/standalone/umd/vis-network.min.js
    (sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1).
    Bumping the vis-network version MUST update both the URL and the hash.
    """
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()

    # Versioned URL — unversioned `vis-network/standalone/...` is rejected.
    assert "vis-network@9.1.6/standalone/umd/vis-network.min.js" in content
    assert "https://unpkg.com/vis-network/standalone" not in content

    # SRI integrity attribute pinning the known-good hash.
    assert 'integrity="sha384-Ux6phic9PEHJ38YtrijhkzyJ8yQlH8i/+buBR8s3mAZOJrP1gwyvAcIYl3GWtpX1"' in content

    # crossorigin="anonymous" is required for SRI on cross-origin scripts.
    assert 'crossorigin="anonymous"' in content

def test_to_html_contains_search():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "search" in content.lower()

def test_to_html_contains_legend_with_labels():
    G = make_graph()
    communities = cluster(G)
    labels = {cid: f"Group {cid}" for cid in communities}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), community_labels=labels)
        content = out.read_text()
        assert "Group 0" in content

def test_to_html_contains_nodes_and_edges():
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out))
        content = out.read_text()
        assert "RAW_NODES" in content
        assert "RAW_EDGES" in content


def test_to_html_member_counts_accepted():
    """to_html accepts member_counts without raising."""
    G = make_graph()
    communities = cluster(G)
    member_counts = {cid: len(members) for cid, members in communities.items()}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), member_counts=member_counts)
        assert out.exists()


def _vis_nodes_from_html(content: str) -> list:
    """Extract the RAW_NODES JSON array embedded in the generated HTML."""
    m = re.search(r"const RAW_NODES = (\[.*?\]);", content, re.DOTALL)
    assert m, "RAW_NODES not found in HTML"
    return json.loads(m.group(1).replace("<\\/", "</"))


def test_to_html_annotated_node_gets_learning_status_and_ring():
    """A node with an overlay entry gets learning_status + learning_stale fields,
    a status-colored ring (border), and a Lesson line in its hover title."""
    G = make_graph()
    communities = cluster(G)
    overlay = {
        "n_transformer": {"status": "preferred", "uses": 3, "score": 2.4,
                          "stale": False, "neg": 0},
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), learning_overlay=overlay)
        content = out.read_text()
    nodes = {n["id"]: n for n in _vis_nodes_from_html(content)}
    ann = nodes["n_transformer"]
    assert ann["learning_status"] == "preferred"
    assert ann["learning_stale"] is False
    assert ann["color"]["border"] == "#22c55e"  # green ring for preferred
    assert ann.get("borderWidth") == 3
    assert "Lesson: preferred source" in ann["title"]
    # An un-annotated node carries no learning fields.
    other = next(n for nid, n in nodes.items() if nid != "n_transformer")
    assert "learning_status" not in other
    assert "learning_stale" not in other


def test_to_html_contested_stale_node_gets_dashed_desaturated_ring():
    G = make_graph()
    communities = cluster(G)
    overlay = {
        "n_transformer": {"status": "contested", "uses": 2, "neg": 1,
                          "verdict": "dead end", "stale": True},
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.html"
        to_html(G, communities, str(out), learning_overlay=overlay)
        content = out.read_text()
    ann = {n["id"]: n for n in _vis_nodes_from_html(content)}["n_transformer"]
    assert ann["learning_status"] == "contested"
    assert ann["learning_stale"] is True
    assert ann["color"]["border"] == "#9ca3af"  # desaturated when stale
    assert ann["shapeProperties"]["borderDashes"] == [4, 4]
    assert "code changed" in ann["title"]


def test_to_html_unannotated_identical_to_pre_feature():
    """With no overlay, the HTML is byte-identical whether learning_overlay is
    omitted or passed empty — no learning fields leak into the un-annotated render."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp) / "a.html"
        b = Path(tmp) / "b.html"
        to_html(G, communities, str(a))
        to_html(G, communities, str(b), learning_overlay={})
        # Output path appears in the title, so compare with paths normalized out.
        ca = a.read_text().replace("a.html", "X.html")
        cb = b.read_text().replace("b.html", "X.html")
    assert ca == cb
    assert "learning_status" not in ca


def test_to_canvas_file_paths_relative_to_vault():
    """Node file paths in canvas must be vault-root-relative (just fname.md), not hardcoded."""
    G = make_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        file_nodes = [n for n in data["nodes"] if n.get("type") == "file"]
        assert file_nodes, "canvas should contain file nodes"
        for node in file_nodes:
            assert "/" not in node["file"], f"file path should not contain '/': {node['file']}"
            assert node["file"].endswith(".md")


def test_to_canvas_no_communities_still_populates():
    """#1324: empty communities (e.g. --no-cluster builds) on a populated graph
    must NOT produce the 32-byte empty `{"nodes": [], "edges": []}` shell."""
    G = make_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, {}, str(out))  # no community data — the bug condition
        data = json.loads(out.read_text())
        assert len(data["nodes"]) >= G.number_of_nodes()
        assert len(data["edges"]) >= 1
        assert out.stat().st_size > 32


def test_to_canvas_node_grid_matches_box_columns():
    """#1452: a community's node cards are laid out in the same ceil(sqrt(n))-column
    grid the group box is sized for. Previously the box width assumed sqrt(n)
    columns while the placement loop hardcoded 3, so any community bigger than ~9
    rendered as a cramped 3-wide strip filling only part of an over-wide box.
    Covers a perfect square (25 -> 5x5) and a non-square count (10 -> 4 cols, a
    partial last row) so both the column count and the row count are pinned."""
    for n in (10, 25):
        G = build_from_json({
            "nodes": [
                {"id": f"n{i}", "label": f"sym_{i:02d}", "file_type": "code", "source_file": "a.py"}
                for i in range(n)
            ],
            "edges": [],
        })
        communities = {0: [f"n{i}" for i in range(n)]}
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "graph.canvas"
            to_canvas(G, communities, str(out))
            data = json.loads(out.read_text())

        group = next(g for g in data["nodes"] if g.get("type") == "group")
        cards = [c for c in data["nodes"] if c.get("type") == "file"]
        assert len(cards) == n, f"n={n}"

        # Cards occupy the ceil(sqrt(n))-column / ceil(n/cols)-row grid the box is
        # sized for — not the old fixed 3 columns, which spread cards across far
        # more rows (the load-bearing checks: distinct column/row positions).
        expected_cols = math.ceil(math.sqrt(n))
        expected_rows = math.ceil(n / expected_cols)
        distinct_x = len({c["x"] for c in cards})
        distinct_y = len({c["y"] for c in cards})
        assert distinct_x == expected_cols, f"n={n}: expected {expected_cols} cols, got {distinct_x}"
        assert distinct_y == expected_rows, f"n={n}: expected {expected_rows} rows, got {distinct_y}"

        # And every card sits fully inside its group box on both axes.
        gx, gy, gw, gh = group["x"], group["y"], group["width"], group["height"]
        for c in cards:
            assert gx <= c["x"] and c["x"] + c["width"] <= gx + gw, (n, c)
            assert gy <= c["y"] and c["y"] + c["height"] <= gy + gh, (n, c)


# ── Issue #1409: punctuation-only Obsidian/Canvas filenames ───────────────────

def _punct_graph(label: str):
    """A 2-node graph where one node's label is all-punctuation (e.g. a `@/*`
    tsconfig paths key) and the other is a normal symbol."""
    return build_from_json({
        "nodes": [
            {"id": "n1", "label": label, "file_type": "code", "source_file": "tsconfig.json"},
            {"id": "n2", "label": "AuthHandler", "file_type": "code", "source_file": "auth.ts"},
        ],
        "edges": [],
    })


def test_to_obsidian_never_emits_punctuation_only_filenames():
    """#1409: an all-punctuation label (e.g. `@/*`) must not produce a `@.md`-style
    filename — valid on disk but empty once a downstream tool re-slugs on word chars
    (crashes `qmd update`). It falls back to `unnamed`."""
    G = _punct_graph("@/*")
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        to_obsidian(G, communities, tmp)
        stems = [p.stem for p in Path(tmp).rglob("*.md")]
        assert stems, "to_obsidian wrote no notes"
        bad = [s for s in stems if not re.search(r"\w", s, flags=re.UNICODE)]
        assert not bad, f"punctuation-only filenames emitted: {bad}"
        assert any(s == "unnamed" or s.startswith("unnamed") for s in stems), stems


def test_to_canvas_never_emits_punctuation_only_filenames():
    """#1409: same guard on the canvas exporter's file-node names."""
    G = _punct_graph("@")
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        file_nodes = [n for n in data["nodes"] if n.get("type") == "file"]
        assert file_nodes, "canvas has no file nodes"
        bad = [n["file"] for n in file_nodes if not re.search(r"\w", Path(n["file"]).stem, flags=re.UNICODE)]
        assert not bad, f"punctuation-only canvas filenames: {bad}"


# ── Existing-vault safety: graphify must not clobber user notes / .obsidian (#1506) ──

def _two_node_graph():
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="Database", community=0, source_file="app/db.py", type="code")
    G.add_node("n2", label="Server", community=0, source_file="app/srv.py", type="code")
    G.add_edge("n1", "n2")
    return G, {0: ["n1", "n2"]}


def test_to_obsidian_preserves_existing_user_notes_and_obsidian_config():
    """#1506: exporting into an existing vault must not overwrite a user's note that
    collides with a graphify node name, nor their .obsidian/ graph settings."""
    G, communities = _two_node_graph()
    with tempfile.TemporaryDirectory() as tmp:
        vault = Path(tmp)
        (vault / "Database.md").write_text("# MY NOTES\nkeep me\n", encoding="utf-8")
        (vault / ".obsidian").mkdir()
        (vault / ".obsidian" / "graph.json").write_text('{"USER":"settings"}', encoding="utf-8")
        to_obsidian(G, communities, str(vault), community_labels={0: "Backend"})
        # user content untouched
        assert "MY NOTES" in (vault / "Database.md").read_text()
        assert json.loads((vault / ".obsidian" / "graph.json").read_text()) == {"USER": "settings"}
        # non-colliding graphify note still written
        assert (vault / "Server.md").exists()


def test_to_obsidian_empty_dir_writes_full_vault():
    """No regression: a fresh/empty dir still gets every note + .obsidian/graph.json."""
    G, communities = _two_node_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        n = to_obsidian(G, communities, str(out), community_labels={0: "Backend"})
        assert (out / "Database.md").exists() and (out / "Server.md").exists()
        assert (out / ".obsidian" / "graph.json").exists()
        assert n == 3  # 2 nodes + 1 community note


def test_to_obsidian_rerun_updates_own_notes_but_not_user_files():
    """A re-run overwrites graphify's own prior notes (via the manifest) but leaves a
    user-added note in the same dir alone."""
    G, communities = _two_node_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        to_obsidian(G, communities, str(out), community_labels={0: "Backend"})
        (out / "UserNote.md").write_text("mine\n", encoding="utf-8")
        to_obsidian(G, communities, str(out), community_labels={0: "Backend2"})
        assert (out / "Database.md").exists()  # graphify re-wrote its own
        assert (out / "UserNote.md").read_text().strip() == "mine"  # user's untouched


def _four_node_two_community_graph():
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="Database", community=0, source_file="app/db.py", type="code")
    G.add_node("n2", label="Server", community=0, source_file="app/srv.py", type="code")
    G.add_node("n3", label="Cache", community=1, source_file="infra/cache.py", type="code")
    G.add_node("n4", label="Queue", community=1, source_file="infra/queue.py", type="code")
    G.add_edge("n1", "n2")
    G.add_edge("n3", "n4")
    return G, {0: ["n1", "n2"], 1: ["n3", "n4"]}


def test_to_obsidian_rerun_prunes_removed_nodes():
    """#1896: re-exporting into the same vault must delete graphify's own notes for
    nodes (and communities) that dropped out of the graph, so the vault mirrors the
    current graph rather than old-union-new. User files are never touched."""
    G4, comm4 = _four_node_two_community_graph()
    G2, comm2 = _two_node_graph()
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        to_obsidian(G4, comm4, str(out), community_labels={0: "Backend", 1: "Infra"})
        assert (out / "Cache.md").exists() and (out / "_COMMUNITY_Infra.md").exists()
        (out / "MyOwnNote.md").write_text("mine\n", encoding="utf-8")
        to_obsidian(G2, comm2, str(out), community_labels={0: "Backend"})
        # notes for removed nodes and the stale community overview are pruned
        assert not (out / "Cache.md").exists()
        assert not (out / "Queue.md").exists()
        assert not (out / "_COMMUNITY_Infra.md").exists()
        # surviving graphify notes and the user's own note remain
        assert (out / "Database.md").exists() and (out / "Server.md").exists()
        assert (out / "_COMMUNITY_Backend.md").exists()
        assert (out / "MyOwnNote.md").read_text().strip() == "mine"


def test_to_obsidian_removed_node_returning_is_writable_again(capsys):
    """#1896 follow-on: a node that disappears and later returns must be writable
    again. Before the fix, the manifest was rewritten to only this run's files, so
    the orphaned note was disowned and the returning node's write was skipped as a
    'pre-existing user file' forever."""
    import networkx as nx
    GA, commA = _two_node_graph()
    GB = nx.Graph()
    GB.add_node("n1", label="Database", community=0, source_file="app/db.py", type="code")
    commB = {0: ["n1"]}
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "obsidian"
        to_obsidian(GA, commA, str(out), community_labels={0: "Backend"})
        to_obsidian(GB, commB, str(out), community_labels={0: "Backend"})
        assert not (out / "Server.md").exists()  # pruned while absent
        capsys.readouterr()
        to_obsidian(GA, commA, str(out), community_labels={0: "Backend"})
        # returned node's note exists with current content, written this run
        assert (out / "Server.md").exists()
        assert "# Server" in (out / "Server.md").read_text()
        captured = capsys.readouterr()
        assert "skipped" not in captured.err.lower()


# ── Case-only-distinct labels must not collide on case-insensitive filesystems ──

def _case_collision_graph():
    """Two nodes whose labels differ only by case - on macOS/APFS and Windows/NTFS
    their notes resolve to the same path unless the dedup map folds case."""
    return build_from_json({
        "nodes": [
            {"id": "n1", "label": "References", "file_type": "code", "source_file": "a.py"},
            {"id": "n2", "label": "references", "file_type": "document", "source_file": "b.md"},
        ],
        "edges": [],
    })


def test_to_obsidian_case_only_distinct_labels_dont_overwrite():
    """Both notes must survive as separate files. On a case-insensitive filesystem
    a missing suffix silently overwrites the first note (fewer files than nodes);
    on a case-sensitive one it writes two stems equal under .lower(). Assert both:
    every node note is on disk, and no two stems collide case-insensitively."""
    G = _case_collision_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        to_obsidian(G, communities, tmp)
        notes = [p for p in Path(tmp).rglob("*.md") if not p.name.startswith("_COMMUNITY")]
        assert len(notes) == G.number_of_nodes(), [p.name for p in notes]
        lowered = [p.stem.lower() for p in notes]
        assert len(set(lowered)) == len(lowered), [p.name for p in notes]
        # the suffixed name must be the expected one, not merely distinct
        assert sorted(p.stem for p in notes) == ["References", "references_1"], [p.name for p in notes]


def test_to_obsidian_generated_suffix_doesnt_overwrite_literal():
    """A generated `_1` suffix must not collide with a node whose literal label is
    already that suffixed name. With labels [dup, dup, dup_1] the second `dup`
    becomes `dup_1`, which would clobber the third node unless the candidate is
    re-checked. This collides on case-sensitive filesystems too, so it guards the
    dedup loop independently of case-folding."""
    G = build_from_json({
        "nodes": [
            {"id": "a", "label": "dup", "file_type": "code", "source_file": "a.py"},
            {"id": "b", "label": "dup", "file_type": "code", "source_file": "b.py"},
            {"id": "c", "label": "dup_1", "file_type": "code", "source_file": "c.py"},
        ],
        "edges": [],
    })
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        to_obsidian(G, communities, tmp)
        notes = [p for p in Path(tmp).rglob("*.md") if not p.name.startswith("_COMMUNITY")]
        assert len(notes) == 3, [p.name for p in notes]
        assert len({p.stem.lower() for p in notes}) == 3, [p.name for p in notes]


def test_to_canvas_case_only_distinct_labels_get_distinct_files():
    """Canvas file-node references for case-only-distinct labels must be distinct
    case-insensitively, else both cards point at one overwritten note."""
    G = _case_collision_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        files = [n["file"] for n in data["nodes"] if n.get("type") == "file"]
        lowered = [f.lower() for f in files]
        assert len(set(lowered)) == len(lowered), files


def test_obsidian_canvas_filenames_agree():
    """The CLI calls to_obsidian and to_canvas separately with no shared map, so
    they must independently produce the same node->filename mapping - otherwise a
    canvas card points at a note file that doesn't exist on disk."""
    G = _case_collision_graph()
    communities = cluster(G)
    with tempfile.TemporaryDirectory() as tmp:
        to_obsidian(G, communities, tmp)
        note_stems = {p.stem for p in Path(tmp).rglob("*.md") if not p.name.startswith("_COMMUNITY")}
        out = Path(tmp) / "graph.canvas"
        to_canvas(G, communities, str(out))
        data = json.loads(out.read_text())
        canvas_stems = {Path(n["file"]).stem for n in data["nodes"] if n.get("type") == "file"}
        assert canvas_stems <= note_stems, (sorted(canvas_stems), sorted(note_stems))


def test_to_obsidian_community_notes_case_collision():
    """Two community labels differing only by case must each get their own
    `_COMMUNITY_*.md` overview note. This path had no dedup at all, so even
    same-case duplicate labels previously overwrote silently."""
    G = build_from_json({
        "nodes": [
            {"id": "n1", "label": "alpha", "file_type": "code", "source_file": "a.py"},
            {"id": "n2", "label": "beta", "file_type": "code", "source_file": "b.py"},
        ],
        "edges": [],
    })
    communities = {0: ["n1"], 1: ["n2"]}
    labels = {0: "API", 1: "Api"}
    with tempfile.TemporaryDirectory() as tmp:
        to_obsidian(G, communities, tmp, community_labels=labels)
        comm = [p for p in Path(tmp).rglob("_COMMUNITY_*.md")]
        assert len(comm) == 2, [p.name for p in comm]
        lowered = [p.stem.lower() for p in comm]
        assert len(set(lowered)) == len(lowered), [p.name for p in comm]


# ── Issue #834: backup_if_protected ──────────────────────────────────────────

def test_backup_no_graph_json(tmp_path):
    """No graph.json → no backup."""
    from graphify.export import backup_if_protected
    assert backup_if_protected(tmp_path) is None


def test_backup_no_markers(tmp_path):
    """graph.json present but no sentinel and no curated labels → no backup."""
    from graphify.export import backup_if_protected
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    assert backup_if_protected(tmp_path) is None


def test_backup_semantic_marker(tmp_path):
    """graph.json + .graphify_semantic_marker → backup taken."""
    from graphify.export import backup_if_protected
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / "GRAPH_REPORT.md").write_text("# Report")
    (tmp_path / ".graphify_semantic_marker").write_text('{"output_tokens": 1234}')
    result = backup_if_protected(tmp_path)
    assert result is not None
    assert result.is_dir()
    assert (result / "graph.json").exists()
    assert (result / "GRAPH_REPORT.md").exists()
    assert (result / ".graphify_semantic_marker").exists()


def test_backup_curated_labels(tmp_path):
    """graph.json + non-default label in .graphify_labels.json → backup taken."""
    import json
    from graphify.export import backup_if_protected
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({"0": "Auth Pipeline", "1": "Community 1"}))
    result = backup_if_protected(tmp_path)
    assert result is not None


def test_backup_default_labels_only(tmp_path):
    """All-default labels → no backup (not curated)."""
    import json
    from graphify.export import backup_if_protected
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_labels.json").write_text(json.dumps({"0": "Community 0", "1": "Community 1"}))
    assert backup_if_protected(tmp_path) is None


def test_backup_same_day_no_accumulation(tmp_path):
    """Same content on same day returns existing backup dir without re-copying."""
    from graphify.export import backup_if_protected
    from datetime import date
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    b1 = backup_if_protected(tmp_path)
    b2 = backup_if_protected(tmp_path)
    assert b1 is not None and b2 is not None
    assert b1 == b2  # same dir, no _2 accumulation
    assert b1.name == date.today().isoformat()


def test_backup_same_day_changed_content(tmp_path):
    """Changed graph.json on same day overwrites the existing backup in place."""
    from graphify.export import backup_if_protected
    from datetime import date
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    b1 = backup_if_protected(tmp_path)
    (tmp_path / "graph.json").write_text('{"nodes":[{"id":"x"}],"links":[]}')
    b2 = backup_if_protected(tmp_path)
    assert b1 == b2  # still one folder per day
    assert (b2 / "graph.json").read_text() == '{"nodes":[{"id":"x"}],"links":[]}'


def test_backup_env_disable(tmp_path, monkeypatch):
    """GRAPHIFY_NO_BACKUP=1 disables backup entirely."""
    from graphify.export import backup_if_protected
    monkeypatch.setenv("GRAPHIFY_NO_BACKUP", "1")
    (tmp_path / "graph.json").write_text('{"nodes":[],"links":[]}')
    (tmp_path / ".graphify_semantic_marker").write_text("{}")
    assert backup_if_protected(tmp_path) is None


def _mkG(n):
    import networkx as nx
    G = nx.Graph()
    for i in range(n):
        G.add_node(f"n{i}", label=f"n{i}", community=0)
    return G


def test_to_json_refuses_shrink(tmp_path):
    """#479: refuse to silently overwrite an existing graph with fewer nodes."""
    p = tmp_path / "graph.json"
    json.dump({"nodes": [{"id": f"n{i}"} for i in range(5)]}, p.open("w"))
    assert to_json(_mkG(2), {}, str(p), force=False) is False
    assert to_json(_mkG(2), {}, str(p), force=True) is True  # force overrides


def test_to_json_fails_safe_on_corrupt_existing(tmp_path):
    """A non-empty but unparseable existing graph.json (corrupt or mid-write)
    must NOT be silently overwritten — we can't verify the new graph isn't a
    partial shrink, so fail safe (refuse) unless force is given."""
    p = tmp_path / "graph.json"
    p.write_text("{ this has content but is not valid json")
    assert to_json(_mkG(10), {}, str(p), force=False) is False
    assert to_json(_mkG(10), {}, str(p), force=True) is True


def test_to_json_proceeds_on_empty_existing(tmp_path):
    """An empty/whitespace existing file has no nodes to lose, so it is not a
    shrink risk — the write proceeds."""
    p = tmp_path / "graph.json"
    p.write_text("")
    assert to_json(_mkG(3), {}, str(p), force=False) is True
    data = json.loads(p.read_text())
    assert len(data["nodes"]) == 3


def test_to_html_handles_null_source_file_and_label(tmp_path):
    """#1775: a node with source_file=None or label=None must not crash to_html
    (synthetic/aggregate nodes legitimately carry null source_file; JSON `null`
    survives .get()'s default). Regression guard — fixed via sanitize_label's
    None-coercion + the str(source_file or "") call-site guard."""
    import networkx as nx
    G = nx.Graph()
    G.add_node("n1", label="Foo", source_file=None, community=0)
    G.add_node("n2", label=None, source_file="a.py", community=0)
    G.add_node("n3", label=None, source_file=None, community=0)
    out = tmp_path / "graph.html"
    to_html(G, {0: ["n1", "n2", "n3"]}, str(out))
    assert out.exists() and out.stat().st_size > 0
