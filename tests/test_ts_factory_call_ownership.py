"""Keep TypeScript factory calls on the definitions whose bodies make them."""

from pathlib import Path

import pytest

from graphify.extract import extract


@pytest.mark.parametrize("suffix", [".ts", ".tsx"])
def test_returned_factory_methods_own_their_calls(tmp_path: Path, suffix: str):
    factory = tmp_path / f"factory{suffix}"
    factory.write_text(
        "import { load as importedLoad } from './store';\n"
        "function persist() {}\n"
        "function initialize() {}\n"
        "export function make() {\n"
        "  initialize();\n"
        "  const helper = () => persist();\n"
        "  const saveImpl = function () { helper(); };\n"
        "  return {\n"
        "    save: () => saveImpl(),\n"
        "    read() { return importedLoad(); },\n"
        "    reset: function () { helper(); },\n"
        "  };\n"
        "}\n",
        encoding="utf-8",
    )
    store = tmp_path / "store.ts"
    store.write_text("export function load() { return 1; }\n", encoding="utf-8")

    result = extract([factory, store], root=tmp_path, cache_root=tmp_path / "cache")
    nodes = {node["id"]: node for node in result["nodes"]}
    owned_members = set()
    for edge in result["edges"]:
        if edge["relation"] not in {"contains", "method"}:
            continue
        if nodes[edge["source"]]["label"] != "make()":
            continue
        member = nodes[edge["target"]]
        assert member["source_file"] == factory.name
        assert edge["source_location"] == member["source_location"]
        owned_members.add((edge["relation"], member["label"], member["source_location"]))
    assert owned_members == {
        ("contains", "helper()", "L6"),
        ("contains", "saveImpl()", "L7"),
        ("method", ".save()", "L9"),
        ("method", ".read()", "L10"),
        ("method", ".reset()", "L11"),
    }
    assert {
        (nodes[edge["source"]]["label"], nodes[edge["target"]]["label"])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    } == {
        ("make()", "initialize()"),
        ("helper()", "persist()"),
        ("saveImpl()", "helper()"),
        (".save()", "saveImpl()"),
        (".read()", "load()"),
        (".reset()", "helper()"),
    }


def test_factory_method_ids_and_local_bindings_follow_their_owners(tmp_path: Path):
    path = tmp_path / "factory.ts"
    path.write_text(
        "function one() { return 1; }\n"
        "function two() { return 2; }\n"
        "const first = () => {\n"
        "  const helper = () => one();\n"
        "  return { save: () => helper(), masked(helper: () => number) { return helper(); } };\n"
        "};\n"
        "const second = () => {\n"
        "  const helper = () => two();\n"
        "  return { save: () => helper(), masked: (callback: () => number) => {\n"
        "    const helper = callback;\n"
        "    return helper();\n"
        "  } };\n"
        "};\n"
        "const concise = () => ({ save: () => one(), read() { return two(); } });\n"
        "declare const helper: () => number;\n"
        "function unrelated() { return helper(); }\n",
        encoding="utf-8",
    )

    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache")
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    owners = {
        edge["target"]: labels[edge["source"]]
        for edge in result["edges"]
        if edge["relation"] in {"contains", "method"}
        and labels[edge["source"]] in {"first()", "second()", "concise()"}
    }
    assert sorted((owner, labels[node]) for node, owner in owners.items()) == [
        ("concise()", ".read()"),
        ("concise()", ".save()"),
        ("first()", ".masked()"),
        ("first()", ".save()"),
        ("first()", "helper()"),
        ("second()", ".masked()"),
        ("second()", ".save()"),
        ("second()", "helper()"),
    ]
    assert {
        (
            (owners.get(edge["source"]), labels[edge["source"]]),
            (owners.get(edge["target"]), labels[edge["target"]]),
        )
        for edge in result["edges"]
        if edge["relation"] == "calls"
    } == {
        (("first()", ".save()"), ("first()", "helper()")),
        (("first()", "helper()"), (None, "one()")),
        (("second()", ".save()"), ("second()", "helper()")),
        (("second()", "helper()"), (None, "two()")),
        (("concise()", ".save()"), (None, "one()")),
        (("concise()", ".read()"), (None, "two()")),
    }


def test_returned_arrows_keep_the_factory_receiver(tmp_path: Path):
    path = tmp_path / "factory.ts"
    path.write_text(
        "function make(this: { save(): number }) {\n"
        "  return {\n"
        "    save() { return 1; },\n"
        "    method() { return this.save(); },\n"
        "    arrow: () => this.save(),\n"
        "  };\n"
        "}\n",
        encoding="utf-8",
    )

    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache")
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    assert {
        (labels[edge["source"]], labels[edge["target"]])
        for edge in result["edges"]
        if edge["relation"] == "calls"
    } == {(".method()", ".save()")}
