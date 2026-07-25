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
from graphify.diagnostics import diagnose_extraction


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


def _write_file(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1
    return matches[0]


def _has_edge(result: dict, source: str, target: str, relation: str) -> bool:
    return any(
        edge.get("source") == source
        and edge.get("target") == target
        and edge.get("relation") == relation
        for edge in result["edges"]
    )


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
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='ambiguous'\nversion='1'\n"
    )
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


def test_namespace_package_import_resolves_without_init_file(tmp_path):
    project = tmp_path / "api"
    project.mkdir()
    (project / "pyproject.toml").write_text("[project]\nname='api'\nversion='1'\n")
    model = _write_file(project / "src/models/base.py", "class Base:\n    pass\n")
    service = _write_file(
        project / "src/services/use.py", "from models.base import Base\n"
    )

    result = extract(
        [model, service],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    model_id = _node_id(result, "base.py", "api/src/models/base.py")
    service_id = _node_id(result, "use.py", "api/src/services/use.py")

    assert _has_edge(result, service_id, model_id, "imports_from")
    summary = diagnose_extraction(result, root=tmp_path)
    assert summary["unresolved_internal_endpoint_edges"] == 0


def test_same_module_name_resolves_inside_each_monorepo_workspace(tmp_path):
    paths = []
    expected = []
    for project_name in ("alpha", "beta"):
        project = tmp_path / project_name
        (project / "pyproject.toml").parent.mkdir(parents=True, exist_ok=True)
        (project / "pyproject.toml").write_text(
            f"[project]\nname='{project_name}'\nversion='1'\n"
        )
        model = _write_file(
            project / "src/models/base.py",
            f"class {project_name.title()}Base:\n    pass\n",
        )
        service = _write_file(
            project / "src/services/use.py", "import models.base\n"
        )
        paths.extend((model, service))
        expected.append((project_name, model, service))

    result = extract(
        paths,
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    for project_name, _, _ in expected:
        model_id = _node_id(
            result, "base.py", f"{project_name}/src/models/base.py"
        )
        service_id = _node_id(
            result, "use.py", f"{project_name}/src/services/use.py"
        )
        assert _has_edge(result, service_id, model_id, "imports")


def test_project_without_manifest_uses_first_scan_root_directory(tmp_path):
    model = _write_file(
        tmp_path / "legacy/src/models/base.py", "class Base:\n    pass\n"
    )
    service = _write_file(
        tmp_path / "legacy/src/app.py", "from models.base import Base\n"
    )

    result = extract(
        [model, service],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )

    assert _has_edge(
        result,
        _node_id(result, "app.py", "legacy/src/app.py"),
        _node_id(result, "base.py", "legacy/src/models/base.py"),
        "imports_from",
    )


def test_python_stub_module_and_external_import_are_classified(tmp_path):
    project = tmp_path / "typed"
    (project / "pyproject.toml").parent.mkdir(parents=True, exist_ok=True)
    (project / "pyproject.toml").write_text("[project]\nname='typed'\nversion='1'\n")
    stub = _write_file(
        project / "src/contracts/types.pyi", "class Payload: ...\n"
    )
    consumer = _write_file(
        project / "src/app.py",
        "from contracts.types import Payload\n"
        "import pathlib\n"
        "import third_party_sdk\n",
    )

    result = extract(
        [stub, consumer],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    assert _has_edge(
        result,
        _node_id(result, "app.py", "typed/src/app.py"),
        _node_id(result, "types.pyi", "typed/src/contracts/types.pyi"),
        "imports_from",
    )
    external = [
        edge for edge in result["edges"]
        if edge.get("target") in {"pathlib", "third_party_sdk"}
    ]
    assert len(external) == 2
    assert all(edge.get("external") is True for edge in external)
    summary = diagnose_extraction(result, root=tmp_path)
    assert summary["external_endpoint_edges"] == 2
    assert summary["unresolved_internal_endpoint_edges"] == 0
    assert summary["unclassified_endpoint_edges"] == 0


def test_unresolved_relative_import_is_internal_not_external(tmp_path):
    source = _write_file(
        tmp_path / "pkg/__init__.py", "from .missing import value\n"
    )

    result = extract(
        [source],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )
    edge = next(e for e in result["edges"] if e["relation"] == "imports_from")
    assert edge.get("unresolved_internal") is True
    assert edge.get("external") is not True


def test_imported_symbol_disambiguates_stale_relative_module_path(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='moved-models'\nversion='1'\n"
    )
    wrong = _write_file(
        tmp_path / "models/legacy/scenario.py",
        "class OtherScenario:\n    pass\n",
    )
    intended = _write_file(
        tmp_path / "models/scenario/scenario.py",
        "class Scenario:\n    pass\n",
    )
    consumer = _write_file(
        tmp_path / "models/node/node.py",
        "from .scenario import Scenario\n",
    )

    result = extract(
        [wrong, intended, consumer],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )

    assert _has_edge(
        result,
        _node_id(result, "node.py", "models/node/node.py"),
        _node_id(result, "scenario.py", "models/scenario/scenario.py"),
        "imports_from",
    )


def test_imported_symbol_disambiguates_absolute_package_facade(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        "[project]\nname='facades'\nversion='1'\n"
    )
    alpha = _write_file(
        tmp_path / "alpha/models/__init__.py",
        "from .entity import Alpha\n",
    )
    alpha_entity = _write_file(
        tmp_path / "alpha/models/entity.py",
        "class Alpha:\n    pass\n",
    )
    beta = _write_file(
        tmp_path / "beta/models/__init__.py",
        "from .entity import Beta\n",
    )
    beta_entity = _write_file(
        tmp_path / "beta/models/entity.py",
        "class Beta:\n    pass\n",
    )
    consumer = _write_file(
        tmp_path / "consumer.py",
        "from models import Beta\n",
    )

    result = extract(
        [alpha, alpha_entity, beta, beta_entity, consumer],
        cache_root=tmp_path / "cache",
        root=tmp_path,
        parallel=False,
    )

    assert _has_edge(
        result,
        _node_id(result, "consumer.py", "consumer.py"),
        "beta_models_init",
        "imports_from",
    )
