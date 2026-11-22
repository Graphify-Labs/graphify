"""Structural ``href`` / ``src`` references from HTML pages (#5226).

HTML is a document, so the AST-only pass used to skip it. A page now yields a
page node plus a ``references`` edge for every literal, existing, scanned
relative target; everything else (remote URLs, anchors, routes, dynamic
strings, missing files, assets, paths outside the scan root) yields no edge.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from graphify.detect import FileType, classify_file
from graphify.extract import collect_files, extract
from graphify.extractors import html as html_mod


def _run(tmp_path: Path, files: dict[str, str], *, scan: str = ""):
    """Write *files* under ``tmp_path/repo``; extract everything under ``scan``."""
    root = tmp_path / "repo"
    for name, text in files.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    scan_root = root / scan if scan else root
    paths = collect_files(scan_root, root=scan_root)
    data = extract(paths, root=scan_root, cache_root=tmp_path / "cache", parallel=False)
    file_of = {n["id"]: n.get("source_file") for n in data["nodes"]}
    # A target that is not a node stays visible (as `<dangling ...>`), so a
    # "gives no edge" assertion also fails on a dangling reference.
    refs = sorted(
        (file_of[e["source"]], file_of.get(e["target"], f"<dangling {e['target']}>"),
         e.get("source_location"))
        for e in data["edges"]
        if e["relation"] == "references" and e["source"] in file_of
    )
    return refs, data


def _targets(refs, page: str) -> list[str]:
    return [t for s, t, _ in refs if s == page]


def _raw_edges(tmp_path: Path, name: str) -> list[dict]:
    """What the extractor itself emits for ``tmp_path/repo/<name>``, before any pass."""
    return html_mod.extract_html(tmp_path / "repo" / name)["edges"]


_JS = {"scripts/app.js": "function sample() { return 1; }\n"}
_DETAILS = {"pages/details.html": "<h1>Details</h1>\n"}


def test_page_links_and_script_sources_become_references(tmp_path):
    refs, _ = _run(tmp_path, {
        "pages/index.html": (
            '<a href="./details.html">Details</a>\n'
            '<script src="../scripts/app.js"></script>\n'
        ),
        **_DETAILS, **_JS,
    })
    assert refs == [
        ("pages/index.html", "pages/details.html", "L1"),
        ("pages/index.html", "scripts/app.js", "L2"),
    ]


def test_html_is_still_classified_as_a_document(tmp_path):
    page = tmp_path / "index.html"
    page.write_text("<h1>x</h1>")
    assert classify_file(page) == FileType.DOCUMENT


def test_page_node_is_emitted_even_without_references(tmp_path):
    _, data = _run(tmp_path, {"only.html": "<p>hello</p>\n"})
    pages = [n for n in data["nodes"] if n.get("source_file") == "only.html"]
    assert len(pages) == 1
    assert pages[0]["file_type"] == "document" and pages[0]["node_kind"] == "page"


@pytest.mark.parametrize("value", [
    "https://example.com/details.html",
    "http://example.com/details.html",
    "//cdn.example.com/details.html",
    "mailto:a@b.c",
    "tel:+100",
    "javascript:void(0)",
    "ftp:details.html",
    "data:text/html,x",
    "#details",
    "",
    "/details.html",
    "missing.html",
    "{{ url_for('details') }}",
    "{% static 'details.html' %}",
    "<%= details %>",
    "${details}.html",
    "$details.html",
    "@Url.Content(\"details.html\")",
    "..\\pages\\details.html",
])
def test_non_literal_or_non_local_targets_give_no_edge(tmp_path, value):
    # A value that itself holds a double quote (the Razor case) needs a
    # single-quoted attribute, or the markup is malformed and nothing is tested.
    quote = "'" if '"' in value else '"'
    refs, _ = _run(tmp_path, {
        "index.html": f"<a href={quote}{value}{quote}>x</a>\n",
        "details.html": "<h1>d</h1>\n",
    })
    assert _targets(refs, "index.html") == []
    assert _raw_edges(tmp_path, "index.html") == []


def test_fragment_and_query_are_stripped(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": '<a href="details.html#top">a</a>\n<a href="details.html?x=1">b</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert refs == [("index.html", "details.html", "L1")]  # one edge, first line


def test_percent_encoded_target_resolves(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": '<a href="My%20Page.html">x</a>\n',
        "My Page.html": "<h1>d</h1>\n",
    })
    assert refs == [("index.html", "My Page.html", "L1")]


def test_encoded_scheme_is_not_followed(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": '<a href="%2F%2Fhost%2Fdetails.html">x</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert _targets(refs, "index.html") == []


def test_target_outside_the_scan_root_gives_no_edge(tmp_path):
    refs, _ = _run(tmp_path, {
        "site/index.html": '<a href="../secret.html">x</a>\n<a href="inner.html">y</a>\n',
        "site/inner.html": "<h1>i</h1>\n",
        "secret.html": "<h1>s</h1>\n",
    }, scan="site")
    assert _targets(refs, "index.html") == ["inner.html"]


def test_base_href_disables_relative_resolution(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": '<base href="/app/">\n<a href="details.html">x</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert _targets(refs, "index.html") == []


@pytest.mark.parametrize("base", [
    'href="#top"', 'href=""', 'href="?x=1"', 'target="_blank"',
    'href="./"', 'href="."', 'href="index.html"', 'href="./index.html"', 'href="./#top"',
])
def test_a_base_that_moves_nothing_keeps_relative_references(tmp_path, base):
    # A base naming this very document (`#top`, empty), a spot in this same folder
    # (`./`, `.`, `index.html`), or with no href at all, changes nothing, so local
    # links still resolve.
    refs, _ = _run(tmp_path, {
        "index.html": f'<base {base}>\n<a href="details.html">x</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert refs == [("index.html", "details.html", "L2")]


@pytest.mark.parametrize("base", [
    'href="/app/"', 'href="sub/"', 'href="https://cdn.example.com/"',
    'href="../"', 'href="./sub/"', 'href="sub/index.html"', 'href="{{ base }}"',
])
def test_a_base_with_a_path_hides_relative_references(tmp_path, base):
    refs, _ = _run(tmp_path, {
        "index.html": f'<base {base}>\n<a href="details.html">x</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert refs == []
    assert _raw_edges(tmp_path, "index.html") == []


def test_encoded_hash_in_a_file_name_is_not_a_fragment(tmp_path):
    # `%23` is part of the name `a#b.html`; it must not truncate the link to `a`.
    refs, _ = _run(tmp_path, {
        "index.html": '<a href="a%23b.html">x</a>\n<a href="%23lead.html">y</a>\n',
        "a.html": "<p>decoy</p>\n", "a#b.html": "<p>b</p>\n", "#lead.html": "<p>l</p>\n",
    })
    assert sorted(_targets(refs, "index.html")) == ["#lead.html", "a#b.html"]


def test_unreadable_page_keeps_its_node_and_reads_no_references(tmp_path, monkeypatch):
    page = tmp_path / "repo" / "index.html"
    page.parent.mkdir(parents=True)
    page.write_text('<a href="details.html">x</a>', encoding="utf-8")

    def boom(_path):
        raise OSError("unreadable")

    monkeypatch.setattr(html_mod, "_read_source_text", boom)
    result = html_mod.extract_html(page)
    assert [n["node_kind"] for n in result["nodes"]] == ["page"]
    assert result["edges"] == []


def test_assets_graphify_does_not_index_give_no_edge(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": (
            '<link rel="stylesheet" href="style.css">\n'
            '<img src="logo.png">\n'
            '<a href="app.js">js</a>\n'
        ),
        "style.css": "body {}\n", "logo.png": "not really a png",
        "app.js": "function f() {}\n",
    })
    assert _targets(refs, "index.html") == ["app.js"]


def test_comments_and_script_strings_are_not_references(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": (
            '<!-- <a href="details.html">old</a> -->\n'
            "<script>var s = '<a href=\"details.html\">x</a>';</script>\n"
            "<p>see href=\"details.html\" in prose</p>\n"
        ),
        "details.html": "<h1>d</h1>\n",
    })
    assert _targets(refs, "index.html") == []


def test_other_tags_and_attribute_case(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": (
            '<LINK REL="import" HREF="partial.html">\n'
            '<iframe src="frame.html"></iframe>\n'
            '<script src="app.js"/>\n'
        ),
        "partial.html": "<p>p</p>\n", "frame.html": "<p>f</p>\n", "app.js": "function f() {}\n",
    })
    assert sorted(_targets(refs, "index.html")) == ["app.js", "frame.html", "partial.html"]


def test_a_repeated_target_is_one_edge_at_its_first_line(tmp_path):
    refs, _ = _run(tmp_path, {
        "index.html": '<p></p>\n<a href="details.html">a</a>\n<a href="./details.html">b</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert refs == [("index.html", "details.html", "L2")]


def test_self_reference_gives_no_edge(tmp_path):
    refs, _ = _run(tmp_path, {"index.html": '<a href="index.html">me</a>\n'})
    assert refs == []


def test_pages_are_collected_by_the_structural_pass(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "a.html").write_text("<h1>a</h1>")
    assert [p.name for p in collect_files(root, root=root)] == ["a.html"]


def test_oversized_page_keeps_its_node_but_reads_no_references(tmp_path, monkeypatch):
    monkeypatch.setattr(html_mod, "_HTML_MAX_BYTES", 10)
    refs, data = _run(tmp_path, {
        "index.html": '<a href="details.html">a link longer than ten bytes</a>\n',
        "details.html": "<h1>d</h1>\n",
    })
    assert refs == []
    assert any(n.get("source_file") == "index.html" for n in data["nodes"])


def test_extraction_is_deterministic(tmp_path):
    files = {
        "index.html": '<a href="b.html">b</a><a href="a.html">a</a><script src="x.js"></script>\n',
        "a.html": "<p>a</p>\n", "b.html": "<p>b</p>\n", "x.js": "function x() {}\n",
    }
    first, _ = _run(tmp_path / "one", files)
    second, _ = _run(tmp_path / "two", files)
    assert first == second

    # The extractor's own edge order is the order the references are written in
    # (not sorted), and identical across runs: `_run` sorts, so check it raw.
    def order(base: Path) -> list[tuple[str, str]]:
        edges = html_mod.extract_html(base / "repo" / "index.html")["edges"]
        return [(Path(e["target_file"]).name, e["source_location"]) for e in edges]

    expected = [("b.html", "L1"), ("a.html", "L1"), ("x.js", "L1")]
    assert order(tmp_path / "one") == expected
    assert order(tmp_path / "two") == expected
