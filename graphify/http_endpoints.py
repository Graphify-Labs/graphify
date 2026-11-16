"""Shared contract for HTTP endpoint linking.

Django ``urls.py`` route declarations and frontend ``fetch``/``axios`` call sites
never meet in a static call graph: the frontend issues a string literal
(``fetch('/api/devices')``) and the backend binds strings to views
(``path("devices", views.devices)``). ``_DISPATCH``-driven extractors therefore
stamp these literals onto ``raw_calls`` (established precedent: markdown raw_calls
carry ``language``/``path``/``qualifiers``; ``_dynamic_import_js`` reads
``import('...')`` string arguments), and two ``LanguageResolver`` passes consume the
stamps. Each pass mints one deterministic ``http_endpoint`` node per *normalized*
URL pattern with an id derived from the pattern's hash (terraform ``_scope_id``
precedent: ``make_id`` folds case and punctuation, which must not merge
``api/a-b`` with ``api/a_b``). A frontend call and the backend route that serves it
then meet at the same node instead of an unhopped gap.
"""
from __future__ import annotations

import hashlib
import re

from .ids import make_id

HTTP_ENDPOINT_TYPE = "http_endpoint"
HTTP_RELATION_CALLS = "calls_endpoint"
HTTP_RELATION_SERVES = "serves"
HTTP_CONTEXT = "http"

# Corpus suffixes the frontend resolver reacts to. ``_JS_TS_SUFFIXES`` (extract.py)
# deliberately omits .svelte/.vue/.astro, all of which route through the JS/TS
# configs via ``extract_svelte``/``extract_vue``/``extract_astro``; this set covers
# every web suffix whose extractor can stamp an HTTP call.
HTTP_CALL_SUFFIXES = frozenset(
    {".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".mts", ".cts", ".svelte", ".vue", ".astro"}
)

# Plain global callees whose first string argument is a URL (config-gated on the
# JS/TS language configs so other languages never pay for the scan).
HTTP_GLOBAL_CALLEES = frozenset({"fetch"})

# Member calls (``receiver.method(...)``) whose first string argument is a URL. The
# receiver must also match ``HTTP_MEMBER_RECEIVERS``; anything else is not guessed.
HTTP_MEMBER_CALLEES = frozenset({"get", "post", "put", "patch", "delete", "request"})
HTTP_MEMBER_RECEIVERS = frozenset({"axios"})

# raw_call stamp keys (names only, never node ids — parking-hall rule).
KEY_ROUTE_PATTERN = "route_pattern"
KEY_ROUTE_TARGET = "route_target"
KEY_ROUTE_KIND = "route_kind"
KEY_HTTP_URL = "http_url"
KEY_HTTP_METHOD = "http_method"

ROUTE_KIND_PATH = "path"
ROUTE_KIND_INCLUDE = "include"
ROUTE_KIND_RE_PATH = "re_path"

# A Django path converter: <name>, <int:pk>, <slug:x>, ... (no nesting in practice).
_DJANGO_ARG = re.compile(r"<[^<>]*>")
# A JS template substitution: ${...} (non-greedy to the closing brace).
_JS_TEMPLATE_ARG = re.compile(r"\$\{[^}]*\}")

_PLACEHOLDER = "{param}"


def normalize_pattern(raw: str) -> tuple[str, bool]:
    """Reduce a URL or route pattern to the canonical shared form.

    Returns ``(normalized, has_placeholder)``. Frontend literals and backend
    (composed) routes that describe the same endpoint normalize to the same string:
    query strings and fragments are dropped, leading/trailing slashes and regex
    anchors are stripped, everything is casefolded, and every kind of parameter
    placeholder (Django converters, JS template substitutions) collapses to one
    positional token, so ``/api/runs/${id}`` and ``api/`` + ``runs/<int:pk>`` match.
    """
    s = raw.strip()
    s = s.split("?", 1)[0].split("#", 1)[0]
    s = s.lstrip("^").rstrip("$")
    s = s.strip("/")
    s = s.casefold()
    placeholder = False
    if "<" in s:
        s = _DJANGO_ARG.sub(_PLACEHOLDER, s)
        placeholder = True
    if "${" in s:
        s = _JS_TEMPLATE_ARG.sub(_PLACEHOLDER, s)
        placeholder = True
    return s, placeholder or _PLACEHOLDER in s


def endpoint_id(normalized: str) -> str:
    """Deterministic node id for a normalized pattern, stable from both resolvers."""
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]
    return make_id("http_endpoint", digest)


def endpoint_node(
    normalized: str,
    *,
    source_file: str,
    source_location: str | None,
    origin: str,
    methods: list[str] | tuple[str, ...] = (),
    has_placeholder: bool = False,
) -> dict:
    """Build the shared endpoint node (``file_type`` stays ``"code"`` so
    ``dedup`` never label-merges it with a namesake from another file)."""
    node: dict = {
        "id": endpoint_id(normalized),
        "label": f"/{normalized}" if normalized else "/",
        "file_type": "code",
        "type": HTTP_ENDPOINT_TYPE,
        "language": "http",
        "source_file": source_file,
        "metadata": {
            "http_endpoint": {
                "methods": sorted(set(methods)),
                "has_placeholder": has_placeholder,
                "origin": origin,
            }
        },
    }
    if source_location is not None:
        node["source_location"] = source_location
    return node


def find_or_mint_endpoint(
    nodes: list[dict],
    *,
    normalized: str,
    has_placeholder: bool,
    source_file: str,
    source_location: str | None,
    origin: str,
    methods: list[str] | tuple[str, ...] = (),
) -> dict:
    """Return the shared endpoint node, appending a new one only when absent.

    ``nodes`` includes incremental-rebuild context, so a re-extracted frontend file
    finds the endpoint a previous build minted. Enrichment is additive-only except
    that a backend claim upgrades the frontend's source of record: the resolver
    order (``django_routes`` before ``http_fetch_calls``) means the backend normally
    mints first and the frontend enriches observed methods in place.
    """
    nid = endpoint_id(normalized)
    for node in nodes:
        if node["id"] == nid:
            meta = node.setdefault("metadata", {}).setdefault("http_endpoint", {})
            for method in methods:
                if method not in meta.get("methods", []):
                    meta.setdefault("methods", []).append(method)
            if origin == "backend" and meta.get("origin") != "backend":
                meta["origin"] = "backend"
                node["source_file"] = source_file
                if source_location is not None:
                    node["source_location"] = source_location
            return node
    fresh = endpoint_node(
        normalized,
        source_file=source_file,
        source_location=source_location,
        origin=origin,
        methods=methods,
        has_placeholder=has_placeholder,
    )
    nodes.append(fresh)
    return fresh


def endpoint_edge(
    *,
    source: str,
    target: str,
    relation: str,
    source_file: str,
    source_location: str | None,
) -> dict:
    """Build an endpoint edge. Both endpoint relations are explicit in the source —
    the call site names the URL it fetches, the route names the view it serves — so
    both carry ``EXTRACTED``; the frontend↔backend meeting point is node identity,
    not an inferred edge."""
    edge: dict = {
        "source": source,
        "target": target,
        "relation": relation,
        "context": HTTP_CONTEXT,
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": source_file,
        "weight": 1.0,
    }
    if source_location is not None:
        edge["source_location"] = source_location
    return edge


def edge_key_index(edges: list[dict]) -> set[tuple[str, str, str]]:
    """Existing ``(source, target, relation)`` keys for the duplicate-edge guard
    (the swift resolver's ``existing_pairs`` pattern). ``validate`` guarantees all
    three keys on every edge, so direct indexing cannot raise."""
    return {(e["source"], e["target"], e["relation"]) for e in edges}


def park_endpoint_meta(node: dict, key: str, value: str) -> None:
    """Park a name-only fact on the endpoint node (parking-hall rule: names, never
    ids, so cache relocation and corpus id remaps cannot dangle)."""
    node.setdefault("metadata", {}).setdefault("http_endpoint", {})[key] = value
