"""Exercise the shared file-based B3 and Part C pipeline (#3820)."""
import json
import re
import shlex
from pathlib import Path

from tools.skillgen import gen

REPO_ROOT = Path(__file__).resolve().parent.parent


def _pipeline_scripts(platform):
    config = gen.load_platforms()[platform]
    core = next(a.content for a in gen.render(config) if a.path == config.skill_dst)
    pipeline = core.split("**Step B3 - Collect, cache, and merge**", 1)[1].split("### Step 4", 1)[0]
    blocks = re.findall(r'```bash\n\$\(cat graphify-out/\.graphify_python\) -c "(.*?)"\n```', pipeline, re.S)
    assert len(blocks) == 4
    spec = REPO_ROOT / f"graphify/skills/{platform}/references/extraction-spec.md"
    return [shlex.split('python -c "' + block + '"')[2]
            .replace("INPUT_PATH", ".").replace("SPEC_PATH", spec.as_posix()) for block in blocks]


def test_shared_chunk_pipeline_preserves_results_and_cache(tmp_path, monkeypatch):
    from graphify.cache import load_cached

    monkeypatch.chdir(tmp_path)
    out = Path("graphify-out")
    out.mkdir()
    chunks = []
    for number in range(2):
        doc = tmp_path / f"doc{number}.md"
        doc.write_text("# Example\nThree related concepts.\n", encoding="utf-8")
        nodes = [{"id": f"doc{number}_{name}", "label": name, "source_file": str(doc)} for name in ("a", "b", "c")]
        chunk = {
            "nodes": nodes,
            "edges": [{"source": nodes[0]["id"], "target": nodes[1]["id"], "relation": "references", "source_file": str(doc)}],
            "hyperedges": [{"id": f"group{number}", "nodes": [node["id"] for node in nodes], "source_file": str(doc)}],
            "input_tokens": 12 + number, "output_tokens": 8 + number,
        }
        chunks.append(chunk)
        (out / f".graphify_chunk_{number:02}.json").write_text(json.dumps(chunk), encoding="utf-8")
    cached = {
        "nodes": [{"id": "cached", "label": "Cached"}],
        "edges": [{"source": "cached", "target": "doc0_a"}],
        "hyperedges": [{"id": "cached_group", "nodes": ["cached", "doc0_a", "doc1_a"]}],
    }
    ast = {"nodes": [{"id": "ast", "label": "AST"}, chunks[0]["nodes"][0]], "edges": [{"source": "ast", "target": "doc0_a"}]}
    (out / ".graphify_cached.json").write_text(json.dumps(cached), encoding="utf-8")
    (out / ".graphify_ast.json").write_text(json.dumps(ast), encoding="utf-8")
    (out / ".graphify_uncached.txt").write_text("".join(f"{tmp_path / f'doc{n}.md'}\n" for n in range(2)), encoding="utf-8")
    expected_new = {key: chunks[0][key] + chunks[1][key] for key in chunks[0]}
    results = []
    caches = []
    for platform in ("claude", "codex"):
        for name in (".graphify_semantic_new.json", ".graphify_semantic.json", ".graphify_extract.json"):
            (out / name).unlink(missing_ok=True)
        for script in _pipeline_scripts(platform):
            exec(compile(script, f"<rendered {platform} pipeline>", "exec"), {})
        assert json.loads((out / ".graphify_semantic_new.json").read_text()) == expected_new
        semantic = json.loads((out / ".graphify_semantic.json").read_text())
        assert semantic == {**expected_new, **{key: cached[key] + expected_new[key] for key in cached}}
        final = json.loads((out / ".graphify_extract.json").read_text())
        assert final == {**semantic,
                         "nodes": ast["nodes"] + [node for node in semantic["nodes"] if node["id"] not in {n["id"] for n in ast["nodes"]}],
                         "edges": ast["edges"] + semantic["edges"]}
        results.append(final)
        spec = REPO_ROOT / f"graphify/skills/{platform}/references/extraction-spec.md"
        saved = [load_cached(tmp_path / f"doc{n}.md", root=tmp_path, kind="semantic", prompt_file=spec) for n in range(2)]
        for chunk, entry in zip(chunks, saved):
            assert entry is not None
            for key in ("nodes", "edges", "hyperedges"):
                assert entry[key] == chunk[key]
        caches.append(saved)
    assert results[0] == results[1]
    assert caches[0] == caches[1]
