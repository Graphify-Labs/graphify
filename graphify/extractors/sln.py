"""Sln extractor. Moved verbatim from graphify/extract.py."""
from __future__ import annotations

import re

from pathlib import Path
from graphify.extractors.base import _make_id

#: Visual Studio's well-known project type GUID for a solution folder -- a
#: grouping that exists only inside the .sln, with no counterpart on disk.
_SOLUTION_FOLDER_TYPE_GUID = "2150e333-8fdc-42a3-9474-1a3956d46de8"


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
        r'Project\("([^"]*)"\)\s*=\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]*)"'
    )
    _DEP_RE = re.compile(r'\{([0-9a-fA-F-]+)\}\s*=\s*\{([0-9a-fA-F-]+)\}')

    guid_to_nid: dict[str, str] = {}

    for m in _PROJECT_RE.finditer(src):
        proj_type = m.group(1).strip("{}").lower()
        proj_name = m.group(2)
        proj_path = m.group(3).replace("\\", "/")
        proj_guid = m.group(4).strip("{}")

        # A solution folder is a VIRTUAL grouping declared only inside the .sln --
        # there is no such directory on disk -- so it is not a file and does not
        # become a node. Visual Studio marks one with this project type GUID, and
        # writes the folder name in the path position, e.g.
        #
        #   Project("{2150E333-...}") = "Solution Items", "Solution Items", "{C40B...}"
        #
        # against a real project's relative path:
        #
        #   Project("{8BC9CEB8-...}") = "jpgfltr", "jpgfltr\jpgfltr.vcproj", "{EA73...}"
        #
        # Emitting it produced a node whose source_file was a bare name with no
        # directory component and a null source_location, which reads downstream as
        # a stray unignored top-level path -- and no .graphifyignore pattern can
        # match it, because there is no path to match.
        #
        # This supersedes the earlier `proj_path == proj_name` heuristic added for
        # #1789 (resolving a folder to an absolute path leaked the scan path, and
        # the OS username with it, into graph.json). Skipping the entry entirely
        # closes that leak too, and keys off the field that actually states what
        # the entry is rather than a coincidence between two other fields -- a real
        # project whose path equals its name would have tripped the old test.
        if proj_type == _SOLUTION_FOLDER_TYPE_GUID:
            continue

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
