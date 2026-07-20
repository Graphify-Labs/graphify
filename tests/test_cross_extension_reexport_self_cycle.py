"""Same-basename cross-extension re-exports must not collapse to a self-cycle (#1814).

A hand-written ``.mjs`` plain-ESM runtime plus a thin typed ``.ts`` wrapper that
re-exports it (``export { N } from "./foo.mjs"``) is a common convention. Because
``_file_stem`` drops the extension, ``foo.ts`` and ``foo.mjs`` both collapse to the
base file id ``foo`` at extract time. ``_disambiguate_colliding_node_ids`` salts the
two NODES apart correctly (``foo_ts_foo`` / ``foo_mjs_foo``), but the file-level
re-export edge (and the ``re_exports`` export edge) keyed its target salt by the
IMPORTER's own source_file, mis-pointing the ``./foo.mjs`` target back onto the
importer's own variant — a phantom ``foo.ts -> foo.ts`` self-loop reported as a
1-file import cycle.

These lock: the salted node ids stay unchanged (the fix does NOT make ids
extension-aware — Option A rejected, #1033), the re-export edge lands on the
sibling node, and no phantom 1-file cycle survives.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.build import build
from graphify.export import to_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _node_id_by_label(result: dict, label: str) -> str:
    ids = [n["id"] for n in result["nodes"] if n.get("label") == label]
    assert len(ids) == 1, f"expected exactly one node labelled {label!r}; got {ids}"
    return ids[0]


def _reexport_like_edges(result: dict) -> list[dict]:
    return [
        e for e in result["edges"]
        if e.get("relation") in ("imports_from", "re_exports")
    ]


def test_cross_ext_reexport_emits_no_self_loop(tmp_path: Path):
    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    result = extract([mjs, ts], cache_root=tmp_path)

    self_loops = [
        e for e in _reexport_like_edges(result)
        if e.get("source") == e.get("target")
    ]
    assert not self_loops, (
        f"cross-extension re-export produced a phantom self-loop; got {self_loops}"
    )


def test_cross_ext_reexport_target_is_the_sibling_node(tmp_path: Path):
    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    result = extract([mjs, ts], cache_root=tmp_path)

    foo_ts = _node_id_by_label(result, "foo.ts")
    foo_mjs = _node_id_by_label(result, "foo.mjs")
    # The scheme stays as-is: extension dropped from the base stem, siblings salted
    # apart by source path. The fix must NOT make node ids extension-aware (#1814
    # Option A rejected).
    assert foo_ts == "foo_ts_foo"
    assert foo_mjs == "foo_mjs_foo"

    file_level = [
        e for e in result["edges"]
        if e.get("relation") == "imports_from" and e.get("source") == foo_ts
    ]
    assert file_level, "no file-level re-export edge from foo.ts was emitted"
    assert all(e.get("target") == foo_mjs for e in file_level), (
        f"file-level re-export must target the .mjs sibling node {foo_mjs!r}; "
        f"got {[e.get('target') for e in file_level]}"
    )

    # The symbol-provenance re_exports (context='export') edge must also point at
    # the sibling, never back at the importer.
    export_edges = [
        e for e in result["edges"]
        if e.get("relation") == "re_exports" and e.get("context") == "export"
        and e.get("source") == foo_ts
    ]
    assert export_edges, "no re_exports export edge from foo.ts was emitted"
    assert all(e.get("target") == foo_mjs for e in export_edges), (
        f"re_exports export edge must target the .mjs sibling node {foo_mjs!r}; "
        f"got {[e.get('target') for e in export_edges]}"
    )


def test_cross_ext_reexport_no_phantom_import_cycle(tmp_path: Path):
    import networkx as nx

    from graphify.analyze import find_import_cycles

    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    result = extract([mjs, ts], cache_root=tmp_path)

    graph = nx.DiGraph()
    for node in result["nodes"]:
        graph.add_node(node["id"], **{k: v for k, v in node.items() if k != "id"})
    for edge in result["edges"]:
        graph.add_edge(
            edge["source"],
            edge["target"],
            **{k: v for k, v in edge.items() if k not in ("source", "target")},
        )
    assert find_import_cycles(graph) == [], (
        "cross-extension re-export must not manufacture a file-level import cycle"
    )


def test_same_basename_three_colliding_siblings_reexport_selects_named_variant(
    tmp_path: Path,
):
    """With three same-basename siblings that all collapse to the base id ``foo``
    (``foo.mjs`` / ``foo.cjs`` / ``foo.ts``), keying the re-export target by the
    RESOLVED target file — not the importer's file — must land on the specifically
    named ``./foo.mjs`` variant, proving the fix is a real per-file selection and
    not a binary coin-flip between two colliders.

    (The issue's illustrative trio uses ``foo.d.mts``, but a ``.d.mts`` stem keeps
    its ``.d`` segment and so does NOT collide with ``foo`` — it cannot exercise
    multi-variant salt selection. ``foo.cjs`` is the realistic dual-format sibling
    that genuinely collides.)
    """
    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    cjs = _write(tmp_path / "foo.cjs", "module.exports.M = 2;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    result = extract([mjs, cjs, ts], cache_root=tmp_path)

    foo_ts = _node_id_by_label(result, "foo.ts")
    foo_mjs = _node_id_by_label(result, "foo.mjs")
    foo_cjs = _node_id_by_label(result, "foo.cjs")
    assert foo_mjs != foo_cjs != foo_ts

    file_level = [
        e for e in result["edges"]
        if e.get("relation") == "imports_from" and e.get("source") == foo_ts
    ]
    assert file_level, "no file-level re-export edge from foo.ts was emitted"
    assert all(e.get("target") == foo_mjs for e in file_level), (
        f"re-export of './foo.mjs' must resolve to the .mjs node {foo_mjs!r}, not "
        f"the .cjs sibling {foo_cjs!r}; got {[e.get('target') for e in file_level]}"
    )
    self_loops = [
        e for e in _reexport_like_edges(result)
        if e.get("source") == e.get("target")
    ]
    assert not self_loops, f"unexpected self-loop among siblings; got {self_loops}"


# --------------------------------------------------------------------------- #
# The ``target_file`` the fix stamps on import/re-export edges is a transient
# extraction-time disambiguation salt hint (its only reader is the salt lookup
# in ``_disambiguate_colliding_node_ids``). It carries an ABSOLUTE filesystem
# path, so it must never survive its consumer onto a persisted edge: leaking it
# into graph.json breaks determinism across checkout locations and the
# cross-machine merge/global-graph portability the codebase engineered for. The
# following lock that the hint is stripped after disambiguation and never
# reaches graph.json — on the raw-dump extract path AND the build path — and
# that a persisted absolute hint from a pre-fix graph is dropped on the next
# build rather than carried forward.
# --------------------------------------------------------------------------- #


def test_disambiguation_strips_transient_target_file_hint(tmp_path: Path):
    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    result = extract([mjs, ts], cache_root=tmp_path)

    leaked = [e for e in result["edges"] if "target_file" in e]
    assert not leaked, (
        f"the target_file salt hint must not survive disambiguation onto an "
        f"edge (it carries an absolute path with no downstream reader); got {leaked}"
    )


def test_target_file_hint_stripped_even_without_a_collision(tmp_path: Path):
    # No same-basename collision here, so `_disambiguate_colliding_node_ids`
    # takes its early `if not remap: return` exit before the edge loop. An
    # ordinary import still stamps target_file at extraction, so that early
    # exit must strip it too — otherwise every non-colliding import leaks an
    # absolute path.
    util = _write(tmp_path / "util.ts", "export const helper = 1;\n")
    main = _write(tmp_path / "main.ts", 'import { helper } from "./util";\n')

    result = extract([util, main], cache_root=tmp_path)

    leaked = [e for e in result["edges"] if "target_file" in e]
    assert not leaked, (
        f"a non-colliding import leaked the transient target_file hint; got {leaked}"
    )


def test_graph_json_has_no_target_file_and_no_absolute_path(tmp_path: Path):
    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    result = extract([mjs, ts], cache_root=tmp_path)
    graph = build([result], root=tmp_path)
    out = tmp_path / "graph.json"
    to_json(graph, {}, str(out), force=True)

    raw = out.read_text(encoding="utf-8")
    data = json.loads(raw)
    leaked = [link for link in data["links"] if "target_file" in link]
    assert not leaked, f"absolute target_file persisted into graph.json links: {leaked}"
    assert str(tmp_path.resolve()) not in raw, (
        "graph.json leaked an absolute checkout path (source_file is relativized, "
        "but the target_file hint was serialized verbatim)"
    )


def test_graph_json_is_checkout_location_independent(tmp_path: Path):
    """Building the byte-identical repo at two different absolute locations must
    yield identical graph.json edges. A leaked absolute target_file differs by
    its checkout prefix and would defeat the cross-machine merge/global-graph
    portability the codebase is built around."""

    def _links_built_at(dirname: str) -> list[dict]:
        d = tmp_path / dirname
        d.mkdir()
        mjs = _write(d / "foo.mjs", "export const N = 1;\n")
        ts = _write(d / "foo.ts", 'export { N } from "./foo.mjs";\n')
        result = extract([mjs, ts], cache_root=d)
        graph = build([result], root=d)
        out = d / "graph.json"
        to_json(graph, {}, str(out), force=True)
        links = json.loads(out.read_text(encoding="utf-8"))["links"]
        return sorted(
            links,
            key=lambda link: (
                str(link.get("source")),
                str(link.get("target")),
                str(link.get("relation")),
            ),
        )

    assert _links_built_at("loc_a") == _links_built_at("loc_bbbb_longer"), (
        "graph.json edges differ across checkout locations — an absolute path leaked"
    )


def test_build_drops_persisted_target_file_from_a_pre_fix_graph(tmp_path: Path):
    # A graph.json written by a pre-fix build carries an absolute target_file on
    # its import edges. On the next (incremental) build those base edges are
    # re-serialized through build(), which does NOT re-run disambiguation — so
    # the serializer itself must drop the persisted absolute path rather than
    # carry a foreign checkout prefix forward into the updated graph.
    legacy_chunk = {
        "nodes": [
            {"id": "foo_ts_foo", "label": "foo.ts",
             "source_file": "foo.ts", "file_type": "code"},
            {"id": "foo_mjs_foo", "label": "foo.mjs",
             "source_file": "foo.mjs", "file_type": "code"},
        ],
        "edges": [
            {
                "source": "foo_ts_foo",
                "target": "foo_mjs_foo",
                "relation": "imports_from",
                "context": "re-export",
                "confidence": "EXTRACTED",
                "source_file": "foo.ts",
                "target_file": "/some/other/checkout/foo.mjs",
                "weight": 1.0,
            }
        ],
    }

    graph = build([legacy_chunk], root=tmp_path)

    assert graph.number_of_edges() == 1, "the base import edge should survive the merge"
    for _src, _tgt, data in graph.edges(data=True):
        assert "target_file" not in data, (
            f"build() carried a persisted absolute target_file into the graph: {data}"
        )


def test_target_file_hint_never_written_to_the_ast_cache(tmp_path: Path):
    """The hint is emitted only on JS/TS-family edges, and those suffixes bypass
    the AST cache entirely (``_JS_CACHE_BYPASS_SUFFIXES``). A warm/relocated
    cache therefore can never carry a foreign absolute target_file that would
    miss the disambiguation salt. Lock that no AST cache entry stores it."""
    mjs = _write(tmp_path / "foo.mjs", "export const N = 1;\n")
    ts = _write(tmp_path / "foo.ts", 'export { N } from "./foo.mjs";\n')

    extract([mjs, ts], cache_root=tmp_path)

    ast_dir = tmp_path / "graphify-out" / "cache" / "ast"
    entries = list(ast_dir.rglob("*.json")) if ast_dir.exists() else []
    for entry in entries:
        payload = json.loads(entry.read_text(encoding="utf-8"))
        for edge in payload.get("edges", []):
            assert "target_file" not in edge, (
                f"AST cache entry {entry.name} stored a non-portable target_file "
                f"hint: {edge}"
            )
