"""CSS selector extraction for Shopify themes: pure scanner, node shape and theme gating."""
from __future__ import annotations

import time
from pathlib import Path

from graphify.extractors.css import css_result, css_selector_id, css_selectors, extract_css


def _sel(text: str) -> list[tuple[str, int]]:
    return css_selectors(text)


def test_pseudo_classes_never_produce_a_selector() -> None:
    text = "a:first-child {}\n.btn:focus-visible, .card-x:hover {}\n:focus-visible {}\n"
    found = _sel(text)
    assert found == [(".btn", 2), (".card-x", 2)]
    labels = " ".join(s for s, _ in found)
    assert "first-child" not in labels
    assert "focus-visible" not in labels
    assert "hover" not in labels


def test_media_blocks_comments_strings_and_numbers() -> None:
    text = (
        "a:first-child {}\n"
        ".btn:focus-visible, .card-x:hover { margin: .5em; content: \".no\"; }\n"
        "@media (min-width: 750px) { .foo--bar {} }\n"
        "x-popover[open] {}\n"
        "/* .no {} */\n"
    )
    assert _sel(text) == [(".btn", 2), (".card-x", 2), (".foo--bar", 3), ("x-popover", 4)]


def test_every_occurrence_is_returned_with_its_line() -> None:
    text = ".flag {}\n\n\n\n.flag { color: red }\n"
    assert _sel(text) == [(".flag", 1), (".flag", 5)]


def test_compound_ids_and_functional_pseudos() -> None:
    text = "#main.wide > .row:not(.hidden) {}\n.a:nth-child(2n+1):lang(en-US) {}\n"
    assert _sel(text) == [("#main", 1), (".wide", 1), (".row", 1), (".hidden", 1), (".a", 2)]


def test_custom_element_type_selector_keeps_no_angle_brackets() -> None:
    found = _sel("cart-drawer .item, div {}\n::-webkit-scrollbar {}\n")
    assert found == [("cart-drawer", 1), (".item", 1)]


def test_unterminated_comment_and_string_do_not_hang_or_leak() -> None:
    assert _sel(".ok {}\n/* .gone {}\n") == [(".ok", 1)]
    assert _sel(".ok {}\n\"unterminated .gone {}\n") == [(".ok", 1)]


def test_megabyte_of_css_is_fast() -> None:
    text = ("/*" * 100) + ".a-b:hover > .c { color: red; }\n" * 30000 + "{{" * 1000
    start = time.perf_counter()
    found = _sel(text)
    assert time.perf_counter() - start < 2.0
    assert found == []  # the leading unterminated comment swallows the rest
    text = ".a-b:hover > .c { color: red; }\n" * 30000 + "{{" * 1000
    start = time.perf_counter()
    found = _sel(text)
    assert time.perf_counter() - start < 2.0
    assert found[0] == (".a-b", 1)


def test_selector_id_distinguishes_kinds_and_dash_underscore() -> None:
    ids = {css_selector_id("/t/assets/a.css", s) for s in (".btn", "#btn", ".btn-x", ".btn_x", "btn-x")}
    assert len(ids) == 5
    assert css_selector_id("/t/assets/a.css", ".btn") == css_selector_id("/t/assets/a.css", ".btn")


def test_css_result_one_node_per_selector_one_edge_per_line(tmp_path: Path) -> None:
    path = tmp_path / "assets" / "a.css"
    result = css_result(path, ".flag {}\n.x-y {}\n.flag {}\n")
    labels = sorted(n["label"] for n in result["nodes"] if n["label"] != "a.css")
    assert labels == [".flag", ".x-y"]
    flag = next(n for n in result["nodes"] if n["label"] == ".flag")
    assert flag["source_location"] == "L1"
    edges = [e for e in result["edges"] if e["target"] == flag["id"]]
    assert sorted(e["source_location"] for e in edges) == ["L1", "L3"]
    assert {e["relation"] for e in edges} == {"contains"}


def _theme_with(tmp_path: Path, rel: str, body: str) -> Path:
    root = tmp_path / "theme"
    (root / "layout").mkdir(parents=True)
    (root / "layout" / "theme.liquid").write_text("{{ content_for_layout }}\n", encoding="utf-8")
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


def test_theme_css_asset_yields_selector_nodes_with_lines(tmp_path: Path) -> None:
    css = _theme_with(tmp_path, "assets/base.css", ".top {}\n\n.btn:hover {}\n")
    result = extract_css(css)
    assert "error" not in result
    nodes = {n["label"]: n["source_location"] for n in result["nodes"]}
    assert nodes[".top"] == "L1"
    assert nodes[".btn"] == "L3"


def test_non_theme_css_yields_no_nodes_and_is_marked_skipped(tmp_path: Path) -> None:
    css = tmp_path / "site" / "main.css"
    css.parent.mkdir()
    css.write_text(".a {}\n.b {}\n", encoding="utf-8")
    result = extract_css(css)
    assert result["nodes"] == []
    assert result["edges"] == []
    assert result["skipped"]


def test_non_theme_repo_graph_is_unchanged_by_css_support(tmp_path: Path) -> None:
    from graphify.extract import extract

    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "app.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    (repo / "style.css").write_text(".a {}\n.b:hover {}\n", encoding="utf-8")
    with_css = extract([repo / "app.py", repo / "style.css"])
    without_css = extract([repo / "app.py"])
    assert len(with_css["nodes"]) == len(without_css["nodes"])
    assert len(with_css["edges"]) == len(without_css["edges"])


def test_css_is_registered_for_extraction_and_detection(tmp_path: Path) -> None:
    from graphify.detect import CODE_EXTENSIONS
    from graphify.extract import extract

    assert ".css" in CODE_EXTENSIONS
    css = _theme_with(tmp_path, "assets/base.css", ".top {}\n.btn:hover {}\n")
    result = extract([css])
    labels = {n["label"] for n in result["nodes"]}
    assert {".top", ".btn"} <= labels


def test_escaped_class_names_are_returned_unescaped():
    assert css_selectors(".md\\:flex { a: b }\n.w-1\\/2 { a: b }\n") == [(".md:flex", 1), (".w-1/2", 2)]
