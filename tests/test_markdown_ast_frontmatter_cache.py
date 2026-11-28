from graphify.cache import load_cached, save_cached
from graphify.extract import extract


def test_markdown_frontmatter_edit_refreshes_ast_but_keeps_semantic_cache(tmp_path):
    note = tmp_path / "doc.md"
    for page in ("old", "new"):
        (tmp_path / f"{page}.md").write_text(f"# {page}\n", encoding="utf-8")

    def write(target):
        note.write_text(f'---\nconsulted: "[[{target}]]"\n---\n# Notes\n',
                        encoding="utf-8")

    def assert_graph(target):
        result = extract([note], root=tmp_path, cache_root=tmp_path, parallel=False)
        metadata = next(n["frontmatter"] for n in result["nodes"] if n.get("frontmatter"))
        assert metadata["consulted"] == f"[[{target}]]"
        assert {edge["target"] for edge in result["edges"]
                if edge["relation"] == "references"} == {target}

    write("old")
    assert_graph("old")
    semantic = {"nodes": [{"id": "meaning", "label": "Meaning", "source_file": "doc.md"}],
                "edges": []}
    save_cached(note, semantic, root=tmp_path, kind="semantic")
    write("new")
    # Prime the body-only digest first to exercise the shared stat memo.
    hit = load_cached(note, root=tmp_path, kind="semantic")
    assert hit is not None and hit["nodes"][0]["id"] == "meaning"
    assert_graph("new")
    assert load_cached(note, root=tmp_path, kind="semantic") is not None
