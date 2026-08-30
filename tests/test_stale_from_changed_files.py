"""stale_from_changed_files() — surfaces nodes elsewhere in the graph that
reference a node in a changed file, so an incremental update can flag
possibly-stale relationships without re-verifying them (see affected.py
docstring for why this stops short of OpenWiki-style claim verification).
"""
from __future__ import annotations

import networkx as nx

from graphify.affected import stale_from_changed_files, format_stale


def _g():
    g = nx.DiGraph()
    g.add_node("base_retry", label="BaseHandler.retry()", source_file="base.py")
    g.add_node("worker_run", label="Worker.run()", source_file="worker.py")
    g.add_node("worker_helper", label="Worker._helper()", source_file="worker.py")
    g.add_node("unrelated", label="Other.noop()", source_file="other.py")
    g.add_edge("worker_run", "base_retry", relation="calls", source_file="worker.py", source_location="L12")
    g.add_edge("worker_helper", "worker_run", relation="calls", source_file="worker.py", source_location="L20")
    g.add_edge("unrelated", "worker_run", relation="calls", source_file="other.py", source_location="L5")
    return g


def test_changed_file_surfaces_external_caller():
    g = _g()
    by_file = stale_from_changed_files(g, ["base.py"], depth=1)
    assert "base.py" in by_file
    hit_ids = {h.node_id for h in by_file["base.py"]}
    assert hit_ids == {"worker_run"}


def test_depth_controls_how_far_the_walk_goes():
    g = _g()
    depth1 = stale_from_changed_files(g, ["base.py"], depth=1)
    depth2 = stale_from_changed_files(g, ["base.py"], depth=2)
    assert {h.node_id for h in depth1["base.py"]} == {"worker_run"}
    assert {h.node_id for h in depth2["base.py"]} == {"worker_run", "worker_helper", "unrelated"}


def test_unchanged_file_with_no_dependents_is_omitted():
    g = _g()
    by_file = stale_from_changed_files(g, ["other.py"], depth=1)
    assert by_file == {}


def test_changed_file_not_in_graph_is_omitted():
    g = _g()
    by_file = stale_from_changed_files(g, ["never_extracted.py"], depth=1)
    assert by_file == {}


def test_seed_nodes_from_the_changed_file_itself_never_reported_as_hits():
    # worker.py contains both worker_run and worker_helper, and unrelated.py
    # (other.py) calls into worker_run. Changing worker.py must surface the
    # external caller (unrelated) but never report worker_run/worker_helper
    # as hits of their own file's change.
    g = _g()
    by_file = stale_from_changed_files(g, ["worker.py"], depth=2)
    hit_ids = {h.node_id for h in by_file["worker.py"]}
    assert hit_ids == {"unrelated"}


def test_format_stale_reports_no_hits_plainly():
    g = _g()
    out = format_stale(g, ["other.py"], depth=1)
    assert "nothing flagged" in out


def test_format_stale_includes_relation_and_location():
    g = _g()
    out = format_stale(g, ["base.py"], depth=1)
    assert "base.py changed" in out
    assert "Worker.run()" in out
    assert "[calls]" in out
    assert "worker.py:L12" in out
