"""Kotlin receiver-typed member-call resolution (#1699)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from graphify.extract import extract


def _extract(tmp_path: Path, files: dict[str, str]) -> dict:
    paths: list[Path] = []
    for name, body in files.items():
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        return extract(
            [path.relative_to(tmp_path) for path in paths],
            cache_root=tmp_path / "graphify-out",
            parallel=False,
        )
    finally:
        os.chdir(previous)


def _find(result: dict, label: str, id_contains: str) -> str:
    return next(
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and id_contains in node["id"]
    )


def _call_edges(result: dict) -> list[dict]:
    return [edge for edge in result["edges"] if edge.get("relation") == "calls"]


def test_issue_1699_resolves_four_typed_receiver_shapes(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "InputView.kt": (
                "class InputView {\n"
                "    fun updateKeyboardShow(show: Boolean) {}\n"
                "}\n"
            ),
            "PanelController.kt": (
                "class PanelController {\n"
                "    private val input = InputView()\n"
                "    fun updateKeyboardShow(show: Boolean) {}\n"
                "    fun getInputView(): InputView = input\n"
                "    fun onPanelClose() { input.updateKeyboardShow(false) }\n"
                "    fun onPanelOpen() { getInputView().updateKeyboardShow(true) }\n"
                "    fun onPanelToggle() {\n"
                "        val view = getInputView()\n"
                "        view.updateKeyboardShow(true)\n"
                "    }\n"
                "}\n"
            ),
            "Window.kt": (
                "fun open() {\n"
                "    val view = InputView()\n"
                "    view.updateKeyboardShow(true)\n"
                "}\n"
            ),
        },
    )

    update = _find(result, ".updateKeyboardShow()", "inputview")
    callers = {
        _find(result, ".onPanelClose()", "panelcontroller"),
        _find(result, ".onPanelOpen()", "panelcontroller"),
        _find(result, ".onPanelToggle()", "panelcontroller"),
        _find(result, "open()", "window"),
    }
    resolved = {
        edge["source"]: edge
        for edge in _call_edges(result)
        if edge.get("target") == update and edge.get("source") in callers
    }
    assert set(resolved) == callers
    assert all(edge.get("confidence") == "INFERRED" for edge in resolved.values())
    assert all(edge.get("confidence_score") == 0.85 for edge in resolved.values())

    get_input = _find(result, ".getInputView()", "panelcontroller")
    assert any(
        edge["source"] in callers
        and edge["target"] == get_input
        and edge.get("confidence") == "EXTRACTED"
        for edge in _call_edges(result)
    )


def test_member_call_coexists_with_method_ownership_edge(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "Owner.kt": (
                "class Owner {\n"
                "    companion object {\n"
                "        fun ping() {}\n"
                "        val initialized = Owner.ping()\n"
                "    }\n"
                "}\n"
            ),
        },
    )

    owner = _find(result, "Owner", "owner")
    ping = _find(result, ".ping()", "owner")
    relations = {
        edge["relation"]
        for edge in result["edges"]
        if edge.get("source") == owner and edge.get("target") == ping
    }
    assert {"method", "calls"} <= relations


def test_receiver_bindings_do_not_leak_between_methods(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "Alpha.kt": "class Alpha { fun close() {} }\n",
            "Beta.kt": "class Beta { fun close() {} }\n",
            "Worker.kt": (
                "class Worker {\n"
                "    fun first(service: Alpha) { service.close() }\n"
                "    fun second(service: Beta) { service.close() }\n"
                "}\n"
            ),
        },
    )

    first = _find(result, ".first()", "worker")
    second = _find(result, ".second()", "worker")
    alpha_close = _find(result, ".close()", "alpha")
    beta_close = _find(result, ".close()", "beta")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert (first, alpha_close) in pairs
    assert (second, beta_close) in pairs
    assert (first, beta_close) not in pairs
    assert (second, alpha_close) not in pairs


def test_explicit_this_call_resolves_only_to_its_owner(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "First.kt": (
                "class First {\n"
                "    fun target() {}\n"
                "    fun caller() { this.target() }\n"
                "}\n"
            ),
            "Second.kt": "class Second { fun target() {} }\n",
        },
    )

    caller = _find(result, ".caller()", "first")
    first_target = _find(result, ".target()", "first")
    second_target = _find(result, ".target()", "second")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert (caller, first_target) in pairs
    assert (caller, second_target) not in pairs


def test_nested_this_with_same_named_top_level_owner_fails_closed(
    tmp_path: Path,
) -> None:
    result = _extract(
        tmp_path,
        {
            "Owners.kt": (
                "package sample\n"
                "class Inner { fun target() {} }\n"
                "class Outer {\n"
                "    class Inner {\n"
                "        fun target() {}\n"
                "        fun caller() { this.target() }\n"
                "    }\n"
                "}\n"
            ),
        },
    )

    caller = _find(result, ".caller()", "owners_inner")
    assert not any(edge["source"] == caller for edge in _call_edges(result))


def test_shadow_and_reassignment_poison_receiver_but_this_field_survives(
    tmp_path: Path,
) -> None:
    result = _extract(
        tmp_path,
        {
            "Alpha.kt": "class Alpha { fun ping() {} }\n",
            "Beta.kt": "class Beta { fun ping() {} }\n",
            "Owner.kt": (
                "class Owner(var service: Alpha) {\n"
                "    fun shadow(service: Beta) { service.ping() }\n"
                "    fun reassigned() {\n"
                "        var local = Alpha()\n"
                "        local = unknown\n"
                "        local.ping()\n"
                "    }\n"
                "    fun explicitThis(service: Beta) { this.service.ping() }\n"
                "    fun explicitReassigned(other: Beta) {\n"
                "        this.service = other\n"
                "        service.ping()\n"
                "    }\n"
                "    fun bareReassigned(other: Beta) {\n"
                "        service = other\n"
                "        this.service.ping()\n"
                "    }\n"
                "    fun localShadow(other: Beta) {\n"
                "        var service = other\n"
                "        service = other\n"
                "        this.service.ping()\n"
                "    }\n"
                "}\n"
            ),
        },
    )

    shadow = _find(result, ".shadow()", "owner")
    reassigned = _find(result, ".reassigned()", "owner")
    explicit_this = _find(result, ".explicitThis()", "owner")
    explicit_reassigned = _find(result, ".explicitReassigned()", "owner")
    bare_reassigned = _find(result, ".bareReassigned()", "owner")
    local_shadow = _find(result, ".localShadow()", "owner")
    alpha_ping = _find(result, ".ping()", "alpha")
    beta_ping = _find(result, ".ping()", "beta")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert not any(
        source in {shadow, reassigned, explicit_reassigned, bare_reassigned}
        and target in {alpha_ping, beta_ping}
        for source, target in pairs
    )
    assert (explicit_this, alpha_ping) in pairs
    assert (explicit_this, beta_ping) not in pairs
    assert (local_shadow, alpha_ping) in pairs
    assert (local_shadow, beta_ping) not in pairs


def test_import_alias_and_fqn_select_the_exact_type(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "a/Service.kt": "package a\nclass Service { fun run() {} }\n",
            "b/Service.kt": "package b\nclass Service { fun run() {} }\n",
            "app/Use.kt": (
                "package app\n"
                "import a.Service as Primary\n"
                "fun alias(value: Primary) { value.run() }\n"
                "fun qualified(value: a.Service) { value.run() }\n"
            ),
        },
    )

    alias = _find(result, "alias()", "use")
    qualified = _find(result, "qualified()", "use")
    a_run = _find(result, ".run()", "a_service")
    b_run = _find(result, ".run()", "b_service")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert (alias, a_run) in pairs
    assert (qualified, a_run) in pairs
    assert (alias, b_run) not in pairs
    assert (qualified, b_run) not in pairs


def test_dotted_relative_receivers_do_not_bind_absolute_package_decoy(
    tmp_path: Path,
) -> None:
    result = _extract(
        tmp_path,
        {
            "domain/Outer.kt": (
                "package domain\n"
                "class Outer {\n"
                "    class Service { fun run() {} }\n"
                "}\n"
            ),
            "absolute_decoy/Service.kt": (
                "package Outer\n"
                "class Service { fun run() {} }\n"
            ),
            "companion_decoy/Service.kt": (
                "package Companion\n"
                "class Service { fun run() {} }\n"
            ),
            "implicit_decoy/Option.kt": (
                "package StackWalker\n"
                "class Option { override fun toString(): String = \"x\" }\n"
            ),
            "domain/SamePackageUse.kt": (
                "package domain\n"
                "fun samePackage(value: Outer.Service) { value.run() }\n"
            ),
            "app/Use.kt": (
                "package app\n"
                "import domain.Outer\n"
                "fun imported(value: Outer.Service) { value.run() }\n"
            ),
            "app/WildcardUse.kt": (
                "package app\n"
                "import domain.*\n"
                "fun wildcard(value: Outer.Service) { value.run() }\n"
            ),
            "app/Alias.kt": "package app\ntypealias Outer = domain.Outer\n",
            "app/TypeAliasUse.kt": (
                "package app\n"
                "fun typeAlias(value: Outer.Service) { value.run() }\n"
            ),
            "app/NestedUse.kt": (
                "package app\n"
                "class Container {\n"
                "    class Outer {\n"
                "        class Service { fun run() {} }\n"
                "    }\n"
                "    fun nested(value: Outer.Service) { value.run() }\n"
                "}\n"
            ),
            "app/NamedCompanionUse.kt": (
                "package app\n"
                "class NamedHost {\n"
                "    companion object Outer {\n"
                "        class Service { fun run() {} }\n"
                "    }\n"
                "    fun namedCompanion(value: Outer.Service) { value.run() }\n"
                "}\n"
            ),
            "app/UnnamedCompanionUse.kt": (
                "package app\n"
                "class UnnamedHost {\n"
                "    companion object {\n"
                "        class Service { fun run() {} }\n"
                "    }\n"
                "    fun unnamedCompanion(value: Companion.Service) { value.run() }\n"
                "}\n"
            ),
            "app/ImplicitUse.kt": (
                "package app\n"
                "fun implicit(value: StackWalker.Option) { value.toString() }\n"
            ),
        },
    )

    callers = {
        _find(result, "samePackage()", "samepackageuse"),
        _find(result, "imported()", "use"),
        _find(result, "wildcard()", "wildcarduse"),
        _find(result, "typeAlias()", "typealiasuse"),
        _find(result, ".nested()", "nesteduse"),
        _find(result, ".namedCompanion()", "namedcompanionuse"),
        _find(result, ".unnamedCompanion()", "unnamedcompanionuse"),
        _find(result, "implicit()", "implicituse"),
    }
    decoy_runs = {
        node["id"]
        for node in result["nodes"]
        if node.get("label") == ".run()"
        and str(node.get("source_file", "")).endswith(
            ("absolute_decoy/Service.kt", "companion_decoy/Service.kt")
        )
    }
    decoy_methods = decoy_runs | {
        node["id"]
        for node in result["nodes"]
        if node.get("label") == ".toString()"
        and str(node.get("source_file", "")).endswith(
            "implicit_decoy/Option.kt"
        )
    }
    assert not any(
        edge["source"] in callers and edge["target"] in decoy_methods
        for edge in _call_edges(result)
    )


def test_markerless_incremental_kotlin_context_fails_closed(tmp_path: Path) -> None:
    caller_path = tmp_path / "Caller.kt"
    caller_path.write_text(
        "package app\n"
        "import lib.Service\n"
        "fun call(service: Service) { service.ping() }\n",
        encoding="utf-8",
    )
    previous = Path.cwd()
    try:
        os.chdir(tmp_path)
        result = extract(
            [Path("Caller.kt")],
            cache_root=tmp_path / "graphify-out",
            parallel=False,
            resolution_context_nodes=[
                {
                    "id": "service_type",
                    "label": "Service",
                    "source_file": "Service.kt",
                    "file_type": "code",
                    "_callable": True,
                    "_callable_class": True,
                    "_kotlin_fqn": "lib.Service",
                },
                {
                    "id": "service_ping",
                    "label": ".ping()",
                    "source_file": "Service.kt",
                    "file_type": "code",
                    "_callable": True,
                },
            ],
            resolution_context_edges=[
                {
                    "source": "service_type",
                    "target": "service_ping",
                    "relation": "method",
                    "source_file": "Service.kt",
                }
            ],
        )
    finally:
        os.chdir(previous)

    caller = _find(result, "call()", "caller")
    assert not any(edge["source"] == caller for edge in _call_edges(result))


def test_ambiguous_type_and_overloaded_method_emit_no_edge(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "one/Service.kt": "package dup\nclass Service { fun ping() {} }\n",
            "two/Service.kt": "package dup\nclass Service { fun ping() {} }\n",
            "Use.kt": (
                "package dup\n"
                "fun ambiguous(value: Service) { value.ping() }\n"
            ),
            "Overloaded.kt": (
                "package overload\n"
                "class Service {\n"
                "    fun ping() {}\n"
                "    fun ping(value: Int) {}\n"
                "}\n"
                "fun overloaded(value: Service) { value.ping() }\n"
            ),
        },
    )

    ambiguous = _find(result, "ambiguous()", "use")
    overloaded = _find(result, "overloaded()", "overloaded")
    assert not any(
        edge["source"] in {ambiguous, overloaded} for edge in _call_edges(result)
    )


def test_nullable_script_receiver_and_external_negatives(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "lib/Service.kt": "package lib\nclass Service { fun ping() {} }\n",
            "decoy/Log.kt": "package decoy\nclass Log { fun d() {} }\n",
            "decoy/List.kt": "package decoy\nclass List { fun map() {} }\n",
            "app/Main.kts": (
                "package app\n"
                "import lib.Service\n"
                "import android.util.Log\n"
                "val service: Service? = null\n"
                "fun run(list: List<String>) {\n"
                "    service?.ping()\n"
                "    Log.d(\"tag\", \"message\")\n"
                "    list.map { it }\n"
                "}\n"
            ),
        },
    )

    caller = _find(result, "run()", "main")
    service_ping = _find(result, ".ping()", "lib_service")
    decoy_d = _find(result, ".d()", "decoy_log")
    decoy_map = _find(result, ".map()", "decoy_list")
    targets = {
        edge["target"] for edge in _call_edges(result) if edge["source"] == caller
    }
    assert service_ping in targets
    assert decoy_d not in targets
    assert decoy_map not in targets


def test_same_named_factory_makes_constructor_binding_ambiguous(tmp_path: Path) -> None:
    result = _extract(
        tmp_path,
        {
            "Widget.kt": (
                "package model\n"
                "class Widget { fun render() {} }\n"
            ),
            "Product.kt": (
                "package model\n"
                "class Product { fun render() {} }\n"
            ),
            "Factory.kt": (
                "package model\n"
                "fun Widget(size: Int): Product = Product()\n"
            ),
            "Use.kt": (
                "package model\n"
                "fun use() {\n"
                "    val value = Widget(1)\n"
                "    value.render()\n"
                "}\n"
                "fun typed(value: Widget) { value.render() }\n"
            ),
        },
    )

    caller = _find(result, "use()", "use")
    typed = _find(result, "typed()", "use")
    widget_render = _find(result, ".render()", "widget")
    product_render = _find(result, ".render()", "product")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert not any(
        source == caller and target in {widget_render, product_render}
        for source, target in pairs
    )
    assert (typed, widget_render) in pairs
    assert (typed, product_render) not in pairs


def test_same_package_factory_shadows_imported_class_constructor(
    tmp_path: Path,
) -> None:
    result = _extract(
        tmp_path,
        {
            "lib/Widget.kt": (
                "package lib\n"
                "class Widget { fun render() {} }\n"
            ),
            "app/Product.kt": (
                "package app\n"
                "class Product { fun render() {} }\n"
                "fun Widget(size: Int): Product = Product()\n"
            ),
            "app/Use.kt": (
                "package app\n"
                "import lib.Widget\n"
                "fun use() {\n"
                "    val value = Widget(1)\n"
                "    value.render()\n"
                "}\n"
                "fun typed(value: Widget) { value.render() }\n"
            ),
        },
    )

    caller = _find(result, "use()", "use")
    typed = _find(result, "typed()", "use")
    widget_render = _find(result, ".render()", "lib_widget")
    product_render = _find(result, ".render()", "product")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert not any(
        source == caller and target in {widget_render, product_render}
        for source, target in pairs
    )
    assert (typed, widget_render) in pairs
    assert (typed, product_render) not in pairs


def test_wildcard_imported_factory_makes_constructor_binding_ambiguous(
    tmp_path: Path,
) -> None:
    result = _extract(
        tmp_path,
        {
            "model/Widget.kt": (
                "package model\n"
                "class Widget { fun render() {} }\n"
            ),
            "product/Product.kt": (
                "package product\n"
                "class Product { fun render() {} }\n"
            ),
            "factory/Factory.kt": (
                "package factory\n"
                "import product.Product\n"
                "fun Widget(size: Int): Product = Product()\n"
            ),
            "app/Use.kt": (
                "package app\n"
                "import model.Widget\n"
                "import factory.*\n"
                "fun use() {\n"
                "    val value = Widget(1)\n"
                "    value.render()\n"
                "}\n"
                "fun typed(value: Widget) { value.render() }\n"
            ),
        },
    )

    caller = _find(result, "use()", "use")
    typed = _find(result, "typed()", "use")
    widget_render = _find(result, ".render()", "widget")
    product_render = _find(result, ".render()", "product")
    pairs = {(edge["source"], edge["target"]) for edge in _call_edges(result)}
    assert not any(
        source == caller and target in {widget_render, product_render}
        for source, target in pairs
    )
    assert (typed, widget_render) in pairs
    assert (typed, product_render) not in pairs


def test_recovery_parsed_kotlin_provider_fails_inventory_closed(
    tmp_path: Path,
) -> None:
    result = _extract(
        tmp_path,
        {
            "Widget.kt": (
                "package model\n"
                "class Widget(val size: Int) {\n"
                "    fun render() {}\n"
                "}\n"
            ),
            "Product.kt": "package model\nclass Product { fun render() {} }\n",
            "Use.kt": (
                "package model\n"
                "fun use() {\n"
                "    val value = Widget(1)\n"
                "    value.render()\n"
                "}\n"
            ),
            "Broken.kt": (
                "package model\n"
                "class A { val value: Money = Money(5) }\n"
                "class B { val value: Ledger = Ledger() }\n"
                "fun Widget(size: Int): Product = Product()\n"
            ),
        },
    )

    caller = _find(result, "use()", "use")
    widget_render = _find(result, ".render()", "widget")
    product_render = _find(result, ".render()", "product")
    assert not any(
        edge["source"] == caller
        and edge["target"] in {widget_render, product_render}
        for edge in _call_edges(result)
    )


def test_zero_node_kotlin_provider_fails_inventory_closed(tmp_path: Path) -> None:
    root, missing = _incremental_factory_corpus(tmp_path / "zero-node-provider")
    previous = Path.cwd()
    try:
        os.chdir(root)
        result = extract(
            [Path("Widget.kt"), Path("Product.kt"), Path("Use.kt"), missing],
            cache_root=root / "graphify-out",
            parallel=False,
        )
    finally:
        os.chdir(previous)

    caller = _find(result, "use()", "use")
    widget_render = _find(result, ".render()", "widget")
    product_render = _find(result, ".render()", "product")
    assert not any(
        edge["source"] == caller
        and edge["target"] in {widget_render, product_render}
        for edge in _call_edges(result)
    )
    assert any(
        str(node.get("source_file", "")).endswith("Factory.kt")
        and node.get("_kotlin_member_symbol_inventory_incomplete") is True
        for node in result["nodes"]
    )


def _incremental_corpus(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    (root / "Service.kt").write_text(
        "package lib\nclass Service { fun ping() {} }\n", encoding="utf-8"
    )
    caller = root / "Caller.kt"
    caller.write_text(
        "package app\n"
        "import lib.Service\n"
        "fun call(service: Service) { service.ping() }\n",
        encoding="utf-8",
    )
    return root, caller


def _incremental_member_edges(root: Path) -> list[tuple[str, str]]:
    graph = json.loads((root / "graphify-out" / "graph.json").read_text())
    caller = next(
        node["id"]
        for node in graph["nodes"]
        if node.get("label") == "call()"
        and str(node.get("source_file", "")).endswith("Caller.kt")
    )
    target = next(
        node["id"]
        for node in graph["nodes"]
        if node.get("label") == ".ping()"
        and str(node.get("source_file", "")).endswith("Service.kt")
    )
    return [
        (edge["source"], edge["target"])
        for edge in graph.get("links", graph.get("edges", []))
        if edge.get("relation") == "calls"
        and edge["source"] == caller
        and edge["target"] == target
    ]


def _incremental_factory_corpus(root: Path) -> tuple[Path, Path]:
    root.mkdir(parents=True)
    (root / "Widget.kt").write_text(
        "package model\nclass Widget(val size: Int) { fun render() {} }\n",
        encoding="utf-8",
    )
    (root / "Product.kt").write_text(
        "package model\nclass Product { fun render() {} }\n",
        encoding="utf-8",
    )
    (root / "Use.kt").write_text(
        "package model\n"
        "fun use() {\n"
        "    val value = Widget(1)\n"
        "    value.render()\n"
        "}\n",
        encoding="utf-8",
    )
    return root, root / "Factory.kt"


def _factory_call_targets(root: Path) -> set[str]:
    graph = json.loads((root / "graphify-out" / "graph.json").read_text())
    caller = next(
        node["id"]
        for node in graph["nodes"]
        if node.get("label") == "use()"
        and str(node.get("source_file", "")).endswith("Use.kt")
    )
    return {
        edge["target"]
        for edge in graph.get("links", graph.get("edges", []))
        if edge.get("relation") == "calls" and edge["source"] == caller
    }


def _factory_render_ids(root: Path) -> tuple[str, str]:
    graph = json.loads((root / "graphify-out" / "graph.json").read_text())
    widget_render = next(
        node["id"]
        for node in graph["nodes"]
        if node.get("label") == ".render()"
        and str(node.get("source_file", "")).endswith("Widget.kt")
    )
    product_render = next(
        node["id"]
        for node in graph["nodes"]
        if node.get("label") == ".render()"
        and str(node.get("source_file", "")).endswith("Product.kt")
    )
    return widget_render, product_render


def _write_factory(path: Path) -> None:
    path.write_text(
        "package model\nfun Widget(size: Int): Product = Product()\n",
        encoding="utf-8",
    )


def _strip_kotlin_inventory_markers(root: Path) -> None:
    graph_path = root / "graphify-out" / "graph.json"
    graph = json.loads(graph_path.read_text())
    for node in graph["nodes"]:
        for key in list(node):
            if key.startswith("_kotlin_member_"):
                node.pop(key)
    graph_path.write_text(json.dumps(graph), encoding="utf-8")


def test_watch_changed_caller_resolves_against_unchanged_kotlin_context(
    tmp_path: Path,
) -> None:
    from graphify.watch import _rebuild_code

    root, caller = _incremental_corpus(tmp_path / "watch")
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False) is True
    assert len(_incremental_member_edges(root)) == 1

    caller.write_text(caller.read_text() + "// changed\n", encoding="utf-8")
    for _ in range(2):
        assert _rebuild_code(
            root, changed_paths=[caller], no_cluster=True, acquire_lock=False
        ) is True
        assert len(_incremental_member_edges(root)) == 1


def test_watch_requeues_caller_when_factory_is_added_and_removed(
    tmp_path: Path,
) -> None:
    from graphify.watch import _rebuild_code

    root, factory = _incremental_factory_corpus(tmp_path / "watch-factory")
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False) is True
    widget_render, product_render = _factory_render_ids(root)
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)

    _strip_kotlin_inventory_markers(root)
    _write_factory(factory)
    assert _rebuild_code(
        root, changed_paths=[factory], no_cluster=True, acquire_lock=False
    ) is True
    assert not _factory_call_targets(root) & {widget_render, product_render}

    factory.unlink()
    assert _rebuild_code(
        root, changed_paths=[factory], no_cluster=True, acquire_lock=False
    ) is True
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)


def test_watch_requeues_caller_when_factory_becomes_excluded(
    tmp_path: Path,
) -> None:
    from graphify.watch import _rebuild_code

    root, factory = _incremental_factory_corpus(tmp_path / "watch-excluded-factory")
    _write_factory(factory)
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False) is True
    widget_render, product_render = _factory_render_ids(root)
    assert not _factory_call_targets(root) & {widget_render, product_render}

    ignore = root / ".graphifyignore"
    ignore.write_text("Factory.kt\n", encoding="utf-8")
    assert _rebuild_code(
        root, changed_paths=[ignore], no_cluster=True, acquire_lock=False
    ) is True
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)


def test_watch_recovery_parsed_provider_invalidates_existing_caller(
    tmp_path: Path,
) -> None:
    from graphify.watch import _rebuild_code

    root, _ = _incremental_factory_corpus(tmp_path / "watch-recovery-provider")
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False) is True
    widget_render, product_render = _factory_render_ids(root)
    assert widget_render in _factory_call_targets(root)

    broken = root / "Broken.kt"
    broken.write_text(
        "package model\n"
        "class A { val value: Money = Money(5) }\n"
        "class B { val value: Ledger = Ledger() }\n"
        "fun Widget(size: Int): Product = Product()\n",
        encoding="utf-8",
    )
    assert _rebuild_code(
        root, changed_paths=[broken], no_cluster=True, acquire_lock=False
    ) is True
    assert not _factory_call_targets(root) & {widget_render, product_render}


def test_watch_zero_node_provider_invalidates_existing_caller(
    tmp_path: Path,
    monkeypatch,
) -> None:
    import graphify.extract as extract_module
    from graphify.watch import _rebuild_code

    root, _ = _incremental_factory_corpus(tmp_path / "watch-zero-provider")
    broken = root / "Factory.KT"
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False) is True
    widget_render, product_render = _factory_render_ids(root)
    assert widget_render in _factory_call_targets(root)

    broken.write_text(
        "package model\nfun Widget(size: Int): Product = Product()\n",
        encoding="utf-8",
    )
    original = extract_module.extract_kotlin

    def fail_broken(path: Path) -> dict:
        if path.name == "Factory.KT":
            raise RuntimeError("forced Kotlin extraction failure")
        return original(path)

    monkeypatch.setattr(extract_module, "extract_kotlin", fail_broken)
    monkeypatch.setitem(extract_module._DISPATCH, ".kt", fail_broken)
    assert _rebuild_code(
        root, changed_paths=[broken], no_cluster=True, acquire_lock=False
    ) is True
    assert not _factory_call_targets(root) & {widget_render, product_render}

    # The failure sentinel must survive graph persistence. A later caller-only
    # rebuild cannot treat the still-broken provider as proven absent.
    use = root / "Use.kt"
    use.write_text(use.read_text() + "// changed again\n", encoding="utf-8")
    assert _rebuild_code(
        root, changed_paths=[use], no_cluster=True, acquire_lock=False
    ) is True
    assert not _factory_call_targets(root) & {widget_render, product_render}


def test_watch_inventory_requeue_survives_invocation_style_changes(
    tmp_path: Path,
) -> None:
    from graphify.watch import _rebuild_code

    parent = tmp_path / "invocation-style"
    root, factory = _incremental_factory_corpus(parent / "project")
    assert _rebuild_code(root, no_cluster=True, acquire_lock=False) is True
    widget_render, product_render = _factory_render_ids(root)
    assert widget_render in _factory_call_targets(root)

    use = root / "Use.kt"
    use.write_text(use.read_text() + "// changed\n", encoding="utf-8")
    previous = Path.cwd()
    try:
        os.chdir(parent)
        assert _rebuild_code(
            Path("project"),
            changed_paths=[Path("project/Use.kt")],
            no_cluster=True,
            acquire_lock=False,
        ) is True
    finally:
        os.chdir(previous)
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)

    _write_factory(factory)
    try:
        os.chdir(parent)
        assert _rebuild_code(
            Path("project"),
            changed_paths=[Path("project/Factory.kt")],
            no_cluster=True,
            acquire_lock=False,
        ) is True
    finally:
        os.chdir(previous)
    assert not _factory_call_targets(root) & {widget_render, product_render}

    factory.unlink()
    assert _rebuild_code(
        root, changed_paths=[factory], no_cluster=True, acquire_lock=False
    ) is True
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)


def test_cli_incremental_preserves_kotlin_call_to_unchanged_target(
    tmp_path: Path,
) -> None:
    root, caller = _incremental_corpus(tmp_path / "cli")

    def run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "graphify",
                "extract",
                str(root),
                "--code-only",
                "--no-cluster",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    first = run()
    assert first.returncode == 0, first.stderr
    assert len(_incremental_member_edges(root)) == 1

    caller.write_text(caller.read_text() + "// changed\n", encoding="utf-8")
    second = run()
    assert second.returncode == 0, second.stderr
    assert "incremental scan" in second.stdout.lower()
    assert len(_incremental_member_edges(root)) == 1


def test_cli_requeues_caller_when_factory_is_added_and_removed(
    tmp_path: Path,
) -> None:
    root, factory = _incremental_factory_corpus(tmp_path / "cli-factory")

    def run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "graphify",
                "extract",
                str(root),
                "--code-only",
                "--no-cluster",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    first = run()
    assert first.returncode == 0, first.stderr
    widget_render, product_render = _factory_render_ids(root)
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)

    _strip_kotlin_inventory_markers(root)
    _write_factory(factory)
    second = run()
    assert second.returncode == 0, second.stderr
    assert "re-queuing 3 kotlin member-call caller" in second.stdout.lower()
    assert not _factory_call_targets(root) & {widget_render, product_render}

    factory.unlink()
    third = run()
    assert third.returncode == 0, third.stderr
    assert "re-queuing 1 kotlin member-call caller" in third.stdout.lower()
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)


def test_cli_requeues_caller_when_factory_becomes_excluded(tmp_path: Path) -> None:
    root, factory = _incremental_factory_corpus(tmp_path / "cli-excluded-factory")
    _write_factory(factory)

    def run() -> subprocess.CompletedProcess:
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "graphify",
                "extract",
                str(root),
                "--code-only",
                "--no-cluster",
            ],
            cwd=tmp_path,
            capture_output=True,
            text=True,
        )

    first = run()
    assert first.returncode == 0, first.stderr
    widget_render, product_render = _factory_render_ids(root)
    assert not _factory_call_targets(root) & {widget_render, product_render}

    (root / ".graphifyignore").write_text("Factory.kt\n", encoding="utf-8")
    second = run()
    assert second.returncode == 0, second.stderr
    assert "re-queuing 1 kotlin member-call caller" in second.stdout.lower()
    assert widget_render in _factory_call_targets(root)
    assert product_render not in _factory_call_targets(root)
