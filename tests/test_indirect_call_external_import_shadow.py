"""An import from outside the corpus must shadow indirect_call resolution.

`_js_local_bound_names` collects a function's locals from parameters and
`variable_declarator` nodes, and `_js_module_bound_names` only the latter. A name
introduced by `import { X } from "pkg"` is neither, so it was absent from both
shadow sets: listing it in a dispatch table (`{ icon: X }`) or passing it on as a
call argument read as an unresolved by-name reference, resolved against the
corpus-wide label index, and fabricated an `indirect_call` edge (INFERRED, 0.8) to
an unrelated same-named callable elsewhere in the corpus.

Same class as the `catch`-binding, single-parameter-arrow and untracked-closure
shadows already fixed — an import is simply a module-scoped binding. A UI icon kit
makes it land constantly: `Palette`, `Search`, `Filter` and `Menu` are icon exports
*and* ordinary component names, so any repo with both grows cross-package edges
between files that never referenced one another.

The guard asks `_resolve_js_import_target` rather than second-guessing it, so a
relative import — which resolves to a real file, and whose edge is the whole point
of the graph — keeps resolving. `node_modules` is tested separately because a
`tsconfig` `paths` entry pointing a package at its own installed copy
(`"lucide-react": ["./node_modules/lucide-react"]`) *does* resolve, to a tree every
scan prunes.
"""
import os
from pathlib import Path

from graphify.extract import extract


def _extract_js_dir(tmp_path, files: dict[str, str]):
    base = tmp_path / "src"
    base.mkdir()
    for name, body in files.items():
        target = base / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        r = extract(
            [Path("src") / name for name in files],
            cache_root=Path(".cache"), parallel=False,
        )
    finally:
        os.chdir(old)
    nid = {n["label"].rstrip("()"): n["id"] for n in r["nodes"]}
    return r, nid


def _rels(r, relation):
    return {(e["source"], e["target"]) for e in r["edges"] if e["relation"] == relation}


def test_external_named_import_emits_no_indirect_call(tmp_path):
    """Reported shape: an icon imported from a UI kit must not become a fabricated
    indirect_call target because an unrelated component shares its name."""
    r, nid = _extract_js_dir(tmp_path, {
        "Palette.tsx": "export function Palette() { return null; }\n",
        "Sidebar.tsx": (
            "import { Palette } from 'lucide-react';\n"
            "export function Sidebar() {\n"
            "  return [{ label: 'personalise', icon: Palette }];\n"
            "}\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["Palette"] for _s, t in indirect)


def test_external_default_import_emits_no_indirect_call(tmp_path):
    r, nid = _extract_js_dir(tmp_path, {
        "Chart.tsx": "export function Chart() { return null; }\n",
        "Panel.tsx": (
            "import Chart from 'some-chart-lib';\n"
            "export function Panel(sink) { sink.register(Chart); }\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["Chart"] for _s, t in indirect)


def test_external_namespace_import_emits_no_indirect_call(tmp_path):
    r, nid = _extract_js_dir(tmp_path, {
        "Utils.ts": "export function Utils() { return 1; }\n",
        "run.ts": (
            "import * as Utils from 'vendor-utils';\n"
            "export function run(sink) { sink.push(Utils); }\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["Utils"] for _s, t in indirect)


def test_aliased_import_shadows_the_local_name_only(tmp_path):
    """`import { Search as Find }` binds `Find` in this file, not `Search`. The
    shadow must follow the binding: a same-named local `Find` is not referenced
    here, while an unrelated `Search` definition stays reachable by its own name."""
    r, nid = _extract_js_dir(tmp_path, {
        "Find.ts": "export function Find() { return 1; }\n",
        "app.ts": (
            "import { Search as Find } from 'icon-pack';\n"
            "export function app(sink) { sink.push(Find); }\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["Find"] for _s, t in indirect)


def test_tsconfig_alias_into_node_modules_still_counts_as_external(tmp_path):
    """A `paths` entry pointing a package at its own installed copy resolves to a
    real path — inside `node_modules`, which every scan prunes, so no node is ever
    created for it. Resolution succeeding must not read as 'internal'."""
    (tmp_path / "tsconfig.json").write_text(
        '{"compilerOptions": {"paths": {"icon-kit": ["./node_modules/icon-kit"]}}}\n'
    )
    nm = tmp_path / "node_modules" / "icon-kit"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("export function Palette(){}\n")
    r, nid = _extract_js_dir(tmp_path, {
        "Palette.tsx": "export function Palette() { return null; }\n",
        "Bar.tsx": (
            "import { Palette } from 'icon-kit';\n"
            "export function Bar() { return [{ icon: Palette }]; }\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert all(t != nid["Palette"] for _s, t in indirect)


def test_relative_import_still_resolves(tmp_path):
    """The counter-test that bounds the fix: an import of a file INSIDE the corpus
    is exactly the relationship the graph exists to record, so its name must stay
    resolvable. Shadowing every import would delete real edges."""
    r, nid = _extract_js_dir(tmp_path, {
        "widgets.ts": "export function Widget() { return null; }\n",
        "host.ts": (
            "import { Widget } from './widgets';\n"
            "export function host(sink) { sink.push(Widget); }\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert (nid["host"], nid["Widget"]) in indirect


def test_unimported_same_file_callable_still_emits(tmp_path):
    """Widening the shadow set must not blanket-suppress a file that also happens to
    import something external: an unshadowed by-name reference still emits."""
    r, nid = _extract_js_dir(tmp_path, {"a.ts": (
        "import { Icon } from 'icon-pack';\n"
        "function handler(x) { return x; }\n"
        "export function run(pool) { pool.submit(handler); }\n"
    )})
    indirect = _rels(r, "indirect_call")
    assert (nid["run"], nid["handler"]) in indirect


def test_external_import_shadow_does_not_bind_to_a_same_named_local_callable(tmp_path):
    """The precise collision the fix must survive: a name that is BOTH imported
    externally AND defined as a callable in another corpus file. Using the
    external `Filter` value must not fabricate an indirect_call onto the unrelated
    corpus `Filter` — while a genuine by-name use of a local callable still binds."""
    r, nid = _extract_js_dir(tmp_path, {
        "table.ts": "export function Filter() { return null; }\n",   # unrelated corpus callable
        "toolbar.tsx": (
            "import { Filter } from 'lucide-react';\n"                # external, same name
            "function onClick(x) { return x; }\n"
            "export function build(sink, pool) {\n"
            "  sink.push(Filter);\n"                                  # external -> must NOT bind to table.ts Filter
            "  pool.submit(onClick);\n"                               # local -> must still bind
            "}\n"
        ),
    })
    indirect = _rels(r, "indirect_call")
    assert (nid["build"], nid["Filter"]) not in indirect   # no cross-file phantom
    assert (nid["build"], nid["onClick"]) in indirect      # real local reference preserved
