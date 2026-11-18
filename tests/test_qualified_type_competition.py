"""Adding an unrelated type must not erase a uniquely qualified call (#5185)."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from graphify.extract import extract


CASES = [
    ("csharp-nested", "cs",
     "public class Left { public class Builder { public void setEnabled(bool v) {} } }\n",
     "public class Caller { public void run(Left.Builder b) { b.setEnabled(true); } }\n",
     "public class Right { public class Builder { public void setEnabled(bool v) {} } }\n"),
    ("csharp-namespace", "cs",
     "namespace Left { public class Builder { public void setEnabled(bool v) {} } }\n",
     "public class Caller { public void run(Left.Builder b) { b.setEnabled(true); } }\n",
     "namespace Right { public class Builder { public void setEnabled(bool v) {} } }\n"),
    ("csharp-global-nested", "cs",
     "public class Left { public class Builder { public void setEnabled(bool v) {} } }\n",
     "public class Caller { public void run(global::Left.Builder b) { b.setEnabled(true); } }\n",
     "public class Right { public class Builder { public void setEnabled(bool v) {} } }\n"),
    ("csharp-inherited-nested", "cs",
     "public class Parent { public class Builder { public void setEnabled(bool v) {} } }\n"
     "public class Child : Parent {}\n",
     "public class Caller { public void run(Child.Builder b) { b.setEnabled(true); } }\n",
     "public class Right { public class Builder { public void setEnabled(bool v) {} } }\n"),
    ("csharp-global-inherited-nested", "cs",
     "public class Parent { public class Builder { public void setEnabled(bool v) {} } }\n"
     "public class Child : Parent {}\n",
     "public class Caller { public void run(global::Child.Builder b) { b.setEnabled(true); } }\n",
     "public class Right { public class Builder { public void setEnabled(bool v) {} } }\n"),
    ("csharp-using-control", "cs",
     "namespace Left { public class Builder { public void setEnabled(bool v) {} } }\n",
     "using Left;\npublic class Caller { public void run(Builder b) { b.setEnabled(true); } }\n",
     "namespace Right { public class Builder { public void setEnabled(bool v) {} } }\n"),
    ("kotlin-imported-object", "kt",
     "package left\nobject Builder {\n fun setEnabled(v: Boolean) {}\n}\n",
     "import left.Builder\nclass Caller {\n fun run() { Builder.setEnabled(true) }\n}\n",
     "package right\nobject Builder {\n fun setEnabled(v: Boolean) {}\n}\n"),
    ("swift-static", "swift",
     "class Builder {\n static func setEnabled(_ v: Bool) {}\n}\n",
     "class Caller {\n func run() { Builder.setEnabled(true) }\n}\n",
     "class Right {\n class Builder {\n static func setEnabled(_ v: Bool) {}\n }\n}\n"),
    ("swift-qualified-static", "swift",
     "class Left {\n class Builder {\n static func setEnabled(_ v: Bool) {}\n }\n}\n",
     "class Caller {\n func run() { Left.Builder.setEnabled(true) }\n}\n",
     "class Right {\n class Builder {\n static func setEnabled(_ v: Bool) {}\n }\n}\n"),
    ("swift-qualified-parameter", "swift",
     "class Left {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n",
     "class Caller {\n func run(_ b: Left.Builder) { b.setEnabled(true) }\n}\n",
     "class Right {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n"),
    ("swift-qualified-constructor", "swift",
     "class Left {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n",
     "class Caller {\n func run() {\n let b = Left.Builder()\n b.setEnabled(true)\n }\n}\n",
     "class Right {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n"),
    ("swift-deep-qualified-constructor", "swift",
     "class Left {\n class Group {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n }\n}\n",
     "class Caller {\n func run() {\n let b = Left.Group.Builder()\n b.setEnabled(true)\n }\n}\n",
     "class Right {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n"),
    ("cpp-qualified-control", "hpp",
     "struct Left { struct Builder { void setEnabled(bool v) {} }; };\n",
     '#include "Left.hpp"\nvoid run(Left::Builder& b) { b.setEnabled(true); }\n',
     "struct Right { struct Builder { void setEnabled(bool v) {} }; };\n"),
    ("typescript-imported-control", "ts",
     "export class Builder { setEnabled(v: boolean): void {} }\n",
     'import { Builder } from "./Left";\nexport function run(b: Builder): void { b.setEnabled(true); }\n',
     "export class Builder { setEnabled(v: boolean): void {} }\n"),
]


@pytest.mark.parametrize("name,suffix,target,caller,competitor", CASES, ids=[case[0] for case in CASES])
@pytest.mark.parametrize("reverse", [False, True])
def test_competing_type_preserves_explicit_receiver(
    tmp_path: Path, name: str, suffix: str, target: str,
    caller: str, competitor: str, reverse: bool,
):
    left = tmp_path / f"Left.{suffix}"
    use = tmp_path / ("Caller.cpp" if suffix == "hpp" else f"Caller.{suffix}")
    right = tmp_path / f"Right.{suffix}"
    left.write_text(target, encoding="utf-8")
    use.write_text(caller, encoding="utf-8")
    selected_id = None
    for added in (False, True):
        paths = [left, use]
        if added:
            right.write_text(competitor, encoding="utf-8")
            paths.append(right)
        if reverse:
            paths.reverse()
        for _ in range(2):
            result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
            assert not result["failed_sources"]
            assert not result["skipped_sources"]
            nodes = {n["id"]: n for n in result["nodes"]}
            methods = [n for n in nodes.values() if n.get("source_file") and n["label"] == ".setEnabled()"]
            assert len(methods) == 1 + added
            selected = [n["id"] for n in methods if Path(n["source_file"]).name == left.name]
            assert len(selected) == 1
            if selected_id is None:
                selected_id = selected[0]
            assert selected == [selected_id]
            targets = {
                e["target"] for e in result["edges"]
                if e["relation"] == "calls"
                and nodes[e["source"]]["label"].lstrip(".") == "run()"
                and Path(nodes[e["source"]].get("source_file", "")).name == use.name
                and e["target"] in {n["id"] for n in methods}
            }
            assert targets == {selected_id}, name


@pytest.mark.parametrize("suffix,target,caller", [
    ("cs",
     "public class Builder { public void setEnabled(bool v) {} }\n",
     "class Caller { void run(Missing.Builder b) { b.setEnabled(true); } }\n"),
    ("cs",
     "namespace Local { public class Left { public class Builder { public void setEnabled(bool v) {} } } }\n",
     "namespace Local { class Caller { void run(global::Left.Builder b) { b.setEnabled(true); } } }\n"),
    ("kt",
     "package left\nobject Builder {\n fun setEnabled(v: Boolean) {}\n}\n",
     "import missing.Builder\nclass Caller {\n fun run() { Builder.setEnabled(true) }\n}\n"),
])
def test_absent_explicit_type_never_falls_back_to_bare_name(
    tmp_path: Path, suffix: str, target: str, caller: str,
):
    paths = [tmp_path / f"Left.{suffix}", tmp_path / f"Caller.{suffix}"]
    for path, body in zip(paths, (target, caller)):
        path.write_text(body, encoding="utf-8")
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}
    assert not [
        e for e in result["edges"] if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == ".run()"
        and nodes[e["target"]]["label"] == ".setEnabled()"
    ]


def test_swift_nested_lexical_type_beats_unrelated_top_level_type(tmp_path: Path):
    path = tmp_path / "Types.swift"
    path.write_text(
        "class Outer {\n"
        " class Builder {\n static func setEnabled(_ v: Bool) {}\n }\n"
        " func run() { Builder.setEnabled(true) }\n"
        "}\n"
        "class Builder {\n static func setEnabled(_ v: Bool) {}\n}\n",
        encoding="utf-8",
    )
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}
    targets = [
        nodes[e["target"]] for e in result["edges"] if e["relation"] == "calls"
        and nodes[e["source"]]["label"] == ".run()"
        and nodes[e["target"]]["label"] == ".setEnabled()"
    ]
    assert len(targets) == 1
    assert targets[0]["source_location"] == "L3"


@pytest.mark.parametrize("constructor", ["Right.Builder()", "Missing.Builder()"])
def test_swift_qualified_constructor_does_not_guess_an_unrelated_method(
    tmp_path: Path, constructor: str,
):
    path = tmp_path / "Types.swift"
    path.write_text(
        "class Left {\n class Builder {\n func setEnabled(_ v: Bool) {}\n }\n}\n"
        "class Right {\n class Builder {}\n}\n"
        f"class Caller {{\n func run() {{\n let b = {constructor}\n b.setEnabled(true)\n }}\n}}\n",
        encoding="utf-8",
    )
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not result["failed_sources"]
    assert not result["skipped_sources"]
    nodes = {node["id"]: node for node in result["nodes"]}
    assert not [
        edge for edge in result["edges"]
        if edge["relation"] == "calls"
        and nodes[edge["source"]]["label"] == ".run()"
        and nodes[edge["target"]]["label"] == ".setEnabled()"
    ]


@pytest.mark.parametrize("child", [
    "public class Child : Parent { public new class Builder {} }",
    "public class Child : Missing {}",
])
def test_csharp_inherited_nested_lookup_does_not_bypass_a_missing_or_hidden_type(
    tmp_path: Path, child: str,
):
    path = tmp_path / "Types.cs"
    path.write_text(
        "public class Parent { public class Builder { public void setEnabled(bool v) {} } }\n"
        + child
        + "\npublic class Caller { public void run(Child.Builder b) { b.setEnabled(true); } }\n",
        encoding="utf-8",
    )
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    assert not result["failed_sources"]
    assert not result["skipped_sources"]
    nodes = {node["id"]: node for node in result["nodes"]}
    assert not [
        edge for edge in result["edges"]
        if edge["relation"] == "calls"
        and nodes[edge["source"]]["label"] == ".run()"
        and nodes[edge["target"]]["label"] == ".setEnabled()"
    ]


@pytest.mark.parametrize("qualifier,namespace,type_path", [
    ("Left.Builder", "Local", "Left.Builder"),
    ("global::Left.Builder", "Left", "Builder"),
])
def test_csharp_qualified_type_respects_lexical_shadowing(
    tmp_path: Path, qualifier: str, namespace: str, type_path: str,
):
    path = tmp_path / "Types.cs"
    path.write_text(
        "namespace Left { public class Builder { public void setEnabled(bool v) {} } }\n"
        "namespace Local {\n"
        " public class Left { public class Builder { public void setEnabled(bool v) {} } }\n"
        f" public class Caller {{ public void run({qualifier} b) {{ b.setEnabled(true); }} }}\n"
        "}\n",
        encoding="utf-8",
    )
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}
    owners = {e["target"]: nodes[e["source"]] for e in result["edges"] if e["relation"] == "method"}
    targets = [
        owners[e["target"]]["metadata"] for e in result["edges"]
        if e["relation"] == "calls" and nodes[e["source"]]["label"] == ".run()"
    ]
    assert len(targets) == 1
    assert targets[0]["namespace"] == namespace
    assert targets[0]["type_path"] == type_path


@pytest.mark.parametrize("import_statement,receiver,expected", [
    ("import external.Builder as OtherBuilder", "Builder", True),
    ("import local.Builder as LocalBuilder", "LocalBuilder", True),
    ("import external.Builder as ExternalBuilder", "ExternalBuilder", False),
])
def test_kotlin_import_alias_only_binds_its_local_name(
    tmp_path: Path, import_statement: str, receiver: str, expected: bool,
):
    paths = [tmp_path / "Left.kt", tmp_path / "Caller.kt"]
    for path, body in zip(paths, (
        "package local\nobject Builder { fun setEnabled(v: Boolean) {} }\n",
        f"package local\n{import_statement}\n"
        f"class Caller {{ fun run() {{ {receiver}.setEnabled(true) }} }}\n",
    )):
        path.write_text(body, encoding="utf-8")
    result = extract(paths, root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    nodes = {n["id"]: n for n in result["nodes"]}
    targets = [
        nodes[e["target"]]["source_file"] for e in result["edges"]
        if e["relation"] == "calls" and nodes[e["source"]]["label"] == ".run()"
    ]
    assert targets == (["Left.kt"] if expected else [])


INCREMENTAL_CASES = [
    case for case in CASES if case[0] in {
        "csharp-nested", "csharp-namespace", "kotlin-imported-object", "swift-static",
        "swift-qualified-static", "swift-qualified-parameter",
        "swift-qualified-constructor", "swift-deep-qualified-constructor",
        "csharp-inherited-nested", "csharp-global-inherited-nested",
    }
]


@pytest.mark.parametrize("backend", ["watch", "cli"])
@pytest.mark.parametrize(
    "name,suffix,target,caller,competitor", INCREMENTAL_CASES,
    ids=[case[0] for case in INCREMENTAL_CASES],
)
def test_changed_caller_keeps_unchanged_qualified_type_facts(
    tmp_path: Path, backend: str, name: str, suffix: str,
    target: str, caller: str, competitor: str,
):
    from graphify.watch import _rebuild_code

    left, use, right = [tmp_path / f"{stem}.{suffix}" for stem in ("Left", "Caller", "Right")]
    for path, body in zip((left, use, right), (target, caller, competitor)):
        path.write_text(body, encoding="utf-8")

    def rebuild():
        if backend == "watch":
            assert _rebuild_code(
                tmp_path, incremental=True, no_cluster=True, acquire_lock=False,
            )
        else:
            result = subprocess.run(
                [sys.executable, "-B", "-m", "graphify", "extract", ".", "--code-only", "--no-cluster"],
                cwd=tmp_path,
                env=dict(os.environ, PYTHONPATH=str(Path(__file__).resolve().parents[1])),
                capture_output=True, text=True, timeout=90,
            )
            assert result.returncode == 0, result.stdout + result.stderr

    def targets():
        graph = json.loads((tmp_path / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        nodes = {n["id"]: n for n in graph["nodes"]}
        return {
            e["target"] for e in graph.get("links", graph.get("edges", []))
            if e["relation"] == "calls"
            and nodes[e["source"]]["label"].rsplit(".", 1)[-1] == "run()"
            and nodes[e["target"]]["label"].rsplit(".", 1)[-1] == "setEnabled()"
            and Path(nodes[e["target"]].get("source_file", "")).name == left.name
        }

    rebuild()
    before = targets()
    assert len(before) == 1, name
    use.write_text(caller + "\n// changed caller\n", encoding="utf-8")
    rebuild()
    assert targets() == before, name
