"""Markdown code-span mentions become heading --references--> symbol edges.

``extract_markdown``'s docstring promised ``heading --references--> other node``
for a backtick `Name`, but nothing implemented it: a docs corpus and its code
corpus shared no edge at all. Mentions now ride the ``raw_calls`` channel
(tagged ``language: "markdown"``) and the ``markdown_mentions`` language
resolver matches them against the merged corpus after the id-remap passes.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.markdown import _code_span_mention, extract_markdown
from graphify.markdown_resolution import _match_cited_file

_WIDGET_PY = '''\
class Widget:
    def render(self):
        return "w"


def helper():
    return Widget()
'''

_GADGET_PY = '''\
class Gadget:
    def render(self):
        return "g"


def helper():
    return Gadget()
'''

_GUIDE_MD = '''\
# Guide

Start with `Widget`; `str` and `print()` are built-ins.

## Rendering

`Widget` draws through `Widget.render()`; `helper()` is defined twice.

```python
print(Widget)
```

## Pinned

See `src/widget.py::Widget::render` and `src/gadget.py::helper`.
Also `../src/widget.py::Widget` and the missing `src/nowhere.py::Widget`.
'''


def _extract(tmp_path, files: dict[str, str]):
    for name, body in files.items():
        p = tmp_path / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    old = os.getcwd()
    try:
        os.chdir(tmp_path)
        return extract([Path(n) for n in files],
                       cache_root=tmp_path / ".cache", parallel=False)
    finally:
        os.chdir(old)


def _node(r, label, source_contains=""):
    return next(n for n in r["nodes"]
                if n["label"] == label and source_contains in str(n.get("source_file", "")))


def _references(r):
    return {(e["source"], e["target"]): e for e in r["edges"]
            if e["relation"] == "references"}


def test_code_span_mentions_are_classified():
    assert _code_span_mention("Widget") == (None, ["Widget"])
    assert _code_span_mention("render()") == (None, ["render"])
    assert _code_span_mention("pkg.sub.Widget") == (None, ["pkg", "sub", "Widget"])
    assert _code_span_mention("Widget.render()") == (None, ["Widget", "render"])
    # A file-like span with an unknown extension classifies as a mention and
    # is rejected at resolution, where `pyproject` matches no callable.
    assert _code_span_mention("pyproject.toml") == (None, ["pyproject", "toml"])
    pinned = ("src/widget.py", ["Widget", "render"])
    assert _code_span_mention("src/widget.py::Widget::render") == pinned
    assert _code_span_mention("src/widget.py::Widget::render()") == pinned
    # Files, commands, expressions and prose are not symbol mentions.
    for span in ("setup.py", "README.md", "notes.txt", "git revert", "x = 1", "a-b",
                 "--flag", "", "src/widget.py"):
        assert _code_span_mention(span) is None, span


def test_cited_file_matching():
    sources = {"src/mod.py", ".github/scripts/check.py", "lib/x.py", "vendor/lib/x.py",
               "docs/src/mod.py"}
    # Doc-relative first, then exact, then a unique segment-aligned suffix.
    assert _match_cited_file("src/mod.py", "docs/guide.md", sources) == "docs/src/mod.py"
    assert _match_cited_file("src/mod.py", "README.md", sources) == "src/mod.py"
    assert _match_cited_file("mod.py", "README.md", sources) is None
    assert _match_cited_file("scripts/check.py", "README.md", sources) == (
        ".github/scripts/check.py")
    # `./` and `../` are stripped as segments: a hidden directory keeps its dot.
    assert _match_cited_file(".github/scripts/check.py", "docs/guide.md", sources) == (
        ".github/scripts/check.py")
    assert _match_cited_file("./src/mod.py", "README.md", sources) == "src/mod.py"
    # The suffix form also names a root-level file.
    assert _match_cited_file("lib/x.py", "docs/guide.md", {"lib/x.py"}) == "lib/x.py"
    # An explicit relative cite resolves against the document only: escaping
    # the corpus never falls through to another copy of the file.
    assert _match_cited_file("../lib/x.py", "docs/guide.md", sources) == "lib/x.py"
    assert _match_cited_file("../lib/x.py", "README.md", sources) is None
    assert _match_cited_file("../../vendor/lib/x.py", "docs/guide.md", sources) is None


def test_extract_markdown_reports_mentions_as_markdown_raw_calls(tmp_path):
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir()
    doc.write_text(_GUIDE_MD)

    r = extract_markdown(doc)

    assert r["edges"] == [e for e in r["edges"] if e["relation"] == "contains"]
    calls = r["raw_calls"]
    assert calls and all(rc["language"] == "markdown" for rc in calls)
    assert all(rc["is_member_call"] is False for rc in calls)
    heading_ids = {n["label"]: n["id"] for n in r["nodes"]}
    owners = {(rc["context"], rc["caller_nid"]) for rc in calls}
    # Body prose belongs to the enclosing heading; the first paragraph to the H1.
    assert ("Widget", heading_ids["Guide"]) in owners
    assert ("Widget", heading_ids["Rendering"]) in owners
    dotted = next(rc for rc in calls if rc["context"] == "Widget.render()")
    assert (dotted["caller_nid"], dotted["callee"]) == (heading_ids["Rendering"], "render")
    pinned = next(rc for rc in calls if rc["context"] == "src/widget.py::Widget::render")
    assert (pinned["path"], pinned["qualifiers"], pinned["callee"]) == (
        "src/widget.py", ["Widget"], "render")
    assert pinned["caller_nid"] == heading_ids["Pinned"]
    assert pinned["source_location"] == "L15"
    # Fenced code is not prose: `print(Widget)` inside the block adds nothing.
    assert [rc for rc in calls if rc["source_location"] == "L10"] == []
    # One raw call per (owner, mention), however often the heading repeats it.
    assert len([rc for rc in calls if rc["callee"] == "Widget"
                and rc["caller_nid"] == heading_ids["Rendering"]]) == 1


def test_extract_markdown_heading_code_span_belongs_to_that_heading(tmp_path):
    doc = tmp_path / "api.md"
    doc.write_text("# API\n\n## `Widget`\n\nText.\n")

    r = extract_markdown(doc)

    (rc,) = r["raw_calls"]
    heading = next(n for n in r["nodes"] if n["label"] == "`Widget`")
    assert (rc["caller_nid"], rc["callee"], rc["path"] if "path" in rc else None) == (
        heading["id"], "Widget", None)


def test_mentions_resolve_to_references_edges_end_to_end(tmp_path):
    r = _extract(tmp_path, {
        "src/widget.py": _WIDGET_PY,
        "src/gadget.py": _GADGET_PY,
        "docs/guide.md": _GUIDE_MD,
    })

    refs = _references(r)
    guide = _node(r, "Guide")
    rendering = _node(r, "Rendering")
    pinned = _node(r, "Pinned")
    widget = _node(r, "Widget", "widget.py")
    widget_render = next(
        n for n in r["nodes"] if n["label"] == ".render()" and "widget" in n["id"])
    gadget_helper = _node(r, "helper()", "gadget.py")

    # Bare unique name: INFERRED reference from the citing heading.
    assert refs[(guide["id"], widget["id"])]["confidence"] == "INFERRED"
    assert refs[(guide["id"], widget["id"])]["confidence_score"] == 0.95
    assert (rendering["id"], widget["id"]) in refs
    # `render` is defined twice, but the qualifier in `Widget.render()` names
    # the owner, so the mention resolves; the bare `helper()` stays ambiguous.
    assert {t for (s, t) in refs if s == rendering["id"]} == {
        widget["id"], widget_render["id"]}
    assert refs[(rendering["id"], widget_render["id"])]["confidence"] == "INFERRED"
    # Path-qualified mentions are EXTRACTED and scoped to the cited file.
    assert refs[(pinned["id"], widget_render["id"])]["confidence"] == "EXTRACTED"
    assert refs[(pinned["id"], widget_render["id"])]["confidence_score"] == 1.0
    assert refs[(pinned["id"], gadget_helper["id"])]["confidence"] == "EXTRACTED"
    # `../src/widget.py::Widget` resolves relative to the document.
    assert (pinned["id"], widget["id"]) in refs
    # A cited file that is not in the corpus yields nothing.
    assert {t for (s, t) in refs if s == pinned["id"]} == {
        widget_render["id"], gadget_helper["id"], widget["id"]}
    # Built-ins never resolve, and no mention becomes a call.
    node_ids = {n["id"] for n in r["nodes"]}
    assert all(s in node_ids and t in node_ids for (s, t) in refs)
    doc_ids = {n["id"] for n in r["nodes"] if n.get("file_type") == "document"}
    assert not [e for e in r["edges"]
                if e["relation"] in ("calls", "indirect_call") and e["source"] in doc_ids]


def test_ambiguous_bare_name_yields_no_edge(tmp_path):
    r = _extract(tmp_path, {
        "a/thing.py": "class Thing:\n    pass\n",
        "b/thing.py": "class Thing:\n    pass\n",
        "notes.md": "# Notes\n\nUse `Thing`.\n",
    })

    notes = _node(r, "Notes")
    assert {t for (s, t) in _references(r) if s == notes["id"]} == set()


def test_dotted_mentions_need_qualifier_evidence(tmp_path):
    r = _extract(tmp_path, {
        "src/widget.py": _WIDGET_PY + "\n\ndef sleep():\n    pass\n",
        "src/gadget.py": _GADGET_PY + "\n\ndef toml():\n    pass\n",
        "docs/notes.md": (
            "# Notes\n\n"
            "`time.sleep` and `pyproject.toml` are not this repo's sleep or toml.\n"
            "`widget.Widget`, `src.gadget.Gadget` and `Widget.render` are.\n"
            "`Gadget.helper` is not: `helper` is not owned by `Gadget`.\n"
        ),
    })

    notes = _node(r, "Notes")
    cited = {t for (s, t) in _references(r) if s == notes["id"]}
    widget = _node(r, "Widget", "widget.py")
    gadget = _node(r, "Gadget", "gadget.py")
    widget_render = next(
        n for n in r["nodes"] if n["label"] == ".render()" and "widget" in n["id"])
    assert cited == {widget["id"], gadget["id"], widget_render["id"]}


def test_mentions_survive_a_rebuild_over_an_existing_graph(tmp_path):
    """The watch reconcile owns authored ``[link](file)`` edges, not mentions.

    A rebuild over an existing graph re-parses the Markdown corpus and prunes
    any ``references`` edge it did not author; a code-span mention targets a
    code symbol, never a file, so it must survive a no-change rebuild and the
    incremental rebuilds of either side.
    """
    from graphify.watch import _rebuild_code

    corpus = tmp_path / "corpus"
    corpus.mkdir()
    (corpus / "widget.py").write_text(_WIDGET_PY)
    doc = corpus / "doc.md"
    doc.write_text("# Doc\n\n## Usage\n\nBuild a `Widget`.\n")
    graph_path = corpus / "graphify-out" / "graph.json"

    def mention_edges():
        links = json.loads(graph_path.read_text(encoding="utf-8"))["links"]
        return {(e["source"], e["target"]) for e in links
                if e.get("relation") == "references" and e.get("confidence_score")}

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    expected = mention_edges()
    assert len(expected) == 1

    assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
    assert mention_edges() == expected, "no-change rebuild"

    doc.write_text(doc.read_text() + "\nStill a `Widget`.\n")
    assert _rebuild_code(corpus, changed_paths=[doc], no_cluster=True,
                         acquire_lock=False) is True
    assert mention_edges() == expected, "document re-extracted"

    (corpus / "widget.py").write_text(_WIDGET_PY + "\n\ndef extra():\n    pass\n")
    assert _rebuild_code(corpus, changed_paths=[corpus / "widget.py"], no_cluster=True,
                         acquire_lock=False) is True
    assert mention_edges() == expected, "code re-extracted"


def test_mentions_survive_the_extraction_cache(tmp_path):
    files = {"src/widget.py": _WIDGET_PY, "docs/guide.md": _GUIDE_MD}
    first = _extract(tmp_path, files)
    second = _extract(tmp_path, files)

    def _pairs(r):
        return {(s, t) for (s, t) in _references(r)}

    assert _pairs(first) == _pairs(second)
    guide = _node(second, "Guide")
    widget = _node(second, "Widget", "widget.py")
    assert (guide["id"], widget["id"]) in _pairs(second)
