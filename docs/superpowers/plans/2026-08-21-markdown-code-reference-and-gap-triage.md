# Markdown-to-Code References and Gap Triage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make Graphify connect Markdown documentation to exact code symbols, canonicalize imported Python type aliases, and report only actionable local graph gaps, then use the enhanced extractor to refresh and verify DebtGPS.

**Architecture:** Markdown extraction records a normalized target path and optional line anchor; a whole-corpus resolver maps that evidence to canonical code nodes after ID normalization. A separate deterministic Python pass materializes module-level type aliases and rewires uniquely import-supported references. A shared gap-classification module powers both analysis questions and report breakdowns without removing benign nodes from the graph.

**Tech Stack:** Python 3.10+, tree-sitter-backed Graphify AST extraction, `ast`, NetworkX, pytest, uv tool environments, Markdown semantic extraction cache, DebtGPS Flask/pytest suite.

---

## File Structure

### Graphify checkout

- Modify `graphify/extractors/markdown.py` — parse local document/code links into structured targets and retain line evidence on reference edges.
- Modify `graphify/symbol_resolution.py` — resolve line-targeted Markdown edges and canonicalize Python module-level type aliases.
- Modify `graphify/extract.py` — call the two deterministic corpus-level resolvers at the correct normalization points.
- Create `graphify/gaps.py` — single classification vocabulary and gap/community breakdown helpers.
- Modify `graphify/analyze.py` — use actionable-local filtering for isolated-node and low-cohesion questions.
- Modify `graphify/report.py` — render actionable counts plus auditable benign-category counts.
- Modify `tests/test_languages.py` — unit coverage for structured Markdown target parsing/extraction.
- Modify `tests/test_incremental.py` — full/incremental parity for line-targeted Markdown edges.
- Modify `tests/test_symbol_resolution.py` — code-line and Python type-alias resolution coverage.
- Modify `tests/test_analyze.py` — classification and suggested-question coverage.
- Create `tests/test_gap_reporting.py` — focused report breakdown tests.

### DebtGPS consumer

- Modify `server/routes_planning.py` — add the refinance route rationale docstring without changing runtime behavior.
- Modify `tests/test_coverage_gaps.py` — enforce that the route documents validation/delegation authority.
- Refresh `graphify-out/` — merge cached and newly extracted semantics with the patched AST graph.

---

### Task 1: Parse and Extract Markdown Code Targets

**Files:**
- Modify: `graphify/extractors/markdown.py:16-230`
- Modify: `graphify/extractors/markdown.py:295-350`
- Test: `tests/test_languages.py`

- [ ] **Step 1: Write failing parser tests**

Add imports for `ResolvedMarkdownTarget` and `_resolve_markdown_target`, then add:

```python
def test_markdown_target_keeps_code_line_anchor(tmp_path):
    source_dir = tmp_path / "docs"
    source_dir.mkdir()

    target = _resolve_markdown_target(
        "../src/service.py#L17", source_dir, wikilink=False
    )

    assert target == ResolvedMarkdownTarget(
        path=tmp_path / "src" / "service.py",
        line=17,
    )


@pytest.mark.parametrize("fragment", ["#L0", "#L-2", "#Labc", "#section"])
def test_markdown_target_invalid_code_line_falls_back_to_file(tmp_path, fragment):
    target = _resolve_markdown_target(
        f"../src/service.py{fragment}", tmp_path / "docs", wikilink=False
    )

    assert target == ResolvedMarkdownTarget(
        path=tmp_path / "src" / "service.py",
        line=None,
    )


def test_markdown_target_keeps_document_fragment_behavior(tmp_path):
    target = _resolve_markdown_target(
        "./architecture.md#decisions", tmp_path, wikilink=False
    )

    assert target == ResolvedMarkdownTarget(
        path=tmp_path / "architecture.md",
        line=None,
    )
```

- [ ] **Step 2: Run parser tests and verify RED**

Run:

```powershell
uv run pytest tests/test_languages.py -k "markdown_target" -v
```

Expected: collection/import failure because `ResolvedMarkdownTarget` and `_resolve_markdown_target` do not exist.

- [ ] **Step 3: Implement the structured target parser**

In `graphify/extractors/markdown.py`, add:

```python
from dataclasses import dataclass
from graphify.detect import CODE_EXTENSIONS

_MD_LINE_FRAGMENT_RE = re.compile(r"^L([1-9][0-9]*)$", re.IGNORECASE)


@dataclass(frozen=True)
class ResolvedMarkdownTarget:
    path: Path
    line: int | None = None


def _resolve_markdown_target(
    raw: str,
    source_dir: Path,
    wikilink: bool = False,
) -> ResolvedMarkdownTarget | None:
    target = raw.strip()
    if not target:
        return None
    path_and_query, separator, fragment = target.partition("#")
    path_text = path_and_query.split("?", 1)[0].strip()
    if not path_text:
        return None
    low = path_text.lower()
    if "://" in path_text or low.startswith(("mailto:", "tel:", "//", "data:")):
        return None
    suffix = Path(path_text).suffix.lower()
    if not suffix:
        path_text += ".md"
        suffix = ".md"
    if suffix not in _MD_LINKABLE_EXTS and suffix not in CODE_EXTENSIONS:
        return None
    candidate = Path(path_text)
    if not candidate.is_absolute():
        candidate = source_dir / candidate
    resolved = Path(os.path.normpath(str(candidate)))
    if wikilink and suffix in _MD_LINKABLE_EXTS and not Path(path_text).is_absolute():
        try:
            missing = not resolved.is_file()
        except OSError:
            missing = False
        if missing:
            root = _active_scan_root()
            hit = _vault_lookup(path_text, root) if root is not None else None
            if hit is not None:
                resolved = Path(os.path.normpath(str(hit)))
    match = _MD_LINE_FRAGMENT_RE.fullmatch(fragment.strip()) if separator else None
    line = int(match.group(1)) if match and suffix in CODE_EXTENSIONS else None
    return ResolvedMarkdownTarget(path=resolved, line=line)


def _resolve_markdown_link(
    raw: str,
    source_dir: Path,
    wikilink: bool = False,
) -> Path | None:
    target = _resolve_markdown_target(raw, source_dir, wikilink=wikilink)
    return target.path if target is not None else None
```

Retain the existing vault helper and remove only the superseded body of `_resolve_markdown_link`.

- [ ] **Step 4: Run parser tests and existing Markdown tests**

Run:

```powershell
uv run pytest tests/test_languages.py -k "markdown" -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Write a failing extraction-edge test**

Add:

```python
def test_markdown_code_link_emits_target_file_and_line(tmp_path):
    docs = tmp_path / "docs"
    src = tmp_path / "src"
    docs.mkdir()
    src.mkdir()
    target = src / "service.py"
    target.write_text("def run():\n    return 1\n", encoding="utf-8")
    page = docs / "architecture.md"
    page.write_text("[implementation](../src/service.py#L2)\n", encoding="utf-8")

    result = extract_markdown(page)
    edge = next(edge for edge in result["edges"] if edge["relation"] == "references")

    assert edge["target_file"] == str(target)
    assert edge["target_line"] == 2
```

- [ ] **Step 6: Run extraction test and verify RED**

Run:

```powershell
uv run pytest tests/test_languages.py::test_markdown_code_link_emits_target_file_and_line -v
```

Expected: FAIL because the extracted edge has no `target_line`.

- [ ] **Step 7: Retain target-line evidence on extracted edges**

Change `add_edge` and `add_link` to:

```python
def add_edge(
    src: str,
    tgt: str,
    relation: str,
    line: int,
    confidence: str = "EXTRACTED",
    weight: float = 1.0,
    target_file: str | None = None,
    target_line: int | None = None,
) -> None:
    edge = {
        "source": src,
        "target": tgt,
        "relation": relation,
        "confidence": confidence,
        "source_file": str_path,
        "source_location": f"L{line}",
        "weight": weight,
    }
    if target_file is not None:
        edge["target_file"] = target_file
    if target_line is not None:
        edge["target_line"] = target_line
    edges.append(edge)


def add_link(raw: str, line: int, wikilink: bool = False) -> None:
    target = _resolve_markdown_target(raw, source_dir, wikilink=wikilink)
    if target is None:
        return
    tgt_nid = _make_id(str(target.path))
    dedupe_key = f"{tgt_nid}:L{target.line or 0}"
    if tgt_nid == file_nid or dedupe_key in linked_targets:
        return
    linked_targets.add(dedupe_key)
    target_file = None
    try:
        if target.path.is_file():
            target_file = str(target.path)
    except OSError:
        pass
    add_edge(
        file_nid,
        tgt_nid,
        "references",
        line,
        target_file=target_file,
        target_line=target.line,
    )
```

- [ ] **Step 8: Run Markdown regression tests**

Run:

```powershell
uv run pytest tests/test_languages.py -k "markdown" -v
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 1**

```powershell
git add graphify/extractors/markdown.py tests/test_languages.py
git commit -m "feat: retain markdown code link targets"
```

---

### Task 2: Resolve Markdown Line Anchors to Canonical Code Symbols

**Files:**
- Modify: `graphify/symbol_resolution.py`
- Modify: `graphify/extract.py:6760-6850`
- Modify: `tests/test_symbol_resolution.py`
- Modify: `tests/test_incremental.py`

- [ ] **Step 1: Write failing resolver tests**

Add:

```python
from graphify.symbol_resolution import resolve_markdown_code_references


def test_markdown_code_reference_prefers_exact_symbol(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def run():\n    return 1\n", encoding="utf-8")
    nodes = [
        {"id": "service", "label": "service.py", "file_type": "code", "source_file": str(source), "source_location": "L1"},
        {"id": "service_run", "label": "run", "file_type": "code", "node_kind": "function", "source_file": str(source), "source_location": "L1"},
    ]
    edges = [{"source": "architecture", "target": "service", "relation": "references", "target_file": str(source), "target_line": 1}]

    resolve_markdown_code_references(nodes, edges)

    assert edges[0]["target"] == "service_run"
    assert "target_line" not in edges[0]


def test_markdown_code_reference_uses_nearest_preceding_symbol(tmp_path):
    source = tmp_path / "service.py"
    source.write_text("def first():\n    pass\n\ndef second():\n    pass\n", encoding="utf-8")
    nodes = [
        {"id": "service", "label": "service.py", "file_type": "code", "source_file": str(source), "source_location": "L1"},
        {"id": "first", "label": "first", "file_type": "code", "node_kind": "function", "source_file": str(source), "source_location": "L1"},
        {"id": "second", "label": "second", "file_type": "code", "node_kind": "function", "source_file": str(source), "source_location": "L4"},
    ]
    edges = [{"source": "architecture", "target": "service", "relation": "references", "target_file": str(source), "target_line": 5}]

    resolve_markdown_code_references(nodes, edges)

    assert edges[0]["target"] == "second"
```

- [ ] **Step 2: Run resolver tests and verify RED**

Run:

```powershell
uv run pytest tests/test_symbol_resolution.py -k "markdown_code_reference" -v
```

Expected: import/collection failure because `resolve_markdown_code_references` does not exist.

- [ ] **Step 3: Implement deterministic line resolution**

Add to `graphify/symbol_resolution.py`:

```python
_SOURCE_LINE_RE = re.compile(r"^L([1-9][0-9]*)")
_SYMBOL_KIND_PRIORITY = {
    "method": 0,
    "function": 1,
    "class": 2,
    "type_alias": 3,
}


def _source_line(node: dict[str, Any]) -> int | None:
    match = _SOURCE_LINE_RE.match(str(node.get("source_location", "")))
    return int(match.group(1)) if match else None


def resolve_markdown_code_references(
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    by_path: dict[Path, list[tuple[int, int, str]]] = {}
    file_ids: dict[Path, str] = {}
    for node in nodes:
        source_file = node.get("source_file")
        if not source_file or node.get("file_type") != "code" or not node.get("id"):
            continue
        try:
            path = Path(str(source_file)).resolve()
        except (OSError, RuntimeError):
            continue
        label = str(node.get("label", ""))
        if label == Path(str(source_file)).name:
            file_ids[path] = str(node["id"])
            continue
        line = _source_line(node)
        if line is None:
            continue
        priority = _SYMBOL_KIND_PRIORITY.get(str(node.get("node_kind", "")), 10)
        by_path.setdefault(path, []).append((line, priority, str(node["id"])))
    for candidates in by_path.values():
        candidates.sort(key=lambda item: (item[0], item[1], item[2]))

    for edge in edges:
        if edge.get("relation") != "references" or not edge.get("target_file"):
            continue
        raw_line = edge.pop("target_line", None)
        try:
            path = Path(str(edge["target_file"])).resolve()
        except (OSError, RuntimeError):
            continue
        fallback = file_ids.get(path)
        if fallback is not None:
            edge["target"] = fallback
        if not isinstance(raw_line, int) or raw_line < 1:
            continue
        preceding = [item for item in by_path.get(path, []) if item[0] <= raw_line]
        if not preceding:
            continue
        best_line = preceding[-1][0]
        same_line = [item for item in preceding if item[0] == best_line]
        edge["target"] = min(same_line, key=lambda item: (item[1], item[2]))[2]
```

- [ ] **Step 4: Run resolver tests and verify GREEN**

Run:

```powershell
uv run pytest tests/test_symbol_resolution.py -k "markdown_code_reference" -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Write failing full/incremental parity test**

Add a test to `tests/test_incremental.py` that creates `docs/map.md` linking to `src/service.py#L2`, performs a full extraction, changes only the Markdown document, performs an incremental extraction, and asserts both results target the same `service_run` node and ship neither `target_file` nor `target_line`.

Use this complete assertion helper:

```python
def _reference_target(result):
    edge = next(
        edge for edge in result["edges"]
        if edge.get("relation") == "references"
        and edge.get("source_file", "").endswith("map.md")
    )
    assert "target_file" not in edge
    assert "target_line" not in edge
    return edge["target"]


assert _reference_target(full) == "src_service_run"
assert _reference_target(incremental) == _reference_target(full)
```

- [ ] **Step 6: Run parity test and verify RED**

Run the exact new node ID reported by pytest:

```powershell
uv run pytest tests/test_incremental.py -k "markdown_code_line" -v
```

Expected: FAIL because extraction still targets the file node.

- [ ] **Step 7: Integrate the resolver after final ID/path normalization**

Import the resolver in `graphify/extract.py` and call it immediately before transient edge metadata is removed and before the AST provenance loop:

```python
from graphify.symbol_resolution import resolve_markdown_code_references

# All node IDs and source paths are canonical at this point. Refine Markdown
# code references before transient target evidence is removed.
resolve_markdown_code_references(all_nodes, all_edges)
for edge in all_edges:
    edge.pop("target_file", None)
    edge.pop("target_line", None)
```

If an earlier pass already removes `target_file`, move that removal to this single cleanup point without changing other resolver ordering.

- [ ] **Step 8: Run parity and canonical-ID regressions**

Run:

```powershell
uv run pytest tests/test_incremental.py -k "markdown or target_file" -v
uv run pytest tests/test_node_id_canonical.py -v
```

Expected: all selected tests pass.

- [ ] **Step 9: Commit Task 2**

```powershell
git add graphify/extract.py graphify/symbol_resolution.py tests/test_symbol_resolution.py tests/test_incremental.py
git commit -m "feat: resolve markdown links to code symbols"
```

---

### Task 3: Materialize and Canonicalize Python Type Aliases

**Files:**
- Modify: `graphify/symbol_resolution.py`
- Modify: `graphify/extract.py`
- Modify: `tests/test_symbol_resolution.py`

- [ ] **Step 1: Write failing alias-discovery tests**

Add:

```python
from graphify.symbol_resolution import parse_python_type_aliases


def test_parse_python_type_aliases_supports_assignment_and_typealias(tmp_path):
    module = tmp_path / "ordering.py"
    module.write_text(
        "from typing import Callable, TypeAlias\n"
        "OrderFn = Callable[[int], str]\n"
        "ExplicitOrderFn: TypeAlias = Callable[[int], str]\n",
        encoding="utf-8",
    )

    aliases = parse_python_type_aliases(module)

    assert [(alias.name, alias.source_location) for alias in aliases] == [
        ("OrderFn", "L2"),
        ("ExplicitOrderFn", "L3"),
    ]


def test_parse_python_type_aliases_ignores_function_local_assignments(tmp_path):
    module = tmp_path / "ordering.py"
    module.write_text(
        "from typing import Callable\n"
        "def build():\n"
        "    LocalOrderFn = Callable[[int], str]\n",
        encoding="utf-8",
    )

    assert parse_python_type_aliases(module) == []
```

- [ ] **Step 2: Run discovery tests and verify RED**

Run:

```powershell
uv run pytest tests/test_symbol_resolution.py -k "parse_python_type_aliases" -v
```

Expected: import/collection failure because the parser does not exist.

- [ ] **Step 3: Implement conservative alias discovery**

Add:

```python
@dataclass(frozen=True)
class PythonTypeAlias:
    name: str
    module_stem: str
    source_file: str
    source_location: str


def _annotation_names(node: ast.AST | None) -> set[str]:
    return {
        child.id
        for child in ast.walk(node)
        if isinstance(child, ast.Name)
    } if node is not None else set()


def parse_python_type_aliases(path: Path) -> list[PythonTypeAlias]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, SyntaxError):
        return []
    result: list[PythonTypeAlias] = []
    for node in tree.body:
        name: str | None = None
        value: ast.AST | None = None
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if "TypeAlias" in _annotation_names(node.annotation):
                name = node.target.id
                value = node.value
        elif hasattr(ast, "TypeAlias") and isinstance(node, ast.TypeAlias):
            name_node = getattr(node, "name", None)
            name = getattr(name_node, "id", None)
            value = getattr(node, "value", None)
        if not name or value is None:
            continue
        value_names = _annotation_names(value)
        if not value_names.intersection({"Callable", "Union", "Literal", "Protocol", "Type", "Annotated"}):
            continue
        result.append(PythonTypeAlias(
            name=name,
            module_stem=path.stem,
            source_file=str(path),
            source_location=f"L{getattr(node, 'lineno', 1)}",
        ))
    return result
```

- [ ] **Step 4: Run discovery tests and verify GREEN**

Run:

```powershell
uv run pytest tests/test_symbol_resolution.py -k "parse_python_type_aliases" -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Write a failing import-canonicalization test**

Add:

```python
from graphify.symbol_resolution import canonicalize_python_type_aliases


def test_canonicalize_python_type_aliases_rewires_imported_stub(tmp_path):
    definitions = tmp_path / "ordering.py"
    consumer = tmp_path / "planner.py"
    definitions.write_text(
        "from typing import Callable\nOrderFn = Callable[[int], str]\n",
        encoding="utf-8",
    )
    consumer.write_text(
        "from ordering import OrderFn\ndef plan(order: OrderFn):\n    return order(1)\n",
        encoding="utf-8",
    )
    nodes = [
        {"id": "ordering", "label": "ordering.py", "file_type": "code", "source_file": str(definitions), "source_location": "L1"},
        {"id": "planner", "label": "planner.py", "file_type": "code", "source_file": str(consumer), "source_location": "L1"},
        {"id": "planner_plan", "label": "plan", "file_type": "code", "node_kind": "function", "source_file": str(consumer), "source_location": "L2"},
        {"id": "stub_orderfn", "label": "OrderFn", "file_type": "code"},
    ]
    edges = [{"source": "planner_plan", "target": "stub_orderfn", "relation": "references", "source_file": str(consumer)}]

    canonicalize_python_type_aliases([definitions, consumer], nodes, edges)

    aliases = [node for node in nodes if node.get("node_kind") == "type_alias"]
    assert len(aliases) == 1
    assert aliases[0]["label"] == "OrderFn"
    assert aliases[0]["source_file"] == str(definitions)
    assert edges[0]["target"] == aliases[0]["id"]
    assert all(node["id"] != "stub_orderfn" for node in nodes)
```

- [ ] **Step 6: Run canonicalization test and verify RED**

Run:

```powershell
uv run pytest tests/test_symbol_resolution.py -k "canonicalize_python_type_aliases" -v
```

Expected: import/collection failure because `canonicalize_python_type_aliases` does not exist.

- [ ] **Step 7: Implement source-backed alias nodes and safe rewiring**

Add a helper that derives the containing file node by resolved `source_file`, creates stable alias IDs with `_shared_make_id(file_node_id, alias.name)`, appends a `contains` edge, indexes aliases by `(module_stem, lower_name)`, and rewires only edges whose `source_file` has matching top-level import evidence.

Use this public shape:

```python
def canonicalize_python_type_aliases(
    paths: Sequence[Path],
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> None:
    file_ids = _file_node_ids_by_resolved_path(nodes)
    alias_index = _materialize_python_type_alias_nodes(paths, nodes, edges, file_ids)
    node_by_id = {str(node.get("id")): node for node in nodes if node.get("id")}
    rewired_stub_ids: set[str] = set()
    for path in paths:
        if path.suffix.lower() not in {".py", ".pyw"}:
            continue
        imports = parse_python_import_aliases(path)
        for edge in edges:
            if _resolved_source(edge.get("source_file")) != _resolved_source(str(path)):
                continue
            stub = node_by_id.get(str(edge.get("target")))
            if not stub or stub.get("source_file"):
                continue
            imported = imports.get(str(stub.get("label", "")))
            if imported is None:
                continue
            candidates = alias_index.get((imported.module_stem, imported.imported_name.lower()), [])
            if len(candidates) != 1:
                continue
            edge["target"] = candidates[0]
            rewired_stub_ids.add(str(stub["id"]))
    referenced = {str(edge.get(key)) for edge in edges for key in ("source", "target")}
    nodes[:] = [
        node for node in nodes
        if str(node.get("id")) not in rewired_stub_ids
        or str(node.get("id")) in referenced
    ]
```

Implement `_file_node_ids_by_resolved_path`, `_materialize_python_type_alias_nodes`, and `_resolved_source` as private helpers in the same module. `_materialize_python_type_alias_nodes` must deduplicate existing source-backed alias nodes before appending and sanitize metadata consistently with the other resolvers.

- [ ] **Step 8: Integrate alias canonicalization before final Markdown refinement**

In `graphify/extract.py`, after all node IDs and source paths are canonical but before `resolve_markdown_code_references`, call:

```python
canonicalize_python_type_aliases(paths, all_nodes, all_edges)
resolve_markdown_code_references(all_nodes, all_edges)
```

- [ ] **Step 9: Add and run ambiguity regressions**

Add tests proving star imports, function-local imports, external modules, and two same-module candidates leave the stub unresolved. Run:

```powershell
uv run pytest tests/test_symbol_resolution.py -k "type_alias or import_guided" -v
```

Expected: all selected tests pass.

- [ ] **Step 10: Commit Task 3**

```powershell
git add graphify/symbol_resolution.py graphify/extract.py tests/test_symbol_resolution.py
git commit -m "feat: canonicalize imported python type aliases"
```

---

### Task 4: Classify External and Benign Gap Nodes

**Files:**
- Create: `graphify/gaps.py`
- Modify: `graphify/analyze.py:428-540`
- Modify: `tests/test_analyze.py`

- [ ] **Step 1: Write failing classifier tests**

Add:

```python
from graphify.gaps import GapCategory, classify_gap_node, gap_breakdown


@pytest.mark.parametrize("attrs", [
    {"external": True, "file_type": "code"},
    {"node_kind": "external_symbol", "file_type": "code"},
    {"metadata": {"scip_kind": "external"}, "file_type": "code"},
])
def test_external_evidence_is_benign(attrs):
    graph = nx.Graph()
    graph.add_node("external", label="Flask", **attrs)

    assert classify_gap_node(graph, "external") is GapCategory.EXTERNAL


def test_sourceless_semantic_concept_is_not_external():
    graph = nx.Graph()
    graph.add_node("concept", label="Debt Strategy", file_type="concept")

    assert classify_gap_node(graph, "concept") is GapCategory.STRUCTURAL


def test_source_backed_leaf_is_actionable():
    graph = nx.Graph()
    graph.add_node("service", label="Service", file_type="code", source_file="src/service.py")

    assert classify_gap_node(graph, "service") is GapCategory.ACTIONABLE_LOCAL
```

- [ ] **Step 2: Run classifier tests and verify RED**

Run:

```powershell
uv run pytest tests/test_analyze.py -k "external_evidence or sourceless_semantic or source_backed_leaf" -v
```

Expected: import/collection failure because `graphify.gaps` does not exist.

- [ ] **Step 3: Implement the shared classifier**

Create `graphify/gaps.py`:

```python
from __future__ import annotations

from collections import Counter
from enum import StrEnum
from typing import Iterable

import networkx as nx


class GapCategory(StrEnum):
    ACTIONABLE_LOCAL = "actionable_local"
    EXTERNAL = "external"
    RATIONALE = "rationale"
    METADATA = "metadata"
    STRUCTURAL = "structural"


def _is_external(attrs: dict) -> bool:
    metadata = attrs.get("metadata") if isinstance(attrs.get("metadata"), dict) else {}
    return bool(
        attrs.get("external") is True
        or attrs.get("node_kind") == "external_symbol"
        or metadata.get("scip_kind") == "external"
        or str(attrs.get("id", "")).startswith("ref_")
    )


def classify_gap_node(graph: nx.Graph, node_id: str) -> GapCategory:
    from graphify.analyze import _is_concept_node, _is_file_node, _is_json_key_node

    attrs = dict(graph.nodes[node_id])
    attrs.setdefault("id", node_id)
    if _is_external(attrs):
        return GapCategory.EXTERNAL
    if attrs.get("file_type") == "rationale":
        return GapCategory.RATIONALE
    if _is_json_key_node(graph, node_id):
        return GapCategory.METADATA
    if _is_file_node(graph, node_id) or _is_concept_node(graph, node_id):
        return GapCategory.STRUCTURAL
    if attrs.get("node_kind") in {"page", "heading"}:
        return GapCategory.STRUCTURAL
    if attrs.get("source_file"):
        return GapCategory.ACTIONABLE_LOCAL
    return GapCategory.STRUCTURAL


def gap_breakdown(graph: nx.Graph, node_ids: Iterable[str]) -> dict[str, int]:
    counts = Counter(classify_gap_node(graph, node_id).value for node_id in node_ids)
    return {category.value: counts.get(category.value, 0) for category in GapCategory}
```

If the supported Python floor does not provide `StrEnum`, use `class GapCategory(str, Enum)` with the same values.

- [ ] **Step 4: Run classifier tests and verify GREEN**

Run:

```powershell
uv run pytest tests/test_analyze.py -k "external_evidence or sourceless_semantic or source_backed_leaf" -v
```

Expected: all selected tests pass.

- [ ] **Step 5: Write failing suggested-question tests**

Add a graph with one local code leaf, one explicit external leaf, one rationale leaf, and one JSON noise leaf. Assert the generated `isolated_nodes` question reports exactly one weakly connected node and names only the local code node.

```python
def test_suggest_questions_counts_only_actionable_local_leaves():
    graph = nx.Graph()
    graph.add_node("local", label="LocalService", file_type="code", source_file="src/local.py")
    graph.add_node("external", label="Flask", file_type="code", external=True)
    graph.add_node("reason", label="Why", file_type="rationale", source_file="src/local.py")
    graph.add_node("json", label="name", file_type="code", source_file="fixtures/data.json")

    questions = suggest_questions(graph, {}, {}, top_n=10)
    isolated = next(item for item in questions if item["type"] == "isolated_nodes")

    assert isolated["why"].startswith("1 weakly-connected node")
    assert "LocalService" in isolated["question"]
    assert "Flask" not in isolated["question"]
```

- [ ] **Step 6: Run question test and verify RED**

Run:

```powershell
uv run pytest tests/test_analyze.py::test_suggest_questions_counts_only_actionable_local_leaves -v
```

Expected: FAIL because current analysis counts the external leaf.

- [ ] **Step 7: Filter analysis through the shared category**

Replace the isolated-node filter in `suggest_questions` with:

```python
from graphify.gaps import GapCategory, classify_gap_node

isolated = [
    node_id
    for node_id in G.nodes()
    if G.degree(node_id) <= 1
    and classify_gap_node(G, node_id) is GapCategory.ACTIONABLE_LOCAL
]
```

For low-cohesion community questions, compute a breakdown and skip the question when `actionable_local == 0`; retain the community itself in clustering output.

- [ ] **Step 8: Run analysis regressions**

Run:

```powershell
uv run pytest tests/test_analyze.py -v
```

Expected: all tests pass.

- [ ] **Step 9: Commit Task 4**

```powershell
git add graphify/gaps.py graphify/analyze.py tests/test_analyze.py
git commit -m "feat: classify actionable graph gaps"
```

---

### Task 5: Render Auditable Gap and Thin-Community Breakdowns

**Files:**
- Modify: `graphify/report.py:270-315`
- Create: `tests/test_gap_reporting.py`

- [ ] **Step 1: Write failing report tests**

Create `tests/test_gap_reporting.py` with a small helper that calls `report.generate` using empty scores/surprises/detection/token inputs, then add:

```python
def test_report_separates_actionable_and_benign_isolated_nodes():
    graph = nx.Graph()
    graph.add_node("local", label="LocalService", file_type="code", source_file="src/local.py")
    graph.add_node("external", label="Flask", file_type="code", external=True)
    graph.add_node("reason", label="Decision", file_type="rationale", source_file="src/local.py")

    report = _generate(graph, communities={0: ["local"], 1: ["external"], 2: ["reason"]})

    assert "1 actionable isolated node(s)" in report
    assert "external: 1" in report
    assert "rationale: 1" in report
    assert "`LocalService`" in report


def test_report_marks_all_benign_thin_community_non_actionable():
    graph = nx.Graph()
    graph.add_node("external", label="parametrize", file_type="code", external=True)

    report = _generate(graph, communities={0: ["external"]})

    assert "benign thin communities: 1" in report
    assert "actionable thin communities: 0" in report
```

- [ ] **Step 2: Run report tests and verify RED**

Run:

```powershell
uv run pytest tests/test_gap_reporting.py -v
```

Expected: FAIL because the report has no categorized breakdown.

- [ ] **Step 3: Replace the undifferentiated gaps section**

Use `classify_gap_node` and `gap_breakdown` in `graphify/report.py`:

```python
from .gaps import GapCategory, classify_gap_node, gap_breakdown

weak_nodes = [node_id for node_id in G.nodes() if G.degree(node_id) <= 1]
weak_breakdown = gap_breakdown(G, weak_nodes)
actionable_isolated = [
    node_id for node_id in weak_nodes
    if classify_gap_node(G, node_id) is GapCategory.ACTIONABLE_LOCAL
]
thin_communities = {
    cid: nodes for cid, nodes in communities.items()
    if 0 < sum(1 for node_id in nodes if not _is_file_node(G, node_id)) < min_community_size
}
thin_breakdowns = {
    cid: gap_breakdown(G, nodes) for cid, nodes in thin_communities.items()
}
actionable_thin = {
    cid: counts for cid, counts in thin_breakdowns.items()
    if counts[GapCategory.ACTIONABLE_LOCAL.value] > 0
}
benign_thin_count = len(thin_breakdowns) - len(actionable_thin)
```

Render the section with these exact labels:

```python
lines.append(f"- **{len(actionable_isolated)} actionable isolated node(s):** {labels}{suffix}")
lines.append(
    "- **Benign weak-node breakdown:** "
    f"external: {weak_breakdown['external']}, "
    f"rationale: {weak_breakdown['rationale']}, "
    f"metadata: {weak_breakdown['metadata']}, "
    f"structural: {weak_breakdown['structural']}"
)
lines.append(f"- **actionable thin communities: {len(actionable_thin)}**")
lines.append(f"- **benign thin communities: {benign_thin_count}**")
```

Keep the ambiguity warning unchanged.

- [ ] **Step 4: Run report and analysis tests**

Run:

```powershell
uv run pytest tests/test_gap_reporting.py tests/test_analyze.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit Task 5**

```powershell
git add graphify/report.py tests/test_gap_reporting.py
git commit -m "feat: report actionable and benign graph gaps"
```

---

### Task 6: Document the DebtGPS Refinance Route Rationale

**Files:**
- Modify: `../../server/routes_planning.py:384-406`
- Modify: `../../tests/test_coverage_gaps.py`

- [ ] **Step 1: Write a failing route-contract test**

Add to `../../tests/test_coverage_gaps.py`:

```python
def test_refinance_route_documents_validation_and_engine_authority():
    from server.routes_planning import refinance

    rationale = refinance.__doc__ or ""

    assert "validat" in rationale.lower()
    assert "delegat" in rationale.lower()
    assert "analyze_refinance" in rationale
```

- [ ] **Step 2: Run the contract test and verify RED**

From the DebtGPS root, run:

```powershell
pytest tests/test_coverage_gaps.py::test_refinance_route_documents_validation_and_engine_authority -v
```

Expected: FAIL because `refinance.__doc__` is empty.

- [ ] **Step 3: Add the minimal rationale docstring**

Add immediately inside `refinance()`:

```python
def refinance():
    """Validate request and ownership state, then delegate pricing to analyze_refinance.

    The route is an HTTP boundary only; canonical payoff and refinance math stays
    in the engine so route behavior cannot diverge from planning simulations.
    """
```

Do not change the route body.

- [ ] **Step 4: Run the focused route tests**

From the DebtGPS root, run:

```powershell
pytest tests/test_coverage_gaps.py::test_refinance_route_documents_validation_and_engine_authority tests/test_coverage_gaps.py::test_refinance_requires_a_term_or_a_payment tests/test_routes.py::test_refinance_route_consolidates_and_validates -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit Task 6 in the DebtGPS repository only if the user-owned worktree policy permits a focused commit**

If existing unrelated changes make a focused commit unsafe, leave the verified modification uncommitted and report it. Otherwise:

```powershell
git add server/routes_planning.py tests/test_coverage_gaps.py
git commit -m "docs: explain refinance route authority"
```

---

### Task 7: Run Graphify Regression Gates and Install the Local Build

**Files:**
- Verify all Graphify changes
- Update the active uv tool environment

- [ ] **Step 1: Run formatting/static checks configured by the repository**

From the Graphify checkout:

```powershell
uv run ruff check graphify tests/test_languages.py tests/test_incremental.py tests/test_symbol_resolution.py tests/test_analyze.py tests/test_gap_reporting.py
```

Expected: exit 0. If `ruff` is not configured in the environment, record that fact and run the repository's configured pre-commit checks instead.

- [ ] **Step 2: Run focused Graphify regression suites**

```powershell
uv run pytest tests/test_languages.py tests/test_incremental.py tests/test_symbol_resolution.py tests/test_analyze.py tests/test_gap_reporting.py tests/test_node_id_canonical.py -v
```

Expected: all selected tests pass with zero failures.

- [ ] **Step 3: Run the full Graphify test suite**

```powershell
uv run pytest -q
```

Expected: exit 0. If unrelated pre-existing failures occur, rerun each failure in isolation, capture evidence, and do not classify the patch as fully green until the distinction is proven.

- [ ] **Step 4: Install Graphify from the verified checkout**

```powershell
uv tool install --force --from . graphifyy
```

Expected: the `graphifyy` tool environment is replaced from the local checkout.

- [ ] **Step 5: Verify the active executable**

```powershell
Get-Command graphify | Format-List Source
graphify --version
```

Expected: the known local executable path is used and its version matches the checkout metadata.

---

### Task 8: Perform the Cached Semantic Extraction and Rebuild DebtGPS

**Files:**
- Read: `../../.codex/skills/graphify/references/extraction-spec.md`
- Refresh: `../../graphify-out/`

- [ ] **Step 1: Re-read the semantic extraction contract completely**

Read the full DebtGPS Graphify extraction specification before launching semantic work. Confirm the allowed node schema, relation directions, file-type enum, rationale policy, cache output requirements, and token-usage reporting.

- [ ] **Step 2: Re-detect the corpus and cache state**

From the DebtGPS root, run the Graphify detection/cache procedure and save the exact uncached list. Expected baseline from design time:

```text
448 files
641,073 words
310 code files
113 documents
25 images
138 semantic files
134 cached
4 uncached documents
0 uncached images
```

The execution-time result is authoritative; do not force these baseline numbers if files changed.

- [ ] **Step 3: Extract only current cache misses**

Because no `GEMINI_API_KEY` or `GOOGLE_API_KEY` is configured, use one host semantic extraction task for up to 25 uncached documents. Each image cache miss, if any, gets its own task. Require schema-valid JSON, exact `source_file`, cache save, and reported input/output token usage.

- [ ] **Step 4: Merge cached semantics and rebuild**

Run the Graphify merge/build/cluster/report sequence prescribed by the installed skill so cached semantic output, fresh semantic output, and AST output all contribute to the final graph. Then run:

```powershell
graphify update .
```

Expected: AST state is current after all DebtGPS code changes, with no API cost for the update step.

- [ ] **Step 5: Capture build metrics and warnings**

Record final node, edge, and community counts; cached/fresh semantic counts; token usage; and every graph-health warning. A generated report with a health warning is not considered a clean build.

---

### Task 9: Verify DebtGPS Graph Acceptance and Close Remaining Gaps

**Files:**
- Verify: `../../docs/debt-model.md`
- Verify: `../../graphify-out/graph.json`
- Verify: `../../graphify-out/GRAPH_REPORT.md`
- Verify: DebtGPS focused test suites

- [ ] **Step 1: Verify all documented local links**

Run a local-link checker over `docs/debt-model.md` that strips Markdown fragments, resolves paths relative to the document, and asserts every referenced local file exists. Expected: 0 broken local links.

- [ ] **Step 2: Verify the nine documentation-to-code targets**

Load `graphify-out/graph.json`; for each critical implementation link in the DebtGPS canonical map, resolve the target file and optional line with the same deterministic rule and assert at least one incoming `references` edge from a document node. Print the nine source-document/target-node pairs as evidence.

- [ ] **Step 3: Verify canonical `OrderFn`**

Query graph nodes whose normalized label is `orderfn`. Assert:

```python
assert len(orderfn_nodes) == 1
assert orderfn_nodes[0].get("source_file")
assert orderfn_nodes[0].get("node_kind") == "type_alias"
```

- [ ] **Step 4: Verify known external symbols are retained but benign**

For `route`, `Flask`, `parametrize`, `given`, and `composite`, print matching nodes and their classification. Assert no matching node appears in the actionable-isolated set while externally evidenced matches remain in `graph.json`.

- [ ] **Step 5: Verify every weak/thin node is categorized**

Recompute weak nodes and thin communities using the report rules. Assert the category counts sum to their respective totals and print:

```text
actionable_local
external
rationale
metadata
structural
```

Any remaining actionable local node is reported with label, source file, degree, and community rather than silently declared closed.

- [ ] **Step 6: Run focused DebtGPS verification suites**

From the DebtGPS root:

```powershell
pytest tests/test_planning.py tests/test_math_oracle.py tests/test_event_integrity.py tests/test_audit_batch1.py tests/test_audit_batch6.py tests/test_audit_batch7.py tests/test_routes.py tests/test_coverage_gaps.py tests/test_scenario_authority.py tests/test_scenario_provenance.py -q
```

Expected: zero failures.

- [ ] **Step 7: Review diffs and repository state**

In both repositories, run:

```powershell
git status --short
git diff --check
git log --oneline -8
```

Confirm no unrelated user change was overwritten and every Graphify production change has a previously observed RED test and a current GREEN test.

- [ ] **Step 8: Final evidence summary**

Report:

- Graphify commits and changed components
- DebtGPS changed files
- focused and full test counts
- final graph node/edge/community counts
- semantic cache hits/misses and token usage
- nine document-to-code reference results
- canonical `OrderFn` result
- external/benign/actionable gap breakdown
- every unresolved graph-health warning or actionable local node

Do not state that all gaps are closed unless the fresh acceptance checks show zero remaining actionable local gaps.
