r"""An ignore file that is not valid UTF-8 must not silently lose its rules.

`_load_dir_own_ignore` / `_load_graphifyignore` read .gitignore,
.graphifyignore and $GIT_DIR/info/exclude with `errors="ignore"`, which turns a
mis-encoded byte into no byte at all. A file saved in the host ANSI codepage —
Notepad's historical default on Windows, and still what `Set-Content` writes
without `-Encoding` — is not valid UTF-8, so a rule reading `Orçamento/`
(cp1252 `Or\xe7amento/`) decoded to `Oramento/`, matched nothing, and said
nothing. The directory was scanned despite an explicit exclusion.

That is the failure mode the NFC/NFD tests in test_detect.py already warn about
in prose ("the rule silently does nothing — the files get scanned, and
docs/PDFs are sent to an LLM despite an explicit exclusion"), reached by a
different route.

These tests write the bytes directly rather than going through `write_text`, so
they pin the decoding behaviour on every platform, not just where cp1252 is the
default.
"""
import unicodedata

import pytest

from graphify.detect import _read_ignore_text, detect

NAME = "Orçamento"  # "Orçamento" — ç is U+00E7, present in cp1252


def _corpus(tmp_path, ignore_bytes: bytes, dirname: str = NAME):
    (tmp_path / ".graphifyignore").write_bytes(ignore_bytes)
    d = tmp_path / dirname
    d.mkdir()
    (d / "contrato.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "main.py").write_text("print('hi')", encoding="utf-8")
    return tmp_path


def _scanned(result) -> set[str]:
    from pathlib import Path
    return {Path(f).name for f in result["files"]["code"]}


# ---------------------------------------------------------------------------
# The bug
# ---------------------------------------------------------------------------

def test_ansi_encoded_rule_still_excludes(tmp_path):
    """The reported case: a cp1252 .graphifyignore must still exclude."""
    _corpus(tmp_path, f"{NAME}/\n".encode("cp1252"))
    scanned = _scanned(detect(tmp_path))
    assert "contrato.py" not in scanned, (
        "a non-UTF-8 ignore rule silently did nothing; scanned=" + repr(scanned))
    assert "main.py" in scanned


def test_ansi_encoded_rule_warns_once_naming_the_file(tmp_path, capsys):
    import graphify.detect as detect_mod
    detect_mod._warned_ignore_encodings.clear()
    _corpus(tmp_path, f"{NAME}/\n".encode("cp1252"))
    detect(tmp_path)
    err = capsys.readouterr().err
    assert ".graphifyignore" in err and "UTF-8" in err, err


def test_utf8_rule_is_unaffected(tmp_path):
    """The control: the format we document keeps working, with no warning."""
    _corpus(tmp_path, f"{NAME}/\n".encode("utf-8"))
    assert "contrato.py" not in _scanned(detect(tmp_path))


def test_ascii_rules_are_untouched(tmp_path):
    (tmp_path / ".graphifyignore").write_bytes(b"vendor/\n")
    (tmp_path / "vendor").mkdir()
    (tmp_path / "vendor" / "lib.py").write_text("x = 1", encoding="utf-8")
    (tmp_path / "main.py").write_text("x = 1", encoding="utf-8")
    scanned = _scanned(detect(tmp_path))
    assert scanned == {"main.py"}, scanned


def test_no_warning_for_a_clean_utf8_file(tmp_path, capsys):
    import graphify.detect as detect_mod
    detect_mod._warned_ignore_encodings.clear()
    _corpus(tmp_path, f"{NAME}/\n".encode("utf-8"))
    detect(tmp_path)
    assert "not valid UTF-8" not in capsys.readouterr().err


# ---------------------------------------------------------------------------
# _read_ignore_text directly
# ---------------------------------------------------------------------------

def test_utf8_with_bom_is_still_stripped(tmp_path):
    p = tmp_path / ".graphifyignore"
    p.write_bytes(b"\xef\xbb\xbfvendor/\n")
    assert _read_ignore_text(p) == "vendor/\n"


def test_decoding_never_raises_on_arbitrary_bytes(tmp_path):
    """The previous contract: reading an ignore file cannot blow up a scan."""
    p = tmp_path / ".graphifyignore"
    p.write_bytes(bytes(range(256)))
    assert isinstance(_read_ignore_text(p), str)


def test_no_byte_is_dropped_from_a_mis_encoded_file(tmp_path):
    """The actual regression: every rule survives, even if a third encoding
    renders it wrong, rather than being silently truncated to nothing."""
    p = tmp_path / ".graphifyignore"
    p.write_bytes("café/\nvendor/\n".encode("cp1252"))
    lines = [ln for ln in _read_ignore_text(p).splitlines() if ln]
    assert len(lines) == 2, lines
    assert lines[1] == "vendor/"
    assert len(lines[0]) == len("café/"), lines[0]


def test_empty_file_is_empty(tmp_path):
    p = tmp_path / ".graphifyignore"
    p.write_bytes(b"")
    assert _read_ignore_text(p) == ""


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_utf8_rules_still_match_across_normalisation_forms(tmp_path, form):
    """The existing NFC/NFD guarantee must survive the new decode path."""
    pattern = unicodedata.normalize(form, NAME)
    other = unicodedata.normalize("NFD" if form == "NFC" else "NFC", NAME)
    _corpus(tmp_path, f"{pattern}/\n".encode("utf-8"), dirname=other)
    assert "contrato.py" not in _scanned(detect(tmp_path))


def test_utf16_bom_encoded_rule_still_excludes(tmp_path):
    """A UTF-16 (BOM) .graphifyignore — what PowerShell Set-Content and Notepad
    'Unicode' emit — must decode by its BOM and apply, not fall to latin-1 and
    garble every rule into NUL-laden noise."""
    _corpus(tmp_path, f"{NAME}/\n".encode("utf-16"))
    scanned = _scanned(detect(tmp_path))
    assert "contrato.py" not in scanned, (
        "a UTF-16 ignore rule silently did nothing; scanned=" + repr(scanned))
    assert "main.py" in scanned


def test_utf16_is_decoded_without_nul_garbage(tmp_path):
    """Direct check: the decoded text is clean UTF-16, not latin-1 mojibake."""
    p = tmp_path / ".graphifyignore"
    p.write_bytes("build/\nsecret.py\n".encode("utf-16"))
    text = _read_ignore_text(p)
    assert "\x00" not in text
    assert text.splitlines() == ["build/", "secret.py"]
