"""Django routes: urls.py route stamping and cross-file resolution.

``extract._stamp_django_url_routes`` mints route-stamped raw_calls for Django
``urls.py`` module-level ``path()``/``re_path()``/``include()`` calls — a region
the function-body call walk never visits — and ``graphify.django_routes.
resolve_django_routes`` composes them: include prefixes compose across files,
each composed pattern mints one shared ``http_endpoint`` node (``graphify.
http_endpoints`` is the cross-resolver contract), and the named view gets a
``serves`` edge when it resolves through the urls.py's own import evidence.

Fail-closed cases park name-only facts on the endpoint node instead of edges
(house rule: no guessed relations): an include ambiguous between corpus files
adds no prefix; a view that is absent, duplicated or class-based parks
``unresolved_view``; a ``re_path`` regex parks ``unresolved_route`` and never
binds a view.
"""
from __future__ import annotations

from pathlib import Path

from graphify.django_routes import resolve_django_routes
from graphify.extract import extract, extract_python
from graphify.http_endpoints import (
    HTTP_RELATION_SERVES,
    KEY_ROUTE_KIND,
    KEY_ROUTE_PATTERN,
    KEY_ROUTE_TARGET,
    ROUTE_KIND_INCLUDE,
    ROUTE_KIND_PATH,
    ROUTE_KIND_RE_PATH,
    endpoint_id,
)
from graphify.resolver_registry import LanguageResolver


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _endpoint_nodes(nodes: list[dict]) -> dict[str, dict]:
    """Endpoint nodes keyed by their normalized pattern (label minus the
    leading slash; '' is the repo root route)."""
    out: dict[str, dict] = {}
    for n in nodes:
        if n.get("type") == "http_endpoint":
            out[str(n.get("label", "")).lstrip("/")] = n
    return out


def _serves_edges(edges: list[dict]) -> list[dict]:
    return [e for e in edges if e.get("relation") == HTTP_RELATION_SERVES]


def _stamps(result: dict) -> list[dict]:
    return [rc for rc in result.get("raw_calls", []) if KEY_ROUTE_KIND in rc]


# ── stamping (extract._stamp_django_url_routes, via extract_python) ──────────


def test_urls_py_route_calls_mint_stamped_raw_calls(tmp_path: Path):
    """path()/re_path() stamps carry the pattern (first literal arg), the
    target (second positional arg's source text, a string decoded to its
    value) and the kind; a non-literal first arg fails closed and stamps
    nothing, a keyword-only second arg leaves no target."""
    urls = _write(tmp_path / "api" / "urls.py", (
        "from django.urls import path, re_path\n"
        "from . import views\n"
        "from . import data\n"
        "\n"
        "urlpatterns = [\n"
        '    path("devices", views.devices),\n'
        '    path("data", data.data),\n'
        '    re_path(r"^runs$", views.runs),\n'
        "    path(premade(\"x\"), views.devices),\n"
        '    path("kwarg", view=views.devices),\n'
        '    path("runs", "views.runs"),\n'
        "]\n"
    ))
    result = extract_python(urls, root=tmp_path)
    stamps = _stamps(result)
    observed = {
        (rc[KEY_ROUTE_KIND], rc.get(KEY_ROUTE_PATTERN), rc.get(KEY_ROUTE_TARGET))
        for rc in stamps
    }
    assert observed == {
        (ROUTE_KIND_PATH, "devices", "views.devices"),
        (ROUTE_KIND_PATH, "data", "data.data"),
        (ROUTE_KIND_RE_PATH, "^runs$", "views.runs"),
        (ROUTE_KIND_PATH, "kwarg", None),         # keyword arg is not positional: no target
        (ROUTE_KIND_PATH, "runs", "views.runs"),  # string literal arg decoded to the name
    }
    # `path(premade("x"), ...)` — non-literal first argument stamps nothing.
    assert not any(rc.get(KEY_ROUTE_PATTERN) == "x" for rc in stamps)
    # Inert to every other raw_calls consumer: no callee, no member-call
    # marker. The caller anchor is the module-level file node id (#2231).
    file_ids = {n["id"] for n in result["nodes"] if n.get("label") == "urls.py"}
    assert file_ids
    for rc in stamps:
        assert "callee" not in rc
        assert not rc.get("is_member_call")
        assert rc["caller_nid"] in file_ids
        assert rc["source_file"] == str(urls)
        assert rc["source_location"].startswith("L")


def test_only_urls_py_files_stamp_and_nested_include_stamps_once(tmp_path: Path):
    """A file not named urls.py stamps nothing; the nested include() inside
    path(...) is stamped exactly once — on the outer call, as kind include,
    with the include's module literal as target (never a second standalone
    include stamp for the same construct)."""
    plain = _write(tmp_path / "web" / "routes.py", (
        "from django.urls import path\n"
        "urlpatterns = [path('devices', None)]\n"
    ))
    assert _stamps(extract_python(plain, root=tmp_path)) == []

    urls = _write(tmp_path / "web" / "urls.py", (
        "from django.urls import include, path\n"
        "urlpatterns = [\n"
        '    path("api/", include("api.urls")),\n'
        "]\n"
    ))
    result = extract_python(urls, root=tmp_path)
    stamps = _stamps(result)
    assert len(stamps) == 1
    assert stamps[0][KEY_ROUTE_KIND] == ROUTE_KIND_INCLUDE
    assert stamps[0][KEY_ROUTE_PATTERN] == "api/"
    assert stamps[0][KEY_ROUTE_TARGET] == "api.urls"


# ── resolver semantics (drive-the-resolver-directly style) ──────────────────


def _mini_nodes_and_edges(*, import_views: bool = True) -> tuple[list[dict], list[dict]]:
    """Hand-built lists mirroring the post-extract shapes of a urls.py corpus:
    file nodes carry the basename as label, def nodes are labelled ``name()``,
    and ``from . import views`` lands as an imports_from edge to the views
    file node (shapes observed via extract() over the same fixture)."""
    nodes = [
        {"id": "backend_example_server_urls", "label": "urls.py", "file_type": "code",
         "source_file": "backend/example_server/urls.py"},
        {"id": "backend_api_urls", "label": "urls.py", "file_type": "code",
         "source_file": "backend/api/urls.py"},
        {"id": "backend_api_views", "label": "views.py", "file_type": "code",
         "source_file": "backend/api/views.py"},
        {"id": "backend_api_views_devices", "label": "devices()", "file_type": "code",
         "source_file": "backend/api/views.py"},
        {"id": "backend_api_views_runs", "label": "runs()", "file_type": "code",
         "source_file": "backend/api/views.py"},
        {"id": "backend_api_data", "label": "data.py", "file_type": "code",
         "source_file": "backend/api/data.py"},
        {"id": "backend_api_data_data", "label": "data()", "file_type": "code",
         "source_file": "backend/api/data.py"},
    ]
    edges = [
        {"source": "backend_api_views", "target": "backend_api_views_devices",
         "relation": "contains", "confidence": "EXTRACTED",
         "source_file": "backend/api/views.py"},
        {"source": "backend_api_views", "target": "backend_api_views_runs",
         "relation": "contains", "confidence": "EXTRACTED",
         "source_file": "backend/api/views.py"},
        {"source": "backend_api_data", "target": "backend_api_data_data",
         "relation": "contains", "confidence": "EXTRACTED",
         "source_file": "backend/api/data.py"},
    ]
    if import_views:
        edges.append({"source": "backend_api_urls", "target": "backend_api_views",
                      "relation": "imports_from", "context": "submodule_import",
                      "confidence": "EXTRACTED", "source_file": "backend/api/urls.py"})
        edges.append({"source": "backend_api_urls", "target": "backend_api_data",
                      "relation": "imports_from", "context": "submodule_import",
                      "confidence": "EXTRACTED", "source_file": "backend/api/urls.py"})
    return nodes, edges


def _resolve_batch(*batches: list[dict]) -> tuple[list[dict], list[dict], list[dict]]:
    """Resolve one per_file batch against fresh node/edge lists; returns all
    three for assertions."""
    nodes, edges = _mini_nodes_and_edges()
    per_file = [{"raw_calls": [*batch]} for batch in batches]
    resolve_django_routes(per_file, nodes, edges)
    return per_file, nodes, edges


def _include_stamp(pattern="api/", target="api.urls", sf="backend/example_server/urls.py"):
    return {"caller_nid": "backend_example_server_urls", "source_file": sf,
            "source_location": "L5", KEY_ROUTE_KIND: ROUTE_KIND_INCLUDE,
            KEY_ROUTE_PATTERN: pattern, KEY_ROUTE_TARGET: target}


def _path_stamp(pattern, target, sf="backend/api/urls.py", line="L6"):
    rc = {"caller_nid": "backend_api_urls", "source_file": sf, "source_location": line,
          KEY_ROUTE_KIND: ROUTE_KIND_PATH, KEY_ROUTE_PATTERN: pattern}
    if target is not None:
        rc[KEY_ROUTE_TARGET] = target
    return rc


def _re_path_stamp(pattern, target, sf="backend/api/urls.py", line="L8"):
    return {"caller_nid": "backend_api_urls", "source_file": sf, "source_location": line,
            KEY_ROUTE_KIND: ROUTE_KIND_RE_PATH, KEY_ROUTE_PATTERN: pattern,
            KEY_ROUTE_TARGET: target}


def test_endpoint_composition_and_serves_edges():
    """The nested include prefix composes onto every route in the child file;
    endpoints mint backend-origin; serves edges bind the real view defs with
    EXTRACTED confidence, and a re_path regex parks unresolved_route."""
    _per_file, nodes, edges = _resolve_batch(
        [_include_stamp()],
        [_path_stamp("devices", "views.devices"),
         _path_stamp("data", "data.data"),
         _re_path_stamp(r"^runs$", "views.runs")],
    )

    endpoints = _endpoint_nodes(nodes)
    assert set(endpoints) == {"api/devices", "api/data", "api/^runs"}
    devices = endpoints["api/devices"]
    assert devices["id"] == endpoint_id("api/devices")
    assert devices["source_file"] == "backend/api/urls.py"
    assert devices["metadata"]["http_endpoint"] == {
        "methods": [], "has_placeholder": False, "origin": "backend",
    }

    serves = _serves_edges(edges)
    assert len(serves) == 2
    devices_edge = next(e for e in serves if e["target"] == "backend_api_views_devices")
    assert devices_edge == {
        "source": endpoint_id("api/devices"),
        "target": "backend_api_views_devices",
        "relation": "serves",
        "context": "http",
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": "backend/api/urls.py",
        "source_location": "L6",
        "weight": 1.0,
    }
    assert any(e["target"] == "backend_api_data_data" for e in serves)

    # re_path: the endpoint node exists (the regex anchors survive the shared
    # normalizer — regex normalization is out of scope by contract) but it is
    # parked, and no serves edge leaves it.
    runs = endpoints["api/^runs"]
    assert runs["metadata"]["http_endpoint"]["unresolved_route"] == "api/^runs$"
    assert not any(e.get("source") == runs["id"] for e in edges)
    assert "unresolved_view" not in runs["metadata"]["http_endpoint"]


def test_ambiguous_include_target_yields_no_prefix():
    """Two candidate files ending api/urls.py: the include fails closed — its
    child routes mint with their raw pattern (still bound to the view)."""
    urls_sf = "backend/api/urls.py"
    nodes = [
        {"id": "root_urls", "label": "urls.py", "file_type": "code",
         "source_file": "root/urls.py"},
        {"id": "backend_api_urls", "label": "urls.py", "file_type": "code",
         "source_file": urls_sf},
        {"id": "dup_api_urls", "label": "urls.py", "file_type": "code",
         "source_file": "dup/api/urls.py"},
        {"id": "backend_api_views", "label": "views.py", "file_type": "code",
         "source_file": "backend/api/views.py"},
        {"id": "backend_api_views_devices", "label": "devices()", "file_type": "code",
         "source_file": "backend/api/views.py"},
    ]
    edges = [
        {"source": "backend_api_views", "target": "backend_api_views_devices",
         "relation": "contains", "confidence": "EXTRACTED",
         "source_file": "backend/api/views.py"},
        {"source": "backend_api_urls", "target": "backend_api_views",
         "relation": "imports_from", "confidence": "EXTRACTED", "source_file": urls_sf},
    ]
    per_file = [
        {"raw_calls": [_include_stamp(sf="root/urls.py")]},
        {"raw_calls": [_path_stamp("devices", "views.devices")]},
    ]
    resolve_django_routes(per_file, nodes, edges)

    endpoints = _endpoint_nodes(nodes)
    assert set(endpoints) == {"devices"}
    assert endpoints["devices"]["id"] == endpoint_id("devices")
    serves = _serves_edges(edges)
    assert [(e["source"], e["target"], e["confidence"]) for e in serves] == [
        (endpoint_id("devices"), "backend_api_views_devices", "EXTRACTED"),
    ]
    # The view itself resolved: nothing parked.
    assert "unresolved_view" not in endpoints["devices"]["metadata"]["http_endpoint"]


def test_unresolved_view_parks_name_only():
    """A dotted view whose module the urls.py never imports (and a member that
    does not exist under an imported module) mints the endpoint with the
    composed prefix, parks the name and emits no serves edge."""
    _per_file, nodes, edges = _resolve_batch(
        [_include_stamp()],
        [_path_stamp("devices", "views.devices"),       # views IS imported: resolves
         _path_stamp("ghosts", "missing.ghost")],       # module never imported
    )
    endpoints = _endpoint_nodes(nodes)
    assert set(endpoints) == {"api/devices", "api/ghosts"}
    assert "unresolved_view" not in endpoints["api/devices"]["metadata"]["http_endpoint"]
    ghost = endpoints["api/ghosts"]
    assert ghost["metadata"]["http_endpoint"]["unresolved_view"] == "missing.ghost"
    assert not any(e.get("source") == ghost["id"] for e in edges)

    # Member missing under an imported module parks the same way (fresh corpus).
    _, nodes2, edges2 = _resolve_batch(
        [_include_stamp()],
        [_path_stamp("nosuch", "views.nosuch")],
    )
    parked = _endpoint_nodes(nodes2)["api/nosuch"]
    assert parked["metadata"]["http_endpoint"]["unresolved_view"] == "views.nosuch"
    assert _serves_edges(edges2) == []


def test_bare_and_imported_def_targets_resolve():
    """A bare `inline_view` resolves to the urls.py's own contained def; a
    `from .views import devices` import edge targets the def node itself and
    resolves bare names exactly; a class-based view (label without call
    parens) and a bare name with two visible defs park unresolved_view."""
    urls_sf = "backend/api/urls.py"
    nodes, edges = _mini_nodes_and_edges(import_views=False)
    nodes.extend([
        {"id": "backend_api_urls_inline_view", "label": "inline_view()", "file_type": "code",
         "source_file": urls_sf},
        {"id": "backend_api_views_view", "label": "DeviceView", "file_type": "code",
         "source_file": "backend/api/views.py"},
        {"id": "dup_views_misc", "label": "misc()", "file_type": "code",
         "source_file": "dup/views.py"},
        {"id": "dup_views_misc2", "label": "misc()", "file_type": "code",
         "source_file": "dup2/views.py"},
    ])
    edges.extend([
        {"source": "backend_api_urls", "target": "backend_api_urls_inline_view",
         "relation": "contains", "confidence": "EXTRACTED", "source_file": urls_sf},
        {"source": "dup_views", "target": "dup_views_misc", "relation": "contains",
         "confidence": "EXTRACTED", "source_file": "dup/views.py"},
        {"source": "dup2_views", "target": "dup_views_misc2", "relation": "contains",
         "confidence": "EXTRACTED", "source_file": "dup2/views.py"},
        # `from .views import devices` — the edge points at the def node.
        {"source": "backend_api_urls", "target": "backend_api_views_devices",
         "relation": "imports", "confidence": "EXTRACTED", "source_file": urls_sf},
    ])
    stamps = [
        _path_stamp("inline", "inline_view"),
        _path_stamp("imported", "devices"),
        _path_stamp("twins", "misc"),
        _path_stamp("cls", "views.DeviceView"),
    ]
    nodes.append({"id": "backend_example_server_urls", "label": "urls.py", "file_type": "code",
                  "source_file": "backend/example_server/urls.py"})
    resolve_django_routes(
        [{"raw_calls": [_include_stamp()]}, {"raw_calls": stamps}], nodes, edges
    )

    endpoints = _endpoint_nodes(nodes)
    assert set(endpoints) == {"api/inline", "api/imported", "api/twins", "api/cls"}
    serves = {e["source"]: e["target"] for e in _serves_edges(edges)}
    assert serves == {
        endpoint_id("api/inline"): "backend_api_urls_inline_view",
        endpoint_id("api/imported"): "backend_api_views_devices",
    }
    meta = endpoints["api/twins"]["metadata"]["http_endpoint"]
    assert meta["unresolved_view"] == "misc"          # two visible defs: ambiguous
    assert endpoints["api/cls"]["metadata"]["http_endpoint"]["unresolved_view"] == (
        "views.DeviceView"
    )


def test_resolver_run_twice_never_duplicates():
    """Driving the resolver a second time over the same batch mints no new
    endpoint node and no new edge (mint-if-absent + duplicate-edge guard)."""
    per_file = [
        {"raw_calls": [_include_stamp()]},
        {"raw_calls": [_path_stamp("devices", "views.devices"),
                       _path_stamp("data", "data.data"),
                       _re_path_stamp(r"^runs$", "views.runs")]},
    ]
    nodes, edges = _mini_nodes_and_edges()
    resolve_django_routes(per_file, nodes, edges)
    node_count = len(nodes)
    edge_count = len(edges)
    endpoint_ids = sorted(n["id"] for n in nodes if n.get("type") == "http_endpoint")

    resolve_django_routes(per_file, nodes, edges)
    assert len(nodes) == node_count
    assert len(edges) == edge_count
    assert sorted(n["id"] for n in nodes if n.get("type") == "http_endpoint") == endpoint_ids


# ── full pipeline (extract() + in-test registration) ───────────────────────


def _with_django_resolver(extractor):
    """Register resolve_django_routes around one extract() call. The permanent
    registration line is W3's integration step, so each test owns the global
    registry and restores it afterwards (tests/csharp_extension_harness.py
    precedent)."""
    from graphify import resolver_registry

    def _run(*args, **kwargs):
        saved = resolver_registry._REGISTRY[:]
        resolver = LanguageResolver(
            "django_routes_test", frozenset({".py"}), resolve_django_routes
        )
        resolver_registry._REGISTRY.append(resolver)
        try:
            return extractor(*args, **kwargs)
        finally:
            resolver_registry._REGISTRY[:] = saved

    return _run


_extract_with_django = _with_django_resolver(extract)


def _mini_django_repo(base: Path) -> list[Path]:
    _write(base / "backend" / "example_server" / "urls.py", (
        "from django.urls import include, path\n"
        "\n"
        "urlpatterns = [\n"
        '    path("api/", include("api.urls")),\n'
        "]\n"
    ))
    _write(base / "backend" / "api" / "urls.py", (
        "from django.urls import path, re_path\n"
        "from . import views\n"
        "from . import data\n"
        "\n"
        "urlpatterns = [\n"
        '    path("devices", views.devices),\n'
        '    path("data", data.data),\n'
        '    re_path(r"^runs$", views.runs),\n'
        "]\n"
    ))
    _write(base / "backend" / "api" / "views.py", (
        "def devices(request):\n    return None\n\n\n"
        "def runs(request):\n    return None\n\n\n"
        "# A same-named decoy: the minted route stamps carry no callee, so the\n"
        "# shared cross-file bare-name pass must never wire a calls edge here.\n"
        "def path(request):\n    return None\n"
    ))
    _write(base / "backend" / "api" / "data.py", "def data(request):\n    return None\n")
    return sorted(base.rglob("*.py"))


def _pipeline_endpoints(result: dict) -> dict[str, dict]:
    return _endpoint_nodes(result["nodes"])


def test_full_extract_mints_composed_routes_and_reextract_does_not_duplicate(tmp_path: Path):
    """End to end: extract() composes the include prefix, binds serves edges
    through the real post-extract node ids, and a second extract() over the
    same corpus (the AST cache replay supplies the stamps) reproduces the
    same endpoint ids without duplicating nodes or edges."""
    files = _mini_django_repo(tmp_path / "proj")
    root = (tmp_path / "proj").resolve()
    cache = tmp_path / "cache"

    first = _extract_with_django(files, cache_root=cache, root=root)
    endpoints = _pipeline_endpoints(first)
    assert set(endpoints) == {"api/devices", "api/data", "api/^runs"}
    devices = endpoints["api/devices"]
    assert devices["id"] == endpoint_id("api/devices")
    assert devices["source_file"] == "backend/api/urls.py"
    assert devices["metadata"]["http_endpoint"]["origin"] == "backend"

    serves = _serves_edges(first["edges"])
    assert {(e["source"], e["target"]) for e in serves} == {
        (endpoint_id("api/devices"), "backend_api_views_devices"),
        (endpoint_id("api/data"), "backend_api_data_data"),
    }
    for edge in serves:
        assert edge["confidence"] == "EXTRACTED"
        assert edge["source_file"] == "backend/api/urls.py"

    # The re_path endpoint is parked, never served (the interior ^ survives
    # the shared normalizer — regex normalization is out of scope).
    runs = endpoints["api/^runs"]
    assert runs["metadata"]["http_endpoint"]["unresolved_route"] == "api/^runs$"
    assert not any(e.get("source") == runs["id"] for e in first["edges"])

    # The decoy def proves the callee-less stamps never reached the bare-name
    # pass: the urls.py file node has no calls edge at all.
    urls_nid = next(
        n["id"] for n in first["nodes"] if n.get("source_file") == "backend/api/urls.py"
    )
    assert not any(
        e.get("source") == urls_nid and e.get("relation") == "calls" for e in first["edges"]
    )

    second = _extract_with_django(files, cache_root=cache, root=root)
    endpoints2 = _pipeline_endpoints(second)
    assert {key: node["id"] for key, node in endpoints2.items()} == {
        key: node["id"] for key, node in endpoints.items()
    }
    assert len(_serves_edges(second["edges"])) == len(serves)
