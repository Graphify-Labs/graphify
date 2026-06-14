"""Tests for graphify/_minhash.py — MinHash sketch and band-LSH."""
from __future__ import annotations
import numpy as np
import pytest
from graphify._minhash import MinHash, MinHashLSH, _optimal_lsh_params


def _minhash_for(text: str, num_perm: int = 128) -> MinHash:
    m = MinHash(num_perm=num_perm)
    for i in range(0, len(text) - 2):
        m.update(text[i:i + 3].encode())
    return m


# ── MinHash ───────────────────────────────────────────────────────────────────

def test_identical_texts_produce_identical_hashvalues():
    a = _minhash_for("graphextractor")
    b = _minhash_for("graphextractor")
    assert np.array_equal(a.hashvalues, b.hashvalues)


def test_similar_texts_share_most_hashvalues():
    a = _minhash_for("authentication manager")
    b = _minhash_for("authentication managers")
    overlap = np.sum(a.hashvalues == b.hashvalues) / len(a.hashvalues)
    assert overlap > 0.5


def test_unrelated_texts_share_few_hashvalues():
    a = _minhash_for("authentication manager")
    b = _minhash_for("file system watcher")
    overlap = np.sum(a.hashvalues == b.hashvalues) / len(a.hashvalues)
    assert overlap < 0.3


def test_update_mutates_hashvalues():
    m = MinHash(num_perm=64)
    before = m.hashvalues.copy()
    m.update(b"hello")
    assert not np.array_equal(m.hashvalues, before)


# ── MinHashLSH ────────────────────────────────────────────────────────────────

def test_near_duplicates_are_candidates():
    lsh = MinHashLSH(threshold=0.5, num_perm=128)
    a = _minhash_for("authentication manager")
    b = _minhash_for("authentication managers")
    lsh.insert("a", a)
    lsh.insert("b", b)
    assert "b" in lsh.query(a)


def test_unrelated_strings_not_candidates():
    lsh = MinHashLSH(threshold=0.5, num_perm=128)
    a = _minhash_for("authentication manager")
    b = _minhash_for("file system watcher")
    lsh.insert("a", a)
    lsh.insert("b", b)
    assert "b" not in lsh.query(a)


def test_query_always_returns_self():
    lsh = MinHashLSH(threshold=0.5, num_perm=128)
    m = _minhash_for("graphextractor")
    lsh.insert("x", m)
    assert "x" in lsh.query(m)


def test_duplicate_insert_raises():
    lsh = MinHashLSH(threshold=0.5, num_perm=128)
    m = _minhash_for("foo")
    lsh.insert("key", m)
    with pytest.raises(ValueError, match="already exists"):
        lsh.insert("key", m)


# ── _optimal_lsh_params ───────────────────────────────────────────────────────

def test_optimal_params_within_budget():
    b, r = _optimal_lsh_params(0.5, 128)
    assert b >= 1 and r >= 1
    assert b * r <= 128


def test_optimal_params_cached():
    result1 = _optimal_lsh_params(0.7, 128)
    result2 = _optimal_lsh_params(0.7, 128)
    assert result1 is result2


# ── EDR regression: scipy / numpy.testing must not be imported ──────────────────

def test_dedup_import_does_not_pull_scipy_or_numpy_testing():
    import sys
    for mod in ("scipy", "numpy.testing"):
        sys.modules.pop(mod, None)
    import graphify.dedup  # noqa: F401
    assert "scipy" not in sys.modules
    assert "numpy.testing" not in sys.modules
