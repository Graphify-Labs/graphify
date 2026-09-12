"""A valid C/C++ file with no trailing newline must not be reported as having
a syntax error (#3513).

tree-sitter-c/tree-sitter-cpp requires a newline to terminate a preprocessor
directive; when the directive is the last thing in the file and the file does
not end in a newline, the grammar recovers with an ERROR node even though the
directive itself is complete and legal. That trips the #2551 partial-extraction
gate in ``_extract_generic`` (``root.has_error``) and reports a spurious
syntax error on a file that compiles fine and loses no symbols.

Not header-specific: reproduces for any C/C++-family extension whose last
line is a preprocessor directive, ``.c``/``.cpp`` sources included.
"""
from pathlib import Path

import pytest

from graphify.extract import extract_c, extract_cpp

pytest.importorskip("tree_sitter_c")
pytest.importorskip("tree_sitter_cpp")

# #define is not node-worthy on its own, so both variants extract exactly the
# file node — the trailing newline changes nothing about what is recovered,
# only whether a syntax error is (falsely) reported.
_SOURCE = "#define A 8\n#define AA 3"

_C_EXTENSIONS = (".h", ".c")
_CPP_EXTENSIONS = (".hpp", ".cpp", ".cc", ".cxx", ".cu", ".cuh", ".metal")


def _extract(path: Path) -> dict:
    return extract_cpp(path) if path.suffix in _CPP_EXTENSIONS else extract_c(path)


@pytest.mark.parametrize("ext", _C_EXTENSIONS + _CPP_EXTENSIONS)
def test_no_trailing_newline_is_not_a_syntax_error(tmp_path, ext):
    p = tmp_path / f"valid{ext}"
    p.write_text(_SOURCE)  # deliberately no trailing newline
    result = _extract(p)
    assert result.get("parse_errors") is None, (
        f"{ext}: valid file with no trailing newline falsely reported as "
        f"having a syntax error: {result.get('parse_errors')!r}")


@pytest.mark.parametrize("ext", _C_EXTENSIONS + _CPP_EXTENSIONS)
def test_trailing_newline_is_the_positive_control(tmp_path, ext):
    """The same content WITH a trailing newline must be clean — this pins the
    defect to the missing newline, not to anything else about the fixture."""
    p = tmp_path / f"valid{ext}"
    p.write_text(_SOURCE + "\n")
    result = _extract(p)
    assert result.get("parse_errors") is None


@pytest.mark.parametrize("ext,content", [
    (".c", b"int f(void){return 1;}\n#define A 1"),
    (".cpp", b"struct P{int x;};\nint g(void){return 0;}\n#include <a.h>"),
])
def test_no_trailing_newline_shifts_no_node_or_edge(tmp_path, ext, content):
    """The fix appends the missing newline past the last real token, so the
    supplied newline must not move a single node or edge — extracting the
    same path with and without the trailing byte must yield byte-identical
    nodes and edges (only ``parse_errors`` is allowed to differ)."""
    p = tmp_path / f"f{ext}"
    p.write_bytes(content)
    without_nl = _extract(p)
    p.write_bytes(content + b"\n")
    with_nl = _extract(p)
    without_nl.pop("parse_errors", None)
    with_nl.pop("parse_errors", None)
    assert without_nl["nodes"] == with_nl["nodes"]
    assert without_nl["edges"] == with_nl["edges"]


def test_end_to_end_warning_is_silent_for_a_header_missing_only_a_newline(
    tmp_path, capsys,
):
    """The observable symptom from #3513: ``extract()`` prints the #2551
    partial-extraction warning for a header that is otherwise completely
    valid, purely because it lacks a trailing newline."""
    from graphify.extract import extract

    p = tmp_path / "my_file.h"
    p.write_text(_SOURCE)
    extract([p], root=tmp_path, cache_root=tmp_path)
    err = capsys.readouterr().err
    assert "syntax error" not in err and "partially extracted" not in err, (
        f"spurious syntax-error warning for a file missing only a trailing "
        f"newline: {err!r}")


@pytest.mark.parametrize("ext,fn", [(".c", extract_c), (".cpp", extract_cpp)])
def test_a_genuine_syntax_error_is_still_flagged(tmp_path, ext, fn):
    """The fix only supplies a missing trailing newline — it must not swallow
    an actual syntax error that happens to sit before a trailing directive."""
    p = tmp_path / f"broken{ext}"
    p.write_bytes(b"int f( { return 1; }\n#define A 1")
    result = fn(p)
    assert result.get("parse_errors") is not None, (
        f"{ext}: a genuinely broken file is no longer flagged as having a "
        f"syntax error")


def test_an_unterminated_conditional_is_still_flagged(tmp_path):
    """A trailing newline does not excuse an ``#if`` with no matching
    ``#endif`` — this has nothing to do with the missing-newline fix and must
    keep failing."""
    p = tmp_path / "broken.c"
    p.write_bytes(b"#if FOO\nint x;\n")
    result = extract_c(p)
    assert result.get("parse_errors") is not None


@pytest.mark.parametrize("ext,fn", [(".c", extract_c), (".cpp", extract_cpp)])
def test_backslash_continued_macro_at_eof_is_not_flagged(tmp_path, ext, fn):
    """A multi-line macro via line continuation, with no trailing newline
    after the final continuation line — a common shape for the last macro in
    a header. The narrow "last line starts with #" guard missed this because
    the offending line does not itself start with ``#``."""
    p = tmp_path / f"valid{ext}"
    p.write_bytes(b"#define MAX(a,b) \\\n  ((a) > (b) ? (a) : (b))")
    result = fn(p)
    assert result.get("parse_errors") is None


def test_utf8_bom_before_trailing_directive_is_not_flagged(tmp_path):
    """A UTF-8 BOM at the start of the file must not defeat the missing-
    newline detection at the end of the file."""
    p = tmp_path / "valid.c"
    p.write_bytes(b"\xef\xbb\xbf#define A 8")
    result = extract_c(p)
    assert result.get("parse_errors") is None
    # Control: the same bytes plus a trailing newline were already clean, so
    # the BOM — not something else about this fixture — is the variable.
    p.write_bytes(b"\xef\xbb\xbf#define A 8\n")
    assert extract_c(p).get("parse_errors") is None


def test_comment_before_trailing_directive_is_not_flagged(tmp_path):
    """A block comment ahead of the final, unterminated directive must not
    prevent the fix from recognizing the directive as the last real line."""
    p = tmp_path / "valid.c"
    p.write_bytes(b"int a;\n/* guard */ #define A 1")
    result = extract_c(p)
    assert result.get("parse_errors") is None


def test_fix_is_scoped_to_c_and_cpp_grammars(tmp_path, monkeypatch):
    """The #3513 fix must supply the missing trailing newline only ahead of
    the tree_sitter_c / tree_sitter_cpp grammars. Python parsing itself does
    not care whether the file ends in a newline, so comparing extracted nodes
    can't tell a scoped fix from an unscoped one; spy on the bytes actually
    handed to the parser instead, which is the one place the scoping lives."""
    import tree_sitter

    from graphify.extract import extract_python

    # extract_python runs the tree-sitter-python parse twice — once in
    # _extract_generic, once more in the docstring/rationale post-pass — so
    # every call must be checked, not just whichever happens to run last.
    seen: list[bytes] = []
    orig_parse = tree_sitter.Parser.parse

    def _spy_parse(self, source, *args, **kwargs):
        seen.append(bytes(source))
        return orig_parse(self, source, *args, **kwargs)

    monkeypatch.setattr(tree_sitter.Parser, "parse", _spy_parse)

    content = b"x = 1\n# trailing comment"
    p = tmp_path / "f.py"
    p.write_bytes(content)
    extract_python(p)
    assert seen, "the parse spy never fired"
    assert all(s == content for s in seen), (
        "a non-C/C++ file had a newline silently appended before parsing - "
        f"the #3513 fix must stay scoped to tree_sitter_c/tree_sitter_cpp: {seen!r}")
