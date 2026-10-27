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
import subprocess
import sys
import textwrap
from pathlib import Path

from graphify.extract import extract
from graphify.extractors.markdown import _code_span_mention, extract_markdown
from graphify.markdown_resolution import _match_cited_file


def _run_isolated(script: str, *args: str) -> subprocess.CompletedProcess:
    """Run *script* in a fresh interpreter so in-process global state cannot leak in.

    ``_rebuild_code`` touches module-level globals: the cache stat index
    (#3989) and the active scan root.  In the full suite a prior test's root
    can be served to a later rebuild, dropping resolver-minted markdown
    reference edges.  A subprocess starts from a clean slate, matching the
    isolated run the test sees when executed on its own.
    """
    repo_root = Path(__file__).resolve().parent.parent
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(script), *args],
        cwd=str(repo_root),
        capture_output=True,
        text=True,
    )

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
    # A source-file span classifies with an empty symbol chain, so resolution
    # can record it as file evidence (#4804).
    assert _code_span_mention("setup.py") == ("setup.py", [])
    assert _code_span_mention("src/widget.py") == ("src/widget.py", [])
    # A *document* span is not evidence (only code files are), so it is not a
    # mention at all.
    assert _code_span_mention("README.md") is None
    assert _code_span_mention("docs/notes.mdx") is None
    # Commands, expressions and prose are not symbol mentions.
    for span in ("git revert", "x = 1", "a-b", "--flag", ""):
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


def test_bare_lowercase_word_does_not_link_to_an_unrelated_method(tmp_path):
    """`redis` the server is prose, not a reference to whichever method is named redis (#4609)."""
    r = _extract(tmp_path, {
        "cache.py": "class Cache:\n    def redis(self):\n        return 'connection'\n",
        "README.md": "# Queue\n\nJobs run on `redis` (the server, not our code).\n",
    })

    queue = _node(r, "Queue")
    assert {t for (s, t) in _references(r) if s == queue["id"]} == set()


def test_bare_method_mention_survives_when_the_document_cites_its_class(tmp_path):
    """`successWithWarnings` next to `HandlerResult` is a real reference (#4609)."""
    r = _extract(tmp_path, {
        "handler.py": "class HandlerResult:\n    def successWithWarnings(self):\n        return 1\n",
        "notes.md": "# Notes\n\n`HandlerResult` returns `successWithWarnings`.\n",
    })

    notes = _node(r, "Notes")
    method = _node(r, ".successWithWarnings()")
    assert (notes["id"], method["id"]) in _references(r)


def test_bare_method_with_parentheses_still_resolves(tmp_path):
    """A trailing () is explicit evidence, so the owner does not have to be cited (#4609)."""
    r = _extract(tmp_path, {
        "cache.py": "class Cache:\n    def redis(self):\n        return 'connection'\n",
        "notes.md": "# Notes\n\nCall `redis()` on the cache.\n",
    })

    notes = _node(r, "Notes")
    method = _node(r, ".redis()")
    assert (notes["id"], method["id"]) in _references(r)


def test_bare_lowercase_word_does_not_link_to_an_unrelated_function(tmp_path):
    """`token` the query parameter is prose, not a reference to token() in an unrelated JS file (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) {\n  return name;\n}\n",
        "docs/feed.md": "# Quote feed\n\nThe client sends the API key as the `token` query parameter.\n",
    })

    feed = _node(r, "Quote feed")
    assert {t for (s, t) in _references(r) if s == feed["id"]} == set()


def test_bare_function_mention_survives_when_the_document_cites_another_symbol_from_its_file(tmp_path):
    """`token` next to `palette()` from the same file is a real reference (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": (
            "export function palette() { return 'dark'; }\n"
            "export function token(name) { return name; }\n"
        ),
        "docs/feed.md": "# Quote feed\n\nWalks through charts, mentions `palette()` and then `token`.\n",
    })

    feed = _node(r, "Quote feed")
    token = _node(r, "token()", "charts.js")
    palette = _node(r, "palette()", "charts.js")
    assert (feed["id"], token["id"]) in _references(r)
    assert (feed["id"], palette["id"]) in _references(r)


def test_bare_function_with_parentheses_still_resolves(tmp_path):
    """A trailing () is explicit evidence, so defining file does not need another symbol cited (#4804)."""
    r = _extract(tmp_path, {
        "deploy.py": "def deploy():\n    pass\n",
        "notes.md": "# Notes\n\nRun `deploy()` after the tests.\n",
    })

    notes = _node(r, "Notes")
    deploy = _node(r, "deploy()", "deploy.py")
    assert (notes["id"], deploy["id"]) in _references(r)


def test_bare_function_survives_when_a_class_in_its_file_is_cited(tmp_path):
    """`deploy` next to `Deployer` in the same file is a real reference (#4804)."""
    r = _extract(tmp_path, {
        "deploy.py": "class Deployer:\n    pass\n\ndef deploy():\n    pass\n",
        "notes.md": "# Notes\n\nUse `Deployer` then run `deploy`.\n",
    })

    notes = _node(r, "Notes")
    deploy = _node(r, "deploy()", "deploy.py")
    assert (notes["id"], deploy["id"]) in _references(r)


def test_function_evidence_cited_in_another_document_does_not_count(tmp_path):
    """The file-symbol evidence is per document: one doc's mention cannot license another's (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": (
            "export function palette() { return 'dark'; }\n"
            "export function token(name) { return name; }\n"
        ),
        "a.md": "# A\n\nUses `palette()`.\n",
        "b.md": "# B\n\nSends `token`.\n",
    })

    b = _node(r, "B")
    assert {t for (s, t) in _references(r) if s == b["id"]} == set()


def test_owner_cited_in_another_document_does_not_count(tmp_path):
    """The owner evidence is per document: one doc's mention cannot license another's (#4609)."""
    r = _extract(tmp_path, {
        "handler.py": "class HandlerResult:\n    def successWithWarnings(self):\n        return 1\n",
        "a.md": "# A\n\n`HandlerResult` is the result type.\n",
        "b.md": "# B\n\nReads `successWithWarnings`.\n",
    })

    b = _node(r, "B")
    assert {t for (s, t) in _references(r) if s == b["id"]} == set()


def test_owner_evidence_survives_an_edge_that_already_exists():
    """A mention whose edge is already in the graph still counts as citing its target.

    The resolver skips an edge that is already there, but the document has still
    cited that symbol, so the evidence must stay on record for a later method
    mention in the same document (#4609, review finding on the PR).
    """
    from graphify.markdown_resolution import resolve_markdown_mentions

    per_file = [{"raw_calls": [
        {"caller_nid": "doc_notes", "callee": "HandlerResult", "language": "markdown",
         "context": "HandlerResult", "source_file": "notes.md", "source_location": "L3"},
        {"caller_nid": "doc_notes", "callee": "successWithWarnings", "language": "markdown",
         "context": "successWithWarnings", "source_file": "notes.md", "source_location": "L3"},
    ]}]
    nodes = [
        {"id": "doc_notes", "label": "Notes", "file_type": "document",
         "source_file": "notes.md"},
        {"id": "handler_handlerresult", "label": "HandlerResult", "file_type": "code",
         "_callable": True, "_callable_class": True, "source_file": "handler.py"},
        {"id": "handler_handlerresult_successwithwarnings", "label": ".successWithWarnings()",
         "file_type": "code", "_callable": True, "source_file": "handler.py"},
    ]
    edges = [
        {"source": "handler_handlerresult",
         "target": "handler_handlerresult_successwithwarnings", "relation": "method"},
        # The class reference edge is already in the graph.
        {"source": "doc_notes", "target": "handler_handlerresult", "relation": "references"},
    ]

    resolve_markdown_mentions(per_file, nodes, edges)

    assert ("doc_notes", "handler_handlerresult_successwithwarnings") in {
        (e["source"], e["target"]) for e in edges if e.get("relation") == "references"}


def test_bare_function_survives_when_file_is_cited(tmp_path):
    """Naming the defining file (span or link) licenses a bare function (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/span.md": "# Span\n\n- `web/charts.js` — uses `token` to read styles.\n",
        "docs/link.md": "# Link\n\nSee [charts](../web/charts.js). Uses `token`.\n",
    })

    token = _node(r, "token()", "charts.js")
    span_node = _node(r, "Span")
    link_node = _node(r, "Link")
    refs = _references(r)
    assert (span_node["id"], token["id"]) in refs
    assert (link_node["id"], token["id"]) in refs


def test_two_bare_functions_from_one_file_with_no_other_citation_yield_no_edge(tmp_path):
    """Two bare prose-like names cannot circularly license each other without evidence (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": (
            "export function palette() { return 'dark'; }\n"
            "export function token(name) { return name; }\n"
        ),
        "notes.md": "# Notes\n\nCalls `palette` then `token`.\n",
    })

    notes = _node(r, "Notes")
    assert {t for (s, t) in _references(r) if s == notes["id"]} == set()


def test_bare_function_resolves_when_class_is_cited_after_it_in_document(tmp_path):
    """Pass 2a/2c ordering ensures license is document-scoped, not reading-order dependent (#4804)."""
    r = _extract(tmp_path, {
        "deploy.py": "class Deployer:\n    pass\n\ndef deploy():\n    pass\n",
        "notes.md": "# Notes\n\nRun `deploy` first. Then use `Deployer`.\n",
    })

    notes = _node(r, "Notes")
    deploy = _node(r, "deploy()", "deploy.py")
    deployer = _node(r, "Deployer", "deploy.py")
    refs = _references(r)
    assert (notes["id"], deploy["id"]) in refs
    assert (notes["id"], deployer["id"]) in refs


def test_bare_function_survives_with_path_qualified_evidence(tmp_path):
    """A path-qualified class citation licenses a bare function from that file (#4804)."""
    r = _extract(tmp_path, {
        "deploy.py": "class Deployer:\n    pass\n\ndef deploy():\n    pass\n",
        "notes.md": "# Notes\n\nSee `deploy.py::Deployer`. Then run `deploy`.\n",
    })

    notes = _node(r, "Notes")
    deploy = _node(r, "deploy()", "deploy.py")
    assert (notes["id"], deploy["id"]) in _references(r)


def test_target_with_no_source_file_is_safely_skipped():
    """A callable target without a source_file sentinel is skipped without error (#4804)."""
    from graphify.markdown_resolution import resolve_markdown_mentions

    per_file = [{"raw_calls": [
        {"caller_nid": "doc_notes", "callee": "sourceless", "language": "markdown",
         "context": "sourceless", "source_file": "notes.md", "source_location": "L1"},
    ]}]
    nodes = [
        {"id": "doc_notes", "label": "Notes", "file_type": "document", "source_file": "notes.md"},
        {"id": "code_sourceless", "label": "sourceless()", "file_type": "code",
         "_callable": True, "source_file": ""},
    ]
    edges: list[dict] = []
    resolve_markdown_mentions(per_file, nodes, edges)
    assert not [e for e in edges if e.get("relation") == "references"]


def test_nested_class_resolves_standalone(tmp_path):
    """A nested class is a class, not a method; it resolves without outer class cited (#4804)."""
    r = _extract(tmp_path, {
        "tree.py": "class Outer:\n    class Inner:\n        pass\n",
        "notes.md": "# Notes\n\nUse `Inner`.\n",
    })

    notes = _node(r, "Notes")
    inner = _node(r, "Inner", "tree.py")
    assert (notes["id"], inner["id"]) in _references(r)


def test_bare_function_with_snake_case_or_camel_case_resolves_without_file_citation(tmp_path):
    """Distinct code identifiers (snake_case or camelCase) resolve standalone (#4804)."""
    r = _extract(tmp_path, {
        "build.py": (
            "def deduplicate_by_label():\n    pass\n\n"
            "def buildFromJson():\n    pass\n"
        ),
        "notes.md": (
            "# Notes\n\n"
            "Calls `deduplicate_by_label` and `buildFromJson`.\n"
        ),
    })

    notes = _node(r, "Notes")
    dedup = _node(r, "deduplicate_by_label()", "build.py")
    build_json = _node(r, "buildFromJson()", "build.py")
    refs = _references(r)
    assert (notes["id"], dedup["id"]) in refs
    assert (notes["id"], build_json["id"]) in refs


def test_bare_function_mention_survives_when_symbol_itself_cited_with_parentheses(tmp_path):
    """An explicit () mention under h1 licenses a bare mention under h2 (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function palette() { return 'dark'; }\n",
        "docs/guide.md": (
            "# Overview\n\n"
            "Call `palette()` to configure theme.\n\n"
            "## Details\n\n"
            "Reads `palette` for current colors.\n"
        ),
    })

    overview = _node(r, "Overview")
    details = _node(r, "Details")
    palette = _node(r, "palette()", "charts.js")
    refs = _references(r)
    assert (overview["id"], palette["id"]) in refs
    assert (details["id"], palette["id"]) in refs


def test_link_to_scanned_source_file_is_a_reference_and_licenses_bare_mentions(tmp_path):
    """A link to a scanned source file is a doc->file edge AND licenses a bare mention (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/guide.md": "# Guide\n\nSee [charts](../web/charts.js). Sends `token`.\n",
    })

    guide = _node(r, "Guide")
    token = _node(r, "token()", "charts.js")
    charts_file = _node(r, "charts.js", "charts.js")
    page = _node(r, "guide.md")
    refs = _references(r)
    assert (guide["id"], token["id"]) in refs
    # The link itself is a real reference from the page to the scanned file
    # node — EXTRACTED, since the document names the file verbatim.
    assert refs[(page["id"], charts_file["id"])]["confidence"] == "EXTRACTED"


def test_extract_markdown_records_a_source_file_link_as_a_citation(tmp_path):
    """The citation rides the markdown raw-call channel with only `path`, so the
    corpus-aware resolver can decide edge vs evidence-only (#4804)."""
    doc = tmp_path / "docs" / "guide.md"
    doc.parent.mkdir()
    doc.write_text("# Guide\n\nSee [charts](../web/charts.js) and `token`.\n")

    r = extract_markdown(doc)

    assert all(e["relation"] == "contains" for e in r["edges"])
    page = next(n for n in r["nodes"] if n.get("node_kind") == "page")
    citations = [rc for rc in r["raw_calls"] if rc["callee"] == "" and rc.get("path")]
    assert [(rc["caller_nid"], rc["path"]) for rc in citations] == [
        (page["id"], "../web/charts.js")]
    assert all(rc.get("file_link") for rc in citations)
    # The symbol mention still travels as a normal markdown raw call.
    assert [rc["callee"] for rc in r["raw_calls"] if rc.get("path") is None] == ["token"]


def test_link_to_unscanned_source_file_yields_no_edge_or_phantom(tmp_path):
    """A link to a source file outside the corpus is evidence only, never a dangling edge."""
    outside = tmp_path / "outside" / "script.py"
    outside.parent.mkdir()
    outside.write_text("def run():\n    pass\n")
    r = _extract(tmp_path, {"docs/guide.md": "# Guide\n\nSee [script](../outside/script.py).\n"})

    assert r["edges"] == [e for e in r["edges"] if e["relation"] == "contains"]


def test_wikilink_to_scanned_source_file_yields_only_a_file_edge(tmp_path):
    """An Obsidian wikilink naming a scanned source file is a page->file reference."""
    r = _extract(tmp_path, {
        "setup.py": "def setup():\n    pass\n",
        "docs/guide.md": "# Guide\n\nSee [[setup.py]].\n",
    })

    page = _node(r, "guide.md")
    setup_file = _node(r, "setup.py", "setup.py")
    assert set(_references(r)) == {(page["id"], setup_file["id"])}


def test_single_word_pascal_case_function_resolves_standalone(tmp_path):
    """An exported Go/C#/Swift entry point (`Serve`) is a distinct identifier, not prose (#4804)."""
    r = _extract(tmp_path, {
        "worker.go": "package worker\n\nfunc Serve() {}\n",
        "docs/guide.md": "# Guide\n\n`Serve` starts the server.\n",
    })

    guide = _node(r, "Guide")
    serve = _node(r, "Serve()", "worker.go")
    assert (guide["id"], serve["id"]) in _references(r)


def test_single_word_lowercase_function_still_needs_evidence(tmp_path):
    """The PascalCase exemption does not loosen the prose-like test (`serve`)."""
    r = _extract(tmp_path, {
        "worker.go": "package worker\n\nfunc serve() {}\n",
        "docs/guide.md": "# Guide\n\n`serve` starts the server.\n",
    })

    guide = _node(r, "Guide")
    assert {t for (s, t) in _references(r) if s == guide["id"]} == set()


def test_file_citation_evidence_survives_a_rebuild(tmp_path):
    """A source-file link's citation comes from the cached fragment, so a rebuild keeps the edge.

    Runs in a subprocess: ``_rebuild_code`` shares the cache stat index and the
    active scan root as process globals, and a prior test in the full suite can
    leave a root bound that makes a partial rebuild drop the reference edges.
    A fresh interpreter gives the test the same clean slate it has in isolation.
    """
    corpus = tmp_path / "corpus"
    (corpus / "docs").mkdir(parents=True)
    (corpus / "web").mkdir()
    (corpus / "web" / "charts.js").write_text(
        "export function token(name) { return name; }\n")
    doc = corpus / "docs" / "guide.md"
    doc.write_text("# Guide\n\nSee [charts](../web/charts.js). Sends `token`.\n")
    result_file = tmp_path / "result.json"

    script = '''
        import json, sys
        from pathlib import Path
        from graphify.watch import _rebuild_code

        corpus = Path(sys.argv[1])
        result_file = Path(sys.argv[2])
        doc = corpus / "docs" / "guide.md"
        charts = corpus / "web" / "charts.js"
        graph_path = corpus / "graphify-out" / "graph.json"

        def reference_edges():
            links = json.loads(graph_path.read_text(encoding="utf-8"))["links"]
            return sorted((e["source"], e["target"]) for e in links
                          if e.get("relation") == "references")

        assert _rebuild_code(corpus, no_cluster=True, acquire_lock=False) is True
        first = reference_edges()

        doc.write_text(doc.read_text() + "\\nStill `token`.\\n")
        assert _rebuild_code(corpus, changed_paths=[doc], no_cluster=True,
                             acquire_lock=False) is True
        second = reference_edges()

        charts.write_text(
            "export function token(name) { return name; }\\n"
            "export function palette() { return 'dark'; }\\n")
        assert _rebuild_code(corpus, changed_paths=[charts], no_cluster=True,
                             acquire_lock=False) is True
        third = reference_edges()

        result_file.write_text(
            json.dumps({"first": first, "second": second, "third": third}),
            encoding="utf-8")
    '''
    completed = _run_isolated(script, str(corpus), str(result_file))
    assert completed.returncode == 0, completed.stderr[-2000:]

    payload = json.loads(result_file.read_text(encoding="utf-8"))
    expected = payload["first"]
    # Two edges: the doc->file link reference and the licensed mention edge.
    assert len(expected) == 2
    assert payload["second"] == expected, "document re-extracted"
    assert payload["third"] == expected, "code re-extracted"


def test_bare_function_mention_in_a_sibling_section_needs_its_own_evidence(tmp_path):
    """Evidence is section-scoped: a citation in one h1 does not license a sibling h1 (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": (
            "export function palette() { return 'dark'; }\n"
            "export function token(name) { return name; }\n"
        ),
        "docs/guide.md": (
            "# Charts\n\n"
            "`palette()` configures the theme.\n\n"
            "# Token notes\n\n"
            "The API key travels as the `token` query parameter.\n"
        ),
    })

    token_notes = _node(r, "Token notes")
    charts = _node(r, "Charts")
    token = _node(r, "token()", "charts.js")
    palette = _node(r, "palette()", "charts.js")
    refs = _references(r)
    # The explicit () citation resolves on its own.
    assert (charts["id"], palette["id"]) in refs
    # The sibling section's prose word gets no license from it...
    assert {t for (s, t) in refs if s == token_notes["id"]} == set()
    # ...but a nested section would: evidence at h1 licenses its h2 children.
    r = _extract(tmp_path, {
        "web/charts.js": (
            "export function palette() { return 'dark'; }\n"
            "export function token(name) { return name; }\n"
        ),
        "docs/guide.md": (
            "# Charts\n\n"
            "`palette()` configures the theme.\n\n"
            "## Colors\n\n"
            "Reads `palette` for the current scheme.\n"
        ),
    })
    colors = _node(r, "Colors")
    assert (colors["id"], palette["id"]) in _references(r)


def test_pascal_case_in_a_lowercase_convention_language_needs_evidence(tmp_path):
    """`Token` in Python is prose as often as not; only PascalCase-export languages skip the test (#4804)."""
    r = _extract(tmp_path, {
        "build.py": "def Token():\n    pass\n",
        "notes.md": "# Notes\n\n`Token` builds the response.\n",
    })

    notes = _node(r, "Notes")
    assert {t for (s, t) in _references(r) if s == notes["id"]} == set()

    # With the defining file cited, the same mention resolves.
    r = _extract(tmp_path, {
        "build.py": "def Token():\n    pass\n",
        "notes.md": "# Notes\n\nSee `build.py`. `Token` builds the response.\n",
    })
    notes = _node(r, "Notes")
    token = _node(r, "Token()", "build.py")
    assert (notes["id"], token["id"]) in _references(r)


def test_file_span_is_evidence_but_not_a_doc_file_edge(tmp_path):
    """A source-file code span licenses bare mentions; only a link is a doc->file reference (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/span.md": "# Span\n\n- `web/charts.js` — uses `token` to read styles.\n",
    })

    span_node = _node(r, "Span")
    token = _node(r, "token()", "charts.js")
    refs = _references(r)
    assert (span_node["id"], token["id"]) in refs
    assert len(refs) == 1, "a span is evidence, not a link: no doc->file edge"


def test_cited_file_fallback_respects_explicit_relative_discipline():
    """The suffix fallback fires only under detected path-form mixing (#4804).

    Runs in a subprocess so ``_active_scan_root()`` is None: the resolver's
    fallback consults that process global, and a root leaked by an earlier test
    would prefix-mismatch the synthetic ``/repo`` path and return None.
    """
    script = '''
        import json
        from graphify.markdown_resolution import _match_cited_file_any_form

        sources = {"web/charts.js"}
        # Uniform path forms: an explicit ../ cite resolves against the citing
        # document's directory only — even when the doc sits outside the corpus
        # root and a corpus file shares the tail (#4804's discipline).
        uniform = _match_cited_file_any_form(
            "../web/charts.js", "/other/docs/guide.md", sources,
            form_mismatch=False)
        # An absolute citing document against a relative corpus is exactly the
        # partial-rebuild mixing the fallback exists for.
        mixed = _match_cited_file_any_form(
            "../web/charts.js", "/repo/docs/guide.md", sources,
            form_mismatch=True)
        print("===RESULT===" + json.dumps({"uniform": uniform, "mixed": mixed}))
    '''
    completed = _run_isolated(script)
    assert completed.returncode == 0, completed.stderr[-2000:]
    line = next(l for l in completed.stdout.splitlines()
                if l.startswith("===RESULT==="))
    payload = json.loads(line[len("===RESULT==="):])
    assert payload["uniform"] is None
    assert payload["mixed"] == "web/charts.js"


def test_escaping_citation_does_not_match_in_corpus_file():
    """An explicit cite escaping the scan root does not match an in-corpus file."""
    from graphify.markdown_resolution import _match_cited_file_any_form

    sources = {"web/charts.js"}
    assert _match_cited_file_any_form(
        "../../outside/web/charts.js", "/repo/docs/guide.md", sources,
        form_mismatch=True, scan_root="/repo",
    ) is None


def test_source_file_link_in_heading_does_not_license_sibling_heading(tmp_path):
    """A source-file link licenses mentions in its own section, not sibling sections."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/guide.md": (
            "# Charts\n\n"
            "See [charts](../web/charts.js).\n\n"
            "# Authentication\n\n"
            "Sends `token` for auth.\n"
        ),
    })

    auth = _node(r, "Authentication")
    token = _node(r, "token()", "charts.js")
    assert (auth["id"], token["id"]) not in _references(r)


def test_missing_source_link_does_not_reference_other_files(tmp_path):
    """An inline Markdown link to a missing path does not fall back to unrelated files."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/guide.md": "# Guide\n\nSee [charts](web/charts.js).\n",
    })

    page = _node(r, "guide.md")
    charts_file = _node(r, "charts.js", "charts.js")
    assert (page["id"], charts_file["id"]) not in _references(r)


def test_reference_style_use_licenses_its_own_section(tmp_path):
    """A reference-style use `[charts][source]` licenses a bare mention in its own section,
    not the section where the definition sits (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/guide.md": (
            "# Charts\n\n"
            "See [charts][source]. Uses `token`.\n\n"
            "# Authentication\n\n"
            "[source]: ../web/charts.js\n"
        ),
    })

    charts = _node(r, "Charts")
    token = _node(r, "token()", "charts.js")
    charts_file = _node(r, "charts.js", "charts.js")
    page = _node(r, "guide.md")
    refs = _references(r)
    # The use's section licenses the bare mention.
    assert (charts["id"], token["id"]) in refs
    # The link itself is a doc->file edge from the page.
    assert (page["id"], charts_file["id"]) in refs


def test_reference_definition_section_does_not_license_bare_mention(tmp_path):
    """A definition's own section does not inherit citation evidence from the
    definition line (#4804 regression)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/guide.md": (
            "# Charts\n\n"
            "Uses `token`.\n\n"
            "# Authentication\n\n"
            "Sends `token` for auth.\n\n"
            "[source]: ../web/charts.js\n"
        ),
    })

    auth = _node(r, "Authentication")
    token = _node(r, "token()", "charts.js")
    assert (auth["id"], token["id"]) not in _references(r)


def test_reference_style_use_shared_by_multiple_sections(tmp_path):
    """Each use of a shared definition licenses its own section (#4804)."""
    r = _extract(tmp_path, {
        "web/charts.js": "export function token(name) { return name; }\n",
        "docs/guide.md": (
            "# Charts\n\n"
            "See [charts][source]. Uses `token`.\n\n"
            "# Token notes\n\n"
            "Also [charts][source]. Sends `token`.\n\n"
            "[source]: ../web/charts.js\n"
        ),
    })

    charts = _node(r, "Charts")
    token_notes = _node(r, "Token notes")
    token = _node(r, "token()", "charts.js")
    refs = _references(r)
    assert (charts["id"], token["id"]) in refs
    assert (token_notes["id"], token["id"]) in refs
