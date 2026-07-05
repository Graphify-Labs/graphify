"""Tests for ``.vue`` SFC extraction.

Feeding a whole SFC to the JS grammar produces a top-level ERROR node, dropping
imports and symbols. :func:`extract_vue` masks the non-script regions and parses
the ``<script>`` with the TypeScript grammar, recovering the full graph.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import (
    _make_id,
    _vue_mask_non_script,
    extract,
    extract_vue,
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


def test_vue_is_in_code_extensions():
    assert ".vue" in CODE_EXTENSIONS


def test_mask_preserves_line_numbers_and_blanks_markup():
    src = (
        "<template>\n"
        "  <div>{{ msg }}</div>\n"
        "</template>\n"
        "\n"
        '<script setup lang="ts">\n'
        "const msg = 'hi'\n"
        "</script>\n"
    )
    masked, lang = _vue_mask_non_script(src)
    assert lang == "ts"
    # Same number of lines (newlines preserved) so line numbers are stable.
    assert masked.count("\n") == src.count("\n")
    # Template content is gone; the script body survives verbatim.
    assert "div" not in masked
    assert "const msg = 'hi'" in masked
    # The script body sits on the same line it does in the source (line 6).
    assert masked.splitlines()[5].strip() == "const msg = 'hi'"


def test_script_setup_ts_static_imports_resolve(tmp_path):
    _write(tmp_path / "Child.vue", "<template><div/></template>\n")
    _write(tmp_path / "utils/helper.ts", "export function helper(){}\n")
    comp = _write(
        tmp_path / "Comp.vue",
        """<template>
  <Child />
</template>

<script setup lang="ts">
import Child from './Child.vue'
import { helper } from './utils/helper'
helper()
</script>
""",
    )
    result = extract_vue(comp)
    targets = _targets(result, relation="imports_from")
    assert _make_id(str(tmp_path / "Child.vue")) in targets
    assert _make_id(str(tmp_path / "utils/helper.ts")) in targets


def test_script_setup_extracts_symbols_with_correct_lines(tmp_path):
    comp = _write(
        tmp_path / "Widget.vue",
        """<template>
  <button @click="onClick">x</button>
</template>

<script setup lang="ts">
import { ref } from 'vue'

const count = ref(0)

function onClick(): void {
  count.value += 1
}
</script>
""",
    )
    result = extract_vue(comp)
    by_label = {n["label"]: n for n in result["nodes"]}
    assert "count" in by_label
    assert "onClick()" in by_label
    # count is declared on line 8, onClick on line 10 of the SFC.
    assert by_label["count"]["source_location"] == "L8"
    assert by_label["onClick()"]["source_location"] == "L10"


def test_typed_props_reference_imported_type(tmp_path):
    _write(tmp_path / "types.ts", "export interface Thing { id: number }\n")
    comp = _write(
        tmp_path / "Typed.vue",
        """<script setup lang="ts">
import type { Thing } from './types'

defineProps<{ item: Thing }>()

function use(x: Thing): Thing {
  return x
}
</script>

<template><div/></template>
""",
    )
    result = extract_vue(comp)
    # The imported type is referenced from the script.
    assert _make_id(str(tmp_path / "types.ts")) in _targets(result, relation="imports_from")


def test_two_script_blocks_both_parsed(tmp_path):
    """Vue allows a classic ``<script>`` plus ``<script setup>``; both are TS."""
    _write(tmp_path / "a.ts", "export const a = 1\n")
    _write(tmp_path / "b.ts", "export const b = 2\n")
    comp = _write(
        tmp_path / "Dual.vue",
        """<script lang="ts">
import { a } from './a'
export default { name: 'Dual' }
</script>

<script setup lang="ts">
import { b } from './b'
</script>

<template><div/></template>
""",
    )
    result = extract_vue(comp)
    targets = _targets(result, relation="imports_from")
    assert _make_id(str(tmp_path / "a.ts")) in targets
    assert _make_id(str(tmp_path / "b.ts")) in targets


def test_dynamic_import_recovered(tmp_path):
    _write(tmp_path / "Lazy.vue", "<template><div/></template>\n")
    comp = _write(
        tmp_path / "Host.vue",
        """<script setup lang="ts">
import { defineAsyncComponent } from 'vue'
const Lazy = defineAsyncComponent(() => import('./Lazy.vue'))
</script>

<template><Lazy /></template>
""",
    )
    result = extract_vue(comp)
    assert _make_id(str(tmp_path / "Lazy.vue")) in _targets(result, relation="dynamic_import")


def test_plain_js_script_block(tmp_path):
    _write(tmp_path / "dep.js", "export const x = 1\n")
    comp = _write(
        tmp_path / "Legacy.vue",
        """<script>
import { x } from './dep'
export default { name: 'Legacy' }
</script>

<template><div/></template>
""",
    )
    result = extract_vue(comp)
    assert _make_id(str(tmp_path / "dep.js")) in _targets(result, relation="imports_from")


def test_template_only_file_does_not_crash(tmp_path):
    comp = _write(tmp_path / "Static.vue", "<template>\n  <h1>hi</h1>\n</template>\n")
    result = extract_vue(comp)
    assert isinstance(result, dict)
    # Only the file node; no script means no imports/symbols.
    assert _targets(result, relation="imports_from") == set()


def test_whole_file_to_js_grammar_would_extract_nothing(tmp_path):
    """The SFC must not be parsed as one JS blob.

    With the bug, a real SFC yields just the file node; after the fix it yields
    its imports.
    """
    _write(tmp_path / "dep.ts", "export const v = 1\n")
    comp = _write(
        tmp_path / "Guard.vue",
        """<template>
  <div class="x" :data-y="z">markup that is not valid JS</div>
</template>

<script setup lang="ts">
import { v } from './dep'
const z = v
</script>
""",
    )
    result = extract_vue(comp)
    assert _make_id(str(tmp_path / "dep.ts")) in _targets(result, relation="imports_from")


def test_vue_joins_cross_file_symbol_resolution(tmp_path):
    """A ``.vue`` calling an imported function wires to the real symbol across files.

    The SFC's calls should resolve like any ``.ts`` file's would.
    """
    helper = _write(tmp_path / "helper.ts", "export function helper() {}\n")
    comp = _write(
        tmp_path / "Caller.vue",
        """<script setup lang="ts">
import { helper } from './helper'

function go(): void {
  helper()
}
</script>

<template><div @click="go" /></template>
""",
    )
    result = extract([comp, helper], cache_root=tmp_path)
    by_label = {n["label"]: n["id"] for n in result["nodes"]}
    edges = {(e["source"], e["target"], e["relation"]) for e in result["edges"]}
    assert (by_label["go()"], by_label["helper()"], "calls") in edges



def test_generic_component_open_tag_with_angle_brackets(tmp_path):
    """A Vue 3.3+ generic= attribute containing '>' (e.g. Record<string, unknown>)
    must not prematurely end the <script> open tag and swallow the body (#1468)."""
    _write(tmp_path / "utils/helper.ts", "export function helper(){}\n")
    comp = _write(
        tmp_path / "Generic.vue",
        """<template><div/></template>
<script setup lang="ts" generic="T extends Record<string, unknown>">
import { helper } from './utils/helper'
const value = helper()
</script>
""",
    )
    result = extract_vue(comp)
    # the import inside the script body is recovered (body wasn't masked away)
    assert _make_id(str(tmp_path / "utils/helper.ts")) in _targets(result, relation="imports_from")
    # and no stray '">' leaked from the open tag into a parse error
    masked, lang = _vue_mask_non_script(comp.read_text(encoding="utf-8"))
    assert lang == "ts"
    assert 'generic="T extends Record' not in masked  # open tag fully blanked
    assert "import { helper }" in masked               # body preserved
