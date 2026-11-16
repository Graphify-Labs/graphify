"""End-to-end HTTP endpoint linking: frontend ``fetch()`` sites meet the Django
routes that serve them at shared ``http_endpoint`` nodes.

The fixture mirrors a two-tier Django layout plus a JS/Svelte frontend: the
root ``urls.py`` includes ``api.urls`` under the ``api/`` prefix, ``api/urls.py``
binds views, and the frontend calls ``fetch()`` inside function bodies
(module-level calls are invisible to the JS walk — tests/test_http_fetch_calls.py
covers that boundary). Everything runs through :func:`graphify.extract.extract`,
so extractor stamping, the AST cache, the resolver registry and both resolvers
(``django_routes`` before ``http_fetch_calls``) all have to cooperate for the
assertions to hold.
"""
from __future__ import annotations

from graphify.extract import extract
from graphify.http_endpoints import (
    HTTP_RELATION_CALLS,
    HTTP_RELATION_SERVES,
    endpoint_id,
    normalize_pattern,
)

ROOT_URLS = """\
from django.urls import include, path

urlpatterns = [
    path("api/", include("api.urls")),
]
"""

API_URLS = """\
from django.urls import path

from . import views

urlpatterns = [
    path("devices", views.list_devices, name="devices"),
    path("runs/<int:run_id>", views.run_detail, name="run_detail"),
]
"""

VIEWS = """\
def list_devices(request):
    return None


def run_detail(request, run_id):
    return None
"""

MAIN_JS = """\
export async function boot() {
  const r = await fetch('/api/devices');
  if (r.ok) {
    return await r.json();
  }
  return [];
}

export async function loadRun(runId) {
  const r = await fetch(`/api/runs/${runId}`);
  return r.json();
}
"""

SPEC_SVELTE = """\
<script>
  export async function refresh() {
    const r = await fetch('/api/specs');
    return r.ok;
  }
</script>

<p>specs</p>
"""

_PATTERNS = ("/api/devices", "/api/runs/${runId}", "/api/specs")


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _project(tmp_path):
    proj = tmp_path / "proj"
    files = [
        _write(proj / "backend" / "example_server" / "urls.py", ROOT_URLS),
        _write(proj / "backend" / "api" / "urls.py", API_URLS),
        _write(proj / "backend" / "api" / "views.py", VIEWS),
        _write(proj / "frontend" / "src" / "main.js", MAIN_JS),
        _write(proj / "frontend" / "src" / "Spec.svelte", SPEC_SVELTE),
    ]
    return proj, files


def _run(files, proj, cache_root):
    return extract(files, root=proj, cache_root=cache_root, parallel=False)


def _strip_parens(label):
    return label[:-2] if isinstance(label, str) and label.endswith("()") else label


def _function_node(result, name, path_suffix):
    matches = [
        n
        for n in result["nodes"]
        if _strip_parens(n.get("label")) == name
        and str(n.get("source_file", "")).endswith(path_suffix)
    ]
    assert len(matches) == 1, f"expected one {name!r} node in *{path_suffix}, got {matches}"
    return matches[0]


def _endpoint_node(result, pattern):
    normalized, _ = normalize_pattern(pattern)
    nid = endpoint_id(normalized)
    matches = [n for n in result["nodes"] if n.get("id") == nid]
    assert len(matches) == 1, f"expected one endpoint {normalized!r}, got {matches}"
    return matches[0]


def _endpoint_type_count(result):
    return sum(1 for n in result["nodes"] if n.get("type") == "http_endpoint")


def _assert_edge(result, source, target, relation):
    edges = [
        e
        for e in result["edges"]
        if e.get("source") == source
        and e.get("target") == target
        and e.get("relation") == relation
    ]
    assert len(edges) == 1, f"missing single edge {source} -{relation}-> {target}"
    assert edges[0]["confidence"] == "EXTRACTED"
    return edges[0]


def _relation_triples(result):
    triples = [
        (e["source"], e["target"], e["relation"])
        for e in result["edges"]
        if e["relation"] in (HTTP_RELATION_CALLS, HTTP_RELATION_SERVES)
    ]
    assert len(triples) == len(set(triples)), f"duplicate endpoint edges: {triples}"
    return set(triples)


def test_frontend_call_reaches_backend_view(tmp_path):
    proj, files = _project(tmp_path)
    result = _run(files, proj, tmp_path / "cache")
    boot = _function_node(result, "boot", "main.js")
    view = _function_node(result, "list_devices", "views.py")
    endpoint = _endpoint_node(result, "/api/devices")
    meta = endpoint["metadata"]["http_endpoint"]
    assert endpoint["type"] == "http_endpoint"
    assert endpoint["label"] == "/api/devices"
    assert endpoint["file_type"] == "code"
    # django_routes runs first, so the backend declaration owns the source of
    # record and the frontend call only enriches observed methods.
    assert meta["origin"] == "backend"
    assert "GET" in meta["methods"]
    _assert_edge(result, boot["id"], endpoint["id"], HTTP_RELATION_CALLS)
    _assert_edge(result, endpoint["id"], view["id"], HTTP_RELATION_SERVES)


def test_endpoint_corpus_is_exactly_the_three_patterns(tmp_path):
    proj, files = _project(tmp_path)
    result = _run(files, proj, tmp_path / "cache")
    assert _endpoint_type_count(result) == 3
    boot = _function_node(result, "boot", "main.js")
    load_run = _function_node(result, "loadRun", "main.js")
    refresh = _function_node(result, "refresh", ".svelte")
    devices_view = _function_node(result, "list_devices", "views.py")
    runs_view = _function_node(result, "run_detail", "views.py")
    devices_ep = _endpoint_node(result, "/api/devices")
    runs_ep = _endpoint_node(result, "/api/runs/${runId}")
    specs_ep = _endpoint_node(result, "/api/specs")
    # Three frontend call edges and two backend serves edges — /api/specs has
    # no backend side, so nothing serves it.
    assert _relation_triples(result) == {
        (boot["id"], devices_ep["id"], HTTP_RELATION_CALLS),
        (load_run["id"], runs_ep["id"], HTTP_RELATION_CALLS),
        (refresh["id"], specs_ep["id"], HTTP_RELATION_CALLS),
        (devices_ep["id"], devices_view["id"], HTTP_RELATION_SERVES),
        (runs_ep["id"], runs_view["id"], HTTP_RELATION_SERVES),
    }


def test_placeholder_patterns_converge(tmp_path):
    proj, files = _project(tmp_path)
    result = _run(files, proj, tmp_path / "cache")
    # Frontend template literal and Django <int:...> converter describe the
    # same endpoint; both sides land on one shared node.
    frontend = _endpoint_node(result, "/api/runs/${runId}")
    backend_id = endpoint_id(normalize_pattern("api/runs/<int:run_id>")[0])
    assert frontend["id"] == backend_id
    meta = frontend["metadata"]["http_endpoint"]
    assert meta["has_placeholder"] is True
    assert meta["origin"] == "backend"
    caller = _function_node(result, "loadRun", "main.js")
    backend_view = _function_node(result, "run_detail", "views.py")
    _assert_edge(result, caller["id"], frontend["id"], HTTP_RELATION_CALLS)
    _assert_edge(result, frontend["id"], backend_view["id"], HTTP_RELATION_SERVES)


def test_svelte_fetch_mints_frontend_endpoint(tmp_path):
    proj, files = _project(tmp_path)
    result = _run(files, proj, tmp_path / "cache")
    endpoint = _endpoint_node(result, "/api/specs")
    caller = _function_node(result, "refresh", ".svelte")
    meta = endpoint["metadata"]["http_endpoint"]
    # No backend route declares this pattern: frontend-only origin, and no
    # serves edge ever leaves the node.
    assert meta["origin"] == "frontend"
    assert meta["methods"] == ["GET"]
    _assert_edge(result, caller["id"], endpoint["id"], HTTP_RELATION_CALLS)
    serves = [e for e in result["edges"] if e.get("relation") == HTTP_RELATION_SERVES]
    assert all(e["source"] != endpoint["id"] for e in serves)


def test_reextract_with_cache_does_not_duplicate(tmp_path):
    proj, files = _project(tmp_path)
    cache = tmp_path / "cache"
    first = _run(files, proj, cache)
    first_triples = _relation_triples(first)
    ids = {pattern: _endpoint_node(first, pattern)["id"] for pattern in _PATTERNS}

    # Touch one backend file (unrelated helper) and re-extract over the same
    # cache: the JS family bypasses the cache per file, urls.py entries come
    # from the stamped AST-cache blobs, and the endpoint corpus must stay
    # byte-stable — same ids, same edges, no duplicates.
    (proj / "backend" / "api" / "views.py").write_text(
        VIEWS + "\n\ndef helper():\n    return None\n", encoding="utf-8"
    )
    second = _run(files, proj, cache)
    assert _relation_triples(second) == first_triples
    assert _endpoint_type_count(second) == 3
    for pattern, nid in ids.items():
        matches = [n for n in second["nodes"] if n.get("id") == nid]
        assert len(matches) == 1, f"endpoint for {pattern!r} duplicated: {matches}"
        assert matches[0]["metadata"]["http_endpoint"]["methods"] == ["GET"]
