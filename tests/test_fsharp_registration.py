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
    assert "f()" in labels, "extract() did not route .fs to the F# extractor"


def test_dispatch_routes_fsx_to_fsharp_extractor(tmp_path):
    pytest.importorskip("tree_sitter_fsharp")
    # .fsx must be tested separately: the .fs entry alone keeps this green,
    # and the .fsx entry's removal survived a mutation run until this existed.
    from graphify.extract import extract
    p = tmp_path / "s.fsx"
    p.write_text("let hello name = name\n", encoding="utf-8")
    r = extract([p], root=tmp_path)
    labels = {n["label"] for n in r["nodes"]}
    assert "hello()" in labels, "extract() did not route .fsx to the F# extractor"


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


def test_glsl_guard_is_load_bearing_for_marker_collisions(tmp_path):
    # A modern shader with no #version line but a comment mentioning `type ` —
    # an F# marker — must STILL be rejected on its GLSL markers. Deleting the
    # GLSL marker check flips this file to "F#", so this test kills that
    # mutant (the original test's shader had no F# markers and could not).
    from graphify.extract import _get_extractor
    p = tmp_path / "lighting.fs"
    p.write_text("// type of light: directional\n"
                 "in vec3 normal;\nout vec4 fragColor;\n"
                 "void main() { fragColor = vec4(normal, 1.0); }\n",
                 encoding="utf-8")
    assert _get_extractor(p) is None


def test_modern_shader_without_version_line_not_dispatched(tmp_path):
    from graphify.extract import _get_extractor
    p = tmp_path / "phong.fs"
    p.write_text("// phong lighting\nin vec3 normal;\nout vec4 fragColor;\n"
                 "void main() { float d = 0.0; }\n", encoding="utf-8")
    assert _get_extractor(p) is None


# ── Round-4 sniff + resolution gates ─────────────────────────────────────────


def test_fsharp_with_glsl_words_in_comments_is_dispatched(tmp_path):
    # Round-3's sniff DROPPED this file ("uniform " matched inside a comment).
    from graphify.extract import _get_extractor
    p = tmp_path / "stats.fs"
    p.write_text("module Stats\n"
                 "// Draws a sample from a uniform distribution over [lo, hi).\n"
                 "let sampleUniform lo hi = lo + hi\n", encoding="utf-8")
    assert _get_extractor(p) is not None


def test_fsharp_with_float_expression_lines_is_dispatched(tmp_path):
    # Cross-exam counterexample: real corpus lines start with `float ` —
    # weak GLSL evidence must not override a strong F# declaration.
    from graphify.extract import _get_extractor
    p = tmp_path / "fmt.fs"
    p.write_text("namespace Grasp.Tui\nmodule Fmt =\n"
                 "    let pct count total =\n"
                 "        float count / float total * 100.0\n", encoding="utf-8")
    assert _get_extractor(p) is not None


def test_marker_free_shader_rejected_on_weak_evidence(tmp_path):
    from graphify.extract import _get_extractor
    p = tmp_path / "blur.fs"
    p.write_text("// blur\nfloat weight = 0.5;\nfloat offset = 1.3;\n",
                 encoding="utf-8")
    assert _get_extractor(p) is None


def test_comment_only_marker_regression(tmp_path):
    # Kills the mutant that re-adds b"//" as F# evidence: this shader's only
    # F#-marker-shaped bytes are comments.
    from graphify.extract import _get_extractor
    p = tmp_path / "glow.fs"
    p.write_text("// glow pass\n// type: additive\nfloat glow = 2.0;\n",
                 encoding="utf-8")
    assert _get_extractor(p) is None


def test_pure_fsharp_corpus_resolves_open_to_canonical_namespace(tmp_path):
    # The imports repoint was gated on .cs presence: a pure-F# corpus dangled
    # every open edge and build silently pruned them (verified by two arms).
    pytest.importorskip("tree_sitter_fsharp")
    from graphify.extract import extract
    from graphify.extractors.engine import _csharp_namespace_id
    lib = tmp_path / "Lib.fs"
    lib.write_text("namespace Acme.Widgets\ntype Gadget() = member this.Go() = 1\n",
                   encoding="utf-8")
    prog = tmp_path / "Program.fs"
    prog.write_text("namespace Acme.App\nopen Acme.Widgets\n"
                    "module Main =\n    let run () = 1\n", encoding="utf-8")
    r = extract([lib, prog], root=tmp_path, max_workers=1)
    canon = _csharp_namespace_id("Acme.Widgets")
    hits = [e for e in r["edges"]
            if e["relation"] == "imports" and e["target"] == canon]
    assert hits, "open edge was not repointed to the canonical namespace node"
