"""Regression lock-in for #4262: a cross-module reference to a type defined
exactly once must bind to that single located definition, not dangle on a
per-file stub.

The reporter saw a `Settings` class defined once at `config/settings/_models.py`
(node `config_settings_models_settings`) with hundreds of per-file `Settings`
stub nodes and zero links to the real class. On current `v8` the reference binds
through the re-export chain (and, failing that, through the unique-stub rewire),
so these tests pin that behavior against regressions.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _edge_set(G):
    return {
        (d.get("relation"), d.get("_src", u), d.get("_tgt", v))
        for u, v, d in G.edges(data=True)
    }


def _settings_stub_count(res: dict) -> int:
    return sum(
        1 for n in res["nodes"]
        if n.get("label") == "Settings" and not n.get("source_file")
    )


def test_reexported_type_reference_binds_to_single_located_def(tmp_path: Path) -> None:
    (tmp_path / "config" / "settings").mkdir(parents=True)
    (tmp_path / "app").mkdir()
    (tmp_path / "config" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "config" / "settings" / "__init__.py").write_text(
        "from ._models import Settings\n", encoding="utf-8"
    )
    (tmp_path / "config" / "settings" / "_models.py").write_text(
        "class Settings:\n    def load(self):\n        return 1\n", encoding="utf-8"
    )
    (tmp_path / "app" / "service.py").write_text(
        "from config.settings import Settings\n\n\n"
        "def run(s: Settings):\n    return s.load()\n",
        encoding="utf-8",
    )

    paths = [
        tmp_path / "config" / "__init__.py",
        tmp_path / "config" / "settings" / "__init__.py",
        tmp_path / "config" / "settings" / "_models.py",
        tmp_path / "app" / "service.py",
    ]
    res = extract(paths, root=tmp_path, parallel=False, cache_root=tmp_path / "graphify-cache")

    assert _settings_stub_count(res) == 0, "no sourceless per-file Settings stub should survive"
    G = build_from_json(res, root=str(tmp_path), directed=True)
    edges = _edge_set(G)
    assert ("references", "app_service_run", "config_settings_models_settings") in edges, (
        f"cross-module Settings reference did not bind to the single located def: {edges}"
    )


def test_unresolved_type_references_coalesce_to_unique_def(tmp_path: Path) -> None:
    """No imports at all: several files inherit a `Settings` defined exactly once.
    The unique-stub rewire must bind every reference to the one real class rather
    than leaving a per-file stub in each file."""
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "_models.py").write_text("class Settings:\n    pass\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("class A(Settings):\n    pass\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("class B(Settings):\n    pass\n", encoding="utf-8")

    paths = [tmp_path / "pkg" / "_models.py", tmp_path / "a.py", tmp_path / "b.py"]
    res = extract(paths, root=tmp_path, parallel=False, cache_root=tmp_path / "graphify-cache")

    assert _settings_stub_count(res) == 0
    G = build_from_json(res, root=str(tmp_path), directed=True)
    edges = _edge_set(G)
    assert ("inherits", "a_a", "pkg_models_settings") in edges
    assert ("inherits", "b_b", "pkg_models_settings") in edges
