"""Extraction coverage for Shopify theme JSON (templates, section groups, schema keys).

In an Online Store 2.0 theme the page structure lives in `templates/*.json` and
`sections/*-group.json`. Without an extractor those files were skipped as data
JSON, so "which pages use this section" had no answer. Routing is gated on a theme
root (a `layout/theme.liquid` ancestor).
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

from graphify.extract import _get_extractor, _make_id, extract, extract_liquid

FIXTURE = Path(__file__).parent / "fixtures" / "liquid_theme"


def _theme(tmp_path: Path, files: dict[str, str]) -> Path:
    root = tmp_path / "theme"
    root.mkdir()
    base = {"layout/theme.liquid": "{{ content_for_layout }}\n"}
    for rel, body in {**base, **files}.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body, encoding="utf-8")
    return root


def _run(root: Path, rel: str) -> dict:
    path = root / rel
    func = _get_extractor(path)
    assert func is not None
    result = func(path)
    assert "error" not in result
    return result


def _edges(root: Path, rel: str) -> list[dict]:
    return _run(root, rel)["edges"]


def _placed(root: Path, rel: str) -> list[str]:
    """Theme-relative target files of the EXTRACTED edges, in order."""
    return [
        Path(e["target_file"]).relative_to(root).as_posix()
        for e in _edges(root, rel)
        if e["confidence"] == "EXTRACTED" and e.get("target_file")
    ]


def _unresolved(root: Path, rel: str) -> list[tuple[str, str]]:
    result = _run(root, rel)
    nodes = {n["id"]: n for n in result["nodes"]}
    return [
        (nodes[e["target"]]["ref_kind"], nodes[e["target"]]["label"])
        for e in result["edges"]
        if e["confidence"] == "AMBIGUOUS"
    ]


def test_settings_schema_file_node_contains_each_setting(tmp_path):
    schema = (
        '/* c */\n[{"name": "theme_info"},\n {"name": "G", "settings": [\n'
        '  {"type": "header", "content": "H"},\n  {"type": "checkbox", "id": "show_breadcrumbs"}\n ]}]\n'
    )
    root = _theme(tmp_path, {"config/settings_schema.json": schema})
    result = _run(root, "config/settings_schema.json")
    nodes = {n["id"]: n for n in result["nodes"]}
    file_id = _make_id(str(root / "config" / "settings_schema.json"))
    contained = [nodes[e["target"]] for e in result["edges"] if e["source"] == file_id and e["relation"] == "contains"]
    assert [n["label"] for n in contained] == ["settings.show_breadcrumbs"]
    assert contained[0]["source_location"] == "L5"
    assert Path(contained[0]["source_file"]) == root / "config" / "settings_schema.json"


def test_registered():
    from graphify.extractors import LANGUAGE_EXTRACTORS
    from graphify.extractors.shopify_theme_json import extract_shopify_theme_json

    assert LANGUAGE_EXTRACTORS["shopify_theme_json"] is extract_shopify_theme_json


def test_tracer_template_reaches_affected(tmp_path):
    import networkx as nx

    from graphify.affected import affected_nodes
    from graphify.build import build_from_json

    theme = tmp_path / "theme"
    shutil.copytree(FIXTURE, theme)
    files = sorted(theme.rglob("*.liquid")) + sorted(theme.rglob("*.json"))
    extraction = extract(files, cache_root=theme, root=theme, parallel=False)
    graph = build_from_json(extraction, directed=True)
    assert isinstance(graph, nx.DiGraph)
    seed = next(
        n for n, d in graph.nodes(data=True)
        if str(d.get("source_file", "")).endswith("sections/featured.liquid") and d.get("label") == "featured.liquid"
    )
    sources = {graph.nodes[h.node_id].get("source_file") for h in affected_nodes(graph, seed)}
    assert any(str(s).endswith("templates/index.json") for s in sources), sources


def test_template_with_schema_key_routes_to_theme_extractor(tmp_path):
    from graphify.extractors.shopify_theme_json import extract_shopify_theme_json

    root = _theme(tmp_path, {
        "sections/hero.liquid": "",
        "templates/index.json": json.dumps({
            "$schema": "https://example.invalid/schema.json",
            "sections": {"a": {"type": "hero"}},
        }),
    })
    assert _get_extractor(root / "templates/index.json") is extract_shopify_theme_json
    assert _placed(root, "templates/index.json") == ["sections/hero.liquid"]


def test_banner_is_ignored(tmp_path):
    body = "/* auto-generated */\n" + json.dumps({"sections": {"a": {"type": "hero"}}})
    root = _theme(tmp_path, {"sections/hero.liquid": "", "templates/page.json": body})
    assert _placed(root, "templates/page.json") == ["sections/hero.liquid"]


def test_group_and_context_variant(tmp_path):
    group = json.dumps({"sections": {"h": {"type": "header"}}, "order": ["h"]})
    root = _theme(tmp_path, {
        "sections/header.liquid": "",
        "sections/header-group.json": group,
        "sections/header-group.context.market-a.json": group,
    })
    assert _placed(root, "sections/header-group.json") == ["sections/header.liquid"]
    assert _placed(root, "sections/header-group.context.market-a.json") == ["sections/header.liquid"]


def test_empty_and_layout_only_templates_give_only_the_file_node(tmp_path):
    root = _theme(tmp_path, {
        "templates/a.json": '{"sections": {}, "order": []}',
        "templates/b.json": '{"layout": "alternate"}',
    })
    for rel in ("templates/a.json", "templates/b.json"):
        result = _run(root, rel)
        assert len(result["nodes"]) == 1 and result["edges"] == []


def test_unparsable_json_gives_only_the_file_node(tmp_path):
    root = _theme(tmp_path, {"templates/a.json": "{ not json"})
    result = _run(root, "templates/a.json")
    assert len(result["nodes"]) == 1 and result["edges"] == []


def test_key_order_does_not_change_extraction(tmp_path):
    root = _theme(tmp_path, {
        "sections/a.liquid": "",
        "sections/b.liquid": "",
        "blocks/card.liquid": "",
        "templates/one.json": json.dumps({"sections": {
            "x": {"type": "b", "blocks": {"m": {"type": "card"}}},
            "y": {"type": "a"},
        }}),
        "templates/two.json": json.dumps({"sections": {
            "y": {"type": "a"},
            "x": {"blocks": {"m": {"type": "card"}}, "type": "b"},
        }}),
    })

    def shape(rel: str) -> list[tuple[str, str, str]]:
        return [(e["relation"], Path(e["target_file"]).name, e["source_location"]) for e in _edges(root, rel)]

    assert shape("templates/one.json") == shape("templates/two.json")
    assert len(shape("templates/one.json")) == 3


def test_nested_blocks_link_only_existing_block_files(tmp_path):
    root = _theme(tmp_path, {
        "sections/a.liquid": "",
        "blocks/card.liquid": "",
        "templates/t.json": json.dumps({"sections": {"s": {"type": "a", "blocks": {
            "b1": {"type": "card", "blocks": {"deep": {"type": "card"}}},
            "b2": {"type": "local-only"},
            "b3": {"type": "@app"},
        }}}}),
    })
    assert _placed(root, "templates/t.json") == ["sections/a.liquid", "blocks/card.liquid"]
    assert _unresolved(root, "templates/t.json") == []


def test_app_section_ignored_and_missing_section_unresolved(tmp_path):
    root = _theme(tmp_path, {
        "templates/t.json": json.dumps({"sections": {
            "a": {"type": "shopify://apps/x/blocks/y/abc"},
            "b": {"type": "ghost"},
        }}),
    })
    assert _placed(root, "templates/t.json") == []
    assert _unresolved(root, "templates/t.json") == [("section", "sections/ghost.liquid")]


def test_builtin_blocks_section_is_not_a_missing_file_but_its_blocks_link(tmp_path):
    root = _theme(tmp_path, {
        "blocks/card.liquid": "",
        "templates/t.json": json.dumps({"sections": {"s": {
            "type": "_blocks", "blocks": {"b": {"type": "card"}},
        }}}),
    })
    assert _placed(root, "templates/t.json") == ["blocks/card.liquid"]
    assert _unresolved(root, "templates/t.json") == []


def test_unsafe_section_type_gets_nothing(tmp_path):
    root = _theme(tmp_path, {
        "templates/t.json": json.dumps({"sections": {"a": {"type": "../layout/theme"}}}),
    })
    assert _edges(root, "templates/t.json") == []


def test_json_outside_a_theme_keeps_generic_routing(tmp_path):
    from graphify.extractors.json_config import extract_json

    repo = tmp_path / "repo"
    (repo / "templates").mkdir(parents=True)
    f = repo / "templates" / "x.json"
    f.write_text(json.dumps({"sections": {"a": {"type": "hero"}}}), encoding="utf-8")
    assert _get_extractor(f) is extract_json


def test_depth_and_unrelated_json_are_not_routed(tmp_path):
    from graphify.extractors.shopify_theme_json import is_shopify_theme_json_path

    root = _theme(tmp_path, {
        "templates/customers/login.json": "{}",
        "templates/a/b/too-deep.json": "{}",
        "locales/en.default.json": "{}",
        "config/settings_data.json": "{}",
        "sections/nested/x.json": "{}",
    })
    assert is_shopify_theme_json_path(root / "templates/customers/login.json")
    assert not is_shopify_theme_json_path(root / "templates/a/b/too-deep.json")
    assert not is_shopify_theme_json_path(root / "locales/en.default.json")
    assert is_shopify_theme_json_path(root / "config/settings_data.json")
    assert not is_shopify_theme_json_path(root / "config/other.json")
    assert not is_shopify_theme_json_path(root / "sections/nested/x.json")


def test_settings_data_places_current_and_preset_sections(tmp_path):
    from graphify.extractors.shopify_theme_json import extract_shopify_theme_json

    data = json.dumps({
        "current": {
            "sections": {"a": {"type": "hero", "blocks": {"b": {"type": "card"}, "c": {"type": "@app"}}}},
            "order": ["a"],
            "color": "#fff",
        },
        "presets": {"Alt": {"sections": {"x": {"type": "footer"}}}},
    })
    root = _theme(tmp_path, {
        "sections/hero.liquid": "", "sections/footer.liquid": "", "blocks/card.liquid": "",
        "config/settings_data.json": data,
    })
    assert _get_extractor(root / "config/settings_data.json") is extract_shopify_theme_json
    assert _placed(root, "config/settings_data.json") == [
        "sections/hero.liquid", "blocks/card.liquid", "sections/footer.liquid",
    ]
    assert _unresolved(root, "config/settings_data.json") == []

    (tmp_path / "s").mkdir()
    root2 = _theme(tmp_path / "s", {"config/settings_data.json": json.dumps({"current": "Default", "presets": {}})})
    assert len(_run(root2, "config/settings_data.json")["edges"]) == 0


SCHEMA_LOCALE = json.dumps({"sections": {"featured": {"name": "Featured"}}, "settings": {"colors": "Colors"}})


def test_schema_t_keys_in_liquid_schema_and_settings_schema(tmp_path):
    root = _theme(tmp_path, {
        "locales/en.default.schema.json": SCHEMA_LOCALE,
        "sections/featured.liquid": (
            "{% schema %}\n"
            '{"name": "t:sections.featured.name", "settings": [{"label": "t:sections.nope.label"}]}\n'
            "{% endschema %}\n"
        ),
        "config/settings_schema.json": json.dumps([{"name": "t:settings.colors"}, {"name": "t:settings.gone"}]),
    })
    liquid = extract_liquid(root / "sections/featured.liquid")
    by_target = {e["target"]: e for e in liquid["edges"]}
    ok = _make_id("liquid_t_schema", "sections.featured.name")
    assert by_target[ok]["relation"] == "references" and by_target[ok]["confidence"] == "EXTRACTED"
    assert [n["ref_kind"] for n in liquid["nodes"] if n.get("unresolved")] == ["schema_t"]

    settings = _run(root, "config/settings_schema.json")
    ids = {e["target"] for e in settings["edges"] if e["confidence"] == "EXTRACTED"}
    assert ids == {_make_id("liquid_t_schema", "settings.colors")}
    assert [n["ref_kind"] for n in settings["nodes"] if n.get("unresolved")] == ["schema_t"]


def test_schema_t_keys_need_exactly_one_default_schema_locale(tmp_path):
    root = _theme(tmp_path, {
        "sections/featured.liquid": '{% schema %}{"name": "t:sections.featured.name"}{% endschema %}',
    })
    assert extract_liquid(root / "sections/featured.liquid")["edges"] == []
    (root / "locales").mkdir()
    (root / "locales" / "en.default.schema.json").write_text(SCHEMA_LOCALE, encoding="utf-8")
    (root / "locales" / "fr.default.schema.json").write_text(SCHEMA_LOCALE, encoding="utf-8")
    assert extract_liquid(root / "sections/featured.liquid")["edges"] == []
