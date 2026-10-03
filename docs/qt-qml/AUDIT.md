# Qt and QML support: upstream audit

Audited on 2026-10-03. The objective is to extend Graphify's source analysis of Qt and QML projects and contribute the changes upstream. The implementation remains a Python Graphify extension.

The initial support profile is Qt 6 with both CMake and qmake projects. Qt 5.15 compatibility is a separate future profile that needs its own fixtures and acceptance gates.

The required analysis includes Qt C++ signals, slots, signal emission and connection semantics, plus bidirectional C++/QML interaction. C++ access to QML-created objects and their properties, methods and signals is part of the scope alongside QML access to exposed C++ objects. These additions are tracked as `REQ-QML-016` and `REQ-QML-017` in [REQUIREMENTS.md](../REQUIREMENTS.md).

## Baseline and evidence

| Item | Audited baseline |
| --- | --- |
| Upstream | [Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) |
| Upstream development branch | `v8`, also the imported remote default branch |
| Commit | [`0b60d47e6cd9338c51143f39f35b6c45c8453385`](https://github.com/Graphify-Labs/graphify/commit/0b60d47e6cd9338c51143f39f35b6c45c8453385) |
| Commit subject | `docs(readme): add VS Code one-click and Smithery MCP install` |
| Commit timestamp | `2026-10-02T23:12:01+01:00` |
| Python distribution | `graphifyy`, version `0.9.74`; `pyproject.toml:6-7` |
| Supported Python floor | `>=3.10`; `pyproject.toml:13` |

Line references below refer to this immutable baseline unless explicitly marked as PR-head evidence. They describe source inspection, not successful execution. At the start of the audit, no `graphify-out/wiki/index.md` or generated graph report was available; source inspection followed the root `AGENTS.md` and upstream `CONTRIBUTING.md` guidance. This audit performed source and public API inspection; setup and runtime verification are recorded separately in [VALIDATION.md](VALIDATION.md).

The key finding is that upstream already analyzes ordinary C++ and JavaScript, but it has no dedicated QML or Qt meta-object semantics. A `.qml` file is currently omitted from directory detection and collection. Generic C++ support must not be presented as complete Qt support.

## Existing upstream proposal: review before implementation

GitHub API inspection on 2026-10-03 found an existing feature request, [issue #1716](https://github.com/Graphify-Labs/graphify/issues/1716), and an existing implementation, [PR #1748](https://github.com/Graphify-Labs/graphify/pull/1748). The PR is a reuse candidate and an upstream coordination reference. These changes have not been merged into the audited `v8` baseline.

| PR metadata | Observed value |
| --- | --- |
| State | Open, not draft, not merged |
| Title | `feat(extract): add QML support and Qt C++/QML bridge (#1716)` |
| Base branch | `v8` |
| Head commit | `7b38d4c2e2226b1db826a26774c7a5f299b8d62f` |
| Merge base with audited `v8` | `edec9eabeceeae6aa2375eddb3835efa1a32c0a3` |
| Last API-reported update | `2026-07-20T07:04:16Z` |
| Feature diff | 11 files; 1,684 additions and 10 deletions |
| Submitted tests | 17 QML tests and 9 C++/QML bridge tests |
| Checks/reviews visible at inspection | Check-runs endpoint returned zero runs for the head; reviews endpoint returned no reviews. This is not a passing CI result. |

The feature diff adds `graphify/extractors/qml.py`, QML scan/dispatch/registry wiring, C++ Qt section and property handling, an alias bridge, the parser extra, a fixture and tests. It does not modify watch, cache, metadata ingestion, query/export consumers or CI workflows. The tests and reported smoke test are the contributor's evidence; this project has not executed that PR.

The current [PR-head manifest](https://github.com/Hamza-Masuadi/graphify/blob/7b38d4c2e2226b1db826a26774c7a5f299b8d62f/pyproject.toml) uses `tree-sitter-qmljs>=0.3.1` in `qml`, `all` and the development dependencies. The older PR description's claim that the parser is unavailable on PyPI is stale. A later [dependency update comment](https://github.com/Graphify-Labs/graphify/pull/1748#issuecomment-4946168692) and current [PyPI metadata](https://pypi.org/project/tree-sitter-qmljs/0.3.1/) show version 0.3.1, an MIT license and Python `>=3.8`; the release currently contains one source distribution and no wheels. Windows installation therefore still needs a tested compilation path or an approved packaging alternative.

Source inspection identifies the following adaptation work. These findings are static review conclusions and reproduction targets, not a runtime certification of the PR:

| Risk / gap at PR head | Exact evidence | Required gate before reuse |
| --- | --- | --- |
| Standard named-element syntax is missed | PR `engine.py:1396` matches only a quoted `QML_NAMED_ELEMENT("Alias")`; Qt documents identifier syntax such as `QML_NAMED_ELEMENT(EventDatabase)` in [the macro reference](https://doc.qt.io/qt-6/qqmlintegration-h.html#QML_NAMED_ELEMENT). The submitted alias test mirrors the quoted form. | Regression using valid Qt macro syntax, including foreign/namespace cases and no false matches in comments or strings. |
| Whole-file name tables lose component scopes | PR `qml.py:133-135`, `:250-251`, `:361-379`, `:462-510` uses flat `id_table` and `func_table`. Receiver validation prevents some incorrect member calls but bare calls/references still use the global table. | Repeated IDs/methods in inline components and shadowed JavaScript scopes resolve only inside their valid context. |
| Module information is discarded | PR `qml.py:90-105`, `:174-185`, `:410-425` strips qualified type names to their last segment and does not index import aliases or versions. | URI/version/alias-scoped resolution, duplicate local names and imported directory isolation. |
| Builtin-name suppression hides legitimate local candidates | PR `qml.py:37-78`, `:174-185` suppresses a fixed name list before module lookup. | Locally defined `Button.qml` or an aliased type named like a Qt builtin remains resolvable when the imports authorize it. |
| Partial parses have no QML warning metadata | PR `qml.py:108-123`, `:526` reads `root_node` but never checks `root.has_error` or returns `parse_errors`. | Malformed QML produces actionable bounded diagnostics and preserves persistence guards. |
| Registration bridge relies on global labels | PR `extract.py:2813-2893`; aliases lack a module URI/version in the resolution key. Same-name matching also uses generic stub rewiring. | Prove explicit registration/import compatibility; an unrelated same-name C++ class must not become a QML type. |
| Alias bridge activation misses QML-only batches | PR `extract.py:2933-2940` registers only C/C++ suffixes. | A QML-only incremental change still resolves against unchanged registered C++ types; C++-only changes evict stale QML edges. |
| Declaration tags do not model emissions, connections or reverse access | PR `engine.py:1375-1376`, `:1502-1583` tags signal/slot sections and property accessors. Inspection found no dedicated emission/`QObject::connect` or QML-object-access pass in the PR's `graphify/` source. | Verify signal emission, connection endpoints/mode and C++ access to source-resolved QML objects, rather than treating declaration tags or ordinary calls as the complete relationship. |
| Consumer defaults omit instantiation dependencies | PR `qml.py:256` emits `instantiates`; audited `graphify/affected.py:12-32` does not include it in default traversal. The PR does not modify that consumer. | Queries and affected traversal expose component-instantiation dependencies with original direction and evidence. |
| Macro preprocessing is not lexically scoped | PR `extract.py:1640-1651` globally inserts semicolons after `Q_OBJECT`/`Q_GADGET`, including matching bytes in comments/literals. | Preserve original text/spans and never modify a literal/comment as if it were a declaration. |
| Old C++ extraction edits overlap newer invariants | PR `extract.py:1643` replaces the old generic `extract_cpp()` body; audited upstream `extract.py:2895-2912` now includes C++/CLI normalization and test-macro recovery. PR engine edits also overlap newer C++ method-declaration handling. | Adapt small hunks onto the current baseline and retain all C++ regression coverage; do not replace current functions with older PR versions. |

The first implementation increment should decide which code and fixtures from PR #1748 to reuse and how to preserve attribution and license notices. Rebase/review that contribution against the current baseline, resolve the packaging and correctness gaps, then extend it through the scoped roadmap. Do not open a duplicate Qt/QML issue or assume a clean merge implies correctness.

## Existing support and extension points

| Area | Existing behavior and evidence | Implication |
| --- | --- | --- |
| Pipeline | `ARCHITECTURE.md`; `detect -> extract -> build -> cluster -> report/export` | Extend this pipeline; retain existing CLI and output contracts. |
| Corpus classification | `graphify/detect.py:47`, `:517-551` recognizes code suffixes, named package manifests and extensionless shebang scripts | `.qml`, `.qmltypes`, `.qrc`, `qmldir` and Qt build files need deliberate classification rules. |
| Corpus containment | `graphify/detect.py:1824`; `graphify/extract.py:8871-8930` uses shared ignore rules, noise-directory filtering and resolved-root checks | New metadata walkers must reuse these boundaries, including ignored files and symlinks. |
| Extractor dispatch | `graphify/extract.py:6709`, `:6959-7002`; `graphify/extractors/__init__.py:1-6` | `_DISPATCH` and `_get_extractor` are authoritative. `LANGUAGE_EXTRACTORS` is a registry seed, not the live dispatch mechanism. |
| Per-language modules | `graphify/extractors/base.py:1`; `graphify/extractors/MIGRATION.md`; `tests/test_extractors_registry.py` | Use a focused new module with a facade re-export and registry identity checks; preserve the dependency direction `extract -> extractors`. |
| Generic C++ | `graphify/extract.py:1355-1372`, `:2895-2912`; `graphify/extractors/engine.py:3070-3097` | Classes, structs, enums, functions, calls, quoted includes and enum members already have extraction paths. Extend Qt semantics around those results. |
| C++ headers | `graphify/extract.py:6924-6927`, `:6944-6986` sniffs `.h` for C++ markers after Objective-C detection | Normal QObject subclasses can reach the C++ parser, but Qt macros have no dedicated handling. Preserve C/Objective-C routing. |
| C++ include resolution | `graphify/extract.py:993-1029`; `graphify/extractors/resolution.py:860-871` | Quoted includes resolve relative to the including file. System headers and arbitrary compiler include-search paths do not become complete project metadata. |
| Header/implementation merge | `graphify/extractors/resolution.py:2918-2968`; `tests/test_cpp_objc_cross_file_calls.py`, `tests/test_cpp_method_declarations.py` | Existing declaration/definition identity is useful for Qt bridge targets. Test macros and overloaded methods separately. |
| C++ member calls | `graphify/extract.py:4207-4232`; `cpp_type_table` and per-file raw-call metadata | Explicit scope and `this` evidence can resolve; locally typed receivers are inferred. Ambiguous types are skipped. |
| JavaScript | `.js`/`.mjs`/`.cjs` dispatch and JS/TS symbol-resolution paths in `graphify/extract.py:2034`, `graphify/extractors/resolution.py:2043` | Reusable parsing infrastructure exists. QML imports, `.pragma library`, instance scopes and declarative bindings need their own semantics. |
| Mixed declarative formats | Vue extraction `graphify/extract.py:2548`; XAML extraction `:6450`; XAML corpus context `:7005` | Existing precedents support member nodes, embedded script and framework bridges. They are patterns, not QML implementations. |
| Resolver extension seam | `graphify/resolver_registry.py:29-85`; invocations in `graphify/extract.py:8277`, `:8658-8662` | Add scoped resolution passes after ID remapping and merged indexes. Account for resolver ordering and incremental activation. |
| Provenance and confidence | `graphify/validate.py:4-7`, `:10-86` | Keep `file_type="code"`, source-backed IDs, `source_file`, source locations and `EXTRACTED`/`INFERRED`/`AMBIGUOUS` confidence. Relations are not restricted to an enum by this validator. |
| Searchable attributes | `graphify/serve.py:330-354` flattens only the node `attributes` dictionary for search | A future `metadata.qml`/`metadata.qt` bucket is not automatically indexed. Discoverability requires consumer integration or a deliberate searchable projection. |
| AST cache | `graphify/cache.py:39`, `:429-494`, `:933-998`, `:1071-1118` | Cache keys use source content and the relative path; namespace uses installed distribution version plus cache schema. Relative paths and metadata round trips matter. |
| AST-only updates | `graphify/watch.py:1415-1446` rebuilds code without LLM calls | Preserve offline deterministic extraction and integrate Qt dependency invalidation with this path. |
| Incremental context | `graphify/watch.py:1716-1818`; `graphify/extract.py:8658-8662` | Unchanged graph nodes can be indexed as resolver context; a new Qt/QML resolver still needs the facts required to reconstruct relationships. |
| Persistence integrity | `graphify/export.py:272`; `graphify/watch.py:1221`; `graphify/build.py:1926-1953` | Retain partial/zero-node/shrink guards, portable sources, explicit ownership and directedness across updates. |
| Watch recognition | `graphify/watch.py:318`, `:2348-2387`, `:2437-2438` | Watched suffixes derive from code/document sets. Extensionless metadata is currently rejected by the event handler. |

## Prioritized gaps

Priorities indicate development order. These are functional and integration gaps, not claims of exploitable security defects.

### A01 — P0: QML cannot enter the deterministic pipeline

`.qml` is absent from `CODE_EXTENSIONS`, `_DISPATCH` and the language registry. `classify_file()` returns `None` for unknown suffixes (`graphify/detect.py:517-551`); directory `collect_files()` admits only dispatch suffixes (`graphify/extract.py:8876`, `:8904-8909`). There is no QML parser dependency in `pyproject.toml:14-47`.

Adding a suffix alone is insufficient. Select and validate a parser, implement the extractor, register all entry points, provide actionable unavailable-parser diagnostics, and ensure that malformed QML cannot silently produce a cached empty or misleadingly complete graph. The first acceptance fixture must show QML entering both scan and extraction paths.

### A02 — P0: Graph identity needs QML component and instance scopes

`normalize_id()` casefolds and normalizes names (`graphify/ids.py:50-93`); `_file_stem()` strips the extension (`graphify/extractors/base.py:58-82`). Generic type-like classification is based largely on labels (`graphify/extractors/resolution.py:1118-1128`). Repeated `onClicked`, `width`, `id` values and nested object declarations need identities that cannot collapse into unrelated members.

Define identity before feature extraction: repository-relative source, component scope, object/inline-component scope, member kind and original case-sensitive name, with deterministic collision salts compatible with the existing ID contract. Test `Button.qml` and `Button.cpp`, different directories containing `Main.qml`, inline components, repeated anonymous objects and names that normalize identically. Labels alone must never establish a bridge to an unrelated C++ or JavaScript symbol.

### A03 — P1: Imports, component visibility and named metadata are missing

No parser or resolver for `qmldir`, `.qmltypes`, QML URI/version/alias imports, local component directories or resource URLs was found in `graphify/` or tests. No dedicated CMake/qmake/Qt resource integration was found. Directory collection and watch handling are suffix-based, so an extensionless `qmldir` needs recognition beyond `_get_extractor()`.

Introduce one consistent source-recognition rule used by detection, collection, update and watch. Build a corpus-scoped module/type index with source-backed candidates, explicit aliases and recorded ambiguity. Keep missing Qt SDK types as declared external references or unresolved facts; do not guess a local type by name. Treat `.qmltypes` metadata as input data with its own provenance and precedence, not as proof that an unavailable runtime object exists.

### A04 — P1: Declarative relationships and script semantics are missing

No QML extraction exists for properties, aliases, signals, methods, handlers, bindings, `Connections`, inline components, singletons or JavaScript embedded inside QML. Parsing the whole file as JavaScript would lose QML's declarative structure; parsing script spans without scope and byte-position mapping can misattribute calls and lines.

Add source spans and component/object scope first. Distinguish reads, writes, binding dependencies, handler bodies and explicit signal connections. Keep runtime-selected targets unresolved when static evidence is insufficient. Reuse the JavaScript parser only for well-delimited script regions with the enclosing QML context and original source locations. Cover ordinary helper scripts and QML-specific script directives as separate cases.

### A05 — P1: Qt C++ semantics and bidirectional QML bridges are missing

`extract_cpp()` only performs C++/CLI normalization and test-macro augmentation (`graphify/extract.py:2895-2912`). No dedicated `Q_OBJECT`, `Q_GADGET`, `Q_PROPERTY`, `Q_SIGNAL`/`signals`, `Q_SLOT`/`slots`, `Q_INVOKABLE`, `Q_ENUM`, `QML_ELEMENT`, QML registration, context-property or `QObject::connect` pass was found.

Generic C++ parse recovery can retain some surrounding declarations, but that does not provide a Qt property model, registration identity or signal/slot endpoint resolution. Build a bounded source overlay that consumes current C++ nodes and records Qt declarations and registration facts with exact provenance. Initially resolve only explicitly evidenced registrations, properties and callable members; macros, overloaded signatures, private visibility and dynamic context objects need negative tests.

For `REQ-QML-016`, ordinary C++ call extraction may retain a signal-method call or a `connect()` invocation. Inspection found no Qt-specific pass that identifies an emission site, sender object, signal signature, receiving object, slot/lambda target and connection mode as one relationship. The existing PR's signal/slot declaration tags do not fill this gap. Add source-backed handling for `emit`/`Q_EMIT`, pointer-to-member and literal `SIGNAL`/`SLOT` connection forms, explicit overload selection and context-bound lambdas. Retain `Qt::AutoConnection` and explicitly selected modes without claiming runtime delivery order or thread affinity from a static call. Qt distinguishes signal emission, direct slot calls and connection-dependent delivery in its [signals and slots documentation](https://doc.qt.io/qt-6/signalsandslots.html).

For `REQ-QML-017`, no dedicated pass was found for C++ obtaining QML-created objects through literal `load`/`loadFromModule`, `QQmlComponent::create`, `rootObjects()`/`rootObject()`, or literal `objectName`/`findChild` selection, then accessing their APIs through `property`/`setProperty`, `QQmlProperty`, `QMetaObject::invokeMethod`, or signal connections. Generic extraction can retain ordinary calls to these APIs; it does not identify the source QML component or member behind them. Trace an explicitly evidenced loaded component and object handle to declared QML properties, methods and signals, retaining the C++ access site and direction. Distinguish a QML `id` from an `objectName`; duplicate names, computed member names, unresolved object creation and dynamic descendants must not produce guessed targets. These APIs and their distinct property-write behavior are described in [Qt's C++ interaction guide](https://doc.qt.io/qt-6/qtqml-cppintegration-interactqmlfromcpp.html); version-specific loader APIs need an explicit minimum-version gate from the [engine reference](https://doc.qt.io/qt-6/qqmlapplicationengine.html).

The design must also recognize source-backed exposure patterns in existing applications: a literal `setContextProperty("backend", object)` with an established object type and engine/context scope; `setContextObject(object)` where that context and the object's exposed members are source-resolved; and literal initial-property maps passed to a known QML component through `setInitialProperties` or `createWithInitialProperties`. These are bounded evidence-based cases, not permission to infer a global object from any matching name. Computed names, unresolved context ownership and unknown map contents remain explicit unresolved facts. Consult [context property integration](https://doc.qt.io/qt-6/qtqml-cppintegration-contextproperties.html) and the [component API](https://doc.qt.io/qt-6/qqmlcomponent.html) when defining those acceptance fixtures.

Cross-language guards are an additional integration constraint. `graphify/build.py:1383-1402` drops inferred `calls` when language families differ, including an unknown `.qml` family versus C++. It also rejects certain `imports`/`references` when both families are known and differ. Any narrowly evidenced bridge allowance must preserve the existing anti-phantom-call regressions. Assigning all QML to the native language family would hide this distinction.

### A06 — P1: Metadata-dependent incremental correctness needs design

The current AST cache is per file; it does not provide a Qt module dependency graph (`graphify/cache.py:429-494`, `:933-957`). Resolver activation uses suffixes in the supplied input paths (`graphify/resolver_registry.py:78-80`). Partial rebuilds preserve unchanged graph records (`graphify/watch.py:1431-1435`) and add bounded unchanged context to resolution (`:1716-1818`).

Changing only `qmldir`, `.qmltypes`, a C++ registration, a resource alias or an import root can change relationships in unchanged QML. Design dependency ownership, fact persistence, affected-source re-resolution and stale-edge eviction explicitly. Compare incremental output against a clean full rebuild for every metadata-only change, deletion, rename, ambiguity introduction and ignore-rule change. Development changes at the same package version must deliberately invalidate the relevant AST cache; distribution version namespacing alone does not invalidate each local code edit.

### A07 — P1: Multiple relationships between the same endpoints can be lost

`build_from_json()` creates `nx.Graph` or `nx.DiGraph` (`graphify/build.py:1031`), and later applies relation precedence before `add_edge()` (`:1413-1468`). One endpoint pair can retain only one edge in either simple-graph mode. `graphify/multigraph_compat.py:1-10` is a future-mode capability probe; it does not enable multigraph assembly.

A component can read, bind, write and connect to the same target. Use explicit member/binding/handler nodes and retained structured facts within existing compatibility constraints, then test extraction-to-build-to-export preservation. Do not claim lossless Qt relationship coverage merely because extraction emitted every edge. An upstream multigraph project should remain a separate compatibility decision.

### A08 — P2: Consumers do not automatically understand new relations

The validator permits new relation strings, but affected traversal uses a fixed default relation list (`graphify/affected.py:12-32`), call-flow selection prefers a fixed set (`graphify/callflow_html.py:566-579`), and its call table filters another set (`:1250`). Direction is persisted using `_src`/`_tgt` in simple graphs (`graphify/build.py:1413-1429`).

Prefer established relations plus precise Qt context where semantics match. If new relations are necessary, update query, affected traversal, call-flow, report/wiki and relevant exporters with consumer-level regression tests. Verify both direction and confidence; a new edge that serializes successfully can still be absent from default user-facing answers.

### A09 — P2: Parser packaging, platform coverage and upstream gates are incomplete

The package explicitly lists shipped Python packages (`pyproject.toml:147-149`) and pins tree-sitter API ranges (`:19-47`). A grammar spike must establish maintained source, license compatibility, ABI/API compatibility, offline operation and installability on supported Python/OS combinations. Qt SDK installation must not become a requirement for ordinary source extraction.

The current CI runs the full suite with extras on Ubuntu at Python 3.10, 3.12, 3.13 and 3.14 (`.github/workflows/ci.yml:49-74`); it has no Windows/macOS test matrix in that workflow. New grammar wheels and path behavior require targeted Windows/macOS coverage. Push/PR branch filters list version branches and `main` (`:5-7`), so a push to a `codex/` development branch alone will not run this workflow unless it is dispatched or a matching-base PR exists. The security scans are currently non-blocking (`:100-106`); a green overall run is not proof those findings are absent.

## Security and correctness boundaries for the extension

`SECURITY.md` defines Graphify as a local development tool whose AST path parses source without executing it. Retain that behavior for Qt/QML: importing modules, instantiating components, loading plugins, running CMake/qmake, invoking `moc`, or starting a QML engine must not happen during ordinary analysis.

QML, `qmldir`, generated `.qmltypes`, build files and resource manifests are untrusted inputs. Metadata references must not widen the scanned corpus through absolute paths, `..`, symlinks or ignored files. Parse resource XML without external entities or DTD resolution; the existing project XML safety helper (`graphify/extract.py:5721`) is a useful precedent. Apply explicit limits to bytes, nesting, item count and resolver fan-out; return bounded diagnostics on malformed input.

Record evidence per fact and edge: declaring source, location, resolution basis and confidence. Distinguish an observed registration statement from proof that it executes for a particular runtime configuration. Imported Qt types, generated members, `NOTIFY` signals, asynchronous connections and dynamically loaded components have different evidence requirements. A name match is insufficient.

Preserve portable IDs and paths in every new metadata bucket; `graphify/cache.py:573`, `:796`, `:813`, `:836` already has recursive portability handling, and `graphify/watch.py:388-411` has explicit source-key handling. Verify new structured facts across save/load, separate cache locations and relocated checkouts. Do not include machine-specific paths or credential data in public reports or fixtures.

## Reproducible baseline experiments

The setup verification already reproduced the B01/B02 classifications below; detailed commands and focused test results are in [VALIDATION.md](VALIDATION.md). The remaining experiments are proposed acceptance work whose expected outcomes are inferred from inspected source. Use temporary corpus and output directories; preserve the imported baseline and commit no generated graph/cache files.

Observed baseline classifications: `Main.qml`, `Panel.ui.qml`, `plugins.qmltypes`, `qmldir`, `app.pro` and `assets.qrc` each return no classification and no extractor. `CMakeLists.txt` is a document with no AST extractor. Control files `backend.hpp` and `helpers.mjs` are code and select `extract_cpp` and `extract_js`, respectively.

| Experiment | Minimal corpus or mutation | Expected baseline limitation / acceptance evidence |
| --- | --- | --- |
| B01: Entry points | `Main.qml` containing an import and a root object; an ordinary `helper.js`; a plain C++ class | Observed: QML classifier and extractor return `None`. Source inspection shows directory omission. Ordinary JS/C++ establish controls; add end-to-end explicit-file and directory tests. |
| B02: Named metadata | Extensionless `qmldir`, `plugins.qmltypes`, `resources.qrc`, `CMakeLists.txt` | Observed: Qt metadata has no extractor; `CMakeLists.txt` follows the document path. Add scan/collector/watch consistency tests before shared filename recognition. |
| B03: Qt parser recovery | QObject class with `Q_OBJECT`, `Q_PROPERTY`, signal, slot and invokable method; paired header/implementation | Capture node/edge labels and parse warnings. Compare to equivalent plain C++ without macros. Determine which declarations survive; do not infer Qt awareness from survival. |
| B04: Bridge precision | Explicit registered C++ type used by QML; unrelated class with identical member names; duplicate type registrations | Before implementation there is no QML bridge. Acceptance requires only the evidenced type/member targets, with unresolved or ambiguous cases visible and no name-only edges. |
| B05: Identity | Same QML basenames in two module directories, case-distinct names, repeated handlers and inline components | Stable distinct IDs, original labels and correct scopes after sequential, parallel, cached and relocated runs. |
| B06: Build/export loss | Extracted `references` and `uses` between the same two source-backed nodes | Baseline simple graph collapses the pair to one surviving edge; quantify and verify the extension's chosen representation across JSON reload. |
| B07: Partial rebuild | Change only `qmldir` version/type mapping, `.qmltypes`, C++ registration or resource alias; then delete a referenced component | Incremental output equals normalized clean-build output in supported cases; stale edges disappear and unchanged sources remain intact. |
| B08: Corpus isolation | Refer to excluded/out-of-root files and a symlink escaping the root; fake XML external entity | No source expansion or host-file reads; bounded diagnostics; no Graphify cache created inside a separate analyzed source tree. |
| B09: User queries | Ask which type a component uses, which C++ member backs a binding, and which handlers are affected by a signal/property change | Correct provenance, direction, confidence and evidence survive default MCP/query/affected/export consumption. |
| B10: Packaging | Install a built wheel in a clean environment and parse the checked-in QML fixtures without network/Qt SDK | Required extractor code/grammar is packaged, optional-parser behavior is explicit, and supported OS/Python lanes work. |
| B11: Qt event relationships | Signals/slots using keyword and `Q_*` forms; `emit`/`Q_EMIT`; pointer-member, literal macro, overload and lambda connections; explicit and automatic modes | Ordinary calls are distinguished from source-backed emissions/connections, all endpoints and modes retain provenance, and unknown receivers/overloads stay unresolved. Verify queries, exports and incremental change/removal of connections (`REQ-QML-016`). |
| B12: Bidirectional object APIs | A literal-loaded QML component obtained through a root/create handle; a unique named child; C++ property read/write, method invocation and signal connection; source-backed context-object/property and initial-property maps | C++ sites resolve to the declared QML object/member and direction; QML sites resolve to their evidenced exposed C++ objects. Duplicate/computed object or member names do not create guessed edges. Compare incremental output against clean rebuilds when either side changes (`REQ-QML-017`). |

For B01, a minimal read-only API probe after the environment is installed is:

```python
from pathlib import Path
from graphify.detect import classify_file
from graphify.extract import _get_extractor, collect_files

root = Path("<temporary-corpus>")
qml = root / "Main.qml"
print(classify_file(qml))
print(_get_extractor(qml))
print([p.relative_to(root).as_posix() for p in collect_files(root)])
```

For B03, run `extract([header, implementation], root=corpus, cache_root=temporary_output, parallel=False)` and inspect source-backed nodes, Qt-specific facts, relationships and `parse_errors`. Repeat from a clean cache after grammar/normalization changes. Parse warnings indicate uncertainty and must not be discarded solely to make this experiment appear green.

## Verification commands and upstream compatibility

Use the pinned lockfile and the repository's own workflow conventions once the environment is available:

```text
uv sync --all-extras --frozen
uv run --frozen python -X utf8 -m pytest tests/ -q --tb=short
uv run --frozen ruff check .
uv run --frozen pyright
uv run --frozen python -m tools.skillgen --check
```

Relevant existing regression groups are detection/ignore and non-regular-file tests; C++ declarations, header pairing and cross-file calls; language resolver and cross-language guard tests; ID/cache portability tests; incremental/stale-prune/partial-extraction tests; query/affected direction tests; export/round-trip tests; and wheel packaging tests. Reuse these contracts and add fixtures that demonstrate new failure modes, rather than replacing the generic C++/JS behavior.

The module-based pytest invocation supplies an importable main module to Windows multiprocessing, and `-X utf8` avoids default-codepage differences. The setup run using this form recorded 1,265 passed, 53 skipped and two Windows deleted-current-directory failures across six focused suites; it was not a full-suite run. Ruff and generated-skill checks passed. Pyright reported 634 errors and four warnings, including optional imports and existing typing issues; the baseline must not be described as passing all checks. See [VALIDATION.md](VALIDATION.md) for exact commands and limitations.

If documentation for installed agent skills changes, edit authoritative fragments under `tools/skillgen/`, regenerate according to `CONTRIBUTING.md`, and run the workflow's schema/coverage/round-trip checks. After implementation code changes, run `graphify update .` as required by the root development guidance and record any inability to refresh the graph.

The architecture and increment plan should turn A01-A09 into narrow upstream contributions with explicit supported syntax, unsupported runtime cases, regression evidence and full-build/incremental equivalence gates. Complete QML support is a measurable sequence of language-analysis capabilities; this audit establishes the baseline from which to measure it.
