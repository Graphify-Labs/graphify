"""PHP `new Foo(...)` links the constructing method to Foo.

`_PHP_CONFIG.call_types` never listed `object_creation_expression`, so a
method that only constructed a class — never called a method on it — got no
edge to it at all. Java has taken `new Foo(...)` as a call since #1373, C#
caught up in #2998; PHP had not. Message-bus code is the sharpest case:
`$bus->dispatch(new SomeCommand(...))` is exactly the shape where
construction *is* the control flow, and none of it showed up (#3115).

Unlike Java (`type` field) and C# (`type` field), tree-sitter-php exposes no
named fields on `object_creation_expression` at all — `new`, the class name,
and the argument list are purely positional — so this needed its own branch
in `walk_calls` rather than reusing either existing one.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract([Path(n) for n in files], cache_root=Path(tempfile.mkdtemp()))
    finally:
        os.chdir(old)
    calls = {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == "calls"}
    return calls, r


def _find(r, label, id_contains):
    return next(n["id"] for n in r["nodes"]
                if n["label"] == label and id_contains in n["id"])


def test_assignment_position_links_to_constructed_type(tmp_path):
    calls, r = _extract(tmp_path, {"S.php": (
        "<?php\n"
        "class Foo { public function __construct(public int $x = 0) {} }\n"
        "class Caller {\n"
        "    public function run() { $a = new Foo(1); }\n"
        "}\n"
    )})
    assert (_find(r, ".run()", "caller"), _find(r, "Foo", "foo")) in calls


def test_argument_position_links_to_constructed_type(tmp_path):
    # The message-bus shape from #3115: the constructed type never appears in
    # a declared/assigned position, only as a call argument.
    calls, r = _extract(tmp_path, {"S.php": (
        "<?php\n"
        "class Bar { public function __construct(public int $y = 0) {} }\n"
        "class Caller {\n"
        "    public function run(Bus $bus) { $bus->dispatch(new Bar(2)); }\n"
        "}\n"
    )})
    assert (_find(r, ".run()", "caller"), _find(r, "Bar", "bar")) in calls


def test_qualified_construction_names_the_last_segment(tmp_path):
    calls, r = _extract(tmp_path, {"S.php": (
        "<?php\n"
        "namespace App;\n"
        "class Baz { public static function create(): self { return new self(); } }\n"
        "class Caller {\n"
        "    public function run() { $c = new \\App\\Baz(); }\n"
        "}\n"
    )})
    assert (_find(r, ".run()", "caller"), _find(r, "Baz", "baz")) in calls


def test_static_call_still_resolves(tmp_path):
    # Guard: adding object_creation_expression to call_types must not disturb
    # the existing scoped_call_expression (Baz::create()) path.
    calls, r = _extract(tmp_path, {"S.php": (
        "<?php\n"
        "class Baz { public static function create(): self { return new self(); } }\n"
        "class Caller {\n"
        "    public function run() { $c = Baz::create(); }\n"
        "}\n"
    )})
    assert (_find(r, ".run()", "caller"), _find(r, "Baz", "baz")) in calls


def test_member_call_still_resolves(tmp_path):
    # Guard: member_call_expression ($obj->method()) must not be swept into
    # the new object_creation_expression branch.
    calls, r = _extract(tmp_path, {"S.php": (
        "<?php\n"
        "class Worker { public function work() {} }\n"
        "class Caller {\n"
        "    public function run(Worker $w) { $w->work(); }\n"
        "}\n"
    )})
    assert (_find(r, ".run()", "caller"), _find(r, ".work()", "worker")) in calls


def test_all_three_call_shapes_in_one_method(tmp_path):
    # The exact repro from #3115: only the static call produced an edge
    # before the fix; both `new` sites were silently dropped.
    calls, r = _extract(tmp_path, {"S.php": (
        "<?php\n"
        "class Foo { public function __construct(public int $x = 0) {} }\n"
        "class Bar { public function __construct(public int $y = 0) {} }\n"
        "class Baz { public static function create(): self { return new self(); } }\n"
        "class Caller {\n"
        "    public function run(Bus $bus) {\n"
        "        $a = new Foo(1);\n"
        "        $bus->dispatch(new Bar(2));\n"
        "        $c = Baz::create();\n"
        "    }\n"
        "}\n"
    )})
    run = _find(r, ".run()", "caller")
    assert (run, _find(r, "Foo", "foo")) in calls
    assert (run, _find(r, "Bar", "bar")) in calls
    assert (run, _find(r, "Baz", "baz")) in calls
