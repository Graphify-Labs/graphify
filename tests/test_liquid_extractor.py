"""Extraction coverage for Liquid templates of Shopify themes.

A `.liquid` file inside a Shopify theme composes the theme: sections render
snippets, templates reference sections, assets and translation keys. Without an
extractor those files contributed nothing, so "who uses this snippet" had no
answer. The extractor is gated on a theme root (a `layout/theme.liquid`
ancestor) because Jekyll and Eleventy use `.liquid` with different semantics.
"""
from __future__ import annotations

import json
import random
import shutil
import subprocess
import sys
import time
from pathlib import Path

import pytest

from graphify.extract import _make_id, extract, extract_liquid

FIXTURE = Path(__file__).parent / "fixtures" / "liquid_theme"
BROKEN = Path(__file__).parent / "fixtures" / "liquid_theme_broken"


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
    """(relation, target path or key node id, location) per EXTRACTED edge, in order."""
    out = []
    for e in _edges(root, rel):
        if e["confidence"] != "EXTRACTED":
            continue
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


def test_asset_url_with_query_or_fragment_resolves_the_file(tmp_path):
    root = _theme(tmp_path, {
        "assets/font.eot": "",
        "sections/a.liquid": "{{ 'font.eot?#iefix' | asset_url }}\n{{ 'gone.svg#frag' | asset_url }}\n",
    })
    assert _targets(root, "sections/a.liquid") == [("references", "assets/font.eot", "L1")]
    nodes = {n["id"]: n for n in extract_liquid(root / "sections/a.liquid")["nodes"]}
    labels = [n["label"] for n in nodes.values() if n.get("unresolved")]
    assert labels == ["assets/gone.svg"]


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
    key_nodes = {
        n["label"]: n for n in result["nodes"]
        if n["file_type"] == "concept" and not n.get("unresolved")
    }
    assert set(key_nodes) == {"general.cart", "products.count"}
    assert key_nodes["general.cart"]["id"] == _make_id("liquid_t", "general.cart")


def test_translation_keys_with_line_comments_in_the_locale(tmp_path):
    # Shopify locale files start with a `//` header; a URL inside a string must survive.
    locale = (
        "// Do not edit, generated file\n"
        "{\n"
        "  /* section */\n"
        '  "general": {"cart": "Cart", "link": "https://example.com/a // b"}, // trailing\n'
        '  "q": {"say": "He said \\"hi\\" // not a comment"}\n'
        "}\n"
    )
    root = _theme(tmp_path, {
        "locales/en.default.json": locale,
        "sections/a.liquid": "{{ 'general.cart' | t }}\n{{ 'general.link' | t }}\n{{ 'q.say' | t }}\n",
    })
    assert [(r, loc) for r, _, loc in _targets(root, "sections/a.liquid")] == [
        ("references", "L1"), ("references", "L2"), ("references", "L3"),
    ]


def test_asset_edges_survive_the_build_when_siblings_share_a_stem(tmp_path):
    from graphify.build import build_from_json

    root = _theme(tmp_path, {
        "assets/app.css": "a{}\n",
        "assets/app.js": "var x = 1;\n",
        "sections/a.liquid": "{{ 'app.css' | asset_url }}\n{{ 'app.js' | asset_url }}\n",
    })
    files = sorted(p for p in root.rglob("*") if p.is_file())
    G = build_from_json(extract(files), root=root)
    liquid = [n for n, d in G.nodes(data=True) if d["source_file"].endswith("a.liquid")]
    reached = {
        Path(G.nodes[v]["source_file"]).name
        for u in liquid for v in G.neighbors(u)
    }
    assert {"app.css", "app.js"} <= reached


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


def _unresolved(root: Path, rel: str) -> list[tuple[str, str, str]]:
    """(ref_kind, label, location) per AMBIGUOUS edge, in order."""
    result = extract_liquid(root / rel)
    nodes = {n["id"]: n for n in result["nodes"]}
    out = []
    for e in result["edges"]:
        if e["confidence"] != "AMBIGUOUS":
            continue
        node = nodes[e["target"]]
        assert node["unresolved"] is True
        assert e["confidence_score"] < 0.5
        assert "target_file" not in e
        out.append((node["ref_kind"], node["label"], e["source_location"]))
    return out


def test_broken_fixture_lists_exactly_three_unresolved(tmp_path):
    theme = tmp_path / "theme"
    shutil.copytree(BROKEN, theme)
    assert _unresolved(theme, "sections/main.liquid") == [
        ("snippet", "snippets/missing-card.liquid", "L1"),
        ("asset", "assets/missing.css", "L2"),
        ("t", "missing.key", "L3"),
    ]
    kinds = {e["confidence"] for e in _edges(theme, "sections/main.liquid")}
    assert kinds == {"AMBIGUOUS", "EXTRACTED"}


def test_unresolved_survives_build_and_export(tmp_path):
    from graphify.build import build_from_json

    theme = tmp_path / "theme"
    shutil.copytree(BROKEN, theme)
    files = sorted(theme.rglob("*.liquid"))
    extraction = extract(files, cache_root=theme, root=theme, parallel=False)
    graph = build_from_json(extraction, directed=True)
    refs = {n: d for n, d in graph.nodes(data=True) if d.get("unresolved")}
    assert len(refs) == 3
    assert all(n.startswith("ref_liquid_") for n in refs)
    ambiguous = [
        (u, v) for u, v, d in graph.edges(data=True)
        if d.get("confidence") == "AMBIGUOUS" and v in refs
    ]
    assert len(ambiguous) == 3
    assert not [
        1 for _, v, d in graph.edges(data=True)
        if v in refs and d.get("confidence") == "EXTRACTED"
    ]


def test_other_unresolved_kinds(tmp_path):
    schema = json.dumps({"blocks": [{"type": "ghost"}]})
    root = _theme(tmp_path, {
        "sections/a.liquid": (
            "{% section 'nope' %}\n{% sections 'nogroup' %}\n"
            "{% content_for 'block', type: 'noblock' %}\n"
            "{% schema %}\n" + schema + "\n{% endschema %}\n"
        ),
    })
    kinds = [k for k, _, _ in _unresolved(root, "sections/a.liquid")]
    assert kinds == ["section", "section_group", "block", "block"]


def test_no_locale_no_t_edges_and_no_unresolved_t(tmp_path):
    root = _theme(tmp_path, {"sections/a.liquid": "{{ 'a.b' | t }}\n"})
    assert _unresolved(root, "sections/a.liquid") == []


def _graph_json(theme: Path) -> dict:
    proc = subprocess.run(
        [sys.executable, "-m", "graphify", "update", str(theme)],
        capture_output=True, text=True, timeout=300, check=False,
    )
    assert proc.returncode == 0, proc.stderr[-500:]
    return json.loads((theme / "graphify-out" / "graph.json").read_text(encoding="utf-8"))


def _links(graph: dict) -> list[dict]:
    return graph.get("links") or graph.get("edges") or []


def test_extraction_is_deterministic(tmp_path):
    theme = tmp_path / "theme"
    shutil.copytree(BROKEN, theme)
    files = sorted(theme.rglob("*.liquid"))
    first = json.dumps([extract_liquid(f) for f in files], sort_keys=True)
    second = json.dumps([extract_liquid(f) for f in files], sort_keys=True)
    assert first == second
    shuffled = list(files)
    random.Random(7).shuffle(shuffled)
    a = extract(files, cache_root=theme, root=theme, parallel=False)
    b = extract(shuffled, cache_root=theme, root=theme, parallel=False)
    key = lambda d: json.dumps(d, sort_keys=True)  # noqa: E731
    assert sorted(map(key, a["nodes"])) == sorted(map(key, b["nodes"]))
    assert sorted(map(key, a["edges"])) == sorted(map(key, b["edges"]))


def test_two_updates_give_the_same_graph(tmp_path):
    theme = tmp_path / "theme"
    shutil.copytree(BROKEN, theme)
    g1 = _graph_json(theme)
    g2 = _graph_json(theme)
    norm = lambda g: (  # noqa: E731
        sorted(json.dumps(n, sort_keys=True) for n in g["nodes"]),
        sorted(json.dumps(e, sort_keys=True) for e in _links(g)),
    )
    assert norm(g1) == norm(g2)
    unresolved = [
        e for e in _links(g1)
        if e.get("confidence") == "AMBIGUOUS" and str(e["target"]).startswith("ref_liquid_")
    ]
    assert len(unresolved) == 3


@pytest.mark.xfail(
    strict=True,
    reason="incremental cache keeps the unchanged citing file's AMBIGUOUS edge; a full rebuild clears it",
)
def test_update_after_the_missing_file_appears_resolves_the_edge(tmp_path):
    theme = tmp_path / "theme"
    shutil.copytree(BROKEN, theme)
    _graph_json(theme)
    (theme / "snippets").mkdir()
    (theme / "snippets" / "missing-card.liquid").write_text("<p></p>\n", encoding="utf-8")
    after = _graph_json(theme)
    ambiguous = [
        e for e in _links(after)
        if e.get("confidence") == "AMBIGUOUS" and "missing_card" in str(e["target"]).replace("-", "_")
    ]
    assert ambiguous == []


def test_two_megabyte_file_is_fast(tmp_path):
    line = "{% render 'x' %}{{ 'a.b' | t }}{%- liquid\n  echo 'c.d' | t\n-%}\n<div>text</div>\n"
    body = line * (2 * 1024 * 1024 // len(line))
    root = _theme(tmp_path, {"sections/a.liquid": body})
    start = time.perf_counter()
    extract_liquid(root / "sections/a.liquid")
    assert time.perf_counter() - start < 2


def test_inline_asset_content_filter_links_the_asset(tmp_path):
    root = _theme(tmp_path, {
        "assets/icon.svg": "<svg/>",
        "sections/a.liquid": "{{ 'icon.svg' | inline_asset_content }}\n{{ 'gone.svg' | inline_asset_content }}\n",
    })
    assert _targets(root, "sections/a.liquid") == [("references", "assets/icon.svg", "L1")]
    unresolved = [e for e in _edges(root, "sections/a.liquid") if e["confidence"] == "AMBIGUOUS"]
    assert len(unresolved) == 1 and unresolved[0]["source_location"] == "L2"


def test_content_for_blocks_with_theme_blocks_infers_public_blocks(tmp_path):
    schema = json.dumps({"name": "S", "blocks": [{"type": "@theme"}, {"type": "@app"}]})
    root = _theme(tmp_path, {
        "blocks/card.liquid": "", "blocks/badge.liquid": "", "blocks/_private.liquid": "",
        "sections/open.liquid": "{% content_for 'blocks' %}\n{% schema %}\n" + schema + "\n{% endschema %}\n",
        "sections/named.liquid": "{% content_for 'blocks' %}\n{% schema %}\n"
        + json.dumps({"name": "N", "blocks": [{"type": "card"}]}) + "\n{% endschema %}\n",
        "sections/no_call.liquid": "{% schema %}\n" + schema + "\n{% endschema %}\n",
    })
    inferred = [e for e in _edges(root, "sections/open.liquid") if e["confidence"] == "INFERRED"]
    assert sorted(Path(e["target_file"]).name for e in inferred) == ["badge.liquid", "card.liquid"]
    assert {e["relation"] for e in inferred} == {"imports"} and inferred[0]["source_location"] == "L1"
    assert [e for e in _edges(root, "sections/named.liquid") if e["confidence"] == "INFERRED"] == []
    assert [e for e in _edges(root, "sections/no_call.liquid") if e["confidence"] == "INFERRED"] == []


def test_asset_img_url_filter_links_the_asset(tmp_path):
    root = _theme(tmp_path, {
        "assets/logo.png": "",
        "sections/a.liquid": "<img src=\"{{ 'logo.png' | asset_img_url: '100x' }}\">\n",
    })
    assert _targets(root, "sections/a.liquid") == [("references", "assets/logo.png", "L1")]


def test_enabled_and_disabled_on_link_templates_and_groups(tmp_path):
    schema = json.dumps({
        "name": "Banner",
        "enabled_on": {"templates": ["index", "customers/account", "*"], "groups": ["header", "aside"]},
        "disabled_on": {"templates": ["cart", "ghost"]},
    }, indent=2)
    root = _theme(tmp_path, {
        "templates/index.json": "{}", "templates/customers/account.json": "{}", "templates/cart.liquid": "",
        "sections/header-group.json": "{}", "sections/aside.json": "{}",
        "sections/banner.liquid": "{% schema %}\n" + schema + "\n{% endschema %}\n",
    })
    assert sorted(x[1] for x in _targets(root, "sections/banner.liquid")) == [
        "sections/aside.json", "sections/header-group.json",
        "templates/cart.liquid", "templates/customers/account.json", "templates/index.json",
    ]
    unresolved = [e for e in _edges(root, "sections/banner.liquid") if e["confidence"] == "AMBIGUOUS"]
    assert len(unresolved) == 1 and unresolved[0]["target"].startswith("ref_liquid_template_")


def test_preset_blocks_link_existing_block_files_nested_and_dict_form(tmp_path):
    schema = json.dumps({
        "name": "Hero",
        "blocks": [{"type": "local", "name": "Local"}],
        "presets": [
            {"name": "A", "blocks": [
                {"type": "card", "blocks": [{"type": "badge"}]},
                {"type": "local"},
                {"type": "@app"},
                {"type": "nofile"},
            ]},
            {"name": "B", "blocks": {"x": {"type": "tile", "blocks": {"y": {"type": "card"}}}}},
        ],
    }, indent=2)
    root = _theme(tmp_path, {
        "blocks/card.liquid": "", "blocks/badge.liquid": "", "blocks/tile.liquid": "",
        "sections/hero.liquid": "{% schema %}\n" + schema + "\n{% endschema %}\n",
    })
    t = _targets(root, "sections/hero.liquid")
    assert sorted(x[1] for x in t if x[0] == "imports") == ["blocks/badge.liquid", "blocks/card.liquid", "blocks/tile.liquid"]
    assert [e for e in _edges(root, "sections/hero.liquid") if e["confidence"] == "AMBIGUOUS"] == []


# -- settings (R4) -----------------------------------------------------------

_SETTINGS_SCHEMA = """/* synthetic schema */
[
  {"name": "theme_info", "theme_name": "Demo"},
  {
    "name": "Header",
    "settings": [
      {"type": "header", "content": "Header"},
      {"type": "checkbox", "id": "show_breadcrumbs", "label": "Breadcrumbs"},
      {"type": "select", "id": "text_direction", "label": "Direction"},
      {"type": "text", "id": "logo", "label": "Logo"}
    ]
  }
]
"""


def _line_of(text: str, needle: str) -> int:
    return text[: text.index(needle)].count("\n") + 1


def _used(root: Path, rel: str) -> list[dict]:
    """Edges leaving the file, each with its target node under ``node``."""
    result = extract_liquid(root / rel)
    assert "error" not in result
    nodes = {n["id"]: n for n in result["nodes"]}
    fid = _make_id(str(root / rel))
    return [{**e, "node": nodes[e["target"]]} for e in result["edges"] if e["source"] == fid and e["target"] in nodes]


def _by_label(edges: list[dict], label: str) -> list[dict]:
    return [e for e in edges if e["node"]["label"] == label]


def test_settings_global_links_to_schema_line(tmp_path):
    layout = (
        "{{ settings.show_breadcrumbs }}\n"
        "{% if settings.text_direction == 'rtl' %}x{% endif %}\n"
        "{% liquid\n  assign a = 1\n  echo settings.logo\n%}\n"
    )
    root = _theme(tmp_path, {"layout/password.liquid": layout, "config/settings_schema.json": _SETTINGS_SCHEMA})
    edges = _used(root, "layout/password.liquid")
    for sid, line in (("show_breadcrumbs", 1), ("text_direction", 2), ("logo", 5)):
        found = _by_label(edges, f"settings.{sid}")
        assert len(found) == 1, sid
        e = found[0]
        assert e["relation"] == "references" and e["confidence"] == "EXTRACTED"
        assert e["source_location"] == f"L{line}"
        assert Path(e["node"]["source_file"]) == root / "config" / "settings_schema.json"
        needle = '"id": "' + sid + '"'
        assert e["node"]["source_location"] == f"L{_line_of(_SETTINGS_SCHEMA, needle)}"


def test_settings_bracket_form_links(tmp_path):
    root = _theme(tmp_path, {
        "layout/password.liquid": "{{ settings['logo'] }}{{ settings[\"logo\"] }}{{ settings[var] }}\n",
        "config/settings_schema.json": _SETTINGS_SCHEMA,
    })
    edges = _used(root, "layout/password.liquid")
    assert len(_by_label(edges, "settings.logo")) == 1
    assert len(edges) == 1


def test_settings_missing_id_is_ambiguous_unresolved(tmp_path):
    root = _theme(tmp_path, {
        "layout/password.liquid": "{{ settings.missing }}\n",
        "config/settings_schema.json": _SETTINGS_SCHEMA,
    })
    edges = _used(root, "layout/password.liquid")
    assert len(edges) == 1
    e = edges[0]
    assert e["confidence"] == "AMBIGUOUS"
    assert e["node"]["unresolved"] is True and e["node"]["ref_kind"] == "setting"
    assert e["node"]["label"] == "settings.missing"


def test_settings_in_nested_comment_and_t_prefix_ignored(tmp_path):
    layout = (
        "{% comment %}{% comment %}{{ settings.logo }}{% endcomment %}{{ settings.logo }}{% endcomment %}\n"
        "{{ product.settings.logo }}{{ 't:settings.logo' }}\n"
    )
    root = _theme(tmp_path, {"layout/password.liquid": layout, "config/settings_schema.json": _SETTINGS_SCHEMA})
    assert _used(root, "layout/password.liquid") == []


def test_settings_hostile_schema_is_treated_as_missing(tmp_path, monkeypatch):
    from graphify.extractors import liquid

    root = _theme(tmp_path, {"layout/password.liquid": "{{ settings.logo }}\n", "config/settings_schema.json": "[{"})
    edges = _used(root, "layout/password.liquid")
    assert [e["confidence"] for e in edges] == ["AMBIGUOUS"]

    big = tmp_path / "big"
    big.mkdir()
    monkeypatch.setattr(liquid, "_MAX_LOCALE_BYTES", 10)
    root = _theme(big, {"layout/password.liquid": "{{ settings.logo }}\n", "config/settings_schema.json": _SETTINGS_SCHEMA})
    assert [e["confidence"] for e in _used(root, "layout/password.liquid")] == ["AMBIGUOUS"]


def test_settings_regex_is_linear_on_a_huge_line(tmp_path):
    root = _theme(tmp_path, {
        "layout/password.liquid": "{{ " + "settings." * 60000 + "x" + " section.settings[ " * 20000 + " }}\n",
        "config/settings_schema.json": _SETTINGS_SCHEMA,
    })
    start = time.perf_counter()
    extract_liquid(root / "layout/password.liquid")
    assert time.perf_counter() - start < 2
