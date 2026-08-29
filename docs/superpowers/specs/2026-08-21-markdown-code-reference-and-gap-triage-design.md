# Design: Markdown-to-Code References and Actionable Gap Triage

**Date:** 2026-08-21
**Branch:** v8
**Consumer validation corpus:** DebtGPS

---

## Problem

Graphify currently builds useful structural graphs for code and useful semantic graphs for documents, but three deterministic boundaries leave avoidable gaps in a mixed code-and-document corpus:

1. The Markdown extractor follows links only when the target is another document. A design or domain document can link to `server/routes_planning.py` or `server/routes_planning.py#L83`, but Graphify discards that reference instead of connecting the document to the implementation it describes.
2. Python import-guided resolution canonicalizes callable uses, but imported type aliases such as `OrderFn` can remain as sourceless stubs beside their source-backed definition.
3. Knowledge-gap analysis treats several benign leaves as actionable gaps. Framework symbols, test-library symbols, rationale leaves, and metadata/configuration keys can dominate isolated-node and thin-community counts even when no project work is missing.

DebtGPS exposes all three limitations. Its domain-model documentation contains explicit code references that should become graph edges; `OrderFn` is split across imported and defined representations; and symbols such as `route`, `Flask`, `parametrize`, `given`, and `composite` are dependencies rather than missing local implementations.

The enhancement must improve graph fidelity without introducing LLM inference into code resolution, deleting useful semantic nodes, or changing existing document-to-document link behavior.

---

## Goals

- Convert local Markdown links to code files into deterministic `references` edges.
- Use a `#L<number>` fragment to connect a document to the exact or nearest source-backed symbol in that file.
- Canonicalize Python imported type-alias references when import evidence uniquely identifies a source-backed alias.
- Mark provable external symbols consistently and remove them from actionable gap counts while retaining them in the graph.
- Separate actionable local gaps from benign external, rationale, and metadata/configuration leaves in analysis and reporting.
- Preserve semantic extraction cache behavior and merge the four currently uncached DebtGPS documents with the 134 cached semantic results.
- Add the missing rationale for the DebtGPS refinance route and prove the documented implementation-to-verification links are represented in the rebuilt graph.

## Non-goals

- Resolving arbitrary prose mentions that are not links.
- Resolving Markdown heading fragments to document-heading nodes; existing document-link behavior remains unchanged.
- Inferring symbol ranges with a language server or compiler.
- Binding a sourceless name to a same-named local symbol without unique path/import evidence.
- Removing external, rationale, or metadata nodes from `graph.json`.
- Running an LLM over code; code remains AST-extracted and deterministically resolved.
- Reclassifying low-cohesion communities as bugs. The change only makes their reported composition explicit.

---

## Design Principles

1. **Evidence before name matching.** A local path plus line anchor, or a Python import plus module/name pair, is sufficient evidence. A bare matching label is not.
2. **Lossless graph, selective reporting.** Benign nodes remain queryable; only their gap classification changes.
3. **Backward-compatible extraction.** Existing Markdown document links, wikilinks, reference definitions, cache stamps, and incremental remapping continue to work.
4. **Deterministic fallback.** Ambiguous or malformed references fall back to a file node or remain unresolved; they never pick a symbol nondeterministically.
5. **One classification vocabulary.** Analysis and report rendering consume the same node-classification helper so their counts cannot drift.

---

## Architecture

```text
Markdown extractor
  local link + optional #L line
            |
            v
  references edge stamped with target_file / target_line
            |
            v
whole-corpus deterministic resolution pass
  target file index + source-line symbol index
            |
            +--> exact symbol at line
            +--> nearest preceding symbol in file
            +--> target file node fallback

Python extraction fragments
  imports + type-alias definitions/references
            |
            v
import-guided symbol resolution
  unique (module, alias) source-backed match
            |
            v
canonical alias node; duplicate stub rewired/removed

final graph
            |
            v
shared gap classifier
  actionable_local | external | rationale | metadata | structural
            |
            +--> suggest_questions()
            +--> GRAPH_REPORT.md gap and community breakdowns
```

The Markdown extractor records resolution evidence but does not select a code symbol itself. At per-file extraction time, it cannot see all source nodes and would produce order-dependent results. Symbol selection therefore happens in the existing whole-corpus normalization/resolution stage after all file fragments are available and before edge stamps are removed.

---

## Component 1: Structured Markdown Link Targets

### Files

- `graphify/extractors/markdown.py`
- `graphify/extractors/base.py` or a new small shared path-classification helper if importing the central extractor registry would create a cycle
- `tests/test_languages.py`
- `tests/test_incremental.py`
- `tests/test_cache.py`

### Target representation

Introduce an immutable internal value object, `ResolvedMarkdownTarget`, with:

```python
path: Path
line: int | None
```

A new parser/resolver returns this structured target. `_resolve_markdown_link()` remains as a compatibility wrapper that returns only `Path | None` for existing callers and tests.

### Accepted targets

- Existing document extensions remain accepted exactly as today.
- Local files with extensions already recognized as code by Graphify are accepted as code targets.
- `#L83` and case-insensitive `#l83` are accepted as one-based line anchors for code targets.
- A query string may precede the fragment; both are removed from the filesystem path.
- External URLs, protocol-relative URLs, `mailto:`, `tel:`, `data:`, images, and pure in-page anchors continue to be skipped.
- An absent, zero, negative, non-numeric, or overflow line anchor is treated as no usable line evidence; the local file link can still resolve to its file node.
- Extensionless wikilinks remain document links. The feature does not guess that an extensionless name is code.

### Extracted edge

The source remains the Markdown page node. The edge remains:

```json
{
  "relation": "references",
  "confidence": "EXTRACTED",
  "target_file": "<normalized target path>",
  "target_line": 83
}
```

`target_line` is omitted when no valid code-line fragment exists. The provisional target ID is the normal file-node ID so the edge is still valid if later symbol resolution cannot improve it. The existing `target_file` stamp remains the authoritative incremental/canonical-path evidence.

### Existing behavior preserved

- Document targets still end at the target document page node, even if their URL has a heading fragment.
- Obsidian vault fallback is applied only to document wikilinks.
- Inline, reference-style, and wikilink extraction share the same structured parser.
- Cached paths continue to be remapped when a corpus root or file location changes.

---

## Component 2: Line-Aware Code Target Resolution

### Files

- `graphify/extract.py`
- `graphify/symbol_resolution.py`
- `tests/test_symbol_resolution.py`
- `tests/test_node_id_canonical.py`
- `tests/test_incremental.py`

### Index

Build a per-source-file index from final source-backed code nodes. Each candidate must have:

- `file_type == "code"`
- a non-empty `source_file`
- a parseable one-based `source_location` beginning with `L<number>`
- a non-file node ID

Candidates are sorted by `(start_line, node_id)` for deterministic lookup. File nodes are indexed separately through the existing canonical file-node mapping.

### Resolution rule

For every `references` edge carrying `target_file`:

1. Canonicalize `target_file` with the same root/path logic used by other cross-file edges.
2. If `target_line` is absent, target the canonical file node.
3. If one or more non-file symbols start exactly at `target_line`, choose the most specific candidate deterministically. Specificity is based on node kind, preferring method/function/class/type-alias definitions over generic container nodes; ties use the stable node ID.
4. Otherwise choose the nearest preceding candidate in the same file.
5. If no preceding source-backed symbol exists, target the canonical file node.
6. Remove transient `target_file` and `target_line` stamps only after canonicalization, matching the current cleanup contract.

Nearest-preceding resolution is intentionally conservative. The current graph stores start lines reliably but not uniform end lines across all languages. A following symbol must never be selected for a line that appears before it.

### Failure behavior

- A missing target file does not create a ghost code symbol.
- An ambiguous path preserves the existing deterministic path handling and falls back to a file node only when a unique canonical target exists.
- Malformed edge metadata is ignored without aborting extraction.
- Direct calls to a single-file extractor still return a valid file-target edge; symbol refinement is a corpus-level feature.

---

## Component 3: Canonical Python Type Aliases

### Files

- `graphify/symbol_resolution.py`
- the Python extractor module that emits assignment/type-reference facts
- `tests/test_symbol_resolution.py`
- the focused Python extraction test module selected during implementation

### Definition discovery

Recognize source-backed module-level aliases from:

- `OrderFn = Callable[...]`
- `OrderFn: TypeAlias = Callable[...]`
- Python 3.12 `type OrderFn = ...` when the running parser exposes `ast.TypeAlias`

The alias node is a code node with its source file, source location, stable ID, label, and `node_kind: "type_alias"`. Only module-level definitions participate in file-wide import resolution.

### Import-guided canonicalization

Extend the existing `ImportedSymbol`-based flow with a symbol-reference resolution path that is independent of callable resolution:

1. Parse top-level `from module import OrderFn` and aliased forms.
2. Index source-backed type aliases by normalized `(module stem, exported name)`.
3. Resolve only when the import evidence maps to exactly one candidate.
4. Rewire annotation/reference edges from the imported stub to the canonical source-backed alias.
5. Remove the sourceless stub only when all of its incident evidence has been transferred and it is not shared by an unresolved external reference.

The callable resolver remains unchanged for function calls. Type aliases are not added to the callable label index merely to make this feature work.

### Safety constraints

- Plain `import module` member annotations are not resolved until receiver/module facts are retained by extraction.
- Star imports do not justify resolution.
- Function-local imports do not become file-wide evidence.
- Two matching source aliases remain unresolved and visible rather than being guessed.
- An external package exporting the same alias name never collapses onto a local alias without a uniquely matching local module path.

---

## Component 4: External Symbol Classification

### Files

- `graphify/analyze.py`
- a shared classification module if report code cannot safely import the analysis helper
- `tests/test_analyze.py`

Add a single node classifier used by both analysis and report generation. A node is `external` only when Graphify has affirmative evidence, including one of:

- `external: true`
- `node_kind == "external_symbol"`
- sanitized metadata with `scip_kind == "external"`
- a recognized external-reference/stub ID namespace emitted by an extractor
- an extractor-originated external import/reference marker on the node

Absence of `source_file` alone is not enough because semantic concepts also lack source paths. During graph normalization, provable external stubs should receive the common `external: true` and `node_kind: "external_symbol"` fields while retaining extractor-specific metadata.

This classification covers dependency/framework nodes such as `route`, `Flask`, `parametrize`, `given`, and `composite` when their extraction evidence identifies them as external. It does not maintain a hard-coded library-name denylist.

---

## Component 5: Actionable Gap and Thin-Community Reporting

### Files

- `graphify/analyze.py`
- `graphify/report.py`
- `tests/test_analyze.py`
- the focused report test module selected during implementation

### Categories

Every weakly connected node considered for gap reporting receives one category:

| Category | Meaning | Actionable gap? |
|---|---|---:|
| `actionable_local` | Source-backed local implementation or project documentation with insufficient graph connections | Yes |
| `external` | Dependency/framework/test-library symbol | No |
| `rationale` | Decision rationale retained for semantic queries | No |
| `metadata` | Known manifest/configuration key or structural serialization leaf | No |
| `structural` | File/page/heading or intentional extractor scaffolding | No |

The main “Knowledge Gaps” number and the generated isolated-node question use only `actionable_local`. The report also prints the suppressed-category counts so users can audit why the total changed.

### Thin communities

A thin community is no longer presented as one undifferentiated gap. For each low-cohesion community, the report records:

- total nodes
- actionable local nodes
- external nodes
- rationale nodes
- metadata/structural nodes

Communities with zero actionable local nodes are labeled benign and omitted from the top actionable-gap list, but remain in the community table. Communities with actionable nodes retain the current structural question and include representative local labels.

This closes the DebtGPS triage gap without hiding the approximately 150 isolated and 115 thin-community nodes that motivated the enhancement: each is retained and placed into an auditable category.

---

## Component 6: DebtGPS Rationale and Semantic Refresh

### DebtGPS code change

Add a concise rationale-bearing docstring to `server/routes_planning.py::refinance`. It must explain that the route validates request/ownership state and delegates financial calculations to the canonical refinance service; it must not duplicate calculation formulas or introduce runtime behavior.

The docstring completes route-level rationale coverage alongside the existing domain model, budget, planning-state, refinance-tool, and verification documentation.

### Semantic extraction

After the patched Graphify package passes its tests and is installed into the active local tool environment:

1. Re-run corpus detection and semantic-cache comparison.
2. Use the host-agent semantic backend because no Gemini/Google API key is configured.
3. Extract only the four uncached DebtGPS documents as one document chunk, following Graphify's extraction schema exactly.
4. Save the fresh semantic results in the normal content-hash cache.
5. Merge them with the 134 cached semantic files and the AST extraction results.
6. Build, cluster, analyze, and write the final graph/report/wiki outputs.

No image extraction is needed unless the re-check discovers a changed or uncached image. Any newly uncached images must be processed one per extraction task.

---

## Data Flow and Ordering

The full validation build uses this order:

```text
detect corpus and cache state
  -> AST extraction for code
  -> semantic extraction for uncached documents only
  -> merge all per-file fragments
  -> canonicalize file paths and imported symbols
  -> refine Markdown code-link targets by line
  -> normalize external-symbol metadata
  -> build graph and prune replaced/deleted source data
  -> cluster and score
  -> classify actionable and benign gaps
  -> write graph.json, analysis JSON, GRAPH_REPORT.md, and wiki
```

Line-aware Markdown resolution must happen after code node IDs are canonical and before transient edge stamps are removed. Gap classification must happen after external normalization and graph construction, because it depends on both node metadata and final degree.

---

## Testing Strategy

Implementation follows test-driven development: add one focused failing test, observe the intended failure, implement the smallest behavior, and then run the relevant regression group.

### Markdown links

- A Markdown link to `module.py` produces a `references` edge to the canonical file node.
- `module.py#L10` resolves to a symbol starting on line 10.
- A line inside a function resolves to the nearest preceding function/method/class definition.
- A line before the first symbol falls back to the file node.
- Invalid line anchors fall back to the file node.
- Document heading fragments retain document-page behavior.
- Images and external URLs remain absent from references.
- Cached and incremental extraction remap `target_file` and preserve `target_line` until final resolution.
- Full and incremental builds produce the same canonical target IDs.

### Type aliases

- Each supported alias syntax creates one source-backed `type_alias` node.
- Direct and `as` imports resolve annotation/reference edges to that node.
- Function-local, star, external, and ambiguous imports do not collapse.
- A duplicate sourceless `OrderFn` stub is removed only after safe rewiring.
- Callable resolution regressions remain green.

### Gap classification

- Explicit and SCIP external nodes are categorized as external.
- A sourceless semantic concept is not misclassified as external.
- Rationale, JSON noise, files/pages/headings, and external nodes do not increase actionable isolated counts.
- Actionable source-backed leaves still generate a question.
- Thin-community output exposes category totals and suppresses only all-benign communities from the actionable list.
- Report totals equal the sum of category counts.

### DebtGPS acceptance checks

- The refinance route contract test fails before and passes after the rationale docstring is added.
- All local links in `docs/debt-model.md` resolve.
- Every critical implementation node named by the DebtGPS documentation map gains at least one incoming document `references` edge; the current acceptance set contains nine nodes.
- `OrderFn` has exactly one source-backed canonical node and no unresolved local duplicate.
- The known framework/test symbols are retained but excluded from actionable gaps.
- Every previously isolated or thin-community node is either actionable or assigned a benign category.
- Existing focused DebtGPS verification suites remain green.
- The rebuilt report surfaces graph-health warnings, if any, rather than treating successful file generation as proof of graph health.

---

## Installation and Rollback

After the Graphify test suite passes, reinstall the active `graphify` tool from this local checkout using the same isolated `uv tool` environment currently providing the command. Verify the executable path and version/source before rebuilding DebtGPS.

Rollback is reinstalling the published `graphifyy` package into that isolated tool environment and rebuilding DebtGPS with the previously saved graph outputs. The source patch remains committed in this checkout, so it can be reviewed or submitted upstream independently of the installed tool state.

---

## Verification Gates

The work is complete only when all gates pass:

1. Focused Graphify tests for Markdown extraction, canonical IDs, incremental caching, Python symbol resolution, analysis, and reporting pass.
2. The broader Graphify test suite passes, or any unrelated pre-existing failures are identified with evidence.
3. The local Graphify build is installed and is the executable used for DebtGPS.
4. Semantic extraction processes only the cache misses discovered at execution time.
5. `graphify update .` or the full semantic build completes and refreshes DebtGPS graph artifacts.
6. The nine documentation targets, canonical `OrderFn`, external-node classification, isolated-node categories, and thin-community categories satisfy the acceptance checks above.
7. DebtGPS refinance and focused domain/planning/refinance/route verification tests pass.
8. The final handoff reports exact graph node/edge/community counts, semantic cache hits/misses, test results, remaining actionable gaps, and any graph-health warning.

---

## Expected Outcome

DebtGPS documentation becomes a first-class structural bridge into the implementation instead of a parallel semantic island. Local type aliases resolve to one canonical source definition. External framework/test symbols remain visible for queries but stop masquerading as missing work. The knowledge-gap report becomes an actionable backlog with an auditable benign remainder, and semantic extraction refreshes only the content that is actually uncached.
