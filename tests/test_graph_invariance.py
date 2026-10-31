"""The same source tree must give the same graph.json, however it is built.

Each test builds the whole ``tests/fixtures`` corpus (every language graphify
ships an extractor for) two ways that must not matter, through the real CLI,
and compares every node and edge with all attributes:

- two checkouts in different folders (no checkout path in any id or edge),
- a cold build and a rebuild of the unchanged tree,
- an LF checkout and a CRLF checkout of the same files,
- and, for the raw ``--no-cluster`` output, every edge endpoint is a declared node.

Bugs of this shape were found one at a time by diffing builds by hand (#4152,
#4154, #4156, #4164, #4180, #4182, #4188); this pins the invariants for every
extractor at once, so a new extractor or a change to the write paths cannot
silently break them.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
# Attributes that are not a function of the source tree: community ids are
# assigned by clustering and are compared elsewhere (#3761).
_UNSTABLE_KEYS = frozenset({"community", "community_name"})


def _copy(src: Path, dst: Path, *, crlf: bool = False) -> Path:
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("graphify-out"))
    if crlf:
        for path in dst.rglob("*"):
            if not path.is_file():
                continue
            data = path.read_bytes()
            if b"\0" in data:
                continue
            try:
                data.decode("utf-8")
            except UnicodeDecodeError:
                continue
            path.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    return dst


def _build(root: Path, *, cluster: bool) -> dict:
    """Build ``root`` with the CLI and return graph.json, parsed, plus its raw text under ``"__text__"``."""
    args = [sys.executable, "-m", "graphify", "update", str(root), "--force"]
    if not cluster:
        args.append("--no-cluster")
    env = dict(os.environ, PYTHONHASHSEED="0", PYTHONIOENCODING="utf-8")
    result = subprocess.run(args, cwd=root, env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr[-2000:]
    text = (root / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    graph = json.loads(text)
    graph["__text__"] = text
    return graph


def _links(graph: dict) -> list[dict]:
    return graph.get("links", graph.get("edges", []))


def _canonical(graph: dict) -> tuple[Counter, Counter]:
    def key(item: dict) -> str:
        return json.dumps({k: v for k, v in item.items() if k not in _UNSTABLE_KEYS}, sort_keys=True)
    return Counter(key(n) for n in graph["nodes"]), Counter(key(e) for e in _links(graph))


def _assert_same(a: dict, b: dict, what: str) -> None:
    keys_a = set(a) - {"__text__", "built_at_commit"}
    keys_b = set(b) - {"__text__", "built_at_commit"}
    assert keys_a == keys_b, f"{what} changed graph.json's top-level keys: {sorted(keys_a ^ keys_b)}"
    nodes_a, edges_a = _canonical(a)
    nodes_b, edges_b = _canonical(b)
    only = {
        "nodes only in the first": list((nodes_a - nodes_b).elements())[:5],
        "nodes only in the second": list((nodes_b - nodes_a).elements())[:5],
        "edges only in the first": list((edges_a - edges_b).elements())[:5],
        "edges only in the second": list((edges_b - edges_a).elements())[:5],
    }
    assert not any(only.values()), f"{what} changed graph.json: " + json.dumps(only, indent=1)[:4000]


@pytest.fixture(scope="module", params=[False, True], ids=["no_cluster", "clustered"])
def builds(request, tmp_path_factory) -> dict:
    cluster = request.param
    base = tmp_path_factory.mktemp("invariance_clustered" if cluster else "invariance_raw")
    first = _copy(FIXTURES, base / "alice_home" / "proj")
    second = _copy(FIXTURES, base / "bob_elsewhere" / "checkout" / "proj")
    crlf = _copy(FIXTURES, base / "crlf_checkout" / "proj", crlf=True)
    cold = _build(first, cluster=cluster)
    return {
        "cluster": cluster,
        "cold": cold,
        "other_folder": _build(second, cluster=cluster),
        "rebuilt": _build(first, cluster=cluster),
        "crlf": _build(crlf, cluster=cluster),
    }


def test_fixture_corpus_is_not_trivial(builds):
    # Guard against a silently empty build making every comparison pass.
    assert len(builds["cold"]["nodes"]) > 500
    assert len(_links(builds["cold"])) > 500


def test_checkout_folder_does_not_change_the_graph(builds):
    _assert_same(builds["cold"], builds["other_folder"], "moving the checkout to another folder")


def test_graph_never_contains_the_checkout_path(builds):
    for graph in (builds["cold"], builds["rebuilt"], builds["other_folder"]):
        lowered = graph["__text__"].lower()
        assert "alice_home" not in lowered and "bob_elsewhere" not in lowered, (
            "graph.json embeds the checkout path: "
            + str([
                item.get("id") or (item.get("source"), item.get("target"))
                for item in graph["nodes"] + _links(graph)
                if "alice_home" in json.dumps(item).lower() or "bob_elsewhere" in json.dumps(item).lower()
            ][:10])
        )


def test_rebuilding_an_unchanged_tree_changes_nothing(builds):
    _assert_same(builds["cold"], builds["rebuilt"], "rebuilding the unchanged tree")


def test_line_endings_do_not_change_the_graph(builds):
    _assert_same(builds["cold"], builds["crlf"], "converting every text file to CRLF")


def test_every_edge_endpoint_is_a_declared_node(builds):
    for graph in (builds["cold"], builds["rebuilt"]):
        declared = {n["id"] for n in graph["nodes"]}
        undeclared = [
            (e.get("relation"), e.get("source"), e.get("target"))
            for e in _links(graph)
            if e.get("source") not in declared or e.get("target") not in declared
        ]
        assert undeclared == [], f"edges with an undeclared endpoint: {undeclared[:10]}"
