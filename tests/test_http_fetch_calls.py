"""HTTP call stamps (JS/TS/Svelte engine pass) and the http_fetch resolver.

Frontend HTTP call sites (``fetch('/api/devices')``, ``axios.get('/api/y')``)
name the URL they talk to, but the call graph has nowhere to put it: the callee
is unresolved (``fetch`` is no project symbol) and the URL is a string literal.
The engine pass therefore stamps ``http_url``/``http_method`` onto the call's
``raw_call`` — additive keys, the markdown raw_calls' ``language``/``path``
precedent — gated on the language config carrying ``http_callees`` (the
extract.py JS/TS/Svelte configs opt in). The resolver mints one shared
``http_endpoint`` node per normalized pattern and a ``calls_endpoint`` edge
from the calling function.

Stamp tests drive the one-file engine extraction exactly like ``extract_js``
does, but with a test config carrying the gate key, so the tests do not depend
on the registration wiring. Resolver tests drive ``resolve_http_fetch_calls``
with hand-built raw_calls (the ruby resolution tests' synthetic style).
"""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from graphify.extract import (
    _JS_CONFIG,
    _TS_CONFIG,
    _extract_generic,
    _normalize_ts_import_types,
    _svelte_mask_non_script,
)
from graphify.http_endpoints import (
    HTTP_GLOBAL_CALLEES,
    HTTP_RELATION_CALLS,
    KEY_HTTP_METHOD,
    KEY_HTTP_URL,
    endpoint_id,
    endpoint_node,
    normalize_pattern,
)
from graphify.http_fetch import resolve_http_fetch_calls


def _http_config(config=None):
    """A copy of a language config opted into HTTP-call stamping.

    ``http_callees`` is the config key the stamping is gated on; setting it on
    a copy keeps the module-level configs in extract.py untouched (they get
    the key added there by the registration wiring).
    """
    cfg = replace(_JS_CONFIG if config is None else config)
    setattr(cfg, "http_callees", HTTP_GLOBAL_CALLEES)
    return cfg


def _extract(path: Path, body: str, *, config=None) -> dict:
    """Write ``body`` to ``path`` and run the one-file engine extraction."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return _extract_generic(path, _http_config(config))


def _stamped(result: dict) -> list[dict]:
    return [rc for rc in result.get("raw_calls", []) if KEY_HTTP_URL in rc]


def _fetches(result: dict) -> list[dict]:
    return [rc for rc in result.get("raw_calls", []) if rc.get("callee") == "fetch"]


# --------------------------------------------------------------------------
# Stamp-side: the engine reads the call's first argument inside walk_calls
# --------------------------------------------------------------------------


def test_fetch_string_literal_stamps_http_url(tmp_path):
    """A plain string first argument is stamped as-is (raw, unnormalized):
    shape normalization belongs to the shared contract, not the extractor."""
    result = _extract(
        tmp_path / "api.js",
        "export async function load() {\n"
        "  await fetch('/api/devices?verbose=1');\n"
        "}\n",
    )
    stamped = _stamped(result)
    assert len(stamped) == 1
    rc = stamped[0]
    # The stamp rides the ordinary raw_call: base fields all present.
    assert rc["callee"] == "fetch"
    assert rc["is_member_call"] is False
    assert rc["receiver"] is None
    assert rc["source_file"].endswith("api.js")
    assert rc["source_location"] == "L2"
    assert rc["caller_nid"] in {n["id"] for n in result["nodes"]}
    assert rc[KEY_HTTP_URL] == "/api/devices?verbose=1"
    # No init object -> no method stamp: the resolver applies the GET default.
    assert KEY_HTTP_METHOD not in rc


def test_fetch_template_literal_keeps_substitution_as_written(tmp_path):
    """A template literal keeps its ``${...}`` substitutions verbatim — the
    shared normalizer (not the extractor) unifies them with route params."""
    result = _extract(
        tmp_path / "api.js",
        "export async function loadRun(id) {\n"
        "  await fetch(`/api/runs/${id}`);\n"
        "}\n",
    )
    stamped = _stamped(result)
    assert [rc[KEY_HTTP_URL] for rc in stamped] == ["/api/runs/${id}"]


def test_fetch_init_object_method_stamp(tmp_path):
    """``{method: 'POST'}`` stamps an uppercase verb; a non-string ``method``
    value (computed verb) stamps nothing — the URL stamp still stands."""
    result = _extract(
        tmp_path / "api.js",
        "export function a() { return fetch('/api/x', {method: 'POST'}); }\n"
        "export function b() { return fetch('/api/lower', {method: 'patch'}); }\n"
        "export function c(verb) { return fetch('/api/dyn', {method: verb}); }\n"
        "export function d() { return fetch('/api/nomethod', {body: '{}'}); }\n",
    )
    by_url = {rc[KEY_HTTP_URL]: rc for rc in _stamped(result)}
    assert set(by_url) == {"/api/x", "/api/lower", "/api/dyn", "/api/nomethod"}
    assert by_url["/api/x"][KEY_HTTP_METHOD] == "POST"
    assert by_url["/api/lower"][KEY_HTTP_METHOD] == "PATCH"
    assert KEY_HTTP_METHOD not in by_url["/api/dyn"]
    assert KEY_HTTP_METHOD not in by_url["/api/nomethod"]


def test_axios_member_call_stamps_url(tmp_path):
    """``axios.get(...)``/``axios.post(...)`` stamp the URL like fetch; a
    member call on any other receiver (jQuery, a friend object) does not."""
    result = _extract(
        tmp_path / "api.js",
        "export function a() {\n"
        "  axios.get('/api/y');\n"
        "  axios.post('/api/z', {id: 1});\n"
        "}\n"
        "export function b() {\n"
        "  jQuery.get('/not-http');\n"
        "  friend.get('/not-http');\n"
        "}\n",
    )
    stamped = _stamped(result)
    assert sorted(rc[KEY_HTTP_URL] for rc in stamped) == ["/api/y", "/api/z"]
    # The axios.get member call keeps its member raw_call shape.
    axios_rc = next(rc for rc in stamped if rc[KEY_HTTP_URL] == "/api/y")
    assert axios_rc["is_member_call"] is True
    assert axios_rc["receiver"] == "axios"
    # axios.post's data object is not an init object with a method string.
    post_rc = next(rc for rc in stamped if rc[KEY_HTTP_URL] == "/api/z")
    assert KEY_HTTP_METHOD not in post_rc
    # Non-matching receivers produce unstamped raw_calls, not silence.
    unstamped = [
        rc for rc in result["raw_calls"]
        if rc.get("callee") == "get" and rc.get("receiver") != "axios"
    ]
    assert len(unstamped) == 2
    assert all(KEY_HTTP_URL not in rc for rc in unstamped)


def test_non_literal_first_argument_stamps_nothing(tmp_path):
    """Fail closed: a computed URL (binary expression, nested call, zero
    args) yields the raw_call but no URL stamp."""
    result = _extract(
        tmp_path / "api.js",
        "export function a(base) { return fetch(base + '/no'); }\n"
        "export function b() { return fetch(buildUrl('/x')); }\n"
        "export function c() { return fetch(); }\n",
    )
    assert len(_fetches(result)) == 3
    assert _stamped(result) == []
    # The nested helper call itself is not an HTTP call either.
    assert all(
        KEY_HTTP_URL not in rc for rc in result["raw_calls"]
    )


def test_stamp_requires_config_gate(tmp_path):
    """A config without ``http_callees`` (every non-web language, and any
    config built with the field empty) stamps nothing."""
    path = tmp_path / "api.js"
    path.write_text(
        "export function load() { return fetch('/api/devices'); }\n",
        encoding="utf-8",
    )
    result = _extract_generic(path, replace(_JS_CONFIG, http_callees=frozenset()))
    assert any(rc.get("callee") == "fetch" for rc in result["raw_calls"])
    assert _stamped(result) == []


def test_in_file_fetch_definition_is_not_an_http_call(tmp_path):
    """A corpus-defined ``fetch`` symbol resolves like any other in-file call
    (a plain calls edge), so no raw_call survives to stamp: a project's own
    ``fetch`` helper is not a URL-carrying HTTP call site."""
    path = tmp_path / "api.js"
    path.write_text(
        "export function fetch(url) { return null; }\n"
        "export function load() { return fetch('/api/devices'); }\n",
        encoding="utf-8",
    )
    result = _extract_generic(path, _http_config())
    assert _stamped(result) == []
    # The call still resolved in-file: fetch() is a plain calls edge target.
    assert any(
        e.get("relation") == "calls" for e in result["edges"]
    )


def test_typescript_config_stamps_template_url(tmp_path):
    """The TS grammar path stamps the same way (``.ts`` files, and Svelte
    script blocks parsed with the TS config)."""
    result = _extract(
        tmp_path / "api.ts",
        "export async function loadRun(id: number) {\n"
        "  await fetch(`/api/runs/${id}`);\n"
        "}\n",
        config=_TS_CONFIG,
    )
    stamped = _stamped(result)
    assert [rc[KEY_HTTP_URL] for rc in stamped] == ["/api/runs/${id}"]


def test_svelte_masked_source_stamps_http_url(tmp_path):
    """Stamps work on masked Svelte sources: blank the markup with the
    extract.py helper and drive the engine with ``source_override``, the
    exact path extract_svelte takes (script blocks parsed via the configs)."""
    component = tmp_path / "Comp.svelte"
    source = (
        "<script>\n"
        "  function load(name) { return fetch(`/api/svelte/${name}`); }\n"
        "</script>\n"
        "<button>hi</button>\n"
    )
    masked, lang = _svelte_mask_non_script(source)
    base = _JS_CONFIG if lang in ("js", "jsx") else _TS_CONFIG
    masked_bytes = masked.encode("utf-8")
    if base is _TS_CONFIG:
        masked_bytes = _normalize_ts_import_types(masked_bytes) or masked_bytes
    result = _extract_generic(component, _http_config(base), source_override=masked_bytes)

    stamped = _stamped(result)
    assert len(stamped) == 1
    rc = stamped[0]
    assert rc[KEY_HTTP_URL] == "/api/svelte/${name}"
    # the .svelte file, not a phantom script file, carries the call site
    assert rc["source_file"].endswith("Comp.svelte")
    assert rc["source_location"] == "L2"


# --------------------------------------------------------------------------
# Resolver-side: synthetic raw_calls, ruby-resolution test style
# --------------------------------------------------------------------------


def _frontend_call(url, *, caller: str | None = "caller", method=None, source_file="src/api.js"):
    rc = {
        "caller_nid": caller,
        "callee": "fetch",
        "is_member_call": False,
        "source_file": source_file,
        "source_location": "L3",
        KEY_HTTP_URL: url,
    }
    if method is not None:
        rc[KEY_HTTP_METHOD] = method
    return rc


def _endpoints(nodes: list) -> list:
    return [n for n in nodes if n.get("type") == "http_endpoint"]


def test_resolver_mints_frontend_endpoint_with_get_default():
    nodes: list[dict] = [{"id": "caller", "label": "load()", "source_file": "src/api.js"}]
    edges: list[dict] = []
    resolve_http_fetch_calls(
        [{"raw_calls": [_frontend_call("/api/devices")]}], nodes, edges
    )

    assert len(_endpoints(nodes)) == 1
    ep = _endpoints(nodes)[0]
    assert ep["id"] == endpoint_id("api/devices")
    assert ep["label"] == "/api/devices"
    assert ep["file_type"] == "code"
    assert ep["language"] == "http"
    assert ep["source_file"] == "src/api.js"
    assert ep["source_location"] == "L3"
    assert ep["metadata"]["http_endpoint"]["origin"] == "frontend"
    assert ep["metadata"]["http_endpoint"]["methods"] == ["GET"]
    assert ep["metadata"]["http_endpoint"]["has_placeholder"] is False

    assert edges == [
        {
            "source": "caller",
            "target": ep["id"],
            "relation": HTTP_RELATION_CALLS,
            "context": "http",
            "confidence": "EXTRACTED",
            "confidence_score": 1.0,
            "source_file": "src/api.js",
            "source_location": "L3",
            "weight": 1.0,
        }
    ]


def test_resolver_normalizes_pattern_and_uses_stamped_method():
    nodes: list[dict] = []
    edges: list[dict] = []
    resolve_http_fetch_calls(
        [{"raw_calls": [
            _frontend_call("/api/runs/${id}", caller="one", method="post"),
            _frontend_call("/api/RUNS/${anything}", caller="two", method="POST"),
        ]}],
        nodes,
        edges,
    )
    # ${...} unifies to one positional token; case folds; two callers, one node.
    endpoints = _endpoints(nodes)
    assert len(endpoints) == 1
    ep = endpoints[0]
    assert ep["label"] == "/api/runs/{param}"
    assert ep["id"] == endpoint_id("api/runs/{param}")
    assert ep["metadata"]["http_endpoint"]["has_placeholder"] is True
    assert ep["metadata"]["http_endpoint"]["methods"] == ["POST"]
    assert len(edges) == 2
    assert {e["source"] for e in edges} == {"one", "two"}


def test_resolver_two_callers_share_one_endpoint():
    nodes: list[dict] = []
    edges: list[dict] = []
    resolve_http_fetch_calls(
        [{"raw_calls": [
            _frontend_call("/api/devices", caller="c1"),
            _frontend_call("/api/devices", caller="c2"),
        ]}],
        nodes,
        edges,
    )
    assert len(_endpoints(nodes)) == 1
    assert len(edges) == 2
    assert {e["source"] for e in edges} == {"c1", "c2"}
    assert {e["target"] for e in edges} == {_endpoints(nodes)[0]["id"]}


def test_resolver_re_drive_is_idempotent():
    """Running the resolver again over the same stamps must not drift: the
    endpoint node is reused (find_or_mint id-reuse) and the duplicate-edge
    guard suppresses the second calls_endpoint edge."""
    nodes: list[dict] = [{"id": "caller", "label": "load()", "source_file": "src/api.js"}]
    edges: list[dict] = []
    per_file = [{"raw_calls": [_frontend_call("/api/devices")]}]
    resolve_http_fetch_calls(per_file, nodes, edges)
    ep_before = _endpoints(nodes)[0]
    node_count, edge_count = len(nodes), len(edges)

    resolve_http_fetch_calls(per_file, nodes, edges)
    assert len(nodes) == node_count
    assert len(edges) == edge_count
    assert _endpoints(nodes)[0] is ep_before
    assert ep_before["metadata"]["http_endpoint"]["methods"] == ["GET"]


def test_resolver_missing_caller_mints_endpoint_but_no_edge():
    """A raw_call without an anchor is still real evidence for the URL, so
    the endpoint is minted — but the resolver must not invent a caller id."""
    nodes: list[dict] = []
    edges: list[dict] = []
    rc = _frontend_call("/api/devices", caller=None)
    resolve_http_fetch_calls([{"raw_calls": [rc]}], nodes, edges)
    endpoints = _endpoints(nodes)
    assert len(endpoints) == 1
    assert endpoints[0]["metadata"]["http_endpoint"]["origin"] == "frontend"
    assert edges == []


def test_resolver_enriches_backend_endpoint_without_re_anchoring():
    """A backend-minted endpoint (django side won the id) keeps its source of
    record; the frontend pass only adds the observed method in place."""
    backend = endpoint_node(
        "api/devices", source_file="backend/api/urls", source_location="L7",
        origin="backend",
    )
    nodes: list[dict] = [backend]
    edges: list[dict] = []
    resolve_http_fetch_calls(
        [{"raw_calls": [_frontend_call("/api/devices")]}], nodes, edges
    )
    assert len(nodes) == 1  # reused, not re-minted
    ep = nodes[0]
    assert ep is backend
    assert ep["metadata"]["http_endpoint"]["origin"] == "backend"
    assert ep["source_file"] == "backend/api/urls"
    assert ep["source_location"] == "L7"
    assert ep["metadata"]["http_endpoint"]["methods"] == ["GET"]
    assert len(edges) == 1
    assert edges[0]["target"] == ep["id"]


@pytest.mark.parametrize(
    "raw_call",
    [
        # unstamped ordinary call: the resolver's input is normal raw_calls too
        {"caller_nid": "c", "callee": "helper", "source_file": "src/api.js"},
        # stamp but outside the web suffixes: not this resolver's input
        {"caller_nid": "c", "source_file": "tool/run.py", KEY_HTTP_URL: "/api/x"},
        # empty URL: fail closed
        {"caller_nid": "c", "source_file": "src/api.js", KEY_HTTP_URL: " "},
        # malformed entries never crash the pass
        None,
        "junk",
    ],
)
def test_resolver_skips_non_matching_raw_calls(raw_call):
    nodes: list[dict] = []
    edges: list[dict] = []
    resolve_http_fetch_calls([{"raw_calls": [raw_call]}], nodes, edges)
    assert nodes == []
    assert edges == []


def test_resolver_dedupes_against_existing_edges():
    """The (source, target, relation) guard also covers edges minted by a
    previous pass over the same stamps (e.g. incremental context)."""
    normalized, _ = normalize_pattern("api/devices")
    existing_target = endpoint_id(normalized)
    nodes: list[dict] = []
    edges: list[dict] = [
        {"source": "caller", "target": existing_target, "relation": HTTP_RELATION_CALLS}
    ]
    resolve_http_fetch_calls(
        [{"raw_calls": [_frontend_call("/api/devices")]}], nodes, edges
    )
    assert len(_endpoints(nodes)) == 1  # the node is still new
    assert len(edges) == 1  # the edge is not
