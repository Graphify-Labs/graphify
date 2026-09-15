"""Markdown code-span mentions become heading --references--> symbol edges.

``extract_markdown``'s docstring promised ``heading --references--> other node``
for a backtick `Name`, but nothing implemented it: a docs corpus and its code
corpus shared no edge at all. Mentions now ride the ``raw_calls`` channel
(tagged ``language: "markdown"``) and the ``markdown_mentions`` language
resolver matches them against the merged corpus after the id-remap passes.
"""
from __future__ import annotations

import os
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.markdown import _code_span_mention, extract_markdown

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
    assert _code_span_mention("pkg.sub.Widget") == (None, ["Widget"])
    pinned = ("src/widget.py", ["Widget", "render"])
    assert _code_span_mention("src/widget.py::Widget::render") == pinned
    assert _code_span_mention("src/widget.py::Widget::render()") == pinned
    # Files, commands, expressions and prose are not symbol mentions.
    for span in ("setup.py", "git revert", "x = 1", "a-b", "--flag", "", "src/widget.py"):
        assert _code_span_mention(span) is None, span


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
    # Dotted `Widget.render()` resolves by its last segment: `render` is
    # ambiguous (two classes define it), so no edge; same for `helper()`.
    assert {t for (s, t) in refs if s == rendering["id"]} == {widget["id"]}
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
