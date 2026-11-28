"""Folding a header/impl class pair must not drop edges of unrelated files.

When _merge_decl_def_classes folds an ObjC or C++ header/impl pair, it then
de-duplicates edges. That de-dup ran over every edge in the batch, keyed only on
(source, target, relation, context). Before disambiguation, two unrelated files
can still share raw ids (``sample.cu`` and ``sample.metal`` both define
``struct Vec3``), so one file's edges were dropped, and which one depended on
the order of the input paths. Every self-loop in the batch, such as a recursive
call, was dropped too. Only edges touching a merged id are twins.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract

_HEADER = "@interface Widget\n- (void)render;\n@end\n"
_IMPL = '#import "Widget.h"\n\n@implementation Widget\n- (void)render {\n}\n@end\n'
_STRUCT = "struct Vec3 {\n    float x;\n    float y;\n};\n"


def _corpus(root: Path) -> list[Path]:
    (root / "objc").mkdir()
    (root / "objc" / "Widget.h").write_text(_HEADER, encoding="utf-8")
    (root / "objc" / "Widget.m").write_text(_IMPL, encoding="utf-8")
    (root / "shader.cu").write_text(_STRUCT, encoding="utf-8")
    (root / "shader.metal").write_text(_STRUCT, encoding="utf-8")
    (root / "rec.py").write_text(
        "def fact(n):\n    return 1 if n < 2 else n * fact(n - 1)\n", encoding="utf-8"
    )
    return sorted(p for p in root.rglob("*") if p.is_file())


def _edges(paths: list[Path], root: Path) -> set[tuple[str, str, str]]:
    result = extract(paths, cache_root=root)
    return {(e["source"], e["target"], e["relation"]) for e in result["edges"]}


@pytest.mark.parametrize("order", ["sorted", "reversed"])
def test_same_stem_files_keep_their_own_member_edges(tmp_path, order):
    paths = _corpus(tmp_path)
    if order == "reversed":
        paths = list(reversed(paths))
    edges = _edges(paths, tmp_path)
    for stem in ("shader_cu", "shader_metal"):
        owner = f"{stem}_shader_vec3"
        assert (owner, f"{owner}_x", "defines") in edges, stem
        assert (owner, f"{owner}_y", "defines") in edges, stem


def test_output_does_not_depend_on_input_order(tmp_path):
    paths = _corpus(tmp_path)
    assert _edges(paths, tmp_path) == _edges(list(reversed(paths)), tmp_path)


def test_recursive_call_survives_a_header_impl_fold(tmp_path):
    paths = _corpus(tmp_path)
    edges = _edges(paths, tmp_path)
    assert ("rec_fact", "rec_fact", "calls") in edges


def test_header_impl_pair_is_still_folded_once(tmp_path):
    paths = _corpus(tmp_path)
    result = extract(paths, cache_root=tmp_path)
    widgets = [n for n in result["nodes"] if n.get("label") == "Widget"]
    assert len(widgets) == 1
    keys = [
        (e["source"], e["target"], e["relation"], e.get("context"))
        for e in result["edges"]
        if widgets[0]["id"] in (e["source"], e["target"])
    ]
    assert len(keys) == len(set(keys))
