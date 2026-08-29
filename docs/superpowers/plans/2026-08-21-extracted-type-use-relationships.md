# Extracted Type-Use Relationships Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace annotation-backed Python `uses/INFERRED` edges with deterministic `uses_type/EXTRACTED` edges that preserve every type role without weakening runtime relationships.

**Architecture:** Extend the existing two-pass Python import resolver instead of adding a second parser. The resolver will classify imported identifiers by their Tree-sitter ancestor context, aggregate type roles per source-target pair, and use unchanged-corpus nodes as read-only targets during incremental extraction. `uses_type` joins the graph builder's generic-relation set so `calls`, `inherits`, and other runtime facts remain the single surviving edge in Graphify's simple graph.

**Tech Stack:** Python 3.10+, Tree-sitter Python, NetworkX, pytest

---

## File Structure

- `graphify/extractors/resolution.py` owns Python import-target indexing, annotation-context classification, role aggregation, and raw `uses_type` edge emission.
- `graphify/extract.py` supplies unchanged-corpus nodes and the scan root to the resolver during incremental extraction.
- `graphify/build.py` classifies `uses_type` as generic for same-endpoint collapse precedence.
- `tests/test_extract.py` verifies raw full-extraction semantics, nesting, aliases, forward references, and conservative fallback behavior.
- `tests/test_incremental.py` proves a changed importer resolves the same type target and metadata when its definition file is unchanged.
- `tests/test_relation_collapse_precedence.py` proves runtime edges beat `uses_type` in both input orders and retain their own metadata.
- `docs/superpowers/specs/2026-08-21-extracted-type-use-relationships-design.md` is the approved design contract; implementation must not broaden beyond its Python-only scope.

### Task 1: Emit extracted type-use edges from Python annotations

**Files:**
- Modify: `tests/test_extract.py:3873`
- Modify: `graphify/extractors/resolution.py:1880-2076`

- [ ] **Step 1: Add focused failing extraction tests**

Add this helper and these tests immediately after `_inferred_uses` in `tests/test_extract.py`:

```python
def _type_uses(result):
    """Every deterministic cross-file Python type-use edge."""
    return [e for e in result["edges"] if e.get("relation") == "uses_type"]


def test_cross_file_annotations_emit_extracted_roles(tmp_path):
    (tmp_path / "models.py").write_text(
        "class Payload:\n    pass\n", encoding="utf-8"
    )
    (tmp_path / "api.py").write_text(
        "from models import Payload as P\n\n\n"
        "class Envelope:\n"
        "    value: P\n\n\n"
        "def convert(values: list[P | None]) -> \"P\":\n"
        "    return values[0]\n\n\n"
        "def build(value: P) -> P:\n"
        "    return P()\n",
        encoding="utf-8",
    )

    result = extract(
        [tmp_path / "api.py", tmp_path / "models.py"],
        cache_root=tmp_path,
    )
    by_source = {edge["source"]: edge for edge in _type_uses(result)}

    assert by_source["api_envelope"] == {
        "source": "api_envelope",
        "target": "models_payload",
        "relation": "uses_type",
        "context": "type_annotation",
        "type_roles": ["field"],
        "confidence": "EXTRACTED",
        "confidence_score": 1.0,
        "source_file": str(tmp_path / "api.py"),
        "source_location": "L5",
        "weight": 1.0,
    }
    assert by_source["api_convert"]["target"] == "models_payload"
    assert by_source["api_convert"]["type_roles"] == ["parameter", "return"]
    assert by_source["api_convert"]["confidence"] == "EXTRACTED"
    assert by_source["api_convert"]["confidence_score"] == 1.0
    assert by_source["api_build"]["type_roles"] == ["parameter", "return"]
    inferred_pairs = {
        (edge["source"], edge["target"])
        for edge in result["edges"]
        if edge.get("relation") == "uses" and edge.get("confidence") == "INFERRED"
    }
    assert not inferred_pairs & {
        ("api_envelope", "models_payload"),
        ("api_convert", "models_payload"),
    }
    # Raw extraction retains both facts. The graph builder chooses `calls` for
    # this endpoint pair in Task 3.
    assert ("api_build", "models_payload") in inferred_pairs


def test_nested_annotations_record_nested_roles_on_the_owner(tmp_path):
    (tmp_path / "models.py").write_text("class Debt:\n    pass\n", encoding="utf-8")
    (tmp_path / "order.py").write_text(
        "from models import Debt\n\n\n"
        "def order_custom():\n"
        "    def key(debt: Debt) -> Debt:\n"
        "        return debt\n"
        "    return key\n\n\n"
        "class Holder:\n"
        "    class Inner:\n"
        "        debt: Debt\n",
        encoding="utf-8",
    )

    result = extract(
        [tmp_path / "order.py", tmp_path / "models.py"],
        cache_root=tmp_path,
    )
    by_source = {edge["source"]: edge for edge in _type_uses(result)}

    assert by_source["order_order_custom"]["type_roles"] == [
        "nested_parameter",
        "nested_return",
    ]
    assert by_source["order_holder"]["type_roles"] == ["nested_field"]


def test_local_annotation_and_body_reference_keep_conservative_uses(tmp_path):
    (tmp_path / "models.py").write_text("class Helper:\n    pass\n", encoding="utf-8")
    (tmp_path / "api.py").write_text(
        "from models import Helper\n\n\n"
        "def handler():\n"
        "    local: Helper = Helper()\n"
        "    return local\n",
        encoding="utf-8",
    )

    result = extract(
        [tmp_path / "api.py", tmp_path / "models.py"],
        cache_root=tmp_path,
    )

    assert ("api_handler", "models_helper") in _inferred_uses(result)
    assert not any(edge["source"] == "api_handler" for edge in _type_uses(result))


def test_type_use_skips_ambiguous_and_external_targets(tmp_path):
    for package in ("one", "two"):
        folder = tmp_path / package
        folder.mkdir()
        (folder / "models.py").write_text(
            "class Payload:\n    pass\n", encoding="utf-8"
        )
    api = tmp_path / "api.py"
    api.write_text(
        "from models import Payload\n"
        "from pathlib import Path\n\n\n"
        "def load(value: Payload, path: Path) -> Payload:\n"
        "    return value\n",
        encoding="utf-8",
    )
    star = tmp_path / "star.py"
    star.write_text(
        "from one.models import *\n\n\n"
        "def load(value: Payload) -> Payload:\n"
        "    return value\n",
        encoding="utf-8",
    )

    result = extract(
        [
            api,
            star,
            tmp_path / "one" / "models.py",
            tmp_path / "two" / "models.py",
        ],
        cache_root=tmp_path,
    )

    assert not any(edge["source"] == "api_load" for edge in _type_uses(result))
    assert not any(edge["source"] == "star_load" for edge in _type_uses(result))
```

- [ ] **Step 2: Run the new tests and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extract.py -k "cross_file_annotations_emit_extracted_roles or nested_annotations_record_nested_roles or local_annotation_and_body_reference" -q
```

Expected: the annotation and ambiguity tests fail because `uses_type` classification and ambiguous-target rejection are not implemented; the conservative local-annotation test may already pass.

- [ ] **Step 3: Add syntax-context classification and role aggregation**

Replace `_resolve_cross_file_imports`' docstring with:

```python
    """Resolve source-backed Python imports at the symbol level.

    Pass one indexes project definitions by directory-qualified module stem.
    Pass two attributes each imported-name occurrence to its top-level owning
    class or function. Supported annotations emit deterministic ``uses_type``
    edges with aggregated roles; other body references retain the conservative
    ``uses/INFERRED`` relationship.
    """
```

In `_resolve_cross_file_imports`, replace the single `ref_sources` declaration and the existing `visit` implementation with the following complete block. Keep `resolve_import` unchanged above it.

```python
        # referenced name -> {source symbol nid: first body-reference line}
        ref_sources: dict[str, dict[str, int]] = {}
        # referenced name -> source symbol nid -> roles + first annotation line
        type_ref_sources: dict[str, dict[str, dict[str, Any]]] = {}

        def _same_node(left, right) -> bool:
            return (
                left is not None
                and right is not None
                and left.type == right.type
                and left.start_byte == right.start_byte
                and left.end_byte == right.end_byte
            )

        def _contains(outer, inner) -> bool:
            return (
                outer is not None
                and outer.start_byte <= inner.start_byte
                and inner.end_byte <= outer.end_byte
            )

        def _annotation_role(ref_node, owner_node) -> str | None:
            """Classify an identifier/string only when it is inside a supported annotation."""
            cursor = ref_node
            kind: str | None = None
            anchor = None
            while cursor.parent is not None and not _same_node(cursor, owner_node):
                parent = cursor.parent
                if parent.type in ("typed_parameter", "typed_default_parameter"):
                    type_node = parent.child_by_field_name("type")
                    if _contains(type_node, ref_node):
                        kind, anchor = "parameter", parent
                        break
                if parent.type == "function_definition":
                    return_node = parent.child_by_field_name("return_type")
                    if _contains(return_node, ref_node):
                        kind, anchor = "return", parent
                        break
                if parent.type == "assignment":
                    type_node = parent.child_by_field_name("type")
                    if _contains(type_node, ref_node):
                        kind, anchor = "field", parent
                        break
                cursor = parent

            if kind is None or anchor is None:
                return None

            if kind == "field":
                scope = anchor.parent
                while scope is not None and not _same_node(scope, owner_node):
                    if scope.type in ("class_definition", "function_definition"):
                        break
                    scope = scope.parent
                if scope is None or scope.type != "class_definition":
                    return None
                return "field" if _same_node(scope, owner_node) else "nested_field"

            annotation_function = anchor
            while (
                annotation_function is not None
                and annotation_function.type != "function_definition"
            ):
                annotation_function = annotation_function.parent
            if annotation_function is None:
                return None
            if owner_node.type == "function_definition":
                nested = not _same_node(annotation_function, owner_node)
            else:
                nested = False
                scope = annotation_function.parent
                while scope is not None and not _same_node(scope, owner_node):
                    if scope.type in ("class_definition", "function_definition"):
                        nested = True
                    scope = scope.parent
                if scope is None:
                    return None
            return f"nested_{kind}" if nested else kind

        def _record_type_ref(name: str, source_nid: str, role: str, line: int) -> None:
            by_source = type_ref_sources.setdefault(name, {})
            evidence = by_source.setdefault(source_nid, {"roles": set(), "line": line})
            evidence["roles"].add(role)
            evidence["line"] = min(evidence["line"], line)

        def visit(node, current_nid: str | None, owner_node=None) -> None:
            # Identifiers inside an import statement are the import itself, not a
            # real use — resolve the import here and don't descend into it.
            if node.type == "import_from_statement":
                resolve_import(node)
                return
            # Attribute references to the top-level symbol that contains them.
            if current_nid is None and node.type in ("class_definition", "function_definition"):
                name_node = node.child_by_field_name("name")
                if name_node is not None:
                    mapped = name_to_nid.get(_text(name_node))
                    if mapped is not None:
                        current_nid = mapped
                        owner_node = node
            if current_nid is not None and owner_node is not None:
                if node.type == "identifier":
                    name = _text(node)
                    role = _annotation_role(node, owner_node)
                    if role is None:
                        slot = ref_sources.setdefault(name, {})
                        slot.setdefault(current_nid, node.start_point[0] + 1)
                    else:
                        _record_type_ref(
                            name, current_nid, role, node.start_point[0] + 1
                        )
                elif node.type == "string":
                    role = _annotation_role(node, owner_node)
                    if role is not None:
                        # Tokenize only a string already proven to be an annotation;
                        # do not evaluate it as Python.
                        for name in re.findall(r"\b[A-Za-z_]\w*\b", _text(node)):
                            _record_type_ref(
                                name, current_nid, role, node.start_point[0] + 1
                            )
            for child in node.children:
                visit(child, current_nid, owner_node)
```

Then replace the emission loop after `visit(tree.root_node, None)` with this complete loop:

```python
        for name, tgt_nid in import_targets.items():
            for src_nid, line in ref_sources.get(name, {}).items():
                if src_nid == tgt_nid:
                    continue
                new_edges.append({
                    "source": src_nid,
                    "target": tgt_nid,
                    "relation": "uses",
                    "confidence": "INFERRED",
                    "confidence_score": 0.95,
                    "source_file": str_path,
                    "source_location": f"L{line}",
                    "weight": 0.8,
                })
            for src_nid, evidence in type_ref_sources.get(name, {}).items():
                if src_nid == tgt_nid:
                    continue
                new_edges.append({
                    "source": src_nid,
                    "target": tgt_nid,
                    "relation": "uses_type",
                    "context": "type_annotation",
                    "type_roles": sorted(evidence["roles"]),
                    "confidence": "EXTRACTED",
                    "confidence_score": 1.0,
                    "source_file": str_path,
                    "source_location": f"L{evidence['line']}",
                    "weight": 1.0,
                })
```

Also make the existing bare-module fallback reject collisions instead of retaining its first match. Change its declaration and assignment to:

```python
    bare_to_qualified: dict[str, str | None] = {}

    # Inside the pass-one node loop, after fq_stem is known:
    bare = src_path.stem
    if bare not in bare_to_qualified:
        bare_to_qualified[bare] = fq_stem
    elif bare_to_qualified[bare] != fq_stem:
        bare_to_qualified[bare] = None
```

`resolve_import` already returns when `target_fq` is falsey, so ambiguous absolute imports now produce no local type binding. Exact relative imports still use their directory-qualified stem and remain unaffected.

- [ ] **Step 4: Run the focused extraction tests and existing resolver regressions**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_extract.py -k "cross_file_annotations_emit_extracted_roles or nested_annotations_record_nested_roles or local_annotation_and_body_reference or type_use_skips_ambiguous or inferred_uses_edge or cross_file_type_annotation_refs" -q
```

Expected: all selected tests pass. Existing body-only references remain `uses/INFERRED 0.95`; supported annotations become `uses_type/EXTRACTED 1.0`.

- [ ] **Step 5: Commit the annotation extractor behavior**

```powershell
git add graphify/extractors/resolution.py tests/test_extract.py
git commit -m "feat: extract Python type-use relationships"
```

### Task 2: Make type-use resolution identical in full and incremental extraction

**Files:**
- Modify: `tests/test_incremental.py:214`
- Modify: `graphify/extractors/resolution.py:1880-1936`
- Modify: `graphify/extract.py:5484-5522`
- Modify: `graphify/extract.py:6270-6279`

- [ ] **Step 1: Add a failing changed-importer regression test**

Add this test before `test_incremental_python_relative_import_target_canonicalizes` in `tests/test_incremental.py`:

```python
def test_incremental_python_type_use_matches_full_extraction(tmp_path):
    from graphify.extract import extract

    pkg = tmp_path / "pkg"
    pkg.mkdir()
    model = pkg / "models.py"
    model.write_text("class Debt:\n    pass\n", encoding="utf-8")
    planner = pkg / "planner.py"
    planner.write_text(
        "from .models import Debt\n\n\n"
        "def prioritize(debts: list[Debt]) -> Debt:\n"
        "    return debts[0]\n",
        encoding="utf-8",
    )

    full = extract(
        [planner, model], cache_root=tmp_path, root=tmp_path, parallel=False
    )
    incremental = extract(
        [planner],
        cache_root=tmp_path,
        root=tmp_path,
        parallel=False,
        resolution_context_nodes=full["nodes"],
        resolution_context_edges=full["edges"],
    )

    def type_edge(result):
        return next(
            edge
            for edge in result["edges"]
            if edge.get("relation") == "uses_type"
            and edge.get("source") == "pkg_planner_prioritize"
        )

    full_edge = type_edge(full)
    incremental_edge = type_edge(incremental)
    assert incremental_edge["target"] == full_edge["target"] == "pkg_models_debt"
    assert incremental_edge["type_roles"] == ["parameter", "return"]
    assert incremental_edge["confidence"] == "EXTRACTED"
    assert incremental_edge["confidence_score"] == 1.0
```

- [ ] **Step 2: Run the incremental test and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_incremental.py::test_incremental_python_type_use_matches_full_extraction -q
```

Expected: FAIL because the unchanged `models.py` definition is absent from `_resolve_cross_file_imports`' target index.

- [ ] **Step 3: Extend only the resolver's target index with context nodes**

Change the resolver signature to:

```python
def _resolve_cross_file_imports(
    per_file: list[dict],
    paths: list[Path],
    *,
    resolution_context_nodes: list[dict] | None = None,
    root: Path | None = None,
) -> list[dict]:
```

Replace the pass-one indexing loop with this implementation. Fresh definitions are indexed first and win; context nodes are read-only fallbacks.

```python
    stem_to_entities: dict[str, dict[str, str]] = {}
    bare_to_qualified: dict[str, str | None] = {}

    def index_definition(node: dict, *, overwrite: bool) -> None:
        src = node.get("source_file", "")
        if not src:
            return
        src_path = Path(src)
        if root is not None and not src_path.is_absolute():
            src_path = Path(root) / src_path
        if src_path.suffix not in (".py", ".pyi"):
            return
        fq_stem = _file_stem(src_path)
        label = node.get("label", "")
        nid = node.get("id", "")
        if (
            not label
            or label.endswith((")", ".py", ".pyi"))
            or "_" in label[:1]
            or node.get("file_type") == "rationale"
        ):
            return
        entities = stem_to_entities.setdefault(fq_stem, {})
        if overwrite:
            entities[label] = nid
        else:
            entities.setdefault(label, nid)
        bare = src_path.stem
        if bare not in bare_to_qualified:
            bare_to_qualified[bare] = fq_stem
        elif bare_to_qualified[bare] != fq_stem:
            bare_to_qualified[bare] = None

    for file_result in per_file:
        for node in file_result.get("nodes", []):
            index_definition(node, overwrite=True)
    for node in resolution_context_nodes or []:
        index_definition(node, overwrite=False)
```

In `graphify/extract.py`, update the invocation to:

```python
            cross_file_edges = _resolve_cross_file_imports(
                py_results,
                py_paths,
                resolution_context_nodes=resolution_context_nodes,
                root=root,
            )
```

In `extract()`'s docstring, replace the second process step with:

```python
    2. Cross-file import resolution: emits source-backed runtime relationships
       and deterministic Python ``uses_type`` edges.
```

Replace the `resolution_context_nodes` argument paragraph with:

```python
        resolution_context_nodes: read-only AST nodes from files that are NOT
            being extracted this run (an incremental rebuild's unchanged
            corpus, #2406). They extend the Python import/type-use target index,
            the shared direct-call label/file indexes, the indirect_call
            callable guard (via persisted `_callable` / `_callable_class`
            markers, #2438), and member-call resolvers run by
            `run_language_resolvers` (#2437). They are never parsed, mutated,
            or returned; only edges sourced by re-extracted files are emitted.
```

- [ ] **Step 4: Run incremental and full-extraction tests**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_incremental.py::test_incremental_python_type_use_matches_full_extraction tests/test_incremental.py::test_incremental_python_relative_import_target_canonicalizes tests/test_extract.py -k "type_use or annotations_emit or nested_annotations or inferred_uses_edge" -q
```

Expected: all selected tests pass, and the full and incremental type edges have identical target, roles, and confidence.

- [ ] **Step 5: Commit incremental parity**

```powershell
git add graphify/extract.py graphify/extractors/resolution.py tests/test_incremental.py
git commit -m "fix: resolve type uses against incremental context"
```

### Task 3: Preserve runtime relationships during simple-graph collapse

**Files:**
- Modify: `tests/test_relation_collapse_precedence.py:25-29`
- Modify: `graphify/build.py:55-63`

- [ ] **Step 1: Expand the precedence test matrix and pin metadata survival**

Change the test module's generic list and add the focused regression:

```python
GENERIC = ["references", "uses", "uses_type", "mentions"]


def test_calls_beats_uses_type_and_keeps_runtime_metadata():
    for edges in (
        [
            _edge("calls", source_location="L9", weight=1.0, confidence_score=1.0),
            _edge(
                "uses_type",
                source_location="L4",
                context="type_annotation",
                type_roles=["return"],
                weight=1.0,
                confidence_score=1.0,
            ),
        ],
        [
            _edge(
                "uses_type",
                source_location="L4",
                context="type_annotation",
                type_roles=["return"],
                weight=1.0,
                confidence_score=1.0,
            ),
            _edge("calls", source_location="L9", weight=1.0, confidence_score=1.0),
        ],
    ):
        graph = build_from_json(_extraction(edges))
        data = edge_data(graph, "a", "b")
        assert data["relation"] == "calls"
        assert data["source_location"] == "L9"
        assert "type_roles" not in data
```

- [ ] **Step 2: Run the precedence tests and verify the red state**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_relation_collapse_precedence.py -q
```

Expected: cases containing `uses_type` fail because an unknown relation is currently treated as specific.

- [ ] **Step 3: Mark `uses_type` as a generic structural relationship**

Change the constant in `graphify/build.py` to:

```python
_GENERIC_RELATIONS: frozenset[str] = frozenset(
    {"references", "uses", "uses_type", "mentions"}
)
```

Do not add a total relation ranking. The existing specific-versus-generic guard is sufficient and preserves prior behavior between two specific or two generic relations.

- [ ] **Step 4: Run the precedence and build suites**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_relation_collapse_precedence.py tests/test_build.py -q
```

Expected: all tests pass; `calls` survives over `uses_type` in either input order.

- [ ] **Step 5: Commit graph precedence support**

```powershell
git add graphify/build.py tests/test_relation_collapse_precedence.py
git commit -m "fix: preserve runtime edges over type uses"
```

### Task 4: Verify Graphify and rebuild the DebtGPS knowledge graph

**Files:**
- Verify: `graphify/extractors/resolution.py`
- Verify: `graphify/extract.py`
- Verify: `graphify/build.py`
- Update generated output: `C:/Users/souma/OneDrive/Desktop/Debt Application/Application/DebtGPS/graphify-out/`

- [ ] **Step 1: Run formatting guards and the focused feature suite**

Run from `tmp/graphify-src`:

```powershell
git diff --check
.\.venv\Scripts\python.exe -m pytest tests/test_extract.py tests/test_incremental.py tests/test_relation_collapse_precedence.py tests/test_build.py -q
```

Expected: `git diff --check` prints nothing; all selected tests pass.

- [ ] **Step 2: Run the complete Graphify test suite**

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: the suite completes with zero failures. Pre-existing permission warnings from ignored `.pytest-*` directories do not count as failures.

- [ ] **Step 3: Install the working tree into the configured Graphify tool environment**

The DebtGPS graph records its interpreter in `graphify-out/.graphify_python`. Ensure that environment has pip, then install this checkout without downloading dependencies:

```powershell
& 'C:\Users\souma\AppData\Roaming\uv\tools\graphifyy\Scripts\python.exe' -m ensurepip --upgrade
& 'C:\Users\souma\AppData\Roaming\uv\tools\graphifyy\Scripts\python.exe' -m pip install --no-build-isolation --no-deps --editable 'C:\Users\souma\OneDrive\Desktop\Debt Application\Application\DebtGPS\tmp\graphify-src'
graphify --version
```

Expected: the editable install succeeds and `graphify --version` reports `0.9.48` from the enhanced checkout. This step writes to the user-managed tool environment and therefore may require the normal workspace approval prompt.

- [ ] **Step 4: Rebuild DebtGPS's AST tier while preserving semantic and document tiers**

Run from the DebtGPS root:

```powershell
graphify update . --force
```

Expected: Graphify performs a full code-corpus rebuild because `update` calls `_rebuild_code` with no changed-path subset. Existing semantic/document nodes are retained by tier-aware merge behavior.

- [ ] **Step 5: Assert the corrected Debt relationships**

Run from the DebtGPS root:

```powershell
.\tmp\graphify-src\.venv\Scripts\python.exe -c "import json; p='graphify-out/graph.json'; d=json.load(open(p,encoding='utf-8')); es=d.get('links',d.get('edges',[])); debt='engine_models_debt'; rel=[e for e in es if debt in (e.get('source'),e.get('target'),e.get('_src'),e.get('_tgt'))]; typed=[e for e in rel if e.get('relation')=='uses_type']; inferred=[e for e in rel if e.get('confidence')=='INFERRED']; assert len(typed)==34,(len(typed),typed); assert all(e.get('confidence')=='EXTRACTED' and e.get('confidence_score')==1.0 and e.get('type_roles') for e in typed); assert len(inferred)<=4,(len(inferred),inferred); ps=next(e for e in typed if 'engine_action_plan_planstate' in (e.get('source'),e.get('target'),e.get('_src'),e.get('_tgt'))); assert 'field' in ps['type_roles']; ref=next(e for e in rel if 'engine_refinance_analyze_refinance' in (e.get('source'),e.get('target'),e.get('_src'),e.get('_tgt'))); assert ref['relation']=='calls' and ref['confidence']=='EXTRACTED',ref; print({'debt_type_edges':len(typed),'remaining_inferred':len(inferred),'plan_state_roles':ps['type_roles'],'refinance_relation':ref['relation']})"
```

Expected output contains:

```text
'debt_type_edges': 34
'plan_state_roles': ['field']
'refinance_relation': 'calls'
```

The remaining inferred count is at most four and is limited to body-only test constructor sites rather than annotations.

- [ ] **Step 6: Run DebtGPS's focused domain verification suite**

Use the project's existing test environment and run the same focused coverage used for the original audit:

```powershell
pytest tests/test_models.py tests/test_budget.py tests/test_action_plan.py tests/test_planning.py tests/test_routes.py tests/test_scenario_authority.py tests/test_audit_batch1.py tests/test_audit_batch6.py tests/test_audit_batch7.py tests/test_coverage_gaps.py -q
```

Expected: all tests pass; the previous baseline was 161 passing tests.

- [ ] **Step 7: Commit any final source-only cleanup**

If verification required a source or test correction, commit only those Graphify files:

```powershell
git add graphify tests
git commit -m "test: verify extracted type-use relationships"
```

If no correction was required, do not create an empty commit. Leave DebtGPS's generated `graphify-out/` changes uncommitted unless the user separately asks to commit generated graph artifacts.
