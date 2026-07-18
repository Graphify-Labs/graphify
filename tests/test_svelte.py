"""Svelte and SvelteKit author-AST structural extraction regression coverage.

Christian Winther's upstream Graphify PR #714 established the script-import
recovery requirement. Fixtures in this module are intentionally synthetic.
"""

from __future__ import annotations

import json
from pathlib import Path

import networkx as nx

from graphify.build import build_from_json, build_merge
from graphify.extract import _file_node_id, _make_id, extract, extract_svelte
from graphify.extractors.svelte import (
    SVELTE_AST_CACHE_MAX_ENTRIES,
    clear_svelte_ast_cache,
    mask_svelte_script_facts,
    parse_svelte_ast_batch,
    svelte_ast_cache_info,
    svelte_script_languages,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _targets(result: dict, relation: str) -> set[str]:
    return {
        str(edge.get("target") or "")
        for edge in result.get("edges", [])
        if edge.get("relation") == relation
    }


def test_static_svelte_import_resolves_to_svelte_ts_rune_module(tmp_path: Path):
    target = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        "export class PanelViewModel {}\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import { PanelViewModel } from './PanelViewModel.svelte'
</script>

<section>Panel</section>
""",
    )

    result = extract_svelte(component)

    expected = _make_id(str(target))
    assert expected in _targets(result, "imports_from")
    import_edges = [
        edge for edge in result["edges"]
        if edge.get("relation") == "imports_from" and edge.get("target") == expected
    ]
    assert len(import_edges) == 1
    assert import_edges[0]["source_location"] == "L2"


def test_compiler_script_ranges_preserve_utf8_bytes_and_original_lines(tmp_path: Path):
    source = """<h1>Crème ☕</h1>
<script lang="ts">
export function load(): void {}
</script>
<p>後</p>
"""

    path = tmp_path / "Unicode.svelte"
    facts = parse_svelte_ast_batch([(path, source)])[path]
    masked = mask_svelte_script_facts(source, facts, language="ts")

    assert len(masked) == len(source.encode("utf-8"))
    assert [i for i, byte in enumerate(masked) if byte == 10] == [
        i for i, byte in enumerate(source.encode("utf-8")) if byte == 10
    ]
    assert b"export function load(): void {}" in masked
    assert "Crème".encode() not in masked
    assert "後".encode() not in masked


def test_instance_and_both_module_script_forms_use_their_own_grammars(tmp_path: Path):
    legacy = _write(
        tmp_path / "LegacyMixed.svelte",
        """<script context="module">
export function legacyModule() {}
</script>
<script lang="ts">
export function typedInstance<T>(value: T): T { return value }
</script>

<div>Legacy mixed</div>
""",
    )
    modern = _write(
        tmp_path / "ModernMixed.svelte",
        """<script module lang="ts">
export function modernModule<T>(value: T): T { return value }
</script>
<script>
export function jsInstance() {}
</script>

<div>Modern mixed</div>
""",
    )

    for component in (legacy, modern):
        source = component.read_text(encoding="utf-8")
        facts = parse_svelte_ast_batch([(component, source)])[component]
        assert svelte_script_languages(facts) == {"js", "ts"}

    result = extract([legacy, modern], cache_root=tmp_path, root=tmp_path)
    by_label = {node["label"]: node for node in result["nodes"]}

    assert by_label["legacyModule()"]["source_location"] == "L2"
    assert by_label["typedInstance()"]["source_location"] == "L5"
    assert by_label["modernModule()"]["source_location"] == "L2"
    assert by_label["jsInstance()"]["source_location"] == "L5"


def test_svelte_script_joins_cross_file_symbol_and_call_resolution(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        """export class PanelViewModel {
  refresh(): void {}
}
""",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import { PanelViewModel } from './PanelViewModel.svelte'
const viewModel = new PanelViewModel()

export function reload(): void {
  viewModel.refresh()
}
</script>
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    relations = {
        (labels.get(edge["source"]), edge["relation"], labels.get(edge["target"]))
        for edge in result["edges"]
    }

    assert ("reload()", "calls", ".refresh()") in relations


def test_svelte_script_uses_default_import_through_barrel_for_calls(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        """export class PanelViewModel {
  refresh(): void {}
}
""",
    )
    barrel = _write(
        tmp_path / "index.ts",
        "export { PanelViewModel as default } from './PanelViewModel.svelte'\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import VM from './index'
const viewModel = new VM()

export function reload(): void {
  viewModel.refresh()
}
</script>
""",
    )

    result = extract([component, barrel, view_model], cache_root=tmp_path, root=tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}

    assert any(
        labels.get(edge["source"]) == "reload()"
        and edge["relation"] == "calls"
        and labels.get(edge["target"]) == ".refresh()"
        for edge in result["edges"]
    )


def test_template_view_and_viewmodel_relationships_are_line_cited(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        """export class PanelViewModel {
  title = $state('Panel')
  upperTitle = $derived(this.title.toUpperCase())

  constructor() {
    $effect(() => console.log(this.upperTitle))
  }

  refresh(): void {}
}
""",
    )
    child = _write(
        tmp_path / "PanelBody.svelte",
        """<script lang="ts">
import type { PanelViewModel } from './PanelViewModel.svelte'
interface Props {
  viewModel: PanelViewModel
}
let { viewModel }: Props = $props()
</script>

<button onclick={() => viewModel.refresh()}>
  {viewModel.title}
</button>
""",
    )
    parent = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import PanelBody from './PanelBody.svelte'
import { PanelViewModel } from './PanelViewModel.svelte'
const viewModel = new PanelViewModel()
</script>

<PanelBody onready={() => viewModel.refresh()} {viewModel} />
""",
    )

    result = extract([parent, child, view_model], cache_root=tmp_path, root=tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    nodes_by_label = {node["label"]: node for node in result["nodes"]}

    def matching(relation: str, source_label: str, target_label: str) -> list[dict]:
        return [
            edge for edge in result["edges"]
            if edge["relation"] == relation
            and labels.get(edge["source"]) == source_label
            and labels.get(edge["target"]) == target_label
        ]

    render = matching("renders", "<PanelBody>", "PanelBody.svelte")
    assert render and render[0]["source_location"] == "L7"
    passed = matching("passes_prop", "new PanelViewModel()", "<PanelBody>")
    assert passed and passed[0]["metadata"]["prop"] == "viewModel"
    assert matching("instantiates", "new PanelViewModel()", "PanelViewModel")
    prop_reference = matching("references", "viewModel: PanelViewModel", "PanelViewModel")
    assert any(edge.get("context") == "component_prop_type" for edge in prop_reference)
    read = matching("accesses", "viewModel: PanelViewModel", ".title")
    assert read and read[0]["source_location"] == "L10"
    invoked = matching("calls", "viewModel: PanelViewModel", ".refresh()")
    assert invoked and invoked[0]["source_location"] == "L9"

    assert nodes_by_label[".title"]["type"] == "svelte_state"
    assert nodes_by_label[".upperTitle"]["type"] == "svelte_derived"
    effect = nodes_by_label["$effect@L6"]
    assert effect["type"] == "svelte_effect"
    assert matching("depends_on", ".upperTitle", ".title")
    assert matching("depends_on", "$effect@L6", ".upperTitle")

    graph = build_from_json(result, directed=True, root=tmp_path)
    surviving_relations = {data.get("relation") for _u, _v, data in graph.edges(data=True)}
    assert {
        "renders",
        "passes_prop",
        "instantiates",
        "references",
        "accesses",
        "calls",
        "depends_on",
    } <= surviving_relations


def test_aliased_component_render_resolves_to_real_svelte_file(tmp_path: Path):
    _write(
        tmp_path / "tsconfig.json",
        json.dumps({"compilerOptions": {"paths": {"$lib/*": ["./src/lib/*"]}}}),
    )
    card = _write(tmp_path / "src/lib/Card.svelte", "<article>Card</article>\n")
    page = _write(
        tmp_path / "src/routes/Page.svelte",
        """<script lang="ts">
import Card from '$lib/Card.svelte'
</script>

<Card />
""",
    )

    result = extract([page, card], cache_root=tmp_path, root=tmp_path)
    renders = [edge for edge in result["edges"] if edge["relation"] == "renders"]

    assert len(renders) == 1
    assert renders[0]["target"] == _file_node_id(Path("src/lib/Card.svelte"))
    assert renders[0]["source_location"] == "L5"


def test_commented_import_and_markup_do_not_create_component_usage(tmp_path: Path):
    _write(tmp_path / "Ghost.svelte", "<p>Ghost</p>\n")
    page = _write(
        tmp_path / "Page.svelte",
        """<script>
// import Ghost from './Ghost.svelte'
</script>

<!-- <Ghost /> -->
<main>Nothing rendered</main>
""",
    )

    result = extract_svelte(page)

    assert not [edge for edge in result["edges"] if edge["relation"] == "renders"]


def test_svelte_semantic_edges_survive_graph_build_pruning(tmp_path: Path):
    child = _write(tmp_path / "Child.svelte", "<p>Child</p>\n")
    parent = _write(
        tmp_path / "Parent.svelte",
        """<script>
import Child from './Child.svelte'
</script>
<Child />
""",
    )

    extraction = extract([parent, child], cache_root=tmp_path, root=tmp_path)
    graph = build_from_json(extraction, directed=True, root=tmp_path)
    source = next(
        node_id for node_id, data in graph.nodes(data=True)
        if data.get("type") == "svelte_component_usage"
    )
    target = _file_node_id(Path("Child.svelte"))

    assert graph.has_edge(source, target)
    assert graph[source][target]["relation"] == "renders"


def test_incremental_refresh_replaces_stale_component_render_edge(tmp_path: Path):
    first = _write(tmp_path / "FirstCard.svelte", "<p>First</p>\n")
    second = _write(tmp_path / "SecondCard.svelte", "<p>Second</p>\n")
    page = _write(
        tmp_path / "Page.svelte",
        """<script>
import Card from './FirstCard.svelte'
</script>
<Card />
""",
    )
    initial = extract([page, first, second], cache_root=tmp_path, root=tmp_path)
    initial_graph = build_from_json(initial, directed=True, root=tmp_path)
    graph_path = tmp_path / "graph.json"
    graph_path.write_text(
        json.dumps(nx.node_link_data(initial_graph, edges="edges")),
        encoding="utf-8",
    )

    page.write_text(
        """<script>
import Card from './SecondCard.svelte'
</script>
<Card />
""",
        encoding="utf-8",
    )
    refreshed = extract([page, first, second], cache_root=tmp_path, root=tmp_path)
    page_chunk = {
        "nodes": [node for node in refreshed["nodes"] if node.get("source_file") == "Page.svelte"],
        "edges": [edge for edge in refreshed["edges"] if edge.get("source_file") == "Page.svelte"],
    }
    updated = build_merge(
        [page_chunk],
        graph_path,
        directed=True,
        dedup=False,
        root=tmp_path,
    )
    first_id = _file_node_id(Path("FirstCard.svelte"))
    second_id = _file_node_id(Path("SecondCard.svelte"))
    usage_ids = {
        node_id
        for node_id, data in updated.nodes(data=True)
        if data.get("type") == "svelte_component_usage"
        and data.get("source_file") == "Page.svelte"
    }

    render_targets = {
        target
        for usage_id in usage_ids
        for _source, target, data in updated.edges(usage_id, data=True)
        if data.get("relation") == "renders"
    }
    assert render_targets == {second_id}
    assert first_id not in render_targets


def test_default_import_metadata_never_exports_absolute_resolved_paths(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        "export default class PanelViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import VM from './PanelViewModel.svelte'
const viewModel = new VM()
viewModel.refresh()
</script>
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)
    serialized_metadata = json.dumps(
        [item.get("metadata") for item in result["nodes"] + result["edges"]]
    )

    assert str(tmp_path) not in serialized_metadata


def test_text_and_literal_attributes_do_not_become_template_calls(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        "export class PanelViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import type { PanelViewModel } from './PanelViewModel.svelte'
let { viewModel }: { viewModel: PanelViewModel } = $props()
</script>

<p title="viewModel.refresh()">viewModel.refresh()</p>
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)

    assert not [
        edge
        for edge in result["edges"]
        if edge.get("relation") == "calls"
        and edge.get("context") == "template_method_call"
    ]


def test_component_markup_inside_expression_string_does_not_render(tmp_path: Path):
    ghost = _write(tmp_path / "Ghost.svelte", "<p>Ghost</p>\n")
    page = _write(
        tmp_path / "Page.svelte",
        """<script>
import Ghost from './Ghost.svelte'
</script>

{'<Ghost />'}
""",
    )

    result = extract([page, ghost], cache_root=tmp_path, root=tmp_path)

    assert not [edge for edge in result["edges"] if edge.get("relation") == "renders"]


def test_commented_construction_does_not_instantiate_viewmodel(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        "export class PanelViewModel {}\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import { PanelViewModel } from './PanelViewModel.svelte'
// const viewModel = new PanelViewModel()
</script>

<main>No construction</main>
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)

    assert not [
        node for node in result["nodes"] if node.get("type") == "svelte_construction"
    ]
    assert not [edge for edge in result["edges"] if edge.get("relation") == "instantiates"]


def test_component_imported_through_barrel_resolves_render_target(tmp_path: Path):
    card = _write(tmp_path / "Card.svelte", "<article>Card</article>\n")
    barrel = _write(tmp_path / "index.ts", "export { default as Card } from './Card.svelte'\n")
    page = _write(
        tmp_path / "Page.svelte",
        """<script lang="ts">
import { Card } from './index'
</script>

<Card />
""",
    )

    result = extract([page, barrel, card], cache_root=tmp_path, root=tmp_path)
    renders = [edge for edge in result["edges"] if edge.get("relation") == "renders"]

    assert len(renders) == 1
    assert renders[0]["target"] == _file_node_id(Path("Card.svelte"))


def test_legacy_svelte_component_expression_resolves_render_target(tmp_path: Path):
    card = _write(tmp_path / "Card.svelte", "<article>Card</article>\n")
    page = _write(
        tmp_path / "Page.svelte",
        """<script>
import Card from './Card.svelte'
</script>
<svelte:component this={Card} />
""",
    )

    result = extract([page, card], cache_root=tmp_path, root=tmp_path)
    renders = [edge for edge in result["edges"] if edge.get("relation") == "renders"]

    assert len(renders) == 1
    assert renders[0]["target"] == _file_node_id(Path("Card.svelte"))
    assert renders[0]["metadata"]["imported_as"] == "Card"


def test_named_import_alias_preserves_cross_file_receiver_resolution(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        """export class PanelViewModel {
  refresh(): void {}
}
""",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import { PanelViewModel as VM } from './PanelViewModel.svelte'
const viewModel = new VM()

export function reload(): void {
  viewModel.refresh()
}
</script>
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)
    labels = {node["id"]: node["label"] for node in result["nodes"]}

    assert any(
        labels.get(edge["source"]) == "reload()"
        and edge.get("relation") == "calls"
        and labels.get(edge["target"]) == ".refresh()"
        for edge in result["edges"]
    )


def test_rune_prefix_lookalikes_are_not_svelte_runes(tmp_path: Path):
    module = _write(
        tmp_path / "Lookalikes.svelte.ts",
        """export class Lookalikes {
  state = $stateful('no')
  derived = $derivedValue(this.state)

  run(): void {
    $effectively(() => this.derived)
  }
}
""",
    )

    result = extract([module], cache_root=tmp_path, root=tmp_path)

    assert not [
        node
        for node in result["nodes"]
        if node.get("type") in {"svelte_state", "svelte_derived", "svelte_effect"}
    ]


def test_rune_ast_matching_accepts_compiler_valid_member_spacing(tmp_path: Path):
    module = _write(
        tmp_path / "SpacedRunes.svelte.ts",
        """export class SpacedRunes {
  state = $state .raw({ value: 1 })
  derived = $derived /* compiler-valid trivia */ .by(() => this.state.value)

  run(): void {
    $effect .pre(() => console.log(this.derived))
  }
}
""",
    )

    result = extract([module], cache_root=tmp_path, root=tmp_path)
    by_label = {node["label"]: node for node in result["nodes"]}

    assert by_label[".state"]["type"] == "svelte_state"
    assert by_label[".derived"]["type"] == "svelte_derived"
    assert by_label["$effect.pre@L6"]["type"] == "svelte_effect"


def test_constructor_first_assignment_is_recognised_as_state(tmp_path: Path):
    module = _write(
        tmp_path / "ConstructorState.svelte.ts",
        """export class ConstructorState {
  constructor(initial: string) {
    this.value = $state(initial)
  }
}
""",
    )

    result = extract([module], cache_root=tmp_path, root=tmp_path)
    states = [node for node in result["nodes"] if node.get("type") == "svelte_state"]

    assert [(node["label"], node["source_location"]) for node in states] == [
        (".value", "L3")
    ]


def test_svelte_sources_are_parsed_in_one_cached_batch(tmp_path: Path, monkeypatch):
    from graphify.extractors import svelte as svelte_extractor

    components = [
        _write(tmp_path / f"Component{index}.svelte", f"<p>{index}</p>\n")
        for index in range(3)
    ]
    calls: list[int] = []
    invoke = svelte_extractor._invoke_svelte_bridge

    def counting_invoke(request: dict) -> dict:
        calls.append(len(request["files"]))
        return invoke(request)

    clear_svelte_ast_cache()
    monkeypatch.setattr(svelte_extractor, "_invoke_svelte_bridge", counting_invoke)
    extract(components, cache_root=tmp_path, root=tmp_path)
    extract(components, cache_root=tmp_path, root=tmp_path)

    assert calls == [3]


def test_full_extract_owns_max_plus_one_svelte_facts_without_lru_reparse(
    tmp_path: Path,
    monkeypatch,
):
    from graphify.extractors import svelte as svelte_extractor

    components = [
        _write(tmp_path / f"Component{index}.svelte", f"<p>{index}</p>\n")
        for index in range(SVELTE_AST_CACHE_MAX_ENTRIES + 1)
    ]
    calls: list[int] = []

    def fake_invoke(request: dict) -> dict:
        calls.append(len(request["files"]))
        return {
            "schema_version": svelte_extractor.SVELTE_AST_SCHEMA_VERSION,
            "compiler_version": svelte_extractor.SVELTE_COMPILER_VERSION,
            "svelte2tsx_version": svelte_extractor.SVELTE2TSX_VERSION,
            "typescript_version": svelte_extractor.TYPESCRIPT_VERSION,
            "files": [
                {
                    "id": item["id"],
                    "path": item["path"],
                    "scripts": [],
                    "imports": [],
                    "diagnostics": [],
                }
                for item in request["files"]
            ],
        }

    clear_svelte_ast_cache()
    monkeypatch.setattr(svelte_extractor, "_invoke_svelte_bridge", fake_invoke)

    extract(components, cache_root=tmp_path, root=tmp_path, parallel=False)
    extract(components, cache_root=tmp_path, root=tmp_path, parallel=False)

    # The first run is one compiler batch. The second reparses only the one
    # deterministically evicted entry; neither resolver pass may invoke Node.
    assert calls == [SVELTE_AST_CACHE_MAX_ENTRIES + 1, 1]
    assert svelte_ast_cache_info() == {
        "entries": SVELTE_AST_CACHE_MAX_ENTRIES,
        "max_entries": SVELTE_AST_CACHE_MAX_ENTRIES,
    }


def test_full_extract_does_not_retry_degraded_svelte_facts_downstream(
    tmp_path: Path,
    monkeypatch,
):
    from graphify.extractors import svelte as svelte_extractor

    components = [
        _write(tmp_path / f"Unavailable{index}.svelte", "<p>Unavailable</p>\n")
        for index in range(SVELTE_AST_CACHE_MAX_ENTRIES + 1)
    ]
    calls: list[int] = []

    def failing_invoke(request: dict) -> dict:
        calls.append(len(request["files"]))
        raise RuntimeError("compiler unavailable")

    clear_svelte_ast_cache()
    monkeypatch.setattr(svelte_extractor, "_invoke_svelte_bridge", failing_invoke)

    result = extract(components, cache_root=tmp_path, root=tmp_path, parallel=False)

    assert calls == [SVELTE_AST_CACHE_MAX_ENTRIES + 1]
    assert result["edges"] == []


def test_incremental_extract_reparses_only_changed_svelte_source(
    tmp_path: Path,
    monkeypatch,
):
    from graphify.extractors import svelte as svelte_extractor

    components = [
        _write(tmp_path / f"Component{index}.svelte", f"<p>{index}</p>\n")
        for index in range(3)
    ]
    calls: list[int] = []

    def fake_invoke(request: dict) -> dict:
        calls.append(len(request["files"]))
        return {
            "schema_version": svelte_extractor.SVELTE_AST_SCHEMA_VERSION,
            "compiler_version": svelte_extractor.SVELTE_COMPILER_VERSION,
            "svelte2tsx_version": svelte_extractor.SVELTE2TSX_VERSION,
            "typescript_version": svelte_extractor.TYPESCRIPT_VERSION,
            "files": [
                {
                    "id": item["id"],
                    "path": item["path"],
                    "scripts": [],
                    "imports": [],
                    "diagnostics": [],
                }
                for item in request["files"]
            ],
        }

    clear_svelte_ast_cache()
    monkeypatch.setattr(svelte_extractor, "_invoke_svelte_bridge", fake_invoke)

    extract(components, cache_root=tmp_path, root=tmp_path, parallel=False)
    components[1].write_text("<p>changed</p>\n", encoding="utf-8")
    extract(components, cache_root=tmp_path, root=tmp_path, parallel=False)

    assert calls == [3, 1]


def test_missing_node_surfaces_degraded_diagnostic_without_guesses(
    tmp_path: Path,
    monkeypatch,
):
    component = _write(
        tmp_path / "Unavailable.svelte",
        """<script>const viewModel = new Missing()</script>
<MissingComponent onclick={() => viewModel.refresh()} />
""",
    )
    clear_svelte_ast_cache()
    monkeypatch.setenv("GRAPHIFY_NODE", str(tmp_path / "definitely-not-node"))

    result = extract_svelte(component)

    assert result["diagnostics"] == [
        {
            "code": "svelte_ast_unavailable",
            "message": "Svelte AST unavailable: Node.js is not installed or not on PATH",
            "degraded": True,
        }
    ]
    assert "Svelte AST unavailable" in result["error"]
    assert not result["edges"]
    assert not [
        node
        for node in result["nodes"]
        if node.get("type", "").startswith("svelte_")
    ]


def test_semantic_enrichment_failure_keeps_author_ast_structure(tmp_path: Path):
    component = _write(tmp_path / "Degraded.svelte", "<Panel />\n")
    diagnostic = {
        "code": "svelte_semantic_unavailable",
        "message": "Svelte TypeScript semantic enrichment unavailable: synthetic failure",
        "degraded": True,
    }
    facts = {
        "scripts": [],
        "imports": [],
        "constructions": [],
        "props": [],
        "components": [{
            "name": "Panel",
            "binding_id": None,
            "props": [],
            "start": 0,
            "end": 9,
            "start_byte": 0,
            "end_byte": 9,
            "line": 1,
        }],
        "template_members": [],
        "dynamic_imports": [],
        "diagnostics": [diagnostic],
    }

    result = extract_svelte(component, _ast_facts=facts, _source="<Panel />\n")

    assert result["diagnostics"] == [diagnostic]
    assert any(node.get("type") == "svelte_component_usage" for node in result["nodes"])
    assert not [edge for edge in result["edges"] if edge.get("relation") == "renders"]


def test_fragment_walk_collects_expressions_from_all_container_shapes(tmp_path: Path):
    component = tmp_path / "Containers.svelte"
    source = """<script lang="ts">
let { vm, items, promise, visible, action }: any = $props()
</script>

{#if vm.visible}<p>{vm.ifValue}</p>{/if}
{#each items as item (vm.key(item))}<p>{vm.eachValue}</p>{/each}
{#await promise then value}<p>{vm.awaitValue}</p>{/await}
{#key vm.version}<p>{vm.keyValue}</p>{/key}
{#snippet row(value)}<p>{vm.snippetValue}</p>{/snippet}
{@render row(vm.renderValue)}
{@html vm.html}
{@const local = vm.constant}
<button
  title={vm.attribute}
  {...vm.spread}
  use:action={vm.action}
  class:active={vm.className}
  style:color={vm.color}
  onclick={() => vm.click()}
>{import('./Lazy.svelte')}</button>
"""

    facts = parse_svelte_ast_batch([(component, source)])[component]
    members = {(item["member"], item["call"]) for item in facts["template_members"]}

    assert {
        ("visible", False),
        ("ifValue", False),
        ("key", True),
        ("eachValue", False),
        ("awaitValue", False),
        ("version", False),
        ("keyValue", False),
        ("snippetValue", False),
        ("renderValue", False),
        ("html", False),
        ("constant", False),
        ("attribute", False),
        ("spread", False),
        ("action", False),
        ("className", False),
        ("color", False),
        ("click", True),
    } <= members
    assert facts["dynamic_imports"] == [
        {
            "source": "./Lazy.svelte",
            "surface": "template",
            "start": source.index("import('./Lazy.svelte')"),
            "end": source.index("import('./Lazy.svelte')") + len("import('./Lazy.svelte')"),
            "start_byte": len(source[: source.index("import('./Lazy.svelte')")].encode()),
            "end_byte": len(
                source[: source.index("import('./Lazy.svelte')") + len("import('./Lazy.svelte')")].encode()
            ),
            "line": 20,
        }
    ]


def test_semantic_binding_ids_distinguish_module_instance_and_parameter_shadowing(
    tmp_path: Path,
):
    component = tmp_path / "Scopes.svelte"
    source = """<script module lang="ts">
import { PanelViewModel as VM } from './module-vm'
const moduleVm = new VM()
</script>
<script lang="ts">
import { PanelViewModel as VM } from './instance-vm'
let { vm }: { vm: VM } = $props()
function shadow(vm: { refresh(): void }) { vm.refresh() }
</script>
<button onclick={() => vm.refresh()}>{vm.title}</button>
"""

    facts = parse_svelte_ast_batch([(component, source)])[component]
    imports = {(item["context"], item["local"]): item for item in facts["imports"]}
    prop = next(item for item in facts["props"] if item["binding"] == "vm")
    template = [item for item in facts["template_members"] if item["binding"] == "vm"]

    assert imports[("module", "VM")]["binding_id"] != imports[("default", "VM")]["binding_id"]
    assert prop["type_binding_id"] == imports[("default", "VM")]["binding_id"]
    assert {item["binding_id"] for item in template} == {prop["binding_id"]}
    shadow_call = next(
        item for item in facts["script_members"]
        if item["binding"] == "vm" and item["member"] == "refresh"
    )
    assert shadow_call["binding_id"] != prop["binding_id"]


def test_semantic_binding_ids_distinguish_each_await_and_snippet_bindings(tmp_path: Path):
    component = tmp_path / "TemplateScopes.svelte"
    source = """<script lang="ts">
let { vm, promise, values }: any = $props()
</script>
{#each values as vm}{vm.eachMember}{/each}
{#await promise then vm}{vm.awaitMember}{/await}
{#snippet row(vm)}{vm.snippetMember}{/snippet}
{vm.outerMember}
"""

    facts = parse_svelte_ast_batch([(component, source)])[component]
    by_member = {item["member"]: item["binding_id"] for item in facts["template_members"]}

    assert len({
        by_member["eachMember"],
        by_member["awaitMember"],
        by_member["snippetMember"],
        by_member["outerMember"],
    }) == 4


def test_module_and_instance_same_name_imports_resolve_by_binding_identity(tmp_path: Path):
    module_vm = _write(
        tmp_path / "ModuleViewModel.svelte.ts",
        "export class ViewModel { moduleOnly(): void {} }\n",
    )
    instance_vm = _write(
        tmp_path / "InstanceViewModel.svelte.ts",
        "export class ViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Scopes.svelte",
        """<script module lang="ts">
import { ViewModel as VM } from './ModuleViewModel.svelte'
export const moduleVm = new VM()
</script>
<script lang="ts">
import { ViewModel as VM } from './InstanceViewModel.svelte'
const vm = new VM()
</script>
{vm.refresh()}
""",
    )

    result = extract(
        [component, module_vm, instance_vm],
        cache_root=tmp_path,
        root=tmp_path,
    )
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    instantiations = {
        (labels.get(edge["source"]), labels.get(edge["target"]))
        for edge in result["edges"]
        if edge.get("relation") == "instantiates"
    }
    calls = [
        edge for edge in result["edges"]
        if edge.get("context") == "template_method_call"
    ]

    assert instantiations == {("new VM()", "ViewModel")}
    assert len(instantiations) == 1  # IDs distinguish the same display label below.
    construction_targets = {
        edge["target"] for edge in result["edges"] if edge.get("relation") == "instantiates"
    }
    assert len(construction_targets) == 2
    assert len(calls) == 1
    assert labels[calls[0]["target"]] == ".refresh()"
    assert result["nodes"][
        next(i for i, node in enumerate(result["nodes"]) if node["id"] == calls[0]["target"])
    ]["source_file"] == "InstanceViewModel.svelte.ts"


def test_one_line_module_and_instance_scripts_keep_exact_import_identity(tmp_path: Path):
    module_vm = _write(
        tmp_path / "ModuleViewModel.svelte.ts",
        "export class ViewModel { moduleOnly(): void {} }\n",
    )
    instance_vm = _write(
        tmp_path / "InstanceViewModel.svelte.ts",
        "export class ViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Scopes.svelte",
        "<script module lang=\"ts\">import { ViewModel as VM } from './ModuleViewModel.svelte'; export const moduleVm = new VM()</script>"
        "<script lang=\"ts\">import { ViewModel as VM } from './InstanceViewModel.svelte'; const vm = new VM()</script>"
        "{vm.refresh()}\n",
    )

    result = extract(
        [component, module_vm, instance_vm],
        cache_root=tmp_path,
        root=tmp_path,
    )
    nodes = {node["id"]: node for node in result["nodes"]}
    import_aliases = {
        alias["script_context"]: nodes[edge["target"]]["source_file"]
        for edge in result["edges"]
        if edge.get("relation") == "imports"
        for alias in edge.get("metadata", {}).get("aliases", [])
        if alias.get("local_name") == "VM"
    }
    construction_targets = {
        nodes[edge["source"]].get("metadata", {}).get("binding"):
            nodes[edge["target"]]["source_file"]
        for edge in result["edges"]
        if edge.get("relation") == "instantiates"
    }
    template_calls = [
        edge for edge in result["edges"]
        if edge.get("context") == "template_method_call"
    ]

    assert import_aliases == {
        "module": "ModuleViewModel.svelte.ts",
        "default": "InstanceViewModel.svelte.ts",
    }
    assert construction_targets == {
        "moduleVm": "ModuleViewModel.svelte.ts",
        "vm": "InstanceViewModel.svelte.ts",
    }
    assert len(template_calls) == 1
    assert nodes[template_calls[0]["target"]]["source_file"] == "InstanceViewModel.svelte.ts"


def test_script_scopes_stay_independent_across_order_and_import_forms(tmp_path: Path):
    module_vm = _write(
        tmp_path / "ModuleViewModel.svelte.ts",
        "export default class ViewModel { moduleOnly(): void {} }\n",
    )
    instance_vm = _write(
        tmp_path / "InstanceViewModel.svelte.ts",
        "export class ViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Scopes.svelte",
        """<script lang="ts">
import { ViewModel as VM } from './InstanceViewModel.svelte'
const vm = new VM()
</script>
<script module lang="ts">
import VM from './ModuleViewModel.svelte'
export const moduleVm = new VM()
</script>
{vm.refresh()}
""",
    )

    result = extract(
        [component, module_vm, instance_vm],
        cache_root=tmp_path,
        root=tmp_path,
    )
    nodes = {node["id"]: node for node in result["nodes"]}
    construction_targets = {
        nodes[edge["source"]].get("metadata", {}).get("binding"):
            nodes[edge["target"]]["source_file"]
        for edge in result["edges"]
        if edge.get("relation") == "instantiates"
    }

    assert construction_targets == {
        "moduleVm": "ModuleViewModel.svelte.ts",
        "vm": "InstanceViewModel.svelte.ts",
    }
    assert not [
        diagnostic
        for diagnostic in result.get("diagnostics", [])
        if "duplicate" in str(diagnostic).lower()
    ]


def test_template_shadow_bindings_do_not_attach_to_outer_viewmodel(tmp_path: Path):
    view_model = _write(
        tmp_path / "ViewModel.svelte.ts",
        "export class ViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Shadow.svelte",
        """<script lang="ts">
import type { ViewModel } from './ViewModel.svelte'
let { vm, values }: { vm: ViewModel; values: Array<{ refresh(): void }> } = $props()
</script>
{#each values as vm}{vm.refresh()}{/each}
{#snippet row(vm)}{vm.refresh()}{/snippet}
{#await Promise.resolve(values[0]) then vm}{vm.refresh()}{/await}
{vm.refresh()}
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)
    calls = [
        edge for edge in result["edges"]
        if edge.get("context") == "template_method_call"
    ]

    assert len(calls) == 1
    assert calls[0]["source_location"] == "L8"


def test_duplicate_import_aliases_are_preserved_on_canonical_import_edge(tmp_path: Path):
    view_model = _write(
        tmp_path / "PanelViewModel.svelte.ts",
        "export class PanelViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import { PanelViewModel as FirstVM, PanelViewModel as SecondVM } from './PanelViewModel.svelte'
const first = new FirstVM()
const second = new SecondVM()
</script>
{first.refresh()} {second.refresh()}
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)
    imports = [edge for edge in result["edges"] if edge.get("relation") == "imports"]
    target = next(node for node in result["nodes"] if node.get("label") == "PanelViewModel")
    edge = next(edge for edge in imports if edge.get("target") == target["id"])

    assert [
        {
            "imported_name": alias["imported_name"],
            "local_name": alias["local_name"],
        }
        for alias in edge["metadata"]["aliases"]
    ] == [
        {"imported_name": "PanelViewModel", "local_name": "FirstVM"},
        {"imported_name": "PanelViewModel", "local_name": "SecondVM"},
    ]
    labels = {node["id"]: node["label"] for node in result["nodes"]}
    calls = {
        labels.get(edge["source"])
        for edge in result["edges"]
        if edge.get("relation") == "calls" and labels.get(edge["target"]) == ".refresh()"
    }
    assert calls == {"new FirstVM()", "new SecondVM()"}


def test_svelte_semantic_targets_use_canonical_identity_through_symlink(tmp_path: Path):
    real = tmp_path / "real"
    linked = tmp_path / "linked"
    real.mkdir()
    linked.symlink_to(real, target_is_directory=True)
    view_model = _write(
        real / "PanelViewModel.svelte.ts",
        "export class PanelViewModel { refresh(): void {} }\n",
    )
    component = _write(
        tmp_path / "Panel.svelte",
        """<script lang="ts">
import { PanelViewModel as VM } from './linked/PanelViewModel.svelte'
const vm = new VM()
</script>
{vm.refresh()}
""",
    )

    result = extract([component, view_model], cache_root=tmp_path, root=tmp_path)
    node_ids = {node["id"] for node in result["nodes"]}
    semantic_edges = [
        edge for edge in result["edges"]
        if edge.get("context") in {"constructor", "template_method_call"}
    ]

    assert semantic_edges
    assert all(edge["target"] in node_ids for edge in semantic_edges)
    assert all("linked" not in edge["target"] for edge in semantic_edges)


def test_bridge_subprocess_uses_explicit_utf8(tmp_path: Path, monkeypatch):
    from graphify.extractors import svelte as svelte_extractor

    captured: dict = {}

    class Completed:
        returncode = 0
        stderr = ""
        stdout = json.dumps({
            "schema_version": svelte_extractor.SVELTE_AST_SCHEMA_VERSION,
            "compiler_version": svelte_extractor.SVELTE_COMPILER_VERSION,
            "svelte2tsx_version": svelte_extractor.SVELTE2TSX_VERSION,
            "typescript_version": svelte_extractor.TYPESCRIPT_VERSION,
            "files": [],
        })

    def fake_run(*args, **kwargs):
        captured.update(kwargs)
        return Completed()

    monkeypatch.setattr(svelte_extractor, "_node_executable", lambda: "node")
    monkeypatch.setattr(svelte_extractor.subprocess, "run", fake_run)
    svelte_extractor._invoke_svelte_bridge({"schema_version": 1, "files": []})

    assert captured["encoding"] == "utf-8"


def test_bridge_failure_is_negative_cached_for_every_file(tmp_path: Path, monkeypatch):
    from graphify.extractors import svelte as svelte_extractor

    calls = 0

    def failing_invoke(_request: dict) -> dict:
        nonlocal calls
        calls += 1
        raise RuntimeError("compiler missing")

    items = [
        (tmp_path / "First.svelte", "<p>First</p>"),
        (tmp_path / "Second.svelte", "<p>Second</p>"),
    ]
    clear_svelte_ast_cache()
    monkeypatch.setattr(svelte_extractor, "_invoke_svelte_bridge", failing_invoke)

    first = parse_svelte_ast_batch(items)
    second = parse_svelte_ast_batch(items)

    assert calls == 1
    assert first == second
    assert all(
        facts["diagnostics"][0]["code"] == "svelte_ast_unavailable"
        for facts in second.values()
    )


def test_svelte_ast_cache_is_bounded_lru(tmp_path: Path, monkeypatch):
    from graphify.extractors import svelte as svelte_extractor

    def fake_invoke(request: dict) -> dict:
        return {
            "schema_version": svelte_extractor.SVELTE_AST_SCHEMA_VERSION,
            "compiler_version": svelte_extractor.SVELTE_COMPILER_VERSION,
            "svelte2tsx_version": svelte_extractor.SVELTE2TSX_VERSION,
            "typescript_version": svelte_extractor.TYPESCRIPT_VERSION,
            "files": [
                {"id": item["id"], "path": item["path"], "diagnostics": []}
                for item in request["files"]
            ],
        }

    clear_svelte_ast_cache()
    monkeypatch.setattr(svelte_extractor, "_invoke_svelte_bridge", fake_invoke)
    for index in range(SVELTE_AST_CACHE_MAX_ENTRIES + 5):
        path = tmp_path / f"Component{index}.svelte"
        parse_svelte_ast_batch([(path, f"<p>{index}</p>")])

    info = svelte_ast_cache_info()
    assert info["max_entries"] == SVELTE_AST_CACHE_MAX_ENTRIES
    assert info["entries"] == SVELTE_AST_CACHE_MAX_ENTRIES
