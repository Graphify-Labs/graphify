"""Extraction coverage for Liquid templates of Shopify themes.

A `.liquid` file inside a Shopify theme composes the theme: sections render
snippets, templates reference sections, assets and translation keys. Without an
extractor those files contributed nothing, so "who uses this snippet" had no
answer. The extractor is gated on a theme root (a `layout/theme.liquid`
ancestor) because Jekyll and Eleventy use `.liquid` with different semantics.
"""
from __future__ import annotations

import json
import shutil
import time
from pathlib import Path

from graphify.extract import _make_id, extract, extract_liquid

FIXTURE = Path(__file__).parent / "fixtures" / "liquid_theme"


def _theme(tmp_path: Path, files: dict[str, str]) -> Path:
    """Write a synthetic theme (always with layout/theme.liquid) and return its root."""
    root = tmp_path / "theme"
    root.mkdir()
    base = {"layout/theme.liquid": "{{ content_for_layout }}\n"}
    for rel, body in {**base, **files}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def _edges(root: Path, rel: str) -> list[dict]:
    result = extract_liquid(root / rel)
    assert "error" not in result
    return [e for e in result["edges"] if e["source"] == _make_id(str(root / rel))]


def _targets(root: Path, rel: str) -> list[tuple[str, str, str]]:
    """(relation, target path or key node id, location) per edge, in order."""
    out = []
    for e in _edges(root, rel):
        tf = e.get("target_file")
        label = Path(tf).relative_to(root).as_posix() if tf else e["target"]
        out.append((e["relation"], label, e["source_location"]))
    return out


def test_liquid_registered():
    from graphify.detect import CODE_EXTENSIONS
    from graphify.extract import _DISPATCH
    from graphify.extractors import LANGUAGE_EXTRACTORS

    assert ".liquid" in CODE_EXTENSIONS
    assert _DISPATCH.get(".liquid") is extract_liquid
    assert LANGUAGE_EXTRACTORS["liquid"] is extract_liquid


def test_tracer_render_reaches_affected(tmp_path):
    import networkx as nx

    from graphify.affected import affected_nodes
    from graphify.build import build_from_json

    theme = tmp_path / "theme"
    shutil.copytree(FIXTURE, theme)
    files = sorted(theme.rglob("*.liquid"))
    extraction = extract(files, cache_root=theme, root=theme, parallel=False)
    graph = build_from_json(extraction, directed=True)
    assert isinstance(graph, nx.DiGraph)
    seed = next(
        n for n, d in graph.nodes(data=True)
        if str(d.get("source_file", "")).endswith("snippets/card.liquid") and d.get("label") == "card.liquid"
    )
    hits = affected_nodes(graph, seed)
    sources = {graph.nodes[h.node_id].get("source_file") for h in hits}
    assert any(str(s).endswith("sections/featured.liquid") for s in sources), sources


def test_render_variants_and_whitespace_control(tmp_path):
    root = _theme(tmp_path, {
        "snippets/card.liquid": "",
        "sections/a.liquid": (
            "{% render 'card' %}\n"
            "{%- render 'card', product: p -%}\n"
            "{% render 'card' with x as y %}\n"
            "{% render \"card\" for items as item %}\n"
        ),
    })
    t = _targets(root, "sections/a.liquid")
    assert t == [("imports", "snippets/card.liquid", f"L{n}") for n in (1, 2, 3, 4)]


def test_include_section_sections(tmp_path):
    root = _theme(tmp_path, {
        "snippets/legacy.liquid": "",
        "sections/banner.liquid": "",
        "sections/header-group.json": "{}",
        "sections/a.liquid": "{% include 'legacy' %}\n{% section 'banner' %}\n{% sections 'header-group' %}\n",
    })
    t = _targets(root, "sections/a.liquid")
    assert t == [
        ("imports", "snippets/legacy.liquid", "L1"),
        ("imports", "sections/banner.liquid", "L2"),
        ("imports", "sections/header-group.json", "L3"),
    ]
    result = extract_liquid(root / "sections/a.liquid")
    json_id = _make_id(str(root / "sections/header-group.json"))
    assert any(n["id"] == json_id for n in result["nodes"])


def test_content_for_block_and_schema_blocks(tmp_path):
    schema = json.dumps({"name": "S", "blocks": [
        {"type": "slide"}, {"type": "@app"}, {"type": "local", "name": "Local"},
    ]})
    root = _theme(tmp_path, {
        "blocks/slide.liquid": "",
        "blocks/other.liquid": "",
        "sections/a.liquid": (
            "{% content_for 'block', type: 'other', id: 's1' %}\n"
            "{% content_for 'blocks' %}\n"
            "{% schema %}\n" + schema + "\n{% endschema %}\n"
        ),
    })
    t = _targets(root, "sections/a.liquid")
    assert [x[1] for x in t] == ["blocks/other.liquid", "blocks/slide.liquid"]
    assert all(x[0] == "imports" for x in t)


def test_invalid_schema_json_does_not_raise(tmp_path):
    root = _theme(tmp_path, {"sections/a.liquid": "{% schema %}\n{ not json\n{% endschema %}\n"})
    assert _targets(root, "sections/a.liquid") == []


def test_asset_url(tmp_path):
    root = _theme(tmp_path, {
        "assets/base.css": "",
        "assets/theme.js.liquid": "",
        "sections/a.liquid": "{{ 'base.css' | asset_url }}\n{{ 'theme.js' | asset_url }}\n{{ 'gone.css' | asset_url }}\n",
    })
    t = _targets(root, "sections/a.liquid")
    assert t == [
        ("references", "assets/base.css", "L1"),
        ("references", "assets/theme.js.liquid", "L2"),
    ]


LOCALE = json.dumps({
    "general": {"cart": "Cart"},
    "products": {"count": {"one": "1 item", "other": "{{ n }} items"}},
    "shopify": {"checkout": {"x": "y"}},
})


def test_translation_keys(tmp_path):
    root = _theme(tmp_path, {
        "locales/en.default.json": "/* generated */\n" + LOCALE,
        "sections/a.liquid": (
            "{{ 'general.cart' | t }}\n"
            "{{- 'products.count' | t: count: n -}}\n"
            "{{ 'general.cart' | translate }}\n"
            "{{ 'x' | times: 2 }}\n"
            "{{ 'general.cart' | truncate: 3 }}\n"
            "{{ 'shopify.checkout.x' | t }}\n"
            "{{ 'general.missing' | t }}\n"
        ),
    })
    t = _targets(root, "sections/a.liquid")
    assert [(r, loc) for r, _, loc in t] == [("references", "L1"), ("references", "L2"), ("references", "L3")]
    result = extract_liquid(root / "sections/a.liquid")
    key_nodes = {n["label"]: n for n in result["nodes"] if n["file_type"] == "concept"}
    assert set(key_nodes) == {"general.cart", "products.count"}
    assert key_nodes["general.cart"]["id"] == _make_id("liquid_t", "general.cart")


def test_translation_needs_exactly_one_default_locale(tmp_path):
    root = _theme(tmp_path, {
        "locales/en.default.json": LOCALE,
        "locales/fr.default.json": LOCALE,
        "sections/a.liquid": "{{ 'general.cart' | t }}\n",
    })
    assert _targets(root, "sections/a.liquid") == []
    (tmp_path / "none").mkdir()
    root2 = _theme(tmp_path / "none", {"sections/a.liquid": "{{ 'general.cart' | t }}\n"})
    assert _targets(root2, "sections/a.liquid") == []


def test_liquid_tag_block(tmp_path):
    root = _theme(tmp_path, {
        "snippets/card.liquid": "",
        "assets/base.css": "",
        "locales/en.default.json": LOCALE,
        "sections/a.liquid": (
            "{%- liquid\n"
            "  assign x = 1\n"
            "  render 'card'\n"
            "  echo 'general.cart' | t\n"
            "  assign u = 'base.css' | asset_url\n"
            "  # render 'card'\n"
            "  comment\n"
            "    render 'card'\n"
            "  endcomment\n"
            "-%}\n"
        ),
    })
    t = _targets(root, "sections/a.liquid")
    assert [(r, loc) for r, _, loc in t] == [("imports", "L3"), ("references", "L4"), ("references", "L5")]


def test_dynamic_names_make_no_edge_and_no_node(tmp_path):
    root = _theme(tmp_path, {
        "snippets/card.liquid": "",
        "sections/a.liquid": "{% render some_var %}\n{% render block %}\n{% include var %}\n",
    })
    result = extract_liquid(root / "sections/a.liquid")
    assert result["edges"] == []
    assert len(result["nodes"]) == 1


def test_masked_regions_make_no_edge_and_keep_lines(tmp_path):
    root = _theme(tmp_path, {
        "snippets/card.liquid": "",
        "sections/a.liquid": (
            "{% comment %}\n{% render 'card' %}\n{% endcomment %}\n"
            "{%- comment -%}{% render 'card' %}{%- endcomment -%}\n"
            "{% # render 'card' %}\n"
            "{% doc %}\n  @example\n  {% render 'card' %}\n{% enddoc %}\n"
            "{% raw %}{% render 'card' %}{% endraw %}\n"
            "{% comment %}{% comment %}x{% endcomment %}{% render 'card' %}{% endcomment %}\n"
            "{% render 'card' %}\n"
        ),
    })
    t = _targets(root, "sections/a.liquid")
    assert t == [("imports", "snippets/card.liquid", "L12")]


def test_file_outside_a_theme_yields_only_its_file_node(tmp_path):
    p = tmp_path / "site" / "_includes" / "a.liquid"
    p.parent.mkdir(parents=True)
    p.write_text("{% render 'card' %}{% include 'x' %}", encoding="utf-8")
    (tmp_path / "site" / "snippets").mkdir()
    (tmp_path / "site" / "snippets" / "card.liquid").write_text("", encoding="utf-8")
    result = extract_liquid(p)
    assert result["edges"] == []
    assert [n["label"] for n in result["nodes"]] == ["a.liquid"]


def test_path_traversal_gets_no_edge(tmp_path):
    (tmp_path / "secret.liquid").write_text("", encoding="utf-8")
    (tmp_path / "passwd").write_text("", encoding="utf-8")
    root = _theme(tmp_path, {
        "sections/a.liquid": (
            "{% render '../x' %}\n{% render 'a/b' %}\n{% render 'a\\b' %}\n"
            "{{ '../../passwd' | asset_url }}\n{{ '/etc/passwd' | asset_url }}\n"
            "{% section '../sections/a' %}\n{% content_for 'block', type: '../x' %}\n"
        ),
    })
    assert _targets(root, "sections/a.liquid") == []


def test_edges_are_deduplicated_and_in_source_order(tmp_path):
    root = _theme(tmp_path, {
        "snippets/a.liquid": "", "snippets/b.liquid": "",
        "sections/s.liquid": "{% render 'b' %}{% render 'a' %}\n{% render 'a' %}{% render 'a' %}\n",
    })
    t = _targets(root, "sections/s.liquid")
    assert [x[1] for x in t] == ["snippets/b.liquid", "snippets/a.liquid", "snippets/a.liquid"]
    assert [x[2] for x in t] == ["L1", "L1", "L2"]


def test_pathological_unclosed_openers_are_linear(tmp_path):
    body = ("{% " * 200_000) + ("{{ " * 200_000) + ("'" * 200_000)
    root = _theme(tmp_path, {"sections/a.liquid": body})
    start = time.perf_counter()
    extract_liquid(root / "sections/a.liquid")
    assert time.perf_counter() - start < 5
