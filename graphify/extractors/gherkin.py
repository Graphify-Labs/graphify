from __future__ import annotations

from pathlib import Path
from graphify.extractors.base import _file_stem, _make_id

KEYWORDS = {
    "Feature:": "Feature",
    "Background:": "Background",
    "Scenario Outline:": "Scenario Outline",
    "Scenario:": "Scenario",
    "Examples:": "Examples",
}


def extract_gherkin(path: Path) -> dict:
    """Extract structural nodes and edges from a Gherkin (.feature) file."""
    try:
        source = path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        return {"nodes": [], "edges": [], "error": str(e)}

    stem = _file_stem(path)
    str_path = str(path)
    nodes: list[dict] = []
    edges: list[dict] = []
    seen_ids: set[str] = set()

    def add_node(nid: str, label: str, line: int, file_type: str = "document") -> None:
        if nid not in seen_ids:
            seen_ids.add(nid)
            nodes.append(
                {
                    "id": nid,
                    "label": label,
                    "file_type": file_type,
                    "source_file": str_path,
                    "source_location": f"L{line}",
                }
            )

    def add_edge(src: str, tgt: str, relation: str, line: int) -> None:
        edges.append(
            {
                "source": src,
                "target": tgt,
                "relation": relation,
                "confidence": "EXTRACTED",
                "source_file": str_path,
                "source_location": f"L{line}",
                "weight": 1.0,
            }
        )

    file_nid = _make_id(str(path))
    add_node(file_nid, path.name, 1)

    last_feature_nid = None
    last_outline_nid = None

    lines = source.splitlines()
    for line_num_0, line_text in enumerate(lines):
        line_num = line_num_0 + 1
        stripped = line_text.strip()

        # Ignore Gherkin comments
        if stripped.startswith("#"):
            continue

        # Match keywords
        keyword = None
        title = ""

        for prefix, kw in KEYWORDS.items():
            if stripped.startswith(prefix):
                keyword = kw
                title = stripped[len(prefix) :].strip()
                break

        if keyword is not None:
            # Fix Scenario Outline state bug: reset last_outline_nid when encountering
            # Scenario, Background, or Feature to prevent incorrect attachment of Examples:
            if keyword in ("Feature", "Background", "Scenario"):
                last_outline_nid = None

            label = title if title else keyword
            nid = _make_id(stem, label)
            if nid in seen_ids:
                nid = _make_id(stem, label, str(line_num))

            add_node(nid, label, line_num)

            # Determine parent and add contains edge
            if keyword == "Feature":
                parent = file_nid
                last_feature_nid = nid
            elif keyword == "Background":
                parent = last_feature_nid if last_feature_nid else file_nid
            elif keyword == "Scenario":
                parent = last_feature_nid if last_feature_nid else file_nid
            elif keyword == "Scenario Outline":
                parent = last_feature_nid if last_feature_nid else file_nid
                last_outline_nid = nid
            elif keyword == "Examples":
                parent = (
                    last_outline_nid
                    if last_outline_nid
                    else (last_feature_nid if last_feature_nid else file_nid)
                )

            add_edge(parent, nid, "contains", line_num)

    return {"nodes": nodes, "edges": edges}
