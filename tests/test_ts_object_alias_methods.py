"""Record direct callable members on named structural TypeScript aliases."""

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


@pytest.mark.parametrize("suffix", [".ts", ".tsx"])
def test_object_type_aliases_keep_direct_callable_properties(tmp_path, suffix):
    methods = _method_edges(
        tmp_path / f"ports{suffix}",
        "interface InterfacePort { callback: () => number }\n"
        "type AliasPort = {\n"
        "  read: () => number;\n"
        "  readonly maybeRead?: (/* annotated */ () => number);\n"
        "  name: string;\n"
        "  inner: { nested: () => number };\n"
        "  fallback: (() => number) | undefined;\n"
        "};\n"
        "type ReadonlyPort = Readonly<{\n"
        "  read: () => number;\n"
        "}>;\n",
    )
    assert methods == {
        ("AliasPort", ".read()", "L3"),
        ("AliasPort", ".maybeRead()", "L4"),
        ("ReadonlyPort", ".read()", "L10"),
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


def test_unrelated_generic_parameter_does_not_hide_readonly_alias(tmp_path):
    methods = _method_edges(
        tmp_path / "ports.ts",
        "function identity<Readonly>(item: Readonly): Readonly { return item; }\n"
        "type WrappedPort = Readonly<{ read(): number }>;\n"
        "type GenericPort<Readonly> = Readonly<{ hidden(): number }>;\n",
    )
    assert methods == {("WrappedPort", ".read()", "L2")}


def test_readonly_declaration_only_shadows_its_lexical_scope(tmp_path):
    methods = _method_edges(
        tmp_path / "ports.ts",
        "namespace Local {\n"
        "  type Shadowed = Readonly<{ hidden(): number }>;\n"
        "  type Readonly<T> = { inner: T };\n"
        "}\n"
        "namespace Local { type Reopened = Readonly<{ write(): number }>; }\n"
        "namespace Other { type Visible = Readonly<{ read(): number }>; }\n"
        "type Outside = Readonly<{ open(): number }>;\n",
    )
    assert methods == {
        ("Reopened", ".write()", "L5"),
        ("Visible", ".read()", "L6"),
        ("Outside", ".open()", "L7"),
    }


@pytest.mark.parametrize(
    ("first", "second"),
    [
        (
            "namespace API./* nested */Ports { export type Wrapped = Readonly<{ hidden(): number }>; }",
            "namespace API { export type Readonly<T> = { inner: T }; }",
        ),
        (
            "namespace API { export type Wrapped = Readonly<{ hidden(): number }>; }",
            "namespace API { export declare class Readonly<T> { inner: T; } }",
        ),
        (
            "declare namespace API { namespace Ports { type Wrapped = Readonly<{ hidden(): number }>; } }",
            "declare namespace API { namespace Ports { type Readonly<T> = { inner: T }; } }",
        ),
    ],
)
def test_exported_readonly_shadows_across_reopened_namespaces(tmp_path, first, second):
    methods = _method_edges(
        tmp_path / "ports.ts",
        f"{first}\n{second}\ntype Outside = Readonly<{{ open(): number }}>;\n",
    )
    assert methods == {("Outside", ".open()", "L3")}


def test_ambient_import_only_shadows_its_own_module_body(tmp_path):
    methods = _method_edges(
        tmp_path / "ports.ts",
        "declare module 'base' { type Readonly<T> = { inner: T }; }\n"
        "declare module 'pkg' { import type { Readonly } from 'base';\n"
        "  type Hidden = Readonly<{ hidden(): number }>; }\n"
        "declare module 'pkg' { type Visible = Readonly<{ open(): number }>; }\n",
    )
    assert methods == {("Visible", ".open()", "L4")}


def test_alias_method_calls_require_a_typed_receiver(tmp_path):
    ports = tmp_path / "ports.ts"
    ports.write_text(
        "function identity<Readonly>(item: Readonly): Readonly { return item; }\n"
        "function read(): number { return 0; }\n"
        "export type AliasPort = { read(): number };\n"
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
        "import type { AliasPort } from './ports';\n"
        "function useImported(imported: AliasPort) { return imported.read(); }\n"
        "function useUnresolved() { return onlyOnPort(); }\n",
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
            "useImported()",
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
        (nodes["useImported()"], methods[nodes["AliasPort"]]),
    }


def test_imported_alias_callable_properties_resolve_to_distinct_members(tmp_path):
    ports = tmp_path / "ports.ts"
    ports.write_text(
        "export type Port = Readonly<{ read(): number; _read: () => number }>;\n",
        encoding="utf-8",
    )
    caller = tmp_path / "caller.ts"
    caller.write_text(
        "import type { Port } from './ports';\n"
        "function _read() { return 0; }\n"
        "function useBare() { return _read(); }\n"
        "function useMethod(port: Port) { return port.read(); }\n"
        "function useProperty(port: Port) { return port._read(); }\n",
        encoding="utf-8",
    )
    result = extract([ports, caller], root=tmp_path, cache_root=tmp_path / "cache")
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    assert {
        labels[edge["target"]]
        for edge in result["edges"]
        if edge["relation"] == "method" and labels[edge["source"]] == "Port"
    } == {".read()", "._read()"}
    assert {
        (labels[edge["source"]], labels[edge["target"]])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    } == {
        ("useBare()", "_read()"),
        ("useMethod()", ".read()"),
        ("useProperty()", "._read()"),
    }


@pytest.mark.parametrize("include_base", [False, True])
def test_alias_methods_do_not_supply_a_base_class(tmp_path, include_base):
    ports = tmp_path / "ports.ts"
    if include_base:
        base_declaration = "class Base {}\n"
    else:
        # The declaration exists in TypeScript but is outside the extraction.
        (tmp_path / "base.d.ts").write_text("declare class Base {}\n", encoding="utf-8")
        base_declaration = '/// <reference path="./base.d.ts" />\n'
    ports.write_text(
        base_declaration + "export type AliasPort = { Base(): number };\n"
        "class Derived extends Base {}\n",
        encoding="utf-8",
    )
    result = extract([ports], root=tmp_path, cache_root=tmp_path / "cache")
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    assert ".Base()" in labels.values()
    assert {
        labels[edge["target"]]
        for edge in result["edges"]
        if edge["relation"] == "inherits" and labels[edge["source"]] == "Derived"
    } == ({"Base"} if include_base else set())
