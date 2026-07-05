"""#1638 — an unresolved bare npm import must not alias onto an unrelated
same-named local file, producing a confident cross-language phantom edge.

`import colors from "tailwindcss/colors"` in a .tsx file used to emit an
`imports_from` edge to the bare id ``colors``. build.py's pre-migration alias
index registers every local file's bare stem (``backend/utils/colors.py`` ->
alias ``colors``), so the dangling ``colors`` target was remapped onto the
Python file — an EXTRACTED-confidence edge between two files in different
languages with no real relationship.

The fix namespaces the external-import fallback id with the ``ref`` prefix (the
J-4 convention), so it can never collide with a local file/symbol node id.
"""
from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import _make_id, _resolve_js_import_target, extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# ── unit: the resolver never returns a bare local-shaped id for an external ──


def test_unresolved_bare_import_is_ref_namespaced():
    tgt, resolved_path = _resolve_js_import_target(
        "tailwindcss/colors", "frontend/src/SomeChart.tsx"
    )
    assert resolved_path is None
    # Must not be the bare last-segment id that collides with a local `colors` file.
    assert tgt != _make_id("colors")
    assert tgt != _make_id("colors.py")
    assert tgt.startswith("ref")


def test_scoped_package_import_is_ref_namespaced():
    tgt, resolved_path = _resolve_js_import_target(
        "@scope/utils", "src/thing.ts"
    )
    assert resolved_path is None
    assert tgt != _make_id("utils")
    assert tgt.startswith("ref")


# ── end-to-end: the reporter's exact synthetic monorepo ─────────────────────


def test_no_phantom_edge_from_tsx_to_unrelated_python_file(tmp_path: Path):
    py = _write(
        tmp_path / "backend/utils/colors.py",
        "def hex_to_rgb(value):\n    return (0, 0, 0)\n",
    )
    tsx = _write(
        tmp_path / "frontend/src/SomeChart.tsx",
        'import colors from "tailwindcss/colors";\n\n'
        "export const CHART_COLOR = colors.blue[500];\n",
    )

    result = extract([py, tsx], cache_root=tmp_path / "graphify-out")
    G = build_from_json(result, root=str(tmp_path))

    # Find the python file node.
    py_ids = [
        n for n, d in G.nodes(data=True)
        if str(d.get("source_file", "")).endswith("colors.py")
    ]
    assert py_ids, "colors.py should have produced at least one node"

    # No edge from the TSX file (or any TS symbol) should land on the python file
    # as an imports_from relationship.
    for u, v, d in G.edges(data=True):
        if d.get("relation") != "imports_from":
            continue
        endpoints = {u, v}
        if endpoints & set(py_ids):
            other = (endpoints - set(py_ids)) or endpoints
            srcfiles = {str(G.nodes[e].get("source_file", "")) for e in other}
            assert not any(sf.endswith((".tsx", ".ts")) for sf in srcfiles), (
                f"phantom cross-language imports_from edge onto colors.py: "
                f"{u} -> {v} ({d})"
            )


def test_multiple_tsx_files_do_not_all_alias_onto_one_python_file(tmp_path: Path):
    # The real-world symptom: N unrelated .tsx files all doing the same bare
    # import showed up as N imports_from sources on one python module.
    _write(
        tmp_path / "backend/utils/colors.py",
        "def hex_to_rgb(value):\n    return (0, 0, 0)\n",
    )
    for i in range(3):
        _write(
            tmp_path / f"frontend/src/Chart{i}.tsx",
            'import colors from "tailwindcss/colors";\n'
            f"export const C{i} = colors.blue;\n",
        )

    paths = list((tmp_path).rglob("*.py")) + list((tmp_path / "frontend").rglob("*.tsx"))
    result = extract(paths, cache_root=tmp_path / "graphify-out")
    G = build_from_json(result, root=str(tmp_path))

    py_ids = {
        n for n, d in G.nodes(data=True)
        if str(d.get("source_file", "")).endswith("colors.py")
    }
    phantom = [
        (u, v) for u, v, d in G.edges(data=True)
        if d.get("relation") == "imports_from" and ({u, v} & py_ids)
    ]
    assert not phantom, f"phantom edges onto colors.py: {phantom}"
