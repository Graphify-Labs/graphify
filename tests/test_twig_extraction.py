"""Tests for ``.twig`` template extraction.

Twig templates carry the whole presentation layer of Symfony, Drupal, Craft and
Grav projects, and none of it reached the graph before :func:`extract_twig`: the
extension was absent from ``CODE_EXTENSIONS``, so the files were never even
walked. These tests pin the inheritance chain, the block definitions, and the
``path()``/``url()`` calls that tie a template back to its controller.
"""
from __future__ import annotations

from pathlib import Path

from graphify.detect import CODE_EXTENSIONS
from graphify.extract import _get_extractor, _make_id
from graphify.extractors.twig import extract_twig


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def _targets(result: dict, *, relation: str | None = None) -> set[str]:
    return {
        str(e.get("target") or "")
        for e in result.get("edges", [])
        if relation is None or e.get("relation") == relation
    }


def _labels(result: dict, *, relation: str | None = None) -> set[str]:
    by_id = {n["id"]: str(n.get("label") or "") for n in result.get("nodes", [])}
    return {by_id[t] for t in _targets(result, relation=relation) if t in by_id}


def test_twig_is_in_code_extensions():
    assert ".twig" in CODE_EXTENSIONS


def test_twig_files_dispatch_to_the_twig_extractor():
    assert _get_extractor(Path("templates/base.html.twig")) is extract_twig
    # The double extension is the norm in Symfony; suffix matching must not care.
    assert _get_extractor(Path("templates/admin/list.html.twig")) is extract_twig


def test_extends_resolves_to_the_real_template_file(tmp_path):
    """A resolved reference shares the target file's node id, forming a real edge."""
    base = _write(tmp_path / "templates/base.html.twig", "<html></html>\n")
    child = _write(
        tmp_path / "templates/admin/list.html.twig",
        '{% extends "base.html.twig" %}\n',
    )
    result = extract_twig(child)
    assert _make_id(str(base)) in _targets(result, relation="extends")


def test_nested_reference_resolves_from_the_templates_root(tmp_path):
    """Twig resolves against the loader root, not the including file's directory."""
    partial = _write(tmp_path / "templates/velzon/_topbar.html.twig", "<nav></nav>\n")
    page = _write(
        tmp_path / "templates/admin/desk/index.html.twig",
        '{% include "velzon/_topbar.html.twig" %}\n',
    )
    result = extract_twig(page)
    assert _make_id(str(partial)) in _targets(result, relation="includes")


def test_every_reference_tag_maps_to_its_relation(tmp_path):
    page = _write(
        tmp_path / "templates/page.html.twig",
        """{% extends "layout.html.twig" %}
{% include "partial.html.twig" %}
{% embed "card.html.twig" %}{% endembed %}
{% import "macros.html.twig" as m %}
{% from "forms.html.twig" import field %}
{% use "blocks.html.twig" %}
""",
    )
    result = extract_twig(page)
    assert _labels(result, relation="extends") == {"layout.html.twig"}
    assert _labels(result, relation="includes") == {"partial.html.twig"}
    assert _labels(result, relation="embeds") == {"card.html.twig"}
    assert _labels(result, relation="uses") == {"blocks.html.twig"}
    # {% import %} and {% from %} both express a macro import.
    assert _labels(result, relation="imports") == {"macros.html.twig", "forms.html.twig"}


def test_whitespace_control_markers_are_tolerated(tmp_path):
    page = _write(
        tmp_path / "templates/trim.html.twig",
        '{%- extends "layout.html.twig" -%}\n{%- block body -%}{%- endblock -%}\n',
    )
    result = extract_twig(page)
    assert _labels(result, relation="extends") == {"layout.html.twig"}
    assert _labels(result, relation="defines_block") == {"body"}


def test_function_form_include_is_extracted(tmp_path):
    page = _write(
        tmp_path / "templates/fn.html.twig",
        "{{ include('partial.html.twig', {foo: 1}) }}\n",
    )
    result = extract_twig(page)
    assert _labels(result, relation="includes") == {"partial.html.twig"}


def test_blocks_are_scoped_to_their_file(tmp_path):
    """Two templates defining `content` must not collapse onto one block node."""
    a = _write(tmp_path / "templates/a.html.twig", "{% block content %}{% endblock %}\n")
    b = _write(tmp_path / "templates/b.html.twig", "{% block content %}{% endblock %}\n")
    ta = _targets(extract_twig(a), relation="defines_block")
    tb = _targets(extract_twig(b), relation="defines_block")
    assert ta and tb and ta != tb


def test_path_and_url_calls_become_route_references(tmp_path):
    page = _write(
        tmp_path / "templates/nav.html.twig",
        """<a href="{{ path('admin_desk_index') }}">desks</a>
<a href="{{ url('admin_boutique_edit', {id: b.id}) }}">edit</a>
""",
    )
    result = extract_twig(page)
    assert _labels(result, relation="references_route") == {
        "admin_desk_index",
        "admin_boutique_edit",
    }


def test_function_scans_ignore_inline_script_and_style(tmp_path):
    """`path(` outside a Twig expression is page content, not a route reference."""
    page = _write(
        tmp_path / "templates/inline.html.twig",
        """<script>
  function path(name) { return name }
  path('not-a-route');
  const tpl = include('not-a-template');
</script>
<a href="{{ path('real_route') }}">go</a>
""",
    )
    result = extract_twig(page)
    assert _labels(result, relation="references_route") == {"real_route"}
    assert _targets(result, relation="includes") == set()


def test_namespaced_reference_stays_unresolved_without_crashing(tmp_path):
    """`@Bundle/...` names a template outside the scanned tree; keep it as a label."""
    page = _write(
        tmp_path / "templates/ns.html.twig",
        '{% extends "@AcmeBundle/layout.html.twig" %}\n',
    )
    result = extract_twig(page)
    assert _labels(result, relation="extends") == {"layout.html.twig"}


def test_reference_to_a_missing_file_is_kept_as_a_label(tmp_path):
    page = _write(
        tmp_path / "templates/missing.html.twig",
        '{% include "does/not/exist.html.twig" %}\n',
    )
    result = extract_twig(page)
    # Unresolvable, so it is not the file id, but the edge still exists.
    assert _labels(result, relation="includes") == {"exist.html.twig"}


def test_line_numbers_point_at_the_directive(tmp_path):
    page = _write(
        tmp_path / "templates/lines.html.twig",
        '\n\n{% extends "layout.html.twig" %}\n\n{% block body %}{% endblock %}\n',
    )
    result = extract_twig(page)
    by_label = {n["label"]: n["source_location"] for n in result["nodes"]}
    assert by_label["layout.html.twig"] == "L3"
    assert by_label["body"] == "L5"


def test_plain_markup_yields_only_the_file_node(tmp_path):
    page = _write(tmp_path / "templates/static.html.twig", "<h1>hi</h1>\n")
    result = extract_twig(page)
    assert len(result["nodes"]) == 1
    assert result["edges"] == []


def test_unreadable_file_reports_an_error_instead_of_raising(tmp_path):
    missing = tmp_path / "templates/gone.html.twig"
    result = extract_twig(missing)
    assert "error" in result
