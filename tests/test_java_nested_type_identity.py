"""Qualified Java receivers keep distinct nested owners (#5185)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from graphify.extract import extract


def _extract(root: Path, sources: dict[str, str], *, reverse: bool = False) -> dict:
    paths = []
    for name, body in sources.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    if reverse:
        paths.reverse()
    result = extract(paths, root=root, cache_root=root / "cache", parallel=False)
    assert not result["failed_sources"]
    assert not result["skipped_sources"]
    return result


def _targets(result: dict, caller: str = ".run()") -> list[dict]:
    nodes = {node["id"]: node for node in result["nodes"]}
    return [
        nodes[edge["target"]] for edge in result["edges"]
        if edge["relation"] == "calls"
        and nodes[edge["source"]]["label"] == caller
        and nodes[edge["target"]]["label"] == ".setEnabled()"
    ]


def _type(name: str) -> str:
    return (
        f"class {name} {{ public static class Builder {{ "
        "public Builder size(int n) { return this; } "
        "public Builder setEnabled(boolean x) { return this; } } }"
    )


@pytest.mark.parametrize("reverse", [False, True])
def test_nested_declarations_keep_owners_in_one_file(tmp_path: Path, reverse: bool):
    declarations = [_type("Other"), _type("Item")]
    if reverse:
        declarations.reverse()
    source = "\n".join([
        *declarations,
        "class Loader { void run() { new Item.Builder().setEnabled(true); } }",
    ])
    result = _extract(tmp_path, {"Types.java": source})
    setters = [node for node in result["nodes"] if node["label"] == ".setEnabled()"]
    assert len(setters) == 2
    expected_line = 1 if reverse else 2
    assert [(node["source_location"]) for node in _targets(result)] == [f"L{expected_line}"]
    assert len({node["id"] for node in setters}) == 2


@pytest.mark.parametrize("expression", [
    "Item.Builder b = new Item.Builder(); b.setEnabled(true);",
    "new Item.Builder().size(1).setEnabled(true);",
    "((Item.Builder)new Item.Builder()).setEnabled(true);",
    "Factory.create().size(1).setEnabled(true);",
])
def test_qualified_nested_receiver_with_competing_type(tmp_path: Path, expression: str):
    sources = {
        "Item.java": _type("Item"),
        "Other.java": _type("Other"),
        "Factory.java": "class Factory { static Item.Builder create() { return new Item.Builder(); } }",
        "Loader.java": f"class Loader {{ void run() {{ {expression} }} }}",
    }
    for reverse in (False, True):
        result = _extract(tmp_path, sources, reverse=reverse)
        assert [node["source_file"] for node in _targets(result)] == ["Item.java"]


@pytest.mark.parametrize("import_statement, receiver", [
    ("", "alpha.Item.Builder"),
    ("import alpha.Item;", "Item.Builder"),
    ("import alpha.Item.Builder;", "Builder"),
])
def test_nested_receiver_uses_package_and_explicit_import(
    tmp_path: Path, import_statement: str, receiver: str,
):
    sources = {
        "alpha/Item.java": "package alpha; " + _type("Item").replace("class Item", "public class Item"),
        "beta/Item.java": "package beta; " + _type("Item").replace("class Item", "public class Item"),
        "Loader.java": (
            f"{import_statement} class Loader {{ void run() {{ "
            f"new {receiver}().size(1).setEnabled(true); }} }}"
        ),
    }
    result = _extract(tmp_path, sources)
    assert len(_targets(result)) == 1
    assert _targets(result)[0]["id"].startswith("alpha_")


@pytest.mark.parametrize("import_statement, receiver", [
    ("", "alpha.Builder"),
    ("import alpha.Builder;", "Builder"),
])
def test_top_level_package_receivers_do_not_lose_qualification(
    tmp_path: Path, import_statement: str, receiver: str,
):
    sources = {
        f"{package}/Builder.java": (
            f"package {package}; public class Builder {{ "
            "public void setEnabled(boolean x) {} }"
        ) for package in ("alpha", "beta")
    }
    sources["Loader.java"] = (
        f"{import_statement} class Loader {{ void run() {{ new {receiver}().setEnabled(true); }} }}"
    )
    result = _extract(tmp_path, sources)
    assert len(_targets(result)) == 1
    assert _targets(result)[0]["id"].startswith("alpha_")


def test_unknown_qualified_type_does_not_bind_same_named_local(tmp_path: Path):
    result = _extract(tmp_path, {
        "Item.java": _type("Item"),
        "Loader.java": (
            "import external.Item; class Loader { void run() { "
            "new Item.Builder().setEnabled(true); } }"
        ),
    })
    assert not _targets(result)


def test_unqualified_ambiguous_receiver_stays_unlinked(tmp_path: Path):
    result = _extract(tmp_path, {
        "Item.java": _type("Item"),
        "Other.java": _type("Other"),
        "Loader.java": "class Loader { void run(Builder b) { b.setEnabled(true); } }",
    })
    assert not _targets(result)


@pytest.mark.parametrize("receiver", ["Item.Group.Builder", "Item.Builder<String>"])
def test_deep_and_generic_nested_receivers(tmp_path: Path, receiver: str):
    if "Group" in receiver:
        body = "static class Group { public static class Builder { public void setEnabled(boolean x) {} } }"
    else:
        body = "public static class Builder<T> { public void setEnabled(boolean x) {} }"
    result = _extract(tmp_path, {
        "Item.java": f"class Item {{ {body} }}",
        "Other.java": f"class Other {{ {body} }}",
        "Loader.java": f"class Loader {{ void run() {{ new {receiver}().setEnabled(true); }} }}",
    })
    assert [node["source_file"] for node in _targets(result)] == ["Item.java"]


def test_nested_field_tables_bind_the_correct_owner(tmp_path: Path):
    result = _extract(tmp_path, {
        "Types.java": (
            "class Item { static class Builder { Target value; void run() { value.setEnabled(true); } } }\n"
            "class Other { static class Builder { Decoy value; } }\n"
            "class Target { void setEnabled(boolean x) {} }\n"
            "class Decoy { void setEnabled(boolean x) {} }\n"
        ),
    })
    assert len(_targets(result)) == 1
    assert "_target_setenabled" in _targets(result)[0]["id"]


def test_qualified_calls_match_full_build_after_incremental_addition(tmp_path: Path):
    from graphify.watch import _rebuild_code

    sources = {
        "Item.java": _type("Item"),
        "Loader.java": (
            "class Loader { void run() { new Item.Builder().size(1).setEnabled(true); } }"
        ),
    }
    inc, full = tmp_path / "inc", tmp_path / "full"
    for root in (inc, full):
        root.mkdir()
        for name, body in sources.items():
            (root / name).write_text(body, encoding="utf-8")
    assert _rebuild_code(inc, no_cluster=True, acquire_lock=False, force=True)
    for root in (inc, full):
        (root / "Other.java").write_text(_type("Other"), encoding="utf-8")
    assert _rebuild_code(
        inc, changed_paths=[inc / "Other.java"], no_cluster=True, acquire_lock=False,
    )
    assert _rebuild_code(full, no_cluster=True, acquire_lock=False, force=True)

    def targets(root: Path) -> list[str]:
        graph = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
        graph["edges"] = graph.get("links", graph.get("edges", []))
        return [node["id"] for node in _targets(graph)]

    assert targets(inc) == targets(full)
    assert len(targets(full)) == 1
    caller = inc / "Loader.java"
    caller.write_text(caller.read_text(encoding="utf-8") + "\n// changed\n", encoding="utf-8")
    assert _rebuild_code(
        inc, changed_paths=[caller], no_cluster=True, acquire_lock=False,
    )
    assert targets(inc) == targets(full)


def test_cached_nested_identities_survive_checkout_relocation(tmp_path: Path):
    import shutil

    sources = {
        "Item.java": _type("Item"),
        "Other.java": _type("Other"),
        "Loader.java": (
            "class Loader { void run() { Item.Builder b = new Item.Builder(); b.setEnabled(true); } }"
        ),
    }
    original = tmp_path / "original"
    first = _extract(original, sources)
    relocated = tmp_path / "relocated"
    shutil.copytree(original, relocated)
    warm = _extract(relocated, sources, reverse=True)
    assert len(_targets(first)) == len(_targets(warm)) == 1
    assert _targets(first)[0]["id"] == _targets(warm)[0]["id"]


def test_java_cache_schema_retires_flat_nested_identities(tmp_path: Path, monkeypatch):
    from graphify import cache
    from graphify.extract import extract_java

    path = tmp_path / "Types.java"
    path.write_text(_type("Other") + "\n" + _type("Item"), encoding="utf-8")
    schema = cache._AST_CACHE_SCHEMA
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", schema - 1)
    stale = extract_java(path)
    for node in stale["nodes"]:
        node.pop("_java_type", None)
    cache.save_cached(path, stale, root=tmp_path, cache_root=tmp_path / "cache", kind="ast")
    monkeypatch.setattr(cache, "_AST_CACHE_SCHEMA", schema)
    result = extract([path], root=tmp_path, cache_root=tmp_path / "cache", parallel=False)
    builders = [node for node in result["nodes"] if node["label"] == "Builder"]
    assert len(builders) == 2
    assert {node["_java_type"]["path"] for node in builders} == {"Item.Builder", "Other.Builder"}


@pytest.mark.parametrize("body", [
    "void run(Builder b) { b.setEnabled(true); }",
    "void run() { new Builder().setEnabled(true); }",
])
def test_inherited_nested_type_resolves_through_imported_superclass(tmp_path: Path, body: str):
    result = _extract(tmp_path, {
        "lib/Parent.java": "package lib; public class Parent { public static class Builder { "
                           "public void setEnabled(boolean v) {} } }",
        "lib/Other.java": "package lib; public class Other { public static class Builder { "
                          "public void setEnabled(boolean v) {} } }",
        "app/Child.java": f"package app; import lib.Parent; class Child extends Parent {{ {body} }}",
    })
    assert [n["source_file"] for n in _targets(result)] == ["lib/Parent.java"]


def test_ambiguous_inherited_nested_types_stay_unlinked(tmp_path: Path):
    result = _extract(tmp_path, {
        "lib/First.java": "package lib; public interface First { class Builder { "
                          "public void setEnabled(boolean v) {} } }",
        "lib/Second.java": "package lib; public interface Second { class Builder { "
                           "public void setEnabled(boolean v) {} } }",
        "app/Child.java": "package app; import lib.First; import lib.Second; "
                          "class Child implements First, Second { "
                          "void run(Builder b) { b.setEnabled(true); } }",
    })
    assert not _targets(result)


@pytest.mark.parametrize("bases, expected_sources", [
    ("extends Parent", ["Parent.java"]),
    ("", []),
    ("implements First, Second", []),
])
def test_qualified_nested_type_binds_lexical_prefix(
    tmp_path: Path, bases: str, expected_sources: list[str],
):
    sources = {
        "Parent.java": _type("Parent"),
        "Item.java": _type("Item"),
        "First.java": _type("First").replace("class First", "interface First"),
        "Second.java": _type("Second").replace("class Second", "interface Second"),
        "Caller.java": (
            f"class Caller {{ static class Item {bases} {{}} "
            "void run(Item.Builder b) { b.setEnabled(true); } }"
        ),
    }
    for reverse in (False, True):
        result = _extract(tmp_path, sources, reverse=reverse)
        assert [node["source_file"] for node in _targets(result)] == expected_sources


@pytest.mark.parametrize("field, expression", [
    ("protected Builder builder;", "builder.setEnabled(true);"),
    ("protected Builder builder;", "this.builder.setEnabled(true);"),
    ("public static Builder BUILDER;", "Child.BUILDER.setEnabled(true);"),
    ("public static Builder BUILDER;", "Child.BUILDER.size(1).setEnabled(true);"),
])
def test_inherited_field_type_uses_declaring_import(
    tmp_path: Path, field: str, expression: str,
):
    sources = {
        "lib/Types.java": "package lib; " + _type("Types").replace("class Types", "public class Types"),
        "base/Parent.java": (
            f"package base; import lib.Types.Builder; public class Parent {{ {field} }}"
        ),
        "app/Child.java": (
            "package app; import base.Parent; class Child extends Parent { "
            f"void run() {{ {expression} }} }}"
        ),
    }
    for reverse in (False, True):
        result = _extract(tmp_path, sources, reverse=reverse)
        assert [node["source_file"] for node in _targets(result)] == ["lib/Types.java"]


@pytest.mark.parametrize("field, expression", [
    ("protected Builder value;", "value.setEnabled(true);"),
    ("protected Builder value;", "this.value.setEnabled(true);"),
    ("protected Builder value;", "value.size(1).setEnabled(true);"),
    ("protected Builder value;", "this.value.size(1).setEnabled(true);"),
    ("public static Builder VALUE;", "Child.VALUE.setEnabled(true);"),
])
@pytest.mark.parametrize("same_file", [False, True])
def test_inherited_field_type_ignores_subclass_type_shadow(
    tmp_path: Path, field: str, expression: str, same_file: bool,
):
    sources = {
        "Parent.java": _type("Parent")[:-1] + field + "}",
        "Child.java": (
            _type("Child").replace("class Child", "class Child extends Parent")[:-1]
            + f"void run() {{ {expression} }} }}"
        ),
    }
    if same_file:
        sources = {"Types.java": "\n".join(sources.values())}
    for reverse in (False, True):
        result = _extract(tmp_path, sources, reverse=reverse)
        nodes = {node["id"]: node for node in result["nodes"]}
        targets = {node["id"] for node in _targets(result)}
        owners = [
            nodes[edge["source"]]["_java_type"]["path"] for edge in result["edges"]
            if edge["relation"] == "method" and edge["target"] in targets
        ]
        assert owners == ["Parent.Builder"]


@pytest.mark.parametrize("body", [
    "void run(Builder value) { value.setEnabled(true); }",
    "void run() { Builder value = new Builder(); value.setEnabled(true); }",
])
def test_local_receiver_keeps_its_context_when_it_shadows_inherited_field(
    tmp_path: Path, body: str,
):
    source = (
        _type("Parent")[:-1] + "protected Builder value; }\n"
        + _type("Child").replace("class Child", "class Child extends Parent")[:-1]
        + body + "}"
    )
    result = _extract(tmp_path, {"Types.java": source})
    nodes = {node["id"]: node for node in result["nodes"]}
    targets = {node["id"] for node in _targets(result)}
    owners = [
        nodes[edge["source"]]["_java_type"]["path"] for edge in result["edges"]
        if edge["relation"] == "method" and edge["target"] in targets
    ]
    assert owners == ["Child.Builder"]


@pytest.mark.parametrize("other_overload", [
    "void run(Service Service) {}",
    "void run(int n) { Service Service = new Service(); }",
])
@pytest.mark.parametrize("reverse_declarations", [False, True])
def test_overload_bindings_do_not_become_field_receivers(
    tmp_path: Path, other_overload: str, reverse_declarations: bool,
):
    methods = [other_overload, "void run() { Service.setEnabled(true); }"]
    if reverse_declarations:
        methods.reverse()
    sources = {
        "Service.java": "class Service { static void setEnabled(boolean v) {} }",
        "Caller.java": "class Caller { " + " ".join(methods) + " }",
    }
    for reverse in (False, True):
        result = _extract(tmp_path, sources, reverse=reverse)
        assert [node["source_file"] for node in _targets(result)] == ["Service.java"]
