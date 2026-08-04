"""Behavioral contracts for first-class Gleam structural extraction."""

from __future__ import annotations

import json
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.gleam import extract_gleam


def _node(result: dict, label: str, node_type: str | None = None) -> dict:
    matches = [
        node
        for node in result["nodes"]
        if node["label"] == label and (node_type is None or node.get("type") == node_type)
    ]
    assert len(matches) == 1, (label, node_type, matches)
    return matches[0]


def _edges(result: dict, relation: str) -> list[dict]:
    return [edge for edge in result["edges"] if edge["relation"] == relation]


def _normalized(items: list[dict]) -> list[str]:
    return sorted(json.dumps(item, sort_keys=True) for item in items)


def _assert_no_gleam_hints(result: dict) -> None:
    for item in result["nodes"] + result["edges"]:
        assert not any(key.startswith("gleam_") for key in item), item


def test_extract_gleam_declarations_types_and_pipeline_calls(tmp_path: Path) -> None:
    package_root = tmp_path / "domain"
    source = package_root / "src" / "domain" / "order.gleam"
    source.parent.mkdir(parents=True)
    (package_root / "gleam.toml").write_text(
        'name = "domain"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    source.write_text(
        """import gleam/list

pub const default_order: OrderId = "default"

pub type Order {
  Order(id: OrderId, labels: List(String))
}

pub type OrderId = String

pub external type Database

@external(erlang, "orders", "persist")
pub fn persist(database: Database, order: Order) -> Order

fn helper(order: Order) -> Order { order }

pub fn process(order: Order) -> Order {
  helper(order)
  order
  |> helper
  |> list.reverse
  process(order)
}
""",
        encoding="utf-8",
    )

    result = extract_gleam(source)
    assert "error" not in result

    file_node = _node(result, "order.gleam")
    constant = _node(result, "default_order", "constant")
    order_type = _node(result, "Order", "type_definition")
    constructor = _node(result, "Order", "data_constructor")
    alias = _node(result, "OrderId", "type_alias")
    external_type = _node(result, "Database", "external_type")
    external_function = _node(result, "persist()", "external_function")
    helper = _node(result, "helper()", "function")
    process = _node(result, "process()", "function")

    assert constant["source_location"] == "L3"
    assert order_type["source_location"] == "L5"
    assert constructor["source_location"] == "L6"
    assert alias["source_location"] == "L9"
    assert external_type["source_location"] == "L11"
    assert external_function["source_location"] == "L14"
    assert helper["source_location"] == "L16"
    assert process["source_location"] == "L18"

    contained = {
        edge["target"] for edge in _edges(result, "contains") if edge["source"] == file_node["id"]
    }
    assert contained == {
        constant["id"],
        order_type["id"],
        alias["id"],
        external_type["id"],
        external_function["id"],
        helper["id"],
        process["id"],
    }
    assert any(
        edge["source"] == order_type["id"]
        and edge["target"] == constructor["id"]
        and edge["relation"] == "case_of"
        and edge["source_location"] == "L6"
        for edge in result["edges"]
    )

    references = _edges(result, "references")
    assert {edge["context"] for edge in references} == {
        "field",
        "parameter_type",
        "return_type",
        "type",
    }
    assert any(
        edge["source"] == constant["id"]
        and edge["target"] == alias["id"]
        and edge["context"] == "type"
        for edge in references
    )
    assert any(
        edge["source"] == external_function["id"]
        and edge["target"] == external_type["id"]
        and edge["context"] == "parameter_type"
        for edge in references
    )
    assert not any(
        node["label"] in {"Int", "List", "String", "Result", "Nil"} for node in result["nodes"]
    )

    helper_calls = [
        edge
        for edge in _edges(result, "calls")
        if edge["source"] == process["id"] and edge["target"] == helper["id"]
    ]
    assert len(helper_calls) == 1
    assert helper_calls[0]["source_location"] == "L19"
    assert not any(edge["source"] == edge["target"] for edge in _edges(result, "calls"))
    assert {
        (raw_call["receiver"], raw_call["callee"], raw_call["source_location"])
        for raw_call in result["raw_calls"]
    } == {("list", "reverse", "L22")}

    assert result["gleam_module"] == {
        "name": "domain/order",
        "package_root": str(package_root),
    }
    assert result["gleam_imports"] == [
        {
            "module": "gleam/list",
            "module_alias": "list",
            "line": 1,
            "symbols": [],
        }
    ]
    assert all(edge["confidence"] == "EXTRACTED" for edge in result["edges"])
    assert all(edge["confidence_score"] == 1.0 for edge in result["edges"])


def _write_cross_package_fixture(tmp_path: Path) -> tuple[Path, list[Path]]:
    root = tmp_path.resolve()
    inventory_root = root / "inventory"
    api_root = root / "api"
    inventory_source = inventory_root / "src" / "inventory.gleam"
    qualified_source = api_root / "src" / "api_qualified.gleam"
    unqualified_source = api_root / "src" / "api_unqualified.gleam"
    inventory_source.parent.mkdir(parents=True)
    qualified_source.parent.mkdir(parents=True)
    (inventory_root / "gleam.toml").write_text(
        'name = "inventory"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (api_root / "gleam.toml").write_text(
        'name = "api"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    inventory_source.write_text(
        """pub type Item { Item(name: String) }
pub const fallback = "missing"
pub fn dispatch(item: Item) -> Item { item }
pub fn lookup() -> Item { Item(name: fallback) }
""",
        encoding="utf-8",
    )
    qualified_source.write_text(
        """import inventory as stock

pub fn run(item: stock.Item) -> stock.Item {
  stock.dispatch(item)
}
""",
        encoding="utf-8",
    )
    unqualified_source.write_text(
        """import inventory.{lookup as find, type Item}

pub fn run(item: Item) -> Item {
  find()
}
""",
        encoding="utf-8",
    )
    return root, [inventory_source, qualified_source, unqualified_source]


def test_gleam_resolves_qualified_and_unqualified_imports(tmp_path: Path) -> None:
    root, paths = _write_cross_package_fixture(tmp_path)
    result = extract(
        paths,
        root=root,
        cache_root=root / "cache",
        parallel=False,
    )

    inventory_file = _node(result, "inventory.gleam")
    dispatch = _node(result, "dispatch()", "function")
    lookup = _node(result, "lookup()", "function")
    item_type = _node(result, "Item", "type_definition")
    item_constructor = _node(result, "Item", "data_constructor")
    qualified_run = next(
        node
        for node in result["nodes"]
        if node["label"] == "run()" and node["source_file"].endswith("api_qualified.gleam")
    )
    unqualified_run = next(
        node
        for node in result["nodes"]
        if node["label"] == "run()" and node["source_file"].endswith("api_unqualified.gleam")
    )

    call_pairs = {(edge["source"], edge["target"]) for edge in _edges(result, "calls")}
    assert (qualified_run["id"], dispatch["id"]) in call_pairs
    assert (unqualified_run["id"], lookup["id"]) in call_pairs

    qualified_type_references = {
        edge["target"]
        for edge in _edges(result, "references")
        if edge["source"] == qualified_run["id"]
    }
    unqualified_type_references = {
        edge["target"]
        for edge in _edges(result, "references")
        if edge["source"] == unqualified_run["id"]
    }
    assert qualified_type_references == {item_type["id"]}
    assert unqualified_type_references == {item_type["id"]}

    import_targets = {edge["target"] for edge in _edges(result, "imports")}
    assert inventory_file["id"] in import_targets
    assert lookup["id"] in import_targets
    assert item_type["id"] in import_targets
    assert any(
        edge["source"] == item_type["id"]
        and edge["target"] == item_constructor["id"]
        and edge["relation"] == "case_of"
        for edge in result["edges"]
    )
    assert all(edge["confidence"] == "EXTRACTED" for edge in result["edges"])
    _assert_no_gleam_hints(result)


def test_gleam_record_field_callback_is_not_a_module_call(tmp_path: Path) -> None:
    source = tmp_path / "src" / "callback.gleam"
    source.parent.mkdir(parents=True)
    source.write_text(
        """pub type Handler { Handler(callback: fn() -> Nil) }

pub fn run(record: Handler) {
  record.callback()
}
""",
        encoding="utf-8",
    )

    result = extract_gleam(source)
    assert not result["raw_calls"]
    assert not _edges(result, "calls")
    assert not _edges(result, "imports")
    assert not any(node.get("type") == "module" for node in result["nodes"])


def test_gleam_unresolved_external_module_keeps_import_without_call(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    source = root / "src" / "external.gleam"
    source.parent.mkdir(parents=True)
    source.write_text(
        """import gleam/list

pub fn reverse(items) {
  list.reverse(items)
}
""",
        encoding="utf-8",
    )

    result = extract([source], root=root, cache_root=root / "cache", parallel=False)
    module_stub = _node(result, "gleam/list", "module")
    assert any(
        edge["target"] == module_stub["id"] and edge["relation"] == "imports"
        for edge in result["edges"]
    )
    assert not _edges(result, "calls")
    _assert_no_gleam_hints(result)


def test_gleam_duplicate_modules_prefer_same_package_or_stay_ambiguous(
    tmp_path: Path,
) -> None:
    root = tmp_path.resolve()
    first_root = root / "first"
    second_root = root / "second"
    first_shared = first_root / "src" / "shared.gleam"
    second_shared = second_root / "src" / "shared.gleam"
    same_package_importer = first_root / "src" / "client.gleam"
    outside_importer = root / "outside" / "src" / "client.gleam"
    for source in (first_shared, second_shared, same_package_importer, outside_importer):
        source.parent.mkdir(parents=True, exist_ok=True)
    (first_root / "gleam.toml").write_text(
        'name = "first"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    (second_root / "gleam.toml").write_text(
        'name = "second"\nversion = "1.0.0"\n',
        encoding="utf-8",
    )
    first_shared.write_text("pub fn dispatch() { Nil }\n", encoding="utf-8")
    second_shared.write_text("pub fn dispatch() { Nil }\n", encoding="utf-8")
    importer_source = "import shared\n\npub fn run() { shared.dispatch() }\n"
    same_package_importer.write_text(importer_source, encoding="utf-8")
    outside_importer.write_text(importer_source, encoding="utf-8")

    result = extract(
        [first_shared, second_shared, same_package_importer, outside_importer],
        root=root,
        cache_root=root / "cache",
        parallel=False,
    )
    first_dispatch = next(
        node
        for node in result["nodes"]
        if node["label"] == "dispatch()" and node["source_file"].startswith("first/")
    )
    same_package_run = next(
        node
        for node in result["nodes"]
        if node["label"] == "run()" and node["source_file"].startswith("first/")
    )
    outside_run = next(
        node
        for node in result["nodes"]
        if node["label"] == "run()" and node["source_file"].startswith("outside/")
    )
    calls = _edges(result, "calls")
    assert any(
        edge["source"] == same_package_run["id"] and edge["target"] == first_dispatch["id"]
        for edge in calls
    )
    assert not any(edge["source"] == outside_run["id"] for edge in calls)
    shared_stub = _node(result, "shared", "module")
    assert any(
        edge["source"] != same_package_run["id"]
        and edge["target"] == shared_stub["id"]
        and edge["relation"] == "imports"
        and edge["source_file"].startswith("outside/")
        for edge in result["edges"]
    )
    _assert_no_gleam_hints(result)


def test_gleam_cold_and_warm_cache_outputs_are_identical(tmp_path: Path) -> None:
    root, paths = _write_cross_package_fixture(tmp_path)
    cache_root = root / "cache"
    cold = extract(paths, root=root, cache_root=cache_root, parallel=False)
    warm = extract(paths, root=root, cache_root=cache_root, parallel=False)

    assert _normalized(cold["nodes"]) == _normalized(warm["nodes"])
    assert _normalized(cold["edges"]) == _normalized(warm["edges"])
    _assert_no_gleam_hints(cold)
    _assert_no_gleam_hints(warm)
