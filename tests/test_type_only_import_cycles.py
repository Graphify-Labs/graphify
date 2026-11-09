"""Type-only imports must not manufacture Import Cycles (#3123).

`import type` / `export type ... from` are erased by the TypeScript compiler
— no runtime emit, no module-graph edge — yet the extractor emitted an
ordinary `imports_from` edge for them, and every one of the reporter's
reported cycles (3 of 3 on a ~7,900-node repo) closed only through such
edges. The report even flagged code whose comment said the `export type`
form was chosen for "zero runtime emit"; the mitigation was reported as the
defect.

The edge is kept — the type dependency is real for "what references this
type" — stamped `type_only`, and `find_import_cycles` excludes it the way
it already excludes deferred `import(...)` (#1241).

Python's `if TYPE_CHECKING:` imports never execute either and get the same
stamp (#3159). Merging two edges of one file pair keeps an attribute from
either, so the merged edge is `type_only` only if every import folded into it
is: a runtime import next to a type-only one keeps its cycle.
"""
from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from graphify.analyze import find_import_cycles
from graphify.build import build_from_json, dedupe_edges
from graphify.extract import extract


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return extract([tmp_path / n for n in files], cache_root=Path(tempfile.mkdtemp()),
                   root=tmp_path, parallel=False)


def _module_edges(result, rel="imports_from"):
    return [e for e in result["edges"] if e["relation"] == rel]


# ---------------------------------------------------------------------------
# The stamp
# ---------------------------------------------------------------------------

def test_import_type_statement_is_stamped(tmp_path):
    r = _extract(tmp_path, {
        "types.ts": "export type Variables = { requestId: string };\n",
        "v1.ts": 'import type { Variables } from "./types.js";\n'
                 "export function makeRouter() { return {} as unknown; }\n",
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("v1.ts")]
    assert edges and all(e.get("type_only") for e in edges)


def test_export_type_reexport_is_stamped(tmp_path):
    r = _extract(tmp_path, {
        "v1.ts": "export type RouterType = { v: number };\n",
        "types.ts": 'export type { RouterType } from "./v1.js";\n',
    })
    stamped = [e for e in r["edges"]
               if e["source_file"].endswith("types.ts")
               and e["relation"] in ("imports_from", "re_exports")]
    assert stamped and all(e.get("type_only") for e in stamped)


def test_a_default_binding_named_type_is_a_runtime_import(tmp_path):
    """`import type from './x.js'` imports a value whose name is `type` —
    erased by nothing."""
    r = _extract(tmp_path, {
        "x.ts": "const type = 1;\nexport default type;\n",
        "user.ts": 'import type from "./x.js";\nexport const y = type;\n',
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("user.ts")]
    assert edges and not any(e.get("type_only") for e in edges)


def test_a_mixed_specifier_list_stays_a_runtime_edge(tmp_path):
    """`import { type B, C }` still imports C at runtime."""
    r = _extract(tmp_path, {
        "b.ts": "export type B = number;\nexport const C = 1;\n",
        "user.ts": 'import { type B, C } from "./b.js";\nexport const y = C;\n',
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("user.ts")]
    assert edges and not any(e.get("type_only") for e in edges)


def test_plain_imports_are_untouched(tmp_path):
    r = _extract(tmp_path, {
        "b.ts": "export const C = 1;\n",
        "user.ts": 'import { C } from "./b.js";\nexport const y = C;\n',
    })
    edges = [e for e in _module_edges(r) if e["source_file"].endswith("user.ts")]
    assert edges and not any("type_only" in e for e in edges)


# ---------------------------------------------------------------------------
# The cycles — the reporter's minimal repro
# ---------------------------------------------------------------------------

def _cycles(tmp_path, files, directed=True, raw=False):
    r = _extract(tmp_path, files)
    # directed=True mirrors a --directed build; in the default undirected
    # graph two module edges between one file pair collapse to a single
    # stored edge, so a synthetic 2-cycle needs distinct endpoints anyway.
    # raw=True takes the `update --no-cluster` route: edges are deduplicated
    # before the graph is built from that graph.json (`cluster-only`).
    edges = dedupe_edges(r["edges"]) if raw else r["edges"]
    G = build_from_json({"nodes": r["nodes"], "edges": edges, "hyperedges": []},
                        root=str(tmp_path), directed=directed)
    return find_import_cycles(G)


def test_the_reporters_two_file_cycle_is_gone(tmp_path):
    cycles = _cycles(tmp_path, {
        "types.ts": ("export type Variables = { requestId: string };\n"
                     'export type { RouterType } from "./v1.js";\n'),
        "v1.ts": ('import type { Variables } from "./types.js";\n'
                  "export type RouterType = { v: Variables };\n"
                  "export function makeRouter() { return {} as RouterType; }\n"),
    })
    assert cycles == [], cycles


def test_a_real_runtime_cycle_is_still_reported(tmp_path):
    cycles = _cycles(tmp_path, {
        "a.ts": 'import { b } from "./b.js";\nexport const a = 1;\n',
        "b.ts": 'import { a } from "./a.js";\nexport const b = 2;\n',
    })
    assert len(cycles) == 1
    assert sorted(Path(f).name for f in cycles[0]["cycle"]) == ["a.ts", "b.ts"]


def test_a_cycle_with_one_type_only_leg_is_not_a_cycle(tmp_path):
    """One runtime leg + one type-only leg: no runtime cycle exists."""
    cycles = _cycles(tmp_path, {
        "a.ts": 'import { b } from "./b.js";\nexport type AT = number;\nexport const a = 1;\n',
        "b.ts": 'import type { AT } from "./a.js";\nexport const b = 2;\n',
    })
    assert cycles == [], cycles


def test_undirected_graph_keeps_the_marker_when_the_reverse_import_is_dropped(tmp_path):
    """Default undirected graph: b imports a at runtime, a only `import type`s b.
    The pair keeps one edge (#1061); a's type-only import must not become a
    runtime leg closing a -> b -> c -> a."""
    cycles = _cycles(tmp_path, {
        "a.ts": "import type { B } from './b';\nexport class A { b?: B; }\n",
        "b.ts": ("import { A } from './a';\nimport { C } from './c';\n"
                 "export class B { a = new A(); c = new C(); }\n"),
        "c.ts": "import { A } from './a';\nexport class C { a = new A(); }\n",
    }, directed=False)
    assert cycles == [], cycles


# ---------------------------------------------------------------------------
# Python: imports under `if TYPE_CHECKING:` (#3159)
# ---------------------------------------------------------------------------

def _stamped_by_line(result, importer):
    """{line: some edge of that import statement is stamped} for one file."""
    out: dict[int, bool] = {}
    for e in result["edges"]:
        if e["source_file"].endswith(importer) and e["relation"] in ("imports", "imports_from"):
            line = int(e["source_location"][1:])
            out[line] = out.get(line, False) or bool(e.get("type_only"))
    return out


def _names(cycles):
    return sorted(sorted(Path(f).name for f in c["cycle"]) for c in cycles)


def test_python_imports_under_type_checking_are_stamped(tmp_path):
    r = _extract(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/models.py": "class Item: ...\n",
        "pkg/service.py": (
            "import sys\n"                                     # 1
            "import typing\n"                                  # 2
            "from typing import TYPE_CHECKING\n"               # 3
            "\n"                                               # 4
            "if TYPE_CHECKING:\n"                              # 5
            "    from pkg.models import Item\n"                # 6
            "    import pkg.models\n"                          # 7
            "    from .models import Item as Rel\n"            # 8
            "    if sys.version_info >= (3, 11):\n"            # 9
            "        from pkg.models import Item as Nested\n"  # 10
            "if typing.TYPE_CHECKING:\n"                       # 11
            "    from pkg.models import Item as Attr\n"        # 12
        ),
    })
    stamped = _stamped_by_line(r, "service.py")
    assert [line for line, flag in stamped.items() if flag] == [6, 7, 8, 10, 12]


def test_python_imports_that_run_are_not_stamped(tmp_path):
    """The `else:` of the guard and `if not TYPE_CHECKING:` run at import time."""
    r = _extract(tmp_path, {
        "models.py": "class Item: ...\n",
        "fallback.py": "class Item: ...\n",
        "service.py": (
            "from typing import TYPE_CHECKING\n"               # 1
            "import models\n"                                  # 2
            "if TYPE_CHECKING:\n"                              # 3
            "    from models import Item\n"                    # 4
            "else:\n"                                          # 5
            "    from fallback import Item\n"                  # 6
            "if not TYPE_CHECKING:\n"                          # 7
            "    from models import Item as Late\n"            # 8
        ),
    })
    stamped = _stamped_by_line(r, "service.py")
    assert [line for line, flag in stamped.items() if flag] == [4]
    assert {1, 2, 6, 8} <= set(stamped)


@pytest.mark.parametrize("service_import, expected", [
    ("if TYPE_CHECKING:\n    from app import AppState\n", []),
    ("from app import AppState\n", [["app.py", "service.py"]]),
], ids=["guarded", "runtime"])
def test_python_two_file_cycle_closes_only_through_a_runtime_import(tmp_path, service_import, expected):
    """The shape in the issue, in a directed build."""
    cycles = _cycles(tmp_path, {
        "app.py": "from service import Service\n\nclass AppState:\n    service: Service\n",
        "service.py": ("from __future__ import annotations\nfrom typing import TYPE_CHECKING\n\n"
                       + service_import
                       + "\nclass Service:\n    def run(self, state: AppState):\n        return state\n"),
    })
    assert _names(cycles) == expected


@pytest.mark.parametrize("adapter_import, expected", [
    ("if TYPE_CHECKING:\n    from pkg.main import AppState\n", []),
    ("from pkg.main import AppState\n", [["adapter.py", "main.py", "service.py"]]),
], ids=["guarded", "runtime"])
def test_python_three_file_ring_closes_only_through_a_runtime_import(tmp_path, adapter_import, expected):
    """The reporter's shape, in the default undirected build."""
    cycles = _cycles(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/main.py": "from pkg.service import Service\n\nclass AppState:\n    service: Service\n",
        "pkg/service.py": "from pkg.adapter import Adapter\n\nclass Service:\n    adapter: Adapter\n",
        "pkg/adapter.py": ("from typing import TYPE_CHECKING\n\n" + adapter_import
                           + "\nclass Adapter:\n    def bind(self, state: 'AppState'): ...\n"),
    }, directed=False)
    assert _names(cycles) == expected


# A runtime import and a guarded one for the same pair: the cycle stays ---------

@pytest.mark.parametrize("a_body", [
    "from typing import TYPE_CHECKING\nfrom b import helper\n\nif TYPE_CHECKING:\n    from b import B\n",
    "from typing import TYPE_CHECKING\n\nif TYPE_CHECKING:\n    from b import B\n\nfrom b import helper\n",
], ids=["runtime-first", "guard-first"])
def test_python_runtime_and_guarded_import_of_one_module_keep_the_cycle(tmp_path, a_body):
    cycles = _cycles(tmp_path, {
        "a.py": a_body + "\ndef f(x: 'B'):\n    return helper(x)\n",
        "b.py": "from a import f\n\nclass B: ...\n\ndef helper(x):\n    return f\n",
    })
    assert _names(cycles) == [["a.py", "b.py"]]


_RING_X6 = {
    # a -> b is `from . import b` (resolution pass, not stamped) plus a guarded `from .b import B`
    "pkg/__init__.py": "",
    "pkg/a.py": ("from . import b\nfrom typing import TYPE_CHECKING\n\n"
                 "if TYPE_CHECKING:\n    from .b import B\n\n"
                 "def f(x: 'B'):\n    return b.helper(x)\n"),
    "pkg/b.py": "from pkg.c import C\n\nclass B: ...\n\ndef helper(x):\n    return C\n",
    "pkg/c.py": "from pkg.a import f\n\nclass C:\n    run = f\n",
}


@pytest.mark.parametrize("directed, raw", [(False, False), (True, False), (False, True)],
                         ids=["undirected", "directed", "no-cluster-raw"])
def test_python_ring_through_a_submodule_import_and_a_guard_keeps_its_cycle(tmp_path, directed, raw):
    cycles = _cycles(tmp_path, _RING_X6, directed=directed, raw=raw)
    assert _names(cycles) == [["a.py", "b.py", "c.py"]]


def test_python_guard_in_one_direction_keeps_the_runtime_import_in_the_other(tmp_path):
    """Undirected, a pair is one edge: a.py's guarded `import pkg.b` folds with
    b.py's runtime `from pkg.a import A`, which closes the ring a -> c -> b -> a."""
    cycles = _cycles(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/a.py": ("from typing import TYPE_CHECKING\n\nfrom pkg.c import C\n\n"
                     "if TYPE_CHECKING:\n    import pkg.b\n\nclass A:\n    c: C\n"),
        "pkg/b.py": "from pkg.a import A\n\nclass B:\n    a: A\n",
        "pkg/c.py": "from pkg.b import B\n\nclass C:\n    b: B\n",
    }, directed=False)
    assert _names(cycles) == [["a.py", "b.py", "c.py"]]


def test_a_type_import_beside_a_value_import_of_the_same_file_keeps_the_cycle(tmp_path):
    """The same merge hid a real cycle for TypeScript (#3123)."""
    cycles = _cycles(tmp_path, {
        "a.ts": ('import type { B } from "./b.js";\nimport { helper } from "./b.js";\n'
                 "export const a = (x: B) => helper(x);\n"),
        "b.ts": ('import { a } from "./a.js";\nexport type B = number;\n'
                 "export function helper(x: number) { return a; }\n"),
    })
    assert _names(cycles) == [["a.ts", "b.ts"]]


def test_a_runtime_import_dropped_by_the_merge_still_clears_the_marker():
    """build_from_json drops a lower-confidence duplicate of an edge it already
    holds; the type-only marker must not outlive the runtime import it dropped."""
    def edge(src, tgt, conf, line, **extra):
        return {"source": src, "target": tgt, "relation": "imports_from", "confidence": conf,
                "source_file": f"{src}.py", "source_location": f"L{line}", **extra}

    nodes = [{"id": n, "label": f"{n}.py", "source_file": f"{n}.py", "file_type": "code"}
             for n in ("a", "b")]
    edges = [edge("a", "b", "EXTRACTED", 1, type_only=True),
             edge("a", "b", "INFERRED", 2),
             edge("b", "a", "EXTRACTED", 1)]
    G = build_from_json({"nodes": nodes, "edges": edges, "hyperedges": []}, directed=True)
    assert _names(find_import_cycles(G)) == [["a.py", "b.py"]]
