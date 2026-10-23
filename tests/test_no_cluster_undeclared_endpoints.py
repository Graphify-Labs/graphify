"""The raw --no-cluster graph.json follows build_from_json's endpoint rules (#2873).

build_from_json drops every edge it cannot attach to two declared nodes and
mints a typed stub for an import of an external module. The raw --no-cluster
write paths skip build_from_json: `graphify update --no-cluster` only minted the
stubs, and `graphify extract --no-cluster` did neither. Their graph.json kept
edges to undeclared nodes, and a link to a missing markdown document kept a
target id built from the absolute checkout path.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

PYTHON = sys.executable


def _write_corpus(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "app.py").write_text("import os\n\n\ndef home():\n    return os.getcwd()\n", encoding="utf-8")
    (root / "README.md").write_text(
        "# Demo\n\nSee [the guide](docs/guide.md) and [[Roadmap]].\n", encoding="utf-8"
    )
    return root


def _graph(root: Path) -> tuple[set[str], list[dict]]:
    data = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    return {n["id"] for n in data["nodes"]}, data.get("links", data.get("edges", []))


def _undeclared(ids: set[str], links: list[dict]) -> list[tuple[str, str, str]]:
    return [
        (e["relation"], e["source"], e["target"])
        for e in links
        if e["source"] not in ids or e["target"] not in ids
    ]


def test_finalize_raw_graph_endpoints_matches_build_from_json():
    from graphify.build import finalize_raw_graph_endpoints

    stub = {"label": "", "file_type": "concept", "type": "external", "external": True, "source_file": ""}
    data = {
        "nodes": [{"id": "readme"}, {"id": "app"}, {**stub, "id": "requests"}],
        "edges": [
            {"source": "readme", "target": "home_alice_proj_docs_guide_md", "relation": "references"},
            {"source": "app", "target": "os", "relation": "imports"},
            {"source": "App", "target": "readme", "relation": "references"},
            {"from": "readme", "to": "app", "relation": "mentions"},
            {"source": "ghost", "target": "app", "relation": "calls"},
        ],
    }
    finalize_raw_graph_endpoints(data)
    # `os` is minted for its import; `requests` is a stub no edge points at any more
    assert [n["id"] for n in data["nodes"]] == ["readme", "app", "os"]
    assert [(e.get("source", e.get("from")), e.get("target", e.get("to"))) for e in data["edges"]] == [
        ("app", "os"),
        ("app", "readme"),  # re-pointed by normalization, as build_from_json does
        ("readme", "app"),
    ]


def test_finalize_raw_graph_endpoints_binds_a_basename_import_to_the_real_header():
    # A framework `#import <Kit/ToolEvent.h>` resolves to a real header whose node
    # id is `kit_event_toolevent` but whose import target is the bare basename
    # `toolevent`. The clustered path re-points this onto the file node via its
    # basename alias; the raw path must do the same instead of minting a stub
    # (#4670). A genuinely external `foundation` still gets its stub.
    from graphify.build import finalize_raw_graph_endpoints

    data = {
        "nodes": [
            {"id": "kit_event_toolevent", "label": "ToolEvent.h",
             "source_file": "Kit/Event/ToolEvent.h"},
            {"id": "kit_holder", "label": "Holder.h", "source_file": "Kit/Holder.h"},
        ],
        "edges": [
            {"source": "kit_holder", "target": "toolevent", "relation": "imports"},
            {"source": "kit_event_toolevent", "target": "foundation", "relation": "imports"},
        ],
    }
    finalize_raw_graph_endpoints(data)
    imports = sorted((e["source"], e["target"]) for e in data["edges"]
                     if e["relation"] == "imports")
    assert imports == [("kit_event_toolevent", "foundation"),
                       ("kit_holder", "kit_event_toolevent")]
    assert [n["id"] for n in data["nodes"] if n.get("external")] == ["foundation"]


def test_update_no_cluster_writes_no_undeclared_endpoint(tmp_path: Path):
    from graphify.watch import _rebuild_code

    raw = _write_corpus(tmp_path / "alice_home" / "raw")
    clustered = _write_corpus(tmp_path / "alice_home" / "clustered")
    assert _rebuild_code(raw, no_cluster=True, acquire_lock=False) is True
    assert _rebuild_code(clustered, no_cluster=False, acquire_lock=False) is True

    ids, links = _graph(raw)
    assert _undeclared(ids, links) == []
    leaked = [e["target"] for e in links if "alice_home" in e["target"]]
    assert leaked == [], f"edge target built from the checkout path: {leaked}"

    # Same nodes and the same linked pairs as the clustered graph (which may keep
    # fewer parallel edges per pair, by design).
    clustered_ids, clustered_links = _graph(clustered)
    assert ids == clustered_ids
    def pairs(edges: list[dict]) -> set[frozenset[str]]:
        return {frozenset((e["source"], e["target"])) for e in edges}
    assert pairs(links) == pairs(clustered_links)


def test_extract_no_cluster_writes_no_undeclared_endpoint(tmp_path: Path):
    root = _write_corpus(tmp_path / "proj")
    r = subprocess.run(
        [PYTHON, "-m", "graphify", "extract", ".", "--code-only", "--no-cluster"],
        cwd=root, capture_output=True, text=True,
    )
    assert r.returncode == 0, r.stderr
    ids, links = _graph(root)
    assert _undeclared(ids, links) == []
    assert "os" in ids, "an import of an external module gets a typed stub node"
    assert any(e["relation"] == "imports" and e["target"] == "os" for e in links)


def test_extract_no_cluster_objc_framework_import_matches_clustered(tmp_path: Path):
    # End-to-end #4670: `#import <Kit/ToolEvent.h>` resolving to a real header must
    # attach to the file node under --no-cluster exactly as under the clustered
    # path, not land on a basename stub.
    src = tmp_path / "r" / "Kit" / "Event"
    src.mkdir(parents=True)
    (src / "ToolEvent.h").write_text(
        "#import <Foundation/Foundation.h>\n@interface ToolEvent : NSObject\n@end\n",
        encoding="utf-8",
    )
    (tmp_path / "r" / "Kit" / "Holder.h").write_text(
        "#import <Kit/ToolEvent.h>\n@interface Holder : NSObject\n@end\n", encoding="utf-8"
    )

    def run(out: str, no_cluster: bool) -> tuple[set[str], set[tuple[str, str]]]:
        args = [PYTHON, "-m", "graphify", "extract", "r", "--code-only", "--out", out]
        if no_cluster:
            args.append("--no-cluster")
        r = subprocess.run(args, cwd=tmp_path, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        data = json.loads(
            (tmp_path / out / "graphify-out" / "graph.json").read_text(encoding="utf-8")
        )
        links = data.get("links", data.get("edges", []))
        return (
            {n["id"] for n in data["nodes"] if n.get("external")},
            {(e["source"], e["target"]) for e in links if e["relation"] == "imports"},
        )

    raw_stubs, raw_imports = run("raw", no_cluster=True)
    clu_stubs, clu_imports = run("clu", no_cluster=False)
    assert raw_imports == clu_imports
    assert raw_stubs == clu_stubs == {"foundation"}


def test_extract_no_cluster_drops_stub_of_a_removed_import(tmp_path: Path):
    root = tmp_path / "proj"
    root.mkdir()
    (root / "app.py").write_text(
        "import os\nimport json\n\n\ndef home():\n    return os.getcwd()\n", encoding="utf-8"
    )

    def extract() -> tuple[set[str], list[dict]]:
        r = subprocess.run(
            [PYTHON, "-m", "graphify", "extract", ".", "--code-only", "--no-cluster"],
            cwd=root, capture_output=True, text=True,
        )
        assert r.returncode == 0, r.stderr
        return _graph(root)

    ids, _ = extract()
    assert "os" in ids
    (root / "app.py").write_text("import json\n\n\ndef home():\n    return '.'\n", encoding="utf-8")
    ids, links = extract()
    assert "os" not in ids
    assert "json" in ids
    assert _undeclared(ids, links) == []
