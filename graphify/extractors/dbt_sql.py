"""dbt model SQL extractor: ref()/source() lineage via Jinja2 AST parsing."""
from __future__ import annotations

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id

# Sniffs for any Jinja delimiter rather than specific markers like ref(/source( —
# a model gated entirely by {% if %}/{% for %} would evade a narrower check.
_SNIFF_BYTES = 4096


def _is_dbt_model_sql(path: Path) -> bool:
    """Whether a `.sql` file is Jinja-templated (dbt model or macro) rather than plain SQL."""
    try:
        head = path.read_bytes()[:_SNIFF_BYTES]
    except OSError:
        return False
    return b"{{" in head or b"{%" in head


def extract_dbt_sql(path: Path, content: str | bytes | None = None) -> dict:
    """Extract ref()/source() lineage edges from a dbt model .sql file."""
    try:
        import jinja2
        from jinja2 import nodes as jinja_nodes
    except ImportError:
        return {"nodes": [], "edges": [], "error": "jinja2 not installed. Run: pip install jinja2"}

    source = (
        content if isinstance(content, str)
        else content.decode("utf-8", errors="replace") if content is not None
        else path.read_text(encoding="utf-8", errors="replace")
    )

    stem = _file_stem(path)
    str_path = str(path)
    model_nid = _make_id(stem)
    nodes: list[dict] = [{"id": model_nid, "label": path.stem, "file_type": "code",
                           "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = {model_nid}

    try:
        ast = jinja2.Environment().parse(source)
    except jinja2.exceptions.TemplateSyntaxError as e:
        return {"nodes": nodes, "edges": edges, "error": f"TemplateSyntaxError: {e}"}

    def _add_target(nid: str, label: str) -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            # No origin_file: tagging it would make each caller's stub for the
            # same target look like a different entity and split them apart.
            nodes.append({"id": nid, "label": label, "file_type": "code",
                          "source_file": "", "source_location": ""})

    def _const_args(call: jinja_nodes.Call) -> list[str] | None:
        """Positional arg values if every one is a literal string, else None."""
        try:
            values = [a.as_const() for a in call.args]
        except jinja_nodes.Impossible:
            return None
        if not all(isinstance(v, str) for v in values):
            return None
        return values

    for call in ast.find_all(jinja_nodes.Call):
        fn_name = getattr(call.node, "name", None)
        if fn_name == "ref":
            args = _const_args(call)
            if not args:
                continue
            # ref('model') or ref('package', 'model') both resolve on the model name.
            name = args[-1]
            tgt_nid = _make_id(name)
            _add_target(tgt_nid, name)
            edges.append({"source": model_nid, "target": tgt_nid, "relation": "depends_on",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": str_path, "source_location": f"L{call.lineno}", "weight": 1.0})
        elif fn_name == "source":
            args = _const_args(call)
            if not args or len(args) < 2:
                continue
            schema, table = args[0], args[1]
            label = f"{schema}.{table}"
            tgt_nid = _make_id(label)
            _add_target(tgt_nid, label)
            edges.append({"source": model_nid, "target": tgt_nid, "relation": "reads_from",
                          "confidence": "EXTRACTED", "confidence_score": 1.0,
                          "source_file": str_path, "source_location": f"L{call.lineno}", "weight": 1.0})

    return {"nodes": nodes, "edges": edges}
