"""#4431: the skill's full build runs entity dedup like `graphify extract` does.

Runs the actual rendered Step 4 / Step 5 blocks against a hand-written
extraction and compares with ``build([...], dedup=True)`` (the CLI extract
call) and a following ``build_merge`` (the --update path).
"""
from __future__ import annotations

import copy
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from graphify.build import build, build_from_json, build_merge

ROOT = Path(__file__).resolve().parents[1]
SKILLS = sorted((ROOT / "graphify").glob("skill*.md"))
RUNNABLE = ["skill.md", "skill-aider.md", "skill-devin.md"]
pytestmark = pytest.mark.skipif(shutil.which("bash") is None, reason="needs bash")


def _full_build_part(text: str) -> str:
    cut = text.find("\n## For --update")
    return text if cut < 0 else text[:cut]


def _section(text: str, head: str) -> str:
    s = text[text.index(head):]
    return s[: s.index("\n### ", 5)]


def _blocks(sec: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)\n```", sec, re.S)


def _edge(s, t, src):
    return {"source": s, "target": t, "relation": "references", "confidence": "EXTRACTED",
            "confidence_score": 1.0, "source_file": src}


def frag(stem: str) -> dict:
    """The reporter's fixture (#4431): two docs sharing two entities."""
    src = f"docs/{stem}.md"
    return {"nodes": [
        {"id": f"docs_{stem}", "label": f"{stem}.md", "file_type": "document", "source_file": src},
        {"id": f"docs_{stem}_contract_446", "label": "Contract No. 446", "file_type": "concept", "source_file": src},
        {"id": f"docs_{stem}_acme_corp", "label": "ACME Corp.", "file_type": "concept", "source_file": src}],
        "edges": [_edge(f"docs_{stem}", f"docs_{stem}_contract_446", src),
                  _edge(f"docs_{stem}_contract_446", f"docs_{stem}_acme_corp", src)],
        "hyperedges": []}


def merged(*frags: dict) -> dict:
    return {"nodes": [n for f in frags for n in f["nodes"]], "edges": [e for f in frags for e in f["edges"]],
            "hyperedges": [h for f in frags for h in f.get("hyperedges", [])],
            "input_tokens": 0, "output_tokens": 0}


def run_skill(skill: str, work: Path, extraction: dict, directed: bool = False):
    """Run the rendered Step 4 then Step 5 blocks; return (step4 graph.json, step5 graph.json, stdout)."""
    text = (ROOT / "graphify" / skill).read_text(encoding="utf-8")
    out = work / "graphify-out"
    out.mkdir(parents=True, exist_ok=True)
    (out / ".graphify_python").write_text(sys.executable, encoding="utf-8")
    detect = {"total_files": 2, "total_words": 10, "files": {}}
    for d in (out, work):  # lean skills use graphify-out/, the monoliths use cwd
        (d / ".graphify_extract.json").write_text(json.dumps(extraction), encoding="utf-8")
        (d / ".graphify_detect.json").write_text(json.dumps(detect), encoding="utf-8")

    def sub(b):
        return b.replace("INPUT_PATH", str(work)).replace("IS_DIRECTED", str(directed))

    env = {"PATH": "/usr/bin:/bin", "PYTHONPATH": str(ROOT), "HOME": str(work)}
    step4 = sub(_blocks(_section(text, "### Step 4 -"))[0])
    r = subprocess.run(["bash", "-c", step4], cwd=work, capture_output=True, text=True, env=env)
    if r.returncode != 0:
        return None, None, r.stdout + r.stderr
    g4 = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    step5 = [b for b in _blocks(_section(text, "### Step 5 -")) if "LABELS_DICT" in b][0]
    step5 = sub(step5).replace("LABELS_DICT", "{cid: 'C' + str(cid) for cid in communities}")
    r5 = subprocess.run(["bash", "-c", step5], cwd=work, capture_output=True, text=True, env=env)
    assert r5.returncode == 0, r5.stdout + r5.stderr
    g5 = json.loads((out / "graph.json").read_text(encoding="utf-8"))
    return g4, g5, r.stdout + r.stderr + r5.stdout + r5.stderr


def topo(g: dict):
    return ({n["id"] for n in g["nodes"]},
            {tuple(sorted((e["source"], e["target"]))) + (e["relation"],) for e in g["links"]})


@pytest.mark.parametrize("skill", SKILLS, ids=lambda p: p.name)
def test_rendered_full_build_uses_dedup_build(skill):
    lines = _full_build_part(skill.read_text(encoding="utf-8")).splitlines()
    assert any("build([extraction], dedup=True," in line for line in lines)
    for i, line in enumerate(lines):
        if "build_from_json(" in line and not line.startswith("**"):
            # Only allowed as the no-re-dedup branch for build_merge output (#3477).
            assert "_merged_by_build_merge" in lines[i - 1], f"{skill.name}:{i}: {line}"


@pytest.mark.parametrize("skill", RUNNABLE)
def test_step4_matches_cli_build_and_update_keeps_topology(skill, tmp_path):
    A, B = frag("lot_a"), frag("lot_b")
    cli = build([copy.deepcopy(A), copy.deepcopy(B)], root=str(tmp_path), directed=False)
    assert build_from_json(merged(A, B), root=str(tmp_path)).number_of_nodes() == 6  # the old skill count
    g4, g5, log = run_skill(skill, tmp_path, merged(A, B))
    assert g4 is not None, log
    assert len(g4["nodes"]) == cli.number_of_nodes() == 4
    assert topo(g4) == topo(g5), "Step 5 re-export must not re-shape the Step 4 graph"
    assert {n["id"] for n in g5["nodes"]} == set(cli.nodes)
    # communities in graph.json cover every node (Step 5 reuses Step 4's ids)
    assert all("community" in n for n in g5["nodes"])
    G3 = build_merge([copy.deepcopy(B)], graph_path=str(tmp_path / "graphify-out" / "graph.json"),
                     root=str(tmp_path), directed=False)
    assert set(G3.nodes) == {n["id"] for n in g4["nodes"]}
    lot_a = {n["id"] for n in g4["nodes"] if n.get("source_file") == "docs/lot_a.md"}
    before = {e for e in topo(g4)[1] if set(e[:2]) <= lot_a}
    after = {tuple(sorted((u, v))) + (d["relation"],) for u, v, d in G3.edges(data=True) if {u, v} <= lot_a}
    assert before == after


def test_step4_no_duplicates_unchanged(tmp_path):
    A = frag("only")
    g4, _, log = run_skill("skill.md", tmp_path, merged(A))
    assert g4 is not None, log
    assert topo(g4)[0] == set(build_from_json(merged(A)).nodes)


def test_step4_empty_extraction_stops(tmp_path):
    g4, _, log = run_skill("skill.md", tmp_path, merged())
    assert g4 is None and "Graph is empty" in log
    assert not (tmp_path / "graphify-out" / "graph.json").exists()


def test_step4_code_and_docs_mixed_matches_cli(tmp_path):
    A, B = frag("lot_a"), frag("lot_b")
    code = {"nodes": [
        {"id": "a_main", "label": "main()", "file_type": "code", "source_file": "a.py", "source_location": "L1"},
        {"id": "b_main", "label": "main()", "file_type": "code", "source_file": "b.py", "source_location": "L1"}],
        "edges": [], "hyperedges": []}
    ext = merged(A, B, code)
    cli = build([copy.deepcopy(ext)], root=str(tmp_path))
    g4, _, log = run_skill("skill.md", tmp_path, ext)
    assert g4 is not None, log
    ids = {n["id"] for n in g4["nodes"]}
    assert ids == set(cli.nodes)
    assert {"a_main", "b_main"} <= ids, "same-label code symbols in different files must stay separate"


def test_step4_hyperedges_follow_merged_nodes(tmp_path):
    A, B = frag("lot_a"), frag("lot_b")
    B["hyperedges"] = [{"id": "h1", "label": "signers", "relation": "participate_in",
                        "nodes": ["docs_lot_b_acme_corp", "docs_lot_b_contract_446"], "source_file": "docs/lot_b.md"}]
    g4, _, log = run_skill("skill.md", tmp_path, merged(A, B))
    assert g4 is not None, log
    ids = {n["id"] for n in g4["nodes"]}
    hyper = g4.get("hyperedges") or g4.get("graph", {}).get("hyperedges", [])
    assert hyper, "hyperedge dropped"
    for h in hyper:
        assert set(h["nodes"]) <= ids


def test_step4_directed_flag_kept(tmp_path):
    g4, _, log = run_skill("skill.md", tmp_path, merged(frag("lot_a"), frag("lot_b")), directed=True)
    assert g4 is not None, log
    assert g4["directed"] is True and len(g4["nodes"]) == 4


def test_step4_shrink_over_undeduped_graph_explains_dedup(tmp_path):
    """An old non-dedup graph.json is larger; to_json's #479 guard refuses, and Step 4 says why."""
    A, B = frag("lot_a"), frag("lot_b")
    from graphify.cluster import cluster
    from graphify.export import to_json
    (tmp_path / "graphify-out").mkdir()
    G_old = build_from_json(merged(A, B), root=str(tmp_path))
    to_json(G_old, cluster(G_old), str(tmp_path / "graphify-out" / "graph.json"))
    g4, _, log = run_skill("skill.md", tmp_path, merged(A, B))
    assert g4 is None
    assert "entity dedup merged 2 duplicate node(s)" in log and "refused to shrink" in log


def _as_update_output(G) -> dict:
    """What references/update.md writes back to .graphify_extract.json after build_merge."""
    return {
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": [{**{k: v for k, v in d.items() if k not in ("_src", "_tgt", "source", "target")},
                   "source": d.get("_src", u), "target": d.get("_tgt", v)} for u, v, d in G.edges(data=True)],
        "hyperedges": list(G.graph.get("hyperedges", [])),
        "input_tokens": 0, "output_tokens": 0, "_merged_by_build_merge": True,
    }


def test_update_md_marks_merged_extraction():
    refs = sorted((ROOT / "graphify" / "skills").glob("*/references/update.md"))
    assert refs
    for ref in refs:
        assert "'_merged_by_build_merge': True," in ref.read_text(encoding="utf-8"), ref


def test_step4_after_update_does_not_redup_protected_nodes(tmp_path):
    """#3477: build_merge keeps untouched existing nodes apart; Step 4 must not collapse them afterwards."""
    from graphify.cluster import cluster
    from graphify.export import to_json
    A, B, C = frag("lot_a"), frag("lot_b"), frag("lot_c")
    old = tmp_path / "old"
    old.mkdir()
    G0 = build_from_json(merged(A, B, C), root=str(tmp_path))  # graph.json from a pre-fix skill build
    to_json(G0, cluster(G0), str(old / "graph.json"))
    G1 = build_merge([copy.deepcopy(C)], graph_path=str(old / "graph.json"), root=str(tmp_path))
    g4, _, log = run_skill("skill.md", tmp_path, _as_update_output(G1))
    assert g4 is not None, log
    assert {n["id"] for n in g4["nodes"]} == set(G1.nodes)
