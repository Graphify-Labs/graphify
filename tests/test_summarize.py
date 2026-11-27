"""`graphify summarize`: one deterministic summary per file-level node (#5041).

Summaries live in a sidecar next to graph.json, are written only when the
command is run, and are built by fixed rules with no model call. Code files are
summarized from the graph alone; a Markdown document (or a Word file, which is
converted to Markdown) from its title page when it has one, else from its
heading outline.
"""
from __future__ import annotations

import json
import random
import re
import subprocess
import sys
from pathlib import Path

import networkx as nx
import pytest

from graphify.cli import _load_cli_graph
from graphify.sections import section_root
from graphify.summarize import (
    SUMMARY_DOCUMENT_MAX_CHARS,
    SUMMARY_HARD_MAX_CHARS,
    SUMMARY_MAX_CHARS,
    SUMMARY_SIDECAR_NAME,
    build_summaries,
    file_node_ids,
    load_summaries,
    summarize_node,
    write_summaries,
)
from graphify.watch import _rebuild_code

SECRET = "ghp_abcdefghijklmnopqrstuvwxyz0123456789"

BILLING = '''\
"""Compute invoices and apply discounts for customer orders."""
import os
from pathlib import Path

from pkg import util


class Invoice:
    def total(self):
        return 1


def apply_discount(x):
    return util.helper(x)


def _private():
    return os.getcwd(), Path(".")
'''

GUIDE = """\
# Billing guide

Intro.

## Install
text
### Deep
text
## Usage
text
"""

# A title page: text and `Label: value` lines before the first top-level heading.
PROTOCOL = """\
<!-- converted from protocol.docx -->
Study Protocol

Protocol Number: ABC-123
Study Phase: 3
Sponsor: Acme Pharma
Signed: Date:
APPENDIX: SUPPORTING DETAILS\t55
Note: this sentence only looks like a field because it has a colon in it, and it runs on far too long to be one.

```
Hidden: in a fence
```

# Introduction
Body text.

## Background
More.
"""


def _project(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "proj"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    assert _rebuild_code(root, acquire_lock=False, no_cluster=True) is True
    return root


def _graph_path(root: Path) -> Path:
    return root / "graphify-out" / "graph.json"


def _summaries(root: Path) -> dict[str, str]:
    """``source_file -> summary`` for a built project, read the way the CLI does."""
    gp = _graph_path(root)
    data = build_summaries(_load_cli_graph(gp), section_root(gp))
    return {e["source_file"]: e["summary"] for e in data["nodes"].values()}


def _doc_summary(tmp_path: Path, text: str) -> "str | None":
    return _summaries(_project(tmp_path, {"doc.md": text})).get("doc.md")


# ------------------------------------------------------------------ default off


def test_building_a_graph_writes_no_summaries(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING, "docs/guide.md": GUIDE})
    assert not (root / "graphify-out" / SUMMARY_SIDECAR_NAME).exists()


# ------------------------------------------------------------------------- code


def test_code_file_has_docstring_symbols_and_imports(tmp_path: Path) -> None:
    root = _project(tmp_path, {
        "pkg/__init__.py": "",
        "pkg/billing.py": BILLING,
        "pkg/util.py": "def helper(x):\n    return x\n",
    })
    # Public names before the underscore-prefixed helper; this project's own
    # file before the standard library; the package __init__ is not listed.
    assert _summaries(root)["pkg/billing.py"] == (
        "Compute invoices and apply discounts for customer orders. "
        "Defines Invoice, apply_discount(), _private(); imports util.py, os, pathlib."
    )


def test_code_file_without_a_docstring_starts_with_its_symbols(tmp_path: Path) -> None:
    root = _project(tmp_path, {"util.py": "def helper(x):\n    return x\n"})
    assert _summaries(root)["util.py"] == "Defines helper()."


def test_community_name_is_used_only_when_someone_named_it() -> None:
    def graph(community_name: str) -> nx.DiGraph:
        G = nx.DiGraph()
        G.add_node("f", label="a.py", source_file="a.py", file_type="code",
                   community_name=community_name)
        G.add_node("s", label="run()", source_file="a.py", source_location="L1",
                   file_type="code")
        G.add_node("hub", label="dispatch()", source_file="b.py", file_type="code")
        G.add_edge("f", "s", relation="contains")
        return G

    assert summarize_node(graph("Request routing"), "f") == (
        'Defines run(); community "Request routing".')
    # An unnamed community is called after its busiest node, or "Community N".
    assert summarize_node(graph("dispatch"), "f") == "Defines run()."
    assert summarize_node(graph("Community 7"), "f") == "Defines run()."


def test_file_with_nothing_to_say_gets_no_entry(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/__init__.py": "", "pkg/util.py": "def helper():\n    pass\n"})
    G = _load_cli_graph(_graph_path(root))
    labels = {G.nodes[n]["label"] for n in file_node_ids(G)}
    assert "__init__.py" in labels
    assert "pkg/__init__.py" not in _summaries(root)


def test_only_file_level_nodes_are_summarized(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING, "docs/guide.md": GUIDE})
    G = _load_cli_graph(_graph_path(root))
    data = build_summaries(G, root)
    assert sorted(e["source_file"] for e in data["nodes"].values()) == [
        "docs/guide.md", "pkg/billing.py"]
    symbol = next(n for n, d in G.nodes(data=True) if d.get("label") == "apply_discount()")
    heading = next(n for n, d in G.nodes(data=True) if d.get("label") == "Install")
    assert summarize_node(G, symbol, root) is None
    assert summarize_node(G, heading, root) is None
    assert summarize_node(G, "no-such-node", root) is None


@pytest.mark.parametrize("label, expected", [
    # Cut inside the second sentence: the first one is kept.
    ("Read the section text. A heading node records the…", "Read the section text."),
    # Cut exactly after a sentence: only the ellipsis goes.
    ("Read the section text.…", "Read the section text."),
    # Cut inside the only sentence: nothing complete to keep, so it stays as it is.
    ("Read the section text from the file a heading node…",
     "Read the section text from the file a heading node…"),
    ("Read the section text", "Read the section text."),
])
def test_docstring_label_cut_mid_sentence_keeps_whole_sentences(label: str, expected: str) -> None:
    G = nx.DiGraph()
    G.add_node("f", label="a.py", source_file="a.py", file_type="code")
    G.add_node("r", label=label, source_file="a.py", source_location="L1", file_type="rationale")
    G.add_edge("r", "f", relation="rationale_for")
    assert summarize_node(G, "f") == expected


def test_edge_direction_marker_is_honoured() -> None:
    """A link stored with flipped endpoints carries its real tail in `_src`."""
    G = nx.DiGraph()
    G.add_node("a", label="a.py", source_file="a.py", file_type="code")
    G.add_node("b", label="b.py", source_file="b.py", file_type="code")
    G.add_node("fa", label="fa()", source_file="a.py", source_location="L1", file_type="code")
    G.add_node("fb", label="fb()", source_file="b.py", source_location="L1", file_type="code")
    G.add_edge("a", "fa", relation="contains")
    G.add_edge("b", "fb", relation="contains")
    # a imports b, but the arc is stored b -> a.
    G.add_edge("b", "a", relation="imports", _src="a")
    assert summarize_node(G, "a") == "Defines fa(); imports b.py."
    assert summarize_node(G, "b") == "Defines fb()."


def test_undirected_graph_is_accepted() -> None:
    G = nx.Graph()
    G.add_node("a", label="a.py", source_file="a.py", file_type="code")
    G.add_node("fa", label="fa()", source_file="a.py", source_location="L1", file_type="code")
    G.add_edge("a", "fa", relation="contains")
    assert summarize_node(G, "a") == "Defines fa()."


# -------------------------------------------------------------------- documents


def test_document_opening_with_its_heading_lists_title_and_sections(tmp_path: Path) -> None:
    assert _doc_summary(tmp_path, GUIDE) == '"Billing guide": sections Install, Usage.'


def test_long_document_title_is_kept_whole(tmp_path: Path) -> None:
    title = "Incremental Updates and Entity Deduplication: Implementation Plan for the Build Pipeline"
    assert len(title) > 60
    assert _doc_summary(tmp_path, f"# {title}\n\n## File Map\ntext\n## Tasks\ntext\n") == (
        f'"{title}": sections File Map, Tasks.')


def test_summary_never_ends_with_two_full_stops(tmp_path: Path) -> None:
    # A field value that ends its own sentence, and a shortened section name.
    text = "Template\n\nLimit: 14 characters. Delete if not applicable.\n\n# Body\ntext\n"
    assert _doc_summary(tmp_path, text) == (
        "Template. Limit: 14 characters. Delete if not applicable.")
    long_name = "A section whose name is far too long to be listed in full in any summary at all"
    outline = _doc_summary(tmp_path / "outline", f"# Guide\n\n## {long_name}\ntext\n")
    assert outline and outline.endswith("…") and not outline.endswith("….")


def test_document_with_several_top_level_headings_lists_them(tmp_path: Path) -> None:
    text = "## Install\ntext\n## Usage\ntext\n### Deep\ntext\n## Limits\ntext\n"
    assert _doc_summary(tmp_path, text) == "Sections: Install, Usage, Limits."


def test_title_page_gives_title_and_fields(tmp_path: Path) -> None:
    # The table-of-contents line, the label-only line, the long sentence and
    # the fenced line are not fields.
    assert _doc_summary(tmp_path, PROTOCOL) == (
        "Study Protocol. Protocol Number: ABC-123; Study Phase: 3; Sponsor: Acme Pharma."
    )


def test_labelled_title_wins_over_the_first_line(tmp_path: Path) -> None:
    text = ("CONFIDENTIAL\n\nProtocol Title: A Study of Drug X in Condition Y\n"
            "Protocol Number: ABC-123\n\n# Introduction\ntext\n")
    # The first line is not the title, but it is kept after it as a cover line.
    assert _doc_summary(tmp_path, text) == (
        "A Study of Drug X in Condition Y. CONFIDENTIAL. Protocol Number: ABC-123.")


def test_title_page_that_is_the_first_top_level_section(tmp_path: Path) -> None:
    text = ("Template guidance for authors.\n\n# Title Page\n\nProtocol Number: ABC-123\n"
            "Compound: XYZ-9\n\n## Sponsor details\ntext\n\n# Summary\n\nPhase: 2\n")
    # Fields come from the first top-level section only, not from later ones.
    assert _doc_summary(tmp_path, text) == (
        "Template guidance for authors. Protocol Number: ABC-123; Compound: XYZ-9.")


# A title page laid out as a two-column table, the way Word documents usually do it.
REPORT = """\
CLINICAL STUDY REPORT

| Title: | A Phase 3 Study of Drug X in Condition Y |
| --- | --- |
| Study Phase: | Phase 3 |
| Sponsor | Acme Pharma |
| Short Title | Drug X Study |
| Comparator | placebo \\| standard of care |
| Empty value: |  |

Table 7.1: Study Objectives and Endpoints
Figure 2: Study Design Schematic

| Version | Date |
| --- | --- |
| Draft | 1 Jan 2024 |

| Site | Country | Subjects |
| --- | --- | --- |
| Alpha | France | 12 |

# Introduction
Body text.
"""


def test_title_page_table_rows_are_fields(tmp_path: Path) -> None:
    # Rows of the first two-column table are fields, with or without a colon
    # after the label. Not fields: the second title, the empty cell, the
    # numbered captions, the later two-column table and the three-column one.
    # The line above the table is kept after the title as a cover line.
    assert _doc_summary(tmp_path, REPORT) == (
        "A Phase 3 Study of Drug X in Condition Y. CLINICAL STUDY REPORT. "
        "Study Phase: Phase 3; Sponsor: Acme Pharma; Comparator: placebo | standard of care."
    )


def test_document_opening_with_a_table_has_a_title_page(tmp_path: Path) -> None:
    text = ("| Protocol Number | ABC-123 |\n| --- | --- |\n| Sponsor | Acme Pharma |\n\n"
            "# Introduction\ntext\n")
    assert _doc_summary(tmp_path, text) == "Protocol Number: ABC-123; Sponsor: Acme Pharma."


def test_table_in_a_document_that_opens_with_its_heading_is_not_a_title_page(
        tmp_path: Path) -> None:
    text = ("# Commands\n\n| Command | Description |\n| --- | --- |\n| update | rebuild |\n\n"
            "## Usage\ntext\n")
    assert _doc_summary(tmp_path, text) == '"Commands": sections Usage.'


def test_two_column_table_far_from_the_top_is_not_the_title_page(tmp_path: Path) -> None:
    prose = "".join(
        f"Guidance paragraph {chr(65 + i)} explains to authors how this part of the template "
        "should be filled in before the protocol is submitted.\n\n" for i in range(16))
    text = ("Protocol Template\n\n" + prose
            + "| AE | Adverse Event |\n| --- | --- |\n| SAE | Serious Adverse Event |\n\n"
            + "Version: 2.0\n\n# Introduction\ntext\n")
    assert _doc_summary(tmp_path, text) == "Protocol Template. Version: 2.0."


# A cover page: short lines above the first field, one of them a notice.
COVER = """\
q
READ BEFORE PROCEEDING
This notice explains that the changes in this version are not urgent and will be made at the next revision.
Product Safety Guide
Drug X (DX-1)
Contents:

Version: 14.0
Effective Date: 31 Aug 2023

Owner Team

# Introduction
text
"""


def test_cover_lines_above_the_first_field_are_kept_when_room_is_left(tmp_path: Path) -> None:
    # After the title, in page order: the short lines above the first field.
    # Not kept: the stray mark, the long sentence, the line ending in a colon,
    # and the line that comes after the fields.
    assert _doc_summary(tmp_path, COVER) == (
        "READ BEFORE PROCEEDING. Product Safety Guide. Drug X (DX-1). "
        "Version: 14.0; Effective Date: 31 Aug 2023."
    )


def test_cover_lines_never_push_out_a_field(tmp_path: Path) -> None:
    plain = _doc_summary(tmp_path, MANY_FIELDS)
    assert plain and plain.startswith("Study Report. Field Alpha: ")
    # More fields than fit: the summary is full, with a little room to spare.
    assert "Field Mu" not in plain
    listed = plain[len("Study Report. "):]

    def with_cover_line(line: str) -> str:
        return MANY_FIELDS.replace("Study Report\n", f"Study Report\n{line}\n", 1)

    # A cover line too long for the room that is left changes nothing.
    wide = "A Second Line Of The Cover Page That Is Long Enough Not To Fit Here"
    assert _doc_summary(tmp_path / "wide", with_cover_line(wide)) == plain

    # A short one fits after the title; the fields listed are exactly the same.
    short = _doc_summary(tmp_path / "short", with_cover_line("Draft Copy"))
    assert short == "Study Report. Draft Copy. " + listed
    assert len(short) <= SUMMARY_DOCUMENT_MAX_CHARS


def test_cover_lines_stop_at_six_and_skip_repeats(tmp_path: Path) -> None:
    lines = ["Annual Report", "Line One", "Line Two", "line one", "Line Three", "Line Four",
             "Line Five", "Line Six", "Line Seven"]
    text = "\n".join(lines) + "\n\nVersion: 2\n\n# Body\n"
    assert _doc_summary(tmp_path, text) == (
        "Annual Report. Line One. Line Two. Line Three. Line Four. Line Five. Line Six. "
        "Version: 2.")


def test_stray_first_line_is_not_a_title(tmp_path: Path) -> None:
    text = "q\n\nProduct Safety Guide\n\nVersion: 14.0\n\n# Introduction\ntext\n"
    assert _doc_summary(tmp_path, text) == "Product Safety Guide. Version: 14.0."


def test_second_title_field_is_dropped(tmp_path: Path) -> None:
    text = ("Full Title: A Study of Drug X\nShort Title: DX-1\nProtocol Number: ABC-123\n\n"
            "# Introduction\ntext\n")
    assert _doc_summary(tmp_path, text) == "A Study of Drug X. Protocol Number: ABC-123."


def test_prose_introduction_is_not_a_title_page(tmp_path: Path) -> None:
    text = ("<p align=\"center\">logo</p>\n\nThis tool maps a project into a graph\n"
            "so that an assistant can query it.\n\n## Install\ntext\n## Usage\ntext\n")
    assert _doc_summary(tmp_path, text) == "Sections: Install, Usage."


def test_title_page_in_a_document_with_no_headings(tmp_path: Path) -> None:
    """Headings are not needed for a title page: its fields are read from the text."""
    text = "Study Protocol\n\nProtocol Number: ABC-123\nStudy Phase: 3\nSponsor: Acme Pharma\n"
    assert _doc_summary(tmp_path, text) == (
        "Study Protocol. Protocol Number: ABC-123; Study Phase: 3; Sponsor: Acme Pharma.")


def test_document_with_no_headings_and_no_fields_gets_no_entry(tmp_path: Path) -> None:
    assert _doc_summary(tmp_path, "Just a paragraph of text.\n") is None


def test_word_document_is_summarized_from_its_title_page(tmp_path: Path) -> None:
    docx = pytest.importorskip("docx")
    root = tmp_path / "proj"
    root.mkdir()
    doc = docx.Document()
    doc.add_paragraph("Statistical Analysis Plan")
    table = doc.add_table(rows=2, cols=2)
    for row, (label, value) in zip(table.rows, [("Protocol Number:", "ABC-123"),
                                                ("Study Phase", "Phase 3")]):
        row.cells[0].text, row.cells[1].text = label, value
    doc.add_paragraph("Version: 2.0")
    doc.add_heading("Introduction", level=1)
    doc.add_paragraph("Body text.")
    doc.save(str(root / "sap.docx"))
    assert _rebuild_code(root, acquire_lock=False, no_cluster=True) is True
    summaries = _summaries(root)
    # graphify converts sap.docx to converted/sap_<8 hex>.md and summarizes that.
    converted = [s for src, s in summaries.items()
                 if re.fullmatch(r".*converted/sap_[0-9a-f]{8}\.md", src)]
    assert converted == [
        "Statistical Analysis Plan. Protocol Number: ABC-123; Study Phase: Phase 3; Version: 2.0."]


def test_without_a_root_no_file_is_read(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": PROTOCOL})
    G = _load_cli_graph(_graph_path(root))
    (page,) = file_node_ids(G)
    assert summarize_node(G, page) == '"Introduction": sections Background.'


def test_missing_source_file_falls_back_to_the_outline(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": PROTOCOL})
    (root / "doc.md").unlink()
    assert _summaries(root)["doc.md"] == '"Introduction": sections Background.'


def test_source_file_outside_the_project_is_not_read(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": GUIDE})
    outside = tmp_path / "outside.md"
    outside.write_text("Secret Plan\n\nOwner: someone else\n\n# Body\n", encoding="utf-8")
    G = _load_cli_graph(_graph_path(root))
    (page,) = file_node_ids(G)
    G.nodes[page]["source_file"] = str(outside)
    G.nodes[page]["label"] = "outside.md"
    summary = summarize_node(G, page, root)
    assert summary == '"Billing guide": sections Install, Usage.'


def test_merged_multi_repo_node_is_not_read(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": PROTOCOL})
    G = _load_cli_graph(_graph_path(root))
    (page,) = file_node_ids(G)
    G.nodes[page]["repo"] = "other"
    assert summarize_node(G, page, root) == '"Introduction": sections Background.'


# ------------------------------------------------------- cap, safety, stability


def test_every_summary_fits_the_cap() -> None:
    G = nx.DiGraph()
    G.add_node("f", label="big.py", source_file="big.py", file_type="code")
    G.add_node("r", label="word " * 60, source_file="big.py", source_location="L1",
               file_type="rationale")
    G.add_edge("r", "f", relation="rationale_for")
    for i in range(300):
        G.add_node(f"s{i}", label=f"a_very_long_symbol_name_{i}_" + "x" * 200 + "()",
                   source_file="big.py", source_location=f"L{i + 2}", file_type="code")
        G.add_edge("f", f"s{i}", relation="contains")
        G.add_node(f"m{i}", label="module_" + "y" * 200 + str(i), source_file="")
        G.add_edge("f", f"m{i}", relation="imports")
    summary = summarize_node(G, "f")
    assert summary and len(summary) <= SUMMARY_MAX_CHARS
    assert "(+" in summary


def test_long_title_page_fits_the_cap(tmp_path: Path) -> None:
    names = [a + b for a in "ABCDE" for b in "ABCDEFGH"]
    fields = "".join(f"Field {name}: value {name} " + "v" * 40 + "\n" for name in names)
    text = "Protocol Title: " + "A very long study title " * 20 + "\n" + fields + "\n# Body\ntext\n"
    summary = _doc_summary(tmp_path, text)
    assert summary and SUMMARY_MAX_CHARS < len(summary) <= SUMMARY_DOCUMENT_MAX_CHARS
    assert summary.startswith("A very long study title") and "Field AA: value AA" in summary


def test_hostile_long_lines_cost_a_bounded_amount_of_work(tmp_path: Path, monkeypatch) -> None:
    """A document is untrusted input. Matched against a whole line, the
    table-of-contents pattern took quadratic time on a long run of tabs (over
    30 s for 50,000). The bound is checked on the work done, not on a clock,
    so a slow machine cannot fail it: no rule is handed more than a fixed
    number of characters of any one line."""
    import graphify.summarize as summarize

    seen: list[int] = []
    real = summarize._TOC_TAIL_RE

    class Recording:
        def search(self, text: str):
            seen.append(len(text))
            return real.search(text)

        def __getattr__(self, name: str):
            # Anything else the code calls on the pattern goes to the real one.
            return getattr(real, name)

    monkeypatch.setattr(summarize, "_TOC_TAIL_RE", Recording())
    hostile = ["\t" * 50_000, "\t" * 50_000 + "x", "|" * 50_000,
               "Label: " + "word " * 50_000, "A" * 200_000]
    text = ("Runbook\n\n" + "\n".join(hostile) + "\n\nOwner: ops team\n"
            "Contents\t12\n\n# Steps\ntext\n")
    lines = text.splitlines()
    kept = summarize._plain_lines(lines, 0, len(lines), set())
    assert max(len(line) for line in kept) <= summarize._MAX_LINE_CHARS

    # The rules still read the page: the real field is found, the
    # table-of-contents line and the hostile lines are not.
    assert _doc_summary(tmp_path, text) == "Runbook. Owner: ops team."
    assert seen and max(seen) <= summarize._TOC_TAIL_CHARS


def test_secrets_and_control_characters_do_not_reach_a_summary(tmp_path: Path) -> None:
    text = f"Runbook\n\nOwner: ops\x1b[31m team\nAPI Token: {SECRET}\n\n# Steps\ntext\n"
    summary = _doc_summary(tmp_path, text)
    assert summary == "Runbook. Owner: ops[31m team; API Token: [redacted]."

    G = nx.DiGraph()
    G.add_node("f", label="a.py", source_file="a.py", file_type="code")
    G.add_node("s", label=f"token_{SECRET}\x00\x07()", source_file="a.py",
               source_location="L1", file_type="code")
    G.add_edge("f", "s", relation="contains")
    summary = summarize_node(G, "f")
    assert summary and SECRET not in summary and "\x00" not in summary and "\x07" not in summary


def test_output_is_byte_identical_across_runs_and_input_order(tmp_path: Path) -> None:
    root = _project(tmp_path, {
        "pkg/__init__.py": "", "pkg/billing.py": BILLING,
        "pkg/util.py": "def helper(x):\n    return x\n",
        "docs/guide.md": GUIDE, "docs/protocol.md": PROTOCOL,
    })
    gp = _graph_path(root)
    G = _load_cli_graph(gp)
    first, second = tmp_path / "one.json", tmp_path / "two.json"
    write_summaries(G, first, root)
    write_summaries(G, second, root)
    assert first.read_bytes() == second.read_bytes()

    nodes = list(G.nodes(data=True))
    edges = list(G.edges(data=True))
    rng = random.Random(5041)
    rng.shuffle(nodes)
    rng.shuffle(edges)
    shuffled = nx.DiGraph()
    shuffled.add_nodes_from(nodes)
    shuffled.add_edges_from(edges)
    third = tmp_path / "three.json"
    write_summaries(shuffled, third, root)
    assert third.read_bytes() == first.read_bytes()

    data = json.loads(first.read_text(encoding="utf-8"))
    assert data["version"] == 1 and data["generator"] == "deterministic"
    assert all(set(e) == {"label", "source_file", "summary", "generated_by"}
               for e in data["nodes"].values())


# -------------------------------------------------------------------- max chars

# A title page with more fields than fit in the default length.
MANY_FIELDS = ("Study Report\n\n" + "".join(
    f"Field {name}: value of field {name} for this study\n"
    for name in ("Alpha", "Beta", "Gamma", "Delta", "Epsilon", "Zeta", "Eta", "Theta",
                 "Iota", "Kappa", "Lambda", "Mu")) + "\n# Introduction\ntext\n")


def test_a_document_gets_more_room_than_a_code_file_by_default(tmp_path: Path) -> None:
    symbols = "".join(f"def a_function_with_a_rather_long_name_{i:02d}():\n    pass\n\n"
                      for i in range(12))
    root = _project(tmp_path, {"doc.md": MANY_FIELDS, "big.py": symbols})
    summaries = _summaries(root)
    assert SUMMARY_MAX_CHARS < len(summaries["doc.md"]) <= SUMMARY_DOCUMENT_MAX_CHARS
    assert len(summaries["big.py"]) <= SUMMARY_MAX_CHARS and "(+" in summaries["big.py"]


def test_max_chars_overrides_the_default_of_both_kinds(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": MANY_FIELDS})
    G = _load_cli_graph(_graph_path(root))
    (page,) = file_node_ids(G)
    default = summarize_node(G, page, root)
    shorter = summarize_node(G, page, root, max_chars=250)
    longer = summarize_node(G, page, root, max_chars=800)
    assert default and shorter and longer
    assert len(shorter) <= 250 < len(default) <= SUMMARY_DOCUMENT_MAX_CHARS < len(longer) <= 800
    # Each longer one continues the shorter one: same fields, then more.
    assert default.startswith(shorter.rstrip(".")) and longer.startswith(default.rstrip("."))
    assert "Field Zeta" not in shorter and "Field Zeta" in default
    assert "Field Mu" not in default and "Field Mu" in longer


def test_max_chars_is_held_inside_its_range(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": MANY_FIELDS})
    G = _load_cli_graph(_graph_path(root))
    (page,) = file_node_ids(G)
    tiny = summarize_node(G, page, root, max_chars=1)
    huge = summarize_node(G, page, root, max_chars=10**6)
    assert tiny and len(tiny) <= 50
    assert huge and len(huge) <= SUMMARY_HARD_MAX_CHARS


def test_cli_max_chars_is_written_read_back_and_shown_whole(tmp_path: Path) -> None:
    root = _project(tmp_path, {"doc.md": MANY_FIELDS})
    out = _run_cli(root, "summarize", "--max-chars", "800")
    assert out.returncode == 0, out.stderr
    gp = _graph_path(root)
    (entry,) = load_summaries(gp).values()
    assert SUMMARY_DOCUMENT_MAX_CHARS < len(entry["summary"]) <= 800
    assert "Field Mu" in entry["summary"]
    shown = _run_cli(root, "explain", "doc.md")
    assert f"  Summary:   {entry['summary']}" in shown.stdout.splitlines()
    one = _run_cli(root, "summarize", "doc.md", "--max-chars", "800")
    assert f"  Summary:   {entry['summary']}" in one.stdout.splitlines()


@pytest.mark.parametrize("value", ["10", "5000", "-1", "many"])
def test_cli_rejects_a_max_chars_outside_its_range(tmp_path: Path, value: str) -> None:
    root = _project(tmp_path, {"doc.md": MANY_FIELDS})
    out = _run_cli(root, "summarize", "--max-chars", value)
    assert out.returncode == 2
    assert "--max-chars" in out.stderr
    assert not (root / "graphify-out" / SUMMARY_SIDECAR_NAME).exists()


# ----------------------------------------------------------------------- loader


def _write_sidecar(folder: Path, payload) -> Path:
    path = folder / SUMMARY_SIDECAR_NAME
    path.write_text(payload if isinstance(payload, str) else json.dumps(payload),
                    encoding="utf-8")
    return folder / "graph.json"


def test_load_summaries_round_trip(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING})
    gp = _graph_path(root)
    G = _load_cli_graph(gp)
    path, summarized, file_nodes = write_summaries(G, gp.parent / SUMMARY_SIDECAR_NAME, root)
    assert (summarized, file_nodes) == (1, 1) and path.exists()
    loaded = load_summaries(gp)
    assert loaded == build_summaries(G, root)["nodes"]


def test_load_summaries_tolerates_missing_and_malformed_files(tmp_path: Path) -> None:
    assert load_summaries(tmp_path / "graph.json") == {}
    assert load_summaries(_write_sidecar(tmp_path, "{not json")) == {}
    assert load_summaries(_write_sidecar(tmp_path, [1, 2])) == {}
    assert load_summaries(_write_sidecar(tmp_path, {"nodes": "nope"})) == {}


def test_load_summaries_skips_bad_entries_and_recaps(tmp_path: Path) -> None:
    gp = _write_sidecar(tmp_path, {"version": 1, "nodes": {
        "ok": {"summary": "Fine.", "source_file": "a.py"},
        "long": {"summary": "word " * 400},
        "dirty": {"summary": f"line one\nline two \x1b[0m {SECRET}"},
        "not_a_dict": "text",
        "no_summary": {"source_file": "b.py"},
        "empty": {"summary": "   "},
        "bad_source": {"summary": "Text.", "source_file": 7},
    }})
    loaded = load_summaries(gp)
    assert sorted(loaded) == ["dirty", "long", "ok"]
    assert loaded["ok"] == {"summary": "Fine.", "source_file": "a.py"}
    # A reader holds a summary to the longest `--max-chars` allows.
    assert 900 < len(loaded["long"]["summary"]) <= SUMMARY_HARD_MAX_CHARS
    assert loaded["dirty"]["summary"] == "line one line two [0m [redacted]"


# -------------------------------------------------------------------------- CLI


def _run_cli(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "graphify", *args],
        cwd=root, capture_output=True, text=True, encoding="utf-8",
    )


def test_cli_writes_the_sidecar_and_leaves_the_graph_alone(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING, "docs/guide.md": GUIDE})
    gp = _graph_path(root)
    before = gp.read_bytes()
    out = _run_cli(root, "summarize")
    assert out.returncode == 0, out.stderr
    assert "Summarized 2 of 2 file nodes" in out.stdout
    assert gp.read_bytes() == before
    nodes = json.loads((gp.parent / SUMMARY_SIDECAR_NAME).read_text(encoding="utf-8"))["nodes"]
    assert {e["source_file"] for e in nodes.values()} == {"pkg/billing.py", "docs/guide.md"}


def test_cli_finds_a_word_file_by_its_original_name(tmp_path: Path) -> None:
    # The graph holds the Markdown a Word file was converted to, named
    # <stem>_<8 hex>.md in a converted/ folder, not the Word file itself.
    root = _project(tmp_path, {"converted/protocol_0123abcd.md": PROTOCOL,
                               "docs/guide.md": GUIDE})
    by_original = _run_cli(root, "summarize", "protocol.docx")
    assert by_original.returncode == 0, by_original.stderr
    assert "Node: protocol_0123abcd.md" in by_original.stdout
    assert by_original.stdout == _run_cli(root, "summarize", "protocol_0123abcd.md").stdout
    # Only a converted file answers to the original's name.
    assert _run_cli(root, "summarize", "guide.docx").returncode == 4
    assert _run_cli(root, "summarize", "protocol.pdf").returncode == 4


def test_cli_says_so_when_a_word_file_name_fits_two_converted_files(tmp_path: Path) -> None:
    root = _project(tmp_path, {"a/converted/protocol_0123abcd.md": PROTOCOL,
                               "b/converted/protocol_89abcdef.md": PROTOCOL})
    out = _run_cli(root, "summarize", "protocol.docx")
    assert out.returncode == 3
    assert "a/converted/protocol_0123abcd.md" in out.stdout
    assert "b/converted/protocol_89abcdef.md" in out.stdout


def test_cli_honours_graph_and_out(tmp_path: Path) -> None:
    root = _project(tmp_path, {"docs/guide.md": GUIDE})
    target = tmp_path / "elsewhere" / "summaries.json"
    out = _run_cli(tmp_path, "summarize", "--graph", str(_graph_path(root)), "--out", str(target))
    assert out.returncode == 0, out.stderr
    assert target.exists()
    assert not (root / "graphify-out" / SUMMARY_SIDECAR_NAME).exists()


def test_cli_with_a_file_name_prints_one_summary_and_writes_nothing(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING, "docs/guide.md": GUIDE})
    for name in ("guide.md", "docs/guide.md"):
        out = _run_cli(root, "summarize", name)
        assert out.returncode == 0, out.stderr
        assert out.stdout.splitlines() == [
            "Node: guide.md",
            "  Source:    docs/guide.md",
            '  Summary:   "Billing guide": sections Install, Usage.',
        ]
    assert not (root / "graphify-out" / SUMMARY_SIDECAR_NAME).exists()


def test_cli_with_a_file_that_has_nothing_to_summarize_says_so(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/__init__.py": "", "pkg/util.py": "def helper():\n    pass\n"})
    out = _run_cli(root, "summarize", "pkg/__init__.py")
    assert out.returncode == 0, out.stderr
    assert "  Summary:   (nothing to summarize in this file)" in out.stdout.splitlines()


def test_cli_with_a_name_that_is_not_a_file_points_at_its_file(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING})
    out = _run_cli(root, "summarize", "apply_discount()")
    assert out.returncode == 1
    assert "is not a file" in out.stderr and "pkg/billing.py" in out.stderr
    assert out.stdout == ""


def test_cli_with_an_unknown_name_exits_not_found(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING})
    out = _run_cli(root, "summarize", "no-such-file.md")
    assert out.returncode == 4
    assert "No node matching" in out.stdout


def test_cli_rejects_out_with_a_file_name(tmp_path: Path) -> None:
    root = _project(tmp_path, {"docs/guide.md": GUIDE})
    target = tmp_path / "summaries.json"
    out = _run_cli(root, "summarize", "guide.md", "--out", str(target))
    assert out.returncode == 2
    assert "cannot be used with a file name" in out.stderr
    assert not target.exists()


def _write_graph(folder: Path, nodes: list[dict]) -> Path:
    gp = folder / "graph.json"
    gp.write_text(json.dumps({"directed": True, "multigraph": False, "graph": {},
                              "nodes": nodes, "links": []}), encoding="utf-8")
    return gp


def test_empty_result_replaces_an_earlier_sidecar(tmp_path: Path) -> None:
    """Summaries written for an earlier graph must not outlive it."""
    root = _project(tmp_path, {"util.py": "def helper(x):\n    return x\n"})
    gp = _graph_path(root)
    sidecar = gp.parent / SUMMARY_SIDECAR_NAME
    write_summaries(_load_cli_graph(gp), sidecar, root)
    assert load_summaries(gp)

    path, summarized, file_nodes = write_summaries(nx.DiGraph(), sidecar, root)
    assert (summarized, file_nodes) == (0, 0)
    assert json.loads(sidecar.read_text(encoding="utf-8"))["nodes"] == {}
    assert load_summaries(gp) == {}

    # Where there was no sidecar, an empty result still creates nothing.
    fresh = tmp_path / "fresh" / SUMMARY_SIDECAR_NAME
    write_summaries(nx.DiGraph(), fresh, root)
    assert not fresh.exists()


def test_cli_clears_stale_summaries_and_says_so(tmp_path: Path) -> None:
    gp = _write_graph(tmp_path, [{"id": "f", "label": "a.py", "source_file": "a.py",
                                  "file_type": "code"}])
    sidecar = tmp_path / SUMMARY_SIDECAR_NAME
    sidecar.write_text(json.dumps({"version": 1, "nodes": {
        "f": {"source_file": "a.py", "summary": "Defines something that is gone."}}}),
        encoding="utf-8")
    out = _run_cli(tmp_path, "summarize", "--graph", str(gp))
    assert out.returncode == 0, out.stderr
    # One file node, with nothing to say: the message says that, not "no file nodes".
    assert "None of the 1 file nodes" in out.stdout and "cleared the earlier summaries" in out.stdout
    assert load_summaries(gp) == {}
    shown = _run_cli(tmp_path, "explain", "a.py", "--graph", str(gp))
    assert "Summary:" not in shown.stdout


_SILENT_FILE = {"id": "f", "label": "a.py", "source_file": "a.py", "file_type": "code"}
_NOT_A_FILE = {"id": "c", "label": "a concept"}


@pytest.mark.parametrize("nodes, earlier_sidecar, expected", [
    ([_NOT_A_FILE], False, "No file nodes to summarize in {gp}; nothing written."),
    ([_NOT_A_FILE], True, "No file nodes to summarize in {gp}; cleared the earlier summaries in {out}."),
    ([_SILENT_FILE], False,
     "None of the 1 file nodes in {gp} has anything to summarize; nothing written."),
    ([_SILENT_FILE], True,
     "None of the 1 file nodes in {gp} has anything to summarize; "
     "cleared the earlier summaries in {out}."),
])
def test_cli_says_what_happened_when_nothing_is_summarized(
        tmp_path: Path, nodes: list, earlier_sidecar: bool, expected: str) -> None:
    gp = _write_graph(tmp_path, nodes).resolve()
    sidecar = gp.parent / SUMMARY_SIDECAR_NAME
    if earlier_sidecar:
        sidecar.write_text(json.dumps({"version": 1, "nodes": {
            "old": {"source_file": "old.py", "summary": "Left over."}}}), encoding="utf-8")
    out = _run_cli(tmp_path, "summarize", "--graph", str(gp))
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == expected.format(gp=gp, out=sidecar)
    # Created only to clear an earlier one; never where there was none.
    assert sidecar.exists() == earlier_sidecar
    assert load_summaries(gp) == {}


def test_cli_out_cannot_be_the_graph_file(tmp_path: Path) -> None:
    root = _project(tmp_path, {"docs/guide.md": GUIDE})
    gp = _graph_path(root)
    before = gp.read_bytes()
    targets = [str(gp), "graphify-out/graph.json", "graphify-out/../graphify-out/graph.json"]
    try:
        (root / "alias.json").symlink_to(gp)
        targets.append("alias.json")
    except OSError:  # no permission to create links (Windows without developer mode)
        pass
    for target in targets:
        out = _run_cli(root, "summarize", "--out", target)
        assert out.returncode == 2, target
        assert "graph file itself" in out.stderr
    assert gp.read_bytes() == before
    assert not (gp.parent / SUMMARY_SIDECAR_NAME).exists()


def test_cli_missing_graph_exits_1(tmp_path: Path) -> None:
    out = _run_cli(tmp_path, "summarize", "--graph", str(tmp_path / "nope.json"))
    assert out.returncode == 1
    assert "graph file not found" in out.stderr


def test_cli_with_nothing_to_summarize_writes_nothing(tmp_path: Path) -> None:
    gp = tmp_path / "graph.json"
    gp.write_text(json.dumps({"directed": True, "multigraph": False, "graph": {},
                              "nodes": [{"id": "c", "label": "a concept"}], "links": []}),
                  encoding="utf-8")
    out = _run_cli(tmp_path, "summarize", "--graph", str(gp))
    assert out.returncode == 0, out.stderr
    assert "nothing written" in out.stdout
    assert not (tmp_path / SUMMARY_SIDECAR_NAME).exists()


def test_help_lists_summarize(tmp_path: Path) -> None:
    out = _run_cli(tmp_path, "--help")
    assert out.returncode == 0, out.stderr
    assert "  summarize" in out.stdout


def test_cli_help_shows_the_command_own_options(tmp_path: Path) -> None:
    """`graphify summarize --help` used to stop at the top-level help guard and
    print only "Run 'graphify --help' for full usage."."""
    for flag in ("--help", "-h"):
        out = _run_cli(tmp_path, "summarize", flag)
        assert out.returncode == 0, out.stderr
        assert "usage: graphify summarize" in out.stdout
        for option in ("--max-chars", "--out", "--backend", "--profile", "--pages",
                       "--dry-run", "--force"):
            assert option in out.stdout, option
    assert not (tmp_path / "graphify-out").exists()


def test_cli_out_elsewhere_says_explain_does_not_read_it(tmp_path: Path) -> None:
    root = _project(tmp_path, {"pkg/billing.py": BILLING})
    out = _run_cli(root, "summarize", "--out", str(tmp_path / "elsewhere.json"))
    assert out.returncode == 0, out.stderr
    assert "Note: graphify explain reads" in out.stdout
    # Naming the default file is not "elsewhere".
    default = _graph_path(root).parent / SUMMARY_SIDECAR_NAME
    out = _run_cli(root, "summarize", "--out", str(default))
    assert out.returncode == 0, out.stderr
    assert "Note:" not in out.stdout
