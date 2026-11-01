"""#2072: Python import resolution must not depend on the scan root.

A src-layout project (code under `src/`) used to lose most of its `imports` /
`imports_from` edges when scanned from the repo root, because absolute imports
were resolved only against the scan root while file-node ids are scan-root
relative. The same project scanned from `src/` resolved fine — so the chosen
scan root silently changed the graph.
"""
from __future__ import annotations

import importlib.machinery
import py_compile
import sys
from pathlib import Path

import pytest

from graphify.extract import collect_files, extract
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


# A type named like its package (`flask.Flask`, `shop.Shop`) leaves a
# sourceless annotation stub whose id case-folds to the package alias `shop`.
_STUB_PKG = {
    "src/shop/__init__.py": "from shop.core import Shop\n",
    "src/shop/core.py": "class Shop:\n    def open(self):\n        return 1\n",
}
_STUB_IMPORTERS = {
    "tests/test_plain.py": "import shop\n\n\ndef test_plain(app: shop.Shop):\n    return app\n",
    "tests/test_alias.py": "import shop as s\n\n\ndef test_alias(app: s.Shop):\n    return app\n",
    "tests/test_from.py": "from shop import Shop\n\n\ndef test_from(app: Shop):\n    return app\n",
}


def _extract_files(tmp_path: Path, files: dict[str, str]) -> dict:
    paths = []
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)
    return extract(paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False)


def _module_import_targets(result: dict, importer: str) -> set[str]:
    return {
        e["target"] for e in result["edges"]
        if e.get("source") == importer and e.get("relation") in ("imports", "imports_from")
    }


@pytest.mark.parametrize(
    "importers",
    [["tests/test_plain.py"], list(_STUB_IMPORTERS)],
    ids=["one-importer", "colliding-stubs"],
)
def test_package_import_is_not_blocked_by_same_named_type_stub(tmp_path, importers):
    """A sourceless `Shop` type stub must not keep `import shop` off the scanned
    src/shop/__init__.py. With one importer the stub was rewired onto the class
    and dragged the import edge with it; with several, each file's import bound
    to its own stub or dangled as an external `shop` module."""
    files = {**_STUB_PKG, **{rel: _STUB_IMPORTERS[rel] for rel in importers}}
    result = _extract_files(tmp_path, files)
    G = build_from_json(result, root=str(tmp_path))

    for rel in importers:
        importer = rel[: -len(".py")].replace("/", "_")
        assert "src_shop_init" in _module_import_targets(result, importer), (
            f"{rel}: package import did not reach src/shop/__init__.py: "
            f"{_module_import_targets(result, importer)}"
        )
        built = {
            G.nodes.get(e["target"], {}).get("source_file")
            for e in result["edges"]
            if e.get("source_file") == rel and e.get("relation") in ("imports", "imports_from")
        }
        assert "src/shop/__init__.py" in built, f"{rel}: built graph targets {built}"
    # The annotation stub keeps its own resolution: it names the class, never the package.
    refs = {e["target"] for e in result["edges"] if e.get("relation") == "references"}
    assert "src_shop_core_shop" in refs
    assert "src_shop_init" not in refs


def test_source_backed_node_still_owns_package_alias(tmp_path):
    """A real node with the alias id keeps the import (#2072 guard): the resolver
    binds `import shop` to the scan-root shop.py before any src/ package."""
    files = {
        **_STUB_PKG,
        "shop.py": "class Shop:\n    pass\n",
        "tests/test_plain.py": _STUB_IMPORTERS["tests/test_plain.py"],
    }
    result = _extract_files(tmp_path, files)

    # The colliding-id pass may salt the file node's id, so find it by file.
    root_module = next(
        n["id"] for n in result["nodes"]
        if n.get("source_file") == "shop.py" and n.get("label") == "shop.py"
    )
    targets = _module_import_targets(result, "tests_test_plain")
    assert root_module in targets
    assert "src_shop_init" not in targets


def test_unresolved_import_keeps_v8_result_when_real_node_owns_alias_id(tmp_path):
    """No resolver pick here (shop.js is not a Python module), but the shop.js
    file node is real and holds the id `shop`, so the stub exception is off."""
    files = {
        **_STUB_PKG,
        "shop.js": "export function open() { return 1; }\n",
        "tests/test_plain.py": _STUB_IMPORTERS["tests/test_plain.py"],
    }
    result = _extract_files(tmp_path, files)

    assert "src_shop_init" not in _module_import_targets(result, "tests_test_plain")


def test_stub_shadowed_alias_claimed_by_two_packages_is_not_repointed(tmp_path):
    files = {"tests/test_plain.py": _STUB_IMPORTERS["tests/test_plain.py"]}
    for sub in ("a", "b"):
        for rel, body in _STUB_PKG.items():
            files[f"{sub}/{rel}"] = body
    result = _extract_files(tmp_path, files)

    targets = _module_import_targets(result, "tests_test_plain")
    assert not targets & {"a_src_shop_init", "b_src_shop_init"}, targets


def test_stub_shadowed_alias_requires_exact_module_spelling(tmp_path):
    """`import Shop` folds to the same id as package `shop`, but Python module
    names are case-sensitive. Next to a stub, only the exact spelling repoints."""
    files = {
        **_STUB_PKG,
        "tests/test_case.py": "import Shop\n\n\ndef test_case(app: Shop.Shop):\n    return app\n",
    }
    result = _extract_files(tmp_path, files)

    assert "src_shop_init" not in _module_import_targets(result, "tests_test_case")


def _built_import_sources(
    tmp_path: Path, files: dict[str, str], importer: str, unscanned: tuple[str, ...] = (),
) -> list[tuple[str, str | None]]:
    """(target, target source_file) of the importer's import edges in the built graph."""
    paths = []
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        if rel not in unscanned:
            paths.append(p)
    result = extract(paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False)
    G = build_from_json(result, root=str(tmp_path))
    return [
        (e["target"], G.nodes.get(e["target"], {}).get("source_file"))
        for e in result["edges"]
        if e.get("source_file") == importer and e.get("relation") in ("imports", "imports_from")
    ]


def test_stub_shadowed_alias_keeps_resolved_target_file(tmp_path):
    """The resolver bound `import shop` to the scan-root shop.py (not in this
    scan). A nested package with the same name must not replace that choice."""
    files = {
        "shop.py": "class Root:\n    pass\n",
        "src/shop/__init__.py": "class Nested:\n    pass\n",
        "tests/app.py": "import shop\n\n\ndef f(app: shop.Shop):\n    return app\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py", unscanned=("shop.py",))

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/__init__.py" for _, sf in targets), targets


def test_stub_shadowed_alias_does_not_bind_colliding_destination_id(tmp_path):
    """src/shop/__init__.py and src/shop/__init__.h share the file id
    `src_shop_init`; the colliding-id pass would hand the edge to the header."""
    files = {
        "src/shop/__init__.py": "class Nested:\n    pass\n",
        "src/shop/__init__.h": "struct Other { int x; };\n",
        "tests/app.py": "import shop\n\n\ndef f(app: shop.Shop):\n    return app\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/__init__.h" for _, sf in targets), targets


def test_stub_shadowed_alias_rejects_dotted_directory_name(tmp_path):
    """`import shop.v2` names package `shop`, submodule `v2`, never a literal
    `shop.v2/` directory."""
    files = {
        "src/shop.v2/__init__.py": "class Other:\n    pass\n",
        "tests/app.py": "import shop.v2\n\n\ndef f(app: Shop_v2):\n    return app\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop.v2/__init__.py" for _, sf in targets), targets


@pytest.mark.parametrize(
    "files, unimportable",
    [
        (
            {
                "src/pkg/__init__.py": "",
                "src/pkg/shop.PY": "class Other:\n    pass\n",
                "tests/app.py": "import pkg.shop\n\n\ndef f(x: Pkg_shop):\n    return x\n",
            },
            "src/pkg/shop.PY",
        ),
        (
            # U+212A KELVIN SIGN. Python NFKC-normalizes the imported name to
            # ASCII `K`, so this directory never satisfies the import.
            {
                "src/\u212a/__init__.py": "class Other:\n    pass\n",
                "tests/app.py": "import \u212a\n\n\ndef f(x: K):\n    return x\n",
            },
            "src/\u212a/__init__.py",
        ),
    ],
    ids=["uppercase-suffix", "kelvin-sign-directory"],
)
def test_stub_shadowed_alias_skips_files_python_cannot_import(tmp_path, files, unimportable):
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert targets, "sanity: the import edge must exist"
    assert all(sf != unimportable for _, sf in targets), targets


def test_stub_shadowed_alias_compares_nfkc_normalized_import_name(tmp_path):
    """`import \u212a` (Kelvin sign) imports the ASCII package `K`."""
    files = {
        "src/K/__init__.py": "class Other:\n    pass\n",
        "tests/app.py": "import \u212a\n\n\ndef f(x: K):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert ("src_k_init", "src/K/__init__.py") in targets, targets


@pytest.mark.parametrize("statement", ["import \u212a", "from \u212a import Root"], ids=["import", "from-import"])
@pytest.mark.parametrize("root_module", ["K.py", "K/__init__.py"], ids=["root-module", "root-package"])
def test_stub_shadowed_alias_keeps_scan_root_precedence(tmp_path, statement, root_module):
    """Python reads `\u212a` as ASCII `K`, so the unscanned scan-root K.py or
    K/ is imported first. The resolver probed only the raw spelling and stamped
    nothing; the src/ package must not take the edge."""
    files = {
        root_module: "class Root:\n    pass\n",
        "src/K/__init__.py": "class Nested:\n    pass\n",
        "tests/app.py": f"{statement}\n\n\ndef f(x: K):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py", unscanned=(root_module,))

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/K/__init__.py" for _, sf in targets), targets


@pytest.mark.parametrize(
    "shadow", ["shop.py", "tests/shop.py"], ids=["scan-root", "importer-sys-path-root"],
)
def test_stub_shadowed_alias_respects_a_shadowing_parent_module(tmp_path, shadow):
    """A `shop` module found before src/ (at the scan root, or in the importer's
    own sys.path root) has no submodule `core`, so `import shop.core` never
    reaches src/shop/core.py."""
    files = {
        shadow: "class Root:\n    pass\n",
        "src/shop/__init__.py": "class Nested:\n    pass\n",
        "src/shop/core.py": "class Core:\n    pass\n",
        "tests/app.py": "import shop.core\n\n\ndef f(x: Shop_core):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/core.py" for _, sf in targets), targets


def test_stub_shadowed_alias_is_not_shadowed_by_its_own_sys_path_root(tmp_path):
    """src/ holds the candidate package itself, so it does not shadow it: an
    importer in src/tools/ still resolves `import \u212a` to src/K. (An
    importer directly in src/ is handled by the sibling-import pass, #3430.)"""
    files = {
        "src/K/__init__.py": "class Other:\n    pass\n",
        "src/tools/app.py": "import \u212a\n\n\ndef f(x: K):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "src/tools/app.py")

    assert ("src_k_init", "src/K/__init__.py") in targets, targets


def test_stub_shadowed_alias_checks_the_disk_in_its_own_tree(tmp_path):
    """Python loads the package src/shop/core/ ahead of src/shop/core.py. The
    package is excluded by .graphifyignore, so only the disk shows it."""
    files = {
        ".graphifyignore": "src/shop/core/\n",
        "src/shop/__init__.py": "class Shop:\n    pass\n",
        "src/shop/core.py": "class Core:\n    pass\n",
        "src/shop/core/__init__.py": "class Actual:\n    pass\n",
        "tests/app.py": "import shop.core\n\n\ndef f(x: Shop_core):\n    return x\n",
    }
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    paths = collect_files(tmp_path)
    assert tmp_path / "src/shop/core/__init__.py" not in paths, "sanity: the package is ignored"
    result = extract(paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False)
    G = build_from_json(result, root=str(tmp_path))
    targets = [
        (e["target"], G.nodes.get(e["target"], {}).get("source_file"))
        for e in result["edges"]
        if e.get("source_file") == "tests/app.py" and e.get("relation") in ("imports", "imports_from")
    ]

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/core.py" for _, sf in targets), targets


@pytest.mark.parametrize(
    "competitor",
    ["src/shop/core.abi3.so", "src/shop.py"],
    ids=["extension-ahead-of-source", "module-beside-package-on-the-path"],
)
def test_stub_shadowed_alias_refuses_an_unscanned_competitor_in_its_own_tree(tmp_path, competitor):
    """An extension module is loaded before src/shop/core.py. A module beside
    the package directory `shop/` is refused too, although Python would load
    the package: the rule fails closed when both exist."""
    files = {
        competitor: "",
        "src/shop/__init__.py": "class Shop:\n    pass\n",
        "src/shop/core.py": "class Core:\n    pass\n",
        "tests/app.py": "import shop.core\n\n\ndef f(x: Shop_core):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py", unscanned=(competitor,))

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/core.py" for _, sf in targets), targets


def test_stub_shadowed_alias_ignores_a_pyi_whose_runtime_module_exists(tmp_path):
    """The unscanned src/shop/core.py is what Python imports, not core.pyi."""
    files = {
        "src/shop/__init__.py": "class Shop:\n    pass\n",
        "src/shop/core.pyi": "class Core: ...\n",
        "src/shop/core.py": "class Actual:\n    pass\n",
        "tests/app.py": "import shop.core\n\n\ndef f(x: Shop_core):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py", unscanned=("src/shop/core.py",))

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/core.pyi" for _, sf in targets), targets


@pytest.mark.parametrize(
    "module", ["shop.pyc", "shop.cpython-310-x86_64-linux-gnu.so", "shop.cp312-win_amd64.pyd"],
)
def test_stub_shadowed_alias_respects_sourceless_modules_at_scan_root(tmp_path, module):
    """A scan-root shop.pyc (sourceless bytecode) or extension module is found
    before src/shop/ for `import shop`. Extension names are matched by pattern,
    so a Windows `.pyd` counts on Linux too."""
    if module == "shop.pyc":
        source = tmp_path / "shop.py"
        source.write_text("class Actual:\n    pass\n", encoding="utf-8")
        py_compile.compile(str(source), cfile=str(tmp_path / "shop.pyc"), doraise=True)
        source.unlink()
    else:
        (tmp_path / module).write_bytes(b"")
    files = {
        "src/shop/__init__.py": "class Nested:\n    pass\n",
        "tests/app.py": "import shop\n\n\ndef f(x: Shop):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert targets, "sanity: the import edge must exist"
    assert all(sf != "src/shop/__init__.py" for _, sf in targets), targets


@pytest.mark.parametrize("unreadable", ["scan-root", "own-sys-path-root"])
def test_stub_shadowed_alias_refuses_when_a_directory_cannot_be_listed(tmp_path, monkeypatch, unreadable):
    """A listing error is not an empty directory. With the scan root unreadable
    the unscanned K.py cannot be ruled out; with src/ unreadable the
    candidate's own tree cannot be checked."""
    if unreadable == "scan-root":
        files = {
            "K.py": "class Root:\n    pass\n",
            "src/K/__init__.py": "class Other:\n    pass\n",
            "tests/app.py": "import \u212a\n\n\ndef f(x: K):\n    return x\n",
        }
        unscanned, denied, wrong = ("K.py",), tmp_path, "src/K/__init__.py"
    else:
        files = {**_STUB_PKG, "tests/app.py": _STUB_IMPORTERS["tests/test_plain.py"]}
        unscanned, denied, wrong = (), tmp_path / "src", "src/shop/__init__.py"
    iterdir = Path.iterdir

    def deny(self):
        if self == denied:
            raise PermissionError("directory is searchable but not readable")
        return iterdir(self)

    monkeypatch.setattr(Path, "iterdir", deny)
    targets = _built_import_sources(tmp_path, files, "tests/app.py", unscanned=unscanned)

    assert targets, "sanity: the import edge must exist"
    assert all(sf != wrong for _, sf in targets), targets


def test_stub_shadowed_alias_does_not_depend_on_the_host_extension_suffixes(tmp_path, monkeypatch):
    """The same corpus must give the same graph whichever Python runs graphify:
    shop.cpython-310-...so is a competitor under 3.13's suffix list as well."""
    (tmp_path / "shop.cpython-310-x86_64-linux-gnu.so").write_bytes(b"")
    files = {
        "src/shop/__init__.py": "class Nested:\n    pass\n",
        "tests/app.py": "import shop\n\n\ndef f(x: Shop):\n    return x\n",
    }
    paths = []
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)

    graphs = []
    for suffixes in (
        [".cpython-313-x86_64-linux-gnu.so", ".abi3.so", ".so"],
        [".cpython-310-x86_64-linux-gnu.so", ".abi3.so", ".so"],
    ):
        monkeypatch.setattr(importlib.machinery, "EXTENSION_SUFFIXES", suffixes)
        result = extract(paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False)
        G = build_from_json(result, root=str(tmp_path))
        graphs.append((
            sorted(G.nodes),
            sorted((e["source"], e["relation"], e["target"]) for e in result["edges"]),
            [G.nodes.get(e["target"], {}).get("source_file") for e in result["edges"]
             if e.get("source_file") == "tests/app.py" and e.get("relation") == "imports"],
        ))

    assert graphs[0] == graphs[1]
    assert graphs[0][2] and "src/shop/__init__.py" not in graphs[0][2], graphs[0][2]


@pytest.mark.parametrize("module", ["sys", "os", "time", "tomllib", "distutils"])
def test_stub_shadowed_alias_never_binds_a_standard_library_name(tmp_path, module):
    """`import sys` (built-in), `import os` (frozen) and `import time` always
    load the interpreter's own module, never a local src/<name>/ package.
    `tomllib` (stdlib from 3.11) and `distutils` (removed in 3.12) are refused
    on every host, because graphify carries its own superset of the names."""
    files = {
        f"src/{module}/__init__.py": "class Other:\n    pass\n",
        "tests/app.py": f"import {module}\n\n\ndef f(x: {module.title()}):\n    return x\n",
    }
    targets = _built_import_sources(tmp_path, files, "tests/app.py")

    assert targets, "sanity: the import edge must exist"
    assert all(sf != f"src/{module}/__init__.py" for _, sf in targets), targets


def test_stub_shadowed_alias_does_not_depend_on_the_host_stdlib_names(tmp_path, monkeypatch):
    """The same corpus gives the same graph whatever the running interpreter
    lists as stdlib or built-in: graphify uses its own fixed list."""
    files = {
        "src/time/__init__.py": "class Other:\n    pass\n",
        "tests/app.py": "import time\n\n\ndef f(x: Time):\n    return x\n",
    }
    paths = []
    for rel, body in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
        paths.append(p)

    graphs = []
    for stdlib, builtin in ((frozenset(), ()), (frozenset({"time"}), ("time",))):
        monkeypatch.setattr(sys, "stdlib_module_names", stdlib)
        monkeypatch.setattr(sys, "builtin_module_names", builtin)
        result = extract(paths, cache_root=tmp_path / "cache", root=tmp_path, parallel=False)
        G = build_from_json(result, root=str(tmp_path))
        graphs.append((
            sorted(G.nodes),
            sorted((e["source"], e["relation"], e["target"]) for e in result["edges"]),
            [G.nodes.get(e["target"], {}).get("source_file") for e in result["edges"]
             if e.get("source_file") == "tests/app.py" and e.get("relation") == "imports"],
        ))

    assert graphs[0] == graphs[1]
    assert graphs[0][2] and "src/time/__init__.py" not in graphs[0][2], graphs[0][2]
