"""Record direct method signatures on named structural TypeScript aliases."""

from pathlib import Path

import pytest

from graphify.extract import extract, extract_js


def _method_edges(path: Path, source: str) -> set[tuple[str, str, str]]:
    path.write_text(source, encoding="utf-8")
    result = extract_js(path)
    nodes = {node["id"]: node for node in result["nodes"]}
    methods = set()
    for edge in result["edges"]:
        if edge["relation"] == "method":
            owner = nodes[edge["source"]]
            method = nodes[edge["target"]]
            assert Path(method["source_file"]) == path
            assert edge["source_location"] == method["source_location"]
            methods.add((owner["label"], method["label"], method["source_location"]))
    return methods


@pytest.mark.parametrize("suffix", [".ts", ".tsx"])
def test_object_type_aliases_keep_direct_method_signatures(tmp_path, suffix):
    methods = _method_edges(
        tmp_path / f"ports{suffix}",
        "interface InterfacePort { read(): number }\n"
        "type AliasPort = {\n"
        "  read(): number;\n"
        "  inner: { nested(): number };\n"
        "};\n"
        "type ReadonlyPort = Readonly</* member contract */ {\n"
        "  read(): number;\n"
        "}>;\n",
    )
    assert methods == {
        ("InterfacePort", ".read()", "L1"),
        ("AliasPort", ".read()", "L3"),
        ("ReadonlyPort", ".read()", "L7"),
    }


def test_unrelated_generic_and_nested_members_are_not_alias_methods(tmp_path):
    path = tmp_path / "ports.ts"
    path.write_text(
        "type Box<T> = { inner: T };\n"
        "type BoxedPort = Box<{ boxed(): number }>;\n"
        "type QualifiedPort = Custom.Readonly<{ qualified(): number }>;\n"
        "type NestedPort = { inner: Readonly<{ nested(): number }> };\n",
        encoding="utf-8",
    )
    result = extract_js(path)
    assert not any(edge["relation"] == "method" for edge in result["edges"])
    assert not any(node["label"].endswith("()") for node in result["nodes"])


@pytest.mark.parametrize(
    "declaration",
    [
        "type Readonly<T> = { inner: T };",
        "import type { Wrapper as Readonly } from './wrapper';",
    ],
)
def test_shadowed_readonly_does_not_expose_methods_of_its_type_argument(tmp_path, declaration):
    methods = _method_edges(
        tmp_path / "ports.ts",
        f"{declaration}\n"
        "type WrappedPort = Readonly<{ wrapped(): number }>;\n"
        "type DirectPort = { direct(): number };\n",
    )
    assert methods == {("DirectPort", ".direct()", "L3")}


def test_alias_method_calls_require_a_typed_receiver(tmp_path):
    ports = tmp_path / "ports.ts"
    ports.write_text(
        "function read(): number { return 0; }\n"
        "type AliasPort = { read(): number };\n"
        "type ReadonlyPort = Readonly<{ read(): number }>;\n"
        "type OtherPort = { onlyOnPort(): number };\n"
        "function useBare() { return read(); }\n"
        "function useAlias(port: AliasPort) { return port.read(); }\n"
        "function useReadonly(wrapped: ReadonlyPort) { return wrapped.read(); }\n"
        "function useStatic() { return AliasPort.read(); }\n"
        "function useUnknown(x: unknown) { return x.read(); }\n",
        encoding="utf-8",
    )
    caller = tmp_path / "caller.ts"
    caller.write_text(
        "import './ports';\nfunction useUnresolved() { return onlyOnPort(); }\n",
        encoding="utf-8",
    )
    result = extract([ports, caller], root=tmp_path, cache_root=tmp_path / "cache")
    nodes = {node["label"]: node["id"] for node in result["nodes"]}
    methods = {
        edge["source"]: edge["target"] for edge in result["edges"] if edge["relation"] == "method"
    }
    checked_callers = {
        nodes[name]
        for name in (
            "useBare()",
            "useAlias()",
            "useReadonly()",
            "useStatic()",
            "useUnknown()",
            "useUnresolved()",
        )
    }
    calls = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge["relation"] == "calls" and edge["source"] in checked_callers
    }
    assert calls == {
        (nodes["useBare()"], nodes["read()"]),
        (nodes["useAlias()"], methods[nodes["AliasPort"]]),
        (nodes["useReadonly()"], methods[nodes["ReadonlyPort"]]),
    }


def test_alias_methods_are_not_same_file_base_types(tmp_path):
    (tmp_path / "base.d.ts").write_text("declare class Base {}\n", encoding="utf-8")
    ports = tmp_path / "ports.ts"
    ports.write_text(
        '/// <reference path="./base.d.ts" />\n'
        "export type AliasPort = { Base(): number };\n"
        "class Derived extends Base {}\n",
        encoding="utf-8",
    )
    result = extract([ports], root=tmp_path, cache_root=tmp_path / "cache")
    method = next(node for node in result["nodes"] if node["label"] == ".Base()")
    assert not any(
        edge["relation"] == "inherits" and edge["target"] == method["id"]
        for edge in result["edges"]
    )
