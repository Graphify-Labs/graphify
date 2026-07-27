"""Tests for the SCSS/Sass extractor (graphify/extractors/scss.py)."""
from __future__ import annotations

from pathlib import Path

from graphify.extract import extract_scss


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _rel_targets(r, relation: str) -> set[str]:
    lab = {n["id"]: n["label"] for n in r["nodes"]}
    return {
        lab.get(e["target"], e["target"])
        for e in r["edges"]
        if e["relation"] == relation
    }


def _target_files(r, relation: str) -> set[str]:
    by_id = {n["id"]: n for n in r["nodes"]}
    return {
        by_id[e["target"]]["source_file"]
        for e in r["edges"]
        if e["relation"] == relation
    }


# --- module graph -----------------------------------------------------------

def test_use_resolves_through_the_partial_convention(tmp_path):
    _write(tmp_path, "tokens/_breakpoints.scss", "$tablet: 768px;\n")
    sheet = _write(tmp_path, "tokens/all.scss", "@use 'breakpoints';\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "imports") == {"_breakpoints.scss"}
    assert _target_files(r, "imports") == {
        str((tmp_path / "tokens/_breakpoints.scss").resolve())
    }


def test_use_resolves_through_the_index_convention(tmp_path):
    _write(tmp_path, "tokens/colors/_index.scss", "$red: #f00;\n")
    sheet = _write(tmp_path, "tokens/all.scss", "@use 'colors';\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "imports") == {"_index.scss"}


def test_use_with_an_alias_and_a_relative_path(tmp_path):
    _write(tmp_path, "tokens/_mixins.scss", "@mixin visually-hidden { }\n")
    sheet = _write(tmp_path, "components/card.scss",
                   "@use '../tokens/mixins' as mx;\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "imports") == {"_mixins.scss"}


def test_import_accepts_a_comma_separated_list(tmp_path):
    _write(tmp_path, "_a.scss", "")
    _write(tmp_path, "_b.scss", "")
    sheet = _write(tmp_path, "main.scss", "@import 'a', 'b';\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "imports") == {"_a.scss", "_b.scss"}


def test_builtin_sass_modules_stay_stubs(tmp_path):
    sheet = _write(tmp_path, "main.scss", "@use 'sass:math';\n")

    r = extract_scss(sheet)

    # A real dependency, but not a file in the corpus.
    assert _rel_targets(r, "imports") == {"sass:math"}


# --- mixin graph ------------------------------------------------------------

def test_mixin_definition_and_use_share_one_node(tmp_path):
    definer = _write(tmp_path, "_mixins.scss", "@mixin button-reset { border: 0; }\n")
    user = _write(tmp_path, "card.scss", "@use 'mixins' as mx;\n"
                                         ".c { @include mx.button-reset; }\n")

    defined = extract_scss(definer)
    used = extract_scss(user)

    def_edge = next(e for e in defined["edges"] if e["relation"] == "defines_mixin")
    use_edge = next(e for e in used["edges"] if e["relation"] == "uses_mixin")
    # The namespace is the consumer's local alias; the definition carries the
    # bare name, so both sides must key on the bare name to connect.
    assert def_edge["target"] == use_edge["target"]


def test_unnamespaced_include_also_links(tmp_path):
    sheet = _write(tmp_path, "card.scss", "@mixin focus-ring { }\n"
                                          ".c { @include focus-ring; }\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "defines_mixin") == {"focus-ring"}
    assert _rel_targets(r, "uses_mixin") == {"focus-ring"}


def test_include_at_rule_is_not_mistaken_for_import(tmp_path):
    sheet = _write(tmp_path, "card.scss", ".c { @include focus-ring; }\n")

    r = extract_scss(sheet)

    assert not [e for e in r["edges"] if e["relation"] == "imports"]


# --- design-token graph -----------------------------------------------------

def test_token_definition_and_use_share_one_node(tmp_path):
    definer = _write(tmp_path, "_tokens.scss", ":root { --spacing-05: 16px; }\n")
    user = _write(tmp_path, "card.scss", ".c { padding: var(--spacing-05, 16px); }\n")

    defined = extract_scss(definer)
    used = extract_scss(user)

    def_edge = next(e for e in defined["edges"] if e["relation"] == "defines_token")
    use_edge = next(e for e in used["edges"] if e["relation"] == "uses_token")
    assert def_edge["target"] == use_edge["target"]
    assert _rel_targets(defined, "defines_token") == {"--spacing-05"}


def test_nested_var_fallback_counts_both_tokens(tmp_path):
    sheet = _write(tmp_path, "card.scss",
                   ".c { color: var(--brand, var(--fallback)); }\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "uses_token") == {"--brand", "--fallback"}


def test_repeated_token_use_is_a_single_edge(tmp_path):
    sheet = _write(tmp_path, "card.scss",
                   ".a { margin: var(--spacing-05); }\n"
                   ".b { padding: var(--spacing-05); }\n"
                   ".c { gap: var(--spacing-05); }\n")

    r = extract_scss(sheet)

    assert len([e for e in r["edges"] if e["relation"] == "uses_token"]) == 1


# --- comments ---------------------------------------------------------------

def test_commented_out_rules_are_ignored(tmp_path):
    _write(tmp_path, "_real.scss", "")
    _write(tmp_path, "_ghost.scss", "")
    sheet = _write(tmp_path, "main.scss",
                   "// @use 'ghost';\n"
                   "/* @use 'ghost';\n"
                   "   @include ghost-mixin; */\n"
                   "@use 'real';\n")

    r = extract_scss(sheet)

    assert _rel_targets(r, "imports") == {"_real.scss"}
    assert not [e for e in r["edges"] if e["relation"] == "uses_mixin"]


def test_protocol_slashes_are_not_treated_as_a_comment(tmp_path):
    sheet = _write(tmp_path, "main.scss",
                   ".c { background: url(https://example.com/a.png); "
                   "color: var(--brand); }\n")

    r = extract_scss(sheet)

    # `//` inside the URL must not blank the rest of the line.
    assert _rel_targets(r, "uses_token") == {"--brand"}


def test_comment_stripping_preserves_line_numbers(tmp_path):
    _write(tmp_path, "_real.scss", "")
    sheet = _write(tmp_path, "main.scss",
                   "/* a\n   multiline\n   comment */\n"
                   "@use 'real';\n")

    r = extract_scss(sheet)

    location = next(e["source_location"] for e in r["edges"]
                    if e["relation"] == "imports")
    assert location == "L4"


# --- misc -------------------------------------------------------------------

def test_every_edge_is_extracted_with_full_confidence(tmp_path):
    sheet = _write(tmp_path, "card.scss", ".c { padding: var(--spacing-05); }\n")

    r = extract_scss(sheet)

    assert r["edges"], "expected at least one edge"
    for e in r["edges"]:
        assert e["confidence"] == "EXTRACTED"
        assert e["confidence_score"] == 1.0


def test_unreadable_file_reports_an_error(tmp_path):
    assert "error" in extract_scss(tmp_path / "missing.scss")
