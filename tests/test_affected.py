"""Unit tests for graphify.affected.resolve_seed.

Covers Unicode normalization (NFC) so accented and CJK labels resolve
regardless of whether the query comes in NFC (Python source, most input
methods) or NFD (macOS filenames, some IMEs).
"""
from __future__ import annotations

import unicodedata

import networkx as nx

from graphify.affected import resolve_seed


def _graph_with(label: str) -> nx.Graph:
    """Build a one-node graph whose label is stored exactly as given."""
    g = nx.DiGraph()
    g.add_node("n1", label=label, source_file="pkg/foo.py", source_location="L1")
    return g


def test_resolve_seed_matches_nfd_query_against_nfc_label() -> None:
    label_nfc = "Auditoría"
    query_nfd = unicodedata.normalize("NFD", label_nfc)
    graph = _graph_with(label_nfc)
    assert resolve_seed(graph, query_nfd) == "n1"
