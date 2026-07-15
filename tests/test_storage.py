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
    _close(db, conn)
