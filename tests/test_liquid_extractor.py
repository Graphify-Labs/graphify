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


def _schema_text(**data) -> str:
    return "{% schema %}\n" + json.dumps(data, indent=2) + "\n{% endschema %}\n"


def _setting_edges(root: Path, rel: str) -> list[dict]:
    return [e for e in _used(root, rel) if ".settings." in e["node"]["label"]]


def test_settings_section_links_to_schema_declared_after_the_use(tmp_path):
    schema = _schema_text(name="S", settings=[{"type": "text", "id": "title", "label": "T"}])
    src = "<h1>{{ section.settings.title }}</h1>\n{{ section.settings['title'] }}\n" + schema
    root = _theme(tmp_path, {"sections/s.liquid": src})
    edges = _setting_edges(root, "sections/s.liquid")
    assert [(e["node"]["label"], e["confidence"], e["source_location"]) for e in edges] == [
        ("section.settings.title", "EXTRACTED", "L1"),
        ("section.settings.title", "EXTRACTED", "L2"),
    ]
    node = edges[0]["node"]
    assert Path(node["source_file"]) == root / "sections" / "s.liquid"
    needle = '"id": "title"'
    assert node["source_location"] == f"L{_line_of(src, needle)}"


def test_settings_block_file_links_to_its_own_schema(tmp_path):
    src = "{{ block.settings.width }}\n" + _schema_text(name="B", settings=[{"type": "range", "id": "width"}])
    root = _theme(tmp_path, {"blocks/b.liquid": src})
    (edge,) = _setting_edges(root, "blocks/b.liquid")
    assert (edge["node"]["label"], edge["confidence"]) == ("block.settings.width", "EXTRACTED")
    assert Path(edge["node"]["source_file"]) == root / "blocks" / "b.liquid"


def test_settings_block_in_section_extracted_when_one_block_defines_it(tmp_path):
    schema = _schema_text(name="S", blocks=[
        {"type": "a", "name": "A", "settings": [{"type": "text", "id": "icon"}]},
        {"type": "b", "name": "B", "settings": [{"type": "text", "id": "other"}]},
    ])
    root = _theme(tmp_path, {"sections/s.liquid": "{{ block.settings.icon }}\n" + schema})
    (edge,) = _setting_edges(root, "sections/s.liquid")
    assert (edge["node"]["label"], edge["confidence"]) == ("block.settings.icon", "EXTRACTED")


def test_settings_block_in_section_inferred_when_several_blocks_define_it(tmp_path):
    schema = _schema_text(name="S", blocks=[
        {"type": "a", "name": "A", "settings": [{"type": "text", "id": "icon"}]},
        {"type": "b", "name": "B", "settings": [{"type": "text", "id": "icon"}]},
    ])
    root = _theme(tmp_path, {"sections/s.liquid": "{{ block.settings.icon }}\n" + schema})
    edges = _setting_edges(root, "sections/s.liquid")
    assert [(e["confidence"], e["confidence_score"]) for e in edges] == [("INFERRED", 0.55)] * 2
    assert len({e["target"] for e in edges}) == 2


def test_settings_section_in_block_follows_the_static_parent_section(tmp_path):
    one = _schema_text(name="S", settings=[{"type": "text", "id": "a"}])
    files = {
        "blocks/b.liquid": "{{ section.settings.a }}\n",
        "sections/one.liquid": "{% content_for 'block', type: 'b', id: 'x' %}\n" + one,
    }
    root = _theme(tmp_path, files)
    (edge,) = _setting_edges(root, "blocks/b.liquid")
    assert (edge["node"]["label"], edge["confidence"]) == ("section.settings.a", "EXTRACTED")
    assert Path(edge["node"]["source_file"]) == root / "sections" / "one.liquid"

    files["sections/two.liquid"] = _schema_text(name="T", settings=[{"type": "text", "id": "a"}], blocks=[{"type": "b"}])
    second = tmp_path / "two"
    second.mkdir()
    root = _theme(second, files)
    edges = _setting_edges(root, "blocks/b.liquid")
    assert [e["confidence"] for e in edges] == ["INFERRED", "INFERRED"]
    assert sorted(Path(e["node"]["source_file"]).name for e in edges) == ["one.liquid", "two.liquid"]


def test_settings_section_in_block_without_a_parent_is_ambiguous(tmp_path):
    root = _theme(tmp_path, {"blocks/b.liquid": "{{ section.settings.a }}\n"})
    (edge,) = _setting_edges(root, "blocks/b.liquid")
    assert edge["confidence"] == "AMBIGUOUS"
    assert (edge["node"]["ref_kind"], edge["node"]["label"]) == ("setting", "section.settings.a")


def test_settings_in_snippet_follow_the_sections_that_render_it(tmp_path):
    schema = _schema_text(
        name="S", settings=[{"type": "text", "id": "a"}],
        blocks=[{"type": "k", "name": "K", "settings": [{"type": "text", "id": "b"}]}],
    )
    root = _theme(tmp_path, {
        "snippets/outer.liquid": "{% render 'inner' %}\n",
        "snippets/inner.liquid": "{{ section.settings.a }}{{ block.settings.b }}{{ block.settings.none }}\n",
        "sections/s.liquid": "{% render 'outer' %}\n" + schema,
    })
    edges = _setting_edges(root, "snippets/inner.liquid")
    resolved = [e for e in edges if e["confidence"] == "INFERRED"]
    assert sorted(e["node"]["label"] for e in resolved) == ["block.settings.b", "section.settings.a"]
    assert {Path(e["node"]["source_file"]).name for e in resolved} == {"s.liquid"}
    assert [e["node"]["label"] for e in edges if e["confidence"] == "AMBIGUOUS"] == ["block.settings.none"]


# -- metafields (R6) ---------------------------------------------------------

_METAFIELDS = """{
  "product": [
    {"key": "video_plp", "namespace": "custom", "name": "Video PLP", "description": "",
     "type": {"name": "boolean", "category": "TRUE_FALSE"}},
    {"key": "shared", "namespace": "custom", "name": "Shared on product", "type": {"name": "json", "category": "JSON"}}
  ],
  "variant": [
    {"key": "shared", "namespace": "custom", "name": "Shared on variant", "type": {"name": "json", "category": "JSON"}}
  ],
  "shop": [
    {"key": "only_shop", "namespace": "ns", "name": "Only shop", "type": {"name": "single_line_text_field"}}
  ],
  "page": []
}
"""


def _metafield_theme(tmp_path: Path, liquid: str, metafields: str | None = _METAFIELDS) -> Path:
    files = {"snippets/m.liquid": liquid}
    if metafields is not None:
        files[".shopify/metafields.json"] = metafields
    return _theme(tmp_path, files)


def _metafield_graph(root: Path) -> tuple[list[dict], dict[str, dict], list[dict]]:
    """(Liquid->use edges, nodes by id, every edge) of snippets/m.liquid."""
    result = extract_liquid(root / "snippets/m.liquid")
    nodes = {n["id"]: n for n in result["nodes"]}
    fid = _make_id(str(root / "snippets/m.liquid"))
    return [e for e in result["edges"] if e["source"] == fid], nodes, result["edges"]


def test_metafield_use_links_to_its_definition(tmp_path):
    root = _metafield_theme(tmp_path, "{{ product.metafields.custom.video_plp.value }}\n")
    uses, nodes, edges = _metafield_graph(root)
    (use,) = uses
    node = nodes[use["target"]]
    assert (node["label"], use["relation"], use["confidence"], use["source_location"]) == (
        "metafields.custom.video_plp", "references", "EXTRACTED", "L1")
    (link,) = [e for e in edges if e["source"] == node["id"]]
    definition = nodes[link["target"]]
    assert (link["relation"], link["confidence"]) == ("references", "EXTRACTED")
    assert definition["label"] == "metafields.custom.video_plp@product"
    assert (definition["owner"], definition["metafield_type"], definition["name"]) == ("product", "boolean", "Video PLP")
    assert Path(definition["source_file"]) == root / ".shopify" / "metafields.json"
    needle = '"key": "video_plp"'
    assert definition["source_location"] == f"L{_line_of(_METAFIELDS, needle)}"


def test_metafield_unknown_owner_variable_is_inferred_from_a_single_definition(tmp_path):
    root = _metafield_theme(tmp_path, "{{ thing.metafields.ns.only_shop }}\n")
    uses, nodes, edges = _metafield_graph(root)
    (link,) = [e for e in edges if e["source"] == uses[0]["target"]]
    assert (link["confidence"], link["confidence_score"]) == ("INFERRED", 0.55)
    assert nodes[link["target"]]["owner"] == "shop"


def test_metafield_owner_variable_picks_its_own_definition_among_several(tmp_path):
    root = _metafield_theme(tmp_path, "{{ variant.metafields.custom.shared }}{{ item.metafields.custom.shared }}\n")
    uses, nodes, edges = _metafield_graph(root)
    use_id = uses[0]["target"]
    links = [e for e in edges if e["source"] == use_id]
    by_owner = {nodes[e["target"]]["owner"]: e["confidence"] for e in links}
    assert by_owner == {"variant": "EXTRACTED", "product": "INFERRED"}


def test_metafield_bracket_form_shares_the_use_node(tmp_path):
    root = _metafield_theme(
        tmp_path, "{{ product.metafields.custom.video_plp }}{{ product.metafields['custom']['video_plp'] }}\n")
    uses, nodes, _ = _metafield_graph(root)
    assert len({e["target"] for e in uses}) == 1 and nodes[uses[0]["target"]]["label"] == "metafields.custom.video_plp"


def test_metafield_multiline_tag_gets_the_line_of_the_use(tmp_path):
    root = _metafield_theme(tmp_path, "{% render 'x',\n  a: 1,\n  b: product.metafields.custom.video_plp %}\n")
    uses, _, _ = _metafield_graph(root)
    assert [e["source_location"] for e in uses if e["confidence"] == "EXTRACTED"] == ["L3"]


def test_metafield_without_definition_warns_instead_of_raising(tmp_path):
    root = _metafield_theme(tmp_path, "{{ product.metafields.nope.missing }}\n")
    uses, nodes, _ = _metafield_graph(root)
    (use,) = uses
    node = nodes[use["target"]]
    assert use["confidence"] == "AMBIGUOUS"
    assert (node["label"], node["ref_kind"], node["unresolved"]) == ("metafields.nope.missing", "metafield", True)
    assert node["warning"] == "not defined in .shopify/metafields.json"


def test_metafield_without_definitions_file_or_with_a_hostile_one_warns(tmp_path, monkeypatch):
    from graphify.extractors import liquid

    for i, content in enumerate((None, "{[", "x" * 64)):
        sub = tmp_path / f"t{i}"
        sub.mkdir()
        if content is not None and len(content) == 64:
            monkeypatch.setattr(liquid, "_MAX_LOCALE_BYTES", 10)
        root = _metafield_theme(sub, "{{ product.metafields.custom.video_plp }}\n", content)
        uses, nodes, _ = _metafield_graph(root)
        assert nodes[uses[0]["target"]]["warning"] == "no .shopify/metafields.json"


def test_metafield_regex_is_linear_on_a_huge_line(tmp_path):
    root = _metafield_theme(tmp_path, "{{ " + "a.metafields x " * 40000 + " metafields[ " * 20000 + "a" * 500000 + " }}\n")
    start = time.perf_counter()
    extract_liquid(root / "snippets/m.liquid")
    assert time.perf_counter() - start < 2


def test_metafield_warning_shows_in_explain(tmp_path):
    graph = tmp_path / "graph.json"
    graph.write_text(json.dumps({
        "directed": True, "multigraph": False, "graph": {},
        "nodes": [{"id": "ref_a", "label": "metafields.ns.k", "file_type": "concept", "warning": "not defined in .shopify/metafields.json"}],
        "links": [],
    }), encoding="utf-8")
    out = subprocess.run(
        [sys.executable, "-m", "graphify", "explain", "metafields.ns.k", "--graph", str(graph)],
        capture_output=True, text=True, timeout=60,
    )
    assert out.returncode == 0, out.stderr
    assert "warning: not defined in .shopify/metafields.json" in out.stdout


def test_settings_in_snippets_and_unknown_ids_are_ambiguous(tmp_path):
    root = _theme(tmp_path, {
        "snippets/x.liquid": "{{ block.settings.a }}{{ section.settings.a }}\n",
        "sections/s.liquid": "{{ section.settings.nope }}{{ block.settings[var] }}\n" + _schema_text(name="S", settings=[]),
    })
    snippet = _setting_edges(root, "snippets/x.liquid")
    assert [(e["confidence"], e["node"]["ref_kind"]) for e in snippet] == [("AMBIGUOUS", "setting")] * 2
    (missing,) = _setting_edges(root, "sections/s.liquid")
    assert (missing["confidence"], missing["node"]["label"]) == ("AMBIGUOUS", "section.settings.nope")


def _css_nodes(root: Path, rel: str) -> dict[str, str]:
    result = extract_liquid(root / rel)
    assert "error" not in result
    return {n["label"]: n["source_location"] for n in result["nodes"] if n["label"][:1] in ".#"}


def test_css_liquid_selectors_keep_source_lines(tmp_path):
    body = (
        "{{ settings.c }}\n"
        ".first { color: {{ settings.c }}; }\n"
        "{% comment %}\n"
        "  .masked {}\n"
        "  {% comment %} .inner {} {% endcomment %}\n"
        "  .hidden {}\n"
        "{% endcomment %}\n"
        "{% if x %}\n"
        ".after { margin: 0 }\n"
        "{% endif %}\n"
    )
    root = _theme(tmp_path, {"assets/x.css.liquid": body})
    assert _css_nodes(root, "assets/x.css.liquid") == {".first": "L2", ".after": "L9"}


def test_css_liquid_keeps_raw_content_and_blanks_tags(tmp_path):
    body = "{% raw %}.lit {}{% endraw %}\n.real{% if a %}-x{% endif %} {}\n"
    root = _theme(tmp_path, {"assets/y.css.liquid": body})
    nodes = _css_nodes(root, "assets/y.css.liquid")
    assert ".lit" in nodes
    assert ".real" in nodes


def test_css_liquid_strip_preserves_line_structure():
    from graphify.extractors.liquid import _strip_liquid

    src = "a{% comment %}\nb{% comment %}\nc{% endcomment %}\nd{% endcomment %}\ne {{ x\n}} f\n{% if %}"
    out = _strip_liquid(src)
    assert out.count("\n") == src.count("\n")
    assert len(out) == len(src)
    assert "b" not in out and "c" not in out and "d" not in out
    assert out.startswith("a") and "e" in out and "f" in out


def test_js_liquid_import_has_no_cycle_in_a_clean_process(tmp_path):
    root = _theme(tmp_path, {"assets/a.js.liquid": "function f() {}\n"})
    code = (
        "import sys; from pathlib import Path; "
        "from graphify.extractors.liquid import extract_liquid; "
        "r = extract_liquid(Path(sys.argv[1])); "
        "assert 'error' not in r, r; "
        "assert any(n['label'] == 'f()' for n in r['nodes']), r['nodes']"
    )
    done = subprocess.run([sys.executable, "-c", code, str(root / "assets/a.js.liquid")], capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def _js_nodes(root: Path, rel: str) -> dict[str, tuple[str, str]]:
    result = extract_liquid(root / rel)
    assert "error" not in result
    return {n["label"]: (n["source_location"], n["source_file"]) for n in result["nodes"] if n.get("source_location")}


_APP_JS = (
    "(function () {\n"
    "var u = {{ 'x.js' | asset_url | json }};\n"
    "{% if a %}\n"
    "\n"
    "class CartDrawer extends HTMLElement {}\n"
    "{% endif %}\n"
    "{% comment %}\n"
    "function ghost() {}\n"
    "{% endcomment %}\n"
    "function openCart() {}\n"
    "})();\n"
)


def test_js_liquid_symbols_keep_source_lines_and_file(tmp_path):
    root = _theme(tmp_path, {"assets/app.js.liquid": _APP_JS, "assets/x.js": "// x\n"})
    nodes = _js_nodes(root, "assets/app.js.liquid")
    path = str(root / "assets/app.js.liquid")
    assert nodes["CartDrawer"] == ("L5", path)
    assert nodes["openCart()"] == ("L10", path)
    assert not any("ghost" in label for label in nodes)


def test_js_liquid_keeps_liquid_references(tmp_path):
    root = _theme(tmp_path, {"assets/app.js.liquid": _APP_JS, "assets/x.js": "// x\n"})
    result = extract_liquid(root / "assets/app.js.liquid")
    assert any(e["relation"] == "references" and e["target_file"].endswith("assets/x.js") for e in result["edges"])


def test_js_liquid_uses_no_temporary_file(tmp_path, monkeypatch):
    import tempfile

    def boom(*args, **kwargs):
        raise AssertionError("tempfile used")

    monkeypatch.setattr(tempfile, "NamedTemporaryFile", boom)
    monkeypatch.setattr(tempfile, "mkstemp", boom)
    root = _theme(tmp_path, {"assets/app.js.liquid": _APP_JS})
    assert "CartDrawer" in _js_nodes(root, "assets/app.js.liquid")


def test_stylesheet_selectors_carry_the_absolute_line_of_the_liquid_file(tmp_path):
    body = (
        "<div class=\"sec-x\">{{ section.settings.a }}</div>\n"
        "\n"
        "{% stylesheet %}\n"
        ".sec-x { color: red; }\n"
        "\n"
        "@media (min-width: 750px) { .sec-y:hover { color: blue } }\n"
        "{% endstylesheet %}\n"
        ".not-css {}\n"
    )
    root = _theme(tmp_path, {"sections/s.liquid": body})
    assert _css_nodes(root, "sections/s.liquid") == {".sec-x": "L4", ".sec-y": "L6"}


# -- custom elements (R3) ----------------------------------------------------

_EL_JS = "// el\n\ncustomElements.define('x-popover', class extends HTMLElement {});\n"


def _ce_graph(root: Path):
    from graphify.build import build_from_json

    files = sorted([*root.rglob("*.liquid"), *root.rglob("*.js")])
    return build_from_json(extract(files, cache_root=root, root=root, parallel=False), directed=True)


def _ce_edges(root: Path, rel: str) -> list[tuple[dict, dict]]:
    """(edge, target node) for the ``<x-y>`` edges leaving ``rel``."""
    result = extract_liquid(root / rel)
    nodes = {n["id"]: n for n in result["nodes"]}
    return [
        (e, nodes[e["target"]]) for e in result["edges"]
        if e["source"] == _make_id(str(root / rel)) and nodes.get(e["target"], {}).get("label", "").startswith("<")
    ]


def test_custom_element_tag_links_to_its_define(tmp_path):
    root = _theme(tmp_path, {
        "assets/el.js": _EL_JS,
        "snippets/pop.liquid": "<div>\n{% if a %}\n{% endif %}\n<x-popover open>hi</x-popover>\n",
    })
    [(edge, node)] = _ce_edges(root, "snippets/pop.liquid")
    assert (edge["relation"], edge["confidence"], edge["source_location"]) == ("references", "EXTRACTED", "L4")
    assert node["label"] == "<x-popover>"
    assert node["source_file"] == str(root / "assets/el.js") and node["source_location"] == "L3"


def test_custom_element_define_inside_js_comments_is_not_a_definition(tmp_path):
    root = _theme(tmp_path, {
        "assets/el.js": (
            "// customElements.define('x-line', class {});\n"
            "/* customElements.define('x-block', class {});\n"
            "   customElements.define('x-block2', class {}); */\n"
            "const u = \"https://example.com/a\"; customElements.define('x-real', class {});\n"
        ),
        "sections/s.liquid": (
            "{% javascript %}\n// customElements.define('x-js', class {});\n{% endjavascript %}\n"
            "<x-line></x-line><x-block></x-block><x-block2></x-block2><x-js></x-js><x-real></x-real>\n"
        ),
    })
    resolved = {n["label"]: n["source_location"] for _, n in _ce_edges(root, "sections/s.liquid") if n["source_file"].endswith("el.js")}
    assert resolved == {"<x-real>": "L4"}


def test_custom_element_in_comment_schema_and_closing_tag_makes_nothing(tmp_path):
    root = _theme(tmp_path, {
        "assets/el.js": _EL_JS,
        "snippets/pop.liquid": (
            "{% comment %}\n<x-popover>\n{% comment %}<x-popover>{% endcomment %}\n<x-popover>\n{% endcomment %}\n"
            "</x-popover>\n{% schema %}{\"name\": \"<x-popover>\"}{% endschema %}\n"
        ),
    })
    assert _ce_edges(root, "snippets/pop.liquid") == []


def test_custom_element_affected_from_the_js_lists_the_liquid(tmp_path):
    from graphify.affected import affected_nodes

    root = _theme(tmp_path, {
        "assets/el.js": _EL_JS,
        "snippets/pop.liquid": "<x-popover></x-popover>\n",
    })
    graph = _ce_graph(root)
    seed = next(n for n, d in graph.nodes(data=True) if d.get("label") == "el.js")
    sources = {str(graph.nodes[h.node_id].get("source_file")) for h in affected_nodes(graph, seed)}
    assert any(s.endswith("snippets/pop.liquid") for s in sources), sources


def test_custom_element_is_attribute_with_either_quote(tmp_path):
    root = _theme(tmp_path, {
        "assets/el.js": "customElements.define('cart-button', class {}, { extends: 'button' });\n",
        "snippets/a.liquid": "<button is=\"cart-button\"></button>\n<button is='cart-button'></button>\n",
    })
    edges = _ce_edges(root, "snippets/a.liquid")
    assert [(e["source_location"], n["label"]) for e, n in edges] == [("L1", "<cart-button>"), ("L2", "<cart-button>")]


def test_custom_element_reserved_html_names_are_not_elements(tmp_path):
    root = _theme(tmp_path, {"snippets/a.liquid": "<font-face></font-face><missing-glyph/><annotation-xml>\n"})
    assert _ce_edges(root, "snippets/a.liquid") == []
    assert _unresolved(root, "snippets/a.liquid") == []


def test_custom_element_without_a_define_is_unresolved(tmp_path):
    root = _theme(tmp_path, {"snippets/a.liquid": "<p></p>\n<judgeme-widget data-id=\"1\"></judgeme-widget>\n"})
    [(edge, node)] = _ce_edges(root, "snippets/a.liquid")
    assert (edge["confidence"], edge["source_location"]) == ("AMBIGUOUS", "L2")
    assert node["label"] == "<judgeme-widget>" and node["unresolved"] and node["ref_kind"] == "custom_element"


def test_custom_element_defined_in_a_javascript_block_resolves_from_another_file(tmp_path):
    root = _theme(tmp_path, {
        "sections/s.liquid": "{% javascript %}\n\ncustomElements.define('x-slider', class extends HTMLElement {});\n{% endjavascript %}\n",
        "snippets/a.liquid": "<x-slider></x-slider>\n",
    })
    [(edge, node)] = _ce_edges(root, "snippets/a.liquid")
    assert edge["confidence"] == "EXTRACTED"
    assert node["source_file"] == str(root / "sections/s.liquid") and node["source_location"] == "L3"


def test_custom_element_inside_liquid_tag_string_literals_counts(tmp_path):
    root = _theme(tmp_path, {
        "assets/el.js": _EL_JS,
        "snippets/a.liquid": "{% liquid\n  if a\n    echo '<x-popover open>'\n  endif\n%}\n{{ '<x-popover>' }}\n",
    })
    assert [e["source_location"] for e, _ in _ce_edges(root, "snippets/a.liquid")] == ["L3", "L6"]


# -- CSS classes (R5) --------------------------------------------------------

def _class_edges(root: Path, rel: str) -> list[tuple[str, str, str, float]]:
    """(selector label, selector file, line, score) of the INFERRED class edges leaving ``rel``."""
    result = extract_liquid(root / rel)
    nodes = {n["id"]: n for n in result["nodes"]}
    out = []
    for e in result["edges"]:
        node = nodes.get(e["target"], {})
        if e["source"] == _make_id(str(root / rel)) and e["confidence"] == "INFERRED" and node.get("label", "").startswith("."):
            assert e["relation"] == "references"
            out.append((node["label"], Path(node["source_file"]).relative_to(root).as_posix(), e["source_location"], e["confidence_score"]))
    return sorted(out, key=lambda t: (t[2], t[0], t[1]))


def test_css_class_tokens_link_to_selectors_in_css_and_css_liquid(tmp_path):
    root = _theme(tmp_path, {
        "assets/base.css": ".btn { color: red }\n",
        "assets/c.css.liquid": ".is-open { color: {{ settings.c }} }\n",
        "snippets/a.liquid": "<a class=\"btn btn--{{ x }} {% if y %}is-open{% endif %}\">\n",
    })
    assert _class_edges(root, "snippets/a.liquid") == [
        (".btn", "assets/base.css", "L1", 0.55), (".is-open", "assets/c.css.liquid", "L1", 0.55),
    ]


def test_css_class_with_escaped_characters_links_by_its_unescaped_name(tmp_path):
    root = _theme(tmp_path, {
        "assets/u.css": ".md\\:flex { display: flex }\n.w-1\\/2 { width: 50% }\n",
        "snippets/a.liquid": "<div class=\"md:flex w-1/2\"></div>\n",
    })
    assert _class_edges(root, "snippets/a.liquid") == [
        (".md:flex", "assets/u.css", "L1", 0.55), (".w-1/2", "assets/u.css", "L1", 0.55),
    ]


def test_class_index_recomputes_when_a_file_is_swapped_or_keeps_an_old_mtime(tmp_path):
    import os

    root = _theme(tmp_path, {
        "assets/a.css": ".one {}\n",
        "snippets/s.liquid": "<i class=\"one two\"></i>\n",
    })
    old = (1_000_000_000, 1_000_000_000)
    os.utime(root / "assets/a.css", old)
    assert [c[0] for c in _class_edges(root, "snippets/s.liquid")] == [".one"]
    # Same (old) mtime, different content and size.
    (root / "assets/a.css").write_text(".two  {}\n")
    os.utime(root / "assets/a.css", old)
    assert [c[0] for c in _class_edges(root, "snippets/s.liquid")] == [".two"]
    # Delete one file and add another: the file count is unchanged.
    (root / "assets/a.css").unlink()
    (root / "assets/b.css").write_text(".one {}\n")
    os.utime(root / "assets/b.css", old)
    assert [(c[0], c[1]) for c in _class_edges(root, "snippets/s.liquid")] == [(".one", "assets/b.css")]


def test_custom_element_index_recomputes_when_a_file_is_swapped(tmp_path):
    import os

    root = _theme(tmp_path, {
        "assets/a.js": "customElements.define('x-aa', class {});\n",
        "snippets/s.liquid": "<x-aa></x-aa><x-bb></x-bb>\n",
    })
    old = (1_000_000_000, 1_000_000_000)
    os.utime(root / "assets/a.js", old)
    assert [n["label"] for _, n in _ce_edges(root, "snippets/s.liquid") if n["source_file"].endswith(".js")] == ["<x-aa>"]
    (root / "assets/a.js").unlink()
    (root / "assets/b.js").write_text("customElements.define('x-bb', class {});\n")
    os.utime(root / "assets/b.js", old)
    assert [n["label"] for _, n in _ce_edges(root, "snippets/s.liquid") if n["source_file"].endswith(".js")] == ["<x-bb>"]


def test_css_class_defined_in_two_files_links_to_both(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.css": ".card {}\n", "assets/b.css": "\n.card {}\n",
        "snippets/a.liquid": "<div class='card'></div>\n",
    })
    assert _class_edges(root, "snippets/a.liquid") == [(".card", "assets/a.css", "L1", 0.55), (".card", "assets/b.css", "L1", 0.55)]


def test_css_class_multiline_attribute_with_quotes_inside_a_liquid_tag(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.css": ".x {} .y {} .z {}\n",
        "snippets/a.liquid": "<div\n  class=\"x\n    {% if a != \"\" %}y{% endif %}\n    z\">\n",
    })
    assert [(t[0], t[2]) for t in _class_edges(root, "snippets/a.liquid")] == [(".x", "L2"), (".y", "L3"), (".z", "L4")]


def test_css_class_in_comment_schema_and_data_attribute_makes_nothing(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.css": ".x {}\n",
        "snippets/a.liquid": (
            "{% comment %}<i class=\"x\">{% endcomment %}<i data-class=\"x\">"
            "{% schema %}{\"default\": \"<i class=\\\"x\\\">\"}{% endschema %}\n"
        ),
    })
    assert _class_edges(root, "snippets/a.liquid") == []


def test_css_class_defined_in_a_stylesheet_block_of_another_liquid_file(tmp_path):
    root = _theme(tmp_path, {
        "sections/s.liquid": "<p></p>\n{% stylesheet %}\n.sec-x { color: red }\n{% endstylesheet %}\n",
        "snippets/a.liquid": "<div class=\"sec-x nope\"></div>\n",
    })
    assert _class_edges(root, "snippets/a.liquid") == [(".sec-x", "sections/s.liquid", "L1", 0.55)]


def test_custom_element_scan_of_a_megabyte_of_html_is_fast(tmp_path):
    root = _theme(tmp_path, {
        "assets/el.js": _EL_JS,
        "snippets/big.liquid": "<a-b x=1></a-b>\n" * 30000 + "<x-" + "a-" * 200000 + "\n",
    })
    start = time.perf_counter()
    result = extract_liquid(root / "snippets/big.liquid")
    assert "error" not in result
    assert time.perf_counter() - start < 2
