"""Accepted edge-pair orientation shared by dependency and source-owner consumers.

Markers may reverse undirected storage, but cannot supply foreign endpoints or
partly replace raw orientation. Unmarked legacy edges keep their original pair.
"""
from __future__ import annotations


def logical_endpoints(source, target, data, *, directed):
    """Return the accepted logical pair, or None for inconsistent direction transport."""
    if "_src" not in data and "_tgt" not in data:
        return source, target
    if "_src" not in data or "_tgt" not in data:
        return None
    src, tgt = data["_src"], data["_tgt"]
    # Exact endpoint types prevent bool/integer coercion from authorizing a
    # malformed serialized ID. Equality alone is insufficient for that case.
    if type(src) is type(source) and type(tgt) is type(target) and src == source and tgt == target:
        return src, tgt
    if (not directed and type(src) is type(target) and type(tgt) is type(source)
            and src == target and tgt == source):
        return src, tgt
    return None


def valid_direction_pairs(edges, *, directed):
    """Preflight explicit edge tuples before any comparison or publication shortcut."""
    return all(logical_endpoints(source, target, data, directed=directed) is not None
               for source, target, data in edges)
