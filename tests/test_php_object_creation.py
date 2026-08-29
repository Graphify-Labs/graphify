"""PHP `new Foo(...)` links the constructing method to Foo (#3115).

`object_creation_expression` was absent from `_PHP_CONFIG.call_types`, so a
class a method merely constructs got no edge at all. Java has taken
`new Foo(...)` as a call since #1373 and C# since #2997; PHP never caught up.
On the reporter's Symfony corpus 505 `new X(` sites across 178 classes were
invisible - worst on message-bus code, where construction IS the control flow
(`$bus->dispatch(new SomeCommand(...))`: 0 of 22 sites had any edge).
"""
from __future__ import annotations

import tempfile
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    r = extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                root=tmp_path, parallel=False)
    labels = {n["id"]: n["label"] for n in r["nodes"]}
    calls = {(labels[e["source"]], labels[e["target"]]) for e in r["edges"]
             if e["relation"] == "calls"}
    return calls, r


FOO = "<?php\nnamespace App;\nclass Foo { public function __construct() {} }\n"
BAR = "<?php\nnamespace App;\nclass Bar { public function __construct() {} }\n"


def test_new_in_assignment_links_to_the_constructed_class(tmp_path):
    calls, _ = _extract(tmp_path, {"Foo.php": FOO, "Caller.php": (
        "<?php\nnamespace App;\nclass Caller {\n"
        "    public function run(): void { $a = new Foo(); }\n}\n")})
    assert (".run()", "Foo") in calls


def test_new_in_argument_position_links_the_message_bus_shape(tmp_path):
    """`$bus->dispatch(new Bar(2))` - construction as control flow."""
    calls, _ = _extract(tmp_path, {"Bar.php": BAR, "Caller.php": (
        "<?php\nnamespace App;\nclass Caller {\n"
        "    public function run($bus): void { $bus->dispatch(new Bar(2)); }\n}\n")})
    assert (".run()", "Bar") in calls


def test_qualified_new_names_the_last_segment(tmp_path):
    calls, _ = _extract(tmp_path, {"Bar.php": BAR, "Caller.php": (
        "<?php\nclass Caller {\n"
        "    public function run(): void { $b = new \\App\\Bar(); }\n}\n")})
    assert (".run()", "Bar") in calls


def test_dynamic_and_self_construction_produce_no_junk(tmp_path):
    """`new $cls()` names nothing; `new self()` / `new static()` name no OTHER
    class - none may mint an edge to a phantom."""
    calls, r = _extract(tmp_path, {"Caller.php": (
        "<?php\nnamespace App;\nclass Caller {\n"
        "    public function a($cls) { return new $cls(); }\n"
        "    public function b() { return new self(); }\n"
        "    public function c() { return new static(); }\n}\n")})
    labels = {n["label"] for n in r["nodes"]}
    assert not any(t in ("self", "static", "$cls") for _s, t in calls)
    assert "self" not in labels and "static" not in labels


def test_existing_static_call_edges_are_unchanged(tmp_path):
    calls, _ = _extract(tmp_path, {"Baz.php": (
        "<?php\nnamespace App;\nclass Baz {\n"
        "    public static function create(): self { return new self(); }\n}\n"),
        "Caller.php": (
        "<?php\nnamespace App;\nclass Caller {\n"
        "    public function run() { return Baz::create(); }\n}\n")})
    assert any(s == ".run()" and "Baz" in t for s, t in calls)


def test_cross_file_dispatcher_reaches_the_command_class(tmp_path):
    calls, _ = _extract(tmp_path, {
        "Command/AttachRecord.php": (
            "<?php\nnamespace App\\Command;\n"
            "class AttachRecord { public function __construct(public int $id) {} }\n"),
        "Controller/Records.php": (
            "<?php\nnamespace App\\Controller;\nuse App\\Command\\AttachRecord;\n"
            "class Records {\n"
            "    public function attach($bus): void { $bus->dispatch(new AttachRecord(7)); }\n}\n"),
    })
    assert (".attach()", "AttachRecord") in calls
