"""Skill-side ownership checks before cache writes and destructive replacement."""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from graphify.build import build_merge
from graphify.skill_merge import (
    assert_semantic_scope,
    collect_semantic_dispatch,
    prepare_semantic_dispatch,
)


def node(identifier, source):
    return {"id": identifier, "label": identifier, "file_type": "document",
            "source_file": str(source), "_origin": "semantic"}


def write_chunk(assignment, data):
    Path(assignment["path"]).write_text(json.dumps(data), encoding="utf-8")


def test_foreign_stub_growth_cannot_replace_23_undispatched_nodes(tmp_path):
    own, foreign = tmp_path / "A.md", tmp_path / "B.md"
    own.write_text("Changed A")
    foreign.write_text("Unchanged B")
    output = tmp_path / "graphify-out"
    assignment = prepare_semantic_dispatch([[own]], root=tmp_path, output_dir=output)[0]
    saved = {"nodes": [node(f"b_rich_{i}", "B.md") for i in range(23)]
             + [node("a_old", "A.md")], "links": [], "graph": {},
             "directed": False, "multigraph": False}
    graph_path = output / "graph.json"
    graph_path.write_text(json.dumps(saved), encoding="utf-8")
    cache_path = output / "cache-marker.json"
    cache_path.write_text('{"unchanged": true}', encoding="utf-8")
    graph_before, cache_before = graph_path.read_bytes(), cache_path.read_bytes()
    incoming = {"nodes": [node(f"a_new_{i}", own) for i in range(35)]
                + [node("b_stub", foreign)], "edges": []}
    write_chunk(assignment, incoming)

    # The old unguarded path loses B even though its total grows 24 -> 36.
    unguarded = build_merge([incoming], graph_path, root=tmp_path, dedup=False)
    assert unguarded.number_of_nodes() == 36
    assert not any(f"b_rich_{i}" in unguarded for i in range(23))
    with pytest.raises(ValueError, match="outside its FILE_LIST"):
        collected = collect_semantic_dispatch(output)
        build_merge([collected], graph_path, root=tmp_path, dedup=False)
        cache_path.write_text("should never execute", encoding="utf-8")
    assert graph_path.read_bytes() == graph_before
    assert cache_path.read_bytes() == cache_before


def test_sibling_dispatch_does_not_grant_another_chunks_file(tmp_path):
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    output = tmp_path / "graphify-out"
    assignments = prepare_semantic_dispatch([[a], [b]], root=tmp_path, output_dir=output)
    write_chunk(assignments[0], {"nodes": [node("foreign_stub", b)], "edges": []})
    write_chunk(assignments[1], {"nodes": [node("b_real", b)], "edges": []})
    with pytest.raises(ValueError, match="outside its FILE_LIST"):
        collect_semantic_dispatch(output)


def test_owned_chunks_keep_complete_cross_chunk_edge_references(tmp_path):
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    output = tmp_path / "graphify-out"
    assignments = prepare_semantic_dispatch([[a], [b]], root=tmp_path, output_dir=output)
    edge = {"source": "a_complete", "target": "b_complete", "relation": "references",
            "confidence": "EXTRACTED", "source_file": str(a)}
    write_chunk(assignments[0], {"nodes": [node("a_complete", a)], "edges": [edge]})
    write_chunk(assignments[1], {"nodes": [node("b_complete", b)], "edges": []})
    result = collect_semantic_dispatch(output)
    assert [n["id"] for n in result["nodes"]] == ["a_complete", "b_complete"]
    assert result["edges"] == [edge]


@pytest.mark.parametrize("bucket", ["nodes", "edges", "hyperedges"])
def test_all_semantic_buckets_require_chunk_owned_provenance(tmp_path, bucket):
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    result = {"nodes": [node("a_complete", a)], "edges": [], "hyperedges": []}
    result[bucket].append({"id": "foreign", "source_file": str(b)})
    original = copy.deepcopy(result)
    with pytest.raises(ValueError, match="outside its FILE_LIST"):
        assert_semantic_scope(result, root=tmp_path, allowed_source_files=[a])
    assert result == original  # the guard does not silently trim the result


def test_scope_uses_the_cache_path_alias_rules(tmp_path):
    source = tmp_path / "pkg" / "A.md"
    source.parent.mkdir()
    source.touch()
    result = {"nodes": [node("a_complete", "pkg\\A.md")], "edges": []}
    original = copy.deepcopy(result)
    assert_semantic_scope(result, root=tmp_path, allowed_source_files=[source])
    assert result == original


def test_old_run_glob_matches_never_enter_current_aggregation(tmp_path):
    source = tmp_path / "A.md"
    source.touch()
    output = tmp_path / "graphify-out"
    old = prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)[0]
    Path(old["path"]).write_text("invalid stale JSON", encoding="utf-8")
    current = prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)[0]
    assert current["path"] != old["path"]
    write_chunk(current, {"nodes": [node("fresh", source)], "edges": []})
    assert [n["id"] for n in collect_semantic_dispatch(output)["nodes"]] == ["fresh"]


def test_missing_current_result_never_reuses_an_old_chunk_number(tmp_path):
    source = tmp_path / "A.md"
    source.touch()
    output = tmp_path / "graphify-out"
    old = prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)[0]
    write_chunk(old, {"nodes": [node("old", source)], "edges": []})
    prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)
    with pytest.raises(ValueError, match="current semantic chunks are missing"):
        collect_semantic_dispatch(output)


@pytest.mark.parametrize("name", ["../escape.json", ".graphify_chunk_" + "0" * 32 + "_01.json"])
def test_dispatch_manifest_cannot_read_unowned_paths(tmp_path, name):
    source = tmp_path / "A.md"
    source.touch()
    output = tmp_path / "graphify-out"
    prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)
    manifest_path = output / ".graphify_dispatch.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["chunks"] = {name: [str(source)]}
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="current dispatch run"):
        collect_semantic_dispatch(output)


def test_missing_provenance_is_not_guessed(tmp_path):
    result = {"nodes": [{"id": "stub"}], "edges": []}
    with pytest.raises(ValueError, match="originating source_file"):
        assert_semantic_scope(result, root=tmp_path, allowed_source_files=[])


def runbook_python(text, marker):
    """Execute the actual generated runbook block, with no shell or agent calls."""
    import re

    section = text[text.index(marker):]
    block = re.search(r'```bash\n.*?-c "\n(.*?)\n"\n```', section, re.DOTALL)
    assert block is not None
    return block.group(1).replace('\\"', '"').replace('IS_DIRECTED', 'False')


def test_generated_controller_refuses_before_aggregate_cache_and_update_writes(tmp_path, monkeypatch):
    from tools.skillgen import gen

    arts = gen.render_all(gen.load_platforms(), only="claude")
    core = next(a.content for a in arts if a.path == "graphify/skill.md")
    update = next(a.content for a in arts if a.path.endswith("/update.md"))
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "graphify-out"
    output.mkdir()
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    (output / ".graphify_root").write_text(str(tmp_path))
    (output / ".graphify_detect.json").write_text(json.dumps({"files": {"document": [str(a)]}}))
    (output / ".graphify_uncached.txt").write_text(str(a))
    exec(runbook_python(core, "Before dispatch, persist"), {})
    manifest = json.loads((output / ".graphify_dispatch.json").read_text())
    name = next(iter(manifest["chunks"]))
    write_chunk({"path": output / name}, {"nodes": [node("foreign_stub", b)], "edges": []})
    saved = {"nodes": [node(f"b_rich_{i}", "B.md") for i in range(23)]
             + [node("a_old", "A.md")], "links": [], "graph": {},
             "directed": False, "multigraph": False}
    paths = [output / "graph.json", output / ".graphify_semantic_new.json",
             output / ".graphify_manifest.json", output / ".graphify_extract.json"]
    paths[0].write_text(json.dumps(saved))
    paths[1].write_text('{"previous": "aggregate"}')
    paths[2].write_text('{"previous": "manifest"}')
    paths[3].write_text(json.dumps({"nodes": [node("foreign_stub", b)], "edges": []}))
    before = {p: p.read_bytes() for p in paths}
    (output / ".graphify_incremental.json").write_text(json.dumps({
        "new_files": {"document": [str(a)]}, "files": {"document": [str(a), str(b)]},
    }))
    for text, marker in [(core, "**Step B3"), (core, "Save new results to cache."),
                         (update, "# Load new extraction and incremental state")]:
        # For the update snippet the marker is inside the block, so select its preceding fence.
        if text is update:
            marker = "\nThen:\n"
        with pytest.raises(ValueError, match="outside its FILE_LIST"):
            exec(runbook_python(text, marker).replace("INPUT_PATH", str(tmp_path)), {})
        assert {p: p.read_bytes() for p in paths} == before


def test_generated_incremental_code_only_skips_old_dispatch(tmp_path, monkeypatch):
    from tools.skillgen import gen

    update = next(a.content for a in gen.render_all(gen.load_platforms(), only="claude")
                  if a.path.endswith("/update.md"))
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "graphify-out"
    output.mkdir()
    (tmp_path / "A.py").touch()
    (output / "graph.json").write_text(json.dumps({
        "nodes": [node("a_old", "A.py")], "links": [], "graph": {},
        "directed": False, "multigraph": False,
    }))
    (output / ".graphify_extract.json").write_text(json.dumps({
        "nodes": [node("a_new", "A.py")], "edges": [],
    }))
    (output / ".graphify_incremental.json").write_text(json.dumps({
        "new_files": {"code": [str(tmp_path / "A.py")]},
        "files": {"code": [str(tmp_path / "A.py")]},
    }))
    (output / ".graphify_dispatch.json").write_text("invalid stale manifest")
    exec(runbook_python(update, "\nThen:\n").replace("INPUT_PATH", str(tmp_path)), {})
    merged = json.loads((output / ".graphify_extract.json").read_text())
    assert [n["id"] for n in merged["nodes"]] == ["a_new"]


def test_empty_dispatch_replaces_previous_run_without_old_chunk_replay(tmp_path):
    output = tmp_path / "graphify-out"
    source = tmp_path / "A.md"
    source.touch()
    old = prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)[0]
    write_chunk(old, {"nodes": [node("old", source)], "edges": []})
    assert prepare_semantic_dispatch([], root=tmp_path, output_dir=output) == []
    assert collect_semantic_dispatch(output)["nodes"] == []


def test_missing_dispatch_manifest_is_a_failure(tmp_path):
    with pytest.raises(FileNotFoundError):
        collect_semantic_dispatch(tmp_path)


def test_generated_cached_assembly_reads_owned_chunks_not_old_aggregate(tmp_path, monkeypatch):
    from tools.skillgen import gen

    core = next(a.content for a in gen.render_all(gen.load_platforms(), only="claude")
                if a.path == "graphify/skill.md")
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "graphify-out"
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    assignment = prepare_semantic_dispatch([[a]], root=tmp_path, output_dir=output)[0]
    write_chunk(assignment, {"nodes": [node("a_current", a)], "edges": []})
    (output / ".graphify_cached.json").write_text(json.dumps({
        "nodes": [node("b_cached", b)], "edges": [],
    }))
    (output / ".graphify_semantic_new.json").write_text(json.dumps({
        "nodes": [node("b_foreign_old_aggregate", b)], "edges": [],
    }))
    exec(runbook_python(core, "Merge cached + new results into"), {})
    merged = json.loads((output / ".graphify_semantic.json").read_text())
    assert [n["id"] for n in merged["nodes"]] == ["b_cached", "a_current"]
    before = (output / ".graphify_semantic.json").read_bytes()
    write_chunk(assignment, {"nodes": [node("b_foreign", b)], "edges": []})
    with pytest.raises(ValueError, match="outside its FILE_LIST"):
        exec(runbook_python(core, "Merge cached + new results into"), {})
    assert (output / ".graphify_semantic.json").read_bytes() == before


def test_generated_update_reports_prefix_but_keeps_known_external_reference(tmp_path, monkeypatch, capsys):
    from tools.skillgen import gen

    update = next(a.content for a in gen.render_all(gen.load_platforms(), only="claude")
                  if a.path.endswith("/update.md"))
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "graphify-out"
    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    assignment = prepare_semantic_dispatch([[a]], root=tmp_path, output_dir=output)[0]
    edges = [{"source": "a_complete", "target": target, "relation": "references",
              "confidence": "EXTRACTED", "source_file": str(a)}
             for target in ("b_complete", "b")]
    fresh = {"nodes": [node("a_complete", a)], "edges": edges}
    write_chunk(assignment, fresh)
    (output / "graph.json").write_text(json.dumps({
        "nodes": [node("b_complete", "B.md")], "links": [], "graph": {},
        "directed": False, "multigraph": False,
    }))
    graph_before = (output / "graph.json").read_bytes()
    (output / ".graphify_ast.json").write_text(json.dumps({"nodes": [], "edges": []}))
    (output / ".graphify_extract.json").write_text(json.dumps(fresh))
    (output / ".graphify_incremental.json").write_text(json.dumps({
        "new_files": {"document": [str(a)]}, "files": {"document": [str(a), str(b)]},
    }))
    exec(runbook_python(update, "\nThen:\n").replace("INPUT_PATH", str(tmp_path)), {})
    message = capsys.readouterr().out
    assert "Unresolved incoming references before persistence:" in message
    assert "dangling_endpoint_edges: 1" in message
    merged = json.loads((output / ".graphify_extract.json").read_text())
    assert len(merged["edges"]) == 1
    assert {merged["edges"][0]["source"], merged["edges"][0]["target"]} == {"a_complete", "b_complete"}
    assert (output / "graph.json").read_bytes() == graph_before


def test_generated_update_ignores_stale_payload_and_loads_only_owned_cache(tmp_path, monkeypatch):
    from graphify.cache import save_semantic_cache
    from tools.skillgen import gen

    update = next(a.content for a in gen.render_all(gen.load_platforms(), only="claude")
                  if a.path.endswith("/update.md"))
    monkeypatch.chdir(tmp_path)
    output = tmp_path / "graphify-out"
    a, b, c = (tmp_path / name for name in ("A.md", "B.md", "C.md"))
    for source in (a, b, c):
        source.write_text(source.name)
    spec = tmp_path / "spec.md"
    spec.write_text("test prompt")
    cached_edge = {"source": "c_cached", "target": "b_rich_0", "relation": "references",
                   "confidence": "EXTRACTED", "source_file": str(c)}
    save_semantic_cache([node("c_cached", c)], [cached_edge], [], root=tmp_path, prompt_file=spec)
    assignment = prepare_semantic_dispatch([[a]], root=tmp_path, output_dir=output)[0]
    fresh = {"nodes": [node(f"a_new_{i}", a) for i in range(35)], "edges": []}
    write_chunk(assignment, fresh)
    (output / "graph.json").write_text(json.dumps({
        "nodes": [node(f"b_rich_{i}", "B.md") for i in range(23)] + [node("a_old", "A.md")],
        "links": [], "graph": {}, "directed": False, "multigraph": False,
    }))
    graph_before = (output / "graph.json").read_bytes()
    # Structural records stay outside the semantic ownership check.
    (output / ".graphify_ast.json").write_text(json.dumps({
        "nodes": [node("x_structural", "X.py")], "edges": [],
    }))
    stale = {**fresh, "nodes": fresh["nodes"] + [node("b_foreign_stub", b)]}
    for name in (".graphify_extract.json", ".graphify_semantic.json",
                 ".graphify_semantic_new.json", ".graphify_cached.json"):
        (output / name).write_text(json.dumps(stale))
    (output / ".graphify_incremental.json").write_text(json.dumps({
        "new_files": {"document": [str(a), str(c)]},
        "files": {"document": [str(a), str(b), str(c)]},
    }))
    exec(runbook_python(update, "\nThen:\n").replace("INPUT_PATH", str(tmp_path))
         .replace("SPEC_PATH", str(spec)), {})
    merged = json.loads((output / ".graphify_extract.json").read_text())
    ids = {n["id"] for n in merged["nodes"]}
    assert all(f"b_rich_{i}" in ids for i in range(23))
    assert "b_foreign_stub" not in ids
    assert {"a_new_0", "c_cached", "x_structural"} <= ids
    assert any({e["source"], e["target"]} == {"c_cached", "b_rich_0"} for e in merged["edges"])
    assert (output / "graph.json").read_bytes() == graph_before


def test_update_cannot_reuse_a_valid_dispatch_for_unchanged_sources(tmp_path):
    from graphify.skill_merge import load_skill_update_extraction

    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    output = tmp_path / "graphify-out"
    old = prepare_semantic_dispatch([[b]], root=tmp_path, output_dir=output)[0]
    write_chunk(old, {"nodes": [node("b_old", b)], "edges": []})
    with pytest.raises(ValueError, match="outside its FILE_LIST"):
        load_skill_update_extraction([a], root=tmp_path, prompt_file="missing-spec", output_dir=output)


def test_update_does_not_replay_just_saved_fresh_edges_as_cache_hits(tmp_path):
    from graphify.cache import save_semantic_cache
    from graphify.skill_merge import load_skill_update_extraction

    source = tmp_path / "A.md"
    source.write_text("A")
    output = tmp_path / "graphify-out"
    assignment = prepare_semantic_dispatch([[source]], root=tmp_path, output_dir=output)[0]
    edge = {"source": "a_one", "target": "a_two", "relation": "references",
            "confidence": "EXTRACTED", "source_file": str(source)}
    fresh = {"nodes": [node("a_one", source), node("a_two", source)], "edges": [edge]}
    write_chunk(assignment, fresh)
    (output / ".graphify_ast.json").write_text(json.dumps({"nodes": [], "edges": []}))
    spec = tmp_path / "spec.md"
    spec.write_text("prompt")
    save_semantic_cache(fresh["nodes"], fresh["edges"], [], root=tmp_path, prompt_file=spec)
    merged = load_skill_update_extraction([source], root=tmp_path, prompt_file=spec, output_dir=output)
    assert merged["edges"] == [edge]


def test_empty_foreign_dispatch_plan_cannot_borrow_current_changed_scope(tmp_path):
    from graphify.skill_merge import load_skill_update_extraction

    a, b = tmp_path / "A.md", tmp_path / "B.md"
    a.touch()
    b.touch()
    output = tmp_path / "graphify-out"
    old = prepare_semantic_dispatch([[b]], root=tmp_path, output_dir=output)[0]
    write_chunk(old, {"nodes": [], "edges": []})
    with pytest.raises(ValueError, match="outside its FILE_LIST"):
        load_skill_update_extraction([a], root=tmp_path, prompt_file="missing-spec", output_dir=output)
