"""A node whose source_file equals the scan root must not crash build (#1618).

`_norm_source_file` relativizes an absolute source_file that equals the scan root
to `Path('.')`. `_semantic_id_remap` then fed that into `_file_stem`, whose
`path.with_suffix("")` raises `ValueError: '.' has an empty name` — crashing the
final graph assembly AFTER all LLM extraction cost was spent, writing no graph at
all. A project-level node (source_file == root) has no per-file identity to remap,
so its id is left untouched.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import _semantic_id_remap, build_from_json
from graphify.extractors.base import _file_stem


def test_file_stem_handles_dot_path():
    assert _file_stem(Path(".")) == ""          # no raise
    assert _file_stem(Path("src/foo.py")) == "src/foo"


def test_semantic_id_remap_root_equal_source_file_no_crash():
    root = "/some/project/root"
    node = {"id": "some_concept", "source_file": root, "_origin": "semantic"}
    remap = _semantic_id_remap([node], root)   # must not raise
    # a root-equal node has no file stem, so its id is left untouched (not remapped)
    assert "some_concept" not in remap


def test_build_from_json_with_root_level_concept_node():
    root = "/proj"
    combined = {
        "nodes": [
            {"id": "proj_concept", "label": "Project", "file_type": "concept",
             "source_file": root, "_origin": "semantic"},
            {"id": "src_foo", "label": "foo", "file_type": "code",
             "source_file": "src/foo.py", "_origin": "ast"},
        ],
        "edges": [],
    }
    G = build_from_json(combined, root=root)    # previously crashed here
    assert G.number_of_nodes() == 2


def test_normal_semantic_remap_still_works():
    # regression guard: a real per-file node still gets remap consideration (#1504)
    remap = _semantic_id_remap(
        [{"id": "foo", "source_file": "src/foo.py", "_origin": "semantic"}], "/proj")
    assert isinstance(remap, dict)
