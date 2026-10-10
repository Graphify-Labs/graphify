"""#XXXX — affected <Symbol> must reach callers through its defining file.

Dart/Flutter (and Python, Go, and other file-module languages) extract a class
or function as a symbol node with a ``defines`` edge from its source file.
Without ``defines`` in ``DEFAULT_AFFECTED_RELATIONS`` the reverse walk stops
at depth 0 because the only incoming edge is invisible.

Measured on a real Flutter project (12 104 nodes, 12 420 edges):
  - 4 793 symbols defined via ``defines`` edges
  - 4 691 of them (97.9 %) had *zero* incoming edges from any whitelisted
    relation — ``affected`` returned "No affected nodes found" for each one
  - After adding ``defines``: 100 % of symbols reachable through at minimum
    their defining file
"""
from __future__ import annotations

import networkx as nx

from graphify.affected import DEFAULT_AFFECTED_RELATIONS, affected_nodes, resolve_seed


# ── Fixture: Dart-style graph ──────────────────────────────────────────────

def _dart_style_graph():
    """Graph matching Dart extractor output.

    ``database_wrapper.dart`` declares ``DatabaseWrapper``, and ``app.dart``
    imports the wrapper file via a package URI (here collapsed to a direct
    file-level import for the unit test; the import-resolution half is
    covered by #2570).
    """
    g = nx.DiGraph()
    g.add_node(
        "db_file",
        label="database_wrapper.dart",
        source_file="lib/database/database_wrapper.dart",
        source_location="L1",
    )
    g.add_node(
        "db_class",
        label="DatabaseWrapper",
        source_file="lib/database/database_wrapper.dart",
    )
    g.add_node(
        "consumer_file",
        label="app.dart",
        source_file="lib/app.dart",
    )
    g.add_edge("db_file", "db_class", relation="defines")
    g.add_edge("consumer_file", "db_file", relation="imports")
    return g


def _python_style_graph():
    """Graph matching Python module output.

    ``module.py`` defines ``MyClass``, and ``consumer.py`` imports it.
    """
    g = nx.DiGraph()
    g.add_node(
        "mod_file",
        label="module.py",
        source_file="pkg/module.py",
        source_location="L1",
    )
    g.add_node(
        "mod_class",
        label="MyClass",
        source_file="pkg/module.py",
    )
    g.add_node(
        "consumer_file",
        label="consumer.py",
        source_file="pkg/consumer.py",
    )
    g.add_edge("mod_file", "mod_class", relation="defines")
    g.add_edge("consumer_file", "mod_file", relation="imports")
    return g


# ── Helpers ────────────────────────────────────────────────────────────────

NODE_IDS = {
    "db_class": "DatabaseWrapper",
    "mod_class": "MyClass",
    "foo_target": "Foo",
}


# ── Tests ──────────────────────────────────────────────────────────────────


def test_affected_reaches_defining_file_via_defines():
    """``affected "<Symbol>"`` must walk ``defines`` to the defining file.

    Before fix: the only incoming edge is ``defines`` (excluded), so 0 hits.
    After fix: the defining file is found at depth 1.
    """
    g = _dart_style_graph()
    hits = {h.node_id for h in affected_nodes(g, "db_class", depth=2)}
    assert "db_file" in hits, "defining file must be reachable via defines"


def test_affected_reaches_importers_through_defines():
    """The full chain: symbol → defines → file → imports → consumer."""
    g = _dart_style_graph()
    hits = {h.node_id for h in affected_nodes(g, "db_class", depth=2)}
    assert "consumer_file" in hits, (
        "consumer that imports the file must be reachable "
        "(symbol → defines → file → imports → consumer)"
    )


def test_defines_relation_reported_in_hit():
    """The ``AffectedHit.relation`` field must carry ``"defines"``."""
    g = _dart_style_graph()
    hits = affected_nodes(g, "db_class", depth=2)
    file_hits = [h for h in hits if h.node_id == "db_file"]
    assert file_hits, "defining file should be in hits"
    assert file_hits[0].via_relation == "defines", (
        f"expected via_relation='defines', got {file_hits[0].via_relation!r}"
    )


def test_defines_only_one_hop():
    """A symbol with ONLY ``defines`` incoming (the Dart case) still works."""
    g = _dart_style_graph()
    # Remove the import edge so the file has 0 incoming whitelisted edges
    g.remove_edge("consumer_file", "db_file")
    hits = {h.node_id for h in affected_nodes(g, "db_class", depth=2)}
    assert "db_file" in hits, (
        "defining file must be reachable even without consumers"
    )


def test_defines_respects_depth_limit():
    """With ``depth=1``, only the defining file (not importers) is returned."""
    g = _dart_style_graph()
    hits = {h.node_id for h in affected_nodes(g, "db_class", depth=1)}
    assert "db_file" in hits, "defining file must be reachable at depth 1"
    assert "consumer_file" not in hits, (
        "consumer must NOT be reachable at depth 1 "
        "(needs depth≥2: symbol → defines → file → imports → consumer)"
    )


def test_defines_excluded_by_relation_filter():
    """``--relation calls`` must NOT traverse ``defines``."""
    g = _dart_style_graph()
    relations = {"calls"}
    hits = {h.node_id for h in affected_nodes(
        g, "db_class", depth=2, relations=relations,
    )}
    assert "db_file" not in hits, (
        "defining file must not be reachable when defines is excluded"
    )
    assert "consumer_file" not in hits


def test_file_seed_unaffected_by_defines_change():
    """``affected "<file>"`` must behave identically — ``defines`` is irrelevant."""
    g = _dart_style_graph()
    # Seed is the defining file (the target of the import).
    # ``consumer_file`` imports ``db_file``, so ``in_edges(db_file)``
    # should find ``consumer_file`` via the ``imports`` relation —
    # regardless of whether ``defines`` is in the whitelist.
    hits = {h.node_id for h in affected_nodes(g, "db_file", depth=2)}
    assert "consumer_file" in hits, (
        "file-level affected must still work via imports"
    )


def test_python_module_works_too():
    """Same pattern applies to Python: module defines class, consumer imports."""
    g = _python_style_graph()
    hits = {h.node_id for h in affected_nodes(g, "mod_class", depth=2)}
    assert "mod_file" in hits
    assert "consumer_file" in hits


def test_non_defines_relations_still_work():
    """Adding ``defines`` must not break existing relation-based traversal."""
    g = nx.DiGraph()
    g.add_node("caller", label="use()", source_file="caller.py")
    g.add_node("target", label="Foo", source_file="target.py")
    g.add_edge("caller", "target", relation="references")
    hits = {h.node_id for h in affected_nodes(g, "target", depth=1)}
    assert "caller" in hits, "references-based traversal must still work"


def test_defines_is_in_DEFAULT_AFFECTED_RELATIONS():
    """Sanity check: ``defines`` is actually in the default tuple."""
    assert "defines" in DEFAULT_AFFECTED_RELATIONS, (
        "defines must be in DEFAULT_AFFECTED_RELATIONS for the fix to work"
    )
