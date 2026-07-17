from graphify.analyze import god_nodes, surprising_connections
from graphify.cluster import cluster, score_all
from graphify.report import generate
from tests.native_helpers import graph_from_payload, triangle


def make_inputs():
    G = graph_from_payload(
        [
            {"id": "extract", "label": "extract", "file_type": "code", "source_file": "extract.py"},
            {"id": "build", "label": "build", "file_type": "code", "source_file": "build.py"},
            {"id": "report", "label": "report", "file_type": "code", "source_file": "report.py"},
        ],
        [
            {"source": "extract", "target": "build", "relation": "imports", "confidence": "EXTRACTED"},
            {"source": "build", "target": "report", "relation": "calls", "confidence": "EXTRACTED"},
        ],
    )
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    return (
        G,
        communities,
        cohesion,
        labels,
        god_nodes(G),
        surprising_connections(G, communities),
        {"total_files": 3, "total_words": 1000, "needs_graph": True, "warning": None},
        {"input": 10, "output": 2},
    )


def test_report_is_generated_from_native_snapshot(tmp_path):
    graph = triangle(tmp_path).graph
    communities = cluster(graph)
    cohesion = score_all(graph, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    report = generate(
        graph,
        communities,
        cohesion,
        labels,
        god_nodes(graph),
        surprising_connections(graph, communities),
        {"total_files": 3, "total_words": 10_000, "warning": None},
        {"input": 1_200, "output": 100},
        "./project",
    )
    for heading in (
        "# Graph Report", "## Corpus Check", "## God Nodes",
        "## Surprising Connections", "## Communities", "## Ambiguous Edges",
    ):
        assert heading in report
    assert "1,200" in report

def test_report_shows_raw_cohesion_scores():
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project", min_community_size=1)
    assert "Cohesion:" in report
    assert "✓" not in report
    assert "⚠" not in report


# --- work-memory lessons section ----------------------------------------------

def test_report_work_memory_section_present_with_overlay_and_dead_ends():
    """When a work-memory overlay (preferred sources) and query-scoped dead-ends
    are supplied, the report grows a `## Work-memory lessons` section listing the
    preferred sources and, separately, the dead-ends as question -> nodes."""
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    learning = {
        "overlay": {
            "auth_login": {"status": "preferred", "uses": 3, "score": 2.4,
                           "label": "login()", "stale": False},
            "redis": {"status": "tentative", "uses": 1, "score": 0.5,
                      "label": "RedisClient", "stale": False},
        },
        "dead_ends": [
            {"question": "does it use websockets?", "nodes": ["WSServer"], "date": "2026-05-01"},
        ],
    }
    report = generate(G, communities, cohesion, labels, gods, surprises, detection,
                      tokens, "./project", learning=learning)
    assert "## Work-memory lessons" in report
    assert "**Preferred sources**" in report
    assert "`login()`" in report
    # Tentative is not listed in the report's preferred block.
    assert "RedisClient" not in report
    # Dead-ends are query-scoped: question -> nodes, NOT a node-level status.
    assert "**Known dead ends**" in report
    assert "does it use websockets?" in report
    assert "`WSServer`" in report


def test_report_work_memory_section_absent_without_overlay():
    """No learning input => no section; report identical to pre-feature."""
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    before = generate(G, communities, cohesion, labels, gods, surprises, detection,
                      tokens, "./project")
    assert "## Work-memory lessons" not in before
    # Explicit empty learning also omits the section.
    empty = generate(G, communities, cohesion, labels, gods, surprises, detection,
                     tokens, "./project", learning={"overlay": {}, "dead_ends": []})
    assert "## Work-memory lessons" not in empty
    assert before == empty


def test_import_cycles_section_present_for_code_corpus():
    # #1657: the fixture is a code corpus, so the Import Cycles section shows.
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## Import Cycles" in report


def test_import_cycles_section_absent_for_documents_only_corpus():
    # #1657: a documents-only corpus has no imports; the section is pure noise
    # ("None detected") and must be suppressed.
    extraction = {
        "nodes": [
            {"id": "d1", "label": "intro.md", "file_type": "document"},
            {"id": "d2", "label": "guide.md", "file_type": "document"},
        ],
        "edges": [{"source": "d1", "target": "d2", "relation": "references"}],
        "input_tokens": 0, "output_tokens": 0,
    }
    G = graph_from_payload(extraction["nodes"], extraction["edges"])
    communities = cluster(G)
    cohesion = score_all(G, communities)
    labels = {cid: f"Community {cid}" for cid in communities}
    gods = god_nodes(G)
    surprises = surprising_connections(G)
    detection = {"total_files": 2, "total_words": 100, "needs_graph": True, "warning": None}
    tokens = {"input": 0, "output": 0}
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project")
    assert "## Import Cycles" not in report


def test_report_hubs_are_plain_text_by_default():
    # #1712: without --obsidian the _COMMUNITY_*.md notes don't exist, so wikilinks
    # would dangle (and pollute an Obsidian vault's graph view). Default to plain text.
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    labels = {cid: f"Widget {cid}" for cid in communities}
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project", min_community_size=1)
    assert "## Community Hubs (Navigation)" in report
    assert "[[_COMMUNITY_" not in report, "must not emit dangling Obsidian wikilinks by default (#1712)"
    assert any(f"- Widget {cid}" in report for cid in communities)


def test_report_hubs_use_wikilinks_when_obsidian():
    # The opt-in path keeps the vault-navigable wikilink form.
    G, communities, cohesion, labels, gods, surprises, detection, tokens = make_inputs()
    labels = {cid: f"Widget {cid}" for cid in communities}
    report = generate(G, communities, cohesion, labels, gods, surprises, detection, tokens, "./project", min_community_size=1, obsidian=True)
    assert "[[_COMMUNITY_" in report
