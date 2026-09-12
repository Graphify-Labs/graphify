"""Tests for ``.svelte`` extraction.

Feeding a whole component to the JS grammar produces a top-level ERROR node, so
no declaration is ever reached and a component collapses to a single file node.
:func:`extract_svelte` scans the file into regions, parses the ``<script>``
blocks with the TypeScript grammar at their true offsets, and walks the template
for component usage and snippets.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import _make_id, extract_svelte
from graphify.extractors.svelte import _scan_regions


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _by_kind(result: dict, kind: str) -> set[str]:
    return {
        str(n.get("label") or "")
        for n in result.get("nodes", [])
        if n.get("kind") == kind
    }


def _edges(result: dict, relation: str, context: str | None = None) -> list[dict]:
    return [
        e for e in result.get("edges", [])
        if e.get("relation") == relation
        and (context is None or e.get("context") == context)
    ]


def test_svelte_is_in_code_extensions():
    assert ".svelte" in CODE_EXTENSIONS


def test_scan_regions_preserves_offsets_and_finds_module_block():
    src = (
        '<script module>\n'
        "  export const NAME = 'x'\n"
        "</script>\n"
        '<script lang="ts">\n'
        "  let count = $state(0)\n"
        "</script>\n"
        "<p>{count}</p>\n"
    )
    scripts, template = _scan_regions(src)
    assert len(scripts) == 2
    assert scripts[0]["module"] is True
    assert scripts[1]["module"] is False
    # Masking keeps length and newlines, so offsets into the template are still
    # valid offsets into the source.
    assert len(template) == len(src)
    assert template.count("\n") == src.count("\n")
    assert "$state" not in template
    assert "<p>{count}</p>" in template


def test_scan_regions_is_not_fooled_by_commented_out_script(tmp_path):
    src = "<!-- <script>let hidden = 1</script> -->\n<div>hi</div>\n"
    scripts, _template = _scan_regions(src)
    assert scripts == []


def test_props_runes_functions_and_snippets_become_nodes(tmp_path):
    path = _write(
        tmp_path / "Widget.svelte",
        '<script lang="ts">\n'
        "  let { title, onSave }: { title: string; onSave: () => void } = $props()\n"
        "  let open = $state(false)\n"
        "  const label = $derived(title.toUpperCase())\n"
        "  function toggle() { open = !open }\n"
        "  const reset = () => { open = false }\n"
        "</script>\n"
        "\n"
        "{#snippet row(x)}<li>{x}</li>{/snippet}\n"
        "<button onclick={toggle}>{label}</button>\n",
    )
    result = extract_svelte(path)

    assert _by_kind(result, "prop") == {"title", "onSave"}
    assert _by_kind(result, "state") == {"open"}
    assert _by_kind(result, "derived") == {"label"}
    assert _by_kind(result, "function") == {"toggle()", "reset()"}
    assert _by_kind(result, "snippet") == {"row()"}


def test_renamed_prop_uses_the_public_name(tmp_path):
    """`class: className` exposes `class`; the script refers to `className`."""
    path = _write(
        tmp_path / "Styled.svelte",
        "<script>\n"
        "  let { class: className = '' } = $props()\n"
        "</script>\n"
        "<div class={className}></div>\n",
    )
    result = extract_svelte(path)
    assert _by_kind(result, "prop") == {"class"}
    prop = next(n for n in result["nodes"] if n.get("kind") == "prop")
    assert prop["local_name"] == "className"


def test_rune_variants_share_one_kind(tmp_path):
    path = _write(
        tmp_path / "Raw.svelte",
        "<script>\n"
        "  let a = $state.raw({})\n"
        "  let b = $derived.by(() => 1)\n"
        "</script>\n",
    )
    result = extract_svelte(path)
    kinds = {n["label"]: (n["kind"], n.get("rune")) for n in result["nodes"]
             if n.get("kind") in ("state", "derived")}
    assert kinds == {"a": ("state", "$state.raw"), "b": ("derived", "$derived.by")}


def test_component_usage_emits_uses_edge_with_renders_context(tmp_path):
    _write(tmp_path / "Child.svelte", "<p>child</p>\n")
    path = _write(
        tmp_path / "Parent.svelte",
        "<script>\n"
        "  import Child from './Child.svelte'\n"
        "</script>\n"
        "<Child />\n",
    )
    result = extract_svelte(path)
    # `uses`, not `renders`: DEFAULT_AFFECTED_RELATIONS does not include
    # `renders`, so such an edge would be invisible to `graphify affected`.
    uses = _edges(result, "uses", "renders")
    assert len(uses) == 1
    assert uses[0]["symbol"] == "Child"
    assert uses[0]["target_file"].endswith("Child.svelte")


def test_less_than_operator_is_not_a_component_tag(tmp_path):
    """`{#if i < items.length}` must not read as a component named items.length."""
    path = _write(
        tmp_path / "Cmp.svelte",
        "<script>\n"
        "  let items = $state([])\n"
        "  let i = $state(0)\n"
        "</script>\n"
        "{#if i < items.length}<span>more</span>{/if}\n",
    )
    result = extract_svelte(path)
    assert _edges(result, "uses") == []


def test_barrel_siblings_each_get_their_own_usage_edge(tmp_path):
    """Alert/AlertTitle resolve to one module but are two distinct usages."""
    _write(tmp_path / "ui/index.js", "export const Alert = 1\nexport const AlertTitle = 2\n")
    path = _write(
        tmp_path / "Uses.svelte",
        "<script>\n"
        "  import { Alert, AlertTitle } from './ui/index.js'\n"
        "</script>\n"
        "<Alert><AlertTitle>hi</AlertTitle></Alert>\n",
    )
    result = extract_svelte(path)
    assert {e["symbol"] for e in _edges(result, "uses", "renders")} == {"Alert", "AlertTitle"}


def test_case_colliding_type_and_variable_both_survive(tmp_path):
    """make_id casefolds, so `type State` and `let state` hash alike (#id-collision)."""
    path = _write(
        tmp_path / "Health.svelte",
        '<script lang="ts">\n'
        "  type State = 'on' | 'off'\n"
        "  let state = $state<State>('on')\n"
        "</script>\n",
    )
    result = extract_svelte(path)
    assert _by_kind(result, "type") == {"State"}
    assert _by_kind(result, "state") == {"state"}
    ids = [n["id"] for n in result["nodes"]]
    assert len(ids) == len(set(ids))


def test_imported_call_binds_to_the_symbol_not_just_the_file(tmp_path):
    _write(tmp_path / "fmt.ts", "export function formatOre(x: number) { return x }\n")
    path = _write(
        tmp_path / "Money.svelte",
        "<script>\n"
        "  import { formatOre } from './fmt'\n"
        "</script>\n"
        "<span>{formatOre(1)}</span>\n",
    )
    result = extract_svelte(path)
    calls = _edges(result, "calls")
    assert len(calls) == 1
    # The corpus can hold many `formatOre`; the import says which one this is.
    assert calls[0]["target"] == _make_id(str((tmp_path / "fmt").as_posix()), "formatOre")


def test_dynamic_import_in_markup_is_recovered(tmp_path):
    """`{#await import('./X.svelte')}` lives in markup; no JS parser sees it."""
    _write(tmp_path / "Lazy.svelte", "<p>lazy</p>\n")
    path = _write(
        tmp_path / "Host.svelte",
        "{#await import('./Lazy.svelte') then M}<M.default />{/await}\n",
    )
    result = extract_svelte(path)
    dyn = _edges(result, "dynamic_import")
    assert len(dyn) == 1
    assert dyn[0]["target_file"].endswith("Lazy.svelte")


def test_scalar_locals_and_anonymous_effects_are_not_nodes(tmp_path):
    """Node count is not the goal — a node per `const x = 1` makes the graph worse."""
    path = _write(
        tmp_path / "Quiet.svelte",
        "<script>\n"
        "  const LIMIT = 10\n"
        "  let n = $state(0)\n"
        "  $effect(() => { console.log(n) })\n"
        "</script>\n",
    )
    result = extract_svelte(path)
    labels = {n["label"] for n in result["nodes"]}
    assert "LIMIT" not in labels
    assert _by_kind(result, "state") == {"n"}
    # One component node plus the single rune binding.
    assert len(result["nodes"]) == 2


def test_recursive_component_records_a_self_edge(tmp_path):
    """`import Self from './ChainTree.svelte'` used as <Self /> is recursion."""
    path = _write(
        tmp_path / "ChainTree.svelte",
        "<script>\n"
        "  import Self from './ChainTree.svelte'\n"
        "  let { nodes } = $props()\n"
        "</script>\n"
        "{#each nodes as n}<Self nodes={n.children} />{/each}\n",
    )
    result = extract_svelte(path)
    uses = _edges(result, "uses", "renders")
    assert [e["symbol"] for e in uses] == ["Self"]
    # Self-import: source and target are the same component node.
    assert uses[0]["source"] == uses[0]["target"]


def test_quoted_prop_key_keeps_only_the_prop_name(tmp_path):
    """A hyphenated prop must be quoted; the quotes are syntax, not the name."""
    path = _write(
        tmp_path / "Slot.svelte",
        "<script>\n"
        '  let { "data-slot": dataSlot = "textarea" } = $props()\n'
        "</script>\n",
    )
    result = extract_svelte(path)
    assert _by_kind(result, "prop") == {"data-slot"}
    prop = next(n for n in result["nodes"] if n.get("kind") == "prop")
    assert prop["local_name"] == "dataSlot"


def test_regex_literal_in_an_expression_does_not_swallow_later_components(tmp_path):
    """A miscounted brace is not a local error — it drops the rest of the file.

    `replace(/^https?:\\/\\//, '')` puts two adjacent slashes inside an
    expression; reading them as a comment used to pin the depth above zero so
    every following component silently vanished.
    """
    _write(tmp_path / "Icon.svelte", "<i></i>\n")
    path = _write(
        tmp_path / "Host.svelte",
        "<script>\n"
        "  import Icon from './Icon.svelte'\n"
        "  let { site } = $props()\n"
        "</script>\n"
        "<span>{site.replace(/^https?:\\/\\//, '')}</span>\n"
        "<Icon />\n",
    )
    result = extract_svelte(path)
    assert [e["symbol"] for e in _edges(result, "uses", "renders")] == ["Icon"]


def test_apostrophe_in_markup_text_does_not_swallow_later_components(tmp_path):
    _write(tmp_path / "Icon.svelte", "<i></i>\n")
    path = _write(
        tmp_path / "Text.svelte",
        "<script>\n"
        "  import Icon from './Icon.svelte'\n"
        "</script>\n"
        "<p>Don't panic</p>\n"
        "<Icon />\n",
    )
    result = extract_svelte(path)
    assert [e["symbol"] for e in _edges(result, "uses", "renders")] == ["Icon"]


def test_call_sites_are_reported_at_file_lines_not_block_lines(tmp_path):
    """A `<script module>` block pushes the instance script down the file.

    tree-sitter line numbers are relative to the parsed block, so without the
    offset every call site in such a file is reported several lines too high.
    """
    path = _write(
        tmp_path / "Run.svelte",
        '<script module lang="ts">\n'      # 1
        "  const started = new Set()\n"    # 2
        "</script>\n"                      # 3
        "\n"                               # 4
        '<script lang="ts">\n'             # 5
        "  function helper() { return 1 }\n"   # 6
        "  function go() {\n"              # 7
        "    return helper()\n"            # 8  <- the call site
        "  }\n"                            # 9
        "</script>\n",
    )
    result = extract_svelte(path)
    call = next(e for e in _edges(result, "calls") if e.get("context") == "call")
    assert call["source_location"] == "L8"
