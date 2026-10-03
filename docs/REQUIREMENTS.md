# Graphify requirements

This is the canonical product requirements document. Current entries cover the
Qt/QML support extension. Add or update product requirements here with the
behavioural change, preserving established identifiers and acceptance traceability.

QML-003 is **Verified** for the documented declaration subset. QML-001 and
QML-002/010/011/012/013/014/015 are **Partially implemented**. Others are **Planned**.
See criterion evidence in [IMPLEMENTATION.md](qt-qml/IMPLEMENTATION.md).
Generic C++ and JavaScript behavior remains baseline capability.
Increment references identify delivery stages, not completion evidence.

| ID | Required behavior (summary) | Increments |
| --- | --- | --- |
| QML-001 | The declared parser backend installs on supported Python/OS targets, parses the supported syntax without network access at analysis time, and reports unavailable or incompatible parser support explicitly. Unsupported syntax is distinguished from an empty valid file. | 00, 01, 03 |
| QML-002 | Full detection and update agree on inclusion of `.qml`, `.ui.qml`, and supported named metadata. Existing ignore, root, symlink, and size boundaries apply. `qmldir` is detected by exact filename. Unrelated extensionless files remain excluded. | 01, 02, 05, 06 |
| QML-003 | Components, object instances, properties, signals, and functions produce source-backed nodes with correct locations and deterministic identities. Duplicate `id` values in different component scopes do not merge. Comments, strings, and grouped properties do not create false object declarations. | 01 |
| QML-004 | Directory and URI imports, aliases, versions, and `qmldir` declarations resolve only within documented import paths and module visibility. Duplicate type names in different modules cannot bind by a global name guess. Unknown, ambiguous, or unavailable modules remain unresolved. | 02 |
| QML-005 | Component-local `id` scope, inline components, singleton declarations, inherited members, and external types retain their documented boundaries. Same-name members in separate scopes remain distinct. Only supported, source-backed visibility permits a resolved link. | 02 |
| QML-006 | Supported property bindings and property aliases produce directional dependency links to visible targets with expression evidence. Evaluation, getters, and side effects never run during analysis. Dynamic or unsupported expressions retain an explicit unresolved status. | 03 |
| QML-007 | Embedded functions, handlers, `Connections`, and imported JavaScript participate in scoped call/reference and signal relationships. Lexical shadowing, import aliases, `.pragma library`, and shared JS between QML/other callers are covered. Dynamic dispatch does not become a definite call. | 03 |
| QML-008 | Supported `QML_ELEMENT`/named/singleton and literal `qmlRegister*` registrations link QML-visible names to the correct C++ class and module. `Q_PROPERTY`, invokable methods, signals, and notify relationships retain source evidence. Matching labels or a `Q_OBJECT` macro alone cannot establish exposure. | 04 source overlay, 05 module enrichment |
| QML-009 | Supported literal CMake, qmake, `qmldir`, `.qmltypes`, and `.qrc` declarations describe module membership, type metadata, and resource aliases. Project files, plugins, and JavaScript never execute. Variable expansion or generated inputs outside the supported subset are reported as incomplete. | 02, 05 |
| QML-010 | Repeated analysis of identical input has stable IDs and normalized output. Serialized graphs retain valid endpoints, direction, relation context, and provenance. Multiple distinct relationships between the same endpoints cannot silently disappear. Inferred resolution stays distinct from extracted syntax. | All |
| QML-011 | Cold rebuild, warm cache, manual update, and watch agree on normalized Qt/QML output. File edits, renames, deletion, import-path changes, parser/config changes, and metadata-only or C++-only changes invalidate affected resolution. Unchanged QML files can acquire or lose links after their providers change. | 01 safety, 06 complete |
| QML-012 | Malformed input, missing parser, partial extraction, and failed resolution cannot replace a valid persisted graph/cache with a misleading empty or incomplete result. Diagnostics identify unsupported or failed stages. Existing zero-node, shrink, and provenance protections remain effective. | All |
| QML-013 | Query, explain, path, affected, JSON/HTML and other supported exports, and optional MCP consumers preserve the accepted Qt/QML nodes, relation context, locations, and direction. Scoped results do not invent unavailable framework internals. | 01 smoke, 07 complete |
| QML-014 | Supported Python/OS targets have install and behavior evidence. Mixed C++/JS and other affected language regressions stay green. Windows paths, Unicode, imports with the same stem, and optional-parser absence are explicit cases. Skips and baseline failures remain visible. | All |
| QML-015 | Public support documentation accurately lists implemented syntax, resolution limits, and optional dependencies. Generated assistant instructions are updated through their source fragments. Each increment has a reviewable PR, matching tests, and verified upstream-base compatibility before release. | All |
| QML-016 | Qt C++ signals, slots, emissions and signal connections retain their meta-object semantics. Supported member-pointer, functor/lambda, explicit-overload and legacy `SIGNAL`/`SLOT` forms link source-backed endpoints with connection evidence and declared type/flags; signal delivery is distinct from an ordinary direct call. | 04, 06 parity, 07 consumers |
| QML-017 | Both integration directions are analyzed: registered or explicitly supplied C++ APIs visible to QML, and C++ loading/accessing QML objects, properties, signals and methods. Supported literal loaders, context/initial-property exposure, object lookup and meta-object access resolve only when source/project evidence establishes the target. | 04 source access, 05 module/resource enrichment, 06 parity, 07 consumers |

## Assigned acceptance criteria

Each criterion belongs to the requirement named in its ID. Criteria without
executed evidence in IMPLEMENTATION.md remain **Not executed**. Verification owners
and coverage gaps are assigned in [tests/TRACEABILITY.md](../tests/TRACEABILITY.md).
Fixture/test names remain proposed until their increment implements them.

Each acceptance ID has a planned completion increment in
[tests/TRACEABILITY.md](../tests/TRACEABILITY.md), with dependencies and reviewable
work packages in the [increment plan](qt-qml/PLAN.md). Earlier partial evidence does
not close a criterion whose metadata, incremental or consumer cases remain pending.

The agreed initial profile is Qt 6 with both CMake and qmake. QML-00 records the
exact syntax, version, platform and parser matrix used by the criteria. Cases
outside that matrix must be explicitly Unsupported or Deferred, with a reason;
removing a promised case requires a documented requirement change. A requirement
becomes Verified only when each applicable criterion has cited passing evidence.

### QML-001 — Parser availability and compatibility

- **QML-001-AC01:** A built Graphify wheel with the selected QML extra installs in each declared Python/OS lane and exposes a usable parser through Graphify's production entry point; record parser/API/grammar versions and licenses.
- **QML-001-AC02:** With network access disabled and no Qt SDK, every supported-syntax fixture yields its hand-checked declarations and spans; repeated runs produce the same normalized result.
- **QML-001-AC03:** Without the extra, or with an incompatible parser, scanning a QML file produces a file-level unavailable-parser diagnostic and does not cache an empty result as successful AST extraction.
- **QML-001-AC04:** Empty valid, malformed, and unsupported-syntax fixtures produce distinguishable completion/coverage diagnostics; malformed input never passes as fully analyzed.

### QML-002 — Corpus discovery

- **QML-002-AC01:** Full detection, code-only collection, direct supported-file extraction, manual update and watch admit `.qml` and `.ui.qml`; each path selects the same intended extractor.
- **QML-002-AC02:** Each delivered metadata format, including exact-name `qmldir` and `CMakeLists.txt`, is admitted consistently by its applicable entry points; unrelated extensionless files remain excluded.
- **QML-002-AC03:** Ignored, out-of-root, disallowed symlink and over-limit fixtures remain excluded from extraction and metadata traversal under the existing corpus policy.
- **QML-002-AC04:** Windows/POSIX separators, spaces and Unicode filenames give equivalent normalized corpus membership; existing non-QML classification regression cases still pass.

### QML-003 — Source-backed declarations and identity

- **QML-003-AC01:** A fixture with nested objects, properties, signals and functions yields exactly the expected declarations, ownership links, original names and source locations.
- **QML-003-AC02:** Equal `id`/member names in different component scopes, duplicate basenames in different directories, and `Panel.qml` beside `Panel.cpp` produce distinct identities.
- **QML-003-AC03:** Comments, strings containing braces/type names, and grouped property blocks create no false component/object declarations; valid object declarations remain present.
- **QML-003-AC04:** Unchanged input preserves normalized IDs across sequential/parallel, warm/cold cache and relocated-root runs; a line inserted before a named declaration changes its span without changing its identity.

### QML-004 — Imports and module resolution

- **QML-004-AC01:** Directory, URI, aliased and supported versioned imports resolve to exactly the visible providers in a hand-checked multi-module fixture, preserving import evidence.
- **QML-004-AC02:** Two modules exporting the same type name do not cross-bind; aliases, selected import versions and `qmldir` visibility determine the endpoint.
- **QML-004-AC03:** Missing modules, incompatible versions and duplicate eligible providers retain explicit unresolved/ambiguous reasons and produce no arbitrarily resolved edge.
- **QML-004-AC04:** Resolution uses only declared corpus/import roots; an ignored or out-of-root provider and a remote import do not trigger source expansion or network access.

### QML-005 — Component and member scopes

- **QML-005-AC01:** References to component-local `id` values resolve inside the correct component; identical IDs in another file or inline component are not visible accidentally.
- **QML-005-AC02:** Inline-component shadowing, singleton use and supported inherited-member cases match hand-checked visibility expectations without merging equal names.
- **QML-005-AC03:** Private/internal, unavailable external, and unsupported dynamic members remain unresolved unless explicit supported metadata establishes their visibility.
- **QML-005-AC04:** Imported type names, object instances and members have separate identities and lookup roles; a same-label type or member from an unrelated scope cannot satisfy a reference.

### QML-006 — Bindings and property aliases

- **QML-006-AC01:** Supported property reads and aliases create links to the expected visible source members, with the documented dependency direction and originating expression span.
- **QML-006-AC02:** Nested qualified aliases and binding expressions honor component/object scope; missing or ambiguous targets produce a coverage reason and no guessed endpoint.
- **QML-006-AC03:** A fixture containing an expression with observable side effects is analyzed without executing the expression, invoking a getter or loading its runtime dependencies.
- **QML-006-AC04:** Distinct reads/bindings involving the same endpoints survive extraction, graph construction and serialization according to the accepted nonlossy projection contract.

### QML-007 — JavaScript, handlers and signals

- **QML-007-AC01:** Embedded functions and handlers resolve statically visible calls/references with original QML source locations; lexical shadowing prevents links to hidden same-name functions.
- **QML-007-AC02:** Imported `.js`/`.mjs` helpers, aliases and supported `.pragma library` directives resolve without changing ordinary JS behavior or executing script code.
- **QML-007-AC03:** Supported `Connections` and handler fixtures link the expected target signal and handler, distinguish declarations from subscriptions, and preserve evidence/direction.
- **QML-007-AC04:** Runtime-selected targets and dynamic calls remain explicitly unresolved; shared JS used by QML and non-QML callers does not gain spurious cross-language edges.

### QML-008 — Qt/C++ exposure bridge

- **QML-008-AC01:** Valid `QML_ELEMENT`, identifier-form `QML_NAMED_ELEMENT(Backend)`, singleton and supported literal `qmlRegister*` fixtures map visible QML names to the correct C++ declarations and module evidence.
- **QML-008-AC02:** `Q_PROPERTY`, invokable methods, signals and `NOTIFY` references retain correct source spans and members; header/implementation pairs reuse existing canonical class/method identities.
- **QML-008-AC03:** Duplicate registrations, unsupported macro wrappers and ambiguous overloads retain reasons rather than arbitrary bridges; `Q_OBJECT`, inheritance or matching labels alone create no exposure link.
- **QML-008-AC04:** Qt macro text inside comments/strings has no semantic effect, source offsets remain correct after parser recovery, and existing C++ normalization/test-macro/cross-language guard regressions pass.

### QML-009 — Qt project and resource metadata

- **QML-009-AC01:** Qt 6 CMake and qmake fixtures yield the expected literal module URI/version, sources, imports and resources; macro-based C++ exposure gets its module context from this evidence.
- **QML-009-AC02:** Supported `qmldir` and `.qmltypes` fixtures retain exports, flags, members and provenance; conflicting source/generated declarations retain both origins and a conflict diagnostic.
- **QML-009-AC03:** `.qrc` prefixes/aliases resolve supported resource URLs to accepted source files; traversal, out-of-root references and XML external-entity payloads cannot read host files or expand the corpus.
- **QML-009-AC04:** CMake/qmake conditions or expressions outside the literal subset produce an incomplete/unsupported reason; analysis never runs a build tool, plugin, `moc` or QML engine.

### QML-010 — Deterministic graph and provenance

- **QML-010-AC01:** Identical inputs yield equal canonical node/edge/fact output across process count, filesystem order and cache state; case-distinct or normalization-colliding names remain distinguishable.
- **QML-010-AC02:** Every emitted edge has valid endpoints and every source-backed fact retains an accepted root-relative path and correct source span after ID remapping and JSON reload.
- **QML-010-AC03:** A fixture with different relations on the same endpoint pair round-trips all promised facts through build/export/reload; no relation disappears through simple-graph overwrite.
- **QML-010-AC04:** Extracted syntax, inferred resolution and ambiguity retain their accepted confidence/evidence distinction; sourceless stubs cannot overwrite a source-backed definition's provenance.

### QML-011 — Incremental correctness

- **QML-011-AC01:** Cold build, warm build, manual update and watch produce equal normalized Qt/QML graphs for the supported fixture corpus after a normal QML edit.
- **QML-011-AC02:** Metadata-only and C++-registration-only edits, provider deletion/rename and duplicate-provider introduction update links in unchanged QML and remove stale derived edges.
- **QML-011-AC03:** Parser/grammar/config/import-root/ignore-policy changes invalidate the affected cached facts or resolution; stale output cannot be accepted solely because file content hashes match.
- **QML-011-AC04:** Repeated no-change updates are idempotent and preserve unrelated source facts; the final incremental graph equals a clean rebuild after every delivered mutation case.

### QML-012 — Failure handling and persistence

- **QML-012-AC01:** Missing parser, malformed source and a forced extractor/resolver failure produce bounded, stage-specific diagnostics and an explicit incomplete status.
- **QML-012-AC02:** Starting from a valid persisted graph, those failures cannot replace it with a misleading empty/incomplete graph or poison a successful cache entry under existing write protections.
- **QML-012-AC03:** Intentional deletion is distinguished from extraction failure; zero-node/shrink guards, provenance preference and documented destructive-update controls preserve their existing behavior.
- **QML-012-AC04:** Oversized/deep/hostile source and metadata fixtures terminate under documented bounds, disclose no credentials or machine-private paths, and execute no analyzed instructions.

### QML-013 — User-facing graph consumers

- **QML-013-AC01:** Query, explain and path fixtures return the expected component/module/member route with original locations and confidence; scoped answers do not connect unrelated same-name providers.
- **QML-013-AC02:** Affected traversal follows the documented dependency direction for property/signal changes and includes the expected handlers/components, including accepted Qt relation contexts.
- **QML-013-AC03:** JSON, HTML and each advertised export retain the supported Qt/QML facts and evidence after reload; omission by a consumer is explicit rather than presented as full support.
- **QML-013-AC04:** With the MCP extra installed, production MCP queries agree with equivalent CLI fixtures; searchable Qt metadata is deliberately projected/indexed rather than assumed discoverable.

### QML-014 — Platform and compatibility evidence

- **QML-014-AC01:** Every advertised Python/OS lane has a successful parser install and offline production-extraction result against the agreed corpus, with exact versions and extras recorded.
- **QML-014-AC02:** Windows path, Unicode, same-stem, relocated-root and optional-parser-absence fixtures pass the same observable contracts as supported POSIX lanes.
- **QML-014-AC03:** Relevant generic C++/JS, discovery, graph, cache, update and consumer regressions introduce no unexplained new failures relative to the recorded baseline.
- **QML-014-AC04:** Skips, baseline portability defects, unavailable optional dependencies and type-check failures remain separately reported; a skipped or unrun lane cannot count as passing support evidence.

### QML-015 — Documentation and upstream delivery

- **QML-015-AC01:** Each implementation PR updates requirement/acceptance status, actual test mapping and the public support/limit matrix to match delivered behavior, with no planned case described as shipped.
- **QML-015-AC02:** Changed assistant instructions originate in authoritative skillgen fragments; generated artifacts and applicable schema/round-trip checks pass without hand edits.
- **QML-015-AC03:** Each delivery PR records a reviewed upstream base/head, dependency/license provenance, exact executed checks and the PR #1748 reuse/attribution decision; duplicate feature work is avoided.
- **QML-015-AC04:** The release gate has reviewed evidence for every promised acceptance ID, explains any explicitly deferred criteria, and contains no private project references, credentials, internal endpoints or machine-specific paths.

### QML-016 — Qt C++ signals, slots and connections

- **QML-016-AC01:** Fixtures using `signals`, `Q_SIGNALS`, `Q_SIGNAL`, slot access sections, `Q_SLOTS` and `Q_SLOT` retain member signatures/kinds and source spans; `emit`/`Q_EMIT` link the originating code to the declared signal without inventing immediate receiver calls.
- **QML-016-AC02:** Member-pointer, explicit overload-selector/cast, signal-to-signal, functor/lambda and legacy `SIGNAL`/`SLOT` connect fixtures resolve the expected sender/signal/receiver/callable endpoints from typed or signature evidence, including compatible ordinary member targets and supported private-slot meta-object connections; same-name ordinary functions do not satisfy a connection by global label.
- **QML-016-AC03:** Connection records preserve source location, sender/receiver context, literal connection type/flags and conditional registration evidence; ambiguous signatures, dynamic endpoints or unsupported expressions remain unresolved, and declared Auto/Queued/Direct forms do not imply verified runtime thread affinity or delivery order.
- **QML-016-AC04:** Direct slot calls, signal emissions, connection declarations and supported disconnect statements remain distinct facts through build/export/query/affected and incremental updates; comments/strings do not become signal/slot declarations or connections, and unrelated C++ call regressions still pass.

### QML-017 — Bidirectional QML and C++ object integration

- **QML-017-AC01:** Literal `QQmlApplicationEngine::load`/`loadFromModule`, `QQmlComponent` create and `QQuickView::setSource` fixtures link C++ loader/access sites to the correct QML component using accepted module/resource metadata; unavailable/dynamic URLs and modules retain unresolved reasons without loading an engine.
- **QML-017-AC02:** When the QML object provenance is established, `rootObjects`/`rootObject`, literal `objectName`/`findChild` lookup, supported `property`/`setProperty` and `QMetaObject::invokeMethod` calls resolve to the correct QML object/member and preserve access direction/source evidence; QML `id` alone is not treated as a C++ `objectName` lookup key.
- **QML-017-AC03:** Connections from declared QML signals to C++ slots/callables, and from exposed C++ signals to QML handlers, resolve in the appropriate object scope; supported literal `setContextProperty`, `setContextObject` and initial-property exposure preserve provider/provenance facts, while conditional or dynamic exposure remains visibly uncertain.
- **QML-017-AC04:** Duplicate object names, computed lookup/method names and unsupported dynamic creation produce no guessed member target; query/affected and cold/full/incremental comparisons retain both integration directions after QML members, loader metadata or C++ exposure changes, with no evaluated QML or executed plugin code.

The Qt-specific semantics follow the primary references for
[signals and slots](https://doc.qt.io/qt-6.8/signalsandslots.html),
[QObject connections](https://doc.qt.io/qt-6.8/qobject.html#connect),
[C++ interaction with QML objects](https://doc.qt.io/qt-6.8/qtqml-cppintegration-interactqmlfromcpp.html),
and [meta-object invocation](https://doc.qt.io/qt-6.8/qmetaobject.html#invokeMethod).
These are acceptance contracts for source analysis, not claims that static
relationships prove a particular runtime connection executes.

The [plan](qt-qml/PLAN.md) defines acceptance examples and exit gates. Update statuses
only when implementation and cited evidence justify them; parser selection or a
passing generic C++ test does not change a Qt/QML requirement to Verified.
