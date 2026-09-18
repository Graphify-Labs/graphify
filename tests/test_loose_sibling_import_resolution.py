"""Regression tests for Graphify issue #3430:
Loose/namespace-style sibling module imports below scan root.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import _file_node_id, _repoint_python_sibling_imports, extract


def _edge_set(G):
    """Return set of (relation, source, target) from G."""
    return {
        (d.get("relation"), d.get("_src", u), d.get("_tgt", v))
        for u, v, d in G.edges(data=True)
    }


def test_primary_regression_loose_sibling_import_and_call(tmp_path):
    """A. Primary regression:
    repo/scripts/greeter.py + repo/scripts/main.py with:
    import greeter
    greeter.greet()
    Extract from repo root and assert:
    scripts_main imports scripts_greeter
    scripts_main_run calls scripts_greeter_greet
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "greeter.py").write_text("def greet():\n    return 42\n", encoding="utf-8")
    (scripts / "main.py").write_text(
        "import greeter\n\n"
        "def run():\n"
        "    return greeter.greet()\n",
        encoding="utf-8",
    )

    paths = [scripts / "greeter.py", scripts / "main.py"]
    res = extract(paths, root=tmp_path, parallel=False)
    G = build_from_json(res, root=str(tmp_path), directed=True)

    edges = _edge_set(G)
    assert ("imports", "scripts_main", "scripts_greeter") in edges, (
        f"scripts_main -> scripts_greeter import edge missing: {edges}"
    )
    assert ("calls", "scripts_main_run", "scripts_greeter_greet") in edges, (
        f"scripts_main_run -> scripts_greeter_greet calls edge missing: {edges}"
    )


def test_scan_root_parity(tmp_path):
    """B. Scan-root parity:
    Extract the same two files with scripts/ as the root and verify the
    equivalent unprefixed graph still resolves correctly and is isomorphic.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "greeter.py").write_text("def greet():\n    return 42\n", encoding="utf-8")
    (scripts / "main.py").write_text(
        "import greeter\n\n"
        "def run():\n"
        "    return greeter.greet()\n",
        encoding="utf-8",
    )

    paths = [scripts / "greeter.py", scripts / "main.py"]

    # Scan from repo root
    root_res = extract(paths, root=tmp_path, parallel=False)
    root_G = build_from_json(root_res, root=str(tmp_path), directed=True)

    # Scan from scripts/ root
    scripts_res = extract(paths, root=scripts, parallel=False)
    scripts_G = build_from_json(scripts_res, root=str(scripts), directed=True)

    scripts_edges = _edge_set(scripts_G)
    assert ("imports", "main", "greeter") in scripts_edges
    assert ("calls", "main_run", "greeter_greet") in scripts_edges

    # Map root_edges to stripped prefix forms
    stripped_root_edges = {
        (
            rel,
            src[8:] if src.startswith("scripts_") else src,
            tgt[8:] if tgt.startswith("scripts_") else tgt,
        )
        for rel, src, tgt in _edge_set(root_G)
    }
    assert stripped_root_edges == scripts_edges, (
        f"Parity mismatch between scan roots:\n"
        f"Root-scanned (stripped): {stripped_root_edges}\n"
        f"Scripts-scanned: {scripts_edges}"
    )


def test_same_name_modules_in_separate_loose_directories(tmp_path):
    """C. Same-name modules in separate loose directories:
    scripts/helper.py + scripts/main.py
    tools/helper.py + tools/main.py
    Each importer must resolve only to its own directory's helper.
    """
    scripts = tmp_path / "scripts"
    tools = tmp_path / "tools"
    scripts.mkdir(parents=True)
    tools.mkdir(parents=True)

    (scripts / "helper.py").write_text("def work():\n    return 'scripts'\n", encoding="utf-8")
    (scripts / "main.py").write_text(
        "import helper\n\n"
        "def run():\n"
        "    return helper.work()\n",
        encoding="utf-8",
    )

    (tools / "helper.py").write_text("def work():\n    return 'tools'\n", encoding="utf-8")
    (tools / "main.py").write_text(
        "import helper\n\n"
        "def run():\n"
        "    return helper.work()\n",
        encoding="utf-8",
    )

    paths = [
        scripts / "helper.py",
        scripts / "main.py",
        tools / "helper.py",
        tools / "main.py",
    ]
    res = extract(paths, root=tmp_path, parallel=False)
    G = build_from_json(res, root=str(tmp_path), directed=True)

    edges = _edge_set(G)
    # scripts resolution
    assert ("imports", "scripts_main", "scripts_helper") in edges
    assert ("calls", "scripts_main_run", "scripts_helper_work") in edges
    assert ("imports", "scripts_main", "tools_helper") not in edges
    assert ("calls", "scripts_main_run", "tools_helper_work") not in edges

    # tools resolution
    assert ("imports", "tools_main", "tools_helper") in edges
    assert ("calls", "tools_main_run", "tools_helper_work") in edges
    assert ("imports", "tools_main", "scripts_helper") not in edges
    assert ("calls", "tools_main_run", "scripts_helper_work") not in edges


def test_package_isolation_pep328(tmp_path):
    """D. Package isolation:
    pkg/__init__.py + pkg/helper.py + pkg/app.py with `import helper`
    Verify the new loose-sibling pass does NOT repoint this package import.
    """
    pkg = tmp_path / "pkg"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    (pkg / "helper.py").write_text("def work():\n    return 1\n", encoding="utf-8")
    (pkg / "app.py").write_text(
        "import helper\n\n"
        "def run():\n"
        "    return helper.work()\n",
        encoding="utf-8",
    )

    paths = [pkg / "__init__.py", pkg / "helper.py", pkg / "app.py"]
    res = extract(paths, root=tmp_path, parallel=False)

    # In extract result, pkg_app's import must NOT be repointed to pkg_helper
    import_edges = [
        e for e in res["edges"]
        if e.get("source") == "pkg_app" and e.get("relation") == "imports"
    ]
    assert len(import_edges) == 1
    assert import_edges[0]["target"] == "helper", (
        f"Package import in pkg/app.py was falsely repointed to sibling pkg_helper: {import_edges[0]}"
    )

    # No member call was resolved (package isolation)
    call_edges = [e for e in res["edges"] if e.get("relation") == "calls"]
    assert not call_edges, f"Spurious call edge resolved inside package: {call_edges}"


def test_no_cross_directory_leakage(tmp_path):
    """E. No cross-directory leakage:
    scripts/utils.py + src/app.py with `import utils`
    Verify src/app.py does not acquire an import/call relationship to scripts/utils.py.
    """
    scripts = tmp_path / "scripts"
    src = tmp_path / "src"
    scripts.mkdir(parents=True)
    src.mkdir(parents=True)

    (scripts / "utils.py").write_text("def helper():\n    return 'util'\n", encoding="utf-8")
    (src / "app.py").write_text(
        "import utils\n\n"
        "def run():\n"
        "    return utils.helper()\n",
        encoding="utf-8",
    )

    paths = [scripts / "utils.py", src / "app.py"]
    res = extract(paths, root=tmp_path, parallel=False)

    # In extract result, src_app's import must NOT be repointed to scripts_utils
    import_edges = [
        e for e in res["edges"]
        if e.get("source") == "src_app" and e.get("relation") == "imports"
    ]
    assert len(import_edges) == 1
    assert import_edges[0]["target"] == "utils", (
        f"Unrelated src/app.py import was leaked to scripts_utils: {import_edges[0]}"
    )

    # No member call resolved
    call_edges = [
        e for e in res["edges"]
        if e.get("source") == "src_app_run" and e.get("relation") == "calls"
    ]
    assert not call_edges, f"Spurious cross-directory call edge resolved: {call_edges}"


def test_aliased_import_resolves_member_call(tmp_path):
    """F. Aliased import:
    scripts/greeter.py + scripts/main.py with:
    import greeter as g
    g.greet()
    Verify the calls edge resolves to scripts_greeter_greet and the
    import alias metadata remains intact during repointing.
    """
    scripts = tmp_path / "scripts"
    scripts.mkdir(parents=True)
    (scripts / "greeter.py").write_text("def greet():\n    return 42\n", encoding="utf-8")
    (scripts / "main.py").write_text(
        "import greeter as g\n\n"
        "def run():\n"
        "    return g.greet()\n",
        encoding="utf-8",
    )

    paths = [scripts / "greeter.py", scripts / "main.py"]

    # Verify directly on _repoint_python_sibling_imports that local_alias is preserved
    all_nodes = [
        {"id": "scripts_greeter", "source_file": str(scripts / "greeter.py")},
        {"id": "scripts_main", "source_file": str(scripts / "main.py")},
    ]
    edge = {
        "source": "scripts_main",
        "target": "greeter",
        "relation": "imports",
        "source_file": str(scripts / "main.py"),
        "local_alias": "g",
    }
    all_edges = [edge]
    _repoint_python_sibling_imports(paths, all_nodes, all_edges, root=tmp_path)

    assert edge["target"] == "scripts_greeter"
    assert edge["local_alias"] == "g", "local_alias metadata must remain intact after repointing"

    # Full extraction pipeline verify
    res = extract(paths, root=tmp_path, parallel=False)
    G = build_from_json(res, root=str(tmp_path), directed=True)
    edges = _edge_set(G)
    assert ("imports", "scripts_main", "scripts_greeter") in edges
    assert ("calls", "scripts_main_run", "scripts_greeter_greet") in edges
