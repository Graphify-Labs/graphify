"""ArkTS (.ets) and HarmonyOS project-config extraction."""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract_ets, extract_harmony_config

FIXTURES = Path(__file__).parent / "fixtures"


def _labels(r):
    return [n["label"] for n in r["nodes"]]


def _relations(r):
    return {e["relation"] for e in r["edges"]}


def test_ets_no_error():
    r = extract_ets(FIXTURES / "sample.ets")
    assert "error" not in r or r.get("nodes"), f"Unexpected failure: {r}"


def test_ets_struct_parsed_as_class():
    """struct should be preprocessed → class so AST picks it up."""
    r = extract_ets(FIXTURES / "sample.ets")
    labels = _labels(r)
    assert any("EnvCheckPage" in l for l in labels), f"Missing EnvCheckPage struct: {labels}"
    assert any("LegacyPage" in l for l in labels), f"Missing LegacyPage struct: {labels}"


def test_ets_finds_regular_class():
    """Plain `class` still works alongside struct."""
    r = extract_ets(FIXTURES / "sample.ets")
    assert any("CheckBean" in l for l in _labels(r))


def test_ets_finds_methods():
    r = extract_ets(FIXTURES / "sample.ets")
    labels = _labels(r)
    assert any("build" in l for l in labels)
    assert any("aboutToAppear" in l for l in labels)
    assert any("startCheck" in l for l in labels)


def test_ets_finds_imports():
    r = extract_ets(FIXTURES / "sample.ets")
    rels = _relations(r)
    assert "imports" in rels or "imports_from" in rels, f"No import relation in {rels}"


def test_ets_component_decorator_is_recognized():
    """@Entry / @ComponentV2 / @Component should become arkts_decorator nodes."""
    r = extract_ets(FIXTURES / "sample.ets")
    deco_nodes = [n for n in r["nodes"] if n.get("node_type") == "arkts_decorator"]
    deco_labels = {n["label"] for n in deco_nodes}
    assert "@Entry" in deco_labels, f"Expected @Entry, got {deco_labels}"
    assert "@ComponentV2" in deco_labels, f"Expected @ComponentV2, got {deco_labels}"
    assert "@Component" in deco_labels, f"Expected @Component, got {deco_labels}"


def test_ets_decorator_edges_target_struct():
    r = extract_ets(FIXTURES / "sample.ets")
    deco_edges = [e for e in r["edges"] if e["relation"] == "decorates"]
    assert len(deco_edges) >= 2, f"Expected ≥2 decorates edges, got {deco_edges}"


def test_ets_state_decorators_create_state_nodes():
    """@Local / @State / @Prop / @Link / @Trace etc. → arkts_state nodes."""
    r = extract_ets(FIXTURES / "sample.ets")
    state_nodes = [n for n in r["nodes"] if n.get("node_type") == "arkts_state"]
    state_labels = {n["label"] for n in state_nodes}
    # V2 decorators
    assert any("@Local" in l for l in state_labels), f"No @Local in {state_labels}"
    assert any("@Trace" in l for l in state_labels), f"No @Trace in {state_labels}"
    # V1 decorators
    assert any("@State" in l for l in state_labels), f"No @State in {state_labels}"
    assert any("@Prop" in l for l in state_labels), f"No @Prop in {state_labels}"
    assert any("@Link" in l for l in state_labels), f"No @Link in {state_labels}"


def test_ets_no_dangling_edges():
    """Source endpoints must always exist as nodes. Import targets may legitimately
    point at external modules that are not nodes until cross-file resolution."""
    r = extract_ets(FIXTURES / "sample.ets")
    node_ids = {n["id"] for n in r["nodes"]}
    for e in r["edges"]:
        assert e["source"] in node_ids, f"Dangling source: {e}"
        if e["relation"] in ("imports_from", "imports"):
            continue  # external-module targets are OK
        assert e["target"] in node_ids, f"Dangling target: {e}"


def test_ets_preserves_line_numbers():
    """struct→class preprocessing must keep byte offsets so line numbers match."""
    r = extract_ets(FIXTURES / "sample.ets")
    for n in r["nodes"]:
        if n["label"] == "EnvCheckPage":
            assert n["source_location"] == "L29", f"Line mismatch: {n}"
            break
    else:
        pytest.fail("EnvCheckPage node not found")


# ── Enriched ArkTS semantics (V1+V2 full coverage) ───────────────────────────

def test_ets_component_struct_marked_as_component():
    """@Component / @ComponentV2 struct nodes should be tagged arkts_component."""
    r = extract_ets(FIXTURES / "sample.ets")
    comps = {n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_component"}
    assert "EnvCheckPage" in comps, f"EnvCheckPage not marked as component: {comps}"
    assert "LegacyPage" in comps, f"LegacyPage not marked as component: {comps}"


def test_ets_observed_v2_class_marked():
    """@ObservedV2 class should be tagged arkts_observed_v2."""
    r = extract_ets(FIXTURES / "sample.ets")
    observed = {n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_observed_v2"}
    assert "CheckBean" in observed, f"CheckBean not marked as observed_v2: {observed}"


def test_ets_lifecycle_methods_tagged():
    """Lifecycle methods are typed arkts_lifecycle and stay attached to their struct.

    The AST already links struct -> method with a structural `method` edge and the
    simple graph keeps that edge when a pair collapses, so no parallel
    `has_lifecycle` edge is emitted for methods the AST found.
    """
    r = extract_ets(FIXTURES / "sample.ets")
    lifecycle = {n["id"]: n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_lifecycle"}
    assert any("aboutToAppear" in label for label in lifecycle.values())
    assert any("onPageShow" in label for label in lifecycle.values())
    attached = {e["target"] for e in r["edges"] if e["relation"] in ("method", "has_lifecycle")}
    assert set(lifecycle) <= attached
    assert not [e for e in r["edges"]
                if e["relation"] == "has_lifecycle" and (e["source"], e["target"]) in
                {(m["source"], m["target"]) for m in r["edges"] if m["relation"] == "method"}]

def test_ets_observes_edges_for_traced_fields():
    """@Trace fields inside @ObservedV2 class → observes edge from class."""
    r = extract_ets(FIXTURES / "sample.ets")
    obs_edges = [e for e in r["edges"] if e["relation"] == "observes"]
    assert len(obs_edges) >= 2, f"Expected ≥2 observes edges, got {obs_edges}"


def test_ets_watch_binds_to_target_method():
    """@Watch('onCountChange') should create a watches edge to the onCountChange method."""
    r = extract_ets(FIXTURES / "sample.ets")
    watch_edges = [e for e in r["edges"] if e["relation"] == "watches"]
    assert len(watch_edges) >= 1, f"Expected ≥1 watches edge, got {watch_edges}"
    watch_nodes = [n for n in r["nodes"] if n.get("node_type") == "arkts_watch"]
    assert any("onCountChange" in n["label"] for n in watch_nodes)


def test_ets_monitor_targets_captured():
    """@Monitor('checkState', 'model.titleName') → two monitor_target nodes + monitors edges."""
    r = extract_ets(FIXTURES / "sample.ets")
    monitor_nodes = [n for n in r["nodes"] if n.get("node_type") == "arkts_monitor_target"]
    monitor_labels = {n["label"] for n in monitor_nodes}
    assert any("checkState" in l for l in monitor_labels)
    assert any("model.titleName" in l for l in monitor_labels)
    monitors_edges = [e for e in r["edges"] if e["relation"] == "monitors"]
    assert len(monitors_edges) >= 2


def test_ets_provide_consume_share_key_node():
    """@Provider('sharedKey') + @Consume('sharedKey') should connect via same key node."""
    r = extract_ets(FIXTURES / "sample.ets")
    provides = [e for e in r["edges"] if e["relation"] == "provides"]
    consumes = [e for e in r["edges"] if e["relation"] == "consumes"]
    assert len(provides) >= 1, f"No provides edges: {provides}"
    assert len(consumes) >= 1, f"No consumes edges: {consumes}"
    # Same target key node
    assert {e["target"] for e in provides} == {e["target"] for e in consumes}


def test_ets_storage_bindings_emit_key_nodes():
    """@StorageLink('globalUser') → arkts_app_storage_key node, storage_binds edge."""
    r = extract_ets(FIXTURES / "sample.ets")
    app_keys = {n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_app_storage_key"}
    local_keys = {n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_local_storage_key"}
    assert any("globalUser" in l for l in app_keys), f"globalUser not found: {app_keys}"
    assert any("sessionId" in l for l in local_keys), f"sessionId not found: {local_keys}"


def test_ets_ui_composition_from_build():
    """build() body should emit uses_component edges to child components."""
    r = extract_ets(FIXTURES / "sample.ets")
    ui_edges = [e for e in r["edges"] if e["relation"] == "uses_component"]
    used_labels = set()
    node_by_id = {n["id"]: n for n in r["nodes"]}
    for e in ui_edges:
        if e["target"] in node_by_id:
            used_labels.add(node_by_id[e["target"]]["label"])
    # EnvCheckPage uses at least: NavDestination, Column, TitleBar, Scroll, List, ForEach, ListItem, Text, Button
    expected = {"NavDestination", "Column", "TitleBar", "Scroll", "List", "ForEach", "ListItem", "Text", "Button"}
    missing = expected - used_labels
    assert not missing, f"Missing UI components: {missing}; got {used_labels}"


def test_ets_resources_extracted():
    """$r('app.color.xxx') / $r('app.string.xxx') → arkts_resource nodes."""
    r = extract_ets(FIXTURES / "sample.ets")
    resources = [n for n in r["nodes"] if n.get("node_type") == "arkts_resource"]
    resource_keys = {n["label"] for n in resources}
    assert any("app.media.icon" in l for l in resource_keys)
    assert any("app.string.submit" in l for l in resource_keys)
    assert any("app.color.color_text" in l for l in resource_keys)
    ref_edges = [e for e in r["edges"] if e["relation"] == "references_resource"]
    assert len(ref_edges) >= 2


def test_ets_all_v1_state_decorators_recognized():
    """Check @State / @Prop / @Link / @Provide / @Consume / @Watch / @Observed / @ObjectLink."""
    r = extract_ets(FIXTURES / "sample.ets")
    state_labels = {n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_state"}
    # We have @State oldFashionedState, @Prop title, @Link shared in the fixture
    v1_seen = {"State", "Prop", "Link"}
    for needed in v1_seen:
        assert any(f"@{needed}" in l for l in state_labels), f"Missing @{needed} state node"


def test_ets_all_v2_state_decorators_recognized():
    """Check @Local / @Param / @Event / @Trace / @Computed via state nodes."""
    r = extract_ets(FIXTURES / "sample.ets")
    state_labels = {n["label"] for n in r["nodes"] if n.get("node_type") == "arkts_state"}
    for needed in ("Local", "Param", "Event", "Trace", "Computed"):
        assert any(f"@{needed}" in l for l in state_labels), f"Missing @{needed} state node: {state_labels}"


# ── HarmonyOS config files ───────────────────────────────────────────────────

def test_harmony_module_json5_no_error():
    r = extract_harmony_config(FIXTURES / "module.json5")
    assert "error" not in r or r.get("nodes"), f"Failed: {r}"


def test_harmony_module_finds_abilities():
    r = extract_harmony_config(FIXTURES / "module.json5")
    abilities = [n for n in r["nodes"] if n.get("node_type") == "harmony_ability"]
    assert any("EntryAbility" in n["label"] for n in abilities), f"Missing EntryAbility: {abilities}"
    # declares_ability edge
    assert any(e["relation"] == "declares_ability" for e in r["edges"])


def test_harmony_module_finds_permissions():
    r = extract_harmony_config(FIXTURES / "module.json5")
    perms = [n for n in r["nodes"] if n.get("node_type") == "harmony_permission"]
    perm_names = {n["label"] for n in perms}
    assert "ohos.permission.CAMERA" in perm_names
    assert "ohos.permission.MICROPHONE" in perm_names
    assert "ohos.permission.INTERNET" in perm_names
    assert any(e["relation"] == "requires_permission" for e in r["edges"])


def test_harmony_router_map():
    r = extract_harmony_config(FIXTURES / "router_map.json")
    routes = [n for n in r["nodes"] if n.get("node_type") == "harmony_route"]
    route_names = {n["label"] for n in routes}
    assert "Route:GuidePage" in route_names
    assert "Route:EnvCheckPage" in route_names
    assert "Route:UploadPage" in route_names
    # route_maps_to inferred edges
    map_edges = [e for e in r["edges"] if e["relation"] == "route_maps_to"]
    assert len(map_edges) >= 3


def test_harmony_oh_package():
    r = extract_harmony_config(FIXTURES / "oh-package.json5")
    deps = [n for n in r["nodes"] if n.get("node_type") == "harmony_dependency"]
    dep_names = {n["label"] for n in deps}
    assert "@ohzrtc/lib_zrtc_sdk" in dep_names
    assert "@ohos/axios" in dep_names
    # devDependencies should come through too
    assert "@ohos/hypium" in dep_names
    # depends_on vs dev_depends_on distinction
    rels = {e["relation"] for e in r["edges"]}
    assert "depends_on" in rels
    assert "dev_depends_on" in rels


def test_harmony_json5_handles_comments_and_trailing_commas():
    """Fixture uses both // comments and trailing commas — must not choke."""
    r = extract_harmony_config(FIXTURES / "module.json5")
    assert "error" not in r or r.get("nodes")
    # metadata object has a trailing comma; file must still parse
    assert any(n.get("node_type") == "harmony_module" for n in r["nodes"])


def test_harmony_config_file_detection():
    """classify_file should return CODE for HarmonyOS config files."""
    from graphify.detect import classify_file, FileType, HARMONY_CONFIG_FILES
    assert "module.json5" in HARMONY_CONFIG_FILES
    assert "oh-package.json5" in HARMONY_CONFIG_FILES
    assert "router_map.json" in HARMONY_CONFIG_FILES
    assert classify_file(FIXTURES / "module.json5") == FileType.CODE
    assert classify_file(FIXTURES / "router_map.json") == FileType.CODE
    assert classify_file(FIXTURES / "oh-package.json5") == FileType.CODE


def test_ets_component_minted_when_typescript_grammar_drops_it():
    """ArkUI DSL can make tree-sitter-typescript drop a whole struct; the component
    node (and the edges hanging off it) must still exist."""
    from graphify.extract import _ETS_STRUCT_PATTERN, _TS_CONFIG, _extract_generic

    path = FIXTURES / "arkts_dsl_heavy.ets"
    ast_only = _extract_generic(
        path, _TS_CONFIG, source_override=_ETS_STRUCT_PATTERN.sub(b"class ", path.read_bytes()))
    assert "HeavyPage" not in _labels(ast_only)  # precondition: the grammar really drops it

    r = extract_ets(path)
    component = [n for n in r["nodes"] if n["label"] == "HeavyPage"]
    assert len(component) == 1 and component[0]["node_type"] == "arkts_component"
    ids = {n["id"] for n in r["nodes"]}
    assert any(e["target"] == component[0]["id"] and e["relation"] == "contains" for e in r["edges"])
    hanging = [e for e in r["edges"] if e["source"] == component[0]["id"]]
    assert {"uses_component", "references_resource", "contains_state"} <= {e["relation"] for e in hanging}
    assert all(e["target"] in ids for e in hanging)


def test_harmony_router_map_links_route_to_page_struct(tmp_path):
    """route_maps_to resolves pageSourceFile against the owning module and targets
    the struct declared in that page, keyed the same way extract_ets keys it."""
    module = tmp_path / "feature"
    page = module / "src/main/ets/pages/DetailPage.ets"
    page.parent.mkdir(parents=True)
    page.write_text("@Entry\n@Component\nstruct DetailView {\n  build() {}\n}\n", encoding="utf-8")
    router = module / "src/main/resources/base/profile/router_map.json"
    router.parent.mkdir(parents=True)
    router.write_text('{"routerMap":[{"name":"detail","pageSourceFile":"src/main/ets/pages/DetailPage.ets",'
                      '"buildFunction":"DetailBuilder"}]}', encoding="utf-8")

    page_ids = {n["id"] for n in extract_ets(page)["nodes"] if n["label"] == "DetailView"}
    targets = {e["target"] for e in extract_harmony_config(router)["edges"] if e["relation"] == "route_maps_to"}
    assert page_ids and targets == page_ids


def test_harmony_config_ids_and_labels_do_not_embed_the_checkout_path(tmp_path):
    """A manifest without "name" falls back to the file stem; that fallback feeds
    global IDs, so the absolute checkout path must not leak into them."""
    from graphify.extractors.base import _make_id
    root = tmp_path / "checkout-a"
    root.mkdir()
    (root / "oh-package.json5").write_text('{"dependencies": {"@ohos/lib": "1.0.0"}}', encoding="utf-8")
    (root / "build-profile.json5").write_text('{"app": {"products": []}, "modules": []}', encoding="utf-8")
    for name in ("oh-package.json5", "build-profile.json5"):
        r = extract_harmony_config(root / name)
        for n in r["nodes"]:
            if n.get("node_type") == "harmony_config":
                continue  # the file node is keyed by path like every other file node
            assert str(tmp_path) not in n["label"], n
            assert _make_id(str(tmp_path)) not in n["id"], n
