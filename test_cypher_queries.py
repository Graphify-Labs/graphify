#!/usr/bin/env python3
"""Test all Cypher queries that will be used in the neug clustered path.

Key neug Cypher limitations discovered:
  - No UNWIND with $param (use CASE WHEN for batch writeback)
  - No IN $param (use inline list [...] instead)
  - No size() function (use MATCH (n)-[e]-() + count(e) for degree)
  - NOT (x IN [...]) works, but x NOT IN [...] might not
  - collect(n)[0] works for getting first element
  - OPTIONAL MATCH works
  - count(DISTINCT ...) works
"""
import sys
import tempfile
from pathlib import Path

from neug import Database

# ── Test graph ──────────────────────────────────────────────────────────────
NODES = [
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
    # Noise nodes for god_nodes filtering
    {"id": "n11", "label": "str", "file_type": "concept", "source_file": ""},
    {"id": "n12", "label": "auth.py", "file_type": "code", "source_file": "src/auth.py"},  # file hub
    {"id": "n13", "label": ".init()", "file_type": "code", "source_file": "src/models.py"},  # method stub
]

EDGES = [
    {"from": "n1", "to": "n2", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n2", "to": "n3", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n4", "to": "n5", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n6", "to": "n7", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n7", "to": "n8", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n8", "to": "n9", "relation": "calls", "confidence": "EXTRACTED"},
    {"from": "n9", "to": "n10", "relation": "uses", "confidence": "EXTRACTED"},
    # Cross-community edge (A->C)
    {"from": "n3", "to": "n6", "relation": "calls", "confidence": "INFERRED"},
    # Cross-file edge (auth.py -> models.py) - surprising connection
    {"from": "n3", "to": "n4", "relation": "uses", "confidence": "AMBIGUOUS"},
    # Edges to noise nodes
    {"from": "n1", "to": "n11", "relation": "uses", "confidence": "EXTRACTED"},
    {"from": "n1", "to": "n12", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n4", "to": "n13", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n12", "to": "n1", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n12", "to": "n2", "relation": "contains", "confidence": "EXTRACTED"},
    {"from": "n12", "to": "n3", "relation": "contains", "confidence": "EXTRACTED"},
]


def create_test_db(db_path):
    db = Database(db_path=str(db_path), mode="w")
    conn = db.connect()

    conn.execute("""CREATE NODE TABLE IF NOT EXISTS node (
        id STRING PRIMARY KEY, label STRING, file_type STRING,
        source_file STRING, source_location STRING,
        community INT64, community_name STRING)""")

    conn.execute("""CREATE REL TABLE IF NOT EXISTS edge (
        FROM node TO node,
        relation STRING, confidence STRING,
        confidence_score DOUBLE, source_file STRING, weight DOUBLE)""")

    for n in NODES:
        conn.execute(
            "CREATE (n:node {id: $id, label: $label, file_type: $ft, "
            "source_file: $sf, source_location: $sl, community: 0, community_name: ''})",
            parameters={"id": n["id"], "label": n["label"], "ft": n["file_type"],
                        "sf": n["source_file"], "sl": ""}
        )

    for e in EDGES:
        conn.execute(
            "MATCH (a:node {id: $from}), (b:node {id: $to}) "
            "CREATE (a)-[:edge {relation: $rel, confidence: $conf, "
            "confidence_score: 1.0, source_file: '', weight: 1.0}]->(b)",
            parameters={"from": e["from"], "to": e["to"],
                        "rel": e["relation"], "conf": e["confidence"]}
        )

    return db, conn


# ── Tests ───────────────────────────────────────────────────────────────────

def test_leiden(conn):
    """Test 1: Leiden community detection."""
    print("\n=== Test 1: Leiden ===")

    node_count = list(conn.execute("MATCH (n:node) RETURN count(*)"))
    print(f"  Nodes: {node_count[0][0]}")
    edge_count = list(conn.execute("MATCH ()-[e:edge]->() RETURN count(*)"))
    print(f"  Edges: {edge_count[0][0]}")

    try:
        conn.execute("CALL drop_projected_graph('g')")
    except RuntimeError:
        pass

    conn.execute("CALL project_graph('g', ['node'], {'[node, edge, node]': ''})")
    # Use LOAD directly (local build), fallback to INSTALL+LOAD
    try:
        conn.execute("LOAD gds;")
    except RuntimeError:
        conn.execute("INSTALL gds;")
        conn.execute("LOAD gds;")

    results = list(conn.execute(
        "CALL leiden('g', {concurrency: 1}) "
        "YIELD node, community "
        "RETURN node.id, community ORDER BY node.id"
    ))

    communities = {}
    for nid, cid in results:
        communities.setdefault(cid, []).append(nid)

    print(f"  Communities found: {len(communities)}")
    for cid, members in sorted(communities.items()):
        print(f"    Community {cid}: {members}")

    assert len(communities) >= 2, f"Expected >= 2 communities, got {len(communities)}"
    assert sum(len(v) for v in communities.values()) == len(NODES)

    print("  PASSED")
    return communities


def test_batch_writeback_case_when(conn, communities):
    """Test 2: Batch community writeback using CASE WHEN (neug pattern)."""
    print("\n=== Test 2: Batch writeback (CASE WHEN) ===")

    # Build comm_map: node_id -> community_id
    comm_map = {}
    for cid, members in communities.items():
        for nid in members:
            comm_map[nid] = cid

    # CASE WHEN approach (from test_gds.py:944-954)
    when_clauses = " ".join(
        f"WHEN n.id = '{nid}' THEN {cid}" for nid, cid in comm_map.items()
    )
    conn.execute(
        f"MATCH (n:node) "
        f"SET n.community = CASE {when_clauses} ELSE n.community END;"
    )

    # Verify
    rows = list(conn.execute(
        "MATCH (n:node) WHERE n.community IS NOT NULL "
        "RETURN n.community AS cid, count(*) AS cnt ORDER BY cid"
    ))
    print(f"  Communities in db:")
    for cid, cnt in rows:
        print(f"    cid={cid}: {cnt} nodes")

    assert sum(r[1] for r in rows) == len(NODES), "Not all nodes have community set"
    print("  PASSED")
    return communities


def test_cohesion(conn, communities):
    """Test 3: Cohesion score per community."""
    print("\n=== Test 3: Cohesion ===")

    cohesion = {}
    for cid, nodes in communities.items():
        n = len(nodes)
        if n <= 1:
            cohesion[cid] = 1.0
            print(f"  Community {cid}: n={n}, cohesion=1.0 (single node)")
            continue

        # Count internal edges (directed, but stored one direction)
        rows = list(conn.execute(
            "MATCH (a:node)-[:edge]->(b:node) "
            "WHERE a.community = $cid AND b.community = $cid "
            "RETURN count(*) AS internal_edges",
            parameters={"cid": int(cid)}
        ))
        actual = rows[0][0] if rows else 0
        possible = n * (n - 1) / 2
        score = actual / possible if possible > 0 else 0.0
        cohesion[cid] = score
        print(f"  Community {cid}: n={n}, internal_edges={actual}, possible={possible}, cohesion={score:.4f}")

    for cid, score in cohesion.items():
        assert 0.0 <= score <= 1.0, f"Cohesion {score} out of range for community {cid}"

    print("  PASSED")
    return cohesion


def test_label_by_hub(conn, communities):
    """Test 4: Label communities by highest-degree member."""
    print("\n=== Test 4: label_communities_by_hub ===")

    # Approach: use OPTIONAL MATCH + count(e) for degree, then collect(n)[0] per community
    # Test if this single-query approach works
    try:
        rows = list(conn.execute(
            "MATCH (n:node) "
            "WHERE n.community IS NOT NULL "
            "OPTIONAL MATCH (n)-[e:edge]-() "
            "WITH n, n.community AS cid, count(e) AS degree "
            "ORDER BY cid, degree DESC, n.id ASC "
            "WITH cid, collect(n)[0] AS hub "
            "RETURN cid, hub.label, hub.id"
        ))
        print("  Single-query (OPTIONAL MATCH + collect): WORKS")
        labels = {}
        for cid, label, nid in rows:
            name = label or nid
            if name and name.endswith("()"):
                name = name[:-2]
            labels[cid] = name or f"Community {cid}"
    except Exception as e:
        print(f"  Single-query FAILED: {e}")
        # Fallback: two-step approach
        print("  Trying two-step approach...")

        # Step 1: get degrees per node
        deg_rows = list(conn.execute(
            "MATCH (n:node)-[e:edge]-() "
            "WITH n, count(e) AS degree "
            "RETURN n.id, n.community, n.label, degree "
            "ORDER BY n.community, degree DESC, n.id"
        ))

        # Step 2: pick first per community in Python
        labels = {}
        seen = set()
        for nid, cid, label, degree in deg_rows:
            if cid is not None and cid not in seen:
                seen.add(cid)
                name = label or nid
                if name and name.endswith("()"):
                    name = name[:-2]
                labels[cid] = name

        # Handle nodes with no edges
        for cid, nodes in communities.items():
            if cid not in labels:
                labels[cid] = f"Community {cid}"

    print(f"  Labels:")
    for cid, label in sorted(labels.items()):
        print(f"    Community {cid}: '{label}'")

    print("  PASSED")
    return labels


def test_god_nodes(conn):
    """Test 5: God nodes (degree + noise filtering)."""
    print("\n=== Test 5: find_god_nodes ===")

    # Build inline noise list (neug doesn't support IN $param)
    noise_labels = [
        "str", "int", "float", "bool", "bytes", "object",
        "True", "False", "Mock", "Path", "Any", "Optional",
        "List", "Dict", "Set", "Tuple", "os", "sys", "re", "json",
    ]
    noise_list = "[" + ", ".join(f"'{l}'" for l in noise_labels) + "]"

    # Debug: try simpler queries to find what works
    # Step 1: basic degree query
    try:
        debug_rows = list(conn.execute(
            "MATCH (n:node)-[e:edge]-() "
            "WITH n, count(e) AS degree "
            "RETURN n.id, n.label, degree "
            "ORDER BY degree DESC "
            "LIMIT 10"
        ))
        print(f"  Debug (no filter): {len(debug_rows)} rows")
        for r in debug_rows[:3]:
            print(f"    {r[1]}: degree={r[2]}")
    except Exception as e:
        print(f"  Debug (no filter) FAILED: {e}")
        debug_rows = []

    # Step 2: with NOT IN filter
    if debug_rows:
        try:
            debug_rows2 = list(conn.execute(
                f"MATCH (n:node)-[e:edge]-() "
                f"WITH n, count(e) AS degree "
                f"WHERE degree > 0 "
                f"  AND NOT (n.label IN {noise_list}) "
                f"RETURN n.id, n.label, degree "
                f"ORDER BY degree DESC "
                f"LIMIT 10"
            ))
            print(f"  Debug (NOT IN filter): {len(debug_rows2)} rows")
        except Exception as e:
            print(f"  Debug (NOT IN filter) FAILED: {e}")

    # Step 3: correct query — only use conditions confirmed to work in Cypher.
    # Debug showed: NOT IN works, but IS NOT NULL / <> '' / STARTS WITH in WHERE after WITH may not.
    # Move remaining filters to Python.
    # Test if RETURN n.file_type, n.source_file works
    try:
        rows = list(conn.execute(
            f"MATCH (n:node)-[e:edge]-() "
            f"WITH n, count(e) AS degree "
            f"WHERE degree > 0 "
            f"  AND NOT (n.label IN {noise_list}) "
            f"RETURN n.id, n.label, n.file_type, n.source_file, degree "
            f"ORDER BY degree DESC, n.id ASC "
            f"LIMIT 50"
        ))
        print(f"  Cypher query (simplified WHERE): {len(rows)} candidates")
    except Exception as e:
        print(f"  Cypher query FAILED: {e}")
        # Fallback: minimal query, filter everything in Python
        rows = list(conn.execute(
            f"MATCH (n:node)-[e:edge]-() "
            f"WITH n, count(e) AS degree "
            f"WHERE degree > 0 "
            f"RETURN n.id, n.label, n.file_type, n.source_file, degree "
            f"ORDER BY degree DESC "
            f"LIMIT 50"
        ))
        print(f"  Cypher query (no WHERE filter): {len(rows)} candidates")
    print(f"  Cypher query returned {len(rows)} candidates")

    # Python filtering (all conditions that might not work in Cypher)
    from pathlib import Path as _Path
    noise_set = set(noise_labels)
    json_noise = frozenset({"start", "end", "name", "id", "type", "value", "key"})

    gods = []
    for nid, label, ft, source_file, degree in rows:
        # Empty label
        if not label:
            continue
        # File hub: label == Path(source_file).name
        if source_file and label == _Path(source_file).name:
            continue
        # Method stub with degree <= 1
        if label.endswith("()") and degree <= 1:
            continue
        # Concept node: empty source_file or no extension
        if not source_file or "." not in _Path(source_file).name:
            continue
        # JSON key node
        if source_file.lower().endswith(".json") and label.strip().lower() in json_noise:
            continue
        # Builtin noise (extra check, already filtered in Cypher)
        if label in noise_set:
            continue

        gods.append({"id": nid, "label": label, "degree": degree})
        if len(gods) >= 10:
            break

    print(f"  God nodes ({len(gods)}):")
    for g in gods:
        print(f"    {g['label']}: degree={g['degree']} (id={g['id']})")

    # Verify filtering
    god_ids = {g["id"] for g in gods}
    assert len(gods) > 0, "Should have at least 1 god node after filtering"
    assert "n11" not in god_ids, "n11 (str) should be filtered as noise"
    assert "n12" not in god_ids, "n12 (auth.py) should be filtered as file hub"
    assert "n13" not in god_ids, "n13 (.init()) should be filtered as method stub"

    print("  PASSED")
    return gods


def test_surprising_connections(conn, communities):
    """Test 6: Surprising connections."""
    print("\n=== Test 6: find_surprising_connections ===")

    # Step 1: Determine multi-source
    source_count = list(conn.execute(
        "MATCH (n:node) WHERE n.source_file <> '' "
        "RETURN count(DISTINCT n.source_file) AS cnt"
    ))
    is_multi_source = source_count[0][0] > 1
    print(f"  Unique source files: {source_count[0][0]} -> multi_source={is_multi_source}")

    # Step 2: Pre-compute degrees
    deg_rows = list(conn.execute(
        "MATCH (n:node)-[e:edge]-() "
        "WITH n, count(e) AS degree "
        "RETURN n.id, degree"
    ))
    degrees = {r[0]: r[1] for r in deg_rows}
    print(f"  Degrees computed for {len(degrees)} nodes")

    # Step 3: Get candidate edges
    structural_list = "['imports', 'imports_from', 'contains', 'method']"

    if is_multi_source:
        print("  Using cross-file query (multi-source)")
        rows = list(conn.execute(
            f"MATCH (a:node)-[e:edge]->(b:node) "
            f"WHERE a.source_file <> '' AND b.source_file <> '' "
            f"  AND a.source_file <> b.source_file "
            f"  AND NOT (e.relation IN {structural_list}) "
            f"RETURN a.id, a.label, a.source_file, a.community, "
            f"       b.id, b.label, b.source_file, b.community, "
            f"       e.relation, e.confidence"
        ))
    else:
        print("  Using cross-community query (single-source)")
        rows = list(conn.execute(
            f"MATCH (a:node)-[e:edge]->(b:node) "
            f"WHERE a.community IS NOT NULL AND b.community IS NOT NULL "
            f"  AND a.community <> b.community "
            f"  AND NOT (e.relation IN {structural_list}) "
            f"RETURN a.id, a.label, a.source_file, a.community, "
            f"       b.id, b.label, b.source_file, b.community, "
            f"       e.relation, e.confidence"
        ))

    print(f"  Candidate edges: {len(rows)}")
    for r in rows:
        print(f"    {r[1]} ({r[2]}) -> {r[5]} ({r[6]}), rel={r[8]}, conf={r[9]}")

    print("  PASSED")
    return rows


def test_community_name_update(conn, labels):
    """Test 7: Batch community_name update (per-community SET)."""
    print("\n=== Test 7: community_name update ===")

    for cid, name in labels.items():
        # neug doesn't support $param in SET; use WHERE + inline values
        # Escape single quotes in name
        safe_name = name.replace("'", "\\'")
        conn.execute(
            f"MATCH (n:node) WHERE n.community = {int(cid)} "
            f"SET n.community_name = '{safe_name}'"
        )
        print(f"  Community {cid} -> '{name}': OK")

    # Verify
    rows = list(conn.execute(
        "MATCH (n:node) WHERE n.community IS NOT NULL "
        "RETURN n.community AS cid, n.community_name AS name, count(*) AS cnt "
        "ORDER BY cid"
    ))
    print(f"  Verification:")
    for cid, name, cnt in rows:
        print(f"    cid={cid}, name='{name}', nodes={cnt}")

    print("  PASSED")


def main():
    tmpdir = tempfile.mkdtemp(prefix="neug_cypher_test_")
    db_path = Path(tmpdir) / "test_db"
    print(f"Test DB: {db_path}")

    db, conn = create_test_db(db_path)

    try:
        communities = test_leiden(conn)
        communities = test_batch_writeback_case_when(conn, communities)
        cohesion = test_cohesion(conn, communities)
        labels = test_label_by_hub(conn, communities)
        gods = test_god_nodes(conn)
        surprises = test_surprising_connections(conn, communities)
        test_community_name_update(conn, labels)

        print("\n" + "=" * 60)
        print("ALL TESTS PASSED")
        print("=" * 60)

    except AssertionError as e:
        print(f"\nASSERTION FAILED: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
    finally:
        conn.close()
        db.close()


if __name__ == "__main__":
    main()
