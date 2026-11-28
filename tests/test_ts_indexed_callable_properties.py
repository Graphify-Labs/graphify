"""Resolve a structural call to the receiving indexed-access property."""

import pytest

from graphify.extract import extract


@pytest.mark.parametrize("suffix", [".ts", ".tsx"])
def test_indexed_callable_properties_belong_to_the_receiving_type(tmp_path, suffix):
    ports = tmp_path / f"ports{suffix}"
    ports.write_text(
        "export interface Api {\n"
        "  dispatch: Store['run'];\n"
        "}\n"
        "export interface Store { run(): number }\n"
        "type Runner = { readonly run: (() => number) };\n"
        "type ReadonlyApi = Readonly<{\n"
        '  execute: Runner[/* source member */ "run"];\n'
        "}>;\n"
        "function dispatch() { return 0; }\n"
        # Each `api` belongs to a different lexical scope.
        "function useInterface(api: Api) { return api.dispatch(); }\n"
        "function useReadonly(api: ReadonlyApi) { return api.execute(); }\n"
        "function useStatic() { return ReadonlyApi.execute(); }\n"
        "function useBare() { return dispatch() + execute(); }\n"
        "function useUnknown(api: unknown) { return api.execute(); }\n",
        encoding="utf-8",
    )
    result = extract([ports], root=tmp_path, cache_root=tmp_path / "cache")
    nodes = {node["id"]: node for node in result["nodes"]}
    members = {}
    for edge in result["edges"]:
        if edge["relation"] != "method":
            continue
        owner = nodes[edge["source"]]["label"]
        member = nodes[edge["target"]]
        if owner in {"Api", "ReadonlyApi"}:
            assert edge["source_location"] == member["source_location"]
            assert edge["source_file"] == member["source_file"] == ports.name
            members[(owner, member["label"], member["source_location"])] = member["id"]

    assert set(members) == {("Api", ".dispatch()", "L2"), ("ReadonlyApi", ".execute()", "L7")}
    stand_alone = next(node["id"] for node in nodes.values() if node["label"] == "dispatch()")
    calls = {
        (
            nodes[edge["source"]]["label"],
            edge["target"],
            edge["source_file"],
            edge["source_location"],
        )
        for edge in result["edges"]
        if edge["relation"] == "calls"
    }
    assert calls == {
        ("useInterface()", members[("Api", ".dispatch()", "L2")], ports.name, "L10"),
        ("useReadonly()", members[("ReadonlyApi", ".execute()", "L7")], ports.name, "L11"),
        ("useBare()", stand_alone, ports.name, "L13"),
    }


@pytest.mark.parametrize("incremental", [False, True], ids=["full", "unchanged-type"])
def test_imported_receiver_resolves_to_its_indexed_property(tmp_path, incremental):
    ports = tmp_path / "ports.ts"
    ports.write_text(
        "interface Store { run(): number }\nexport type Api = { dispatch: Store['run'] };\n",
        encoding="utf-8",
    )
    caller = tmp_path / "caller.ts"
    caller.write_text(
        "import type { Api } from './ports';\n"
        "export function invoke(api: Api) {\n"
        "  return api.dispatch();\n"
        "}\n",
        encoding="utf-8",
    )
    options = {"root": tmp_path, "cache_root": tmp_path / "cache"}
    if incremental:
        baseline = extract([ports], **options)
        result = extract(
            [caller],
            resolution_context_nodes=baseline["nodes"],
            resolution_context_edges=baseline["edges"],
            **options,
        )
        type_nodes = baseline["nodes"]
    else:
        result = extract([ports, caller], **options)
        type_nodes = result["nodes"]

    members = [node for node in type_nodes if node["label"] == ".dispatch()"]
    assert [(node["source_file"], node["source_location"]) for node in members] == [
        ("ports.ts", "L2")
    ]
    invoke = next(node["id"] for node in result["nodes"] if node["label"] == "invoke()")
    assert [
        (edge["target"], edge["source_file"], edge["source_location"], edge["confidence"])
        for edge in result["edges"]
        if edge["relation"] == "calls" and edge["source"] == invoke
    ] == [(members[0]["id"], "caller.ts", "L3", "INFERRED")]


@pytest.mark.parametrize(
    ("origin", "indexed_type"),
    [
        pytest.param("interface Store { run: number }", "Store['run']", id="data-member"),
        pytest.param("interface Store { get run(): number }", "Store['run']", id="getter"),
        pytest.param("interface Store { run?(): number }", "Store['run']", id="optional-method"),
        pytest.param("type Store = { run?: () => number }", "Store['run']", id="optional-property"),
        pytest.param("interface Store { run(): number }", "Store['missing']", id="missing-key"),
        pytest.param(
            "interface Store { run(): number; idle(): number }",
            "Store['run' | 'idle']",
            id="union-key",
        ),
        pytest.param(
            "interface Store { run(): number } type Key = 'run';", "Store[Key]", id="named-key"
        ),
        pytest.param("interface Store { run(): number }", "Store[`run`]", id="template-key"),
        pytest.param("interface Store { ['run'](): number }", "Store['run']", id="computed-member"),
        pytest.param("type Store<T> = { run(): T }", "Store<number>['run']", id="generic-type"),
        pytest.param(
            "interface Store { run(): number } interface Store { idle(): number }",
            "Store['run']",
            id="merged-owner",
        ),
        pytest.param(
            "interface Store { run(): number; run(value: number): number }",
            "Store['run']",
            id="overloads",
        ),
        pytest.param(
            "namespace Internal { export interface Store { run(): number } }",
            "Internal.Store['run']",
            id="qualified-type",
        ),
        pytest.param(
            "declare module 'internal' { export interface Store { run(): number } }",
            "Store['run']",
            id="ambient-module",
        ),
        pytest.param("import type { Store } from './store';", "Store['run']", id="imported-origin"),
    ],
)
def test_indexed_types_without_a_unique_required_local_callable_are_omitted(
    tmp_path, origin, indexed_type
):
    store = tmp_path / "store.ts"
    store.write_text("export interface Store { run(): number }\n", encoding="utf-8")
    ports = tmp_path / "ports.ts"
    ports.write_text(
        f"{origin}\n"
        f"type Api = {{ dispatch: {indexed_type} }};\n"
        "function invoke(api: Api) { return api.dispatch(); }\n",
        encoding="utf-8",
    )
    result = extract([store, ports], root=tmp_path, cache_root=tmp_path / "cache")
    nodes = {node["label"]: node["id"] for node in result["nodes"]}
    assert ".dispatch()" not in nodes
    assert not any(
        (edge["relation"] == "method" and edge["source"] == nodes["Api"])
        or (edge["relation"] == "calls" and edge["source"] == nodes["invoke()"])
        for edge in result["edges"]
    )


def test_indexed_type_does_not_look_past_a_shadowing_type_parameter(tmp_path):
    ports = tmp_path / "ports.ts"
    ports.write_text(
        "interface Store { run(): number }\n"
        "interface Api<Store extends { run: number }> { dispatch: Store['run'] }\n",
        encoding="utf-8",
    )
    result = extract([ports], root=tmp_path, cache_root=tmp_path / "cache")
    assert not any(node["label"] == ".dispatch()" for node in result["nodes"])
