"""PageIndex-style document hierarchy contracts."""

from graphify.document_index import build_document_index

from graphify.extractors.markdown import extract_markdown


def test_document_index_builds_stable_section_paths_and_ranges():
    text = """# Overview
intro
## Runtime Flow
details
### Cache
cache details
## Operations
ops
"""

    index = build_document_index("guide.md", text)

    assert [section.path for section in index.sections] == [
        "Overview",
        "Overview / Runtime Flow",
        "Overview / Runtime Flow / Cache",
        "Overview / Operations",
    ]
    assert index.sections[1].start_line == 3
    assert index.sections[1].end_line == 6
    assert index.sections[2].parent_id == index.sections[1].section_id


def test_document_index_hash_changes_only_for_changed_section_content():
    before = build_document_index("guide.md", "# A\none\n# B\ntwo\n")
    after = build_document_index("guide.md", "# A\none\n# B\nchanged\n")

    assert before.sections[0].content_ref == after.sections[0].content_ref
    assert before.sections[1].content_ref != after.sections[1].content_ref


def test_markdown_extraction_publishes_hierarchy_for_lazy_section_navigation(tmp_path):
    """Removing document-index integration must erase parent/path metadata."""
    source = tmp_path / "guide.md"
    source.write_text("# Overview\nintro\n## Runtime Flow\ndetails\n", encoding="utf-8")

    result = extract_markdown(source)
    runtime = next(node for node in result["nodes"] if node["label"] == "Runtime Flow")

    assert runtime["section_path"] == "Overview / Runtime Flow"
    assert runtime["heading_level"] == 2
    assert runtime["parent_section_index_id"]
    assert runtime["content_start_line"] == 3
    assert runtime["content_end_line"] == 4
