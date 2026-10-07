"""An import edge must survive a same-stem file in another language (#33).

Several extractors name an import's target by the bare file-stem id of the
imported file (``import lead`` -> ``lead``). That works only while the id is
unique: add ANY same-stem file -- a ``lead.md`` will do --  and the two file
nodes collide, so ``_disambiguate_colliding_node_ids`` salts them apart into
``lead_ex_lead`` and ``lead_md_lead``. The import edge's target salt is keyed by
the IMPORTER's own source_file, which matches neither, so the edge is left
pointing at an id that no longer names anything and is silently dropped.

The disambiguator already accepts a ``target_file`` hint for exactly this shape
(#1814), keying the target salt by that file instead. Every language below
stamps it now.

Each case asserts BOTH directions, so a fixture that never produced an import
edge in the first place cannot pass by accident: the control corpus must
resolve, and the collision corpus must resolve to the SAME file.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.extract import extract

_IMPORT_RELATIONS = ("imports", "imports_from", "re_exports")

# A language-neutral collider: it shares the stem, mints a file node, and has
# nothing whatsoever to do with the import under test.
_COLLIDER = ("lead.md", "# Lead\n\nUnrelated notes.\n")

# (case id, importer file, importer body, target file, target body)
_CASES = [
    (
        "powershell-dot-source",
        "caller.ps1", ". ./lead.ps1\nfunction Run { Search }\n",
        "lead.ps1", "function Search { return @() }\n",
    ),
    (
        "powershell-import-module",
        "caller.ps1", "Import-Module ./lead.ps1\nfunction Run { Search }\n",
        "lead.ps1", "function Search { return @() }\n",
    ),
    (
        "rust-use",
        "caller.rs", "use crate::lead;\n\npub fn run() { lead::search(); }\n",
        "lead.rs", "pub fn search() {}\n",
    ),
    (
        "pascal-uses",
        "caller.pas",
        "unit Caller;\ninterface\nuses Lead;\nimplementation\nend.\n",
        "lead.pas",
        "unit Lead;\ninterface\nprocedure Search;\n"
        "implementation\nprocedure Search; begin end;\nend.\n",
    ),
    (
        "zig-at-import",
        "caller.zig",
        'const lead = @import("lead.zig");\npub fn run() void { lead.search(); }\n',
        "lead.zig", "pub fn search() void {}\n",
    ),
    (
        "elixir-import",
        "caller.ex",
        "defmodule Caller do\n  import Lead\n  def run, do: search()\nend\n",
        "lead.ex", "defmodule Lead do\n  def search, do: []\nend\n",
    ),
    (
        "bash-source",
        "caller.sh", "source ./lead.sh\nrun() { search; }\n",
        "lead.sh", "search() { echo hi; }\n",
    ),
]


def _extract(tmp_path: Path, files: list[tuple[str, str]]) -> dict:
    tmp_path.mkdir(parents=True, exist_ok=True)
    paths = []
    for name, body in files:
        path = tmp_path / name
        path.write_text(body, encoding="utf-8")
        paths.append(path)
    return extract(paths, cache_root=tmp_path)


def _import_targets(result: dict) -> list[dict]:
    """The node each import edge points at, or ``None`` where it dangles."""
    by_id = {node["id"]: node for node in result["nodes"]}
    return [
        by_id.get(edge.get("target"))
        for edge in result["edges"]
        if edge.get("relation") in _IMPORT_RELATIONS
    ]


@pytest.mark.parametrize(
    ("importer", "importer_body", "target", "target_body"),
    [case[1:] for case in _CASES],
    ids=[case[0] for case in _CASES],
)
def test_import_edge_survives_a_same_stem_foreign_sibling(
    tmp_path: Path, importer: str, importer_body: str, target: str, target_body: str,
):
    corpus = [(importer, importer_body), (target, target_body)]

    control = _import_targets(_extract(tmp_path / "control", corpus))
    assert any(
        node is not None and str(node.get("source_file", "")).endswith(target)
        for node in control
    ), f"fixture is inert: no import edge reached {target} even without a collider"

    collided = _import_targets(_extract(tmp_path / "collided", [*corpus, _COLLIDER]))
    assert None not in collided, \
        "an import edge dangled on the pre-disambiguation stem id"
    assert any(
        str(node.get("source_file", "")).endswith(target) for node in collided
    ), f"the import edge no longer reaches {target}"
    assert not any(
        str(node.get("source_file", "")).endswith(_COLLIDER[0]) for node in collided
    ), "an import edge was repointed onto the unrelated collider"


def test_the_transient_target_file_hint_never_reaches_the_graph(tmp_path: Path):
    """``target_file`` carries an absolute path and is popped by its only reader.

    Asserted across every case at once: a language that stamps the hint but is
    somehow not reached by the disambiguator would ship the analysing machine's
    filesystem layout inside `graph.json`.
    """
    # Two cases share `caller.ps1`; dedupe by name (last wins). The point is
    # breadth of emitters in one graph, not per-case isolation.
    corpus = {_COLLIDER[0]: _COLLIDER[1]}
    for _, importer, importer_body, target, target_body in _CASES:
        corpus[importer] = importer_body
        corpus[target] = target_body
    result = _extract(tmp_path, list(corpus.items()))

    leaked = [edge for edge in result["edges"] if "target_file" in edge]
    assert leaked == [], f"transient hint reached the graph: {leaked[:3]}"
