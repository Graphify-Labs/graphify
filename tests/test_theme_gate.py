"""Tests for scripts/theme_gate.py: Liquid masking, per-category coverage, exit codes."""
from __future__ import annotations

import importlib.util
import json
import time
from pathlib import Path

import pytest

_SPEC = importlib.util.spec_from_file_location(
    "theme_gate", Path(__file__).resolve().parent.parent / "scripts" / "theme_gate.py"
)
gate = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(gate)


def _theme(tmp_path: Path, files: dict[str, str]) -> Path:
    for rel, text in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text, encoding="utf-8")
    return tmp_path


def _graph(root: Path, nodes: list[dict], links: list[dict]) -> None:
    out = root / "graphify-out"
    out.mkdir(exist_ok=True)
    (out / "graph.json").write_text(json.dumps({"nodes": nodes, "links": links}), encoding="utf-8")


def _file_node(path: str) -> dict:
    return {"id": path, "label": path.rsplit("/", 1)[-1], "source_file": path}


def _edge(src: str, tgt: str, file: str, loc: str, **kw) -> dict:
    return {"source": src, "target": tgt, "relation": "imports", "source_file": file, "source_location": loc, **kw}


def _measure(root: Path, cats: str) -> dict:
    return gate.measure(root, gate.Graph(root / "graphify-out" / "graph.json", root), cats)


# ------------------------------------------------------------------ masking

def test_mask_nested_comment_with_intermediate_endcomment():
    text = "{% comment %}a{% comment %}b{% endcomment %}{% render 'x' %}{% endcomment %}{% render 'y' %}"
    out = gate.mask_inactive(text)
    assert "'x'" not in out and "'y'" in out


def test_mask_comment_hides_output_tags_and_text_between_its_delimiters():
    text = "{% comment %}<li>{{ settings.a }}\n{{ product.metafields.n.k }}</li>{% endcomment %}{{ settings.b }}"
    out = gate.mask_inactive(text)
    assert "settings.a" not in out and "metafields" not in out and "settings.b" in out
    assert out.count("\n") == text.count("\n")


def test_mask_raw_inside_comment_hides_its_endcomment():
    text = "{% comment %}{% raw %}{% endcomment %}{% endraw %}{% render 'x' %}{% endcomment %}{% render 'y' %}"
    out = gate.mask_inactive(text)
    assert "'x'" not in out and "'y'" in out


def test_mask_doc_schema_raw_inline_and_liquid_hash_lines():
    text = (
        "{% doc %}{% render 'a' %}{% enddoc %}\n"
        "{% schema %}{\"x\": \"{% render 'b' %}\"}{% endschema %}\n"
        "{% raw %}{% render 'c' %}{% endraw %}\n"
        "{% # render 'd' %}\n"
        "{%- liquid\n  # render 'e'\n  render 'f'\n  comment\n  render 'g'\n  endcomment\n-%}\n"
    )
    out = gate.mask_inactive(text)
    for gone in ("'a'", "'b'", "'c'", "'d'", "'e'", "'g'"):
        assert gone not in out
    assert "render 'f'" in out


def test_mask_preserves_line_count_and_length():
    text = "a\n{% comment %}\nb\n{% endcomment %}\nc\n{% schema %}\n{}\n{% endschema %}\n"
    out = gate.mask_inactive(text)
    assert len(out) == len(text) and out.count("\n") == text.count("\n")


# ------------------------------------------------------------- category (a)

def _a_theme(tmp_path: Path) -> Path:
    return _theme(tmp_path, {
        "snippets/card.liquid": "<p></p>",
        "snippets/page.liquid": "{% render 'card' %}\n{% comment %}{% render 'card' %}{% endcomment %}\n{% render card_name %}\n{% render 'card' %}",
    })


def test_category_a_counts_also_seen_line_and_ignores_dynamic_and_commented_calls(tmp_path):
    root = _a_theme(tmp_path)
    _graph(root, [_file_node("snippets/page.liquid"), _file_node("snippets/card.liquid")],
           [_edge("snippets/page.liquid", "snippets/card.liquid", "snippets/page.liquid", "L4",
                  also_seen=[{"source_file": "snippets/page.liquid", "source_location": "L1"}])])
    res = _measure(root, "a")["a"]
    assert (res["covered"], res["total"]) == (2, 2)


def test_category_a_edge_from_another_file_does_not_count(tmp_path):
    root = _a_theme(tmp_path)
    _graph(root, [_file_node("snippets/page.liquid"), _file_node("snippets/card.liquid")],
           [_edge("snippets/page.liquid", "snippets/card.liquid", "snippets/page.liquid", "L4",
                  also_seen=[{"source_file": "snippets/other.liquid", "source_location": "L1"}])])
    res = _measure(root, "a")["a"]
    assert res["covered"] == 1 and res["failures"][0][:2] == ["snippets/page.liquid", 1]


def test_category_a_target_must_be_the_expected_file_not_just_the_label(tmp_path):
    root = _a_theme(tmp_path)
    wrong = {"id": "w", "label": "card.liquid", "source_file": "sections/card.liquid"}
    _graph(root, [_file_node("snippets/page.liquid"), wrong],
           [_edge("snippets/page.liquid", "w", "snippets/page.liquid", "L1"),
            _edge("snippets/page.liquid", "w", "snippets/page.liquid", "L4")])
    assert _measure(root, "a")["a"]["covered"] == 0


# ------------------------------------------------------------- category (c)

def test_category_c_needs_a_define_and_a_resolved_target(tmp_path):
    root = _theme(tmp_path, {
        "assets/x.js": "customElements.define('x-card', class {})",
        "snippets/a.liquid": "<x-card></x-card>\n<x-other></x-other>",
    })
    unresolved = {"id": "u", "label": "<x-card>", "source_file": "", "unresolved": True}
    _graph(root, [_file_node("snippets/a.liquid"), unresolved], [_edge("snippets/a.liquid", "u", "snippets/a.liquid", "L1")])
    res = _measure(root, "c")["c"]
    assert res["total"] == 1 and res["covered"] == 0
    good = {"id": "g", "label": "<x-card>", "source_file": "assets/x.js"}
    _graph(root, [_file_node("snippets/a.liquid"), good], [_edge("snippets/a.liquid", "g", "snippets/a.liquid", "L1")])
    assert _measure(root, "c")["c"]["covered"] == 1


# ------------------------------------------------------------- category (d)

def _d_theme(tmp_path: Path) -> Path:
    return _theme(tmp_path, {
        "config/settings_schema.json": json.dumps([{"name": "g", "settings": [{"type": "text", "id": "brand"}]}]),
        "sections/s.liquid": "{{ settings.brand }} {{ section.settings.title }} {{ settings.ghost }} {{ 't:settings.brand' }}\n"
                             "{% schema %}{\"settings\": [{\"type\": \"text\", \"id\": \"title\"}]}{% endschema %}",
    })


def test_category_d_definition_required_an_unresolved_edge_for_a_defined_key_is_a_miss(tmp_path):
    root = _d_theme(tmp_path)
    nodes = [_file_node("sections/s.liquid"), _file_node("config/settings_schema.json"),
             {"id": "u1", "label": "settings.brand", "source_file": "", "unresolved": True},
             {"id": "u2", "label": "section.settings.title", "source_file": "", "unresolved": True},
             {"id": "u3", "label": "settings.ghost", "source_file": "", "unresolved": True}]
    links = [_edge("sections/s.liquid", t, "sections/s.liquid", "L1") for t in ("u1", "u2", "u3")]
    _graph(root, nodes, links)
    res = _measure(root, "d")["d"]
    assert res["total"] == 3
    assert [f[2] for f in res["failures"]] == ["settings.brand", "section.settings.title"]
    assert [w[2] for w in res["warnings"]] == ["settings.ghost"]


def test_category_d_resolves_to_definition_node(tmp_path):
    root = _d_theme(tmp_path)
    nodes = [_file_node("sections/s.liquid"),
             {"id": "d1", "label": "settings.brand", "source_file": "config/settings_schema.json"},
             {"id": "d2", "label": "section.settings.title", "source_file": "sections/s.liquid"},
             {"id": "u3", "label": "settings.ghost", "source_file": "", "unresolved": True}]
    links = [_edge("sections/s.liquid", t, "sections/s.liquid", "L1") for t in ("d1", "d2", "u3")]
    _graph(root, nodes, links)
    res = _measure(root, "d")["d"]
    assert (res["covered"], res["total"]) == (3, 3) and not res["failures"]


# ------------------------------------------------------------- category (e)

def test_category_e_tokens_skip_liquid_spans_and_undefined_classes(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.css": ".btn{color:red}.is-open{color:blue}",
        "snippets/a.liquid": "<a class=\"btn btn--{{ x }} {% if y %}is-open{% endif %} nope\"></a>",
    })
    _graph(root, [_file_node("snippets/a.liquid")], [])
    res = _measure(root, "e")["e"]
    assert sorted(f[2] for f in res["failures"]) == [".btn", ".is-open"]


def test_category_e_multiline_class_attribute_with_quote_inside_liquid_tag(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.css": ".one{a:b}.two{a:b}",
        "snippets/a.liquid": "<div\n  class=\"one\n    {% if x != \"\" %}two{% endif %}\"\n></div>",
    })
    _graph(root, [_file_node("snippets/a.liquid")], [])
    res = _measure(root, "e")["e"]
    assert sorted((f[1], f[2]) for f in res["failures"]) == [(2, ".one"), (3, ".two")]


# ------------------------------------------------------------- category (b)

def test_category_b_selectors_skip_pseudo_at_rules_comments_and_declarations(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.css.liquid": "/* .gone */\n.a:hover, #b > .c{color:#fff}\n@media (min-width: 1px){.d{margin:.5em}}\n",
    })
    keys = [k for _l, k in gate.css_selectors((root / "assets/a.css.liquid").read_text())]
    assert keys == [".a", "#b", ".c", ".d"]


def test_category_b_anonymous_class_expression_is_not_a_named_case(tmp_path):
    root = _theme(tmp_path, {
        "assets/a.js.liquid": "var A = class extends Base {};\nclass Named extends Base {}\nfunction go() {}\n",
    })
    keys = [k for _f, _l, k in gate.cases_b(root)]
    assert keys == ["Named", "go"]


# ------------------------------------------------------------- category (f)

def test_category_f_without_metafields_json_every_use_is_a_miss(tmp_path):
    root = _theme(tmp_path, {"snippets/a.liquid": "{{ product.metafields.custom.size }}"})
    use = {"id": "m", "label": "metafields.custom.size", "source_file": ""}
    _graph(root, [_file_node("snippets/a.liquid"), use], [_edge("snippets/a.liquid", "m", "snippets/a.liquid", "L1")])
    assert _measure(root, "f")["f"]["covered"] == 0


def test_category_f_defined_key_needs_edge_chain_to_the_metafields_file(tmp_path):
    root = _theme(tmp_path, {
        "snippets/a.liquid": "{{ product.metafields.custom.size }}",
        ".shopify/metafields.json": json.dumps({"product": [{"namespace": "custom", "key": "size"}]}),
    })
    use = {"id": "m", "label": "metafields.custom.size", "source_file": ""}
    df = _file_node(".shopify/metafields.json")
    links = [_edge("snippets/a.liquid", "m", "snippets/a.liquid", "L1")]
    _graph(root, [_file_node("snippets/a.liquid"), use, df], links)
    assert _measure(root, "f")["f"]["covered"] == 0
    links.append(_edge("m", ".shopify/metafields.json", ".shopify/metafields.json", "L1"))
    _graph(root, [_file_node("snippets/a.liquid"), use, df], links)
    assert _measure(root, "f")["f"]["covered"] == 1


# ---------------------------------------------------------------- CLI contract

def test_exit_code_0_when_everything_is_covered(tmp_path):
    root = _a_theme(tmp_path)
    _graph(root, [_file_node("snippets/page.liquid"), _file_node("snippets/card.liquid")],
           [_edge("snippets/page.liquid", "snippets/card.liquid", "snippets/page.liquid", "L1"),
            _edge("snippets/page.liquid", "snippets/card.liquid", "snippets/page.liquid", "L4")])
    assert gate.main([str(root), "--categories", "a"]) == 0


def test_exit_code_1_and_miss_listed_as_file_line_key(tmp_path, capsys):
    root = _a_theme(tmp_path)
    _graph(root, [_file_node("snippets/page.liquid"), _file_node("snippets/card.liquid")],
           [_edge("snippets/page.liquid", "snippets/card.liquid", "snippets/page.liquid", "L1")])
    assert gate.main([str(root), "--categories", "a"]) == 1
    assert "snippets/page.liquid:4 card -> snippets/card.liquid" in capsys.readouterr().out


def test_exit_code_2_without_graph_json_or_with_bad_arguments(tmp_path):
    assert gate.main([str(tmp_path)]) == 2
    assert gate.main([str(tmp_path), "--categories", "z"]) == 2


def test_zero_cases_counts_as_full_coverage(tmp_path):
    root = _theme(tmp_path, {"snippets/a.liquid": "plain"})
    _graph(root, [], [])
    assert gate.main([str(root), "--categories", "b,c"]) == 0


def test_masking_a_megabyte_of_liquid_stays_linear(tmp_path):
    text = "{% comment %}x{% endcomment %}{% render 'a' %}\n" * 25000
    t0 = time.perf_counter()
    gate.mask_inactive(text)
    assert len(text) > 1_000_000 and time.perf_counter() - t0 < 2


def test_default_categories_measure_all_six(tmp_path):
    root = _theme(tmp_path, {"snippets/a.liquid": "plain"})
    _graph(root, [], [])
    assert gate.main([str(root)]) == 0


def test_real_extractor_covers_custom_elements_and_css_classes(tmp_path):
    from graphify.extract import extract

    root = _theme(tmp_path / "theme", {
        "layout/theme.liquid": "{{ content_for_layout }}\n",
        "assets/el.js": "customElements.define('x-popover', class extends HTMLElement {});\n",
        "assets/base.css": ".btn { color: red }\n.card { color: blue }\n",
        "snippets/a.liquid": "<x-popover open></x-popover>\n<div class=\"btn card--{{ x }} {% if y %}card{% endif %}\">\n",
        "sections/s.liquid": "<button is=\"x-popover\" class='btn nope'></button>\n",
    })
    files = sorted([*root.rglob("*.liquid"), *root.rglob("*.js"), *root.rglob("*.css")])
    result = extract(files, cache_root=root, root=root, parallel=False)
    _graph(root, result["nodes"], result["edges"])
    measured = _measure(root, "ce")
    assert (measured["c"]["covered"], measured["c"]["total"]) == (2, 2)
    assert (measured["e"]["covered"], measured["e"]["total"]) == (3, 3)


def test_category_a_call_to_a_missing_file_needs_an_unresolved_node_with_the_expected_path(tmp_path):
    root = _theme(tmp_path, {"snippets/page.liquid": "{% render 'ghost' %}"})
    ghost = {"id": "g", "label": "snippets/ghost.liquid", "source_file": "snippets/page.liquid", "unresolved": True}
    _graph(root, [_file_node("snippets/page.liquid")], [])
    assert _measure(root, "a")["a"]["covered"] == 0
    _graph(root, [_file_node("snippets/page.liquid"), ghost], [_edge("snippets/page.liquid", "g", "snippets/page.liquid", "L1")])
    assert _measure(root, "a")["a"]["covered"] == 1
