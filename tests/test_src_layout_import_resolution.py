"""#2072: Python import resolution must not depend on the scan root.

A src-layout project (code under `src/`) used to lose most of its `imports` /
`imports_from` edges when scanned from the repo root, because absolute imports
were resolved only against the scan root while file-node ids are scan-root
relative. The same project scanned from `src/` resolved fine — so the chosen
scan root silently changed the graph.
"""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract
from graphify.extractors.resolution import _resolve_python_module_path
from graphify.build import build_from_json


_FILES = {
    "mypkg/__init__.py": "from mypkg.core import Engine\n",
    "mypkg/core.py": "class Engine:\n    pass\n",
    "mypkg/helpers.py": "def helper():\n    return 1\n",
    "mypkg/app.py": (
        "from mypkg.core import Engine\n"
        "import mypkg.helpers\n\n"
        "def run():\n    return mypkg.helpers.helper()\n"
    ),
}


def _write(base: Path, prefix: str = "") -> list[Path]:
    written = []
    for rel, body in _FILES.items():
        p = base / prefix / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        written.append(p)
    return written


def _import_edges(G):
    """(relation, source, target) for import edges, present-endpoints only."""
    return {
        (d.get("relation"), u, v)
        for u, v, d in G.edges(data=True)
        if d.get("relation") in ("imports", "imports_from")
    }


def test_resolve_python_module_path_walks_up_to_src_package_root(tmp_path):
    (tmp_path / "src" / "mypkg").mkdir(parents=True)
    core = tmp_path / "src" / "mypkg" / "core.py"
    core.write_text("class Engine: pass\n")
    app = tmp_path / "src" / "mypkg" / "app.py"
    app.write_text("from mypkg.core import Engine\n")
    # scan root is the repo, code is under src/: must still resolve.
    resolved = _resolve_python_module_path("mypkg.core", app, tmp_path, level=0)
    assert resolved == core
    # flat layout (package at root) is unchanged.
    (tmp_path / "flat").mkdir()
    (tmp_path / "flat" / "mod.py").write_text("x = 1\n")
    assert _resolve_python_module_path("flat.mod", tmp_path / "flat" / "a.py", tmp_path, 0) == (
        tmp_path / "flat" / "mod.py"
    )


def test_import_edges_identical_from_root_or_src(tmp_path):
    """Headline (#2072): the same project yields the same import edges whether
    scanned from the repo root or from src/ (modulo the `src_` id prefix)."""
    direct = tmp_path / "direct"
    nested = tmp_path / "nested"
    _write(direct)                 # direct/mypkg/...
    _write(nested, prefix="src")   # nested/src/mypkg/...  (byte-identical)

    dpaths = [direct / r for r in _FILES]
    npaths = [nested / "src" / r for r in _FILES]
    dG = build_from_json(extract(dpaths, cache_root=tmp_path / "cd", root=direct, parallel=False), root=str(direct))
    nG = build_from_json(extract(npaths, cache_root=tmp_path / "cn", root=nested, parallel=False), root=str(nested))

    d_edges = _import_edges(dG)
    # strip the `src_` prefix the nested layout adds to every id.
    n_edges = {
        (rel, u[4:] if u.startswith("src_") else u, v[4:] if v.startswith("src_") else v)
        for rel, u, v in _import_edges(nG)
    }
    assert d_edges, "sanity: the flat layout must produce import edges"
    assert n_edges == d_edges, (
        f"scan root changed the import graph (#2072)\n root-only: {d_edges - n_edges}\n src-only: {n_edges - d_edges}"
    )
    # Concretely, in the src layout: app<->core are connected by an import edge
    # (endpoint order is storage-dependent on an undirected graph), and no import
    # endpoint is a bare, unresolved `mypkg_*` id — every target resolved to a
    # real `src_mypkg_*` file/symbol node.
    n_imports = _import_edges(nG)
    assert any({"src_mypkg_app"} <= {u, v} and any(n.startswith("src_mypkg_core") for n in (u, v))
               for _, u, v in n_imports), f"app->core import not resolved: {n_imports}"
    endpoints = {n for _, u, v in n_imports for n in (u, v)}
    assert not any(n.startswith("mypkg_") for n in endpoints), (
        f"unresolved bare import id survived (scan-root-relative mismatch): {endpoints}"
    )


def test_ambiguous_package_alias_is_not_repointed(tmp_path):
    """A dotted-module id claimed by two different files (two src roots with the
    same package) must stay dangling rather than pick an arbitrary file."""
    for sub in ("a", "b"):
        d = tmp_path / sub / "src" / "pkg"
        d.mkdir(parents=True)
        (d / "__init__.py").write_text("")
        (d / "mod.py").write_text("def f():\n    return 1\n")
    (tmp_path / "a" / "src" / "pkg" / "app.py").write_text("import pkg.mod\n")
    paths = [
        tmp_path / "a" / "src" / "pkg" / "app.py",
        tmp_path / "a" / "src" / "pkg" / "mod.py",
        tmp_path / "b" / "src" / "pkg" / "mod.py",
        tmp_path / "a" / "src" / "pkg" / "__init__.py",
        tmp_path / "b" / "src" / "pkg" / "__init__.py",
    ]
    G = build_from_json(extract(paths, cache_root=tmp_path / "c", root=tmp_path, parallel=False), root=str(tmp_path))
    # The ambiguous `pkg_mod` alias claimed by both a/ and b/ must not be
    # repointed onto either file — no fabricated cross-tree import edge.
    imports = _import_edges(G)
    targets = {v for _, _, v in imports}
    # Neither file may be chosen — an ambiguous alias must stay dangling.
    assert "a_src_pkg_mod" not in targets and "b_src_pkg_mod" not in targets, (
        f"ambiguous alias was repointed to a specific file: {imports}"
    )


def test_scan_root_module_wins_over_nested_same_name(tmp_path):
    """A nested duplicate must not shadow the resolver's scan-root-first hit."""
    app_path = tmp_path / "app.py"
    root_module = tmp_path / "pkg.py"
    nested_module = tmp_path / "nested" / "pkg.py"
    app_path.write_text("from pkg import Thing\n", encoding="utf-8")
    root_module.write_text("class Thing:\n    pass\n", encoding="utf-8")
    nested_module.parent.mkdir(parents=True)
    nested_module.write_text("class Thing:\n    pass\n", encoding="utf-8")

    result = extract(
        [app_path, root_module, nested_module],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    app_id = next(
        node["id"] for node in result["nodes"] if node.get("label") == "app.py"
    )
    root_module_id = next(
        node["id"] for node in result["nodes"]
        if node.get("label") == "pkg.py" and node.get("source_file") == "pkg.py"
    )
    nested_module_id = next(
        node["id"] for node in result["nodes"]
        if node.get("label") == "pkg.py" and node.get("source_file") == "nested/pkg.py"
    )
    targets = {
        edge["target"] for edge in result["edges"]
        if edge.get("source") == app_id and edge.get("relation") == "imports_from"
    }

    assert root_module_id in targets
    assert nested_module_id not in targets


def test_ambiguous_absolute_from_import_does_not_bind_symbols_or_calls(tmp_path):
    """An importer-relative hit must not bypass corpus-wide module ambiguity."""
    def write_file(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    paths = []
    for sub in ("a", "b"):
        pkg = tmp_path / sub / "src" / "pkg"
        pkg.mkdir(parents=True)
        paths.append(write_file(pkg / "__init__.py", ""))
        paths.append(write_file(
            pkg / "mod.py",
            "class Thing:\n    pass\n\ndef run():\n    return 1\n",
        ))
    app_path = write_file(
        tmp_path / "a" / "src" / "pkg" / "app.py",
        "from pkg.mod import Thing, run\n\n"
        "def invoke():\n    return Thing(), run()\n",
    )
    paths.append(app_path)

    result = extract(
        paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False
    )

    app = next(
        node["id"] for node in result["nodes"]
        if node.get("label") == "app.py"
    )
    module_targets = {
        node["id"] for node in result["nodes"]
        if node["id"].startswith(("a_src_pkg_mod", "b_src_pkg_mod"))
    }
    app_edges = [
        edge for edge in result["edges"]
        if edge.get("source", "").startswith("a_src_pkg_app")
    ]

    assert any(
        edge.get("source") == app and edge.get("relation") == "imports_from"
        for edge in app_edges
    ), "keep the unresolved import evidence"
    assert not any(
        edge.get("target") in module_targets
        and edge.get("relation") in ("imports", "imports_from", "calls", "uses")
        for edge in app_edges
    ), f"ambiguous module was resolved to one src tree: {app_edges}"


def test_ambiguous_namespace_submodule_does_not_bind_calls(tmp_path):
    """Namespace-package submodule imports must use the same ambiguity guard."""
    def write_file(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    paths = []
    for sub in ("a", "b"):
        paths.append(write_file(
            tmp_path / sub / "src" / "pkg" / "mod.py",
            "def run():\n    return 1\n",
        ))
    app = write_file(
        tmp_path / "a" / "src" / "app.py",
        "from pkg import mod\n\ndef invoke():\n    return mod.run()\n",
    )
    paths.append(app)

    result = extract(
        paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False
    )
    module_targets = {
        node["id"] for node in result["nodes"]
        if node["id"].startswith(("a_src_pkg_mod", "b_src_pkg_mod"))
    }
    app_edges = [
        edge for edge in result["edges"]
        if edge.get("source", "").startswith("a_src_app")
    ]

    assert not any(
        edge.get("target") in module_targets
        and edge.get("relation") in ("imports", "imports_from", "calls", "uses")
        for edge in app_edges
    ), f"namespace submodule was resolved to one src tree: {app_edges}"


def test_ambiguous_star_import_does_not_bind_calls(tmp_path):
    """An ambiguous wildcard import must not enable proximity-based call picks."""
    def write_file(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    paths = []
    for sub in ("a", "b"):
        pkg = tmp_path / sub / "src" / "pkg"
        write_file(pkg / "__init__.py", "")
        paths.append(write_file(
            pkg / "mod.py", "def run():\n    return 1\n"
        ))
    app_path = write_file(
        tmp_path / "a" / "src" / "pkg" / "app.py",
        "from pkg.mod import *\n\ndef invoke():\n    return run()\n",
    )
    paths.append(app_path)

    result = extract(
        paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False
    )
    module_targets = {
        node["id"] for node in result["nodes"]
        if node["id"].startswith(("a_src_pkg_mod", "b_src_pkg_mod"))
    }
    app_edges = [
        edge for edge in result["edges"]
        if edge.get("source", "").startswith("a_src_pkg_app")
    ]

    assert not any(
        edge.get("target") in module_targets
        and edge.get("relation") in ("imports", "imports_from", "calls", "uses")
        for edge in app_edges
    ), f"ambiguous star import resolved to one src tree: {app_edges}"


def test_incremental_ambiguous_import_uses_unchanged_python_context(tmp_path):
    """Unchanged files in resolver context still participate in ambiguity checks."""
    def write_file(path: Path, content: str) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    for sub in ("a", "b"):
        write_file(
            tmp_path / sub / "src" / "pkg" / "mod.py",
            "class Thing:\n    pass\n\ndef run():\n    return 1\n",
        )
    app_path = write_file(
        tmp_path / "a" / "src" / "pkg" / "app.py",
        "from pkg.mod import Thing, run\n\n"
        "def invoke():\n    return Thing(), run()\n",
    )
    context_nodes = []
    for sub in ("a", "b"):
        source_file = f"{sub}/src/pkg/mod.py"
        prefix = f"{sub}_src_pkg_mod"
        context_nodes.extend([
            {"id": prefix, "label": "mod.py", "source_file": source_file,
             "file_type": "code"},
            {"id": f"{prefix}_thing", "label": "Thing",
             "source_file": source_file, "file_type": "code"},
            {"id": f"{prefix}_run", "label": "run()",
             "source_file": source_file, "file_type": "code"},
        ])

    result = extract(
        [app_path], cache_root=tmp_path / "cache", root=tmp_path, parallel=False,
        resolution_context_nodes=context_nodes,
    )
    app_edges = [
        edge for edge in result["edges"]
        if edge.get("source", "").startswith("a_src_pkg_app")
    ]
    module_targets = {
        node["id"] for node in context_nodes
        if "_src_pkg_mod" in node["id"]
    }

    assert not any(
        edge.get("target") in module_targets
        and edge.get("relation") in ("imports", "imports_from", "calls", "uses")
        for edge in app_edges
    ), f"incremental import resolved to one unchanged src tree: {app_edges}"


def test_non_python_import_edge_is_not_repointed(tmp_path):
    """#2072 review: the alias map is Python-only, but a non-Python import edge
    whose dangling target coincides with a Python alias must NOT be repointed
    onto a Python file (that would fabricate a cross-language import)."""
    pkg = tmp_path / "src" / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "mod.py").write_text("def f():\n    return 1\n")
    # Simulate a non-Python (C#) import edge whose target string collides with the
    # Python alias `pkg_mod`, by hand-building the extraction the way extract emits.
    result = extract([pkg / "__init__.py", pkg / "mod.py"], cache_root=tmp_path / "c",
                     root=tmp_path, parallel=False)
    result["nodes"].append(
        {"id": "app_cs", "label": "app.cs", "file_type": "code", "source_file": "app.cs"}
    )
    result["edges"].append(
        {"source": "app_cs", "target": "pkg_mod", "relation": "imports",
         "confidence": "EXTRACTED", "source_file": "app.cs"}
    )
    G = build_from_json(result, root=str(tmp_path))
    # The C# edge's target must remain the (dangling, dropped) `pkg_mod`, never
    # repointed to the Python file node src_pkg_mod.
    assert not any(v == "src_pkg_mod" and u == "app_cs" for _, u, v in _import_edges(G)), (
        "non-Python import edge was repointed onto a Python file (#2072 review)"
    )
