"""C# verbatim interpolated strings the bundled grammar rejects (#3376).

A verbatim interpolated string whose text ends with an interpolation hole, an
escaped quote and then the terminator is valid C# -- ``dotnet build`` accepts it
-- but tree-sitter-c-sharp 0.23.5 rejects it. The file is then only partially
extracted and every member declared after that line is silently missing from the
graph. 0.23.5 is the newest release, so there is no grammar bump to take.

The fix neutralizes only the trailing escape, with two spaces. It must be
byte-length preserving: line and column numbers are reported straight from the
parsed buffer, so inserting or deleting a single byte would silently shift every
``source_location`` after it (the #2876 contract).
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import _normalize_csharp_verbatim_interpolation, extract

# The offending literal, kept in one place: `}` then an escaped quote then the
# terminator. Written as a plain string so the C# quoting stays readable.
OFFENDER = 'var s = $@"a""{e}""";'


def _cs_class(body_lines: list[str]) -> str:
    return "using System;\n\npublic class Config\n{\n" + "\n".join(body_lines) + "\n}\n"


def _extract(tmp_path, files: dict[str, str]) -> dict:
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files], cache_root=tmp_path / ".cache")
    finally:
        os.chdir(old)


def test_members_after_the_offending_literal_are_still_extracted(tmp_path):
    """The symptom: every member declared after the literal vanished."""
    src = _cs_class([
        "    public void BeforeOne() { }",
        "    public string Offender(string e) { " + OFFENDER + " return s; }",
        "    public void AfterOne() { }",
        "    public void AfterTwo() { }",
    ])
    result = _extract(tmp_path, {"Config.cs": src})
    labels = {str(n.get("label", "")).lstrip(".") for n in result["nodes"]}
    for member in ("BeforeOne()", "Offender()", "AfterOne()", "AfterTwo()"):
        assert member in labels, f"{member} missing from {sorted(labels)}"


def test_source_locations_are_not_shifted(tmp_path):
    """Line numbers must still point at the real declaration in the file on disk.

    A mask that changed the byte length would move every member after it.
    """
    lines = [
        "    public void BeforeOne() { }",          # line 5
        "",
        "    public string Offender(string e) { " + OFFENDER + " return s; }",  # line 7
        "",
        "    public void AfterOne() { }",           # line 9
        "",
        "    public void AfterTwo() { }",           # line 11
    ]
    src = _cs_class(lines)
    on_disk = {}
    for i, line in enumerate(src.splitlines(), 1):
        for name in ("BeforeOne", "Offender", "AfterOne", "AfterTwo"):
            if f" {name}(" in line:
                on_disk[name] = i

    result = _extract(tmp_path, {"Config.cs": src})
    seen = {}
    for node in result["nodes"]:
        name = str(node.get("label", "")).lstrip(".").rstrip("()")
        if name in on_disk and node.get("source_location"):
            seen[name] = int("".join(c for c in str(node["source_location"]) if c.isdigit()))

    # Assert presence first: without the fix these nodes do not exist at all and
    # a loop over them would vacuously pass.
    assert set(seen) == set(on_disk), f"missing members: {sorted(set(on_disk) - set(seen))}"
    for name, line in sorted(on_disk.items()):
        assert seen[name] == line, f"{name} reported L{seen[name]}, really on line {line}"


def test_mask_is_byte_length_preserving(tmp_path):
    """Only the two quote bytes change; length, newlines and every other byte hold."""
    src = _cs_class([
        "    public string Offender(string e) { " + OFFENDER + " return s; }",
        "    public void AfterOne() { }",
    ]).encode("utf-8")

    masked = _normalize_csharp_verbatim_interpolation(src)
    assert masked is not None, "the mask should apply to a file the grammar rejects"
    assert len(masked) == len(src)
    assert masked.count(b"\n") == src.count(b"\n")

    changed = [i for i in range(len(src)) if src[i] != masked[i]]
    assert len(changed) == 2, f"expected 2 changed bytes, got {len(changed)}"
    assert changed[1] == changed[0] + 1, "the two bytes must be adjacent"
    assert src[changed[0]:changed[0] + 2] == b'""'
    assert masked[changed[0]:changed[0] + 2] == b"  "


def test_multiline_literal_keeps_its_line_breaks(tmp_path):
    """A verbatim string may span lines; the mask must not consume a newline."""
    src = _cs_class([
        '    public string Offender(string e) { var s = $@"one',
        'two {e}"""; return s; }',
        "    public void AfterOne() { }",
    ]).encode("utf-8")

    masked = _normalize_csharp_verbatim_interpolation(src)
    assert masked is not None
    assert len(masked) == len(src)
    assert masked.count(b"\n") == src.count(b"\n")
    assert masked.splitlines()[0] == src.splitlines()[0]


def test_file_that_already_parses_is_left_alone(tmp_path):
    """No error, no rewrite -- a healthy file must never be touched."""
    src = _cs_class([
        '    public string Fine(string e) { var s = $@"a{e}b"; return s; }',
        '    public string AlsoFine(string e) { var s = $@"a""x"""; return s; }',
        "    public void AfterOne() { }",
    ]).encode("utf-8")
    assert _normalize_csharp_verbatim_interpolation(src) is None


def test_literal_spelling_inside_a_comment_is_not_treated_as_code(tmp_path):
    """The scanner skips comments, so a documented example is not rewritten."""
    src = _cs_class([
        "    // example of the broken spelling: " + OFFENDER,
        '    /* also here: var s = $@"a""{e}"""; */',
        "    public void AfterOne() { }",
    ]).encode("utf-8")
    # The file parses as written (the literal is only ever comment text), so the
    # normalizer declines -- and therefore cannot have edited the comment.
    assert _normalize_csharp_verbatim_interpolation(src) is None


def test_two_offending_literals_in_one_file(tmp_path):
    """The reporter's file carried the construct twice; one pass must clear both."""
    src = _cs_class([
        "    public string First(string e) { " + OFFENDER + " return s; }",
        "    public void Between() { }",
        "    public string Second(string e) { " + OFFENDER + " return s; }",
        "    public void Last() { }",
    ])
    raw = src.encode("utf-8")
    masked = _normalize_csharp_verbatim_interpolation(raw)
    assert masked is not None
    assert len(masked) == len(raw)
    changed = [i for i in range(len(raw)) if raw[i] != masked[i]]
    assert len(changed) == 4, f"both literals must be cleared, got {changed}"

    result = _extract(tmp_path, {"Config.cs": src})
    labels = {str(n.get("label", "")).lstrip(".") for n in result["nodes"]}
    for member in ("First()", "Between()", "Second()", "Last()"):
        assert member in labels, f"{member} missing from {sorted(labels)}"
