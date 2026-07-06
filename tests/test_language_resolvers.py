"""Tests for the language resolver registry (graphify.resolver_registry).

The registry formalizes the previously hand-wired, suffix-gated cross-file
resolution passes. These tests pin its contract so future languages can be
registered with confidence: gating by suffix, in-order execution, in-place
mutation, and fault isolation (a failing pass logs and is skipped, never
aborting the build or blocking later passes).
"""

from __future__ import annotations

from pathlib import Path

from graphify.resolver_registry import (
    LanguageResolver,
    registered_resolvers,
    run_language_resolvers,
)


def _make_resolver(name: str, suffix: str, log: list[str]) -> LanguageResolver:
    def _resolve(per_file, all_nodes, all_edges):
        log.append(name)
    return LanguageResolver(name, frozenset({suffix}), _resolve)


def test_default_registry_contains_swift_then_python() -> None:
    # Importing extract registers its resolvers into the shared registry. Order
    # matters: it preserves the prior inlined wiring (Swift before Python).
    import graphify.extract  # noqa: F401  (registers resolvers on import)

    names = [r.name for r in registered_resolvers()]
    assert "swift_member_calls" in names
    assert "python_member_calls" in names
    assert names.index("swift_member_calls") < names.index("python_member_calls")


def test_resolver_runs_only_when_suffix_present() -> None:
    log: list[str] = []
    resolvers = [_make_resolver("ruby", ".rb", log), _make_resolver("go", ".go", log)]
    run_language_resolvers([Path("a.rb")], [], [], [], resolvers=resolvers)
    assert log == ["ruby"]  # go skipped: no .go file present


def test_resolvers_run_in_given_order() -> None:
    log: list[str] = []
    resolvers = [_make_resolver("first", ".rb", log), _make_resolver("second", ".rb", log)]
    run_language_resolvers([Path("a.rb")], [], [], [], resolvers=resolvers)
    assert log == ["first", "second"]


def test_failing_resolver_is_isolated() -> None:
    log: list[str] = []

    def _boom(per_file, all_nodes, all_edges):
        raise RuntimeError("resolver blew up")

    resolvers = [
        LanguageResolver("boom", frozenset({".rb"}), _boom),
        _make_resolver("after", ".rb", log),
    ]
    # Must not raise, and the later resolver still runs.
    run_language_resolvers([Path("a.rb")], [], [], [], resolvers=resolvers)
    assert log == ["after"]


def test_resolver_mutates_edges_in_place() -> None:
    def _add_edge(per_file, all_nodes, all_edges):
        all_edges.append({"source": "x", "target": "y", "relation": "calls"})

    resolvers = [LanguageResolver("adder", frozenset({".rb"}), _add_edge)]
    edges: list[dict] = []
    run_language_resolvers([Path("a.rb")], [], [], edges, resolvers=resolvers)
    assert edges == [{"source": "x", "target": "y", "relation": "calls"}]
