"""A changed-files rebuild must give a re-extracted SDC template the same ids and edges as a full build.

A Single Directory Component keeps `card.twig` beside `card.scss`, so both collapse to one `card`
file id and disambiguation salts them apart. A changed-files rebuild re-extracts only the edited
file, so the collision with its unchanged sibling was invisible: the template kept the bare id, its
includes pointed at bare ids that no node carries, and the unchanged templates that include it
pointed at the salted id the rebuild had just evicted.
"""
from __future__ import annotations

import json
from pathlib import Path

from graphify.watch import _rebuild_code


def _write(root: Path, rel: str, body: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(body, encoding="utf-8")
    return p


def _theme(tmp_path: Path) -> Path:
    root = tmp_path / "mytheme"
    _write(root, "mytheme.info.yml", "name: My Theme\ntype: theme\n")
    _write(root, "components/atoms/link/link.twig", "<a></a>\n")
    _write(root, "components/atoms/link/link.scss", ".mt-link { color: red; }\n")
    _write(root, "components/molecules/card/card.twig", "{% include 'mytheme:link' %}\n")
    _write(root, "components/molecules/card/card.scss", ".mt-card { color: blue; }\n")
    _write(root, "templates/page.html.twig", "{% include 'mytheme:card' %}\n")
    return root


def _rebuild(root: Path, changed: list[Path] | None = None) -> None:
    assert _rebuild_code(
        root,
        changed_paths=changed,
        no_cluster=True,
        acquire_lock=False,
        force=True,
    ) is True


def _shape(root: Path) -> tuple[set, set, int]:
    """File-node ids, file-to-file template edges, and edges that land on a pathless node."""
    graph = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    nodes = {n["id"]: n for n in graph["nodes"]}
    file_ids = {n["id"] for n in graph["nodes"]
                if n.get("source_file") and Path(n["source_file"]).name == n.get("label")}
    edges, pathless = set(), 0
    for e in graph.get("links", graph.get("edges", [])):
        if e.get("relation") not in ("includes", "embeds"):
            continue
        src, tgt = nodes.get(e["source"], {}), nodes.get(e["target"], {})
        if not tgt.get("source_file"):
            pathless += 1
            continue
        edges.add((src.get("source_file"), e["relation"], tgt.get("source_file")))
    return file_ids, edges, pathless


def test_changed_template_keeps_its_ids_and_include_edges(tmp_path):
    root = _theme(tmp_path)
    _rebuild(root)
    full_ids, full_edges, full_pathless = _shape(root)
    assert ("components/molecules/card/card.twig", "includes", "components/atoms/link/link.twig") in full_edges
    assert ("templates/page.html.twig", "includes", "components/molecules/card/card.twig") in full_edges
    assert full_pathless == 0

    card = root / "components/molecules/card/card.twig"
    card.write_text(card.read_text(encoding="utf-8") + "{# edited #}\n", encoding="utf-8")
    _rebuild(root, [card])

    ids, edges, pathless = _shape(root)
    assert pathless == 0
    assert edges == full_edges
    assert ids == full_ids


def test_changed_stylesheet_does_not_break_its_template(tmp_path):
    root = _theme(tmp_path)
    _rebuild(root)
    full_ids, full_edges, _ = _shape(root)

    scss = root / "components/molecules/card/card.scss"
    scss.write_text(scss.read_text(encoding="utf-8") + "// edited\n", encoding="utf-8")
    _rebuild(root, [scss])

    ids, edges, pathless = _shape(root)
    assert pathless == 0
    assert edges == full_edges
    assert ids == full_ids
