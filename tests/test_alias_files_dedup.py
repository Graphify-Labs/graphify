"""Tests for Python absolute import alias resolution deduplication optimization."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import patch
import traceback
import pytest

from graphify.extract import (
    extract,
    _python_absolute_import_alias_files,
)
import graphify.extract as ext


def test_alias_files_deduplicates_identical_paths(tmp_path: Path):
    """Duplicate paths in _python_absolute_import_alias_files should only be processed once."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    mod_file = pkg_dir / "mod.py"
    mod_file.write_text("def foo(): return 42\n", encoding="utf-8")

    # Pass 10 duplicate Path objects and str objects
    duplicate_paths = [mod_file] * 5 + [str(mod_file)] * 5

    orig_probe = ext._probe_python_module_candidate
    probe_calls = []

    def tracking_probe(candidate):
        probe_calls.append(candidate)
        return orig_probe(candidate)

    with patch("graphify.extract._probe_python_module_candidate", side_effect=tracking_probe):
        aliases_dup, scan_root_dup = _python_absolute_import_alias_files(duplicate_paths, tmp_path)

    probe_count_dup = len(probe_calls)

    # Now run with a single path
    probe_calls.clear()
    with patch("graphify.extract._probe_python_module_candidate", side_effect=tracking_probe):
        aliases_single, scan_root_single = _python_absolute_import_alias_files([mod_file], tmp_path)

    probe_count_single = len(probe_calls)

    assert aliases_dup == aliases_single
    assert scan_root_dup == scan_root_single
    # Probe calls for 10 duplicate paths must match the probe calls for a single path!
    assert probe_count_dup == probe_count_single


def test_alias_files_deduplicates_relative_and_absolute_paths(tmp_path: Path):
    """Relative and absolute paths pointing to the same file should resolve to the same canonical path and deduplicate."""
    pkg_dir = tmp_path / "pkg"
    pkg_dir.mkdir()
    (pkg_dir / "__init__.py").write_text("", encoding="utf-8")
    mod_file = pkg_dir / "service.py"
    mod_file.write_text("class Service: pass\n", encoding="utf-8")

    rel_path = Path("pkg/service.py")
    abs_path = mod_file.resolve()

    orig_probe = ext._probe_python_module_candidate
    probe_calls = []

    def tracking_probe(candidate):
        probe_calls.append(candidate)
        return orig_probe(candidate)

    # Running from root directory:
    with patch("graphify.extract._probe_python_module_candidate", side_effect=tracking_probe):
        aliases, scan_root = _python_absolute_import_alias_files([rel_path, abs_path, str(rel_path), str(abs_path)], tmp_path)

    probe_count_mixed = len(probe_calls)

    probe_calls.clear()
    with patch("graphify.extract._probe_python_module_candidate", side_effect=tracking_probe):
        aliases_single, scan_root_single = _python_absolute_import_alias_files([abs_path], tmp_path)

    probe_count_single = len(probe_calls)

    assert aliases == aliases_single
    assert scan_root == scan_root_single
    assert probe_count_mixed == probe_count_single


def test_extract_deduplicates_context_nodes_filesystem_checks(tmp_path: Path):
    """extract() must deduplicate source_file in resolution_context_nodes to avoid repeated filesystem is_file() checks."""
    app_py = tmp_path / "app.py"
    app_py.write_text("def f(): pass\ndef g(): pass\n", encoding="utf-8")

    # Simulate 50 AST nodes originating from app.py
    context_nodes = [
        {"id": f"app_py:func_{i}", "source_file": "app.py", "kind": "function"}
        for i in range(50)
    ]

    is_file_calls_in_context_loop = []
    orig_is_file = Path.is_file

    def tracking_is_file(self):
        stack = traceback.extract_stack()
        for frame in stack:
            if frame.name == "extract" and "context_path" in (frame.line or ""):
                is_file_calls_in_context_loop.append(self)
        return orig_is_file(self)

    with patch.object(Path, "is_file", tracking_is_file):
        extract(
            [app_py],
            root=tmp_path,
            cache_root=tmp_path / "cache",
            resolution_context_nodes=context_nodes,
            parallel=False,
        )

    # app.py in context_nodes should trigger at most 1 is_file check in the context collection loop, not 50!
    assert len(is_file_calls_in_context_loop) == 1


def test_extract_handles_non_python_and_empty_context_nodes(tmp_path: Path):
    """extract() gracefully skips None, non-python, and empty source_file context nodes."""
    doc = tmp_path / "README.md"
    doc.write_text("# Readme\n", encoding="utf-8")
    app_py = tmp_path / "main.py"
    app_py.write_text("x = 1\n", encoding="utf-8")

    context_nodes = [
        {"id": "doc:1", "source_file": "README.md"},
        {"id": "doc:2", "source_file": "README.md"},
        {"id": "empty:1", "source_file": ""},
        {"id": "none:1"},
        {"id": "missing:1", "source_file": "does_not_exist.py"},
        {"id": "missing:2", "source_file": "does_not_exist.py"},
    ]

    result = extract(
        [app_py],
        root=tmp_path,
        cache_root=tmp_path / "cache",
        resolution_context_nodes=context_nodes,
        parallel=False,
    )
    assert "nodes" in result


def test_bit_identical_alias_resolution_on_complex_tree(tmp_path: Path):
    """Verify 100% bit-identical equivalence of aliases and scan_root_aliases with heavy duplicates across complex packages."""
    # Create a complex hierarchy:
    # root/
    #   src/
    #     pkg1/
    #       __init__.py
    #       core.py
    #       utils/
    #         __init__.py
    #         helper.py
    #     pkg2/
    #       __init__.py
    #       api.py
    src = tmp_path / "src"
    pkg1 = src / "pkg1"
    utils = pkg1 / "utils"
    pkg2 = src / "pkg2"

    for d in (pkg1, utils, pkg2):
        d.mkdir(parents=True, exist_ok=True)
        (d / "__init__.py").write_text("", encoding="utf-8")

    files = [
        pkg1 / "__init__.py",
        pkg1 / "core.py",
        utils / "__init__.py",
        utils / "helper.py",
        pkg2 / "__init__.py",
        pkg2 / "api.py",
    ]
    for f in files:
        if not f.exists():
            f.write_text("x = 1\n", encoding="utf-8")

    # Baseline: unique resolved paths
    unique_paths = [f.resolve() for f in files]
    aliases_base, scan_root_base = _python_absolute_import_alias_files(unique_paths, tmp_path)

    # Duplicated list (each file repeated 10 times in various forms: Path, str, relative, resolved)
    duplicated_paths = []
    for f in files:
        rel = f.relative_to(tmp_path)
        duplicated_paths.extend([f, str(f), rel, str(rel), f.resolve()] * 2)

    aliases_dup, scan_root_dup = _python_absolute_import_alias_files(duplicated_paths, tmp_path)

    # Invariant: Output must be 100% identical
    assert aliases_dup == aliases_base
    assert scan_root_dup == scan_root_base
