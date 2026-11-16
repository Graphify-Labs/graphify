"""Frontend HTTP call resolution for shared ``http_endpoint`` nodes.

A ``fetch('/api/devices')`` call site and the Django ``path("devices", ...)``
route that serves it never meet in a call graph: the frontend names a string,
the backend binds strings to views. The JS/TS/Svelte extraction pass stamps the
literal URL (and optional init-object verb) onto the call's ``raw_call``
(``http_url``/``http_method``, :mod:`graphify.http_endpoints`); this resolver
consumes the stamps and mints one deterministic ``http_endpoint`` node per
*normalized* pattern, with a ``calls_endpoint`` edge from the calling
function. The Django-side resolver mints the same node id for the route it
serves, so both sides meet at the same node.

Fail-closed throughout: a raw_call without an anchor (``caller_nid``) still
mints the endpoint — the URL is a real fact of the corpus — but inventing a
caller node is not allowed, so no edge is emitted. Duplicate call edges are
suppressed through the shared ``(source, target, relation)`` index (the swift
resolver's ``existing_pairs`` pattern), so re-driving the same inputs, or two
functions fetching the same URL, mint one endpoint and one edge per caller.

Registered for ``HTTP_CALL_SUFFIXES`` (JS/TS plus .svelte/.vue/.astro, which
extract through the same configs) — see extract.py's registration block.
Runs after ``django_routes`` so a backend-minted endpoint keeps the backend's
source of record (``find_or_mint_endpoint`` enriches methods in place).
"""
from __future__ import annotations

from graphify.http_endpoints import (
    HTTP_CALL_SUFFIXES,
    HTTP_RELATION_CALLS,
    KEY_HTTP_METHOD,
    KEY_HTTP_URL,
    edge_key_index,
    endpoint_edge,
    find_or_mint_endpoint,
    normalize_pattern,
)

_DEFAULT_METHOD = "GET"


def _stamped_http_calls(per_file: list[dict]) -> list[dict]:
    """All raw_calls carrying an HTTP URL stamp, from web-suffixed files.

    The suffix gate mirrors the Ruby resolver's file filter: only the JS-family
    extractors ever stamp ``http_url``, so this is defense in depth against a
    same-named key appearing on some other language's raw_call.
    """
    calls: list[dict] = []
    for result in per_file:
        if not isinstance(result, dict):
            continue
        for rc in result.get("raw_calls", []):
            if not isinstance(rc, dict):
                continue
            url = rc.get(KEY_HTTP_URL)
            if not isinstance(url, str) or not url.strip():
                continue
            if str(rc.get("source_file", "")).endswith(tuple(HTTP_CALL_SUFFIXES)):
                calls.append(rc)
    return calls


def resolve_http_fetch_calls(
    per_file: list[dict],
    all_nodes: list[dict],
    all_edges: list[dict],
) -> None:
    """Mint/claim ``http_endpoint`` nodes and ``calls_endpoint`` edges from
    stamped HTTP call raw_calls. Mutates ``all_nodes``/``all_edges`` in place."""
    existing = edge_key_index(all_edges)
    for rc in _stamped_http_calls(per_file):
        # The extractor stamps an uppercase verb; uppercase again so a
        # hand-built stamp still normalizes, and default to GET (the fetch
        # default) when the call named no method.
        method = str(rc.get(KEY_HTTP_METHOD) or _DEFAULT_METHOD).upper()
        source_file = str(rc.get("source_file", ""))
        source_location = rc.get("source_location")
        normalized, has_placeholder = normalize_pattern(rc[KEY_HTTP_URL])
        node = find_or_mint_endpoint(
            all_nodes,
            normalized=normalized,
            has_placeholder=has_placeholder,
            source_file=source_file,
            source_location=source_location,
            origin="frontend",
            methods=[method],
        )
        caller_nid = rc.get("caller_nid")
        if not caller_nid:
            # No anchor for the call site: the endpoint is still minted (the
            # URL is explicit in the source), but an edge needs a real node on
            # both ends — never an invented id (parking-hall rule).
            continue
        key = (caller_nid, node["id"], HTTP_RELATION_CALLS)
        if key in existing:
            continue
        existing.add(key)
        all_edges.append(
            endpoint_edge(
                source=caller_nid,
                target=node["id"],
                relation=HTTP_RELATION_CALLS,
                source_file=source_file,
                source_location=source_location,
            )
        )
