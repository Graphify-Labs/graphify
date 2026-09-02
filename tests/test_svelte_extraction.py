"""Tests for ``.svelte`` component extraction.

Feeding a whole component to the JS grammar produces a top-level ERROR node,
dropping imports and symbols (#713). :func:`extract_svelte` masks the non-script
regions and parses the ``<script>`` with the TypeScript grammar, recovering the
full graph — the same treatment ``.vue`` already gets.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import (
    _make_id,
    _sfc_mask_non_script,
    _vue_mask_non_script,
    extract,
    extract_svelte,
)


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _targets(result: dict, *, relation: str | None = None) -> set[str]:
    return {
        str(e.get("target") or "")
        for e in result.get("edges", [])
        if relation is None or e.get("relation") == relation
    }


def _labels(result: dict) -> set[str]:
    return {str(n.get("label") or "") for n in result.get("nodes", [])}


def test_svelte_is_in_code_extensions():
    assert ".svelte" in CODE_EXTENSIONS


def test_vue_mask_alias_is_the_shared_masker():
    # The masker was named for Vue before Svelte shared it; the old name is kept
    # as an alias so existing callers and tests keep working.
    assert _vue_mask_non_script is _sfc_mask_non_script


def test_mask_preserves_line_numbers_and_blanks_markup():
    src = (
        '<script lang="ts">\n'
        "  const msg = 'hi'\n"
        "</script>\n"
        "\n"
        "<div class=\"wrap\">{msg}</div>\n"
        "\n"
        "<style>\n"
        "  .wrap { color: red }\n"
        "</style>\n"
    )
    masked, lang = _sfc_mask_non_script(src)
    assert lang == "ts"
    # Same number of lines (newlines preserved) so line numbers are stable.
    assert masked.count("\n") == src.count("\n")
    # Markup and style are gone; the script body survives verbatim.
    assert "div" not in masked
    assert "color: red" not in masked
    assert "const msg = 'hi'" in masked
    # The script body sits on the same line it does in the source (line 2).
    assert masked.splitlines()[1].strip() == "const msg = 'hi'"


def test_static_imports_resolve(tmp_path):
    _write(tmp_path / "Icon.svelte", "<span />\n")
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Card.svelte",
        '<script lang="ts">\n'
        "  import Icon from './Icon.svelte'\n"
        "  import { fmt } from './format'\n"
        "</script>\n"
        "\n"
        "<Icon />{fmt('x')}\n",
    )
    result = extract_svelte(component)
    targets = _targets(result, relation="imports_from")
    assert _make_id(str(tmp_path / "Icon.svelte")) in targets
    # Extensionless specifier probes real on-disk extensions (./format -> .ts).
    assert _make_id(str(tmp_path / "format.ts")) in targets


def test_symbols_extracted_with_correct_lines(tmp_path):
    component = _write(
        tmp_path / "Band.svelte",
        '<script lang="ts">\n'
        "  type Level = 'low' | 'high'\n"
        "\n"
        "  function toggle(level: Level) {\n"
        "    return level\n"
        "  }\n"
        "</script>\n"
        "\n"
        "<button onclick={() => toggle('low')}>go</button>\n",
    )
    result = extract_svelte(component)
    labels = _labels(result)
    assert "Level" in labels
    assert "toggle()" in labels
    # Masking keeps newlines, so reported lines match the real source lines.
    lines = {
        str(n.get("label")): n.get("line")
        for n in result.get("nodes", [])
        if n.get("line") is not None
    }
    if "toggle()" in lines:
        assert lines["toggle()"] == 4


def test_module_and_instance_scripts_both_parsed(tmp_path):
    """Svelte 5 ``<script module>`` sits alongside the instance script."""
    _write(tmp_path / "shared.ts", "export const shared = 1\n")
    _write(tmp_path / "local.ts", "export const local = 2\n")
    component = _write(
        tmp_path / "Both.svelte",
        '<script module lang="ts">\n'
        "  import { shared } from './shared'\n"
        "  export function helper() { return shared }\n"
        "</script>\n"
        "\n"
        '<script lang="ts">\n'
        "  import { local } from './local'\n"
        "  function render() { return local }\n"
        "</script>\n"
        "\n"
        "<p>hi</p>\n",
    )
    result = extract_svelte(component)
    targets = _targets(result, relation="imports_from")
    assert _make_id(str(tmp_path / "shared.ts")) in targets
    assert _make_id(str(tmp_path / "local.ts")) in targets
    labels = _labels(result)
    assert "helper()" in labels
    assert "render()" in labels


def test_svelte_4_context_module_script_parsed(tmp_path):
    """Svelte 4 spells the module block ``context="module"``."""
    _write(tmp_path / "shared.ts", "export const shared = 1\n")
    component = _write(
        tmp_path / "Legacy.svelte",
        '<script context="module" lang="ts">\n'
        "  import { shared } from './shared'\n"
        "</script>\n"
        "\n"
        "<p>hi</p>\n",
    )
    result = extract_svelte(component)
    assert _make_id(str(tmp_path / "shared.ts")) in _targets(
        result, relation="imports_from"
    )


def test_dynamic_import_in_template_recovered(tmp_path):
    """``{#await import('./X.svelte')}`` lives in markup the mask blanks out,
    so the regex pass must scan the raw source, not the masked one."""
    _write(tmp_path / "Heavy.svelte", "<span />\n")
    component = _write(
        tmp_path / "Lazy.svelte",
        "<script>\n"
        "  let show = false\n"
        "</script>\n"
        "\n"
        "{#await import('./Heavy.svelte') then Mod}\n"
        "  <Mod.default />\n"
        "{/await}\n",
    )
    result = extract_svelte(component)
    assert _make_id(str(tmp_path / "Heavy.svelte")) in _targets(
        result, relation="dynamic_import"
    )


def test_typed_props_reference_imported_type(tmp_path):
    _write(tmp_path / "types.ts", "export type Risk = { id: string }\n")
    component = _write(
        tmp_path / "RiskCard.svelte",
        '<script lang="ts">\n'
        "  import type { Risk } from './types'\n"
        "  export function label(risk: Risk): string { return risk.id }\n"
        "</script>\n",
    )
    result = extract_svelte(component)
    assert _make_id(str(tmp_path / "types.ts")) in _targets(
        result, relation="imports_from"
    )


def test_plain_js_script_block(tmp_path):
    """No ``lang`` attribute: the TS grammar is a superset, so JS still parses."""
    _write(tmp_path / "util.js", "export const u = 1\n")
    component = _write(
        tmp_path / "Plain.svelte",
        "<script>\n"
        "  import { u } from './util'\n"
        "  function go() { return u }\n"
        "</script>\n"
        "\n"
        "<b>{go()}</b>\n",
    )
    result = extract_svelte(component)
    assert _make_id(str(tmp_path / "util.js")) in _targets(
        result, relation="imports_from"
    )
    assert "go()" in _labels(result)


def test_markup_only_file_does_not_crash(tmp_path):
    component = _write(tmp_path / "Static.svelte", "<h1>hello</h1>\n")
    result = extract_svelte(component)
    assert isinstance(result.get("nodes"), list)
    assert isinstance(result.get("edges"), list)


def test_runes_do_not_break_the_ts_grammar(tmp_path):
    """Svelte 5 runes (``$state``/``$derived``/``$props``) are syntactically
    ordinary calls, so the TS grammar walks past them to the real symbols."""
    component = _write(
        tmp_path / "Runes.svelte",
        '<script lang="ts">\n'
        "  let count = $state(0)\n"
        "  let doubled = $derived(count * 2)\n"
        "  function bump() { count += 1 }\n"
        "</script>\n"
        "\n"
        "<button onclick={bump}>{doubled}</button>\n",
    )
    result = extract_svelte(component)
    assert "bump()" in _labels(result)


def test_whole_file_to_js_grammar_would_extract_nothing(tmp_path):
    """Regression guard for #713: the unmasked path loses everything but the
    file node, which is what made every .svelte file a stub in the graph."""
    from graphify.extract import _JS_CONFIG, _extract_generic

    component = _write(
        tmp_path / "Guard.svelte",
        '<script lang="ts">\n'
        "  import { thing } from './thing'\n"
        "  function visible() { return thing }\n"
        "</script>\n"
        "\n"
        "<div class=\"x\">{visible()}</div>\n"
        "\n"
        "<style>.x { color: red }</style>\n",
    )
    unmasked = _extract_generic(component, _JS_CONFIG)
    assert "visible()" not in _labels(unmasked)

    masked = extract_svelte(component)
    assert "visible()" in _labels(masked)


def test_svelte_joins_cross_file_symbol_resolution(tmp_path):
    """A ``.svelte`` calling an imported function wires to the real symbol across
    files, so the component is a participant in the call graph rather than a
    leaf stub. Exercises the masked ``_parse_js_tree`` path.
    """
    helper = _write(tmp_path / "helper.ts", "export function helper() {}\n")
    comp = _write(
        tmp_path / "Caller.svelte",
        '''<script lang="ts">
import { helper } from './helper'

function go(): void {
  helper()
}
</script>

<button onclick={go}>go</button>
''',
    )
    result = extract([comp, helper], cache_root=tmp_path)
    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    edges = {(e["source"], e["target"], e["relation"]) for e in result["edges"]}
    assert (by_label["go()"], by_label["helper()"], "calls") in edges


def test_static_imports_rescued_when_the_script_fails_to_parse(tmp_path):
    """A script the grammar cannot parse reaches no ``import_statement``.

    Masking fixed the common case, but a genuine syntax error (or a construct
    tree-sitter-typescript mishandles) still leaves the AST pass with nothing,
    and the pre-mask regex rescue is the only thing that recovers the import.
    """
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Broken.svelte",
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "  const busted = ((( @@@\n"
        "</script>\n"
        "\n"
        "<span />\n",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors"), "test needs a script the grammar rejects"
    assert _make_id(str(tmp_path / "format.ts")) in _targets(
        result, relation="imports_from"
    )


def test_clean_parse_does_not_double_emit_static_imports(tmp_path):
    """The rescue is gated on failure, and duplicates are dropped regardless."""
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Card.svelte",
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "</script>\n"
        "\n"
        "<span>{fmt('x')}</span>\n",
    )
    result = extract_svelte(component)
    assert not result.get("parse_errors")
    target = _make_id(str(tmp_path / "format.ts"))
    matching = [
        e for e in result["edges"]
        if e.get("target") == target and e.get("relation") == "imports_from"
    ]
    assert len(matching) == 1


def test_rescue_does_not_duplicate_a_partially_parsed_import(tmp_path):
    """A recovered parse can edge some imports before the error node."""
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    _write(tmp_path / "later.ts", "export const later = 1\n")
    component = _write(
        tmp_path / "Partial.svelte",
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "  const busted = ((( @@@\n"
        "  import { later } from './later'\n"
        "</script>\n"
        "\n"
        "<span />\n",
    )
    result = extract_svelte(component)
    assert result.get("parse_errors")
    for name in ("format.ts", "later.ts"):
        target = _make_id(str(tmp_path / name))
        matching = [
            e for e in result["edges"]
            if e.get("target") == target and e.get("relation") == "imports_from"
        ]
        assert len(matching) == 1, name


def test_dynamic_import_rescue_still_runs_on_a_clean_parse(tmp_path):
    """Gating the STATIC rescue must not gate the dynamic one."""
    _write(tmp_path / "Lazy.svelte", "<span />\n")
    component = _write(
        tmp_path / "Host.svelte",
        '<script lang="ts">\n'
        "  const ready = true\n"
        "</script>\n"
        "\n"
        "{#await import('./Lazy.svelte')}{/await}\n",
    )
    result = extract_svelte(component)
    assert not result.get("parse_errors")
    assert _make_id(str(tmp_path / "Lazy.svelte")) in _targets(
        result, relation="dynamic_import"
    )


def test_repeated_dynamic_import_emits_one_edge(tmp_path):
    """The same specifier in two markup branches is matched twice by the regex."""
    _write(tmp_path / "Lazy.svelte", "<span />\n")
    component = _write(
        tmp_path / "Host.svelte",
        '<script lang="ts">\n'
        "  const ready = true\n"
        "</script>\n"
        "\n"
        "{#if ready}\n"
        "  {#await import('./Lazy.svelte')}{/await}\n"
        "{:else}\n"
        "  {#await import('./Lazy.svelte')}{/await}\n"
        "{/if}\n",
    )
    result = extract_svelte(component)
    target = _make_id(str(tmp_path / "Lazy.svelte"))
    matching = [
        e for e in result["edges"]
        if e.get("target") == target and e.get("relation") == "dynamic_import"
    ]
    assert len(matching) == 1


def test_mask_preserves_byte_offsets_through_non_ascii_markup():
    """tree-sitter reports BYTE offsets, so the mask must be byte-preserving.

    One space per character shifts every offset after any non-ASCII markup —
    an accented word or an emoji in the template — misreporting the column of
    everything in the script below it.
    """
    src = (
        '<div class="héllo ünïcode ✓ 🎉">{x}</div>\n'
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "</script>\n"
    )
    masked, _lang = _sfc_mask_non_script(src)
    assert len(masked.encode("utf-8")) == len(src.encode("utf-8"))
    assert masked.count("\n") == src.count("\n")
    assert masked.encode("utf-8").index(b"import") == src.encode("utf-8").index(b"import")


def test_symbol_lines_are_right_under_non_ascii_markup(tmp_path):
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Emoji.svelte",
        '<div title="ünïcode 🎉 ✓">{x}</div>\n'
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "  export function handler() { return fmt('x') }\n"
        "</script>\n",
    )
    result = extract_svelte(component)
    lines = {n["label"]: n.get("source_location") for n in result["nodes"]}
    assert lines.get("handler()") == "L4"


def test_lang_is_the_widest_grammar_across_all_script_blocks():
    """Both blocks are parsed as ONE unit, so the grammar must accept both.

    Taking the FIRST block's `lang` parsed a Svelte 5 `<script module
    lang="js">` + `<script lang="ts">` pair with the JS grammar, which
    chokes on the TS block's annotations.
    """
    src = (
        '<script module lang="js">\n  const a = 1\n</script>\n'
        '<script lang="ts">\n  const b: number = 2\n</script>\n'
    )
    assert _sfc_mask_non_script(src)[1] == "ts"


def test_all_js_blocks_still_pick_js():
    src = '<script lang="js">\n  const a = 1\n</script>\n'
    assert _sfc_mask_non_script(src)[1] == "js"


def test_js_then_ts_component_parses_the_ts_block(tmp_path):
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Mixed.svelte",
        '<script module lang="js">\n'
        "  export const PRESET = 1\n"
        "</script>\n"
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "  export function handler(n: number): string { return fmt(String(n)) }\n"
        "</script>\n",
    )
    result = extract_svelte(component)
    assert not result.get("parse_errors")
    assert _make_id(str(tmp_path / "format.ts")) in _targets(
        result, relation="imports_from"
    )
    assert {"PRESET", "handler()"} <= _labels(result)


def test_ts_and_jsx_blocks_together_need_the_tsx_grammar():
    """TSX is the only grammar that takes BOTH annotations and JSX.

    Picking either declared lang breaks the other block.
    """
    src = (
        '<script lang="ts">\n  const a: number = 1\n</script>\n'
        '<script lang="jsx">\n  const b = <div />\n</script>\n'
    )
    assert _sfc_mask_non_script(src)[1] == "tsx"


def test_jsx_only_blocks_pick_jsx():
    src = '<script lang="jsx">\n  const b = <div />\n</script>\n'
    assert _sfc_mask_non_script(src)[1] == "jsx"


def test_tsx_lang_reaches_the_call_graph_pass(tmp_path):
    """`_parse_js_tree` keyed the TSX grammar off the file SUFFIX.

    An SFC's suffix is `.svelte`, so a `lang="tsx"` script was parsed with the
    plain TS grammar, which misparses JSX and drops the calls in it.
    """
    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Tsx.svelte",
        '<script lang="tsx">\n'
        "  import { fmt } from './format'\n"
        "  export function render(n: number) { return <div>{fmt(String(n))}</div> }\n"
        "</script>\n",
    )
    result = extract(
        [component, tmp_path / "format.ts"], cache_root=tmp_path,
    )
    nodes = {n["id"]: n for n in result["nodes"]}
    calls = [
        e for e in result["edges"]
        if e["relation"] == "calls"
        and nodes.get(e["source"], {}).get("label") == "render()"
        and nodes.get(e["target"], {}).get("label") == "fmt()"
    ]
    assert calls


def test_rescue_dedupe_uses_the_shared_build_helper():
    """The rescue dedupes through `build.dedupe_edges`, not a private twin.

    A second `_dedupe_edges` in extract.py collided by name with the alias
    cli.py and watch.py already bind to `build.dedupe_edges`, while taking a
    result dict instead of an edge list — a trap for anyone importing the
    wrong one.
    """
    import graphify.extract as extract_module

    assert not hasattr(extract_module, "_dedupe_edges")


def _generic_hard_error(path, config, source_override=None, **kwargs):
    """What `_extract_generic` returns when it cannot parse at all."""
    return {"nodes": [], "edges": [], "error": "tree-sitter-typescript not installed"}


def test_static_rescue_runs_on_a_hard_extractor_error(tmp_path, monkeypatch):
    """`_extract_generic` signals a HARD failure with `error`, not `parse_errors`.

    A missing grammar or unreadable source returns no tree and no nodes. The
    rescue was gated on `parse_errors` alone, so it never ran and every static
    import was lost — where the pre-mask extractor ran the regex
    unconditionally and recovered them.
    """
    import graphify.extract as extract_module

    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Broken.svelte",
        '<script lang="ts">\n'
        "  import { fmt } from './format'\n"
        "</script>\n"
        "<span />\n",
    )
    monkeypatch.setattr(extract_module, "_extract_generic", _generic_hard_error)
    result = extract_module.extract_svelte(component)

    assert result.get("error"), "the error must stay for extract()'s reporting"
    assert _make_id(str(tmp_path / "format.ts")) in _targets(
        result, relation="imports_from"
    )


def test_hard_error_rescue_mints_the_source_file_node(tmp_path, monkeypatch):
    """A rescued edge needs a real source node or build drops it (#701)."""
    import graphify.extract as extract_module

    _write(tmp_path / "format.ts", "export const fmt = (s: string) => s\n")
    component = _write(
        tmp_path / "Broken.svelte",
        '<script lang="ts">\n  import { fmt } from \'./format\'\n</script>\n',
    )
    monkeypatch.setattr(extract_module, "_extract_generic", _generic_hard_error)
    result = extract_module.extract_svelte(component)

    file_node_id = _make_id(str(component))
    assert file_node_id in {n["id"] for n in result["nodes"]}
    assert all(e["source"] == file_node_id for e in result["edges"])


def test_dynamic_rescue_also_survives_a_hard_error(tmp_path, monkeypatch):
    import graphify.extract as extract_module

    _write(tmp_path / "Lazy.svelte", "<span />\n")
    component = _write(
        tmp_path / "Host.svelte",
        "{#await import('./Lazy.svelte')}{/await}\n",
    )
    monkeypatch.setattr(extract_module, "_extract_generic", _generic_hard_error)
    result = extract_module.extract_svelte(component)

    assert _make_id(str(tmp_path / "Lazy.svelte")) in _targets(
        result, relation="dynamic_import"
    )
