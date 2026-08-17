"""Deterministic ingestion and validation for ``lat.md`` knowledge lattices.

Graphify treats curated lattice sections as first-class graph nodes while keeping
lat.md's Markdown files as the source of truth.  No Node.js runtime or lat CLI is
required: the supported interchange subset is headings, first-paragraph
summaries, ``[[wiki links]]``, ``@lat`` code comments, and the
``require-code-mention`` frontmatter flag.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Iterable

from graphify.extractors.base import _make_id

__all__ = [
    "extract_lattice_markdown",
    "extract_lattice_code_ref_edges",
    "is_lattice_markdown_path",
    "project_source_paths",
    "resolve_lattice_reference_edges",
    "validate_lattice",
]

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
_WIKI_RE = re.compile(r"\[\[([^\]|]+?)(?:\|[^\]]+)?\]\]")
_CODE_REF_RE = re.compile(r"(?:#|//)\s*@lat:\s*\[\[([^\]]+)\]\]")
_INLINE_CODE_RE = re.compile(r"`+[^`]*?`+")
_MAX_FILE_BYTES = 2_000_000


def _lattice_dir(path: Path) -> Path | None:
    path = path.resolve()
    for parent in (path.parent, *path.parents):
        if parent.name == "lat.md":
            return parent
    return None


def is_lattice_markdown_path(path: Path) -> bool:
    """Return whether *path* is a Markdown file inside a ``lat.md/`` directory."""
    return path.suffix.lower() == ".md" and _lattice_dir(path) is not None


def _file_key(path: Path, lattice_dir: Path) -> str:
    return path.resolve().relative_to(lattice_dir).with_suffix("").as_posix()


def _knowledge_node_id(knowledge_id: str) -> str:
    return _make_id("knowledge", knowledge_id)


def _edge(
    source: str,
    target: str,
    relation: str,
    source_file: str,
    line: int,
    **extra: Any,
) -> dict[str, Any]:
    edge: dict[str, Any] = {
        "source": source,
        "target": target,
        "relation": relation,
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": source_file,
        "source_location": f"L{line}",
        "weight": 1.0,
    }
    edge.update(extra)
    return edge


def _wiki_refs(lines: list[str], start: int, end: int) -> list[tuple[str, int]]:
    """Return real wiki links, excluding fenced and inline-code examples."""
    refs: list[tuple[str, int]] = []
    in_fence = False
    for line_number in range(start, end + 1):
        line = lines[line_number - 1]
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        searchable = _INLINE_CODE_RE.sub("", line)
        refs.extend(
            (match.group(1).strip(), line_number) for match in _WIKI_RE.finditer(searchable)
        )
    return refs


def _source_target(target: str, project_root: Path) -> tuple[Path | None, str | None]:
    file_part = target.split("#", 1)[0]
    candidate = project_root / file_part
    # A dot is legal in a lattice filename (for example operations.v2.md), so a
    # suffix alone cannot distinguish knowledge from code. Existing files and
    # explicit relative paths such as src/service.py are source references.
    if not candidate.is_file() and "/" not in file_part.replace("\\", "/"):
        return None, None
    try:
        resolved = candidate.resolve()
        resolved.relative_to(project_root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None, "source reference escapes project root"
    return resolved, None


def extract_lattice_markdown(path: Path) -> dict[str, Any]:
    """Extract stable knowledge-section nodes from one lattice Markdown file."""
    lattice_dir = _lattice_dir(path)
    if lattice_dir is None or path.suffix.lower() != ".md":
        return {"nodes": [], "edges": []}
    try:
        if path.stat().st_size > _MAX_FILE_BYTES:
            return {"nodes": [], "edges": [], "error": "lattice file too large to index"}
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return {"nodes": [], "edges": [], "error": f"lattice read error: {exc}"}

    file_key = _file_key(path, lattice_dir)
    source_file = str(path)
    lines = text.splitlines()
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []
    sections: list[dict[str, Any]] = []
    stack: list[dict[str, Any]] = []
    in_fence = False

    for index, line in enumerate(lines, start=1):
        if line.strip().startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        match = _HEADING_RE.match(line)
        if not match:
            continue
        depth = len(match.group(1))
        heading = match.group(2).strip()
        while stack and stack[-1]["depth"] >= depth:
            stack.pop()
        parent = stack[-1] if stack else None
        knowledge_id = f"{parent['knowledge_id']}#{heading}" if parent else f"{file_key}#{heading}"
        section = {
            "knowledge_id": knowledge_id,
            "heading": heading,
            "depth": depth,
            "line": index,
            "parent": parent,
        }
        sections.append(section)
        stack.append(section)

    for position, section in enumerate(sections):
        start = section["line"]
        end = sections[position + 1]["line"] - 1 if position + 1 < len(sections) else len(lines)
        paragraph: list[str] = []
        started = False
        for raw in lines[start:end]:
            stripped = raw.strip()
            if not stripped:
                if started:
                    break
                continue
            if stripped.startswith(("```", "---")):
                continue
            started = True
            paragraph.append(stripped)
        summary = " ".join(paragraph)
        knowledge_id = section["knowledge_id"]
        node_id = _knowledge_node_id(knowledge_id)
        nodes.append(
            {
                "id": node_id,
                "label": section["heading"],
                "file_type": "document",
                "type": "knowledge_section",
                "knowledge_id": knowledge_id,
                "summary": summary,
                "source_file": source_file,
                "source_location": f"L{section['line']}",
            }
        )
        parent = section["parent"]
        if parent is not None:
            edges.append(
                _edge(
                    _knowledge_node_id(parent["knowledge_id"]),
                    node_id,
                    "contains",
                    source_file,
                    section["line"],
                )
            )
        for target, reference_line in _wiki_refs(lines, start, end):
            if target.startswith("#"):
                target = f"{file_key}{target}"
            source_target, source_error = _source_target(target, lattice_dir.parent)
            if source_target is not None or source_error is not None:
                edges.append(
                    _edge(
                        node_id,
                        _make_id(str(source_target))
                        if source_target is not None
                        else "invalid_source",
                        "documents",
                        source_file,
                        reference_line,
                        source_target=target,
                        target_file=(
                            str(source_target)
                            if source_target is not None and source_target.is_file()
                            else None
                        ),
                        source_reference_error=source_error,
                    )
                )
            else:
                edges.append(
                    _edge(
                        node_id,
                        _knowledge_node_id(target),
                        "references",
                        source_file,
                        reference_line,
                        knowledge_target=target,
                    )
                )

    return {"nodes": nodes, "edges": edges, "input_tokens": 0, "output_tokens": 0}


def _resolve_ref(target: str, knowledge_ids: Iterable[str]) -> tuple[str | None, list[str]]:
    ids = list(knowledge_ids)
    lowered = {item.lower(): item for item in ids}
    exact = lowered.get(target.lower())
    if exact is not None:
        return exact, []
    target_lower = target.lower()
    # A bare ref names a lattice file before it names an arbitrary heading.
    # `[[locate]]` therefore resolves to `tests/locate.md` when that basename is
    # unique, even if another document has a child heading named "locate".
    if "#" not in target:
        file_keys = {
            item.split("#", 1)[0]
            for item in ids
            if item.split("#", 1)[0].lower() == target_lower
            or item.split("#", 1)[0].lower().endswith("/" + target_lower)
        }
        if len(file_keys) == 1:
            file_key = next(iter(file_keys))
            roots = [item for item in ids if item.startswith(file_key + "#")]
            if roots:
                return min(roots, key=lambda item: (item.count("#"), item)), []
        if len(file_keys) > 1:
            roots = [
                min(
                    (item for item in ids if item.startswith(file_key + "#")),
                    key=lambda item: (item.count("#"), item),
                )
                for file_key in sorted(file_keys)
            ]
            return None, roots
    candidates = [
        item
        for item in ids
        if item.lower().endswith("/" + target_lower) or item.lower().endswith("#" + target_lower)
    ]
    if not candidates and "#" in target:
        file_part, heading_part = target.split("#", 1)
        file_suffix = file_part.lower()
        heading_suffix = "#" + heading_part.lower()
        candidates = [
            item
            for item in ids
            if item.split("#", 1)[0].lower().endswith(file_suffix)
            and item.lower().endswith(heading_suffix)
        ]
    if len(candidates) == 1:
        return candidates[0], []
    return None, sorted(candidates)


def resolve_lattice_reference_edges(
    edges: Iterable[dict[str, Any]], nodes: Iterable[dict[str, Any]]
) -> None:
    """Resolve wiki-link edge targets against the complete extracted lattice.

    Per-file extraction cannot know another file's full heading ancestry. This
    post-pass upgrades shorthand such as ``operations#Deployment`` to the stable
    section id ``operations#Operations#Deployment`` once all nodes are present.
    Broken or ambiguous targets remain dangling and are pruned by the normal
    graph builder; ``check-knowledge`` reports the actionable diagnostic.
    """
    knowledge_ids = {
        str(node["knowledge_id"])
        for node in nodes
        if node.get("type") == "knowledge_section" and node.get("knowledge_id")
    }
    for edge in edges:
        if edge.get("relation") != "references" or not edge.get("knowledge_target"):
            continue
        resolved, ambiguous = _resolve_ref(str(edge["knowledge_target"]), knowledge_ids)
        if resolved is not None and not ambiguous:
            edge["target"] = _knowledge_node_id(resolved)
            edge["resolved_knowledge_target"] = resolved


def extract_lattice_code_ref_edges(
    paths: Iterable[Path], nodes: Iterable[dict[str, Any]]
) -> list[dict[str, Any]]:
    """Create ``knowledge_section --implemented_by--> source file`` edges."""
    knowledge_ids = {
        str(node["knowledge_id"])
        for node in nodes
        if node.get("type") == "knowledge_section" and node.get("knowledge_id")
    }
    if not knowledge_ids:
        return []
    edges: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for path, line_number, target in _iter_code_refs(paths):
        resolved, ambiguous = _resolve_ref(target, knowledge_ids)
        if resolved is None or ambiguous:
            continue
        key = (resolved, str(path))
        if key in seen:
            continue
        seen.add(key)
        edges.append(
            _edge(
                _knowledge_node_id(resolved),
                _make_id(str(path)),
                "implemented_by",
                str(path),
                line_number,
                knowledge_id=resolved,
            )
        )
    return edges


def _iter_code_refs(paths: Iterable[Path]) -> Iterable[tuple[Path, int, str]]:
    """Yield bounded ``@lat`` references from eligible source files."""
    for path in paths:
        if is_lattice_markdown_path(path) or path.suffix.lower() == ".md":
            continue
        try:
            if path.stat().st_size > _MAX_FILE_BYTES:
                continue
            lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError:
            continue
        for line_number, line in enumerate(lines, start=1):
            for match in _CODE_REF_RE.finditer(line):
                yield path, line_number, match.group(1).strip()


def _lattice_files(project_root: Path) -> list[Path]:
    lattice_dir = project_root / "lat.md"
    if not lattice_dir.is_dir():
        return []
    return sorted(path for path in lattice_dir.rglob("*.md") if path.is_file())


def project_source_paths(project_root: Path) -> list[Path]:
    """Return ignore-aware, in-root files eligible for ``@lat`` scanning."""
    from graphify.detect import ignored_predicate

    ignored = ignored_predicate(project_root)
    paths: list[Path] = []
    for path in project_root.rglob("*"):
        if not path.is_file() or is_lattice_markdown_path(path) or ignored(path):
            continue
        try:
            path.resolve().relative_to(project_root)
        except (OSError, RuntimeError, ValueError):
            continue
        paths.append(path)
    return paths


def _requires_code_mention(text: str) -> bool:
    frontmatter = re.match(r"^---\s*\n(.*?)\n---", text, flags=re.DOTALL)
    return bool(
        frontmatter and re.search(r"require-code-mention:\s*true", frontmatter.group(1), re.I)
    )


def validate_lattice(project_root: Path) -> dict[str, Any]:
    """Validate wiki references and required ``@lat`` implementation mentions."""
    project_root = project_root.resolve()
    files = _lattice_files(project_root)
    extracted = [extract_lattice_markdown(path) for path in files]
    nodes = [node for result in extracted for node in result.get("nodes", [])]
    knowledge_ids = {str(node["knowledge_id"]) for node in nodes if node.get("knowledge_id")}
    errors: list[dict[str, Any]] = []

    for result in extracted:
        for edge in result.get("edges", []):
            if edge.get("relation") == "documents":
                target = str(edge.get("source_target", ""))
                if edge.get("source_reference_error"):
                    errors.append(
                        {
                            "code": "unsafe-source-reference",
                            "file": edge["source_file"],
                            "line": int(str(edge["source_location"])[1:]),
                            "target": target,
                            "message": f"unsafe source reference [[{target}]]",
                        }
                    )
                    continue
                target_path = Path(str(edge.get("target_file") or ""))
                if not target_path.is_file():
                    errors.append(
                        {
                            "code": "broken-source-reference",
                            "file": edge["source_file"],
                            "line": int(str(edge["source_location"])[1:]),
                            "target": target,
                            "message": f"broken source reference [[{target}]]",
                        }
                    )
                continue
            if edge.get("relation") != "references":
                continue
            target = str(edge.get("knowledge_target", ""))
            resolved, ambiguous = _resolve_ref(target, knowledge_ids)
            if ambiguous:
                errors.append(
                    {
                        "code": "ambiguous-reference",
                        "file": edge["source_file"],
                        "line": int(str(edge["source_location"])[1:]),
                        "target": target,
                        "candidates": ambiguous,
                        "message": f"ambiguous knowledge reference [[{target}]]",
                    }
                )
            elif resolved is None:
                errors.append(
                    {
                        "code": "broken-reference",
                        "file": edge["source_file"],
                        "line": int(str(edge["source_location"])[1:]),
                        "target": target,
                        "message": f"broken knowledge reference [[{target}]]",
                    }
                )

    source_paths = project_source_paths(project_root)
    code_refs = list(_iter_code_refs(source_paths))
    implemented: set[str] = set()
    for source_path, line_number, target in code_refs:
        resolved, ambiguous = _resolve_ref(target, knowledge_ids)
        if ambiguous:
            errors.append(
                {
                    "code": "ambiguous-code-reference",
                    "file": str(source_path),
                    "line": line_number,
                    "target": target,
                    "candidates": ambiguous,
                    "message": f"ambiguous @lat reference [[{target}]]",
                }
            )
        elif resolved is None:
            errors.append(
                {
                    "code": "broken-code-reference",
                    "file": str(source_path),
                    "line": line_number,
                    "target": target,
                    "message": f"stale @lat reference [[{target}]]",
                }
            )
        else:
            implemented.add(resolved)
    for file_path in files:
        text = file_path.read_text(encoding="utf-8", errors="replace")
        if not _requires_code_mention(text):
            continue
        result = extract_lattice_markdown(file_path)
        parent_ids = {
            edge["source"] for edge in result.get("edges", []) if edge.get("relation") == "contains"
        }
        for node in result.get("nodes", []):
            if node["id"] in parent_ids:
                continue
            knowledge_id = str(node["knowledge_id"])
            if knowledge_id not in implemented:
                errors.append(
                    {
                        "code": "missing-code-mention",
                        "file": str(file_path),
                        "line": int(str(node["source_location"])[1:]),
                        "target": knowledge_id,
                        "message": f"knowledge section [[{knowledge_id}]] has no @lat code mention",
                    }
                )

    errors.sort(key=lambda item: (item["file"], item["line"], item["code"], item["target"]))
    return {
        "valid": not errors,
        "lattice_dir": str(project_root / "lat.md"),
        "files": len(files),
        "sections": len(knowledge_ids),
        "errors": errors,
    }
