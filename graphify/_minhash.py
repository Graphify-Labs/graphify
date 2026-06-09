"""MinHash + band-LSH — datasketch-compatible drop-in (no scipy).

datasketch.lsh has `from scipy.integrate import quad` at module level.
scipy's array_api_compat layer then lazily loads numpy.testing, which calls
platform.machine() at import time to set test-skip decorator constants — and
that in turn spawns cmd.exe via subprocess, hanging for minutes under EDR
software in corporate Windows environments.

Covers the exact MinHash/MinHashLSH API surface used by dedup.py.
Hash family (Mersenne-prime permutations) and LSH band structure are
equivalent to datasketch so dedup quality is unchanged.
"""
from __future__ import annotations
import hashlib
import struct

import numpy as np


_MP = np.uint64((1 << 61) - 1)  # Mersenne prime for the hash family
_MH = np.uint64(0xFFFF_FFFF)    # mask to 32-bit values

# One (a, b) coefficient array per num_perm, shared across all instances.
_MH_COEFFS: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def _mh_coeffs(num_perm: int) -> tuple[np.ndarray, np.ndarray]:
    if num_perm not in _MH_COEFFS:
        rng = np.random.RandomState(1)
        a = rng.randint(1, int(_MP), num_perm, dtype=np.uint64)
        b = rng.randint(0, int(_MP), num_perm, dtype=np.uint64)
        _MH_COEFFS[num_perm] = (a, b)
    return _MH_COEFFS[num_perm]


class MinHash:
    """MinHash sketch — same API as datasketch.MinHash for the subset used here."""

    __slots__ = ("num_perm", "hashvalues", "_a", "_b")

    def __init__(self, num_perm: int = 128) -> None:
        self.num_perm = num_perm
        self.hashvalues = np.full(num_perm, int(_MH), dtype=np.uint64)
        self._a, self._b = _mh_coeffs(num_perm)

    def update(self, v: bytes) -> None:
        hv = np.uint64(struct.unpack("<I", hashlib.sha1(v).digest()[:4])[0])
        phv = np.bitwise_and((self._a * hv + self._b) % _MP, _MH)
        self.hashvalues = np.minimum(self.hashvalues, phv)


def _lsh_integrate(f, lo: float, hi: float, n: int = 128) -> float:
    """Numerical integration — replaces scipy.integrate.quad for LSH param search."""
    h = (hi - lo) / n
    return h * sum(f(lo + i * h) for i in range(n))


_LSH_PARAMS_CACHE: dict[tuple[float, int], tuple[int, int]] = {}


def _optimal_lsh_params(threshold: float, num_perm: int) -> tuple[int, int]:
    """Find (bands, rows) that minimise weighted FP+FN error, without scipy."""
    key = (threshold, num_perm)
    if key in _LSH_PARAMS_CACHE:
        return _LSH_PARAMS_CACHE[key]
    best_err, best = float("inf"), (1, 1)
    for b in range(1, num_perm + 1):
        for r in range(1, num_perm // b + 1):
            fp = _lsh_integrate(
                lambda s, _b=float(b), _r=float(r): 1 - (1 - s ** _r) ** _b,
                0.0, threshold,
            )
            fn = _lsh_integrate(
                lambda s, _b=float(b), _r=float(r): 1 - (1 - (1 - s ** _r) ** _b),
                threshold, 1.0,
            )
            err = 0.5 * fp + 0.5 * fn
            if err < best_err:
                best_err, best = err, (b, r)
    _LSH_PARAMS_CACHE[key] = best
    return best


class MinHashLSH:
    """Band-hashing LSH — same API as datasketch.MinHashLSH for the subset used here."""

    def __init__(self, threshold: float = 0.5, num_perm: int = 128) -> None:
        self.b, self.r = _optimal_lsh_params(threshold, num_perm)
        self._tables: list[dict[bytes, list[str]]] = [{} for _ in range(self.b)]
        self._keys: set[str] = set()

    def insert(self, key: str, minhash: MinHash) -> None:
        if key in self._keys:
            raise ValueError(f"Key {key!r} already exists in MinHashLSH")
        self._keys.add(key)
        hv = minhash.hashvalues
        for i, table in enumerate(self._tables):
            band = hv[i * self.r : (i + 1) * self.r].tobytes()
            table.setdefault(band, []).append(key)

    def query(self, minhash: MinHash) -> list[str]:
        hv = minhash.hashvalues
        candidates: set[str] = set()
        for i, table in enumerate(self._tables):
            band = hv[i * self.r : (i + 1) * self.r].tobytes()
            candidates.update(table.get(band, []))
        return list(candidates)
