import networkx as nx

from graphify.report import generate


def _build_mixed_graph():
    G = nx.Graph()
    # Community 0: 3 real code nodes, 1 file node, 1 rationale node, 1 concept node
    G.add_node("r1", label="Parser", file_type="code", source_file="src/parser.py")
    G.add_node("r2", label="Lexer", file_type="code", source_file="src/lexer.py")
    G.add_node("r3", label="Token", file_type="code", source_file="src/token.py")
    G.add_node("f1", label="parser.py", file_type="code", source_file="src/parser.py")
    G.add_node("rat1", label="why_parse", file_type="rationale", source_file="src/parser.py")
    G.add_node("con1", label="Parsing", file_type="document", source_file="concept_only")

    # Community 1: thin (only 2 real nodes)
    G.add_node("r4", label="Helper", file_type="code", source_file="src/helper.py")
    G.add_node("r5", label="Util", file_type="code", source_file="src/util.py")

    # Community 2: non-real only (file + rationale + concept -> 0 real nodes)
    G.add_node("f2", label="util.py", file_type="code", source_file="src/util.py")
    G.add_node("rat2", label="why_util", file_type="rationale", source_file="src/util.py")
    G.add_node("con2", label="Utilities", file_type="document", source_file="")

    # Isolated real node in semantic layer
    G.add_node("iso1", label="OrphanDoc", file_type="document", source_file="docs/orphan.md")

    # Edges: EXTRACTED, INFERRED, AMBIGUOUS, and imports
    G.add_edge("r1", "r2", confidence="EXTRACTED", relation="calls", source_file="src/parser.py")
    G.add_edge("r2", "r3", confidence="INFERRED", confidence_score=0.80, relation="uses", source_file="src/lexer.py")
    G.add_edge("r1", "r3", confidence="AMBIGUOUS", relation="unknown", source_file="src/parser.py")
    G.add_edge("r4", "r5", confidence="EXTRACTED", relation="imports", source_file="src/helper.py")

    communities = {
        0: ["r1", "r2", "r3", "f1", "rat1", "con1"],
        1: ["r4", "r5"],
        2: ["f2", "rat2", "con2"],
        3: ["iso1"],
    }
    cohesion = {0: 0.75, 1: 0.50, 2: 0.0, 3: 0.0}
    labels = {0: "Core", 1: "Helpers", 2: "Noise", 3: "Docs"}
    detection = {"total_files": 6, "total_words": 1200}
    tokens = {"input": 100, "output": 50}
    return G, communities, cohesion, labels, detection, tokens


def test_single_pass_report_mixed_communities_and_edges():
    G, communities, cohesion, labels, detection, tokens = _build_mixed_graph()
    out = generate(
        G,
        communities,
        cohesion,
        labels,
        god_node_list=[{"label": "Parser", "degree": 2}],
        surprise_list=[],
        detection_result=detection,
        token_cost=tokens,
        root="/tmp/myproj",
        min_community_size=3,
    )

    # Summary: 12 nodes, 4 edges, 4 communities (1 shown, 3 thin omitted)
    assert "- 12 nodes · 4 edges · 4 communities (1 shown, 3 thin omitted)" in out
    assert "- Extraction: 50% EXTRACTED · 25% INFERRED · 25% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.8)" in out

    # Community Hubs: only non-empty real communities (0, 1, 3), not all-noise community 2
    assert "- Core" in out
    assert "- Helpers" in out
    assert "- Docs" in out
    assert "- Noise" not in out

    # Communities section: only community 0 shown with exactly 3 real nodes (excluding f1, rat1, con1)
    assert "## Communities (4 total, 3 thin omitted)" in out
    assert '### Community 0 - "Core"' in out
    assert "Nodes (3): Parser, Lexer, Token" in out
    assert '### Community 1 - "Helpers"' not in out
    assert '### Community 2 - "Noise"' not in out

    # Ambiguous edges, import cycles, and knowledge gaps
    assert "## Ambiguous Edges - Review These" in out
    assert "`Parser` → `Token`  [AMBIGUOUS]" in out
    assert "## Import Cycles" in out
    assert "**3 isolated node(s):**" in out
    assert "`OrphanDoc`" in out
    assert "possible missing edges or undocumented components" in out
    assert "**3 thin communities (<3 nodes) omitted from report**" in out
    assert "**High ambiguity: 25% of edges are AMBIGUOUS.**" in out
