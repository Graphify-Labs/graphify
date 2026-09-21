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


def test_bare_python_import_resolves_to_in_repo_file(tmp_path):
    """#2280: Bare module imports (e.g. `import solar_allocator`) used in framework
    layouts like Pyscript must resolve to the in-repo file node instead of dangling."""
    mod = tmp_path / "ha" / "pyscript" / "modules"
    mod.mkdir(parents=True)
    (mod / "__init__.py").write_text("")
    (mod / "solar_allocator.py").write_text("def allocate(): pass\n")
    (mod / "ev_actuator.py").write_text("def actuate(): pass\n")
    (mod / "hws_intent.py").write_text("def intent(): pass\n")
    (mod / "importer.py").write_text(
        "import solar_allocator\n"
        "import ev_actuator\n"
        "import hws_intent\n"
    )

    paths = [
        mod / "__init__.py",
        mod / "solar_allocator.py",
        mod / "ev_actuator.py",
        mod / "hws_intent.py",
        mod / "importer.py",
    ]

    G = build_from_json(extract(paths, cache_root=tmp_path / "c", root=tmp_path, parallel=False), root=str(tmp_path))
    edges = _import_edges(G)

    # Importer must have resolved edges to all 3 in-repo module file nodes
    endpoints = {n for _, u, v in edges for n in (u, v)}
    assert "ha_pyscript_modules_solar_allocator" in endpoints, f"solar_allocator import not resolved: {edges}"
    assert "ha_pyscript_modules_ev_actuator" in endpoints, f"ev_actuator import not resolved: {edges}"
    assert "ha_pyscript_modules_hws_intent" in endpoints, f"hws_intent import not resolved: {edges}"


def test_bare_python_import_external_remains_unresolved(tmp_path):
    """#2280: External imports (e.g. `import requests`) matching no in-repo file stem
    must remain unresolved and be dropped."""
    mod = tmp_path / "app.py"
    mod.write_text("import requests\nimport numpy\n")

    G = build_from_json(extract([mod], cache_root=tmp_path / "c", root=tmp_path, parallel=False), root=str(tmp_path))
    edges = _import_edges(G)
    assert not edges, f"external imports must stay dropped/dangling: {edges}"


def test_bare_python_import_ambiguous_filename_remains_unresolved(tmp_path):
    """#2280: When multiple files share the same stem (e.g. `src/utils.py` and `tests/utils.py`),
    a bare `import utils` resolves to the importable sibling (src/utils.py) but not tests/utils.py."""
    (tmp_path / "src").mkdir()
    (tmp_path / "tests").mkdir()
    (tmp_path / "src" / "utils.py").write_text("def u1(): pass\n")
    (tmp_path / "tests" / "utils.py").write_text("def u2(): pass\n")
    (tmp_path / "src" / "main.py").write_text("import utils\n")

    paths = [tmp_path / "src" / "utils.py", tmp_path / "tests" / "utils.py", tmp_path / "src" / "main.py"]
    G = build_from_json(extract(paths, cache_root=tmp_path / "c", root=tmp_path, parallel=False), root=str(tmp_path))
    edges = _import_edges(G)

    # Under scoped importability rules, main.py imports its sibling src/utils.py,
    # but must NOT import tests/utils.py.
    endpoints = {n for _, u, v in edges for n in (u, v)}
    assert "src_utils" in endpoints, f"sibling utils import was not resolved: {edges}"
    assert "tests_utils" not in endpoints, f"non-sibling utils import was falsely resolved: {edges}"


def test_python_import_mixed_syntaxes(tmp_path):
    """#2280: Verify mixed import syntaxes (bare, relative, package-qualified, external)
    in the same file all resolve correctly per their respective rules."""
    (tmp_path / "mypkg").mkdir()
    (tmp_path / "mypkg" / "__init__.py").write_text("")
    (tmp_path / "mypkg" / "core.py").write_text("class Core: pass\n")
    (tmp_path / "mypkg" / "helpers.py").write_text("def help(): pass\n")
    (tmp_path / "solar_allocator.py").write_text("def alloc(): pass\n")
    (tmp_path / "mypkg" / "app.py").write_text(
        "import solar_allocator\n"
        "import requests\n"
        "from . import helpers\n"
        "import mypkg.core\n"
    )

    paths = [
        tmp_path / "mypkg" / "__init__.py",
        tmp_path / "mypkg" / "core.py",
        tmp_path / "mypkg" / "helpers.py",
        tmp_path / "solar_allocator.py",
        tmp_path / "mypkg" / "app.py",
    ]

    G = build_from_json(extract(paths, cache_root=tmp_path / "c", root=tmp_path, parallel=False), root=str(tmp_path))
    edges = _import_edges(G)
    endpoints = {n for _, u, v in edges for n in (u, v)}

    # 1. Bare import `solar_allocator` -> solar_allocator
    assert "solar_allocator" in endpoints, f"bare import solar_allocator not resolved: {edges}"
    # 2. Package-qualified `mypkg.core` -> mypkg_core
    assert "mypkg_core" in endpoints, f"package-qualified mypkg.core not resolved: {edges}"
    # 3. Relative `from . import helpers` -> mypkg_helpers
    assert "mypkg_helpers" in endpoints, f"relative import helpers not resolved: {edges}"
    # 4. External `requests` -> dropped/dangling (no requests in endpoints)
    assert "requests" not in endpoints, f"external import requests should be dropped: {edges}"

