"""Sln extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _make_id


def extract_sln(path: Path) -> dict:
    """Extract projects and inter-project dependencies from a .sln file."""
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {"nodes": [], "edges": [], "error": f"cannot read {path}"}

    file_nid = _make_id(str(path))
    str_path = str(path)
    nodes: list[dict] = [{"id": file_nid, "label": path.name, "file_type": "code",
                          "source_file": str_path, "source_location": None}]
    edges: list[dict] = []
    seen_ids: set[str] = set()
    seen_ids.add(file_nid)

    _PROJECT_RE = re.compile(
        r'Project\("[^"]*"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"'
    )
    _DEP_RE = re.compile(r'\{([0-9a-fA-F-]+)\}\s*=\s*\{([0-9a-fA-F-]+)\}')

    guid_to_nid: dict[str, str] = {}

    for m in _PROJECT_RE.finditer(src):
        proj_name = m.group(1)
        proj_path = m.group(2).replace("\\", "/")
        proj_guid = m.group(3).strip("{}")

        # A solution folder is a VIRTUAL grouping, not a file: Visual Studio writes
        # its name as both the display name and the "path" (proj_name == proj_path,
        # no real file). Resolving it to an absolute path and keying the node id off
        # that leaked the absolute scan path (incl. the OS username) into graph.json,
        # because the CLI's id-relativization only remaps ids of real files in the
        # scan set — a virtual folder never matches, so its absolute id survived
        # (#1789). Use the folder name itself (relative, no filesystem resolution).
        is_solution_folder = proj_path == proj_name
        if is_solution_folder:
            abs_proj = proj_name
        else:
            try:
                abs_proj = str((path.parent / proj_path).resolve())
            except Exception:
                abs_proj = proj_path
        proj_nid = _make_id(abs_proj)
        if proj_nid and proj_nid not in seen_ids:
            seen_ids.add(proj_nid)
            nodes.append({"id": proj_nid, "label": proj_name,
                          "file_type": "code", "source_file": abs_proj,
                          "source_location": None})
            edges.append({"source": file_nid, "target": proj_nid,
                          "relation": "contains", "confidence": "EXTRACTED",
                          "source_file": str_path, "weight": 1.0})
        if proj_guid:
            guid_to_nid[proj_guid.lower()] = proj_nid

    in_dep_section = False
    current_proj_guid: str | None = None
    _PROJECT_LINE_RE = re.compile(r'Project\("[^"]*"\)\s*=\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*"\{([^}]+)\}"')
    for line in src.splitlines():
        proj_line_m = _PROJECT_LINE_RE.search(line)
        if proj_line_m:
            current_proj_guid = proj_line_m.group(1).lower()
            continue
        if line.strip() == "EndProject":
            current_proj_guid = None
            continue
        if "ProjectSection(ProjectDependencies)" in line:
            in_dep_section = True
            continue
        if in_dep_section and "EndProjectSection" in line:
            in_dep_section = False
            continue
        if in_dep_section and current_proj_guid:
            dep_m = _DEP_RE.search(line)
            if dep_m:
                to_guid = dep_m.group(1).lower()
                from_nid = guid_to_nid.get(current_proj_guid)
                to_nid = guid_to_nid.get(to_guid)
                if from_nid and to_nid and from_nid != to_nid:
                    edges.append({"source": from_nid, "target": to_nid,
                                  "relation": "imports", "confidence": "EXTRACTED",
                                  "source_file": str_path, "weight": 1.0})

    return {"nodes": nodes, "edges": edges}
