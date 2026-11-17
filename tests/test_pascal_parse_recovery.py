"""Regression tests for Pascal units the grammar cannot parse end to end.

tree-sitter-pascal 0.11.0 rejects two constructs that are ordinary Delphi, and
has no usable error recovery for either: everything from the offending bytes to
EOF lands in one ERROR node, so every later declaration is dropped.

  * a string literal whose FIRST content character is an escaped apostrophe --
    ``'''x'`` (Isopod/tree-sitter-pascal#24). The same escape in the middle
    (``'a''b'``) or at the end (``'abc'''``) parses fine. This is the idiom for
    building SQL by concatenation, so data-access units are lost wholesale.
  * a compiler directive between a routine header and its ``begin``
    (Isopod/tree-sitter-pascal#16), the usual way a routine's ``var`` block is
    guarded.

``extract_pascal`` masks the offending bytes and reparses, keeping the rewrite
only when it parses better. Each test below asserts on a routine declared
AFTER the construct: that is what the unmasked parse loses, so these fail
against the old behaviour rather than merely exercising the new code.

Static fixtures rather than tmp_path, for the reason given in
tests/test_pascal_resolution.py: the extractor's cross-file class lookup walks
UP from the source file, and the system temp directory is not a stable project
root.
"""
from __future__ import annotations

import importlib.util as _ilu
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "pascal_parse_recovery"

_needs_pascal = pytest.mark.skipif(
    _ilu.find_spec("tree_sitter_pascal") is None,
    reason="tree-sitter-pascal not installed (this is the AST path)",
)


def _labels(result: dict) -> list[str]:
    return [str(n.get("label", "")) for n in result["nodes"]]


@_needs_pascal
def test_routine_after_sql_quoted_literal_survives():
    from graphify.extract import extract_pascal

    result = extract_pascal(FIXTURES / "SqlBuilder.pas")
    assert "error" not in result
    labels = _labels(result)
    # Declared after `'select db_id('''+Name+''') as dbname'`.
    assert "AfterTheQuotedLiteral()" in labels
    # The literal's own routine must survive too, not just what follows it.
    assert "QuotedLookup()" in labels


@_needs_pascal
def test_routine_after_guarded_var_block_survives():
    from graphify.extract import extract_pascal

    result = extract_pascal(FIXTURES / "Guarded.pas")
    assert "error" not in result
    labels = _labels(result)
    # Declared after the {$IFDEF}-guarded var block.
    assert "AfterTheDirective()" in labels
    assert "WithGuardedLocals()" in labels


@_needs_pascal
def test_masking_preserves_source_locations():
    """The mask is byte-length preserving, so reported lines must still be the
    user's. A mask that shifted offsets would still satisfy the tests above."""
    from graphify.extract import extract_pascal

    source = (FIXTURES / "SqlBuilder.pas").read_text(encoding="utf-8").splitlines()
    result = extract_pascal(FIXTURES / "SqlBuilder.pas")
    for node in result["nodes"]:
        if node.get("label") != "AfterTheQuotedLiteral()":
            continue
        line = int(str(node["source_location"]).lstrip("L"))
        assert "AfterTheQuotedLiteral" in source[line - 1]
        break
    else:  # pragma: no cover - guarded by the test above
        pytest.fail("AfterTheQuotedLiteral() not extracted")


def test_normalizers_are_byte_length_preserving():
    """Both masks must keep every downstream offset identical."""
    from graphify.extractors.pascal import (
        _normalize_pascal_compiler_directives,
        _normalize_pascal_escaped_string_literals,
    )

    literal_src = b"S := '''abc'; T := '''';\n"
    masked = _normalize_pascal_escaped_string_literals(literal_src)
    assert masked is not None
    assert len(masked) == len(literal_src)
    assert b"'''" not in masked

    directive_src = b"procedure P;\n{$IFDEF X}\nvar I: Integer;\n{$ENDIF}\nbegin\nend;\n"
    masked = _normalize_pascal_compiler_directives(directive_src)
    assert masked is not None
    assert len(masked) == len(directive_src)
    assert b"{$" not in masked


def test_normalizers_leave_untouched_sources_alone():
    """No offending construct means no rewrite, so an already-parsing unit
    never takes the retry path."""
    from graphify.extractors.pascal import (
        _normalize_pascal_compiler_directives,
        _normalize_pascal_escaped_string_literals,
    )

    # Escapes in the middle and at the end are valid for the grammar.
    assert _normalize_pascal_escaped_string_literals(b"S := 'a''b' + 'abc''';\n") is None
    # An empty literal is not an escaped apostrophe.
    assert _normalize_pascal_escaped_string_literals(b"S := '';\n") is None
    assert _normalize_pascal_compiler_directives(b"{ plain comment }\nbegin\nend;\n") is None


def test_string_literal_mask_ignores_comments():
    """A `'''` inside a comment is not a literal and must not be rewritten."""
    from graphify.extractors.pascal import _normalize_pascal_escaped_string_literals

    assert _normalize_pascal_escaped_string_literals(b"// why ''' is hard\n") is None
    assert _normalize_pascal_escaped_string_literals(b"{ why ''' is hard }\n") is None
