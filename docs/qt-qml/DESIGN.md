# Qt/QML implementation contracts

Status: INC-QML-00 through INC-QML-07 are implemented and verified for the bounded
static profile, with revision-specific hosted source/artifact proof.
Earlier INC-QML-09 HTML selection is locally verified at exporter/CLI and emitted-
script boundaries for its recorded revision. INC-QML-16 changes REQ-QML-019-AC04
and adds camera navigation under REQ-QML-021; those current contracts have local
emitted-script and reviewed installed-artifact proof. Native browser/device,
other-platform and new hosted behavior remains unverified.
[PLATFORM_MATRIX.md](PLATFORM_MATRIX.md) records declared installation lanes.
[ARCHITECTURE.md](ARCHITECTURE.md) owns ADRs and
[traceability](../../tests/TRACEABILITY.md) owns individual acceptance evidence.
Dependency-directed cache optimization and Qt runtime equivalence remain deferred.
INC-QML-10 native ownership corrections, including accepted-context source/span
deduplication, pass local source, final broad and reviewed installed-artifact checks.
INC-QML-11 inherited-signal ancestor
lookup remains planned; initial profile evidence does not verify that case.
INC-QML-12 constructor source proof and INC-QML-13 source containment/view counts
are implemented with local source and reviewed installed-artifact validation. Missing constructor class proof
cannot be supplied by a same-name header prototype; source containment alone
does not establish a native endpoint.
INC-QML-14 membership projection is locally complete and REQ-QML-020 is Verified
within the bounded static profile with policy 6/schema 7. INC-QML-15 remains planned.

## Ownership and dependency direction

Detection owns corpus inclusion. The QML extractor consumes an already accepted
source file and returns source-local facts. A Qt project index consumes accepted
metadata and C++ facts. The Qt/QML resolver joins those facts after extraction;
it does not rescan ignored directories or reinterpret corpus boundaries.
The graph builder and persistence pipeline remain authoritative for output.

New responsibilities should normally live under `graphify/extractors/` or focused
resolver modules, with thin registration calls in existing large modules. Avoid
moving unrelated language code as part of a feature PR.

Current mutable ownership is explicit: `FactBuilder` owns one source's facts;
module/scope indexes own lookup tables for one run and borrow declarations
read-only; the relationship pass updates fresh source-owned expression sites;
the writer owns durable publication. Unchanged context dictionaries are never
updated by a join. The index API has a read-only lookup contract, without ambient
project state or filesystem discovery.

## Source-local extraction contract

Use the established extractor result envelope (`nodes`, `edges`, and existing
diagnostic conventions). Additional resolution facts must be explicitly carried
through per-file results, cache serialization, path normalization, merging, and
incremental reconstruction before they influence persisted output.

Each fact needs a canonical root-relative source path, a source span, an owning
component/object scope, its literal syntax, and parser/version provenance where
that affects interpretation. Line-number conventions must match existing consumers;
validate column/byte offsets against UTF-8 and multiline fixtures.

Identity must distinguish a file component, each object instance, members, inline
components, and names declared in separate module/version scopes. An anonymous
object can use a documented syntactic scope path; document whether moving it
changes its identity. Never key instances globally by `id: root` or type label.

Do not treat a grouped property block as an object instance, a handler as a new
signal declaration, a string/comment as syntax, or a partial parse as an empty
successful extraction. Bindings retain a bounded expression span and references;
analysis never evaluates them.

Implemented fields live in `metadata.qml` with `contract_version=1`. Each import,
declaration, expression occurrence and metadata record is an independent node,
so the 50-item metadata list cap cannot discard required per-file records.
Names and literal paths are case-sensitive lookup values. IDs use the complete
root-relative filename and an exact-identity digest before normalizing with
Graphify's ID utility; component/object scope keys are fixed-width hashes.
Named declaration IDs survive line insertions, while expression-site IDs include
their source occurrence and can change when text moves.

`qml_facts.encode_metadata` adds bounded base64 `raw_values` companions for string
fields. `qml_facts.qml_metadata` returns decoded lookup values after HTML sanitation
or JSON reload; callers do not parse escaped display text. It rejects nonmapping,
over-50-field, nonstring, invalid base64/UTF-8 or over-512-encoded-byte transport.
The display metadata is not a second resolver owner. Malformed transport becomes
analysis failure/publication rejection; it cannot silently select a different name.

## Resolution contract

Build indexes from explicit module/type declarations, supported project metadata,
documented implicit directory visibility, and configured import roots. Track
alias, version, singleton, registration, and object/component scope separately.

Resolution returns one of resolved, ambiguous, external/unavailable, dynamic, or
unsupported. Only one valid visible candidate may produce a resolved endpoint.
Ambiguous and dynamic candidates keep evidence and a reason instead of an
arbitrary edge. A label match across the repository is insufficient.

The default analysis uses source and metadata already in the accepted corpus.
Optional SDK import paths or generated `.qmltypes` need an explicit configuration,
provenance, root/ignore policy, and version. Do not scan the machine's Qt installation
implicitly or infer exposure solely from C++ inheritance or `Q_OBJECT`.

Implemented entry points:

| Interface | Input/output and owner |
| --- | --- |
| `extract_qml(path, *, root=None)` | One accepted QML source to declarations/expression facts, edges and diagnostics; no cross-file lookup |
| `extract_qmldir(path, *, root=None)` | One accepted literal manifest to independently owned module/export/import/dependency records |
| `build_qml_index(nodes, edges, *, root, import_roots=None, native_index=None, project_index=None)` | Per-run `QmlProjectIndex`; accepted source paths and declaration/provider tables only |
| `resolve_type(file, component_key, name)` | Qualified/document-local type lookup; `Resolution(status, target_id, reason, evidence, candidates)` |
| `resolve_member(file, component_key, object_scope_key, name, *, lexical_names=())` | Component IDs, own/root/known inherited members and typed continuations; no global labels |
| `follow_member(target_id, parts)` | Continue a proven object or typed-property target; alias chasing belongs to `RelationshipLookup` |
| `module_script(...)`, `directory_script(...)` | Script namespaces use a separate role from object types |
| `resolve_qml_project(per_file, all_nodes, all_edges, *, root, import_roots=None, native_index=None, project_index=None)` | Append fresh source-owned import/type sites and resolved edges; do not modify borrowed context |
| `collect_qml_scripts(paths, per_file, *, root)` | Add QML-owned overlays only for admitted, referenced scripts and admitted literal dependencies |
| `resolve_qml_relationships(per_file, all_nodes, all_edges, *, root, import_roots=None, native_index=None, project_index=None)` | Update fresh read/call/alias/handler status, append compatible inferred target edges |

Import roots default to the explicit scan root. CLI/watch and generated assistant
AST guidance inspect the ordered project-relative `GRAPHIFY_QML_IMPORT_ROOTS`
JSON list and pass it explicitly through `extract` to the index. Direct API callers
pass `qml_import_roots`; they do not inherit that environment setting implicitly.
Ambient SDK paths and remote imports are excluded. Current layouts include unversioned providers and explicitly requested
`.major`/`.major.minor` directories. An observed available manifest version precedes
selection of the latest compatible type export. URI aliases stay document-local;
`qmldir import` adds visibility while `depends` does not. Internal/singleton checks,
missing versions and duplicate eligible targets retain explicit reasons. `prefer`
resource redirection remains unsupported by the `qmldir` resolver. The separate
Qt resource index resolves accepted literal QRC/CMake URL mappings.

`qmldir` is capped at 1 MiB/10,000 meaningful records. Lookup caps include 32 module,
inheritance or alias depth, 32 parts per member-continuation API call, 256-character
collected reference paths, 1,024 module-query steps and 50 candidate/evidence
entries. Truncated candidate lists are display summaries, never permission to
choose a winner.

Expression resolution respects parameters, block/catch/loop locals and hoisted
`var`; a per-use shadow flag remains authoritative if lexical display names are
capped. Reassigned local callables and computed targets remain dynamic. Pure
assignment destinations are not reads, but computing receiver/index addresses
and augmented assignment retains dependencies. Alias chains/cycles use bounded
lookup and never evaluate property getters. Current `this` denotes the source
owner; `parent` requires explicit static-parent evidence.

Name-based `Component`, `delegate` and `sourceComponent` barriers conservatively
separate body IDs. They do not prove a Qt runtime creation context or model roles,
and custom names can therefore be conservatively unresolved. Attached handlers
and runtime-selected `Connections.target` remain unresolved. For supported
`Connections`, mixed legacy/function styles mark function-style handlers ignored;
property change handlers get distinct inferred notify-signal facts.

Classic JS directive masking preserves byte positions. Supported `.mjs` exports
control importer visibility; unsupported re-exports do not expose matching local
functions accidentally. QML-owned script overlays have distinct identities from
generic JS declarations, and shared scripts gain no arbitrary QML importer's ID
namespace. Overlay parsing is bounded at 5 MB/100,000 AST nodes/depth 256 and 256
enriched files. No build tool, script, getter or Qt engine is executed.

## Graph projection and compatibility

Project accepted facts into existing node/file types and relation/context fields
where their semantics fit. Cross-file resolution remains inference unless the
existing evidence rules justify an extracted relation. Preserve the literal
reference's source span and the definition's provenance separately.

The baseline builder uses simple graphs. Before bindings and signals share
endpoints, establish a nonlossy representation for distinct facts and confirm
JSON/export/query round trips. A global migration to a multigraph is a separate
architecture decision; it must not be smuggled into a language-parser PR.

The implemented projection uses one source-owned node per occurrence. Declaration
containment is `EXTRACTED`; resolved site-to-target edges are `INFERRED`. Actual
contexts are `qml_import_resolution`, `qml_type_resolution`, `qml_binding_read`,
`qml_alias_target`, `qml_signal_subscription`, `qml_property_notify_signal`,
`qml_signal_emit`, `qml_js_call` and `qml_script_call`. Reads use `uses`, aliases
and subscriptions use `references`, and proven function calls use `calls`.
Signal emission uses a dependency to its declaration and does not invent a
synchronous call to handlers. Status/reason/evidence on unresolved sites remains
queryable without a guessed endpoint.

`qml_projection.allows_qml_script_edge` admits only the dedicated typed QML script
exception through the existing cross-language guard: import proof names the exact
accepted script file/path/role, and calls target QML script-function overlays.
Generic JS callers and unrelated C++ edges keep their existing rules. On reload
of an undirected graph, `load_node_link_graph` restores QML edge `_src`/`_tgt`
from serialized endpoints; consumer direction uses these values, not iteration
order. Build/JSON preservation does not establish all INC-QML-07 presentation support.

Any new fields need compatible defaults, serialization tests, and a cache/version
decision. Remapping IDs must also remap resolver-fact keys, references, and provider
indexes, not just node IDs and edge endpoints.

## Qt events and bidirectional object boundaries

REQ-QML-008 supplies the registered C++ surface to QML. REQ-QML-016 adds native C++
signal/slot semantics independently of the QML parser. REQ-QML-017 follows C++
consumers of QML objects and literal context/initial-property providers back to
their scoped declarations. These are implemented bounded source contracts,
with acceptance evidence and remaining consumer/release gates in traceability.

Retain source-owned emission, connection, disconnect, load, lookup and member
access sites. Existing `contains`, `uses` and `references` relations project
their endpoints; `metadata.qt` retains endpoint roles, signatures, conditions,
declared connection flags, source spans and `bridge_direction`. The implemented
collectors/resolvers retain their exact per-role contexts; `qt_signal_emit`,
`qt_connect_signal` and `qt_cpp_qml_invoke` are examples. Source-owned sites and
endpoint-role nodes distinguish connect, disconnect, load, lookup, property
read/write and provider exposure through the existing simple graph.

An emission refers to a declared signal. A connection refers to its sender signal
and receiver callable/signal, with a separate context object for functors when
supplied. Direct slot calls and calls inside a connected lambda remain ordinary
calls. Do not turn event propagation into caller-to-slot `calls` edges. Support
member pointers, compatible ordinary C++ receiver members, overload selectors,
signal-to-signal, lambdas/functors and legacy `SIGNAL`/`SLOT` signatures only with
source/type evidence. Private slots can be meta-object connection endpoints even
though direct invocation follows C++ access rules. That does not automatically
make private slots a QML API. Preserve declared Auto/Direct/Queued and other
flags without claiming runtime thread affinity, registration success or delivery
order; retain the documented UniqueConnection limitation for functor targets.
See [Qt signals and slots](https://doc.qt.io/qt-6.8/signalsandslots.html) and
[QObject connections](https://doc.qt.io/qt-6.8/qobject.html#connect).

Reverse lookup requires a bounded provenance chain: supported literal loader,
same engine/component/view, uniquely identified root or created object, optional
literal objectName lookup, then a declared member/signature. Initial profiles
cover engine `load`/`loadFromModule` with `rootObjects`, component loading/creation,
and QQuickView `setSource` with `rootObject`. Relative URLs need a known URL base;
they are not automatically relative to C++ source. A QML `id` is not a findChild
objectName. Duplicate names/roots, pointer escape/reassignment and computed names
remain unresolved or conditional. Property read/write and meta-object invocation
retain API variant and access direction; invocation is dispatch evidence rather
than proof of synchronous execution. A declared QML signal connects to C++ using
the same connection-site contract. See
[C++ interaction with QML](https://doc.qt.io/qt-6.8/qtqml-cppintegration-interactqmlfromcpp.html)
and [QQuickView](https://doc.qt.io/qt-6.8/qquickview.html).

Literal setContextProperty, typed setContextObject and named initial-property maps
retain the provider and receiving context/component. Respect known explicit
property precedence and context boundaries. They cannot add a repository-global
name. Arbitrary provider dataflow and runtime replacement stay deferred. Both
directions and native event facts must survive simple graph projection and
consumer output; changed QML APIs must invalidate unchanged C++ consumers.

## Incremental lifecycle and failures

QML and Qt metadata extraction bypass AST cache reads and writes. A Qt analysis
context also bypasses native syntax cache; plain C++ retains portable syntax
caching. Generic JS retains its existing cache-bypass rules, and QML overlays are
constructed for the current run. INC-QML-06 refreshes the accepted code corpus after
provider/script/source changes and parser/import/admission-configuration changes.
Dependency-directed reuse is a later optimization, not a completion prerequisite.

`require_complete_qml` rejects failed, partial or omitted source contributions and
script/join failure markers before graph reconciliation and publication, including
force/partial-output requests. Prior graph/manifest/report output bytes remain
intact. Unsupported subfolder scoped-ID rebasing is rejected separately. Earlier
scan/stat bookkeeping is outside the durable-output guard. See [ERRORS.md](ERRORS.md)
for diagnostic ownership and recovery, rather than treating unresolved coverage
as parser/write failure.

File-content hashes alone cannot validate links dependent on module manifests,
C++ registrations, resource aliases, import configuration, or parser upgrades.
The analysis checkpoint covers installed parser/package versions, Qt fact/policy
versions, ordered roots, accepted paths, ignore files and caller exclusions.
Changed providers/configuration trigger fresh resolution even without a QML edit.

The implemented fallback rebuilds already accepted inputs and removes stale
derived facts after deletion, rename, duplicate-provider or ignore changes.
It never rereads deleted/ignored inputs or expands configured lookup roots.
An unavailable parser cannot create a successful empty cache entry. The checkpoint
is committed only after graph/manifest publication; failed analysis preserves
prior graph/manifest/checkpoint bytes. Unsupported scoped subfolder rebases reject
before publication. Dependency-directed optimization must preserve these contracts.

## Verification boundaries

Test production extractor, resolver, build, serialization, update, and consumer
interfaces. Fixture output must be hand-checked against source facts, not generated
from the implementation under test. Compare normalized output across cold/warm,
full/incremental, relative/absolute, and Windows/POSIX cases.

Each feature increment updates [requirements](../REQUIREMENTS.md),
[traceability](../../tests/TRACEABILITY.md), support documentation, and any changed
design decisions in the same PR. Dynamic object creation, arbitrary plugin code,
full preprocessing, and arbitrary build-script evaluation remain explicit limits.


<a name="implemented-native-qt-contracts-qml-04"></a>

## Implemented native Qt contracts (INC-QML-04)

`qt_qml_pipeline.resolve_qt_qml` owns scratch integration after final generic C++
canonicalization. Exposure, events and object access have focused collectors and
per-run indexes. Every native fact uses recursive, bounded raw semantic transport;
malformed or oversized transport fails rather than becoming a guessed endpoint.
All target IDs refer to accepted canonical declarations or independent owned facts.

Native emissions use `uses`/`qt_signal_emit`. Connection/disconnection endpoint
roles use `references` and their own source sites. Reflective QML method intent
uses `calls`/`qt_cpp_qml_invoke` only for an evidenced declared function; the distinct
context and `operation=invokeMethod` retain its reflective mechanism. This category
records source intent and does not assert successful runtime invocation or delivery.
Qt connection flags and conditional registration are source configuration evidence.

Literal loader URLs establish source components; source-local handles model
roots and objectName lookup. QML id is never an objectName. The follow-up audit
found that reflective member lookup can fall back to the QML root, child lookup
can cross the receiver subtree, and distinct same-named engines can share a
provider. Those cases are incorrect and remain unresolved correction work in
INC-QML-17/18. Earlier scoped-provider fixtures do not prove these boundaries.
Duplicate exposures retain uncertainty. All joins borrow prior corpus dictionaries
read-only. `qml_failures` and `qt_failures` both enter the publication integrity gate.
No force/partial option can publish an incomplete Qt overlay.
That integrity gate rejects recorded analysis failures; it does not detect a
semantically incorrect target labeled resolved. The independent persisted-edge
probes in [FOLLOWUP_AUDIT.md](FOLLOWUP_AUDIT.md) cover that distinction.


INC-QML-05 activates the internally packaged metadata readers at discovery/dispatch.
After native overlays borrow final C++ IDs, QtProjectIndex supplies real source
membership to QtQmlBridgeIndex and both QML resolvers. Resource aliases resolve
only accepted targets. Generated/source disagreements attach to the fresh source
result as warnings; partial metadata participates in the publication failure gate.
Versioned Qt/QML namespace-shaped facts bypass generic C# namespace merging,
retaining distinct provider and repeated resource identities.


INC-QML-06 owners: qt_incremental computes accepted-input refresh/cache policy without
scanning directories; qt_analysis_state inspects accepted ancestors and produces a
frozen checkpoint. CLI/watch own successful publication and checkpoint commit.
Each parallel worker receives native-cache bypass explicitly; no mutable global
root or policy is introduced. Borrowed context facts remain read-only. Native Qt
scoped facts reject subfolder path-only rebasing; callers update the project root.

<a name="qml-07-consumer-and-assistant-contracts"></a>

## INC-QML-07 consumer and assistant contracts

Search projects bounded decoded semantic fields under `graphify_qt_qml` rather
than assuming nested metadata is searchable. Query/explain/path and installed MCP
consume the same source-scoped persisted facts; logical endpoint direction survives
default undirected JSON reload. Affected traversal promotes source-owned sites
through current source-owned containment, respecting the selected dependency
relation. Normally owner, site and containment fact share a source file. A
canonical C++ header declaration may own an implementation site only when its
accepted `definition_file` matches that site's file, the declaration is callable,
and extracted Qt containment proves the exact owner ID, child endpoint and
original span. A foreign file or unproven definition cannot establish ownership.
Emission/connection evidence remains distinct from ordinary direct calls.

HTML exposes source/event/access evidence and uncertainty; coverage counts
unresolved sites separately from resolved-edge confidence. JSON is the canonical
semantic backup. Other formats have individual retention/omission contracts in
[EXPORT_MATRIX.md](EXPORT_MATRIX.md), including undirected GraphML direction loss
and presentation-only Canvas/Obsidian/SVG limits. Driver payload tests do not prove
live database insertion/readback or stale-record cleanup.

Generated assistant extraction reads the trusted root and inspects configuration
without writing state. It passes `qml_import_roots` and `refresh_native` explicitly,
then calls the production integrity gate before AST JSON publication. CLI/watch
alone own the final analysis checkpoint. Authoritative fragments and frozen
generator guards are validated together; artifacts are regenerated rather than
edited independently. Hosted proof must be rerun for the final INC-QML-07 head.

## Valid native syntax recovery during adoption

`extractors/qt_cpp_syntax.py` retains original source/lexical views and delegates
only the recovery parse view to `extractors/qt_cpp_compat.py`. The caller supplies
its bounded parser and iterative traversal; the helper owns no roots, files,
mutable state, cache or persistence. An AST-confirmed empty parameter default is
omitted only in the equal-length parse view. A standalone Qt `Q_UNUSED` statement
uses the macro's existing bytes for its void cast and supplied semicolon while
preserving evaluated argument/call bytes. Original facts, declaration types and
locations still use the original source. Comments, strings, directives, local
macro overrides, ordinary declared/qualified functions, value contexts and
malformed controls cannot authorize recovery. This corrects supported syntax;
it does not relax the graph integrity guard or infer runtime targets.

The lexical owner recognizes C++ preprocessing-number tokens before quote
masking. Numeric digit separators therefore cannot obscure later Qt annotations
or signal sections. Numeric bytes remain unchanged and the parser validates their
syntax; malformed separators do not acquire a successful recovery. Character,
string, raw-string and comment exclusion retain their existing ownership.

The same-version development upgrade uses a new AST cache schema and Qt policy
epoch to prevent reuse of pre-correction declarations/graphs. Conservative native
refresh relevance includes the accepted syntax candidates; unrelated plain C++
keeps its portable cache behavior. Epoch/schema migration invalidates obsolete
AST artifacts under upstream cache ownership; compatible current cache data,
semantic cache and prior accepted graph/manifest/state remain protected on a
failed candidate. The graph writer still commits analysis state after successful
publication. See the exact regression/evidence inventory in IMPLEMENTATION.md.

## HTML community-view ownership

`exporters/html_communities.py` validates complete, disjoint membership for a
large aggregate view. Missing or invalid presentation grouping is recovered on
an export-local graph copy through the existing clustering interface. It fills
missing labels through the existing hub labeler and discards labels tied to a
replaced partition. Small full-node views preserve their existing membership.
Neither grouping recovery nor HTML export changes canonical source facts,
analysis sidecars or graph JSON. The atomic writer retains the previous HTML
until successful replacement; CLI status reflects actual publication.

The HTML viewer starts with Select All checked and all exported view nodes and
edges active in its datasets before layout. Large graphs keep their complete
labeled community aggregate and supported cap; startup selection does not
replace that view with raw full-source rendering. INC-QML-16 removes the Overview
button, its reset function/state and ten-community ranking. Community filters,
search, Select All and Select None keep their existing selection roles. Full exported semantic
payloads remain in the artifact. Community names describe structural hubs;
canonical architecture and design documents retain intentional component
ownership. View selections, camera and search are temporary browser state, with
no saved-view persistence. Earlier checked-default/Overview AC04 proof belongs to
its prior revision; current removal/coexistence checks pass at emitted-script and
reviewed installed-artifact boundaries. [Earlier selection proof](VALIDATION.md#inc-qml-09-current-selection-policy)
and [current removal/navigation proof](VALIDATION.md#inc-qml-16-middle-mouse-navigation-and-overview-removal)
retain their revision boundaries. Native browser/device and other-platform/hosted
checks remain separate unexecuted evidence.

## Native ownership authority (INC-QML-10)

The correction adds `is_definition` to version-1 Qt class facts, derived solely
from the parsed class/struct body's presence. Forward declarations remain owned
facts with their existing canonical IDs and spans; they do not supply complete
class authority to out-of-line binding or native event type lookup. The mapper
and event index require a unique accepted complete definition, preserve ambiguity
between distinct complete definitions, and leave forward-only or unsupported
evidence unresolved. The flag does not establish QML exposure or a runtime object.

`qt_cpp_mapping.CppMapping` maps out-of-line methods using their exact accepted
canonical `definition_file` and `definition_location`, original source span,
callable identity and class-containment evidence. Header provenance remains the
declaration owner; the implementation owns its emitted/access source sites.
These two locations are complementary evidence, not permission to bind a method
in any matching file or namespace. Do not delete forward declarations, merge IDs
by label, relax signature/owner checks or fabricate calls to remove isolated nodes.

`qt_cpp_exposure` transports definition authority and carries it through global
binding; `qt_event_index` consumes it when establishing class-qualified endpoints.
Borrowed complete-class records also transport the producer's exact `source_file`
and original `span`. A fresh AST record and an accepted unchanged-context fact
for one canonical body share that identity and count as one definition. Copying
only ID/name/definition authority loses the body key and creates false ambiguity.
Inputs stay read-only; deduplication cannot merge distinct body locations or
compensate for missing provenance by a name guess.
Indexes remain per-run and borrowed canonical nodes remain unchanged. At the
INC-QML-10 snapshot, Qt policy epoch 3 forced same-package analysis refresh for
old ownership facts and AST cache schema remained 6. INC-QML-12/13 subsequently
use policy 5/schema 7 with the same graph/manifest/checkpoint publication ordering.
Direct/pipeline/build/reload context and ownership tests pass locally. This
internal body-identity transport correction changes no persisted fact contract;
policy epoch 3 and AST schema 6 were appropriate for that revision. Final broad and reviewed
installed-artifact proof passes locally; see
[INC-QML-10 validation](VALIDATION.md#inc-qml-10-native-source-ownership).

## Planned inherited-signal lookup (INC-QML-11)

Current event type compatibility traverses ancestors recursively, but inherited
member lookup considers only immediate bases. The planned correction extends
endpoint lookup over accepted complete definitions while retaining exact
canonical member identity and existing role/signature/access/ambiguity checks.
Traversal must be bounded and cycle-safe; repeated paths cannot invent distinct
declarations or hide conflicting ancestor members. No mutable project state or
new runtime owner is introduced. Actual grandparent-signal source, persistence,
consumer and incremental proof remains unexecuted; the
[INC-QML-11 plan](PLAN.md#inc-qml-11--inherited-qt-signal-endpoint-lookup) owns scope
and exit conditions.

## Constructor source proof (INC-QML-12)

The generic C++ producer augments constructor prototypes that tree-sitter emits
as class-body `declaration` nodes. `cpp_constructors.py` owns bounded exact
qualified names, original-byte spans, normalized parameter-type signature hashes
and ambiguity. `metadata.cpp_class` version 1 records complete-body authority;
`metadata.cpp_constructor` version 1 records declaration/definition identity and
class-binding outcome. Literal names use bounded base64 transport so display
sanitation cannot alter identity. No native Qt role or runtime object is implied.

The engine hook runs only for accepted C++ inputs; the existing declaration/
definition canonicalization calls the focused binder before its normal merge.
A unique complete class, matching unambiguous constructor prototype, exact scope,
signature and accepted source-backed method containment authorize a class join.
Supported singleton definition IDs are retained; missing header prototypes use
the existing ID formula. Unsupported overload collisions can use the baseline
ID disambiguation path and do not establish distinct overload identity.
Qualified namespace definitions need not merge into a differently
keyed header symbol. Both accepted identities retain their own provenance.

Collapsed overloads, missing/malformed facts, foreign scope, mismatched signatures
or conflicting owners cannot authorize a class join. Signature normalization
retains word boundaries, excludes parameter names/defaults and does not resolve
aliases or compiler conversions. Unsupported delegation/overload cases remain
unknown rather than gaining a guessed class. `constructor_class_authorized`
allows consumers to reject class authority without losing an independently
accepted source callable.

Native mapping consumes the exact body candidate and this guard. An unbound or
legacy out-of-line constructor cannot be replaced with a same-name header
prototype. Its source callable may contain observed sites, but `this` cannot
acquire a native type from that spelling alone. Independently typed local
handles and literal QML access retain their own evidence.

## Source containment and aggregate counters (INC-QML-13)

`qt_cpp_exposure._class_facts` keeps accepted class containment first. Without
Qt class authority, a member occurrence may instead be contained by its uniquely
resolved canonical callable; a local class occurrence may be contained by its
accepted enclosing callable. The fallback requires an actual callable node,
never a class-like target or global label. Class IDs, native roles and unresolved
class status remain unchanged. Unknown/conflicting callable evidence adds no
link. Borrowed nodes and edges remain immutable.

`qt_source_containment.attach_qt_file_sites` adds file-to-occurrence `contains`
edges with context `qt_source_file` when callable ownership remains unknown.
It reuses a unique accepted code file node with exact in-root path, filename
label, L1 location and no callable/class/semantic role. Fresh AST identities
are supplied explicitly before final facade tagging; borrowed context requires
its persisted AST marker. Duplicate, foreign or unmarked borrowed candidates
fail closed. Original spans and endpoint direction survive publication. File
context does not populate `owner_id`, class identity or semantic resolution.

The HTML aggregate counts each canonical source-graph edge once as internal to
a community or external at both incident communities. Distinct neighboring
communities remain a separate count. Canonical self-loops and parallel/directed
edges are counted as represented by the input graph; serialized duplicate
occurrences are not additional edges. Counts add no aggregate self-loops or
synthetic relationships. The inspector distinguishes closed connected groups
from actual isolates. A pre-aggregated caller without source counters displays
unavailable counts; ordinary source-node Degree and Select All remain unchanged.

The reviewed INC-QML-12/13 artifact uses AST cache schema 7 to retire older C++
producer facts at the same package version. Its Qt policy epoch 5 invalidates
derived constructor/source-ownership facts, including
the intermediate policy-4 analysis produced before source-file containment.
Graph/manifest/checkpoint persistence owners and publication order are unchanged.
INC-QML-14 subsequently uses Qt policy 6 with schema 7; this earlier artifact's
proof remains tied to its constructor/source-containment revision.
Migration discards incompatible AST cache entries; failed analysis retains prior
graph/manifest/root/Qt state and requires a corrected retry. This is different
from promising incompatible old-cache retention.

### Legacy file cohesion exceptions

Inherited dependency exception: `graphify/extractors/markdown.py::_active_scan_root`
imports the extraction facade and reads `_XAML_ACTIVE_EXTRACT_ROOT`, unchanged
from imported `0b60d47`. Owner: Markdown extractor maintainer; permitted scope is
that existing helper only, with no new consumers or ambient state. Exit: a separate
characterized refactor passes scan root explicitly while preserving vault-link
fallback, cache lifetime, direct-extractor behavior and parallel-worker semantics.
Review this exception before changes to either owner; it does not apply to Qt/QML
extractors or authorize facade imports elsewhere.

| Owner/file | Current measured size / permitted ceiling | Rationale and extraction exit |
| --- | --- | --- |
| HTML exporter maintainer: `exporters/html.py` | 789 / 810 physical lines | Existing embedded template and recursive aggregate projection share serialization. INC-QML-16 removes Overview and injects the isolated camera helper through a narrow seam, retaining this ceiling. Extract aggregate projection or template responsibility in a separate characterized viewer increment when the next cohesive change requires it. |
| Generic extractor maintainer: `extractors/engine.py` | 7694 / 7700 | Five-line constructor producer hook only; domain logic belongs to `cpp_constructors.py`. Continue the upstream mechanical migration sequencing rather than mixing unrelated language moves into this fix. |
| Generic resolver maintainer: `extractors/resolution.py` | 3974 / 3980 | Six-line pre-merge/guard hook only; the helper owns constructor decisions. Extract the existing declaration/definition responsibility as a separate characterized increment when upstream sequencing permits. |
| Cache maintainer: `cache.py` | 1782 / 1783 physical lines | Schema constant/comment changes only; cache ownership and migration ordering stay intact. No responsibility extraction is needed for this epoch update. |
| Export/Qt integration test maintainers: `tests/test_export.py` | 1377 / 1377 physical lines | INC-QML-16 adds listener registration to the existing inspector harness without dispatch, camera math, swallowed errors or changed inspector assertions. New behavior stays in the focused navigation suite. Exit through coordinated upstream inspector-harness extraction that preserves production-script assertions. |

New handwritten constructor/source-link/viewer modules and tests must remain
below 300 lines. Verification measurements and any remaining platform/system
gaps belong to VALIDATION.md and tests/TRACEABILITY.md.

## Metadata membership projection (INC-QML-14)

Status: **Locally complete; Verified within the bounded static source profile**.
QtProjectIndex resolves accepted
source/resource literals for module/load/access lookup. The additional projection
reuses those accepted facts and canonical endpoints rather than reading a declared
path or evaluating a build condition. Functioning lookup and truthful internal
community counts do not establish this new acceptance evidence.
Architecture decision [D15](ARCHITECTURE.md#d15--project-membership-is-independent-of-component-use)
separates membership from component use and Qt runtime behavior.

`qt_project_membership.resolve_project_memberships(results, nodes, edges, *, root,
project_index, fresh_ast_ids=())` owns the derived joins after canonical source
identities exist. It returns `(derived_nodes, derived_edges)` and replaces only
its own scratch/per-file site mechanisms; borrowed declaration/context dictionaries
remain immutable. The pipeline publishes through starting node identities and
edge-object identities, explicitly including fresh same-ID membership replacements.
Replacing a borrowed site cannot shift append offsets or publish unrelated context.
The helper and its focused test
module stay below 300 physical lines. Reader syntax, corpus admission, existing
indexes and graph persistence remain in their existing owners.

Each declaration owns an independent `metadata.qml` contract-version-1
`membership_resolution` site. Its bounded fields include `declaration_id`,
`declaration_kind`, original `span`, `source_kind`, `module_key`, resource alias or
logical URL context, `status`, `reason`, `evidence` and `candidates`. Evidence and
candidates each retain at most 50 IDs. A resolved site also records `target_id`.
Site identity is deterministic for the same accepted declaration/input and does
not depend on an absolute checkout path. It retains the declaration's source
provenance without changing the raw declaration's metadata.

| Logical edge | Relation / context / confidence | Authority |
| --- | --- | --- |
| Declaration to membership site | `contains` / `qt_membership_site` / `EXTRACTED` | The accepted declaration owns this observed membership attempt |
| Resolved build-source site to file/component | `references` / `qt_project_source` / `EXTRACTED` | Supported literal source membership establishes a unique accepted canonical endpoint |
| Resolved resource-alias site to file/component | `references` / `qt_resource_membership` / `EXTRACTED` | Supported literal alias/path evidence establishes a unique accepted canonical endpoint |

Separate sites prevent repeated declarations and parallel source/resource
mechanisms from collapsing in the existing graph representation. Preserve typed
logical endpoints and original source locations through default-undirected and
directed build/JSON transport. A published source reference establishes static
membership, not a runtime import, QObject relationship or architectural module.

Missing, duplicate, conditional, generated or out-of-root targets retain explicit
unresolved/unsupported site status and bounded reason/evidence without a target
edge. The helper does not open a file, expand the corpus, run a build/QML/plugin,
or choose by filename label. Existing module/resource/loader lookup results are
unchanged. Ordinary coverage follows `QML-RESOLVE-001` semantics; invalid transport
or an unexpected join failure propagates into the existing
`QML_RESOLUTION_FAILED` publication guard rather than adding a second writer.

Qt policy epoch is 6; AST cache schema remains 7. Refresh derives new
membership sites from accepted inputs at the same package version and retires
stale target edges after source/resource edits or removal. Existing publication
ordering retains graph/manifest/root/Qt state on genuine failure even under force;
corrected retry and no-change repeat use the normal lifecycle. These migration,
production consumer and reviewed installed-artifact outcomes pass locally; exact
evidence is recorded in [validation](VALIDATION.md#inc-qml-14-membership-projection)
and [traceability](../../tests/TRACEABILITY.md#project-membership-projection).
The helper/source-test/pipeline/lifecycle-test owners are 187/283/85/267 physical
lines, respectively, all below the 300-line handwritten-file ceiling. Prior
policy-5/schema-7 proof remains historical for INC-QML-12/13. No browser, new
hosted, other-platform or executable Qt evidence is inferred from local tests.

## Planned exact overload identity (INC-QML-15)

The generic C++ producer can collapse multiple constructor overloads into one
name-based node. Cold building and watch rebuilding can then retain different
locations for its ordinary file containment edge. This behavior predates the
constructor proof helper. Its conservative proof guard rejects conflicting spans;
native source-file links remain exact, but complete generic overload identity and
full generic overload graph parity are unverified. A separate characterized
producer/identity change must define compatibility and migration before correcting
that ownership boundary. Native file-context parity is not evidence of that fix.

## Semantic correction acceptance matrix (INC-QML-17–20)

Status: implementation and local revalidation in progress. These corrections
retain the existing extraction, scratch-join and publication owners. No corpus
code, build hook, QML engine or plugin executes. Receiver members belong to the
receiving object and accepted type; source construction and search depth constrain
child lookup. Engine/provider joins require declaration identity. Native aliases
require lexical declaration authority. Literal loaders share accepted project
component resolution without making runtime execution claims.

| Increment / acceptance | Positive boundary | Rejection and failure boundary |
| --- | --- | --- |
| INC-QML-17 / REQ-QML-017-AC02/AC04 | Own/inherited members, receiver-relative recursive/direct children, exact byte spans | Root lexical fallback, siblings, duplicates, dynamic options and unsupported/reparented trees cannot supply a target |
| INC-QML-18 / REQ-QML-017-AC03/AC04 | One exact source engine/component declaration and typed provider | Disjoint/nested names, reassignment, conditional exposure, aliases and unknown lifetime cannot establish shared identity |
| INC-QML-19 / REQ-QML-008-AC01/AC03; REQ-QML-016-AC01–AC04 | Direct native types and proved literal aliases retain canonical endpoints and distinct event mechanisms | Shadowed globals, cycles, conflicts, unsupported aliases and incompatible endpoint roles cannot satisfy a join |
| INC-QML-20 / REQ-QML-017-AC01/AC04 | Literal engine URL constructor and component loadUrl/create retain component/root provenance | Computed URLs, unsupported overloads, duplicate/reassigned loaders and unavailable resources remain uncertain |

Each correction requires raw JSON direction, query/affected, cold/warm and actual
manual/watch edit/removal parity. Policy upgrades must reanalyze unchanged inputs;
actual parse, join or publication failure must retain prior durable products and
allow corrected retry. Existing atomic publication and diagnostics are authoritative;
these helpers introduce no new persistence boundary. Reviewed wheel and full
contribution checks are final local gates. Native Qt/browser/platform, hosted
publication and broader API-family proof remain distinct evidence gaps.

## Temporary middle-button camera navigation (INC-QML-16)

Status: **Locally verified at emitted-script and reviewed installed-artifact
boundaries** under REQ-QML-021-AC01–AC03 and changed REQ-QML-019-AC04. Native
browser/device and other-platform behavior remains unverified.
[D16](ARCHITECTURE.md#d16--middle-button-input-owns-only-the-temporary-camera)
assigns mouse middle-button movement to the camera without changing source facts,
node geometry, physics, selection or filters. The Overview control/function/state
and top-ten ranking are removed. Checked full startup, community aggregation,
Select All/None, filters, search and the inspector retain their current roles.

`exporters/html_navigation.py::MIDDLE_PAN_SCRIPT` is a plain JavaScript IIFE using
the existing `container` and `network`, injected once after network construction
and initial physics setup. It has no package, SDK or DOM dependency beyond the
existing viewer. For each active mouse movement, obtain `network.getViewPosition()`
and `network.getScale()`, then call `network.moveTo` with position
`(view.x - dx/scale, view.y - dy/scale)`, unchanged current scale and
`animation: false`. The screen delta is incremental. Reading the scale at each
movement preserves a native wheel zoom that occurs between movements; no wheel
listener or zoom-policy override is added.

Only mouse middle-button pointer input with a held middle-button mask and a
nonnegative integer pointer identity starts the gesture. Guarded container
pointer capture plus window move/up/cancel listeners keep outside-container
movement and capture-failure fallback bounded. Matching release/cancel, lost
middle-button state, lost capture, window blur or page hide ends the gesture.
Pointer coordinates and view coordinates must be finite, scale positive, and the
derived world position finite; invalid camera/API state safely aborts rather than
accumulating a jump. Cleanup restores cursor/user-selection state before optional
capture release. Middle mousedown/auxclick and active text selection are suppressed
to prevent native autoscroll/selection; left/right/touch and wheel behavior are
otherwise retained.

The helper writes only temporary camera/input state. It neither calls node-move/
selection/filter/physics APIs nor writes datasets, RAW metadata, graph JSON,
sidecars, local storage or saved preferences. Camera/capture failure ends or safely
falls back from the gesture; it adds no parser diagnostic, persistence operation
or graph-write bypass. Qt policy 6, AST schema 7 and source fact contracts remain
unchanged. The helper and focused public tests stay below 300 physical lines;
HTML integration measures 789 lines within its existing 810-line legacy ceiling.
The helper/initial-view/middle-pan modules measure 116/245/223 physical lines;
each remains below 300. The inspector-harness compatibility adjustment retains
its own documented 1377-line legacy test ceiling.

Production emitted-script tests pass source/aggregate pan math at normal and
changed zoom, autoscroll prevention, release/invalid-state paths, input/wheel
coexistence, retained controls and immutable payloads. The 60-case focused suite
includes 24 independent horizontal/vertical/diagonal, scale and view variants.
Existing Overview expectations are superseded, not evidence for changed AC04.
Reviewed source/wheel/isolated-install equality covers all 156 Python payloads;
installed viewer scripts retain canonical/RAW facts, checked startup, source
inspectors and clean release/blur/retry camera behavior. Current exact outcomes
belong to traceability/validation. No native browser visual/device, new hosted or
other-platform result is claimed.

## Declaration identity and provider lifetime (INC-QML-18)

`CppDeclarationIdentity` is an immutable per-accepted-file syntax index. Source
path, original declaration span and enclosing lexical scopes own a portable
SHA256 identity. The index accepts bounded local/parameter/auto declarations and
accepted `this` owners; duplicate declarations, writes, deferred/conditional
ownership and computed/member/factory expressions retain rejection reasons.
Display names never replace an absent identity.

The access collector carries receiver/assigned/engine/provider identities and
provider lexical end offsets. Loads and handles use source-owner plus declaration
identity keys. Context exposure requires one load of that engine/component and
a provider whose lexical lifetime contains the load. Event collectors transport
both native endpoint declaration IDs; the cross-language adapter selects the
correct endpoint before resolving its QML handle. Mutable loads/handles remain
owned by one analysis-run access index; source facts belong to their producer.

Original spans, graph IDs and graph persistence ownership remain unchanged.
Policy 8 refreshes prior Qt overlays; AST schema 7 stays compatible. Parse/join/
write failure retention follows existing publication owners. Native execution,
factory/member identities and runtime object lifetime are outside this profile.
The continuing construction review rejects unproven/widget QObject ancestry
without changing native member visibility. Both seams are source-authority checks
under D17 and the existing acceptance IDs.
