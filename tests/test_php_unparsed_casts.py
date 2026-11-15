"""PHP 8.5 `(void)` casts and casts applied to `match (...)` (#4202).

tree-sitter-php has no `(void)` cast and cannot parse `(string) match (...)`,
so those statements came out as ERROR nodes: the call behind the cast was lost
and the file got a partial-extraction warning. extract_php blanks just the cast
(same length, code only) before parsing.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import (
    _PHP_CONFIG,
    _extract_generic,
    _php_blank_unparsed_casts,
    extract,
    extract_php,
)

CACHE = (
    "<?php\nnamespace App;\n"
    "class Cache {\n    public static function warm(string $k): bool { return true; }\n}\n"
)


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        (tmp_path / name).write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(labels[e["source"]], labels[e["target"]]) for e in r["edges"]
             if e["relation"] == "calls"}
    return calls, r


KERNEL = (
    "<?php\nnamespace App;\nclass Kernel {\n"
    "    public function boot(): void {\n"
    "        {cast}Cache::warm('routes');\n"
    "        {cast}$this->ready();\n"
    "    }\n"
    "    private function ready(): void {}\n}\n"
)


def test_void_cast_keeps_the_call_and_parses_cleanly(tmp_path):
    """`(void) X::m()` yields the same call edges as plain `X::m()`."""
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    calls, _ = _extract(tmp_path / "a", {"Cache.php": CACHE,
                                         "Kernel.php": KERNEL.replace("{cast}", "(void) ")})
    plain, _ = _extract(tmp_path / "b", {"Cache.php": CACHE,
                                         "Kernel.php": KERNEL.replace("{cast}", "")})
    assert (".boot()", ".ready()") in calls
    assert any(s == ".boot()" and t != ".ready()" for s, t in calls)  # the Cache::warm call
    assert calls == plain
    assert "parse_errors" not in extract_php(tmp_path / "a" / "Kernel.php")


def test_cast_on_match_parses_and_keeps_what_follows(tmp_path):
    calls, _ = _extract(tmp_path, {"Picker.php": (
        "<?php\nnamespace App;\nclass Picker {\n"
        "    public function label(int $mode): string {\n"
        "        return (string) match ($mode) {\n"
        "            1 => $this->first(),\n"
        "            default => $this->second(),\n"
        "        };\n"
        "    }\n"
        "    public function first(): int { return 1; }\n"
        "    public function second(): int { return 2; }\n"
        "    public function after(): string { return $this->label(1); }\n}\n")})
    assert {(".label()", ".first()"), (".label()", ".second()"),
            (".after()", ".label()")} <= calls
    assert "parse_errors" not in extract_php(tmp_path / "Picker.php")


def test_strings_and_comments_are_never_blanked():
    src = (
        b"<?php\n// (void) foo();\n/* (string) match (x) */\n"
        b"$a = '(void) Foo::bar();';\n$b = \"(int) match (1) {$a}\";\n"
        b"$c = <<<TXT\n(void) Heredoc::thing();\nTXT;\n"
        b"$d = <<<'RAW'\n(bool) match (y) {}\nRAW;\n?>\n<p>(void) html</p>\n"
    )
    assert _php_blank_unparsed_casts(src) == src


def test_blanking_keeps_offsets_and_line_numbers():
    src = b"<?php\n(\n  VOID\n) foo();\n$x = (string)\n  match (1) { 1 => 2 };\n"
    out = _php_blank_unparsed_casts(src)
    assert len(out) == len(src)
    assert [i for i, ch in enumerate(out) if ch == 10] == [i for i, ch in enumerate(src) if ch == 10]
    assert b"VOID" not in out and b"(string)" not in out and b"match (1)" in out


def test_files_without_the_pattern_extract_exactly_as_before(tmp_path):
    p = tmp_path / "Plain.php"
    p.write_text("<?php\nclass Plain {\n    public function a(): int { return (int) '3'; }\n}\n",
                 encoding="utf-8")
    assert extract_php(p) == _extract_generic(p, _PHP_CONFIG)
