# Graphify requirements

This is the canonical product requirements document. Entries cover the
Qt/QML support extension and shared assistant/analysis compatibility. Add or update product requirements here with the
behavioural change, preserving established identifiers and acceptance traceability.
Identifiers use separate `REQ-QML-` and `INC-QML-` namespaces under the
[identifier and legacy-alias contract](qt-qml/IDENTIFIERS.md).
Shared compatibility requirements use `REQ-CORE-NNN` and criteria
`REQ-CORE-NNN-ACNN`; delivery uses `INC-CORE-NN`. These independent counters
preserve every Qt/QML identity. The [compatibility plan](COMPATIBILITY.md)
defines their scope and evidence boundaries.

The Qt/QML catalog contains twenty-one requirements and eighty-five stable acceptance
criteria. INC-QML-00–07 evidence describes the original bounded Qt 6/QML profile;
later corrections and adoption extend that profile without renumbering it.
Current source, update, consumer and installed evidence is assigned individually
in [tests/TRACEABILITY.md](../tests/TRACEABILITY.md).

INC-QML-11, INC-QML-15 and INC-QML-08a/b/c are implemented and locally complete for
the documented Windows x64/Python 3.12 profile. Bounded inherited signals, exact
constructor identity, qmake paths, C++ header admission, declared providers and
child-service subscriptions have source and reviewed installed-wheel evidence.
INC-QML-28–41 correct the additional reproduced producer, consumer, transport,
publication, path-identity and diagnostic failures. AST cache schema 12 and Qt
policy 19 govern the current profile.

All seven REQ-QML-018 criteria have passing local acceptance assignments. The
requirement is **Implemented; locally verified for the bounded Windows profile**,
not Verified across the full declared platform matrix. The earlier adoption
checkpoint retains 59 pre-existing failures; the later native full-source run
records 8,818 passes and zero failures. Subsequent alias and diagnostic profiles
are recorded separately; full typing retains baseline errors. Unexecuted hosted lanes, native browser/device behavior,
live database delivery and runtime Qt effects remain explicit gaps. See the
[final adoption evidence](qt-qml/VALIDATION.md#final-adoption-delivery),
[implementation limits](qt-qml/IMPLEMENTATION.md#final-adoption-delivery),
[export contracts](qt-qml/EXPORT_MATRIX.md) and
[platform matrix](qt-qml/PLATFORM_MATRIX.md).

## Requirement catalog

The [follow-up audit](qt-qml/FOLLOWUP_AUDIT.md) reproduced wrong receiver,
child, engine-provider and native-alias targets at its baseline. INC-QML-17–20
correct those bounded forms and the two omitted literal loader routes. Source,
manual/watch lifecycle and reviewed installed-wheel evidence is recorded per
increment in [validation](qt-qml/VALIDATION.md) and acceptance traceability.
Existing acceptance IDs and numeric identities are unchanged.

The expanded criteria remain **Partially verified** across their full adoption
profile. INC-QML-21–27 implement qualified native identity, static API/loader SDK
authority, retained Windows writes, coordinated product publication, orphan
reference cleanup and native property notification handlers. Their focused source, reviewed installed-artifact and contribution-gate
results are assigned in validation and traceability. The correction cases have
local passing evidence; skipped/system and wider profile cases remain unverified. Provider adoption, inherited endpoints and overload identity
now have the bounded local source and installed evidence recorded for INC-QML-08/11/15. Original fixture passes establish their recorded profiles,
not every SDK API or runtime effect. Baseline test/type failures remain explicit.

Unsupported parenting, type, URL, overload or lifetime evidence retains an
unresolved source site. Matching text or successful publication alone does not
establish a target. The [correction acceptance matrix](qt-qml/DESIGN.md#semantic-correction-acceptance-matrix-inc-qml-1720)
defines success, rejection and lifecycle obligations; the
[API mechanism matrix](qt-qml/QT_API_COVERAGE.md) distinguishes supported forms,
conservative exclusions, generic extraction and remaining omissions.

Each criterion belongs to the requirement named in its ID. Criteria without
executed evidence in IMPLEMENTATION.md remain **Not executed**. Verification owners
and coverage gaps are assigned in [tests/TRACEABILITY.md](../tests/TRACEABILITY.md).
Traceability labels actual executed tests and retains explicit cases for later increments.

Each acceptance ID has a planned completion increment in
[tests/TRACEABILITY.md](../tests/TRACEABILITY.md), with dependencies and reviewable
work packages in the [increment plan](qt-qml/PLAN.md). Earlier partial evidence does
not close a criterion whose metadata, incremental or consumer cases remain pending.

The agreed initial profile is Qt 6 with both CMake and qmake. INC-QML-00 records the
exact syntax, version, platform and parser matrix used by the criteria. Cases
outside that matrix must be explicitly Unsupported or Deferred, with a reason;
removing a promised case requires a documented requirement change. A requirement
becomes Verified only when each applicable criterion has cited passing evidence.

<a name="qml-001--parser-availability-and-compatibility"></a>

### REQ-QML-001 — Parser availability and compatibility

The declared parser backend installs on supported Python/OS targets, parses the supported syntax without network access at analysis time, and reports unavailable or incompatible parser support explicitly. Unsupported syntax is distinguished from an empty valid file.

**Acceptance Criteria**

1 - A built Graphify wheel with the selected QML extra installs in each declared Python/OS lane and exposes a usable parser through Graphify's production entry point; record parser/API/grammar versions and licenses. (`REQ-QML-001-AC01`)

2 - With network access disabled and no Qt SDK, every supported-syntax fixture yields its hand-checked declarations and spans; repeated runs produce the same normalized result. (`REQ-QML-001-AC02`)

3 - Without the extra, or with an incompatible parser, scanning a QML file produces a file-level unavailable-parser diagnostic and does not cache an empty result as successful AST extraction. (`REQ-QML-001-AC03`)

4 - Empty valid, malformed, and unsupported-syntax fixtures produce distinguishable completion/coverage diagnostics; malformed input never passes as fully analyzed. (`REQ-QML-001-AC04`)

<a name="qml-002--corpus-discovery"></a>

### REQ-QML-002 — Corpus discovery

Full detection and update agree on inclusion of `.qml`, `.ui.qml`, and supported named metadata. Existing ignore, root, symlink, and size boundaries apply. `qmldir` is detected by exact filename. Unrelated extensionless files remain excluded.

**Acceptance Criteria**

1 - Full detection, code-only collection, direct supported-file extraction, manual update and watch admit `.qml` and `.ui.qml`; each path selects the same intended extractor. (`REQ-QML-002-AC01`)

2 - Each delivered metadata format, including exact-name `qmldir` and `CMakeLists.txt`, is admitted consistently by its applicable entry points; unrelated extensionless files remain excluded. (`REQ-QML-002-AC02`)

3 - Ignored, out-of-root, disallowed symlink and over-limit fixtures remain excluded from extraction and metadata traversal under the existing corpus policy. (`REQ-QML-002-AC03`)

4 - Windows/POSIX separators, spaces and Unicode filenames give equivalent normalized corpus membership; existing non-QML classification regression cases still pass. (`REQ-QML-002-AC04`)

<a name="qml-003--source-backed-declarations-and-identity"></a>

### REQ-QML-003 — Source-backed declarations and identity

Components, object instances, properties, signals, and functions produce source-backed nodes with correct locations and deterministic identities. Duplicate `id` values in different component scopes do not merge. Comments, strings, and grouped properties do not create false object declarations.

**Acceptance Criteria**

1 - A fixture with nested objects, properties, signals and functions yields exactly the expected declarations, ownership links, original names and source locations. (`REQ-QML-003-AC01`)

2 - Equal `id`/member names in different component scopes, duplicate basenames in different directories, and `Panel.qml` beside `Panel.cpp` produce distinct identities. (`REQ-QML-003-AC02`)

3 - Comments, strings containing braces/type names, and grouped property blocks create no false component/object declarations; valid object declarations remain present. (`REQ-QML-003-AC03`)

4 - Unchanged input preserves normalized IDs across sequential/parallel, warm/cold cache and relocated-root runs; a line inserted before a named declaration changes its span without changing its identity. (`REQ-QML-003-AC04`)

<a name="qml-004--imports-and-module-resolution"></a>

### REQ-QML-004 — Imports and module resolution

Directory and URI imports, aliases, versions, and `qmldir` declarations resolve only within documented import paths and module visibility. Duplicate type names in different modules cannot bind by a global name guess. Unknown, ambiguous, or unavailable modules remain unresolved.

**Acceptance Criteria**

1 - Directory, URI, aliased and supported versioned imports resolve to exactly the visible providers in a hand-checked multi-module fixture, preserving import evidence. (`REQ-QML-004-AC01`)

2 - Two modules exporting the same type name do not cross-bind; aliases, selected import versions and `qmldir` visibility determine the endpoint. (`REQ-QML-004-AC02`)

3 - Missing modules, incompatible versions and duplicate eligible providers retain explicit unresolved/ambiguous reasons and produce no arbitrarily resolved edge. (`REQ-QML-004-AC03`)

4 - Resolution uses only declared corpus/import roots; an ignored or out-of-root provider and a remote import do not trigger source expansion or network access. (`REQ-QML-004-AC04`)

<a name="qml-005--component-and-member-scopes"></a>

### REQ-QML-005 — Component and member scopes

Component-local `id` scope, inline components, singleton declarations, inherited members, and external types retain their documented boundaries. Same-name members in separate scopes remain distinct. Only supported, source-backed visibility permits a resolved link.

**Acceptance Criteria**

1 - References to component-local `id` values resolve inside the correct component; identical IDs in another file or inline component are not visible accidentally. (`REQ-QML-005-AC01`)

2 - Inline-component shadowing, singleton use and supported inherited-member cases match hand-checked visibility expectations without merging equal names. (`REQ-QML-005-AC02`)

3 - Private/internal, unavailable external, and unsupported dynamic members remain unresolved unless explicit supported metadata establishes their visibility. (`REQ-QML-005-AC03`)

4 - Imported type names, object instances and members have separate identities and lookup roles; a same-label type or member from an unrelated scope cannot satisfy a reference. (`REQ-QML-005-AC04`)

<a name="qml-006--bindings-and-property-aliases"></a>

### REQ-QML-006 — Bindings and property aliases

Supported property bindings and property aliases produce directional dependency links to visible targets with expression evidence. Evaluation, getters, and side effects never run during analysis. Dynamic or unsupported expressions retain an explicit unresolved status.

**Acceptance Criteria**

1 - Supported property reads and aliases create links to the expected visible source members, with the documented dependency direction and originating expression span. (`REQ-QML-006-AC01`)

2 - Nested qualified aliases and binding expressions honor component/object scope; missing or ambiguous targets produce a coverage reason and no guessed endpoint. (`REQ-QML-006-AC02`)

3 - A fixture containing an expression with observable side effects is analyzed without executing the expression, invoking a getter or loading its runtime dependencies. (`REQ-QML-006-AC03`)

4 - Distinct reads/bindings involving the same endpoints survive extraction, graph construction and serialization according to the accepted nonlossy projection contract. (`REQ-QML-006-AC04`)

<a name="qml-007--javascript-handlers-and-signals"></a>

### REQ-QML-007 — JavaScript, handlers and signals

Embedded functions, handlers, `Connections`, and imported JavaScript participate in scoped call/reference and signal relationships. Lexical shadowing, import aliases, `.pragma library`, and shared JS between QML/other callers are covered. Dynamic dispatch does not become a definite call.

**Acceptance Criteria**

1 - Embedded functions and handlers resolve statically visible calls/references with original QML source locations; lexical shadowing prevents links to hidden same-name functions. (`REQ-QML-007-AC01`)

2 - Imported `.js`/`.mjs` helpers, aliases and supported `.pragma library` directives resolve without changing ordinary JS behavior or executing script code. (`REQ-QML-007-AC02`)

3 - Supported `Connections` and handler fixtures link the expected target signal and handler, distinguish declarations from subscriptions, and preserve evidence/direction. A native `on<Property>Changed` subscription uses the property's actual accepted
NOTIFY signal, including a differently named or shared signal. Explicit function
and arrow handlers bind their declared formal parameters; only legacy block
handlers receive implicit signal parameters. A missing, invalid, CONSTANT,
ambiguous or unexposed notifier creates no guessed subscription. (`REQ-QML-007-AC03`)

4 - Runtime-selected targets and dynamic calls remain explicitly unresolved; shared JS used by QML and non-QML callers does not gain spurious cross-language edges. (`REQ-QML-007-AC04`)

<a name="qml-008--qtc-exposure-bridge"></a>

### REQ-QML-008 — Qt/C++ exposure bridge

Supported `QML_ELEMENT`/named/singleton and literal `qmlRegister*` registrations link QML-visible names to the correct C++ class and module. `Q_PROPERTY`, invokable methods, signals, and notify relationships retain source evidence. Matching labels or a `Q_OBJECT` macro alone cannot establish exposure.

**Acceptance Criteria**

1 - Valid `QML_ELEMENT`, identifier-form `QML_NAMED_ELEMENT(Backend)`, singleton and supported literal `qmlRegister*` fixtures map visible QML names to the correct C++ declarations and module evidence. (`REQ-QML-008-AC01`)

2 - `Q_PROPERTY`, invokable methods, signals and `NOTIFY` references retain correct source spans and members; header/implementation pairs reuse existing canonical class/method identities. Distinct qualified classes sharing a basename within one source file retain separate canonical class identities. Merged declarations retain exact accepted definition-file/location and class-ownership evidence when mapping native Qt overlays. Forward declarations retain their facts and IDs without competing with a unique complete class definition for ownership. Fresh and accepted-context representations of the same complete body retain exact source file/span and count as one body without mutating borrowed inputs; distinct complete definitions remain ambiguous. A member or function-local class occurrence with a uniquely accepted canonical callable retains a source-site containment link even when its class has no accepted Qt definition; this does not establish a native class, QObject role or QML exposure. Missing or conflicting callable evidence cannot create that link or an arbitrary class owner. An observed Qt occurrence without a callable owner retains containment by its uniquely accepted in-corpus source file, using the actual canonical file ID and original occurrence span. Missing, foreign, ambiguous or incorrectly typed file evidence creates no link; file containment leaves callable/class/target identities and unresolved status unchanged. Native property notification references retain the canonical accepted signal
identity and provider ownership through serialization; property handler spelling
does not create a synthetic native signal. Supported constructors with bounded
builtin, self-class or evidenced QObject parameter types retain distinct signature
identities independent of neighboring overloads, parameter names and defaults.
Exact declaration/definition spans identify each accepted owner; conflicting
signatures, types or bodies cannot lend native authority. (`REQ-QML-008-AC02`)

3 - Duplicate registrations, unsupported macro wrappers and ambiguous overloads retain reasons rather than arbitrary bridges; `Q_OBJECT`, inheritance or matching labels alone create no exposure link. (`REQ-QML-008-AC03`)

4 - Qt macro text inside comments/strings has no semantic effect, source offsets remain correct after parser recovery, and existing C++ normalization/test-macro/cross-language guard regressions pass. (`REQ-QML-008-AC04`)

<a name="qml-009--qt-project-and-resource-metadata"></a>

### REQ-QML-009 — Qt project and resource metadata

Supported literal CMake, qmake, `qmldir`, `.qmltypes`, and `.qrc` declarations describe module membership, type metadata, and resource aliases. Project files, plugins, and JavaScript never execute. Variable expansion or generated inputs outside the supported subset are reported as incomplete.

**Acceptance Criteria**

1 - Qt 6 CMake and qmake fixtures yield the expected literal module URI/version, sources, imports and resources; macro-based C++ exposure gets its module context from this evidence. (`REQ-QML-009-AC01`)

2 - Supported `qmldir` and `.qmltypes` fixtures retain exports, flags, members and provenance; conflicting source/generated declarations retain both origins and a conflict diagnostic. (`REQ-QML-009-AC02`)

3 - `.qrc` prefixes/aliases resolve supported resource URLs to accepted source files; traversal, out-of-root references and XML external-entity payloads cannot read host files or expand the corpus. (`REQ-QML-009-AC03`)

4 - CMake/qmake conditions or expressions outside the literal subset produce an incomplete/unsupported reason; analysis never runs a build tool, plugin, `moc` or QML engine. (`REQ-QML-009-AC04`)

<a name="qml-010--deterministic-graph-and-provenance"></a>

### REQ-QML-010 — Deterministic graph and provenance

Repeated analysis of identical input has stable IDs and normalized output. Serialized graphs retain valid endpoints, direction, relation context, and provenance. Multiple distinct relationships between the same endpoints cannot silently disappear. Inferred resolution stays distinct from extracted syntax.

**Acceptance Criteria**

1 - Identical inputs yield equal canonical node/edge/fact output across process count, filesystem order and cache state; case-distinct or normalization-colliding names remain distinguishable. (`REQ-QML-010-AC01`)

2 - Every emitted edge has valid endpoints and every source-backed fact retains an accepted root-relative path and correct source span after ID remapping and JSON reload. (`REQ-QML-010-AC02`)

3 - A fixture with different relations on the same endpoint pair round-trips all promised facts through build/export/reload; no relation disappears through simple-graph overwrite. (`REQ-QML-010-AC03`)

4 - Extracted syntax, inferred resolution and ambiguity retain their accepted confidence/evidence distinction; sourceless stubs cannot overwrite a source-backed definition's provenance. (`REQ-QML-010-AC04`)

<a name="qml-011--incremental-correctness"></a>

### REQ-QML-011 — Incremental correctness

Cold rebuild, warm cache, manual update, and watch agree on normalized Qt/QML output. File edits, renames, deletion, import-path changes, parser/config changes, and metadata-only or C++-only changes invalidate affected resolution. Unchanged QML files can acquire or lose links after their providers change.

**Acceptance Criteria**

1 - Cold build, warm build, manual update and watch produce equal normalized Qt/QML graphs for the supported fixture corpus after a normal QML edit. (`REQ-QML-011-AC01`)

2 - Metadata-only and C++-registration-only edits, provider deletion/rename and duplicate-provider introduction update links in unchanged QML and remove stale derived edges. (`REQ-QML-011-AC02`)

3 - Parser/grammar/config/import-root/ignore-policy changes invalidate the affected cached facts or resolution; stale output cannot be accepted solely because file content hashes match. (`REQ-QML-011-AC03`)

4 - Repeated no-change updates are idempotent and preserve unrelated source facts; the final incremental graph equals a clean rebuild after every delivered mutation case. Removing or restoring source cannot leave stale synthetic reference nodes without an accepted remaining owner, including generic C++ include stubs. Still-referenced external nodes and source-backed definitions remain intact. (`REQ-QML-011-AC04`)

<a name="qml-012--failure-handling-and-persistence"></a>

### REQ-QML-012 — Failure handling and persistence

Malformed input, missing parser, partial extraction, and failed resolution cannot replace a valid persisted graph/cache with a misleading empty or incomplete result. Diagnostics identify unsupported or failed stages. Existing zero-node, shrink, and provenance protections remain effective.

**Acceptance Criteria**

1 - Missing parser, malformed source and a forced extractor/resolver failure produce bounded, stage-specific diagnostics and an explicit incomplete status. Persistent input-identity failure cannot escape diagnostic construction or disclose the backend exception body; every affected Qt/QML source receives `QML_RESOLUTION_FAILED`, with safe relative context where available and explicit unavailable context otherwise. (`REQ-QML-012-AC01`)

2 - Starting from a valid persisted graph, those failures cannot replace it with a misleading empty/incomplete graph or poison a successful cache entry under existing write protections. Required graph, manifest, analysis-root and Qt-state publication must complete before reporting update success; a failed publication retains prior accepted products and reports failure, with explicit recovery on rollback failure. (`REQ-QML-012-AC02`)

3 - Intentional deletion is distinguished from extraction failure; zero-node/shrink guards, provenance preference and documented destructive-update controls preserve their existing behavior. (`REQ-QML-012-AC03`)

4 - Oversized/deep/hostile source and metadata fixtures terminate under documented bounds, disclose no credentials or machine-private paths, and execute no analyzed instructions. (`REQ-QML-012-AC04`)

Status: **Implemented bounded profile; current local diagnostic/retention proof
passes, hosted proof pending**. INC-QML-41 adds persistent-identity failure coverage
for AC01/AC02: complete failure records and safe context, exact prior-product
retention, repaired retry and byte-stable repeat. A diagnostic label is at most
160 characters and excludes controls/line separators; unavailable or unsafe
context is the empty `source_file` string and grants no lookup authority.
Exact assignments and capability exclusions are in
[traceability](../tests/TRACEABILITY.md#failure-safe-join-diagnostics--inc-qml-41).

<a name="qml-013--user-facing-graph-consumers"></a>

### REQ-QML-013 — User-facing graph consumers

Query, explain, path, affected, JSON/HTML and other supported exports, and optional MCP consumers preserve the accepted Qt/QML nodes, relation context, locations, and direction. Scoped results do not invent unavailable framework internals.

**Acceptance Criteria**

1 - Query, explain and path fixtures return the expected component/module/member route with original locations and confidence; scoped answers do not connect unrelated same-name providers. (`REQ-QML-013-AC01`)

2 - Affected traversal follows the documented dependency direction for property/signal changes and includes the expected handlers/components, including accepted Qt relation contexts. (`REQ-QML-013-AC02`)

3 - JSON, HTML and each advertised export retain the supported Qt/QML facts and evidence after reload; omission by a consumer is explicit rather than presented as full support. (`REQ-QML-013-AC03`)

4 - With the MCP extra installed, production MCP queries agree with equivalent CLI fixtures; searchable Qt metadata is deliberately projected/indexed rather than assumed discoverable. (`REQ-QML-013-AC04`)

<a name="qml-014--platform-and-compatibility-evidence"></a>

### REQ-QML-014 — Platform and compatibility evidence

Supported Python/OS targets have install and behavior evidence. Mixed C++/JS and other affected language regressions stay green. Windows paths, Unicode, imports with the same stem, and optional-parser absence are explicit cases. Skips and baseline failures remain visible.

**Acceptance Criteria**

1 - Every advertised Python/OS lane has a successful parser install and offline production-extraction result against the agreed corpus, with exact versions and extras recorded. (`REQ-QML-014-AC01`)

2 - Windows path, Unicode, same-stem, relocated-root and optional-parser-absence fixtures pass the same observable contracts as supported POSIX lanes. (`REQ-QML-014-AC02`)

3 - Relevant generic C++/JS, discovery, graph, cache, update and consumer regressions introduce no unexplained new failures relative to the recorded baseline. (`REQ-QML-014-AC03`)

4 - Skips, baseline portability defects, unavailable optional dependencies and type-check failures remain separately reported; a skipped or unrun lane cannot count as passing support evidence. (`REQ-QML-014-AC04`)

<a name="qml-015--documentation-and-upstream-delivery"></a>

### REQ-QML-015 — Documentation and upstream delivery

Public support documentation accurately lists implemented syntax, resolution limits, and optional dependencies. Generated assistant instructions are updated through their source fragments. Each increment has a reviewable PR, matching tests, and verified upstream-base compatibility before release.

**Acceptance Criteria**

1 - Each implementation PR updates requirement/acceptance status, actual test mapping and the public support/limit matrix to match delivered behavior, with no planned case described as shipped. (`REQ-QML-015-AC01`)

2 - Changed assistant instructions originate in authoritative skillgen fragments; generated artifacts and applicable schema/round-trip checks pass without hand edits. (`REQ-QML-015-AC02`)

3 - Each delivery PR records a reviewed upstream base/head, dependency/license provenance, exact executed checks and the PR #1748 reuse/attribution decision; duplicate feature work is avoided. (`REQ-QML-015-AC03`)

4 - The release gate has reviewed evidence for every promised acceptance ID, explains any explicitly deferred criteria, and contains no private project references, credentials, internal endpoints or machine-specific paths. (`REQ-QML-015-AC04`)

<a name="qml-016--qt-c-signals-slots-and-connections"></a>

### REQ-QML-016 — Qt C++ signals, slots and connections

Qt C++ signals, slots, emissions and signal connections retain their meta-object semantics. Supported member-pointer, functor/lambda, explicit-overload and legacy `SIGNAL`/`SLOT` forms link source-backed endpoints with connection evidence and declared type/flags; signal delivery is distinct from an ordinary direct call.

**Acceptance Criteria**

1 - Fixtures using `signals`, `Q_SIGNALS`, `Q_SIGNAL`, slot access sections, `Q_SLOTS` and `Q_SLOT` retain member signatures/kinds and source spans; `emit`/`Q_EMIT` link the originating code to the declared signal without inventing immediate receiver calls. Explicit emission sites remain observable and unresolved when their declaration is missing or removed. A forward declaration does not obscure the unique complete class or exact canonical header/implementation method that owns the emission. Supported source-visible inherited signals retain their declaring endpoint through multi-level base chains; incomplete or ambiguous ownership remains unresolved. Source base access gates external member-pointer lookup independently of legacy meta-object access; unavailable access proof cannot authorize an inherited pointer endpoint. (`REQ-QML-016-AC01`)

2 - Member-pointer, explicit overload-selector/cast, signal-to-signal, functor/lambda and legacy `SIGNAL`/`SLOT` connect fixtures resolve the expected sender/signal/receiver/callable endpoints from typed or signature evidence, including compatible ordinary member targets and supported private-slot meta-object connections; same-name ordinary functions do not satisfy a connection by global label. Lexical type-alias shadowing cannot select a different global class; unsupported alias evidence remains unresolved. (`REQ-QML-016-AC02`)

3 - Connection records preserve source location, sender/receiver context, literal connection type/flags and conditional registration evidence; ambiguous signatures, dynamic endpoints or unsupported expressions remain unresolved, and declared Auto/Queued/Direct forms do not imply verified runtime thread affinity or delivery order. (`REQ-QML-016-AC03`)

4 - Direct slot calls, signal emissions, connection declarations and supported disconnect statements remain distinct facts through build/export/query/affected and incremental updates, including supported forward-declaration, header/implementation and inherited-signal ownership changes. Comments/strings do not become signal/slot declarations or connections, and unrelated C++ call regressions still pass. (`REQ-QML-016-AC04`)

<a name="qml-017--bidirectional-qml-and-c-object-integration"></a>

### REQ-QML-017 — Bidirectional QML and C++ object integration

Both integration directions are analyzed: registered or explicitly supplied C++ APIs visible to QML, and C++ loading/accessing QML objects, properties, signals and methods. Supported literal loaders, context/initial-property exposure, object lookup and meta-object access resolve only when source/project evidence establishes the target.

**Acceptance Criteria**

1 - Literal `QQmlApplicationEngine::load`/`loadFromModule`, engine URL construction, `QQmlComponent` literal construction/loadUrl followed by create and `QQuickView::setSource` fixtures link C++ loader/access sites to the correct QML component using accepted module/resource metadata; unavailable/dynamic URLs and modules retain unresolved reasons without loading an engine. Supported literal overloads preserve loader, engine and component declaration identity. Source-defined or incomplete loader/engine/URL-wrapper declarations cannot lend SDK authority merely because no complete canonical class was admitted. Source-defined loader/QUrl wrappers, unsupported creation contexts and compilation modes cannot lend SDK semantics; resource QString convenience forms remain distinct from QUrl and absolute fromLocalFile forms. (`REQ-QML-017-AC01`)

2 - When the QML object provenance is established, `rootObjects`/`rootObject`, literal `objectName`/`findChild<QObject*>` lookup with recursive or direct-only search, supported `property`/`setProperty` and `QMetaObject::invokeMethod` calls resolve to the correct QML object/member and preserve access direction/source evidence, including exact canonical enclosing-method/class ownership for supported header/implementation pairs. Reflective access cannot borrow another object's lexical member; child lookup excludes siblings and honors direct-only depth using accepted parenting evidence. Native child construction requires proven non-widget QObject ancestry; a Q_OBJECT marker or shadowed QObject spelling alone supplies no construction/type-filter authority. Static QMetaObject and QQmlProperty access also requires evidenced SDK API identity; a shadowed class or alias cannot supply that authority. QML `id` alone is not treated as a C++ `objectName` lookup key. (`REQ-QML-017-AC02`)

3 - Connections from declared QML signals to C++ slots/callables, and from exposed C++ signals to QML handlers, resolve in the appropriate object scope; supported literal `setContextProperty`, `setContextObject` and initial-property exposure preserve provider/provenance facts, while conditional or dynamic exposure remains visibly uncertain. Distinct lexical engine declarations sharing a name cannot share context providers without established declaration identity and provider lifetime. Reassignment, conditional ownership, unknown aliases and expired local providers produce no guessed binding and retain the applicable identity reason. (`REQ-QML-017-AC03`)

4 - Duplicate object names, computed lookup/method names and unsupported dynamic creation produce no guessed member target; query/affected and cold/full/incremental comparisons retain both integration directions after QML members, loader metadata, C++ exposure or supported native source-ownership changes, with no evaluated QML or executed plugin code. (`REQ-QML-017-AC04`)

<a name="qml-018--installed-project-adoption-hardening"></a>

### REQ-QML-018 — Installed-project adoption hardening

Installed Qt/QML analysis supports the newly accepted project/declaration and typed context-provider patterns, reports unsupported or uncertain relationships accurately, and preserves existing graphs on genuine parse, integrity or publication failure.

**Acceptance Criteria**

1 - A public qmake fixture with supported unconditional `$$PWD` path prefixes, ordinary unrelated build settings and conditional metadata retains its exact accepted source/module facts and original-byte spans. `$$PWD` uses the current parsed file's directory; paths remain inside accepted corpus boundaries. Qt Creator `QML_IMPORT_PATH` hints, build-time `QMLPATHS` and explicitly configured analysis/runtime roots retain separate provenance. Unevaluated conditions or arbitrary expansion affecting required facts remain uncertain/incomplete, with no invented branch choice or build execution. (`REQ-QML-018-AC01`)

2 - Public hand-checked valid Qt/C++ declaration and macro fixtures, including empty-brace parameter defaults, `Q_UNUSED` use without a caller semicolon, numeric digit separators and supported reference-return callables, extract their expected canonical declarations and original-byte spans without a false syntax failure. Numeric separators do not obscure later signal/member ownership. Paired malformed/incomplete controls remain rejected; an unsupported semantic relationship stays unresolved rather than being confused with a parser failure. Generic C++ declarations and normalization regressions remain unchanged. (`REQ-QML-018-AC02`)

3 - Literal context exposure supplied through a supported factory call or member expression resolves the statically declared API type from accepted canonical declarations and preserves provider, return/member type, owner and context evidence. Supported API hops use one object pointer or lvalue reference; source-owned root values/references use `.`, pointers use `->`, and direct address-of objects and implicit `this` retain their declaration identity. Original CV and declarator shape survive transport. Multiple pointers, pointer references, arrays, function pointers, value-return hops, opaque aliases, operator mismatches, unknown, conflicting, conditional or unsupported type/owner evidence produce no definite provider link. No factory, getter or source code executes; declared API evidence does not prove runtime conversion, allocation or const-correct invocation. (`REQ-QML-018-AC03`)

4 - Supported calls, `Connections` handlers and `signal.connect(handler)` subscriptions through an exposed context provider and a typed child-service property resolve to the correct declared C++ member/signal and QML handler. Scope, lexical shadowing, ambiguity and connection direction survive graph build/reload and query/affected consumers. Source occurrence and endpoint roles authorize the relationship mechanism; changing a read into a call, borrowing another occurrence or substituting an incompatible context grants no bridge. Affected queries use accepted logical source/target direction in directed and undirected graphs, including class-member seeding and actual source-owner propagation. Partial, foreign or contradictory direction metadata grants no dependency. Subscriptions remain distinct from ordinary calls and runtime delivery. (`REQ-QML-018-AC04`)

5 - A clean installed optional wheel analyzes a public mixed Qt 6/QML project containing the accepted positive forms from AC01–AC04 through the production CLI, both at its project root and at an explicitly configured safe application subroot. Hand-checked facts, root boundaries and consumer results match source evidence without executing the analyzed project. Cold/warm, manual-update and watch results equal clean rebuilds after metadata, context-provider, child-member and signal edits/removal; prior initial-profile and unrelated-language evidence remains applicable or is reverified. (`REQ-QML-018-AC05`)

6 - Actual parser, resolver and publication failures against that fixture produce bounded stage-specific diagnostics and preserve prior graph, manifest, analysis state and existing successful content-keyed source-cache bytes, including rejected read-only destination replacement on supported Windows hosts. Missing optional parser, rejected root/path expansion and corrupt transport remain explicit failures. JSON serialization rejects partial, foreign, ill-typed or contradictory direction markers before writing, retains previous output and reports QT_EXPORT_DIRECTION; force cannot turn invalid markers into valid-looking endpoints. A corrected retry succeeds and a repeated no-change update is idempotent from the first successful publication, including raw no-cluster output; transient extraction-run lists or absent-versus-empty diagnostic lists alone cannot rewrite accepted graph bytes or modification time. Meaningful diagnostics and source changes remain observable. Diagnostics and public fixtures contain no private source, identifiers, paths or credentials, and analysis runs no Qt application, build hook or plugin. (`REQ-QML-018-AC06`)

7 - Ambiguous `.h` inputs with supported source-visible C++ declaration markers select the C++ extractor across whitespace, BOM, CRLF and Unicode forms. Comments and string literals cannot supply those markers; plain C and inconclusive headers retain existing C dispatch, and Objective-C dispatch retains its established priority. Header-only edits refresh the selected extractor's source facts through the facade and installed updates without executing the header. (`REQ-QML-018-AC07`)

Status: **Implemented; all seven criteria locally verified for the bounded
Windows x64/Python 3.12 profile**. Individual success, rejection, update and failure
assignments appear in [traceability](../tests/TRACEABILITY.md#final-adoption-delivery).
The reviewed installed wheel passes 3,024 selected tests; four actual installed
CLI profiles cover CMake/qmake at whole-project and configured safe application
roots. Repetition preserves accepted bytes; ordinary regressions additionally
check modification times, real edits, stale-edge removal and repaired retries.
Valid new content-keyed source-cache entries may be added after successful source
analysis before publication; they do not accept a graph or checkpoint. Existing
successful entries and prior products survive the tested failures.

The extended provider and metadata contracts supplement the initial REQ-QML-009
and REQ-QML-017 profiles. Wider hosted-platform verification and baseline full-suite
and type failures remain outstanding delivery evidence; this status does not
claim arbitrary Qt SDK, build or runtime compatibility.

The added qmake distinctions follow the Qt 6.8
[variable reference](https://doc.qt.io/qt-6.8/qmake-variable-reference.html#qml-import-path)
and [`PWD` contract](https://doc.qt.io/qt-6.8/qmake-variable-reference.html#pwd).
Context-provider fixtures follow
[Qt context properties](https://doc.qt.io/qt-6.8/qtqml-cppintegration-contextproperties.html);
static type evidence does not establish a factory's runtime result or signal delivery.

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

### REQ-QML-019 — Readable large-graph HTML export

HTML export of an accepted large graph produces a complete, labeled community
representation when its analysis partition or labels are unavailable, with all
exported view data selected initially. View preparation uses local graph evidence
and preserves the full canonical graph. An unavailable or failed HTML view is
reported accurately instead of claiming that a file was written.

**Acceptance Criteria**

1 - Above the configured HTML node limit, production export accepts a community partition only when it covers every graph node exactly once without foreign or duplicate members. Missing, empty or invalid partitions are replaced by a deterministic local partition of a view copy through the existing clustering interface, without an API call or rewriting graph/analysis files. The production CLI resolves analysis metadata beside an explicitly selected graph. Public fixtures exercise missing, empty, partial, duplicate and foreign-node partitions through the actual export path. (`REQ-QML-019-AC01`)

2 - The emitted community view has visible, nonempty labels and a populated legend whose IDs, labels and member counts agree with its plotted groups. Valid supplied labels are preserved; missing labels use the existing local hub-based labeling, and labels for a replaced partition are not reused as if they described the new groups. The inspector distinguishes internal source edges, external source edges and neighboring communities. A closed community with internal links is distinguished from a genuinely unlinked source group; internal links are not fabricated as cross-community lines or self-loops. The artifact identifies its aggregated representation and omitted source details, retains existing escaping and Qt/QML payload protections, and leaves canonical graph nodes, edges and source facts unchanged. Emitted-script/DOM-harness and payload tests establish their exact coverage; an unexecuted browser inspection is not reported as completed browser verification. (`REQ-QML-019-AC02`)

3 - Unrecoverable grouping reports actionable `HTML_GROUPING_INVALID`; an unusable or skipped aggregate view reports `HTML_VIEW_UNAVAILABLE`; an actual publication failure reports `HTML_VIEW_FAILED`. Each causes the production HTML export command to exit unsuccessfully without a false written-file message, preserving prior valid HTML and canonical graph files. A graph with too many isolated groups to fit the supported aggregate limit reports a bounded failure and focused-graph guidance rather than inventing group membership or bypassing the limit. A corrected retry publishes the expected view, and repeated export of unchanged input retains the same grouping and label behavior under the same clustering backend/configuration. (`REQ-QML-019-AC03`)

4 - Select All starts checked, and all exported view nodes and edges are active in the visualization datasets before network layout begins. Large source graphs retain the complete, labeled community aggregate and supported display cap; selecting all exported view data does not force raw full-source rendering. The Overview button, top-ten selection mode and reset function are absent. Community filters, search, Select All and Select None retain their selection behavior; the Select All checkbox accurately reflects complete, partial and empty active datasets, including ungrouped nodes. Search restores a filtered result before focusing it. The complete exported metadata remains in the RAW payload, canonical graph data is unchanged, and view choices remain temporary with no added saved camera/filter persistence. Production emitted-script tests exercise checked startup, removal of Overview, filters/search/all/none and payload preservation. (`REQ-QML-019-AC04`)

Status: **AC01–AC04 locally verified at exporter/emitted-script boundaries**.
INC-QML-16 removes the former optional Overview contract and re-verifies the
remaining selection lifecycle, with reviewed installed-artifact proof. Earlier
AC04 startup/Overview results remain
evidence for their own revision and do not verify this removal.
Browser visual inspection, other platform lanes and hosted proof are not claimed
for this revision. Acceptance is limited to
HTML view preparation, selection controls and publication. It does not complete remaining
REQ-QML-018 parser, metadata, provider or whole-project adoption work, and does
not change the canonical graph or require project execution. Assigned work and
exit gates are in [INC-QML-09](qt-qml/PLAN.md#inc-qml-09--readable-large-graph-html-export)
and [INC-QML-16](qt-qml/PLAN.md#inc-qml-16--middle-mouse-navigation-and-overview-removal).

### REQ-QML-020 — Explicit project membership relationships

Accepted project-source and resource-alias declarations link to their canonical
source files or QML components in the graph. Metadata lookup and displayed graph
membership describe the same accepted corpus without expanding it or executing
project code.

**Acceptance Criteria**

1 - Public CMake, qmake and resource fixtures project each supported literal module/source or resource-alias membership through an independent source-owned `membership_resolution` site to the uniquely accepted canonical file/component endpoint. Accepted C++ file endpoints retain their file role with valid bounded producer provenance; callable, class, foreign, malformed or unrelated semantic metadata cannot borrow that role. The declaration contains its site with context `qt_membership_site`; a resolved site references the target with confidence `EXTRACTED` and context `qt_project_source` or `qt_resource_membership`. Direction, module/alias context and original span survive build, JSON reload and scoped query; raw declarations and existing loader/module lookup results remain unchanged. Canonical spelling and real contained input aliases, including Windows short paths and parent-directory aliases, accept the same source declaration and produce identical membership identity/provenance. (`REQ-QML-020-AC01`)

2 - Missing, duplicate, conditional, generated or out-of-root targets retain explicit unresolved/unsupported site status, reason and bounded evidence without a target edge. Same-name files in different scopes remain distinct; graph projection neither reads new files nor evaluates expansions, build hooks or QML. Malformed metadata and failed joins retain existing failure diagnostics and prior durable graph/state; force cannot authorize partial membership publication. Canonical input comparison still rejects a foreign input or conflicting declaration identity; an alias cannot authorize out-of-corpus membership or rewrite stored source facts. (`REQ-QML-020-AC02`)

3 - Source/resource edits, rename, deletion and ambiguity introduction remove stale membership edges; cold, warm and incremental graphs agree and no-change updates are idempotent. Source facts and unrelated-language identities remain stable, and HTML community edges reflect only accepted persisted memberships. Exact automated source, persistence, consumer and failure tests cover each supported form. Canonical and real alias profiles agree through cold/warm extraction, full/manual/watch updates and source removal; repaired retry and no-change repeats preserve accepted output. Existing policy-18 native/Qt products refresh under policy 19 at unchanged package/source versions; a failed upgrade retains prior products and repaired retry/repeat completes the same accepted graph. (`REQ-QML-020-AC03`)

Status: **Implemented bounded profile; full canonical-alias verification remains open**.
The earlier canonical-spelling cases have production, lifecycle/consumer and reviewed installed-artifact
evidence assigned in [traceability](../tests/TRACEABILITY.md#project-membership-projection).
The initial two source/lifecycle suites contribute 37 passing cases to their
recorded reviewed-wheel selection. The INC-QML-39 checkpoint uses Qt policy 18
and AST schema 12; INC-QML-40's accepted compatibility decision advances policy
19 while retaining schema 12, refresh and producer ownership. Raw facts and existing module/resource
lookups remain unchanged; static membership does not establish runtime component
use. Browser, new hosted, other-platform and executable Qt proof are not claimed.
[INC-QML-14](qt-qml/PLAN.md#inc-qml-14--explicit-project-membership-relationships)
owns this additional behavior and its evidence; source containment and viewer
counts do not establish completion.

INC-QML-39 adds canonical input-alias acceptance after a reproduced installed
smoke failure. The frozen broader Qt/QML source profile passes 2,259 cases with
nine symlink-capability skips. A fresh source-identical artifact passes ordinary
QML/core smoke but initially fails a near-root alias through the shared facade;
INC-QML-40 corrects that distinct defect. INC-QML-41 corrects the reproduced
persistent-path diagnostic escape. Fresh ordinary QML/core and actual near-root
alias smoke now pass with source-identical payloads. Current hosted acceptance remains open; earlier
canonical-spelling evidence does not close these expanded contracts.

### REQ-QML-021 — Middle mouse graph navigation

Holding the middle mouse button and dragging pans the displayed graph in both
axes. Wheel scrolling retains its existing zoom behavior. Navigation changes
the temporary camera view while preserving source facts, node positions and
community selection.

**Acceptance Criteria**

1 - A mouse middle-button press inside the graph starts panning. Subsequent movement, including outside the graph while that button remains held, moves the camera by the corresponding screen displacement at the current zoom scale without moving individual nodes or changing zoom itself. Horizontal, vertical and diagonal drags work in source and aggregated views, including consecutive drags and multiple positive zoom scales. Middle-button press/auxiliary click suppress browser autoscroll and unintended node selection. An on-screen hint explains middle-button drag and wheel zoom. Actual emitted-script tests verify camera calls and active datasets. (`REQ-QML-021-AC01`)

2 - Button release, a move reporting the middle button no longer held, pointer cancellation, lost capture, window blur or page exit ends panning and restores the previous cursor and selection behavior. A stale or unrelated pointer cannot continue the gesture. Unavailable or failed pointer capture retains a safe cleanup path. Invalid coordinates, non-positive/non-finite camera scale or position, arithmetic overflow and camera API failures cannot produce an invalid move or leave a stuck gesture; a subsequent valid gesture can start normally. Success, interruption and rejection retain source/selection data and add no persistent state or new parser/publication diagnostic. (`REQ-QML-021-AC02`)

3 - Left-button node selection/drag, right-button behavior, touch gestures, native wheel zoom, search, community filters, Select All/None and the inspector retain their supported behavior. Middle-button movement changes only the camera; no node, edge, source metadata, physics configuration, filter or selection is rewritten. Original graph bytes and exported source payloads remain unchanged. The production exporter, emitted script and reviewed installed artifact exercise the new controls and removal of Overview; unavailable browser appearance or platform checks remain explicit gaps. (`REQ-QML-021-AC03`)

Status: **Implemented; AC01–AC03 locally verified at emitted-script and reviewed
installed-artifact boundaries**. Native browser/device appearance and other-platform
interaction remain unverified; the external DOM/network harness does not establish
those system results. Exact evidence and limitations belong to
[INC-QML-16](qt-qml/PLAN.md#inc-qml-16--middle-mouse-navigation-and-overview-removal)
and traceability.
The existing HTML publication and canonical graph contracts remain authoritative.

## Shared compatibility requirements

### REQ-CORE-001 — Installed assistant contracts

Installed assistant hooks invoke the Graphify CLI through the intended executable
identity. Skill installation, refresh and uninstall honor the existing destination
and content contract of the selected operating-system profile.

**Acceptance Criteria**

1 - A Codex hook installed from an executable path containing spaces reaches that exact executable and passes `hook-check` as the CLI subcommand. Literal path transport preserves executable identity and argument boundaries through the supported consumer shells, with a nonmatching executable rejected by the regression. (`REQ-CORE-001-AC01`)

2 - Hermes and Gemini user installations use their platform-owned destinations and include resolvable skill references. POSIX and Windows profiles use their documented home/data and Gemini/shared-agents locations; project installation retains its separate scope. (`REQ-CORE-001-AC02`)

3 - Refresh writes the correct platform-adapted skill bytes for each uniquely owned stale installed destination and preserves unrelated content. Ambiguous shared Gemini/agents copies retain their bytes and stamp; version checking with automatic refresh disabled reports the actual matching destination/installer. An already current installation is unchanged. Shared-directory ownership isolation remains outside the implemented contract. (`REQ-CORE-001-AC03`)

4 - Uninstall observes the established global/project scope and explicit user-skill opt-in. Protected shared-agent content is retained according to the current platform contract; missing installations remain a safe no-op. (`REQ-CORE-001-AC04`)

5 - Windows user-scope hooks preserve the selected Graphify executable through Cmd and PowerShell argument transports when legal path characters include spaces, operators, apostrophes, dollar signs, backticks and paired percent names. A PATH decoy or environment expansion cannot substitute another executable. Missing selected launchers and launcher failures return failure. A missing, inaccessible or unsafe OS-owned PowerShell executable, or an encoded command exceeding the supported Cmd transport limit, rejects hook installation with a bounded actionable reason before changing existing hook JSON or its backup. Repeated installation and uninstall retain unrelated hooks and recognize the owned command through supported status metadata. Project-scope bare invocation and POSIX literal quoting retain their existing contracts. (`REQ-CORE-001-AC05`)

Status: **Locally Verified for native Windows and destination decision profiles**.
All five criteria have focused source and native consumer evidence; the full
Windows source suite has no failures. Other kernels and actual Codex Desktop
event delivery retain separate system boundaries. INC-CORE-01 and INC-CORE-05
belong to the [compatibility plan](COMPATIBILITY.md#plan-and-acceptance-matrix).

### REQ-CORE-002 — Safe filesystem admission and recovery

Source discovery accepts regular files, rejects nonregular or inaccessible inputs
without blocking, and handles an unavailable working directory through the
existing explicit repository-root recovery contract.

**Acceptance Criteria**

1 - Regular files and supported links to them are accepted; directories, FIFOs, sockets, devices, broken links and stat failures are rejected without opening or executing the input. Real fixtures run where the platform/account can create them; portable mode/error tests supplement, and do not replace, actual filesystem evidence. (`REQ-CORE-002-AC01`)

2 - A missing current directory without an explicit repository root returns failure with the existing diagnostic before queue/lock/graph side effects. A valid explicit repository root restores the working directory and publishes the correct source graph. Failed recovery leaves a clear failure result; simulated OS-failure tests and actual POSIX deleted-directory fixtures retain distinct evidence. (`REQ-CORE-002-AC02`)

3 - Missing-CWD diagnostics distinguish an absent explicit repository root from failure to change to a supplied repository root. A failed supplied root is not described as unset, and diagnostic text does not expose its private absolute path. The failure returns before queue, lock or graph publication and preserves the prior graph bytes. (`REQ-CORE-002-AC03`)

Status: **Native admission/recovery verified; actual POSIX proof pending**. Native Windows
cannot establish real FIFO or deleted-current-directory evidence. The exact
system gaps remain in [compatibility verification](COMPATIBILITY.md#verification-profiles-and-remaining-system-work).

### REQ-CORE-003 — Portable Terraform scope and provenance

Terraform analysis preserves distinct directory-scoped declarations and emits
portable source paths and exact source locations in extracted and saved graphs.

**Acceptance Criteria**

1 - Same-named variables and outputs in four distinct directories, including punctuation-colliding directory spellings, retain distinct identities and exactly the expected references to their own directory's variable. No reference binds another directory's same-named declaration. (`REQ-CORE-003-AC01`)

2 - Original UTF-8 LF and CRLF source bytes produce correct portable source paths, source lines, extracted confidence and directed references through the production facade, graph assembly and JSON save/reload. Existing malformed/dynamic input handling is retained. (`REQ-CORE-003-AC02`)

Status: **Locally Verified for native Windows source/persistence**.
The correction is confined to the test's platform-dependent path expectation.
Exact evidence belongs to [traceability](../tests/TRACEABILITY.md#shared-compatibility-verification).

### REQ-CORE-004 — Hosted compatibility evidence

Hosted validation executes the applicable source and consumer tests with their
required tools and disposable services, preserves the tested revision and
dependencies, and reports failures and exclusions explicitly.

**Acceptance Criteria**

1 - Ubuntu Python 3.10, 3.12, 3.13 and 3.14 jobs execute the full source suite with all frozen extras, a real C preprocessor, Bash/sh, Node and a reviewed wheel input. A disposable pinned FalkorDB service admits graph commands before its persistence/idempotency tests run. Missing tools or the wrong service fail readiness; they cannot establish passing acceptance through skips. Real POSIX object, permission and deleted-directory fixtures execute where applicable. (`REQ-CORE-004-AC01`)

2 - A Windows Python 3.12 job executes the assigned native hook, installer, filesystem recovery, Terraform and emitted-script regressions with real Cmd/Windows PowerShell, Git Bash/sh and Node 24.19.0. Application resolution selects the first executable in the configured PATH even when multiple applications match; the selected Node version must be 24.19.0. Bash forwards to the selected Python interpreter; PATH cannot substitute a global Graphify or invoke an installation fallback. Tool preflight fails before collection when a required consumer is unavailable. POSIX-only exclusions retain their separate Linux assignment. (`REQ-CORE-004-AC02`)

3 - Source jobs retain the workflow/event/ref, PR source head and base, actual checkout SHA, interpreter/tool/dependency versions, pytest exit, JUnit outcomes and skip reasons. Tests preserve the checkout, tracked source/configuration and installed dependency identities. Failed pytest remains a failed job when evidence/integrity steps run; unavailable evidence is reported explicitly. Disposable test graphs and the job-owned service are removed with confirmed cleanup; failed or unconfirmed cleanup cannot establish acceptance. Fake SDK providers and public fixtures supply test data without credentials or private corpus inputs. (`REQ-CORE-004-AC03`)

4 - The established push/PR/dispatch triggers and existing required/advisory gate policies remain intact. One PR event owns its validation; no equivalent full feature-push dispatch is added. Obsolete PR revisions can cancel their own workflow runs, while default-branch and explicit recovery runs retain distinct groups and cannot be cancelled by a later PR revision. Jobs use read-only repository permissions. (`REQ-CORE-004-AC04`)

Status: **Implemented configuration; complete hosted execution unverified**. INC-CORE-06/07 in
the [compatibility plan](COMPATIBILITY.md#plan-and-acceptance-matrix) owns readiness,
workflow validation, publication and exact-revision evidence. Local passing
tests and configuration checks do not establish hosted acceptance.
