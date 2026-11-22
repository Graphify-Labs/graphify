"""Render indexed direct callers with bounded, checkout-verified Python excerpts."""

from __future__ import annotations

import ast
import json
import re
import stat
import tokenize
from collections.abc import Iterable
from dataclasses import dataclass
from hashlib import md5
from io import BytesIO
from itertools import chain
from pathlib import Path, PureWindowsPath
from unicodedata import normalize

import networkx as nx

from graphify.build import _CONFIDENCE_RANK
from graphify.paths import _is_test_path
from graphify.security import _MAX_LABEL_LEN, redact_secrets, sanitize_label

_CALLER_QUESTION = re.compile(
    r"who calls (.+?)(?:,? and under what condition[s]?)?\??", re.IGNORECASE
)
_MAX_SOURCE_BYTES = 1024 * 1024
_MAX_MANIFEST_BYTES = 16 * _MAX_SOURCE_BYTES
_MAX_EXCERPT_LINES = 8


def caller_target(question: str) -> str | None:
    match = _CALLER_QUESTION.fullmatch(question.strip())
    if match is None:
        return None
    return match[1].strip().strip("`").strip() or None


def resolve_caller_target(graph: nx.Graph, label: str) -> tuple[str | None, str | None]:
    from graphify.serve import _find_node_tiers, _tier_refusal

    if label in graph:
        return label, None
    source_exact, exact, _, _ = _find_node_tiers(graph, label)
    matches = source_exact or exact
    if not matches:
        return None, None
    refusal = _tier_refusal(graph, label, matches, file_query=False)
    return (None, refusal) if refusal else (matches[0], None)


def _line_number(location: object) -> int:
    match = re.fullmatch(r"L([1-9][0-9]{0,8})(?:-L?[0-9]{1,9})?", str(location))
    return int(match[1]) if match else 0


@dataclass(frozen=True)
class _CallSite:
    caller: str
    confidence: str
    file: str
    line: int
    definition: int


def _direct_callers(graph: nx.Graph, target: str) -> list[_CallSite]:
    edges: Iterable[tuple[str, str, dict]] = graph.edges(target, data=True)
    if isinstance(graph, nx.DiGraph):
        # Legacy graphs can store a link in reversed endpoint order and carry
        # its direction in _src/_tgt. Check incidents on both sides.
        edges = chain(graph.in_edges(target, data=True), edges)
    sites = set()
    for u, v, data in edges:
        if data.get("relation") != "calls":
            continue
        caller, callee = data.get("_src", u), data.get("_tgt", v)
        if callee != target or (caller, callee) not in ((u, v), (v, u)):
            continue
        file = str(data.get("source_file") or "").replace("\\", "/")
        line = _line_number(data.get("source_location"))
        definition = _line_number(graph.nodes[caller].get("source_location"))
        if graph.nodes[caller].get("source_file") != file or definition > line:
            definition = 0
        confidence = str(data.get("confidence") or "")
        if confidence not in _CONFIDENCE_RANK:
            confidence = "UNKNOWN"
        sites.add(_CallSite(caller, confidence, file, line, definition))
    return sorted(sites, key=lambda site: (
        -_CONFIDENCE_RANK.get(site.confidence, 0), not (site.file and site.line),
        _is_test_path(site.file), site.file, site.line, -site.definition, site.caller,
    ))


def _read_regular_file(path: Path, limit: int) -> bytes:
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > limit:
        raise ValueError("expected a bounded regular file")
    with path.open("rb") as stream:
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError("file exceeded the read limit")
    return data


def _manifest(graph_path: Path) -> dict:
    try:
        data = json.loads(_read_regular_file(graph_path.with_name("manifest.json"), _MAX_MANIFEST_BYTES))
    except (OSError, ValueError, RecursionError):
        return {}
    return data if isinstance(data, dict) else {}


def _python_excerpts(
    root: Path, file: str, entry: object, callee: str,
) -> dict[int, tuple[int, list[str]]]:
    if not isinstance(entry, dict):
        return {}
    fingerprint = entry.get("ast_hash", entry.get("hash"))
    if not isinstance(fingerprint, str) or len(fingerprint) != 32:
        return {}
    rel = Path(file)
    if (rel.suffix.lower() != ".py" or PureWindowsPath(file).anchor
            or ".." in rel.parts or ".git" in (part.lower() for part in rel.parts)):
        return {}
    try:
        path = (root / rel).resolve(strict=True)
        if ".git" in (part.lower() for part in path.relative_to(root).parts):
            return {}
        data = _read_regular_file(path, _MAX_SOURCE_BYTES)
        if md5(data, usedforsecurity=False).hexdigest() != fingerprint:
            return {}
        encoding, _ = tokenize.detect_encoding(BytesIO(data).readline)
        source = data.decode(encoding).replace("\r\n", "\n").replace("\r", "\n")
        tree = ast.parse(source)
    except (OSError, RuntimeError, ValueError, SyntaxError, LookupError):
        return {}
    lines = source.split("\n")
    parents = {child: parent for parent in ast.walk(tree) for child in ast.iter_child_nodes(parent)}
    excerpts = {}
    for node in parents:
        if not isinstance(node, ast.Call):
            continue
        name = getattr(node.func, "id", None) or getattr(node.func, "attr", None)
        if name != callee or node.end_lineno is None:
            continue
        start, end = node.lineno, node.end_lineno
        parent = parents.get(node)
        while parent is not None and not isinstance(
            parent, (ast.If, ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef),
        ):
            parent = parents.get(parent)
        if isinstance(parent, ast.If) and end - parent.lineno < _MAX_EXCERPT_LINES:
            start = parent.lineno
        if end - start >= _MAX_EXCERPT_LINES:
            continue
        # An outer same-line call (such as recursive nesting) covers its inner call.
        previous = excerpts.get(node.lineno)
        if previous is None or len(previous[1]) < end - start + 1:
            excerpts[node.lineno] = start, lines[start - 1:end]
    return excerpts


def format_caller_evidence(
    graph: nx.Graph, target: str, root: Path, graph_path: Path, token_budget: int,
) -> str:
    from graphify.hooks import _git_root
    from graphify.llm import _neutralise_injection_sentinels

    label = str(graph.nodes[target].get("label") or target)
    heading = f"Direct callers of {sanitize_label(label)}"
    callers = _direct_callers(graph, target)
    # Match the query command's existing character-based token estimate.
    limit = token_budget * 3 - 1  # print() adds one newline
    if not callers:
        return (heading + "\nNo direct callers found in the index.")[:limit]
    heading = heading[:limit]
    remaining = limit - len(heading)
    ranked_rows = []
    seen = set()
    for site in callers:
        key = (site.caller, site.file, site.line) if site.file and site.line else (site.caller,)
        if key in seen:
            continue
        seen.add(key)
        caller = sanitize_label(str(graph.nodes[site.caller].get("label") or site.caller))
        location = (
            f"{sanitize_label(site.file)}:{site.line}" if site.file and site.line else "no indexed call location"
        )
        ranked_rows.append((site, f"\n{caller} [{sanitize_label(site.confidence)}] at {location}"))

    cwd = Path.cwd()
    scope = _git_root(cwd) or cwd.resolve()
    can_excerpt = graph_path.name == "graph.json" and root.is_relative_to(scope)
    manifest = None
    # Graphify uses decorated labels such as 'Class.method()' for callables.
    callee = label.removesuffix("()").rsplit(".", 1)[-1]
    source_cache: dict[str, dict[int, tuple[int, list[str]]]] = {}

    def render_excerpt(site: _CallSite) -> str | None:
        nonlocal manifest
        if not (can_excerpt and site.confidence == "EXTRACTED"
                and site.file.lower().endswith(".py") and site.line):
            return None
        if manifest is None:
            manifest = _manifest(graph_path)
        if site.file not in source_cache:
            source_cache[site.file] = _python_excerpts(
                root, site.file, manifest.get(normalize("NFC", site.file)), callee,
            )
        excerpt = source_cache[site.file].get(site.line)
        if not excerpt:
            return ""
        start, lines = excerpt
        block = "\n  Source excerpt (untrusted code):"
        for line_no, line in enumerate(lines, start):
            text = _neutralise_injection_sentinels(redact_secrets(line)).expandtabs(4)
            clean = sanitize_label(text)
            suffix = "…" if len(clean) == _MAX_LABEL_LEN < len(text) else ""
            block += f"\n  {line_no} | {clean}{suffix}"
        return block

    notice = ""
    reserved_site = None
    reserved_block = ""
    if sum(len(row) for _, row in ranked_rows) > remaining:
        # Keep enough room for the highest-ranked citation that fits.
        first_width = next((len(row) for _, row in ranked_rows if len(row) <= remaining), 0)
        notice_room = remaining - first_width
        notices = ("\nAdditional callers omitted by the output budget.", "\nMore callers omitted.", "\n…")
        notice = next((message for message in notices if len(message) <= notice_room), "")
        remaining -= len(notice)
        if can_excerpt and remaining >= 300:
            # Reserve the exact size of a verified excerpt from the leading
            # callers. Leave the entire budget to citations if none fits.
            excerpt_budget = remaining // 3
            citation_cost = 0
            for site, row in ranked_rows:
                if len(row) > remaining:
                    continue
                citation_cost += len(row)
                if citation_cost > remaining - excerpt_budget:
                    break
                block = render_excerpt(site)
                if block and len(block) <= excerpt_budget:
                    reserved_site, reserved_block = site, block
                    remaining -= len(block)
                    break
    rows = []
    for site, row in ranked_rows:
        if len(row) > remaining:
            continue
        rows.append((site, row))
        remaining -= len(row)

    output = [heading]
    for site, row in rows:
        output.append(row)
        if site == reserved_site:
            output.append(reserved_block)
            continue
        block = render_excerpt(site) if remaining > 20 else None
        if block is None:
            continue
        if not block or len(block) > remaining:
            block = "\n  Excerpt unavailable. Check the source directly."
        if len(block) <= remaining:
            output.append(block)
            remaining -= len(block)
    return "".join(output) + notice
