"""to_json's lost-node check excuses sources build_merge replaced or pruned.

LLM extraction is not id-stable: re-extracting an edited doc gives its
semantic nodes new ids. build_merge drops the old ones on purpose, so the
#479 write guard must not count them as lost. Nodes of files this run did not
touch, and files with an unverified shrink (#3203), stay guarded.
"""
from __future__ import annotations

import json
from pathlib import Path

import graphify.__main__ as mainmod
import graphify.llm as llmmod
from graphify.build import build_merge
from graphify.export import to_json


def _sem(sf: str, name: str) -> dict:
    stem = sf.replace(".", "_")
    return {"id": f"{stem}_{name}", "label": f"{sf} {name}",
            "file_type": "document", "source_file": sf}


def _write_graph(gp: Path, nodes) -> None:
    gp.parent.mkdir(parents=True, exist_ok=True)
    gp.write_text(json.dumps({"nodes": list(nodes), "edges": [], "hyperedges": []}),
                  encoding="utf-8")


def _saved(tmp_path: Path) -> Path:
    gp = tmp_path / "graphify-out" / "graph.json"
    _write_graph(gp, [_sem("a.md", f"old{i}") for i in range(2)]
                 + [_sem("b.md", f"b{i}") for i in range(3)])
    return gp


def _ids(gp: Path) -> set[str]:
    return {n["id"] for n in json.loads(gp.read_text(encoding="utf-8"))["nodes"]}


def test_reextracted_source_with_new_ids_is_not_lost(tmp_path):
    gp = _saved(tmp_path)
    chunk = {"nodes": [_sem("a.md", f"new{i}") for i in range(2)], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)

    assert to_json(G, {0: list(G.nodes)}, str(gp), force=False) is True
    assert _ids(gp) == {"a_md_new0", "a_md_new1", "b_md_b0", "b_md_b1", "b_md_b2"}
    assert "_replaced_sources" not in json.loads(gp.read_text(encoding="utf-8")).get("graph", {})


def test_pruned_source_is_not_lost(tmp_path, capsys):
    gp = _saved(tmp_path)
    G = build_merge([{"nodes": [], "edges": []}], gp, prune_sources=["b.md"],
                    dedup=False, root=tmp_path)

    # The separate node-count check may still refuse a net shrink; only the
    # lost-id check is under test here.
    to_json(G, {0: list(G.nodes)}, str(gp), force=False)
    assert "saved semantic node(s) are missing" not in capsys.readouterr().err


def test_untouched_source_loss_still_refused(tmp_path, capsys):
    gp = _saved(tmp_path)
    chunk = {"nodes": [_sem("a.md", f"new{i}") for i in range(2)], "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)
    G.remove_node("b_md_b1")  # b.md was neither re-extracted nor pruned

    assert to_json(G, {0: list(G.nodes)}, str(gp), force=False) is False
    err = capsys.readouterr().err
    assert "b_md_b1" in err and "a_md_old0" not in err


def test_unverified_shrink_source_still_refused(tmp_path, capsys):
    gp = _saved(tmp_path)
    chunk = {"nodes": [_sem("a.md", "new0"), _sem("a.md", "new1"), _sem("b.md", "b0")],
             "edges": []}
    G = build_merge([chunk], gp, dedup=False, root=tmp_path)
    assert G.graph["_unverified_semantic_shrink"] == {"b.md": (3, 1)}

    assert to_json(G, {0: list(G.nodes)}, str(gp), force=False) is False
    err = capsys.readouterr().err
    assert "b_md_b1" in err and "a_md_old0" not in err


def _run_cli():
    try:
        mainmod.main()
    except SystemExit as exc:
        return exc.code
    return 0


def _llm(nodes, uncovered=()):
    def run(files, **kwargs):
        res = {"nodes": nodes, "edges": [], "hyperedges": [], "input_tokens": 1,
               "output_tokens": 1, "uncovered_files": list(uncovered)}
        if kwargs.get("on_chunk_done"):
            kwargs["on_chunk_done"](0, 1, res)
        return res
    return run


def test_extract_edit_with_new_ids_and_omitted_file_writes(tmp_path, monkeypatch):
    """Edited README comes back with new ids while GUIDE is omitted by the model.

    The omission arms the guard, but GUIDE's saved nodes are kept and README
    was re-extracted, so nothing is lost and the write must go through.
    """
    corpus = tmp_path / "repo"
    corpus.mkdir()
    (corpus / "README.md").write_text("# Readme\nv1\n", encoding="utf-8")
    (corpus / "GUIDE.md").write_text("# Guide\nv1\n", encoding="utf-8")
    monkeypatch.setattr(mainmod, "_check_skill_version", lambda _: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-fake")
    argv = ["graphify", "extract", str(corpus), "--backend", "claude"]
    monkeypatch.setattr(mainmod.sys, "argv", argv)

    monkeypatch.setattr(llmmod, "extract_corpus_parallel", _llm(
        [_sem("README.md", "a"), _sem("README.md", "b"), _sem("GUIDE.md", "g")]))
    assert _run_cli() == 0

    (corpus / "README.md").write_text("# Readme\nv2\n", encoding="utf-8")
    (corpus / "GUIDE.md").write_text("# Guide\nv2\n", encoding="utf-8")
    monkeypatch.setattr(llmmod, "extract_corpus_parallel", _llm(
        [_sem("README.md", "c"), _sem("README.md", "d")], uncovered=["GUIDE.md"]))
    assert _run_cli() == 0

    ids = _ids(corpus / "graphify-out" / "graph.json")
    assert {"README_md_c", "README_md_d", "GUIDE_md_g"} <= ids
    assert not ids & {"README_md_a", "README_md_b"}
