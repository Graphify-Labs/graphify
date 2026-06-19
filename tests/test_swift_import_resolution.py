from __future__ import annotations

from pathlib import Path

from graphify.build import build_from_json
from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _module_nodes(result: dict, label: str) -> list[dict]:
    return [
        n for n in result["nodes"]
        if n.get("type") == "module" and n.get("label") == label
    ]


def _import_edges(result: dict) -> list[dict]:
    return [e for e in result["edges"] if e.get("relation") == "imports"]


def test_swift_import_resolves_to_module_node(tmp_path: Path):
    # #1327: `import CoreKit` must anchor to a node, or build_from_json prunes
    # the edge as a dangling/external reference.
    core = _write(tmp_path / "Sources/CoreKit/CoreKit.swift", "public struct CoreKit {}\n")
    feature = _write(
        tmp_path / "Sources/FeatureKit/FeatureKit.swift",
        "import CoreKit\n\npublic struct FeatureKit {}\n",
    )

    result = extract([core, feature], cache_root=tmp_path)

    node_ids = {n["id"] for n in result["nodes"]}
    imports = _import_edges(result)
    assert imports
    for e in imports:
        assert e["target"] in node_ids
    assert _module_nodes(result, "CoreKit")


def test_swift_same_module_imported_twice_collapses_to_one_node(tmp_path: Path):
    # #1327: the same module imported from multiple files is ONE module, not N
    # file-qualified duplicates — collision-disambiguation must exempt modules.
    core = _write(tmp_path / "Sources/CoreKit/CoreKit.swift", "public struct CoreKit {}\n")
    a = _write(
        tmp_path / "Sources/AKit/AKit.swift",
        "import CoreKit\n\npublic struct AKit {}\n",
    )
    b = _write(
        tmp_path / "Sources/BKit/BKit.swift",
        "import CoreKit\n\npublic struct BKit {}\n",
    )

    result = extract([core, a, b], cache_root=tmp_path)

    # Each importing file contributes a module-node dict, but they must share a
    # single id (NOT be split into path-qualified duplicates) so build_from_json
    # collapses them into one shared node.
    core_modules = _module_nodes(result, "CoreKit")
    module_ids = {n["id"] for n in core_modules}
    assert len(module_ids) == 1
    # Both importers point at that single shared module id.
    import_targets = {e["target"] for e in _import_edges(result)}
    assert import_targets == module_ids


def test_swift_import_edges_survive_build(tmp_path: Path):
    # #1327: edges must remain after graph assembly, deduped to one module node.
    core = _write(tmp_path / "Sources/CoreKit/CoreKit.swift", "public struct CoreKit {}\n")
    a = _write(tmp_path / "Sources/AKit/AKit.swift", "import CoreKit\n")
    b = _write(tmp_path / "Sources/BKit/BKit.swift", "import CoreKit\n")

    result = extract([core, a, b], cache_root=tmp_path)
    G = build_from_json(result, directed=True)

    import_edges = [
        (u, v) for u, v, d in G.edges(data=True) if d.get("relation") == "imports"
    ]
    assert len(import_edges) == 2
    # Both edges land on the same CoreKit module node.
    assert len({v for _, v in import_edges}) == 1
