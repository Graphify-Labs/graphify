"""The partial-extraction warning must be actionable and must not misdirect.

It used to end in a hardcoded `(#2551)` for EVERY language. #2551 is closed and
Kotlin-specific ("bundled grammar rejects one-line type bodies"), so a reader
following the only lead the message offered landed on a resolved problem in a
different language — and at least one did, recording an Astro failure as
"already tracked upstream" on the strength of that number (#2788).

The message also could not distinguish a file that contributed nothing but its
own file node from one that yielded most of its symbols and lost an ERROR
region. Both rendered as "may be partially extracted".

Part 1 of #2788 — the Astro frontmatter parse itself — is NOT addressed here;
that belongs to the .svelte/.astro AST work in #2731.
"""
import re

import pytest

from graphify.extract import extract

# Any hardcoded issue citation, not just 2551 — re-introducing a different
# number for a message that covers every grammar is the same mistake.
_ISSUE_CITATION = re.compile(r"\(#\d+\)")


def _partial_parse_fixture(tmp_path):
    """A file the parser ACCEPTS only through ERROR recovery — an unclosed table
    constructor swallowing the function that follows it.

    Deliberately not the Kotlin one-line body from #2551: whether that shape
    trips the gate depends on the bundled grammar build, and these tests are
    about the MESSAGE, which must read the same whichever grammar produced it.
    """
    f = tmp_path / "broken.lua"
    f.write_text("local t = {\nfunction f() end\n", encoding="utf-8")
    return f


def _run(tmp_path, files, capsys):
    extract([*files], root=tmp_path)
    return capsys.readouterr().err


def test_warning_carries_no_hardcoded_issue_number(tmp_path, capsys):
    err = _run(tmp_path, [_partial_parse_fixture(tmp_path)], capsys)
    assert "partially extracted" in err, f"fixture no longer trips the gate: {err!r}"
    assert not _ISSUE_CITATION.search(err), (
        f"the warning still cites a single issue for every language: {err!r}")
    assert "#2551" not in err


def test_warning_names_the_file_and_how_much_survived(tmp_path, capsys):
    err = _run(tmp_path, [_partial_parse_fixture(tmp_path)], capsys)
    assert "partially extracted" in err, err
    assert "broken.lua" in err
    assert ("no symbols extracted" in err
            or re.search(r"\d+ symbol\(s\) extracted", err)), (
        f"the warning does not say how much survived: {err!r}")


def test_warning_still_reports_the_first_error_line(tmp_path, capsys):
    """The line number was the one actionable thing the old message had; it must
    survive the rewrite."""
    err = _run(tmp_path, [_partial_parse_fixture(tmp_path)], capsys)
    assert re.search(r"first error at line \d+", err), err


def test_a_clean_file_is_silent(tmp_path, capsys):
    f = tmp_path / "fine.py"
    f.write_text("def ok():\n    return 1\n", encoding="utf-8")
    err = _run(tmp_path, [f], capsys)
    assert "partially extracted" not in err
    assert "syntax errors" not in err


def test_the_citation_is_gone_from_the_source_not_just_one_path():
    import graphify.extract as ex
    text = open(ex.__file__, encoding="utf-8").read()
    assert "may be partially extracted: {_shown}{_more} (#2551)" not in text
    assert "no symbols extracted" in text
    assert "symbol(s) extracted" in text


def test_warning_suppressed_via_graphifyallow(tmp_path, capsys):
    fixture = _partial_parse_fixture(tmp_path)
    allow = tmp_path / ".graphifyallow"
    allow.write_text("broken.lua\n", encoding="utf-8")
    res = extract([fixture], root=tmp_path)
    err = capsys.readouterr().err
    assert "partially extracted" not in err
    assert "syntax errors" not in err
    # Nodes from broken.lua are preserved and extracted
    file_nodes = [n for n in res.get("nodes", []) if n.get("source_file") == "broken.lua"]
    assert len(file_nodes) > 0


def test_warning_suppressed_does_not_suppress_other_files(tmp_path, capsys):
    fixture1 = _partial_parse_fixture(tmp_path)
    fixture2 = tmp_path / "other.lua"
    fixture2.write_text("local t = {\nfunction f() end\n", encoding="utf-8")
    allow = tmp_path / ".graphifyallow"
    allow.write_text("broken.lua\n", encoding="utf-8")
    res = extract([fixture1, fixture2], root=tmp_path)
    err = capsys.readouterr().err
    assert "partially extracted" in err
    assert "other.lua" in err
    assert "broken.lua" not in err


def test_warning_suppressed_via_graphifywarnignore(tmp_path, capsys):
    fixture = _partial_parse_fixture(tmp_path)
    allow = tmp_path / ".graphifywarnignore"
    allow.write_text("broken.lua\n", encoding="utf-8")
    res = extract([fixture], root=tmp_path)
    err = capsys.readouterr().err
    assert "partially extracted" not in err
    assert "syntax errors" not in err


def test_warning_suppressed_via_param(tmp_path, capsys):
    fixture = _partial_parse_fixture(tmp_path)
    res = extract([fixture], root=tmp_path, suppress_syntax_warnings=["broken.lua"])
    err = capsys.readouterr().err
    assert "partially extracted" not in err
    assert "syntax errors" not in err


def test_warning_suppressed_all_via_param_bool(tmp_path, capsys):
    fixture = _partial_parse_fixture(tmp_path)
    res = extract([fixture], root=tmp_path, suppress_syntax_warnings=True)
    err = capsys.readouterr().err
    assert "partially extracted" not in err
    assert "syntax errors" not in err


def test_warning_suppressed_via_env(tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("GRAPHIFY_QUIET_SYNTAX_WARNINGS", "1")
    fixture = _partial_parse_fixture(tmp_path)
    res = extract([fixture], root=tmp_path)
    err = capsys.readouterr().err
    assert "partially extracted" not in err
    assert "syntax errors" not in err


def test_warning_suppressed_with_root_none_or_str(tmp_path, capsys, monkeypatch):
    """Ensure extract() handles root=None or root as a string without crashing when syntax error files exist."""
    monkeypatch.chdir(tmp_path)
    fixture = _partial_parse_fixture(tmp_path)
    allow = tmp_path / ".graphifyallow"
    allow.write_text("broken.lua\n", encoding="utf-8")

    # root as string
    res_str = extract([fixture], root=str(tmp_path))
    err_str = capsys.readouterr().err
    assert "partially extracted" not in err_str

    # root as None (anchors at cwd)
    res_none = extract([fixture], root=None)
    err_none = capsys.readouterr().err
    assert "partially extracted" not in err_none
