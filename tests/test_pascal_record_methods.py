"""Regression tests for record types and operator overloads in the
Pascal/Delphi extractor's regex fallback path (`_extract_pascal_regex`).

Before this fix, `_PAS_TYPE_HEADER_RE`'s ``kind`` group only matched
``class``/``interface``, so a ``record`` type never minted its own node at
all -- advanced records with methods (a common modern Delphi/Free Pascal
pattern) were entirely invisible as owning types, and their method
implementations fell back to being attached directly to the module as free
functions instead of as `method` edges on the record. Separately,
`_PAS_METHOD_DECL_RE`/`_PAS_IMPL_HEADER_RE` only matched
``procedure|function|constructor|destructor``, so a ``class operator``
overload (used for operator overloading on both classes and records) never
matched either regex and was dropped regardless of its container type. See
`sample_record_methods.pas`.
"""
from __future__ import annotations

import pytest
from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures"
FIXTURE_PATH = FIXTURES / "sample_record_methods.pas"


def _extractors():
    from graphify.extract import extract_pascal, _extract_pascal_regex
    return [extract_pascal, _extract_pascal_regex]


def _node(r, label):
    matches = [n for n in r["nodes"] if n["label"] == label]
    assert len(matches) == 1, f"expected exactly one node labeled {label!r}, got {matches}"
    return matches[0]


def _method_edges_from(r, owner_id):
    return [e for e in r["edges"] if e["relation"] == "method" and e["source"] == owner_id]


@pytest.mark.parametrize("extract", [
    pytest.param(0, id="tree-sitter"),
    pytest.param(1, id="regex-fallback"),
])
def test_record_type_gets_its_own_node(extract):
    r = _extractors()[extract](FIXTURE_PATH)
    _node(r, "TVec")


@pytest.mark.parametrize("extract", [
    pytest.param(0, id="tree-sitter"),
    pytest.param(1, id="regex-fallback"),
])
def test_record_plain_method_is_owned_by_the_record(extract):
    r = _extractors()[extract](FIXTURE_PATH)
    record_id = _node(r, "TVec")["id"]
    owned_labels = {n["id"]: n["label"] for n in r["nodes"]}
    owned = [owned_labels[e["target"]] for e in _method_edges_from(r, record_id)]
    assert "Len()" in owned


@pytest.mark.parametrize("extract", [
    pytest.param(0, id="tree-sitter"),
    pytest.param(1, id="regex-fallback"),
])
def test_record_operator_overload_gets_a_method_node(extract):
    r = _extractors()[extract](FIXTURE_PATH)
    record_id = _node(r, "TVec")["id"]
    owned_labels = {n["id"]: n["label"] for n in r["nodes"]}
    owned = [owned_labels[e["target"]] for e in _method_edges_from(r, record_id)]
    assert "Add()" in owned


@pytest.mark.parametrize("extract", [
    pytest.param(0, id="tree-sitter"),
    pytest.param(1, id="regex-fallback"),
])
def test_operator_is_not_wrongly_attached_to_the_module(extract):
    """Control: the operator method must be owned by the record, not fall
    back to a module-level `contains` edge the way it did before the record
    type itself was recognized."""
    r = _extractors()[extract](FIXTURE_PATH)
    add_node = _node(r, "Add()")
    owner_edges = [e for e in r["edges"] if e["target"] == add_node["id"]]
    assert len(owner_edges) == 1
    assert owner_edges[0]["relation"] == "method"
