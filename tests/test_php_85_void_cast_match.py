"""PHP 8.5 `(void)` casts and cast match arms must still extract (#4202).

tree-sitter-php 0.24/0.25 has no `void` cast_type, and a cast operand may only
be a unary/include/error-suppression expression. `(void) SomeClass::method()`
therefore becomes an ERROR (often on the class name), and
`return (string) match { Enum::Case => ... }` drops the arms. When recovery
swallows the declaration the file contributes no symbols. Blanking the cast
before the parse is the fix; suppressing the warning is not.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract, extract_php


def _labels(result):
    return {n["label"] for n in result["nodes"]}


def _calls(result):
    labels = {n["id"]: n["label"] for n in result["nodes"]}
    return {
        (labels[e["source"]], labels[e["target"]])
        for e in result["edges"]
        if e["relation"] == "calls"
    }


def _write(tmp_path: Path, name: str, body: str) -> Path:
    path = tmp_path / name
    path.write_text(body, encoding="utf-8")
    return path


def test_void_cast_keeps_class_method_and_static_call(tmp_path):
    """`(void) SomeClass::someMethod(...)` must not erase the enclosing symbols."""
    path = _write(tmp_path, "Widget.php", """<?php
namespace App;

class SomeClass {
    public static function someMethod($argument): void {}
}

class Widget {
    public function go($argument): void {
        (void) SomeClass::someMethod($argument);
    }
}
""")
    result = extract_php(path)
    assert result.get("parse_errors") is None
    assert "Widget" in _labels(result)
    assert ".go()" in _labels(result)
    assert (".go()", "SomeClass") in _calls(result)


def test_cast_match_keeps_arm_calls(tmp_path):
    """`return (string) match { Enum::Case => $object->first() }` keeps the arms."""
    path = _write(tmp_path, "Mode.php", """<?php
namespace App;

class Mode {
    public function run($mode): string {
        return (string) match ($mode) {
            SomeEnum::First => $this->first(),
            SomeEnum::Second => $this->second(),
        };
    }

    public function first(): string { return "a"; }
    public function second(): string { return "b"; }
}
""")
    result = extract_php(path)
    assert result.get("parse_errors") is None
    assert "Mode" in _labels(result)
    assert ".run()" in _labels(result)
    assert (".run()", ".first()") in _calls(result)
    assert (".run()", ".second()") in _calls(result)


def test_void_return_type_is_not_rewritten(tmp_path):
    """`: void` is a return type, not a cast, and must still yield the method."""
    path = _write(tmp_path, "Task.php", """<?php
namespace App;

class Task {
    public function run(): void {
        $this->work();
    }

    public function work(): void {}
}
""")
    result = extract_php(path)
    assert result.get("parse_errors") is None
    labels = _labels(result)
    assert "Task" in labels
    assert ".run()" in labels
    assert ".work()" in labels
    assert (".run()", ".work()") in _calls(result)


def test_void_literal_in_string_does_not_hide_the_real_cast(tmp_path):
    path = _write(tmp_path, "Keep.php", """<?php
namespace App;

class Other {
    public static function ping($argument): void {}
}

class Keep {
    public function run($argument): void {
        $note = '(void)';
        (void) Other::ping($argument);
    }
}
""")
    result = extract_php(path)
    assert result.get("parse_errors") is None
    assert "Keep" in _labels(result)
    assert ".run()" in _labels(result)
    assert (".run()", "Other") in _calls(result)


def test_issue_snippets_survive_corpus_extract(tmp_path):
    """The two snippets from #4202 still produce symbols through extract()."""
    files = {
        "Void.php": """<?php
namespace App;
class SomeClass { public static function someMethod($argument): void {} }
class VoidDemo {
    public function go($argument): void {
        (void) SomeClass::someMethod($argument);
    }
}
""",
        "Match.php": """<?php
namespace App;
class MatchDemo {
    public function run($mode, $object): string {
        return (string) match ($mode) {
            SomeEnum::First => $object->first(),
            SomeEnum::Second => $object->second(),
        };
    }
}
""",
    }
    paths = [_write(tmp_path, name, body) for name, body in files.items()]
    result = extract(paths, cache_root=Path(tempfile.mkdtemp()), root=tmp_path, parallel=False)
    labels = _labels(result)
    assert "VoidDemo" in labels
    assert ".go()" in labels
    assert "MatchDemo" in labels
    assert ".run()" in labels
    assert (".go()", "SomeClass") in _calls(result)
