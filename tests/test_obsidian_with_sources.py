"""Tests for `--with-sources` on the Obsidian export (issue #1968).

Without the flag, node notes are bare stubs (frontmatter + Connections). With
it, each node's `source_file` is copied into `sources/` as a real note and every
node note gets a callout linking to that source, so the vault is usable
standalone.
"""
import networkx as nx

from graphify.export import to_obsidian


def _graph():
    G = nx.Graph()
    # A markdown doc (copied verbatim) and a code file (fenced), plus a node
    # whose source_file does not exist on disk (must get no callout).
    G.add_node("n0", label="Best Practices", file_type="document",
               source_file="en/best-practices.md", community=0)
    G.add_node("n1", label="foo", file_type="code", source_file="util.py", community=0)
    G.add_node("n2", label="Ghost", file_type="document",
               source_file="missing/nope.md", community=0)
    G.add_edge("n0", "n1", relation="mentions", confidence="EXTRACTED")
    return G, {0: ["n0", "n1", "n2"]}


def _make_sources(root):
    (root / "en").mkdir()
    (root / "en" / "best-practices.md").write_text(
        "---\ntitle: BP\n---\n# Best Practices\n\nUse graphify wisely.\n", encoding="utf-8")
    (root / "util.py").write_text("def foo():\n    return 42\n", encoding="utf-8")


def test_default_export_has_no_source_notes(tmp_path):
    """Absent the flag, behaviour is unchanged: no sources/ dir, no callout."""
    _make_sources(tmp_path)
    G, comms = _graph()
    vault = tmp_path / "vault"
    to_obsidian(G, comms, str(vault))
    assert not (vault / "sources").exists()
    assert "> [!info] Source" not in (vault / "Best Practices.md").read_text(encoding="utf-8")


def test_with_sources_copies_and_wires_notes(tmp_path):
    _make_sources(tmp_path)
    G, comms = _graph()
    vault = tmp_path / "vault"
    to_obsidian(G, comms, str(vault), with_sources=True, source_root=tmp_path)

    # Source notes are copied under sources/ with collision-safe flattened names.
    src_dir = vault / "sources"
    assert (src_dir / "_src_en_best-practices.md").exists()
    assert (src_dir / "_src_util.py.md").exists()

    # Markdown is copied verbatim; code is embedded in a fenced block.
    md_src = (src_dir / "_src_en_best-practices.md").read_text(encoding="utf-8")
    assert "Use graphify wisely." in md_src
    py_src = (src_dir / "_src_util.py.md").read_text(encoding="utf-8")
    assert "```python" in py_src and "return 42" in py_src

    # Each resolvable node note gets a callout linking to its source note,
    # displayed with the original source_file path.
    note = (vault / "Best Practices.md").read_text(encoding="utf-8")
    assert "> [!info] Source" in note
    assert "[[_src_en_best-practices|en/best-practices.md]]" in note


def test_unresolvable_source_gets_no_callout(tmp_path):
    """A node whose source_file is missing on disk must not get a dangling
    callout (and must not abort the export)."""
    _make_sources(tmp_path)
    G, comms = _graph()
    vault = tmp_path / "vault"
    to_obsidian(G, comms, str(vault), with_sources=True, source_root=tmp_path)
    ghost = (vault / "Ghost.md").read_text(encoding="utf-8")
    assert "> [!info] Source" not in ghost
    assert not (vault / "sources" / "_src_missing_nope.md").exists()


def test_rerun_without_sources_prunes_source_notes(tmp_path):
    """Source notes are graphify-owned, so dropping --with-sources on a re-export
    prunes them and removes the callout — the vault returns to bare notes."""
    _make_sources(tmp_path)
    G, comms = _graph()
    vault = tmp_path / "vault"
    to_obsidian(G, comms, str(vault), with_sources=True, source_root=tmp_path)
    assert list((vault / "sources").glob("*.md"))

    to_obsidian(G, comms, str(vault), with_sources=False)
    assert not list((vault / "sources").glob("*.md"))
    assert "> [!info] Source" not in (vault / "foo.md").read_text(encoding="utf-8")


def test_source_root_list_and_fallback(tmp_path):
    """source_root accepts a list of candidate roots (scan root, then out dir for
    <=0.9.16 graphs); the first root that holds the file wins."""
    scan_root = tmp_path / "project"
    out_dir = tmp_path / "project" / "graphify-out"
    scan_root.mkdir()
    out_dir.mkdir()
    # source_file stored relative to the SCAN root (the #1941 layout).
    (scan_root / "a.py").write_text("x = 1\n", encoding="utf-8")
    G = nx.Graph()
    G.add_node("n0", label="a", file_type="code", source_file="a.py", community=0)
    G.add_node("n1", label="b", file_type="code", source_file="a.py", community=0)
    G.add_edge("n0", "n1", relation="r", confidence="EXTRACTED")
    vault = tmp_path / "vault"
    to_obsidian(G, {0: ["n0", "n1"]}, str(vault),
                with_sources=True, source_root=[scan_root, out_dir])
    # One shared source note for the shared source_file, both notes wired to it.
    assert (vault / "sources" / "_src_a.py.md").exists()
    assert "[[_src_a.py|a.py]]" in (vault / "a.md").read_text(encoding="utf-8")
    assert "[[_src_a.py|a.py]]" in (vault / "b.md").read_text(encoding="utf-8")
