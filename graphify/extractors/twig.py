"""Twig template extractor (Symfony, Drupal, Craft CMS, Grav)."""
from __future__ import annotations


import re
from pathlib import Path

from graphify.extractors.base import _make_id


# Tag forms that name another template: {% extends "base.html.twig" %},
# {% include %}, {% embed %}, {% import %}, {% from %}, {% use %}.
_TAG_RE = re.compile(
    r"{%-?\s*(extends|include|embed|import|from|use)\s+['\"]([^'\"]+)['\"]"
)
# {% block content %} / {%- block content -%}
_BLOCK_RE = re.compile(r"{%-?\s*block\s+([A-Za-z_]\w*)")
# Expression-level calls, matched only inside {{ ... }} / {% ... %} (see below).
_FN_INCLUDE_RE = re.compile(r"\binclude\(\s*['\"]([^'\"]+)['\"]")
_ROUTE_RE = re.compile(r"\b(?:path|url)\(\s*['\"]([^'\"]+)['\"]")
# Twig expression/statement regions. Restricting the function-call scans to
# these avoids matching a literal `path(` or `include(` sitting in inline
# <script>/<style> content, which templates carry a lot of.
_EXPR_RE = re.compile(r"{[{%].*?[}%]}", re.DOTALL)

_RELATION_BY_TAG = {
    "extends": "extends",
    "include": "includes",
    "embed": "embeds",
    "import": "imports",
    "from": "imports",
    "use": "uses",
}


def _resolve(path: Path, ref: str) -> str:
    """Map a Twig reference to the real file it names, when that file exists.

    Twig resolves names against the loader's root rather than the current file,
    and the conventional root is a directory literally named ``templates`` in
    Symfony, Drupal, Craft and Grav alike. Walking up to that ancestor and
    joining the reference lets the target node share the *file* node's id, so
    ``{% extends "base.html.twig" %}`` becomes a real edge between two indexed
    templates instead of a dangling label.

    Anything not resolvable is returned unchanged and becomes a standalone node:
    namespaced references (``@AcmeBundle/x.html.twig``), templates supplied by a
    bundle outside the scanned tree, and dynamic names built at runtime.
    """
    for parent in path.parents:
        if parent.name == "templates":
            candidate = parent / ref
            if candidate.is_file():
                return str(candidate)
            break
    return ref


def extract_twig(path: Path) -> dict:
    """Extract template inheritance, blocks and route references from Twig.

    Nodes: the file, each referenced template, each ``{% block %}`` it defines,
    and each route named by ``path()``/``url()``. Edges: ``extends``,
    ``includes``, ``embeds``, ``imports``, ``uses``, ``defines_block`` and
    ``references_route``.

    ``references_route`` is what ties the presentation layer back to the rest of
    the graph: a route name emitted by a template resolves to the controller
    that declares it, so "what renders this action, and what does it link to"
    stops being invisible to the graph.
    """
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    nodes = [{"id": file_nid, "label": path.name, "file_type": "code",
              "source_file": str(path), "source_location": "L1"}]
    edges = []
    seen = {file_nid}

    def add(target_key: str, label: str, relation: str, offset: int) -> None:
        loc = f"L{src.count(chr(10), 0, offset) + 1}"
        nid = _make_id(target_key)
        if nid not in seen:
            seen.add(nid)
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": str(path), "source_location": loc})
        edges.append({"source": file_nid, "target": nid, "relation": relation,
                      "confidence": "EXTRACTED", "confidence_score": 1.0,
                      "source_file": str(path), "source_location": loc,
                      "weight": 1.0})

    for m in _TAG_RE.finditer(src):
        ref = m.group(2)
        add(_resolve(path, ref), Path(ref).name, _RELATION_BY_TAG[m.group(1)], m.start())

    for m in _BLOCK_RE.finditer(src):
        add(f"{path}::block::{m.group(1)}", m.group(1), "defines_block", m.start())

    for expr in _EXPR_RE.finditer(src):
        body, base = expr.group(0), expr.start()
        for m in _FN_INCLUDE_RE.finditer(body):
            ref = m.group(1)
            add(_resolve(path, ref), Path(ref).name, "includes", base + m.start())
        for m in _ROUTE_RE.finditer(body):
            add(m.group(1), m.group(1), "references_route", base + m.start())

    return {"nodes": nodes, "edges": edges}
