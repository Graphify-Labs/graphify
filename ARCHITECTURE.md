# Architecture

graphify is a Claude Code skill backed by a Python library. The skill orchestrates the library; the library can be used standalone.

## Pipeline

```
detect()  →  extract()  →  build()  →  cluster()  →  analyze helpers  →  report.generate()  →  export.to_*()
```

Each stage lives in its own module and they communicate through plain Python dicts and NetworkX graphs. While designed to minimize shared state, some stages (like extractors) rely on ambient module-level state around the active scan root. Most stages are a single function; `analyze.py` and `export.py` are sets of sibling functions rather than one entry point.

## Module responsibilities

Signatures below are the real ones - `tests/test_architecture_doc.py` imports every symbol named here, so this table cannot drift from the code.

| Module | Entry point(s) | Input → Output |
|--------|----------------|----------------|
| `detect.py` | `detect(root)` | directory → scan summary dict: `files` grouped by category, plus `total_files`, `total_words`, `warning`, `scan_root`, … |
| `extract.py` | `extract(paths, *, root=None, ...)`, `collect_files(target)` | **list** of file paths → `{nodes, edges}` dict. `collect_files` expands a directory into that list, and lives here, not in `detect.py` |
| `build.py` | `build(extractions)`, `build_from_json(extraction)` | extraction dict(s) → `nx.Graph` |
| `cluster.py` | `cluster(G)` | graph → `{community_id: [node_id, ...]}` (the graph is not mutated) |
| `analyze.py` | `god_nodes(G)`, `surprising_connections(G)`, `suggest_questions(G, communities, community_labels)`, `find_import_cycles(G)`, `graph_diff(G_old, G_new)` | graph → one list/dict per analysis. There is no single `analyze()` entry point |
| `report.py` | `generate(G, communities, cohesion_scores, community_labels, ...)` | graph + analysis → GRAPH_REPORT.md string |
| `export.py` | `to_json`, `to_html`, `to_obsidian`, `to_svg`, `to_graphml`, `to_canvas`, `to_cypher` | graph → graph.json, graph.html, Obsidian vault, graph.svg, … one function per format |
| `wiki.py` | `to_wiki(G, communities, output_dir, ...)` | graph → one markdown article per community + `index.md` |
| `callflow_html.py` | `write_callflow_html(...)` | graphify-out files → Mermaid architecture/call-flow HTML |
| `ingest.py` | `ingest(url, target_dir, ...)` | URL → file saved to corpus dir |
| `cache.py` | `check_semantic_cache(files, root)`, `save_semantic_cache(nodes, edges, ...)` | files → cached nodes / edges / hyperedges + the list of files still needing extraction |
| `security.py` | `validate_url`, `safe_fetch`, `validate_graph_path`, `sanitize_label` | URL / path / label → validated value, or raises |
| `validate.py` | `validate_extraction(data)`, `assert_valid(data)` | extraction dict → **list of schema error strings** (`validate_extraction` returns them; `assert_valid` raises) |
| `serve.py` | `serve(graph_path)`, `serve_http(graph_path, *, host, port, ...)` | graph file path → MCP stdio server / HTTP server |
| `watch.py` | `watch(watch_path, debounce=3.0)`, `check_update(watch_path)` | directory → rebuild on change; `check_update` reports whether a re-extraction is pending |
| `benchmark.py` | `run_benchmark(graph_path)` | graph file → corpus vs subgraph token comparison |

Detection counts words from text and converted documents. Supported raster images,
audio and video stay in the discovered corpus, but their raw bytes are never decoded
for word counting; detection also bypasses any older cached counts for them. SVG
remains text-readable, and PDF/Office files retain their existing text converters.
This avoids reading and splitting entire binary media files just to size the corpus.

### Calling `extract()` from your own code

`extract()` takes a **list** of paths, and `root` is keyword-only and optional:

```python
from pathlib import Path
from graphify.extract import extract

paths = [Path("src/lib/content.ts"), Path("src/pages/index.astro")]
result = extract(paths, root=Path(".").resolve())   # pass root explicitly
```

Always pass `root`. Node ids and `source_file` values are derived relative to it; when it is omitted, `extract()` infers one from the paths you passed, which is the common parent of *that list* rather than your project root. A single-file call therefore anchors to that file's own directory, and ids can end up carrying path segments from the machine they were extracted on.

## Extraction output schema

Maven manifest ingestion parses XML namespace declarations before normalizing
tags in the root namespace for package and dependency lookups. Default and
prefixed declarations share the same package identity; foreign namespaces and
managed/plugin dependency scopes do not become project dependencies.

Terraform/HCL per-file AST results record the scope used to mint their node IDs.
After a cache hit, extraction consumes that scope to rewrite node IDs and edge
endpoints relative to the current scan root, including when the cache was copied
from another checkout. Module-source topology is still resolved against the
current permitted corpus. The scope marker is internal and is not exported in
the graph. AST cache schema 33 retires entries without this marker; the semantic
cache is unchanged. Existing graphs with stale absolute Terraform IDs need a full
code rebuild: `graphify extract . --code-only --force`.

Every extractor returns:

```json
{
  "nodes": [
    {"id": "unique_string", "label": "human name", "source_file": "path", "source_location": "L42"}
  ],
  "edges": [
    {"source": "id_a", "target": "id_b", "relation": "calls|imports|uses|...", "confidence": "EXTRACTED|INFERRED|AMBIGUOUS"}
  ]
}
```

`validate.py` enforces this schema before `build()` consumes it.

Validation reports list/object enum values as schema errors. Graph assembly
repairs structured `file_type` values to `concept` and structured `confidence`
values to `INFERRED`, without fabricating a confidence score, so malformed
semantic fields cannot abort an otherwise usable build.

JS/TS calls through default imports of directly default-exported object literals reuse existing static method nodes.
Members match the imported module path, exact label and source line. Lexically shadowed receivers, constructor calls,
spread, computed keys, accessors, duplicate keys and dynamic aliases are not inferred. These files bypass the per-file
AST cache, so resolving these cross-file calls does not require an AST cache schema bump.


## Semantic provenance during file-node folding

`build_from_json()` normally folds an evidence-free semantic mention of a
filename into its unique AST file-self node (Pass 2b, #3344); references to
that mention are rewired to the AST node. A cross-source semantic record that
contains its own `rationale`, source URL, author/contributor, capture time,
or metadata is **not** a disposable mention: a label-only fold would discard
its explanation or attribution. Such records remain separate even when their
label matches a unique AST file node. This is intentionally conservative:
a richly annotated mention may remain distinct until an explicit
provenance-preserving merge is available. The saved-semantic-node shrink guard
uses the same rule and still rejects any unexplained loss. Same-source AST/semantic twins that are evidence-free keep their
existing exact-path merge rule (#4389/#4391), but an independently evidenced
semantic YAML/document record is retained across a later AST extractor
upgrade. If AST disambiguation path-qualifies a file-node label, the shrink
guard accounts for a plain same-source fold using the exact source identity
instead of accepting a mere basename collision.

## Edge direction in graph.json

`graph.json` is written `"directed": false`, but every link is directed: **arc order is the direction** (`source` → `target`, #563). Older canonicalized files carry it in `_src`/`_tgt` markers instead, and those win where present (#2309).

A plain `json_graph.node_link_graph()` load loses this: an undirected graph re-orders each edge's endpoints by node-list position. Load through `paths.load_node_link_graph()` (or apply `paths.restore_arc_direction()` to the raw dict first), which stamps `_src`/`_tgt` on every edge. Then read direction as `data.get("_src", u)` / `data.get("_tgt", v)`, never from `u, v`. Anything that writes graph.json back out pops the markers into arc order first, as `export.to_json()` does.

## Confidence labels

| Label | Meaning |
|-------|---------|
| `EXTRACTED` | Relationship is explicitly stated in the source (e.g., an import statement, a direct call) |
| `INFERRED` | Relationship is a reasonable deduction (e.g., call-graph second pass, co-occurrence in context) |
| `AMBIGUOUS` | Relationship is uncertain; flagged for human review in GRAPH_REPORT.md |

Go member calls, including same-file calls, resolve through declared receiver types and
carry `INFERRED` confidence. Bare calls to package-level functions remain `EXTRACTED`;
unknown or ambiguous receivers do not bind by method name alone. AST cache schema 37
retires Go entries created before these receiver-binding rules.

C++ member chains such as `client.actions->Execute()` use lexical local/parameter
bindings and class-scoped field declarations, including fields in unchanged headers.
Raw pointers and single-type-argument `std::unique_ptr<T>` / `std::shared_ptr<T>`
receivers are supported; `.` does not unwrap a smart pointer. Resolved instance
calls are `INFERRED` static-type relationships, not proof of runtime dispatch.
Unknown/shadowed types, ambiguous class identities, unresolved aliases, custom
pointer wrappers, containers, and computed receivers are not guessed. AST cache
schema 41 retires entries without receiver chains and persistent class fields.

C++ receiver types also follow ordinary `using` and `typedef` aliases, including
raw-pointer and supported smart-pointer aliases. Lookup preserves spelling,
lexical block/namespace/class scope and declaration order, and only traverses
explicit includes preceding the receiver declaration. Alias targets resolve in
their declaring scope; unsupported aliases still hide outer declarations.
Qualified-name prefixes also block outer lookup. Namespace aliases and later
class-scoped declarations in complete-class contexts remain unresolved.
Anonymous namespaces retain their enclosing named lexical scope through an
internal lookup placeholder. This placeholder never becomes a class identity;
anonymous-local types and unknown aliases still block outer lookup.
Direct namespace directives and qualified using declarations participate in this
lookup. Alias templates, dependent targets, transitive using directives, arbitrary
template types and cyclic or ambiguous aliases remain unresolved. Alias expansion
stops after 32 steps. Conditional aliases remain unknown shadowing declarations,
except inside a whole-file `#ifndef`/`#define` header guard without alternatives or
an `#undef`. File nodes persist
lexical type/alias facts and include offsets; class nodes persist field declaration
offsets, so unchanged headers support incremental receiver resolution.
C++ parsing normalizes CRLF to LF before collecting lookup facts and call sites,
keeping their byte coordinates consistent across line endings without editing
source files. Mixed LF/CRLF files use the same coordinates.
Field spellings and aliases resolve where declared; an exact forward-declared
type may then be completed by a unique definition visible at the member call.
Definition facts preserve same-file declaration order. Missing, unincluded or
ambiguous definitions remain unresolved, and base types still require completeness
at their declaring class rather than at a later call.
Includes nested in namespace, class or function scopes do not supply global type
visibility; their injected declarations are not modeled. Header guards and global
linkage wrappers preserve ordinary include visibility.

C++ inherited receiver fields and methods follow literal, explicitly reachable
base types. A class declaration hides the same name in every base, including
unknown fields, aliases, nested types and enum constants. Multiple inheritance
resolves only one unambiguous member path; diamonds, unknown/dependent bases,
virtual-base paths, inherited overload families and walks exceeding 32 classes
stay unresolved. Calls retain their declared static receiver target, without
inferring runtime virtual dispatch. AST cache schema 51 retires entries without
the lexical type and inheritance facts or with pre-normalization byte offsets.
This pass covers explicit receiver calls and field chains; unqualified bare calls
retain the existing lexical resolver. Smart-pointer recognition requires an
unshadowed `std` prefix (or explicit `::std`); custom wrappers remain unresolved.
Rebuild existing graphs with `graphify extract . --code-only --force` to populate
unchanged headers before relying on changed-file-only updates.

C++ plain class/struct forwards fold into a unique exactly qualified definition
only when one declaration file reaches the other through unconditional, exactly
resolved quoted includes in the scanned corpus. The definition keeps its ID and
source site; `metadata.cpp_declaration_sites` retains every folded forward site.
`_cpp_reconcile_files` records the source and include-proof files so CLI/watch
updates re-extract the live group after an edit, deletion, or exclusion. New pairs
refresh exact-identity candidates from the permitted unchanged corpus before
the same proof checks run. A whole-file `#ifndef NAME` / `#define NAME` guard is
recognized structurally; feature expressions are never evaluated. Unrelated
same-name files, multiple definitions, templates/specializations, nested/local or
anonymous scopes, and other conditional declarations/includes stay separate.
A common third file including both declarations
does not establish equivalence in this pass.
Non-template members with empty parameter lists also fold a unique declaration/body pair
under one proven owner when literal return type, return pointer/reference shape,
cv/ref qualifiers and noexcept spelling match, backed by the same exact include
proof. The declaration keeps its ID and source site, and the body site remains
in `definition_file` / `definition_location`; body calls are rewired to that ID.
Persisted `_cpp_member_records` retain unsupported or multiple syntax records so
overload families, normalized-name collisions, multiple bodies, conditional
members, pure/defaulted/deleted methods and uncertain signatures do not fold.
Parameter-bearing methods, equivalent type aliases/spellings, templates and
general overload resolution remain outside this repair.
AST cache schema 43 retires records without class/member facts and exact include proofs;
rebuild existing graphs with `graphify extract . --code-only --force`.

C++ template wrappers preserve member ownership, including reference-returning
declarations and matching same-file qualified definitions. Explicit calls such
as `worker.Tick<int>()` resolve through the existing declared-receiver rules;
dependent, unknown and ambiguous receivers do not acquire guessed targets.
This includes dependent `typename` locals/fields and template-template parameters;
an inner template's own parameter names do not shadow the surrounding corpus.
These are method-family nodes, not overload/specialization resolution. Same-file
primary owners such as `template<class T> void Box<T>::Run()` reuse a declared
member only with unique owner/member declarations, plain ordered type parameters,
and matching parameterless primitive-returning signatures (including cv/ref and
bare noexcept qualifiers). Specializations, overloads, dependent signatures,
constrained/defaulted/variadic templates, nested or shadowed owners, and cross-file
template declaration/definition merging remain outside this bounded normalization.

When conditional directives break an initializer or argument list, C++ extraction
can recover separate, byte-preserving branch views. It does not evaluate defines,
read includes, invoke a preprocessor or enumerate configuration combinations.
Recovery is bounded to 128 conditional groups and 32 branch views; malformed,
still-invalid, conflicting, unattributable or over-budget inputs retain their original parse
errors. File-node `metadata.cpp_conditional_recovery` records original errors,
branch ranges and coverage; guarded records carry `metadata.cpp_conditions`.
The file range map also applies to later resolver-created edges and parked C++
calls; cross-repository linking carries the representative callsite's guards to
its inferred edge while retaining the existing callee/receiver deduplication.
This is static branch-wise syntax coverage, not proof that all branches execute together.
AST cache schema 43 invalidates older template and conditional recovery records.

## Adding a new language extractor

1. Add an `extract_<lang>(path: Path) -> dict` function following the existing pattern (tree-sitter parse → walk nodes → collect `nodes` and `edges` → call-graph second pass for INFERRED `calls` edges). New languages go in their own module under `graphify/extractors/` - see `graphify/extractors/MIGRATION.md`; `extract.py` re-exports them while the existing ones are ported out of it.
2. Register the file suffix in `extract()`'s dispatch table and in `collect_files()` (both in `extract.py`).
3. Add the suffix to `CODE_EXTENSIONS` in `detect.py` and `_WATCHED_EXTENSIONS` in `watch.py`.
4. Add the tree-sitter package to `pyproject.toml` dependencies.
5. Add a fixture file to `tests/fixtures/` and tests to `tests/test_languages.py`.

## Search hook scope

The search hook omits project hints when a structured Grep path or every literal
target of a simple grep/rg command resolves outside the project. Mixed targets,
implicit paths, shell composition/expansion, wrappers, unknown options and
unmapped Windows shell drive paths retain the advisory hint. It does not execute
shell input or change search permissions.

## Security

All external input passes through `graphify/security.py` before use:

- URLs → `validate_url()` (http/https only) + `_NoFileRedirectHandler` (blocks file:// redirects)
- Fetched content → `safe_fetch()` / `safe_fetch_text()` (size cap, timeout)
- Graph file paths → `validate_graph_path()` (must resolve inside `graphify-out/`)
- Node labels → `sanitize_label()` (strips control chars, caps 256 chars)

See `SECURITY.md` for the full threat model.

## Testing

`analyze.suggest_questions()` interleaves candidates across question types before
applying its result limit (seven by default). This keeps ambiguous relationships
from hiding bridge, inferred-relationship, isolation, and low-cohesion signals.
The existing candidate order within each type is preserved; if the limit is smaller
than the number of available types, their generation order determines priority.

One test file per module under `tests/`. Run with:

```bash
pytest tests/ -q
```

The test suite is designed to avoid network access and uncontrolled filesystem effects; most tests are isolated with temporary directories and environment fixtures.

Python nested class ids include their enclosing class id. Same-named nested
classes under different parents retain separate definitions, methods, and
containment edges; top-level class ids are unchanged. AST cache schema 7 prevents
older cached definitions from retaining the collapsed identities.

Python injected fields retain an unchanged parameter/local's declared class
through `self.field = value`. A local assigned a member-call result can use the
resolved method's single scalar return-type reference. The link uses the exact
producer call's byte span, not a same-line argument or a bare method name.
Unknown types, conflicting assignments, shadowed names, container returns, and
ambiguous return references emit no inferred call. Resulting call edges remain
`INFERRED`. Changed-caller rebuilds carry unchanged methods' return-type references
as resolver context. Changes to a producer's return annotation require a full
rebuild to recompute unchanged callers' inferred relationships.

Python direct module-level constructor assignments (`g = Service()`) retain the
class for member-call resolution inside functions, including an imported alias
or a lowercase class rebound to its instance. The constructor must be declared
or imported before the assignment and resolve to a unique visible class by exact
spelling. Local shadowing, other module bindings, conditional assignments and
dynamic namespace mutation leave these calls unresolved. Qualified constructors
and decorated classes are not inferred by this pass. Edges remain `INFERRED`;
AST cache schema 37 retires Python entries without the instance marker.

C# partial types merge across files by their path inside the namespace,
enclosing types first and each with its arity (`` Outer`1.Inner ``), within one
assembly. Nested halves merge only under the same enclosing chain, and `Foo` and
`Foo<T>` stay separate types. AST cache schema 9 retires cached C# results that
lack this path. The merge runs after colliding ids are salted apart by path, so
a half whose file stem collides with another file's (`Spec.cs` and `_Spec.cs`,
`Cfg/Helpers.cs` and `Cfg_Helpers.cs`) still merges and keeps its members.

C# constructors (instance, static and a type's primary constructor) are nodes
owned by their type through a `method` edge, labeled `.TypeName()` with
metadata `kind: "constructor"`. The id is the one a method named after the type
would get, `_make_id(type_id, TypeName)`; each further signature is salted like
a method overload, a static constructor is its own `static` signature, and when
a member spelled like the type in another case (`foo()` in `Foo`) already owns
that id, the constructor takes a salted one, so no existing id moves. Calls in
a constructor's body and `: base(...)`/`: this(...)` arguments are its calls.
`new X(...)` keeps its edge to the type and also links the constructor whose
parameter count fits, as do `: base(...)`/`: this(...)`; two fitting overloads,
an unresolved base or an unbound type give no constructor edge. Constructors
stay out of every name-keyed call index. AST cache schema 40 retires C# entries
without them.

C# property and indexer accessor bodies (and expression bodies) are walked
with the member as the caller, and the member counts as owned by its type for
unqualified, `this.`/`base.` and partial-type lookups, like a method. It is never
a call target by name. An indexer is a `this[]` node (`defines`, context
`field`) with id `_make_id(type_id, "this")`, salted per signature and away
from a member spelled `This`. A user-defined operator or conversion is a
`.operator +()` / `.operator int()` node owned through `method`, with id
`_make_id(type_id, "operator", sha1(signature)[:6])`, since several conversions
share one parameter list. Existing ids do not move. AST cache schema 40.

R extraction preserves symbol-only bindings such as `%||%` as separate nodes.
When normal ID normalization removes an entire binding name, its UTF-8 bytes
provide a deterministic operator suffix within the same lexical owner. Its double
underscore separators cannot collide with an ordinary normalized binding ID. Local
call resolution stops if malformed scope metadata cycles.

### Same-ID AST / semantic provenance during extractor upgrades (#4896)

A newly supported AST extractor can mint an ID that is already owned by an
independently evidenced semantic node in a saved graph, even when the two nodes
refer to the same file. Watch reconciliation retains the saved semantic ID and
its rationale/attribution, assigns the fresh AST record a deterministic
ID-derived AST suffix, and rewrites only fresh AST edge/hyperedge
references. This applies to full and incremental re-extractions; incrementally
rebuilt sources are not positive evidence of semantic deletion. The shrink
guard refuses same-ID losses of semantic provenance even when the total node
count grows, preventing the ordinary missing-ID guard from being bypassed.
If multiple new AST records already share that ID, all use one deterministic
AST successor ID: this retains their preexisting AST coalescing behavior while
ensuring they cannot overwrite independent semantic provenance.
