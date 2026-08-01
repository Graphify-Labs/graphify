"""Regression tests: Python cross-file type references (#2363).

Two defects, both reported as "ghost duplicate nodes":

1. Class-body field annotations (`point: PricePoint`, the dataclass shape) were
   never collected. `_python_collect_type_refs` had exactly two call sites,
   function parameters and return types, so a dataclass field emitted no edge at
   all. Java (`_java_collect_type_refs` on record components / field
   declarations) and TS (`_ts_walk_class_members`) already emit
   `references`/context="field" for the same shape.

2. When a simple name is ambiguous (two same-named classes in different
   packages), `_rewire_unique_stub_nodes` bails, so the sourceless stub survives
   as a bare `pricepoint` node and the reference edge stays stuck on it — even
   though `from pkg.a.base import PricePoint` names the defining module exactly.
   Java resolves this with `_resolve_java_type_references`, PHP and C# with their
   own resolvers; Python had none.

The unambiguous single-definition case already worked at 0.9.31 (the sourceless
stub is collapsed by the corpus rewire); it is pinned here so it cannot silently
regress.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from graphify.extract import extract


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def _nodes_labeled(result: dict, label: str) -> list[dict]:
    return [node for node in result["nodes"] if node.get("label") == label]


def _sole_node_id(result: dict, label: str, source_file: str) -> str:
    matches = [
        node["id"]
        for node in result["nodes"]
        if node.get("label") == label and node.get("source_file") == source_file
    ]
    assert len(matches) == 1, matches
    return matches[0]


def _refs(result: dict, source: str) -> set[tuple[str, str | None]]:
    """(target, context) for every references edge out of `source`."""
    return {
        (edge["target"], edge.get("context"))
        for edge in result["edges"]
        if edge["source"] == source and edge["relation"] == "references"
    }


_DEF = (
    "from dataclasses import dataclass\n"
    "\n"
    "@dataclass\n"
    "class PricePoint:\n"
    "    value: float\n"
)


def test_dataclass_field_annotation_emits_reference_edge(tmp_path: Path):
    """Defect 1: a dataclass field type produced no edge and no node."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    quote = _write(
        tmp_path / "pkg/b/quote.py",
        "from dataclasses import dataclass\n"
        "from pkg.a.base import PricePoint\n"
        "\n"
        "@dataclass\n"
        "class Quote:\n"
        "    point: PricePoint\n",
    )

    result = extract([base, quote], cache_root=tmp_path)

    price_nid = _sole_node_id(result, "PricePoint", "pkg/a/base.py")
    quote_nid = _sole_node_id(result, "Quote", "pkg/b/quote.py")
    assert (price_nid, "field") in _refs(result, quote_nid)
    # The reference must not fabricate a second PricePoint.
    assert len(_nodes_labeled(result, "PricePoint")) == 1


def test_class_body_field_generic_arg(tmp_path: Path):
    """A container-wrapped field type is a generic_arg, matching the param path."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    book = _write(
        tmp_path / "pkg/b/book.py",
        "from pkg.a.base import PricePoint\n"
        "\n"
        "class Book:\n"
        "    rows: list[PricePoint]\n",
    )

    result = extract([base, book], cache_root=tmp_path)

    price_nid = _sole_node_id(result, "PricePoint", "pkg/a/base.py")
    book_nid = _sole_node_id(result, "Book", "pkg/b/book.py")
    assert (price_nid, "generic_arg") in _refs(result, book_nid)


def test_plain_class_attribute_without_annotation_emits_nothing(tmp_path: Path):
    """`x = 1` binds a value, not a type — it must not become a reference."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    cfg = _write(
        tmp_path / "pkg/b/cfg.py",
        "class Config:\n"
        "    retries = 3\n"
        "    name = 'x'\n",
    )

    result = extract([base, cfg], cache_root=tmp_path)

    cfg_nid = _sole_node_id(result, "Config", "pkg/b/cfg.py")
    assert _refs(result, cfg_nid) == set()


def test_ambiguous_same_named_class_resolves_through_the_import(tmp_path: Path):
    """Defect 2: the bare sourceless ghost, and an edge pointing at it."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    other = _write(tmp_path / "pkg/z/other.py", "class PricePoint:\n    pass\n")
    consumer = _write(
        tmp_path / "pkg/b/consumer.py",
        "from pkg.a.base import PricePoint\n"
        "\n"
        "def handle(p: PricePoint) -> None:\n"
        "    return None\n",
    )

    result = extract([base, other, consumer], cache_root=tmp_path)

    # Both real definitions survive; the sourceless ghost must not.
    labeled = _nodes_labeled(result, "PricePoint")
    assert len(labeled) == 2, labeled
    assert all(node.get("source_file") for node in labeled), labeled

    wanted = _sole_node_id(result, "PricePoint", "pkg/a/base.py")
    handle_nid = _sole_node_id(result, "handle()", "pkg/b/consumer.py")
    assert (wanted, "parameter_type") in _refs(result, handle_nid)


def test_ambiguous_field_annotation_resolves_through_the_import(tmp_path: Path):
    """Both defects at once: an ambiguous name reached via a dataclass field."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    other = _write(tmp_path / "pkg/z/other.py", "class PricePoint:\n    pass\n")
    quote = _write(
        tmp_path / "pkg/b/quote.py",
        "from pkg.z.other import PricePoint\n"
        "\n"
        "class Quote:\n"
        "    point: PricePoint\n",
    )

    result = extract([base, other, quote], cache_root=tmp_path)

    # Imported from pkg.z.other, so it must bind there — not to pkg.a.base.
    wanted = _sole_node_id(result, "PricePoint", "pkg/z/other.py")
    quote_nid = _sole_node_id(result, "Quote", "pkg/b/quote.py")
    assert (wanted, "field") in _refs(result, quote_nid)


def test_ambiguous_superclass_resolves_through_the_import(tmp_path: Path):
    """`inherits` is in the resolver's repoint set, so it needs its own case.

    Superclasses reach `ensure_named_node` from a different call site than type
    annotations do, so the annotation tests do not cover this path.
    """
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    other = _write(tmp_path / "pkg/z/other.py", "class PricePoint:\n    pass\n")
    sub = _write(
        tmp_path / "pkg/b/sub.py",
        "from pkg.a.base import PricePoint\n"
        "\n"
        "class Sub(PricePoint):\n"
        "    pass\n",
    )

    result = extract([base, other, sub], cache_root=tmp_path)

    assert not [n for n in result["nodes"] if not n.get("source_file")]
    wanted = _sole_node_id(result, "PricePoint", "pkg/a/base.py")
    sub_nid = _sole_node_id(result, "Sub", "pkg/b/sub.py")
    assert any(
        edge["source"] == sub_nid
        and edge["target"] == wanted
        and edge["relation"] == "inherits"
        for edge in result["edges"]
    )


def test_ambiguous_aliased_import_resolves_through_the_local_name(tmp_path: Path):
    """`import X as Y` binds Y — the resolver keys on the local name, not the
    exported one, so the annotation `p: PP` still finds `pkg.a.base.PricePoint`."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    other = _write(tmp_path / "pkg/z/other.py", "class PricePoint:\n    pass\n")
    consumer = _write(
        tmp_path / "pkg/b/consumer.py",
        "from pkg.a.base import PricePoint as PP\n"
        "\n"
        "def handle(p: PP) -> None:\n"
        "    return None\n",
    )

    result = extract([base, other, consumer], cache_root=tmp_path)

    wanted = _sole_node_id(result, "PricePoint", "pkg/a/base.py")
    handle_nid = _sole_node_id(result, "handle()", "pkg/b/consumer.py")
    assert (wanted, "parameter_type") in _refs(result, handle_nid)


def test_ambiguous_name_with_no_import_is_left_alone(tmp_path: Path):
    """No import names the intended definition, so no edge may be invented."""
    base = _write(tmp_path / "pkg/a/base.py", _DEF)
    other = _write(tmp_path / "pkg/z/other.py", "class PricePoint:\n    pass\n")
    consumer = _write(
        tmp_path / "pkg/b/consumer.py",
        "def handle(p: PricePoint) -> None:\n"
        "    return None\n",
    )

    result = extract([base, other, consumer], cache_root=tmp_path)

    handle_nid = _sole_node_id(result, "handle()", "pkg/b/consumer.py")
    real_ids = {
        _sole_node_id(result, "PricePoint", "pkg/a/base.py"),
        _sole_node_id(result, "PricePoint", "pkg/z/other.py"),
    }
    # Guessing one of two equally-plausible definitions would be a false edge.
    assert not (real_ids & {target for target, _ in _refs(result, handle_nid)})


def test_unambiguous_cross_file_annotation_stays_a_single_node(tmp_path: Path):
    """Pins the behavior that already worked at 0.9.31 (the issue's main claim).

    Four referencing files, one definition: the per-file sourceless stubs must
    keep collapsing onto the real node instead of being salted apart by
    ``_disambiguate_colliding_node_ids``.
    """
    base = _write(tmp_path / "agri/baseline.py", _DEF)
    consumers = [
        _write(
            tmp_path / f"signal_intelligence/{name}.py",
            "from agri.baseline import PricePoint\n"
            "\n"
            "def latest(rows: list[PricePoint]) -> PricePoint:\n"
            "    return rows[0]\n",
        )
        for name in ("prices", "deviation", "watch_signals", "resolution")
    ]

    result = extract([base, *consumers], cache_root=tmp_path)

    assert len(_nodes_labeled(result, "PricePoint")) == 1
    price_nid = _sole_node_id(result, "PricePoint", "agri/baseline.py")
    for name in ("prices", "deviation", "watch_signals", "resolution"):
        latest_nid = _sole_node_id(
            result, "latest()", f"signal_intelligence/{name}.py"
        )
        assert (price_nid, "return_type") in _refs(result, latest_nid)


_KEY_VARS = ("GEMINI_API_KEY", "GOOGLE_API_KEY", "OPENAI_API_KEY", "OPENAI_BASE_URL",
             "ANTHROPIC_API_KEY", "MOONSHOT_API_KEY", "DEEPSEEK_API_KEY")


def test_written_graph_has_one_node_per_class_via_the_cli(tmp_path: Path):
    """End-to-end through the real CLI, asserting on the written graph.json.

    A unit test on ``extract()`` can pass while the shipped pipeline drops the
    result, so the user-visible artifact gets its own check (`--code-only` needs
    no API key, so this runs in CI).
    """
    repo = tmp_path / "repo"
    _write(repo / "pkg/a/base.py", _DEF)
    _write(repo / "pkg/z/other.py", "class PricePoint:\n    pass\n")
    _write(
        repo / "pkg/b/quote.py",
        "from dataclasses import dataclass\n"
        "from pkg.a.base import PricePoint\n"
        "\n"
        "@dataclass\n"
        "class Quote:\n"
        "    point: PricePoint\n",
    )

    env = {k: v for k, v in os.environ.items() if k not in _KEY_VARS}
    env["GRAPHIFY_OUT"] = str(repo / "graphify-out")
    result = subprocess.run(
        [sys.executable, "-m", "graphify", "extract", ".", "--code-only"],
        cwd=repo, capture_output=True, text=True, env=env,
    )
    assert result.returncode == 0, result.stderr

    graph = json.loads((repo / "graphify-out" / "graph.json").read_text())
    # NetworkX <= 3.1 serialises edges as "links" (build.py:1154 reads both).
    graph_edges = graph.get("edges", graph.get("links", []))
    price_nodes = [n for n in graph["nodes"] if n.get("label") == "PricePoint"]
    # Exactly the two real definitions — no sourceless ghost.
    assert len(price_nodes) == 2, price_nodes
    assert all(n.get("source_file") for n in price_nodes), price_nodes

    quote = next(n for n in graph["nodes"] if n.get("label") == "Quote")
    wanted = next(
        n["id"] for n in price_nodes if n.get("source_file") == "pkg/a/base.py"
    )
    # The build layer renames the `references` relation to `uses`; context is
    # what pins this to the field-annotation path either way.
    assert any(
        e.get("relation") in ("references", "uses")
        and e.get("context") == "field"
        and {e.get("source"), e.get("target")} == {quote["id"], wanted}
        for e in graph_edges
    ), "dataclass field reference missing from the written graph"
