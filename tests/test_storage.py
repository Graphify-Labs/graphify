"""Tests for graphify.storage — NeuG adapter layer."""
import json
import shutil
import tempfile
from pathlib import Path

import pytest

try:
    import neug
    _has_neug = True
except ImportError:
    _has_neug = False

pytestmark = pytest.mark.skipif(not _has_neug, reason="neug not installed")

FIXTURES = Path(__file__).parent / "fixtures"
EXTRACTION_JSON = FIXTURES / "extraction.json"


def _load_extraction() -> dict:
    return json.loads(EXTRACTION_JSON.read_text())


@pytest.fixture()
def tmp_db(tmp_path):
    db_path = str(tmp_path / "test.db")
    yield db_path


def _init(db_path):
    from graphify.storage import init_db, ensure_schema
    db, conn = init_db(db_path)
    ensure_schema(conn)
    return db, conn


def _close(db, conn):
    from graphify.storage import close_db
    close_db(db, conn)


def _query(conn, cypher):
    from graphify.storage import execute_cypher
    return execute_cypher(conn, cypher)


# --- init_db ---

def test_init_db_creates_tables(tmp_db):
    db, conn = _init(tmp_db)
    rows = _query(conn, "MATCH (n:node) RETURN count(n)")
    assert rows == [[0]]
    _close(db, conn)


# --- ingest_extraction: CREATE mode ---

def test_ingest_extraction_create_mode(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    rows = _query(conn, "MATCH (n:node {file_type: 'code'}) RETURN n.id ORDER BY n.id")
    ids = sorted([r[0] for r in rows])
    assert "n_attention" in ids
    assert "n_transformer" in ids
    assert "n_layernorm" in ids
    edge_rows = _query(conn, "MATCH (a:node)-[e:edge]->(b:node) WHERE e.relation = 'contains' RETURN count(e)")
    assert edge_rows[0][0] == 2
    _close(db, conn)


# --- ingest_extraction: MERGE mode ---

def test_ingest_extraction_merge_mode(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    ext["nodes"][0]["label"] = "TransformerV2"
    ingest_extraction(conn, ext, incremental=True)
    rows = _query(conn, "MATCH (n:node {file_type: 'code'}) WHERE n.id = 'n_transformer' RETURN n.label")
    assert rows[0][0] == "TransformerV2"
    count = _query(conn, "MATCH (n:node {file_type: 'code'}) RETURN count(n)")
    assert count[0][0] == 3
    _close(db, conn)


# --- file_type routing ---

def test_ingest_extraction_file_type_routing(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    doc_rows = _query(conn, "MATCH (n:node {file_type: 'document'}) RETURN n.id")
    assert len(doc_rows) == 1
    assert doc_rows[0][0] == "n_concept_attn"
    _close(db, conn)


# --- prune_sources ---

def test_ingest_extraction_prune(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    before = _query(conn, "MATCH (n:node {file_type: 'code'}) RETURN count(n)")[0][0]
    assert before == 3
    ingest_extraction(conn, ext, incremental=True, prune_sources=["model.py"])
    after_prune = _query(conn, "MATCH (n:node {file_type: 'code'}) RETURN count(n)")[0][0]
    assert after_prune == 3
    _close(db, conn)


# --- communities ---

def test_ingest_communities(tmp_db):
    from graphify.storage import ingest_extraction, ingest_communities
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    communities = {0: ["n_transformer", "n_attention"], 1: ["n_layernorm"]}
    ingest_communities(conn, communities)
    rows = _query(conn, "MATCH (n:node) WHERE n.id = 'n_transformer' RETURN n.community")
    assert rows[0][0] == 0
    rows = _query(conn, "MATCH (n:node) WHERE n.id = 'n_layernorm' RETURN n.community")
    assert rows[0][0] == 1
    _close(db, conn)


# --- execute_cypher ---

def test_execute_cypher(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    rows = _query(conn, "MATCH (n:node {file_type: 'code'}) RETURN n.label ORDER BY n.id")
    labels = [r[0] for r in rows]
    assert "MultiHeadAttention" in labels
    assert "Transformer" in labels
    _close(db, conn)


def test_execute_cypher_bad_query(tmp_db):
    db, conn = _init(tmp_db)
    with pytest.raises(RuntimeError):
        _query(conn, "THIS IS NOT VALID CYPHER")
    _close(db, conn)


# --- roundtrip consistency ---

def test_roundtrip_node_count(tmp_db):
    from graphify.storage import ingest_extraction
    db, conn = _init(tmp_db)
    ext = _load_extraction()
    ingest_extraction(conn, ext, incremental=False)
    rows = _query(conn, "MATCH (n:node) RETURN count(n)")
    assert rows[0][0] == len(ext["nodes"])
    _close(db, conn)


# --- community detection & analysis (neug GDS Leiden + Cypher) ---

_TEST_NODES = [
    {"id": "n1", "label": "AuthService", "file_type": "code", "source_file": "src/auth.py"},
    {"id": "n2", "label": "login", "file_type": "code", "source_file": "src/auth.py"},
    {"id": "n3", "label": "token", "file_type": "code", "source_file": "src/auth.py"},
    {"id": "n4", "label": "UserModel", "file_type": "code", "source_file": "src/models.py"},
    {"id": "n5", "label": "save", "file_type": "code", "source_file": "src/models.py"},
    {"id": "n6", "label": "ApiClient", "file_type": "code", "source_file": "src/client.py"},
    {"id": "n7", "label": "request", "file_type": "code", "source_file": "src/client.py"},
    {"id": "n8", "label": "response", "file_type": "code", "source_file": "src/client.py"},
    {"id": "n9", "label": "parse", "file_type": "code", "source_file": "src/client.py"},
    {"id": "n10", "label": "fetch", "file_type": "code", "source_file": "src/client.py"},
    # Noise nodes
    {"id": "n11", "label": "str", "file_type": "concept", "source_file": ""},
    {"id": "n12", "label": "auth.py", "file_type": "code", "source_file": "src/auth.py"},
    {"id": "n13", "label": ".init()", "file_type": "code", "source_file": "src/models.py"},
]

_TEST_EDGES = [
    {"from": "n1", "to": "n2", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n2", "to": "n3", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n4", "to": "n5", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n6", "to": "n7", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n7", "to": "n8", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n8", "to": "n9", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n9", "to": "n10", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n3", "to": "n6", "relation": "calls", "confidence": "INFERRED"},
    {"from": "n3", "to": "n4", "relation": "uses", "confidence": "AMBIGUOUS"},
    {"from": "n1", "to": "n11", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n1", "to": "n12", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n4", "to": "n13", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n12", "to": "n1", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n12", "to": "n2", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n12", "to": "n3", "relation": "contains", "confidence": "EXTRACTED"},
]


def _populate_test_graph(conn):
    """Insert test nodes and edges into the db."""
    for n in _TEST_NODES:
        conn.execute(
            "CREATE (n:node {id: $id, label: $label, file_type: $ft, "
            "source_file: $sf, source_location: $sl, community: 0, community_name: ''})",
            parameters={"id": n["id"], "label": n["label"], "ft": n["file_type"],
                        "sf": n["source_file"], "sl": ""}
        )
    for e in _TEST_EDGES:
        conn.execute(
            "MATCH (a:node {id: $from}), (b:node {id: $to}) "
            "CREATE (a)-[:edge {relation: $rel, confidence: $conf, "
            "confidence_score: 1.0, source_file: '', weight: 1.0}]->(b)",
            parameters={"from": e["from"], "to": e["to"],
                        "rel": e["relation"], "conf": e["confidence"]}
        )


def test_run_leiden(tmp_db):
    from graphify.storage import run_leiden
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)
    communities = run_leiden(conn)
    assert len(communities) >= 2, f"Expected >= 2 communities, got {len(communities)}"
    total = sum(len(v) for v in communities.values())
    assert total == len(_TEST_NODES), f"Expected {len(_TEST_NODES)} nodes, got {total}"
    _close(db, conn)


def test_compute_cohesion(tmp_db):
    from graphify.storage import run_leiden, ingest_communities, compute_cohesion
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)
    communities = run_leiden(conn)
    ingest_communities(conn, communities)
    cohesion = compute_cohesion(conn, communities)
    for cid, score in cohesion.items():
        assert 0.0 <= score <= 1.0, f"Cohesion {score} out of range for community {cid}"
    _close(db, conn)


def test_find_god_nodes(tmp_db):
    from graphify.storage import run_leiden, ingest_communities, find_god_nodes
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)
    communities = run_leiden(conn)
    ingest_communities(conn, communities)
    gods = find_god_nodes(conn, top_n=10)
    assert len(gods) > 0, "Should have at least 1 god node"
    god_ids = {g["id"] for g in gods}
    assert "n11" not in god_ids, "n11 (str) should be filtered as noise"
    assert "n12" not in god_ids, "n12 (auth.py) should be filtered as file hub"
    assert "n13" not in god_ids, "n13 (.init()) should be filtered as method stub"
    _close(db, conn)


def test_find_surprising_connections(tmp_db):
    from graphify.storage import run_leiden, ingest_communities, find_surprising_connections
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)
    communities = run_leiden(conn)
    ingest_communities(conn, communities)
    surprises = find_surprising_connections(conn, communities, top_n=5)
    # Multi-source graph (3 source files) -> should find cross-file edges
    assert len(surprises) > 0, "Should find at least 1 surprising connection"
    for s in surprises:
        assert "source" in s and "target" in s
        assert "source_files" in s and len(s["source_files"]) == 2
        assert "confidence" in s and "relation" in s
        assert "why" in s
    _close(db, conn)


def test_label_communities_by_hub(tmp_db):
    from graphify.storage import run_leiden, ingest_communities, label_communities_by_hub
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)
    communities = run_leiden(conn)
    ingest_communities(conn, communities)
    labels = label_communities_by_hub(conn, communities)
    assert len(labels) == len(communities)
    for cid, name in labels.items():
        assert name, f"Community {cid} has empty label"
    _close(db, conn)


def test_ingest_communities_batch_writeback(tmp_db):
    from graphify.storage import ingest_communities, execute_cypher
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)
    # Include all 13 nodes (noise nodes get their own community)
    communities = {0: ["n1", "n2", "n3"], 1: ["n4", "n5"], 2: ["n6", "n7", "n8", "n9", "n10"], 3: ["n11", "n12", "n13"]}
    labels = {0: "AuthModule", 1: "Models", 2: "ApiClient", 3: "Noise"}
    ingest_communities(conn, communities, community_labels=labels)
    rows = execute_cypher(conn, "MATCH (n:node) WHERE n.community IS NOT NULL "
                                "RETURN n.community AS cid, n.community_name AS name, "
                                "count(*) AS cnt ORDER BY cid")
    assert sum(r[2] for r in rows) == 13
    for cid, name, cnt in rows:
        assert name, f"Community {cid} has empty name"
    _close(db, conn)


# --- incremental delta analysis (freeze-assign leiden) ---


def test_run_leiden_freeze_assign(tmp_db):
    """Freeze-assign: old nodes frozen, new nodes get previous_community=None."""
    from graphify.storage import run_leiden, ingest_communities, run_leiden_freeze_assign
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    # Phase 1: full leiden
    communities = run_leiden(conn)
    ingest_communities(conn, communities)

    # Build old_communities {node_id: cid}
    old_communities = {}
    for cid, node_ids in communities.items():
        for nid in node_ids:
            old_communities[nid] = cid

    # Phase 2: add a new node + edge (simulating incremental extract)
    conn.execute(
        "CREATE (n:node {id: 'n14', label: 'NewFunc', file_type: 'code', "
        "source_file: 'src/new.py', source_location: '', community: 0, community_name: ''})"
    )
    conn.execute(
        "MATCH (a:node {id: 'n14'}), (b:node {id: 'n1'}) "
        "CREATE (a)-[:edge {relation: 'calls', confidence: 'EXTRACTED', "
        "confidence_score: 1.0, source_file: 'src/new.py', weight: 1.0}]->(b)"
    )

    # Run freeze-assign leiden
    results = run_leiden_freeze_assign(conn, old_communities)

    # All old nodes should have previous_community == their old community
    results_map = {nid: (new_cid, prev_cid) for nid, new_cid, prev_cid in results}
    for nid, old_cid in old_communities.items():
        assert nid in results_map, f"Old node {nid} missing from results"
        new_cid, prev_cid = results_map[nid]
        assert prev_cid == old_cid, (
            f"Node {nid}: prev_cid={prev_cid} should equal old_cid={old_cid}"
        )
        # In freeze-assign mode, old nodes keep their community
        assert new_cid == old_cid, (
            f"Node {nid}: new_cid={new_cid} should equal old_cid={old_cid} (frozen)"
        )

    # New node n14 should have previous_community = None
    assert "n14" in results_map, "New node n14 missing from results"
    new_cid, prev_cid = results_map["n14"]
    assert prev_cid is None, (
        f"New node n14 should have prev=None, got {prev_cid}"
    )
    _close(db, conn)


def test_run_leiden_resolution(tmp_db):
    """run_leiden accepts a resolution parameter and passes it to neug GDS."""
    from graphify.storage import run_leiden
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    # Default resolution (1.0)
    communities_default = run_leiden(conn)
    # High resolution (5.0) — favours smaller communities
    communities_high = run_leiden(conn, resolution=5.0)
    # Low resolution (0.1) — favours larger communities
    communities_low = run_leiden(conn, resolution=0.1)

    # All should produce valid community dicts
    assert isinstance(communities_default, dict)
    assert isinstance(communities_high, dict)
    assert isinstance(communities_low, dict)

    # All nodes should be assigned in each case
    all_nodes = {f"n{i}" for i in range(1, 14)}
    for label, comms in [("default", communities_default),
                          ("high", communities_high),
                          ("low", communities_low)]:
        assigned = set()
        for node_ids in comms.values():
            assigned.update(node_ids)
        assert assigned == all_nodes, f"{label}: missing nodes {all_nodes - assigned}"

    _close(db, conn)


def test_run_leiden_freeze_assign_resolution(tmp_db):
    """run_leiden_freeze_assign accepts resolution and passes it to neug GDS."""
    from graphify.storage import run_leiden, ingest_communities, run_leiden_freeze_assign
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    # Phase 1: full leiden with resolution=0.5
    communities = run_leiden(conn, resolution=0.5)
    ingest_communities(conn, communities)

    old_communities = {}
    for cid, node_ids in communities.items():
        for nid in node_ids:
            old_communities[nid] = cid

    # Phase 2: add new node
    conn.execute(
        "CREATE (n:node {id: 'n14', label: 'NewFunc', file_type: 'code', "
        "source_file: 'src/new.py', source_location: '', community: 0, community_name: ''})"
    )
    conn.execute(
        "MATCH (a:node {id: 'n14'}), (b:node {id: 'n1'}) "
        "CREATE (a)-[:edge {relation: 'calls', confidence: 'EXTRACTED', "
        "confidence_score: 1.0, source_file: 'src/new.py', weight: 1.0}]->(b)"
    )

    # Run freeze-assign with resolution=0.5 (should match the full leiden resolution)
    results = run_leiden_freeze_assign(conn, old_communities, resolution=0.5)

    # Old nodes should be frozen
    results_map = {nid: (new_cid, prev_cid) for nid, new_cid, prev_cid in results}
    for nid, old_cid in old_communities.items():
        assert nid in results_map
        new_cid, prev_cid = results_map[nid]
        assert new_cid == old_cid, f"Frozen node {nid} moved: {old_cid} -> {new_cid}"

    # New node should have prev=None
    assert results_map["n14"][1] is None

    _close(db, conn)


def test_analyze_community_changes():
    """Classify communities into 4 types: stable, changed, new, dissolved."""
    from graphify.storage import analyze_community_changes

    # old_communities: {node_id: community_id}
    old_communities = {
        # Community 0: nodes A, B, C
        "A": 0, "B": 0, "C": 0,
        # Community 1: nodes D, E
        "D": 1, "E": 1,
        # Community 2: nodes F, G, H (will be dissolved — all deleted)
        "F": 2, "G": 2, "H": 2,
    }

    # leiden_results: [(node_id, new_community, previous_community), ...]
    # Community 0: stable (A, B, C still there, no new members)
    # Community 1: changed (D, E still there + new node Z joined)
    # Community 2: dissolved (F, G, H all deleted, not in results)
    # Community 3: new (new nodes X, Y form a new community)
    leiden_results = [
        ("A", 0, 0),  # old, same community
        ("B", 0, 0),
        ("C", 0, 0),
        ("D", 1, 1),  # old, same community
        ("E", 1, 1),
        ("Z", 1, None),  # new node joined community 1
        ("X", 3, None),  # new community
        ("Y", 3, None),
    ]

    changes = analyze_community_changes(leiden_results, old_communities)

    # Summary
    s = changes["summary"]
    assert s["total_before"] == 3, f"Expected 3 before, got {s['total_before']}"
    assert s["total_after"] == 3, f"Expected 3 after, got {s['total_after']}"
    assert s["stable"] == 1, f"Expected 1 stable, got {s['stable']}"
    assert s["changed"] == 1, f"Expected 1 changed, got {s['changed']}"
    assert s["new"] == 1, f"Expected 1 new, got {s['new']}"
    assert s["dissolved"] == 1, f"Expected 1 dissolved, got {s['dissolved']}"

    # Stable: community 0
    assert "0" in changes["stable_communities"]

    # Changed: community 1 (grow_members=[Z], shrink_members=[])
    assert "1" in changes["changed_communities"]
    ch1 = changes["changed_communities"]["1"]
    assert ch1["grow_members"] == ["Z"], f"Expected grow=['Z'], got {ch1['grow_members']}"
    assert ch1["shrink_members"] == [], f"Expected shrink=[], got {ch1['shrink_members']}"

    # New: community 3 (members=[X, Y])
    assert "3" in changes["new_communities"]
    assert sorted(changes["new_communities"]["3"]["members"]) == ["X", "Y"]

    # Dissolved: community 2
    assert len(changes["dissolved_communities"]) == 1
    assert changes["dissolved_communities"][0]["cid"] == 2
    assert changes["dissolved_communities"][0]["old_size"] == 3


def test_delta_analyze(tmp_db):
    """End-to-end: full leiden → incremental update → delta_analyze."""
    from graphify.storage import (
        run_leiden, ingest_communities, delta_analyze,
    )
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    # Phase 1: full leiden
    communities = run_leiden(conn)
    ingest_communities(conn, communities)

    # Build prev_analysis dict (simulates .graphify_analysis.json)
    prev_analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {},
        "gods": [],
        "surprises": [],
        "tokens": {"input": 0, "output": 0},
    }

    # Phase 2: add new node + edge
    conn.execute(
        "CREATE (n:node {id: 'n14', label: 'NewFunc', file_type: 'code', "
        "source_file: 'src/new.py', source_location: '', community: 0, community_name: ''})"
    )
    conn.execute(
        "MATCH (a:node {id: 'n14'}), (b:node {id: 'n1'}) "
        "CREATE (a)-[:edge {relation: 'calls', confidence: 'EXTRACTED', "
        "confidence_score: 1.0, source_file: 'src/new.py', weight: 1.0}]->(b)"
    )

    # Run delta_analyze
    delta_path = Path(tmp_db).parent / "delta_analysis.json"

    class FakeStages:
        def mark(self, stage):
            pass

    delta = delta_analyze(
        conn,
        prev_analysis=prev_analysis,
        delta_analysis_path=delta_path,
        stages=FakeStages(),
        merged={"input_tokens": 0, "output_tokens": 0},
    )

    # Verify output structure
    assert "changed_communities" in delta
    assert "new_communities" in delta
    assert "stable_communities" in delta
    assert "dissolved_communities" in delta
    assert "summary" in delta
    assert "gods" in delta
    assert "surprises" in delta
    assert "tokens" in delta

    # Summary should be consistent
    s = delta["summary"]
    assert s["total_before"] == len(communities), (
        f"total_before={s['total_before']} should equal {len(communities)}"
    )
    # total_after = stable + changed + new
    assert s["total_after"] == s["stable"] + s["changed"] + s["new"], (
        f"total_after={s['total_after']} != stable+changed+new={s['stable']+s['changed']+s['new']}"
    )

    # Verify file was written
    assert delta_path.exists(), f"Delta file not written at {delta_path}"
    written = json.loads(delta_path.read_text())
    assert written["summary"] == delta["summary"]

    # Verify DB community property NOT modified (preview mode)
    # n14 should still have community=0 (the default from creation)
    rows = list(conn.execute("MATCH (n:node {id: 'n14'}) RETURN n.community"))
    assert rows[0][0] == 0, f"n14 community should be 0 (preview), got {rows[0][0]}"

    _close(db, conn)


# --- file-level clustering ---


def test_aggregate_file_edges(tmp_db):
    """_aggregate_file_edges should exclude concept nodes and intra-file edges."""
    from graphify.storage import _aggregate_file_edges
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    import tempfile
    csv_path = Path(tmp_db).parent / "file_edges.csv"
    all_files = _aggregate_file_edges(conn, csv_path)

    # 3 source files in test data
    assert all_files == {"src/auth.py", "src/models.py", "src/client.py"}

    # Read CSV and verify edges
    import csv as _csv
    with open(csv_path) as f:
        rows = list(_csv.DictReader(f))

    # Cross-file edges: n3(auth)→n6(client), n3(auth)→n4(models)
    # Intra-file and concept edges should be excluded
    edge_pairs = {(r["from_file"], r["to_file"], float(r["weight"])) for r in rows}
    assert ("src/auth.py", "src/client.py", 1.0) in edge_pairs
    assert ("src/auth.py", "src/models.py", 1.0) in edge_pairs

    # No intra-file edges
    for r in rows:
        assert r["from_file"] != r["to_file"], "Intra-file edge should be excluded"

    # No concept nodes (source_file='')
    for r in rows:
        assert r["from_file"] != "", "Concept node should be excluded"
        assert r["to_file"] != "", "Concept node should be excluded"

    _close(db, conn)


def test_cluster_on_files(tmp_db):
    """File-level clustering: community members are file paths, not symbol IDs."""
    from graphify.storage import cluster_on_files
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    communities = cluster_on_files(conn)

    # Community members should be file paths (3 source files in test data)
    all_members = set()
    for members in communities.values():
        all_members.update(members)
    assert all_members == {"src/auth.py", "src/models.py", "src/client.py"}, (
        f"Expected 3 file paths, got {all_members}"
    )

    # No symbol node IDs should appear
    for n in _TEST_NODES:
        assert n["id"] not in all_members, f"Symbol ID {n['id']} should not be in communities"

    _close(db, conn)


def test_cluster_on_files_resolution(tmp_db):
    """cluster_on_files accepts resolution parameter."""
    from graphify.storage import cluster_on_files
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    # Just verify it doesn't crash with different resolution
    communities = cluster_on_files(conn, resolution=0.5)
    assert len(communities) >= 1
    _close(db, conn)


def test_delta_analyze_file_level(tmp_db):
    """File-level delta analysis: freeze-assign on file-level graph."""
    from graphify.storage import (
        cluster_on_files, delta_analyze,
    )
    db, conn = _init(tmp_db)
    _populate_test_graph(conn)

    # Phase 1: full file-level clustering
    communities = cluster_on_files(conn)
    # communities = {cid: [file_paths]}

    # Build prev_analysis (simulates .graphify_analysis.json)
    prev_analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {},
        "gods": [],
        "surprises": [],
        "tokens": {"input": 0, "output": 0},
    }

    # Phase 2: add a new file with a node + edge to existing graph
    conn.execute(
        "CREATE (n:node {id: 'n14', label: 'NewFunc', file_type: 'code', "
        "source_file: 'src/new.py', source_location: '', community: 0, community_name: ''})"
    )
    conn.execute(
        "MATCH (a:node {id: 'n14'}), (b:node {id: 'n1'}) "
        "CREATE (a)-[:edge {relation: 'calls', confidence: 'EXTRACTED', "
        "confidence_score: 1.0, source_file: 'src/new.py', weight: 1.0}]->(b)"
    )

    # Run file-level delta_analyze
    delta_path = Path(tmp_db).parent / "delta_file_level.json"

    class FakeStages:
        def mark(self, stage):
            pass

    delta = delta_analyze(
        conn,
        prev_analysis=prev_analysis,
        delta_analysis_path=delta_path,
        stages=FakeStages(),
        merged={"input_tokens": 0, "output_tokens": 0},
        file_level=True,
    )

    # Verify output structure
    assert "changed_communities" in delta
    assert "new_communities" in delta
    assert "stable_communities" in delta
    assert "dissolved_communities" in delta
    assert "summary" in delta

    # Summary should be consistent
    s = delta["summary"]
    assert s["total_after"] == s["stable"] + s["changed"] + s["new"], (
        f"total_after={s['total_after']} != stable+changed+new={s['stable']+s['changed']+s['new']}"
    )

    # Verify file was written
    assert delta_path.exists()
    written = json.loads(delta_path.read_text())
    assert written["summary"] == delta["summary"]

    _close(db, conn)
