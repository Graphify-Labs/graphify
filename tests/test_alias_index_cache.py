"""Tests for per-file caching and sentinel deduplication in _alias_index."""
from pathlib import Path
from unittest.mock import patch

from graphify import build


def test_alias_index_caches_per_source_file(tmp_path: Path) -> None:
    """_alias_index computes old file stems once per distinct source_file."""
    nodes = [
        (f"pkg_sub_mod_fn{i}", {"id": f"pkg_sub_mod_fn{i}", "label": f"fn{i}()", "source_file": "pkg/sub/mod.py", "_origin": "ast"})
        for i in range(25)
    ] + [
        ("pkg_sub_mod", {"id": "pkg_sub_mod", "label": "mod.py", "source_file": "pkg/sub/mod.py", "_origin": "ast"}),
        ("pkg_sub_other_fn0", {"id": "pkg_sub_other_fn0", "label": ".run()", "source_file": "pkg/sub/other.py", "_origin": "ast"}),
    ]

    with patch("graphify.build._old_file_stems", wraps=build._old_file_stems) as spy:
        idx = build._alias_index(nodes)

    assert spy.call_count == 2
    assert idx["sub_mod"] == "pkg_sub_mod"
    assert idx["mod_fn0"] == "pkg_sub_mod_fn0"
    assert idx["sub_mod_fn24"] == "pkg_sub_mod_fn24"
    assert idx["pkg_sub_other_run"] == "pkg_sub_other_fn0"


def test_alias_index_drops_ambiguous_aliases_and_keeps_unique() -> None:
    """Ambiguous aliases across distinct nodes are dropped; unique ones survive."""
    nodes = [
        ("a_b_mod_run", {"id": "a_b_mod_run", "label": "run()", "source_file": "a/b/mod.py", "_origin": "ast"}),
        ("c_d_mod_run", {"id": "c_d_mod_run", "label": "run()", "source_file": "c/d/mod.py", "_origin": "ast"}),
        ("a_b_mod_unique", {"id": "a_b_mod_unique", "label": "unique()", "source_file": "a/b/mod.py", "_origin": "ast"}),
    ]
    idx = build._alias_index(nodes)
    assert "mod_run" not in idx
    assert idx["b_mod_run"] == "a_b_mod_run"
    assert idx["d_mod_run"] == "c_d_mod_run"
    assert idx["mod_unique"] == "a_b_mod_unique"
