"""Registry tests for F# — each asserts one wiring point, so that deleting any
single registration is caught by a named failure rather than by silence.

The F# gap shipped in the first place because .fs matched *no* category and was
skipped without an error; these tests exist to make that class of regression
loud.
"""
from __future__ import annotations

import pytest

# NOTE: no module-level importorskip. The registry entries below are pure
# literals whose absence is a shippable bug regardless of whether the grammar
# is installed; only the two dispatch tests need the grammar and skip
# individually.


def test_detect_categorizes_fs_as_code():
    from graphify.detect import CODE_EXTENSIONS, DOC_EXTENSIONS
    assert ".fs" in CODE_EXTENSIONS
    assert ".fsx" in CODE_EXTENSIONS
    assert ".fs" not in DOC_EXTENSIONS


def test_watch_covers_fs():
    from graphify.watch import _WATCHED_EXTENSIONS
    assert ".fs" in _WATCHED_EXTENSIONS and ".fsx" in _WATCHED_EXTENSIONS


def test_dispatch_routes_fs_to_fsharp_extractor(tmp_path):
    pytest.importorskip("tree_sitter_fsharp")
    # Through the public extract() path, not a direct import: a missing
    # dispatch entry silently yields zero nodes for the file.
    from graphify.extract import extract
    p = tmp_path / "m.fs"
    p.write_text("module M\nlet f x = x\n", encoding="utf-8")
    r = extract([p], root=tmp_path)
    labels = {n["label"] for n in r["nodes"]}
    assert "f" in labels, "extract() did not route .fs to the F# extractor"


def test_dispatch_routes_fsx_to_fsharp_extractor(tmp_path):
    pytest.importorskip("tree_sitter_fsharp")
    # .fsx must be tested separately: the .fs entry alone keeps this green,
    # and the .fsx entry's removal survived a mutation run until this existed.
    from graphify.extract import extract
    p = tmp_path / "s.fsx"
    p.write_text("let hello name = name\n", encoding="utf-8")
    r = extract([p], root=tmp_path)
    labels = {n["label"] for n in r["nodes"]}
    assert "hello" in labels, "extract() did not route .fsx to the F# extractor"


def test_extra_hint_names_fsharp():
    from graphify.extract import _EXTRA_FOR_EXTENSION
    assert _EXTRA_FOR_EXTENSION.get(".fs") == "fsharp"
    assert _EXTRA_FOR_EXTENSION.get(".fsx") == "fsharp"


def test_fs_shares_dotnet_interop_family_with_cs():
    # The load-bearing entry: same family is what allows an F# reference stub
    # to rewire onto a C# definition instead of dangling.
    from graphify.extract import _LANG_FAMILY_BY_EXT
    assert _LANG_FAMILY_BY_EXT.get(".fs") == _LANG_FAMILY_BY_EXT[".cs"] == "dotnet"
    assert _LANG_FAMILY_BY_EXT.get(".fsx") == "dotnet"


def test_analyze_family_matches_cs():
    from graphify.analyze import _LANG_FAMILY
    assert _LANG_FAMILY.get(".fs") == _LANG_FAMILY[".cs"]


def test_build_edge_family_matches_cs():
    from graphify.build import _EDGE_LANG_FAMILY
    assert _EDGE_LANG_FAMILY.get(".fs") == _EDGE_LANG_FAMILY[".cs"]
    assert _EDGE_LANG_FAMILY.get(".fsx") == _EDGE_LANG_FAMILY[".cs"]


def test_glsl_fragment_shader_is_not_dispatched_to_fsharp(tmp_path):
    # .fs is also the standard GLSL fragment-shader extension. A shader must
    # get NO extractor (no-AST-extractor warning path), not be ERROR-parsed
    # into sourceless dotnet-family stubs.
    from graphify.extract import _get_extractor
    p = tmp_path / "frag.fs"
    p.write_text("#version 330 core\nuniform vec4 color;\n"
                 "void main() { gl_FragColor = color; }\n", encoding="utf-8")
    assert _get_extractor(p) is None

    q = tmp_path / "real.fs"
    q.write_text("module M\nlet f x = x\n", encoding="utf-8")
    assert _get_extractor(q) is not None
