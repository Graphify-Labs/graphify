"""End-to-end tests for the incremental community update workflow.

Validates the complete 3-phase workflow from neug-incremental-community-workflow.md:

  Phase 1: Baseline   - full-data leiden, writeback, record old sizes
  Phase 2: Incremental - add/delete vertices, freeze-assign leiden
  Phase 3: Detection   - 6 community change types via Cypher queries

Test graph (12 baseline vertices, 10 edges, 5 communities):
  A: 1-2-3   (edges 1->2, 2->3)   -> growth+shrink (delete 3, add 14->1)
  B: 4-5     (edge  4->5)         -> growth         (add 15->4)
  C: 6-7-8   (edges 6->7, 7->8)   -> stable         (no change)
  D: 9-10    (edge  9->10)        -> dissolved      (delete 9,10)
  E: 11-12-13(edges 11->12,12->13)-> shrink         (delete 13)

  New community F: vertices 16,17 (edge 16->17) -> new

Expected change summary:
  A: old=3, surviving=2, new=1 -> growth+shrink
  B: old=2, surviving=2, new=1 -> growth
  C: old=3, surviving=3, new=0 -> stable
  D: old=2, surviving=0        -> dissolved
  E: old=3, surviving=2, new=0 -> shrink
  F: old=0, new=2              -> new
"""

import sys
from pathlib import Path
from contextlib import contextmanager

import pytest

_tools_dir = str(Path(__file__).resolve().parent.parent)
if _tools_dir not in sys.path:
    sys.path.insert(0, _tools_dir)

from neug import Database

# ── Graph constants ────────────────────────────────────────────────────────

BASELINE_VERTICES = list(range(1, 14))  # 1..13
BASELINE_EDGES = [
    (1, 2), (2, 3),       # Community A
    (4, 5),               # Community B
    (6, 7), (7, 8),       # Community C
    (9, 10),              # Community D
    (11, 12), (12, 13),   # Community E
]

DELETE_VERTICES = [3, 9, 10, 13]  # 3→A shrink, 9,10→D dissolved, 13→E shrink
NEW_VERTICES = [14, 15, 16, 17]
NEW_EDGES = [
    (14, 1),   # 14 joins A (growth)
    (15, 4),   # 15 joins B (growth)
    (16, 17),  # 16-17 form new community F
]

LEIDEN_FREEZE = (
    "CALL leiden('g', "
    "{concurrency: 1, initial_community_property: 'leiden_comm'}) "
    "YIELD node, community, previous_community"
)


@contextmanager
def workflow_connection(tmp_path):
    """Set up graph through all 3 phases, yield (conn, baseline, old_sizes).

    Phase 1: create graph, run baseline leiden, writeback communities
    Phase 2: apply incremental changes, re-project, run freeze-assign leiden
    """
    db_dir = tmp_path / "incremental_workflow_db"
    db = Database(db_path=str(db_dir), mode="w")
    conn = db.connect()
    try:
        # ── Phase 1: Baseline ──────────────────────────────────────────
        conn.execute("CREATE NODE TABLE n(id INT64 PRIMARY KEY);")
        conn.execute("CREATE REL TABLE e(FROM n TO n);")

        for vid in BASELINE_VERTICES:
            conn.execute(f"CREATE (:n {{id: {vid}}});")

        for a, b in BASELINE_EDGES:
            conn.execute(
                f"MATCH (a:n), (b:n) WHERE a.id = {a} AND b.id = {b} "
                f"CREATE (a)-[:e]->(b);"
            )

        conn.execute("CALL project_graph('g', ['n'], {'[n, e, n]': ''});")
        conn.execute("INSTALL gds;")
        conn.execute("LOAD gds;")
        conn.execute("ALTER TABLE n ADD leiden_comm INT64 DEFAULT -1;")

        # Run baseline leiden
        r1 = list(conn.execute(
            "CALL leiden('g', {concurrency: 1}) "
            "YIELD node, community "
            "RETURN node.id, community ORDER BY node.id;"
        ))
        baseline = {row[0]: row[1] for row in r1}

        # Writeback communities
        when_clauses = " ".join(
            f"WHEN n.id = {nid} THEN {comm}"
            for nid, comm in baseline.items()
        )
        conn.execute(
            f"MATCH (n:n) "
            f"SET n.leiden_comm = CASE {when_clauses} ELSE -1 END;"
        )

        # Record old community sizes (Step A)
        old_sizes = {}
        for comm in set(baseline.values()):
            old_sizes[comm] = sum(1 for c in baseline.values() if c == comm)

        # ── Phase 2: Incremental ───────────────────────────────────────
        # Delete vertices
        for vid in DELETE_VERTICES:
            conn.execute(f"MATCH (n:n) WHERE n.id = {vid} DETACH DELETE n;")

        # Add new vertices
        for vid in NEW_VERTICES:
            conn.execute(f"CREATE (:n {{id: {vid}}});")

        # Add new edges
        for a, b in NEW_EDGES:
            conn.execute(
                f"MATCH (a:n), (b:n) WHERE a.id = {a} AND b.id = {b} "
                f"CREATE (a)-[:e]->(b);"
            )

        # Re-project
        conn.execute("CALL drop_projected_graph('g');")
        conn.execute("CALL project_graph('g', ['n'], {'[n, e, n]': ''});")

        yield conn, baseline, old_sizes
    finally:
        conn.close()
        db.close()


# ── Phase 1 tests ──────────────────────────────────────────────────────────


def test_phase1_baseline_communities(tmp_path):
    """Phase 1: baseline leiden should produce 5 communities with correct sizes."""
    db_dir = tmp_path / "phase1_db"
    db = Database(db_path=str(db_dir), mode="w")
    conn = db.connect()
    try:
        conn.execute("CREATE NODE TABLE n(id INT64 PRIMARY KEY);")
        conn.execute("CREATE REL TABLE e(FROM n TO n);")
        for vid in BASELINE_VERTICES:
            conn.execute(f"CREATE (:n {{id: {vid}}});")
        for a, b in BASELINE_EDGES:
            conn.execute(
                f"MATCH (a:n), (b:n) WHERE a.id = {a} AND b.id = {b} "
                f"CREATE (a)-[:e]->(b);"
            )
        conn.execute("CALL project_graph('g', ['n'], {'[n, e, n]': ''});")
        conn.execute("LOAD gds;")

        rows = list(conn.execute(
            "CALL leiden('g', {concurrency: 1}) "
            "YIELD node, community "
            "RETURN node.id, community ORDER BY node.id;"
        ))

        # Should have 12 vertices
        assert len(rows) == 13, f"Expected 13 vertices, got {len(rows)}"

        # Should have 5 communities
        communities = set(r[1] for r in rows)
        assert len(communities) == 5, (
            f"Expected 5 communities, got {len(communities)}: {communities}"
        )

        # Community sizes should be: {3, 3, 3, 2, 2} (A=3, B=2, C=3, D=2, E=3)
        sizes = sorted(
            sum(1 for r in rows if r[1] == c) for c in communities
        )
        assert sizes == [2, 2, 3, 3, 3], f"Expected sizes [2,2,3,3,3], got {sizes}"
    finally:
        conn.close()
        db.close()


# ── Phase 2 tests ──────────────────────────────────────────────────────────


def test_phase2_freeze_assign_previous_community(tmp_path):
    """Phase 2: freeze-assign leiden should yield correct previous_community."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "RETURN node.id, community, previous_community ORDER BY node.id;"
        ))

        # Should have 13 vertices: 9 surviving old + 4 new
        assert len(rows) == 13, f"Expected 13 vertices, got {len(rows)}"

        # New vertices (14,15,16,17) should have previous_community = None
        new_vids = {14, 15, 16, 17}
        for vid, comm, prev in rows:
            if vid in new_vids:
                assert prev is None, (
                    f"Vertex {vid} (new) should have prev=None, got {prev}"
                )
            else:
                assert prev is not None, (
                    f"Vertex {vid} (old) should have prev!=None, got None"
                )
                assert prev == baseline[vid], (
                    f"Vertex {vid}: prev={prev} should equal baseline={baseline[vid]}"
                )


# ── Phase 3: Recipe A — All-in-one classification ─────────────────────────


def test_recipe_a_classification(tmp_path):
    """Recipe A: classify communities into new / stable / growth."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH community, count(*) AS total, "
            "     count(previous_community) AS old_members "
            "WITH community, total, old_members, "
            "     total - old_members AS new_members "
            "RETURN community, total, old_members, new_members, "
            "       CASE "
            "         WHEN old_members = 0 THEN 'new' "
            "         WHEN new_members = 0 THEN 'stable' "
            "         ELSE 'growth' "
            "       END AS change_type "
            "ORDER BY change_type, community;"
        ))

        results = {}
        for comm, total, old_m, new_m, ctype in rows:
            results[comm] = {
                "total": total, "old": old_m, "new": new_m, "type": ctype,
            }

        types = {r["type"] for r in results.values()}
        assert "growth" in types, f"Expected growth, got: {types}"
        assert "stable" in types, f"Expected stable, got: {types}"
        assert "new" in types, f"Expected new, got: {types}"

        # Total vertices = 13 (9 surviving old + 4 new)
        total_v = sum(r["total"] for r in results.values())
        assert total_v == 13, f"Expected 13 vertices, got {total_v}"


# ── Phase 3: Recipe B — Growth communities ────────────────────────────────


def test_recipe_b_growth(tmp_path):
    """Recipe B: communities that gained new vertices (growth and growth+shrink)."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH community, count(*) AS total, "
            "     count(previous_community) AS old_members "
            "WITH community, total, old_members, "
            "     total - old_members AS new_members "
            "WHERE old_members > 0 AND new_members > 0 "
            "RETURN community, old_members, new_members, total "
            "ORDER BY new_members DESC;"
        ))

        # Should have 2 growth communities:
        #   A: old=2, new=1 (growth+shrink, but Recipe B detects it as growth)
        #   B: old=2, new=1 (pure growth)
        assert len(rows) == 2, f"Expected 2 growth communities, got {len(rows)}: {rows}"

        for comm, old_m, new_m, total in rows:
            assert old_m > 0 and new_m > 0
            assert total == old_m + new_m

        # Both should have old=2, new=1
        for comm, old_m, new_m, _ in rows:
            assert old_m == 2, f"Comm {comm}: expected old=2, got {old_m}"
            assert new_m == 1, f"Comm {comm}: expected new=1, got {new_m}"


# ── Phase 3: Recipe C — New communities ───────────────────────────────────


def test_recipe_c_new_communities(tmp_path):
    """Recipe C: communities composed entirely of new vertices."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH community, count(*) AS total, "
            "     count(previous_community) AS old_members "
            "WHERE old_members = 0 "
            "RETURN community, total AS members "
            "ORDER BY members DESC;"
        ))

        # Should have 1 new community with 2 members (vertices 16, 17)
        assert len(rows) >= 1, "Should have at least one new community"

        new_with_2 = [r for r in rows if r[1] == 2]
        assert len(new_with_2) >= 1, (
            f"Expected new community with 2 members, got: {rows}"
        )


# ── Phase 3: Recipe D — Shrink & dissolved detection ──────────────────────


def test_recipe_d_shrink_dissolved(tmp_path):
    """Recipe D: detect shrink and dissolved via two-step comparison."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        # Step B: surviving sizes (WHERE before aggregation!)
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH node, previous_community "
            "WHERE previous_community IS NOT NULL "
            "RETURN previous_community, count(*) AS surviving_size "
            "ORDER BY previous_community;"
        ))
        surviving = {row[0]: row[1] for row in rows}

        dissolved = []
        shrunk = []
        stable_comms = []

        for old_comm, old_size in old_sizes.items():
            surv = surviving.get(old_comm, 0)
            if surv == 0:
                dissolved.append((old_comm, old_size))
            elif surv < old_size:
                shrunk.append((old_comm, old_size, surv))
            else:
                stable_comms.append((old_comm, old_size))

        # D: dissolved (old_size=2, surviving=0)
        assert len(dissolved) == 1, f"Expected 1 dissolved, got {dissolved}"
        assert dissolved[0][1] == 2, (
            f"Dissolved old_size should be 2 (vertices 9,10), got {dissolved[0][1]}"
        )

        # E: shrink (old_size=3, surviving=2) — vertex 13 deleted
        # A: shrink (old_size=3, surviving=2) — vertex 3 deleted
        # But A also has new members, so it's growth+shrink.
        # Recipe D only detects surviving < old_size, doesn't distinguish growth+shrink.
        assert len(shrunk) == 2, f"Expected 2 shrunk, got {shrunk}"

        # Both shrunk communities should have old=3, surviving=2
        for comm, old_size, surv in shrunk:
            assert old_size == 3, f"Comm {comm}: expected old=3, got {old_size}"
            assert surv == 2, f"Comm {comm}: expected surviving=2, got {surv}"

        # C: stable (old_size=3, surviving=3)
        # B: surviving=old_size=2, but B has new members → not truly stable
        # Recipe D counts it as stable here; Recipe F confirms no new members.
        # So we have 2 communities with surviving=old_size: B (old=2) and C (old=3)
        assert len(stable_comms) == 2, f"Expected 2 stable candidates, got {stable_comms}"


# ── Phase 3: Recipe E — New vertex listing ────────────────────────────────


def test_recipe_e_new_vertices(tmp_path):
    """Recipe E: list vertices with previous_community IS NULL."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH node, community, previous_community "
            "WHERE previous_community IS NULL "
            "RETURN node.id, community "
            "ORDER BY community, node.id;"
        ))

        new_vids = {row[0] for row in rows}
        assert new_vids == {14, 15, 16, 17}, (
            f"Expected {{14,15,16,17}}, got {new_vids}"
        )


# ── Phase 3: Recipe F — Stable communities ────────────────────────────────


def test_recipe_f_stable_communities(tmp_path):
    """Recipe F: communities with no new members."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        rows = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH community, count(*) AS total, "
            "     count(previous_community) AS old_members "
            "WITH community, total, old_members, "
            "     total - old_members AS new_members "
            "WHERE new_members = 0 "
            "RETURN community, total AS members "
            "ORDER BY community;"
        ))

        # Communities with no new members:
        #   C (stable): 3 old members, 0 new
        #   E (shrink): 2 old members, 0 new
        # Note: Recipe F alone can't distinguish stable from shrink.
        # Must combine with Recipe D (surviving = old_size) for true stable.
        assert len(rows) >= 2, (
            f"Expected at least 2 communities with no new members, got: {rows}"
        )

        # Community C (stable) should have 3 members
        stable_with_3 = [r for r in rows if r[1] == 3]
        assert len(stable_with_3) >= 1, (
            f"Expected a community with 3 members (C stable), got: {rows}"
        )

        # Community E (shrink) should have 2 members
        shrink_with_2 = [r for r in rows if r[1] == 2]
        assert len(shrink_with_2) >= 1, (
            f"Expected a community with 2 members (E shrink), got: {rows}"
        )


# ── Full workflow: all 6 change types ─────────────────────────────────────


def test_full_workflow_all_six_changes(tmp_path):
    """End-to-end: verify all 6 community change types are correctly detected."""
    with workflow_connection(tmp_path) as (conn, baseline, old_sizes):
        # ── Recipe A: classification ──
        rows_a = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH community, count(*) AS total, "
            "     count(previous_community) AS old_members "
            "WITH community, total, old_members, "
            "     total - old_members AS new_members "
            "RETURN community, total, old_members, new_members, "
            "       CASE "
            "         WHEN old_members = 0 THEN 'new' "
            "         WHEN new_members = 0 THEN 'stable' "
            "         ELSE 'growth' "
            "       END AS change_type "
            "ORDER BY change_type, community;"
        ))
        classification = {}
        for comm, total, old_m, new_m, ctype in rows_a:
            classification[comm] = {
                "total": total, "old": old_m, "new": new_m, "type": ctype,
            }

        # ── Recipe D: surviving sizes ──
        rows_d = list(conn.execute(
            f"{LEIDEN_FREEZE} "
            "WITH node, previous_community "
            "WHERE previous_community IS NOT NULL "
            "RETURN previous_community, count(*) AS surviving_size "
            "ORDER BY previous_community;"
        ))
        surviving = {row[0]: row[1] for row in rows_d}

        # ── Combine Recipe A + Recipe D for full classification ──
        changes = {}

        # Classify old communities
        for old_comm, old_size in old_sizes.items():
            surv = surviving.get(old_comm, 0)
            if surv == 0:
                changes[old_comm] = "dissolved"
            elif surv < old_size:
                # Check if this community has new members
                # Find the current community that contains old members with this prev_comm
                has_new = False
                for comm, info in classification.items():
                    if info["old"] > 0:
                        # Check if any old member in this community has prev = old_comm
                        # We can infer: if the community has new_members > 0 and
                        # its old_members include vertices from old_comm
                        # Simpler: just check if any community with old_members > 0
                        # also has new_members > 0 and surviving for old_comm < old_size
                        pass
                # For growth+shrink: the community has both old and new members
                # and surviving < old_size
                # For pure shrink: the community has only old members (new=0)
                # and surviving < old_size
                # We need to find which current community corresponds to old_comm
                # Since freeze-assign keeps old community IDs, the current community
                # ID should equal old_comm for surviving vertices
                if old_comm in classification:
                    info = classification[old_comm]
                    if info["new"] > 0:
                        changes[old_comm] = "growth+shrink"
                    else:
                        changes[old_comm] = "shrink"
                else:
                    changes[old_comm] = "shrink"
            elif surv == old_size:
                if old_comm in classification:
                    info = classification[old_comm]
                    if info["new"] > 0:
                        changes[old_comm] = "growth"
                    else:
                        changes[old_comm] = "stable"
                else:
                    changes[old_comm] = "stable"

        # Classify new communities
        for comm, info in classification.items():
            if info["old"] == 0:
                changes[comm] = "new"

        # ── Verify all 6 change types are present ──
        change_types = set(changes.values())
        expected_types = {"stable", "growth", "shrink", "dissolved", "new", "growth+shrink"}
        assert change_types == expected_types, (
            f"Expected all 6 change types {expected_types}, got {change_types}.\n"
            f"Details: {changes}"
        )

        # ── Verify specific change details ──
        type_counts = {}
        for ct in changes.values():
            type_counts[ct] = type_counts.get(ct, 0) + 1

        assert type_counts.get("growth+shrink", 0) == 1, (
            f"Expected 1 growth+shrink, got {type_counts}"
        )
        assert type_counts.get("growth", 0) == 1, (
            f"Expected 1 growth, got {type_counts}"
        )
        assert type_counts.get("stable", 0) == 1, (
            f"Expected 1 stable, got {type_counts}"
        )
        assert type_counts.get("dissolved", 0) == 1, (
            f"Expected 1 dissolved, got {type_counts}"
        )
        assert type_counts.get("shrink", 0) == 1, (
            f"Expected 1 shrink, got {type_counts}"
        )
        assert type_counts.get("new", 0) == 1, (
            f"Expected 1 new, got {type_counts}"
        )
