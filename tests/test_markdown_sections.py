"""The section-text read path: `get_section` / `graphify section`.

A heading node records only its heading line. The section it opens is found at
read time from the current file, so an agent gets the section body instead of a
line number it then has to open the file for.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from graphify.extractors.markdown import extract_markdown
from graphify.sections import read_section, resolve_section_query
from graphify.watch import _rebuild_code

DOC = """\
---
title: Payments
token: ghp_abcdefghijklmnopqrstuvwxyz0123456789
---
# Payments
Intro text.

## Retry policy
Retries 3 times with backoff.

```
# not a heading
```
### Limits
Max 30s.


## Refunds
Refunds take 5 days.

"""


def _node(path: Path, label: str) -> dict:
    node = next(n for n in extract_markdown(path)["nodes"] if n["label"] == label)
    return {**node, "source_file": path.name}


@pytest.fixture()
def doc(tmp_path: Path) -> Path:
    p = tmp_path / "design.md"
    p.write_text(DOC, encoding="utf-8")
    return p


def _read(doc: Path, label: str, **kw):
    section, reason = read_section(_node(doc, label), doc.parent, **kw)
    assert section is not None, reason
    return section


def test_section_runs_to_next_heading_of_same_or_shallower_level(doc: Path) -> None:
    s = _read(doc, "Retry policy")
    # Includes its Limits subsection and the fenced `#` line, stops before
    # Refunds, and drops the blank lines in between.
    assert (s.start, s.end) == (8, 15)
    assert s.text.splitlines()[0] == "## Retry policy"
    assert "# not a heading" in s.text and s.text.splitlines()[-1] == "Max 30s."
    assert "Refunds" not in s.text


def test_last_sections_run_to_end_of_file(doc: Path) -> None:
    assert (_read(doc, "Refunds").start, _read(doc, "Refunds").end) == (18, 19)
    assert _read(doc, "Payments").end == 19


def test_page_is_the_body_without_frontmatter(doc: Path) -> None:
    s = _read(doc, "design.md")
    assert s.start == 5 and s.text.startswith("# Payments")
    assert "ghp_" not in s.text


def test_edit_inside_a_section_after_indexing_is_returned_whole(doc: Path) -> None:
    node = _node(doc, "Retry policy")
    doc.write_text(DOC.replace("Max 30s.", "Max 30s.\nJitter 10%.\nCap 5 retries."),
                   encoding="utf-8")
    section, _ = read_section(node, doc.parent)
    assert section is not None and not section.moved
    assert section.text.splitlines()[-1] == "Cap 5 retries."


def test_heading_moved_by_an_edit_above_it_is_still_found(doc: Path) -> None:
    node = _node(doc, "Refunds")
    doc.write_text(DOC.replace("Intro text.", "Intro text.\nmore\nmore"), encoding="utf-8")
    section, _ = read_section(node, doc.parent)
    assert section is not None and section.moved
    assert section.text.startswith("## Refunds") and section.start == 20


def test_removed_heading_is_refused(doc: Path) -> None:
    node = _node(doc, "Refunds")
    doc.write_text("# Payments\n", encoding="utf-8")
    section, reason = read_section(node, doc.parent)
    assert section is None and "graphify update" in reason


def test_truncates_at_max_chars(doc: Path) -> None:
    s = _read(doc, "Payments", max_chars=10)
    assert s.truncated and len(s.text) == 10


def test_secrets_in_a_section_are_redacted(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text(
        "# Setup\nexport GH=ghp_abcdefghijklmnopqrstuvwxyz0123456789\n", encoding="utf-8")
    s = _read(tmp_path / "x.md", "Setup")
    assert "ghp_abcdefghijklmnopqrstuvwxyz0123456789" not in s.text


def test_control_characters_are_stripped_but_tabs_kept(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("# T\nok\x1b[31mred\tkept\n", encoding="utf-8")
    s = _read(tmp_path / "x.md", "T")
    assert "\x1b" not in s.text and "\tkept" in s.text


def test_path_outside_the_project_is_refused(tmp_path: Path) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    (tmp_path / "secret.md").write_text("# s\nkey\n", encoding="utf-8")
    node = {"label": "s", "node_kind": "heading", "source_file": "../secret.md",
            "source_location": "L1"}
    section, reason = read_section(node, root)
    assert section is None and "outside" in reason


def test_code_node_is_refused(tmp_path: Path) -> None:
    node = {"label": "fn", "file_type": "code", "source_file": "x.py", "source_location": "L1"}
    section, reason = read_section(node, tmp_path)
    assert section is None and "not a Markdown" in reason


def _two_file_graph() -> nx.DiGraph:
    G = nx.DiGraph()
    for i, f in enumerate(["README.md", "docs/api.md", "docs/openapi.md"]):
        G.add_node(f"n{i}", label="Installation", node_kind="heading",
                   source_file=f, source_location="L3")
    return G


def test_path_scoped_query_picks_one_of_several_same_named_headings() -> None:
    G = _two_file_graph()
    assert resolve_section_query(G, "docs/api.md::Installation") == ("n1", "")
    assert resolve_section_query(G, "api.md::Installation") == ("n1", "")
    assert resolve_section_query(G, "README.md::Installation") == ("n0", "")


def test_bare_ambiguous_heading_points_at_the_path_scoped_form() -> None:
    nid, err = resolve_section_query(_two_file_graph(), "Installation")
    assert nid is None and "path::" in err


def test_heading_wins_over_a_code_symbol_of_the_same_name() -> None:
    G = _two_file_graph()
    G.add_node("cls", label="Installation", file_type="code",
               source_file="setup.py", source_location="L1")
    G.add_node("cfg", label="Config", file_type="code", source_file="x.py", source_location="L1")
    G.add_node("cfg_h", label="Config", node_kind="heading",
               source_file="README.md", source_location="L9")
    assert resolve_section_query(G, "Config") == ("cfg_h", "")


def test_same_titled_headings_after_an_edit_above_are_refused_not_guessed(tmp_path: Path) -> None:
    p = tmp_path / "api.md"
    p.write_text("# A\n### Example\none\n# B\n### Example\ntwo\n", encoding="utf-8")
    second = [n for n in extract_markdown(p)["nodes"] if n["label"] == "Example"][1]
    second = {**second, "source_file": p.name}
    p.write_text("new\nlines\n" + p.read_text(encoding="utf-8"), encoding="utf-8")
    section, reason = read_section(second, tmp_path)
    assert section is None and "graphify update" in reason


def test_skill_files_are_sections_like_the_extractor_says() -> None:
    from graphify.extract import _DISPATCH
    from graphify.extractors.markdown import extract_markdown as md
    from graphify.sections import _MARKDOWN_SUFFIXES
    assert _MARKDOWN_SUFFIXES == {s for s, fn in _DISPATCH.items() if fn is md}


@pytest.mark.parametrize("text", [
    DOC,
    "---\nnote: |\n  ```\n---\n# Hidden\nx\n",
    "---\nnote: |\n  ```\n---\nx\n```\n# Real\ny\n",
    "# Step\t1\nbody\n",
    "# " + "L" * 300 + "\nbody\n",
])
def test_every_extracted_heading_is_readable(tmp_path: Path, text: str) -> None:
    p = tmp_path / "d.md"
    p.write_text(text, encoding="utf-8")
    for n in extract_markdown(p)["nodes"]:
        section, reason = read_section({**n, "source_file": p.name}, tmp_path)
        assert section is not None and not section.moved, reason


def test_merged_multi_repo_node_is_refused(doc: Path) -> None:
    node = {**_node(doc, "Refunds"), "repo": "billing"}
    section, reason = read_section(node, doc.parent)
    assert section is None and "repo" in reason


def test_out_of_project_root_marker_is_not_trusted(tmp_path: Path) -> None:
    from graphify.sections import section_root
    out = tmp_path / "proj" / "graphify-out"
    out.mkdir(parents=True)
    (out / ".graphify_root").write_text(str(tmp_path.anchor), encoding="utf-8")
    root = section_root(out / "graph.json")
    assert root.resolve() in ((tmp_path / "proj").resolve(), out.resolve())


def _project(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    (root / "design.md").write_text(DOC, encoding="utf-8")
    assert _rebuild_code(root, acquire_lock=False, no_cluster=True) is True
    return root


def test_graph_json_is_unchanged_by_the_feature(tmp_path: Path) -> None:
    """Nothing is stored: the extractor output a graph was built from is enough."""
    root = _project(tmp_path)
    graph = json.loads((root / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert not any("end_location" in n for n in graph["nodes"])


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "graphify", "section", *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    )


def test_cli_section_prints_the_section(tmp_path: Path) -> None:
    root = _project(tmp_path)
    out = _run_cli(root, "Retry policy")
    assert out.returncode == 0, out.stderr
    assert "design.md:L8-L15" in out.stdout
    assert "Max 30s." in out.stdout and "Refunds take" not in out.stdout


def test_cli_section_unknown_heading_exits_not_found(tmp_path: Path) -> None:
    root = _project(tmp_path)
    assert _run_cli(root, "No such heading").returncode == 4


def test_mcp_get_section_and_get_node_hint(tmp_path: Path) -> None:
    from tests.test_serve_http import _call_tool, _client, _init_session
    import graphify.serve as serve_mod

    root = _project(tmp_path)
    app = serve_mod._build_http_app(str(root / "graphify-out" / "graph.json"),
                                    json_response=True)
    with _client(app) as client:
        headers = _init_session(client)
        text = _call_tool(client, headers, "get_section", {"label": "Limits"}, rid=2)
        scoped = _call_tool(client, headers, "get_section",
                            {"label": "design.md::Refunds"}, rid=3)
        node = _call_tool(client, headers, "get_node", {"label": "Limits"}, rid=4)
    assert text.startswith("Section: Limits  [design.md:L14-L15]"), text
    assert "Max 30s." in text
    assert "Refunds take 5 days." in scoped
    assert "get_section returns" in node
