# Qt and QML feature increment plan

Status: planning only. No increment below implements Qt/QML support in this
foundation change. Test commands are proposals for execution during the named
increment, not claims that new tests exist or have passed. Actual baseline results
are recorded in [VALIDATION.md](VALIDATION.md) and `tests/TRACEABILITY.md`.

This plan extends Graphify's existing Python pipeline and contribution workflow.
It does not propose a Qt application rewrite. Read [REQUIREMENTS.md](REQUIREMENTS.md),
[ARCHITECTURE.md](ARCHITECTURE.md), [DESIGN.md](DESIGN.md), [AUDIT.md](AUDIT.md),
and the upstream [contribution guide](../../CONTRIBUTING.md) before
implementation. The approved baseline is the imported upstream `v8` state recorded
by the foundation audit; recheck upstream changes before starting each PR.

Upstream already tracks this feature in [issue #1716](https://github.com/Graphify-Labs/graphify/issues/1716)
and [PR #1748](https://github.com/Graphify-Labs/graphify/pull/1748). The PR was open
when inspected for this foundation and includes QML extraction and a C++ bridge.
Its page contains older dependency notes superseded by later commits. QML-00
must review its current head, tests, dependencies, maintainer feedback and overlap
before deciding what to reuse, supplement or replace. Do not create a duplicate
issue or assume unmerged code is present in the imported baseline.

## Sequence and working contract

| Increment | Outcome | Prerequisites | Requirement references |
| --- | --- | --- | --- |
| QML-00 | Existing-PR review, reproducible baseline and accepted parser decision | Foundation review | QML-001, QML-010, QML-012, QML-014, QML-015 |
| QML-01 | Discover `.qml` and extract minimal source-backed declarations | QML-00 | QML-001, QML-002, QML-003, QML-010, QML-011, QML-012, QML-013, QML-014, QML-015 |
| QML-02 | Resolve explicit QML modules, local components and scoped names | QML-01 | QML-002, QML-004, QML-005, QML-010, QML-012, QML-014, QML-015 |
| QML-03 | Model bindings, aliases, JavaScript and signal relationships | QML-02 | QML-006, QML-007, QML-010, QML-012, QML-014, QML-015 |
| QML-04 | C++ exposure into QML, Qt signal connections and C++ access to QML APIs | QML-02 and QML-03; QML-05 for metadata-dependent URLs/module types | QML-008, QML-016, QML-017, QML-010, QML-012, QML-014, QML-015 |
| QML-05 | Enrich modules and resources from static Qt project metadata | QML-02; enrich QML-04 when available | QML-002, QML-004, QML-008, QML-009, QML-017, QML-010, QML-012, QML-014, QML-015 |
| QML-06 | Guarantee dependency-aware update/watch/cache parity | QML-03, QML-04, QML-05 | QML-011, QML-016, QML-017, QML-010, QML-012, QML-014, QML-015 |
| QML-07 | Verify consumers, publish support matrix and prepare upstream release | QML-00 through QML-06 | QML-013, QML-014, QML-015; regression of all requirements |

The numeric order is the default execution order. QML-05's independent metadata
parsers may follow QML-02 before the C++ bridge, but their bridge integration must
wait for QML-04. Agree ownership before parallel edits to shared discovery,
dispatch, graph, or watcher files. Minimal `qmldir` discovery is part of QML-02;
it cannot wait for broad project metadata support in QML-05.
QML-04's simple literal-file access cases can precede QML-05; resolving
`loadFromModule` exports or qrc aliases through build/resource metadata requires
QML-05's index, so that integration is a later focused PR rather than a circular
prerequisite for the entire bridge increment.

The primary acceptance profiles are ordinary Qt 6.5 and Qt 6.8 source/metadata,
as specified in ARCHITECTURE. Both CMake and qmake project forms are required for
the first Qt 6 target. Literal procedural registration is also part of Qt 6 bridge
support; neither qmake nor procedural registration is restricted to legacy Qt.
Qt 5.15 is a separate legacy compatibility profile with separately reviewed PRs
within QML-02, QML-04 and QML-05. Parsing common versioned-import syntax earlier
does not establish that profile's semantic support. Record module import versions
separately from the Qt release used to define a fixture.

Each increment is a cohesive feature branch and one or more small PRs. A PR may
merge independently only when it delivers a truthful subset, preserves existing
behavior, and satisfies its exit gate. Broad schema migrations, graph-class
changes, unrelated refactoring, and new runtime integrations require separate
review. An upstream-ready PR is not an upstream-accepted PR; approval and merge
remain separate recorded events.

Use existing `file_type="code"`, required source provenance, confidence values,
canonical ID helpers, ignore rules, and graph consumers. New QML detail belongs in
versioned metadata and focused resolver facts, with meanings defined in DESIGN.
Do not globally group QML/JavaScript with C++ to defeat cross-language call guards.
Do not activate a MultiDiGraph migration as an incidental language-support change.
Represent distinct bindings or handlers with their own source-backed nodes where
needed so the current simple graph does not silently overwrite relationships.

## Common verification gate

All paths below are relative to the repository root. Proposed new test files and
fixture directories are deliberately named so work can start without inventing
the test layout. Adapt names to an upstream-reviewed convention while retaining
the acceptance-criterion mapping. Every requirement has individually assigned
criterion IDs in REQUIREMENTS, such as `QML-003-AC01` through `QML-003-AC04`.
Before starting an increment, list all affected criterion IDs and map each one to
a concrete fixture/action/observable result and an exact automated test, or to an
explicit manual/system verification gap. Dedicated tests should use criterion
metadata or names such as `test_QML_003_AC01`; existing tests may map through
`tests/TRACEABILITY.md` without renaming unrelated tests.

Every increment's exit gate requires criterion-level evidence in traceability:
test identity, command, result, supported profile/platform, and remaining gap.
Record applicability explicitly. All applicable assigned criteria must pass
individually before a requirement becomes `Verified`. A skipped test, unexecuted
manual check, aggregate test count, or one passing happy-path test does not verify
the other criteria. Retain `Planned`, `Implemented` or partial/unverified status
until the criterion-level evidence supports promotion; document any criterion
scope change in the requirement rather than silently treating it as a pass.

Establish a pinned development environment with `uv sync --frozen`. If a PR changes
dependencies, deliberately regenerate and review `uv.lock` first; a frozen command
must not be used to pretend that an old lock covers a new dependency. Use the
selected QML extra after QML-00 accepts its packaging contract. Do not substitute
live Qt execution or model calls for deterministic offline parser tests.

Before handoff, execute the increment's focused tests and the following applicable
upstream checks. Capture failures, skips and unavailable optional dependencies.
The proposed pytest commands use Python's module runner and UTF-8 mode because
this project is developed on Windows. Existing POSIX CI may retain its equivalent
pytest entrypoint. The foundation's two remaining Windows-invalid deleted-working-
directory fixture failures are documented in VALIDATION; reproduce and classify
baseline failures instead of treating them as new Qt/QML regressions or claiming
the complete baseline is green.

```text
uv run --frozen python -X utf8 -m pytest tests/ -q --tb=short
uv run --frozen ruff check .
uv run --frozen pyright
uv run --frozen python -m tools.skillgen --check
```

When optional dependencies are involved, reproduce the upstream CI environment
with `uv sync --all-extras --frozen` in a suitable clean job, or use an explicitly
documented extra selection for the focused job. A platform-specific dependency
failure is a finding to resolve or report, not permission to claim full coverage.
When code changes, follow the repository's instruction to run `graphify update .`
and check its result. Generated local graph/build outputs remain uncommitted.

For every increment, review the full diff, canonical documents, test quality,
dependency provenance, and safe diagnostics. Record the actual commands and
results in `tests/TRACEABILITY.md`. Demonstrate regression tests fail against the
old behavior where applicable. Full-suite or cross-platform failures must be
explained before completion; unchanged aggregate coverage does not settle them.

## QML-00 — Baseline and parser decision

**Scope and code paths.** First inspect the current exact head of PR #1748 without
changing this workspace to its branch. Review its extractor, C++ modifications,
dependency metadata, tests, graph-family policy and mergeability against the
current upstream base. Map its existing coverage to the requirements in this plan.
Record a reuse/supplement decision and preserve attribution and license notices
for any later adopted code. Read-only inspection does not authorize posting review
comments or messages to other contributors.

The source audit identifies review cases around flat scope/name tables, discarded
import alias/version context, partial-parse reporting, C++-only resolver activation,
and compatibility of C++ changes with current upstream normalization. Reproduce
these against the recorded candidate head rather than assuming its tests exclude
them. Include the valid identifier form `QML_NAMED_ELEMENT(Backend)`;
[Qt 6.8's macro documentation](https://doc.qt.io/qt-6.8/qqmlintegration-h.html#QML_NAMED_ELEMENT)
shows an identifier argument. A test built only around quoted macro syntax does
not validate the real contract. Also test macro-like text in comments/literals.

Create public, synthetic fixtures under
`tests/fixtures/qml/parser_probe/` and a focused `tests/test_qml_parser_probe.py`
or equivalent nonshipping probe. Record the baseline commit, environment, current
language behavior, and parser ADR in the Qt/QML architecture/design documents.
Inspect `pyproject.toml`, `uv.lock`, `.github/workflows/ci.yml`,
`graphify/extractors/models.py`, `graphify/extractors/engine.py`, `graphify/ids.py`,
and `graphify/validate.py`. Keep experimental adapters out of production dispatch.

Evaluate the direct QML grammar binding and the pinned language-pack option
identified by the architecture audit. Do not choose a package from its name or
advertised grammar list alone. Verify its license, grammar revision, Tree-sitter
API/ABI compatibility, actual installed parser availability, source ranges,
error recovery, distribution size, and offline behavior. A required dynamic
grammar download fails the offline installation/extraction gate.

**Acceptance cases.** Parse imports with and without versions and aliases, objects,
nested objects, properties and modifiers, aliases, signals, methods, inline
components, JavaScript expressions, handlers, and deliberately incomplete files.
Probe `qmldir` independently; a small dedicated metadata parser is an acceptable
decision if its syntax and failure behavior are explicit. Unicode identifiers,
CRLF, comments containing braces, strings containing punctuation, and malformed
input must preserve useful ranges without a crash. The probe must never execute
QML or JavaScript. Missing grammar must yield a safe explicit limitation.

Verify installation and parser invocation on Python 3.10, 3.12, 3.13, and 3.14,
matching upstream's current Python CI matrix; include Windows x64, Linux, and
macOS compatibility evidence or record each unsupported/unverified combination.
Build a syntax matrix using version-tagged source fixtures rather than claiming
runtime support for all Qt releases. Pin the supported syntax subset before QML-01.

**Proposed commands.** The probe test is introduced by this increment; it must not
be entirely skipped in the job used to accept the parser.

```text
uv run --frozen python -X utf8 -m pytest tests/test_qml_parser_probe.py -q --tb=short
uv run --frozen python -X utf8 -m pytest tests/test_languages.py tests/test_multilang.py tests/test_extractors_registry.py tests/test_id_normalization_contract.py tests/test_validate.py -q --tb=short
```

**Exit gate and PR boundary.** Accepted parser ADR, dependency/license decision,
install matrix, synthetic corpus, meaningful recovery tests, baseline evidence,
and the existing-PR reuse/overlap decision.
No release language-support claim. Keep the parser choice/fixture PR separate from
production extraction if that makes review clearer. A missing cross-platform
wheel or incompatible ABI blocks promotion to default-installed support; document
an optional extra or defer instead of silently adding a compiler requirement.

## QML-01 — Discovery and minimal declarations

**Scope and code paths.** Add `graphify/extractors/qml.py` with an isolated parser
adapter and QML facts as necessary. Integrate `graphify/detect.py`, the public
facade and `_DISPATCH` in `graphify/extract.py`, and
`graphify/extractors/__init__.py`; registry entry alone is insufficient. Add the
accepted dependency/extra to `pyproject.toml` and `uv.lock`. Use
`graphify/ids.py`, `graphify/cache.py`, and `graphify/diagnostics.py` through their
existing contracts. Add `tests/test_qml_extract.py` and
`tests/fixtures/qml/declarations/`; update upstream language and detection tests.

Extract file/component declarations, nested object scopes, `id` declarations,
properties, signal declarations, and method declarations with source ranges.
Record imports as raw facts or import records without guessing a target. Method
bodies and bindings remain opaque source facts until QML-03. A declared property
alias may be recognized here while its target relationship remains unsupported.
Keep QML semantic information in `metadata.qml` and the versioned fact contract
specified in DESIGN. Represent `id` as component-local identity, not an ordinary
globally exported property. Preserve the full filename and component/symbol scope
when deriving canonical IDs; prove exact-case/punctuation collision handling.

**Acceptance cases.** Directory and single-file scans discover `.qml` and
`.ui.qml`, obey `.gitignore`/`.graphifyignore`, and leave existing classifications
unchanged. Valid declarations retain source-backed fields and correct ranges;
two files with the same stem, `.qml`/`.js` stem collisions, case-distinct names,
nested identical IDs, and relocation to a different absolute checkout do not merge
unrelated declarations. Malformed or unsupported input yields bounded diagnostics
and a partial/failed status that cannot replace valid persisted state. Missing
optional grammar does not make an unrelated Python/C++ scan fail. Repeated scans
preserve IDs, confidence and order after canonical comparison.

**Proposed focused commands.**

```text
uv run --frozen python -X utf8 -m pytest tests/test_qml_extract.py tests/test_detect.py tests/test_extractors_registry.py tests/test_languages.py tests/test_extract_cli.py tests/test_extract_code_only_cli.py tests/test_validate.py tests/test_node_id_canonical.py tests/test_partial_extraction_warning.py tests/test_zero_node_no_cache.py -q --tb=short
```

**Exit gate and PR boundary.** One PR delivers discovery plus a minimal extractor,
public fixtures, dependency packaging, extraction validation, a cold/warm smoke
test, and an honest declarations-only support note. Do not ship discovery alone
that routes QML into an unusable extractor. Existing zero-node/shrink/cache guards
must apply. Until QML-06, resolver-changing input must take a safe full project
resolution/rebuild path or be explicitly unsupported; a known stale-graph update
path must not be advertised as complete.

## QML-02 — Modules and component scope

**Scope and code paths.** Add `graphify/qml_resolution.py` and focused
`graphify/extractors/qml_metadata.py`, with registry integration through
`graphify/resolver_registry.py` and `graphify/extract.py`. Introduce shared
named-file discovery for `qmldir` in the existing corpus-boundary path; update
`collect_files()` and watcher recognition without creating a separate ignore
policy. Add `tests/test_qml_resolution.py`, `tests/test_qml_metadata.py`, and
`tests/fixtures/qml/modules/`. Use a per-project module/scope index with explicit
inputs and lifetime; retain raw facts separately from resolved graph edges.

Resolve directory imports, module URI imports, aliases, local QML components,
version declarations, `qmldir` type entries, inline-component scopes, and singleton
metadata according to the accepted static policy. Record unresolved or conflicting
imports rather than searching every basename in the repository. Preserve scope
boundaries for IDs, component members, and inline components; do not infer dynamic
delegate/context objects from lexical proximity alone.

**Acceptance cases.** Two modules both export `Button`; an aliased import resolves
only the intended module, while an ambiguous unqualified use has no guessed
concrete target. Imported versions, versionless imports, relative directory imports,
missing components, missing/duplicate module metadata, singleton declarations and
inline components have documented positive and rejection cases. Identical IDs in
separate component scopes stay distinct. An ignored or out-of-corpus `qmldir` does
not grant access to its files. Metadata-only changes trigger the conservative
resolution path even when QML text is unchanged. Synthetic Qt built-in references
remain external/unresolved unless a source-backed type inventory is supplied.

**Proposed focused commands.**

```text
uv run --frozen python -X utf8 -m pytest tests/test_qml_resolution.py tests/test_qml_metadata.py tests/test_qml_extract.py tests/test_language_resolvers.py tests/test_case_sensitive_resolution.py tests/test_import_self_loops.py tests/test_phantom_cross_package_call.py -q --tb=short
```

**Exit gate and PR boundary.** Module lookup/scope rules and ambiguity evidence are
documented and exercised through full extraction. A small named-file discovery
PR may precede the resolver when independently useful and tested. Module resolution
is a separate PR from later binding/call semantics. Keep the module-index contract
small enough for C++ and project metadata enrichment without a generic resolver
rewrite. No global same-name fallback or implicit Qt SDK scan.

## QML-03 — Bindings, aliases, JavaScript and signals

**Scope and code paths.** Extend focused QML extraction/resolution modules, reusing
existing JavaScript AST helpers only through a narrow adapter that preserves QML
lexical scope and original source offsets. Add
`tests/test_qml_bindings.py`, `tests/test_qml_javascript.py`,
`tests/test_qml_signals.py`, and `tests/fixtures/qml/interactions/`. Map relations
through existing `references`, `uses`, and validated `calls` semantics with QML
context metadata. Binding and handler nodes retain distinct source evidence and
avoid same-endpoint relation loss in the current simple graph.

**Acceptance cases.** Property binding reads link to the correct local ID/member;
property aliases retain the target and alias distinction; scoped local variables
shadow component members; inline-component and imported-JavaScript scopes do not
leak. Test expressions, blocks, functions, closures, `.js` imports, `.pragma
library` where accepted by the syntax matrix, signal declarations/emissions,
`onSignal` handlers and `Connections`. A handler's reference to a signal is not
proof of a runtime call. Dynamic `Connections.target`, computed property names,
runtime object creation and unresolved context values stay visibly unresolved or
qualified as inference. Two relationships between the same logical objects must
retain distinct evidence after build/merge/JSON round trip.

**Proposed focused commands.**

```text
uv run --frozen python -X utf8 -m pytest tests/test_qml_bindings.py tests/test_qml_javascript.py tests/test_qml_signals.py tests/test_js_import_resolution.py tests/test_js_callback_calls.py tests/test_indirect_call_block_scoped_shadow.py tests/test_build_merge_hyperedges_and_prune.py tests/test_relation_collapse_precedence.py -q --tb=short
```

**Exit gate and PR boundary.** Split bindings/aliases and JS/signals into separately
reviewable PRs if necessary. Each PR must preserve source ranges, scope, uncertainty,
and relation meaning, with cold/warm output parity. Update diagnostics and the
support matrix for dynamic limitations. No execution of user expressions, no
wholesale reuse of JavaScript resolution without QML scope context, and no claim
of complete runtime signal tracing.

## QML-04 — Qt/C++ exposure, signals and access to QML

**Scope and code paths.** Add a source-overlay module such as
`graphify/extractors/qt_cpp.py`, enriching existing C++ declarations rather than
replacing the C++ extractor. Extend QML project resolution with explicit type
registration and member evidence. Inspect `graphify/extractors/engine.py`, C++
preprocessing, `graphify/build.py` cross-family call guards, and canonical IDs.
Add `tests/test_qt_cpp_bridge.py`, `tests/test_qt_signals_slots.py`,
`tests/test_qml_cpp_access.py`, and synthetic fixtures under
`tests/fixtures/qml/cpp_bridge/`, `qt_connections/`, and `cpp_access/`.

Keep three focused PR boundaries without renumbering the surrounding increments:

- **QML-04a:** C++ types/members exposed into QML, satisfying QML-008's assigned
  criteria with registration and receiver evidence.
- **QML-04b:** Qt C++ signal declarations, emissions and explicit connections,
  satisfying `QML-016-AC01` through `QML-016-AC04`.
- **QML-04c:** C++ consumers of QML objects, functions, properties and signals,
  satisfying `QML-017-AC01` through `QML-017-AC04`; add a metadata integration PR
  after QML-05 where module/resource lookup is required.

Each sub-PR must map every affected criterion to its own observable assertions and
traceability evidence. Later QML-06 verifies invalidation of these facts, and
QML-07 verifies their query/export/MCP projection. Criterion-level status remains
unverified for those later obligations until their evidence exists.

Begin with statically identifiable `Q_OBJECT`, `Q_PROPERTY`, signals/slots,
`Q_INVOKABLE`, QML registration macros, and literal `qmlRegisterType`/singleton
registration calls supported by the accepted design. Treat literal
`setContextProperty` names and known instance types as evidence with their engine
and scope limits; uncertain ownership must remain inferred/unresolved. Use
`uses`/`references` and `qml_cpp_member` context first. Concrete cross-language
`calls` require narrowly validated registration/member evidence and dedicated
negative tests before extending a guard. QML_ELEMENT module URI enrichment that
requires build metadata remains pending until QML-05.

**Acceptance cases.** A QML property or method reference links only to the registered
class/member in the correct URI/version/registration scope. Test declaration and
implementation separation, getters/setters/NOTIFY evidence, overloaded members,
namespace-qualified C++ types, header/source duplicates, nonliteral registration,
conflicting registrations and unknown context-property types. A same-named member
in an unrelated C++ module must not acquire an edge. Macros inside comments or
strings are not registrations. Valid identifier-based `QML_NAMED_ELEMENT(Backend)`
must work; malformed or quoted forms must not substitute for that positive case.
Missing generated metadata or plugin binaries does
not trigger execution, an SDK scan or a guessed linkage. Removing or renaming a
registration on a C++-only change must reach the safe rebuild path.

**Qt signal/connect/slot acceptance cases (QML-016).** Retain signal and slot
declarations/signatures and distinguish an emission from an ordinary method call.
Cover `signals`, `Q_SIGNALS`, `Q_SIGNAL`, slot access sections, `Q_SLOTS`, `Q_SLOT`,
and both `emit` and `Q_EMIT` forms with original source spans.
Extract source-backed `QObject::connect` sites for member-pointer syntax, legacy
`SIGNAL`/`SLOT` signatures, signal-to-signal connections and lambda/functor receivers.
Typed connections may target a compatible ordinary member; do not require a slot
annotation when the typed connection form supplies sufficient member evidence.
Resolve explicitly selected
overloads, including supported `qOverload` or cast forms, only when the declaring
type and signature identify a unique member. Lambda connections retain the lambda
body's ordinary direct calls separately from the signal-to-lambda relationship.
Preserve sender, signal, receiver/context, slot/lambda, source span, conditional
registration evidence and a declared connection type/flags where present.
Record `Qt::AutoConnection`, direct, queued or
blocking declarations as configuration facts without predicting runtime scheduling,
delivery order, thread affinity or whether a connection is successfully established.
In particular, retaining `Qt::UniqueConnection` on a lambda/functor connection
does not establish effective uniqueness or deduplication; test that the graph
preserves the declared flag without asserting that runtime effect.

Test header/implementation pairs, namespaced classes, inherited members, duplicate
method names in unrelated classes, overload disambiguation, unavailable receiver
types, malformed legacy signatures, macro-like text in comments/literals, dynamic
targets and anonymous-lambda scope. Include supported private-slot meta-object
connections without confusing ordinary C++ call visibility with the meta-object
connection contract. A typed callable remains distinct from a same-named global
function; validate the actual endpoint/signature rather than its label.
Unresolved endpoints yield bounded diagnostic
evidence instead of guessed links. Connection sites and emissions retain their own
identity/context through graph construction; they must not become an ordinary
`calls` edge implying execution of the connected slot. Preserve supported
`QObject::disconnect` source statements as separate facts; a disconnect declaration
does not prove execution or justify erasing a prior connection from the source
graph. Ordinary direct slot calls, emit sites, connect sites and disconnect sites
must remain distinguishable after build/export/query/affected and incremental
updates.

**C++ access to QML acceptance cases (QML-017).** Collect literal `load` and
`loadFromModule` requests and `QQmlComponent` creation as access/creation facts with
the owning engine/component. Include the common Qt Quick `QQuickView::setSource`
and `rootObject` loader/access profile with its owning view. Track bounded
source-backed object flow from creation, `rootObjects()` or `rootObject()` to a
known QML root without assuming every engine/view uses the first same-named file.
Resolve literal `objectName`/`findChild` lookups only against the
identified object tree; a QML `id` alone does not establish the runtime lookup name.
Model `QMetaObject::invokeMethod` against declared QML function/signature evidence,
property reads/writes against the declared member, and C++ connections to declared
QML signals separately from ordinary direct calls. Also preserve exposed C++ signal
to QML-handler relationships in the appropriate receiver scope. Supported literal
`setContextProperty`, `setContextObject` and initial-property exposure carry their
provider, engine/component and provenance facts; reuse QML-04a's exposure model
instead of creating competing definitions. Conditional or dynamic exposure remains
visibly uncertain. Annotate static access intent
without claiming object creation, lookup, mutation, invocation or signal delivery
occurred successfully at runtime.

Test separate engines loading equal component names, multiple/unknown root objects,
module-loaded and URL-loaded components, separate QQuickView instances and their
setSource/rootObject provenance, objectName versus id, nested objects,
duplicate/dynamic object names, literal and computed method/property names,
overloads, read-only/unknown members, and QML signal-to-C++ slot connections.
Include C++ signal-to-QML handler cases and literal/dynamic context-property,
context-object and initial-property exposure variants.
Uncertain loader paths or receiver provenance remain unresolved. Resource aliases
and module URI/export mappings consume QML-05's index instead of a global basename
search. Never instantiate an engine, create a component or load a plugin to resolve
these source relationships.
Qt Quick Widgets loaders remain an explicitly deferred, separately reviewed
extension; the QQuickView source profile does not imply widget integration support.

Use the established `uses`/`references` projection plus namespaced connection,
emission, loading and member-access context defined in DESIGN. Dedicated site nodes
preserve distinct evidence when the simple graph would collapse endpoint pairs.
Use proposed contexts `qt_signal_emit`, `qt_connect_signal`,
`qt_connect_receiver`, `qt_disconnect`, `qt_cpp_qml_load`,
`qt_cpp_qml_find_child`, `qt_cpp_qml_property_read`,
`qt_cpp_qml_property_write`, `qt_cpp_qml_invoke`, `qt_context_exposure` and
`qt_initial_property`, with `metadata.qt.bridge_direction` and scoped
engine/component/root provenance. These are planned metadata contracts, not
already implemented graph fields. Reserve ordinary `calls` for evidenced direct
C++/JavaScript calls, including direct slot calls. A reflective QML invocation site
records access intent and its member evidence without implying an ordinary direct
call or runtime execution. Connecting a signal, emitting it and invoking a method
remain different source actions even when they mention the same member name.

**Proposed focused commands.**

```text
uv run --frozen python -X utf8 -m pytest tests/test_qt_cpp_bridge.py tests/test_qt_signals_slots.py tests/test_qml_cpp_access.py tests/test_qml_resolution.py tests/test_cpp_preprocess.py tests/test_cpp_method_declarations.py tests/test_cpp_objc_cross_file_calls.py tests/test_cross_language_call_resolution.py tests/test_cross_repo_external_call_guards.py -q --tb=short
```

**Exit gate and PR boundary.** Ship a narrow metadata overlay/registration PR before
broader bridge behavior if appropriate. Preserve existing C++ extraction and guards.
Every concrete exposure bridge edge has source-backed registration and member
evidence; connection/access edges have source-backed endpoint and object-flow
evidence. Confidence matches the actual claim. Review QML-016/QML-017 criteria
individually, including negative paths and distinct relation preservation. No
unrestricted name-based bridge or runtime event scheduling inference. Runtime
contexts, plugins and dynamic registrations remain documented gaps. Metadata-only
or C++-only changes use the conservative safe rebuild path until QML-06 proves
targeted invalidation; metadata-backed access cases finish with QML-05 integration.

## QML-05 — Build, module and resource metadata

**Scope and code paths.** Extend `qml_metadata.py` or separate focused Qt project
readers for `CMakeLists.txt`/`.cmake`, `.pro`/`.pri`, `.qrc`, `qmldir` and
`.qmltypes`. Reuse discovery and ignore boundaries from QML-02; inspect existing
`graphify/manifest.py`, `graphify/manifest_ingest.py`, `graphify/detect.py`,
`graphify/extract.py`, and watch recognition. Add
`tests/test_qt_project_metadata.py`, `tests/test_qt_resource_resolution.py`, and
`tests/fixtures/qml/project_metadata/`. Generated files remain distinguishable from
authoritative handwritten sources and do not silently override stronger evidence.

Parse a declared static subset of `qt_add_qml_module`, module URI/version,
`QML_FILES`, related C++ source lists, supported qmake statements, and resource
prefix/alias/file mappings. Use `.qmltypes` only within its documented evidence
limits. Resolve resource URLs through `.qrc` mappings; preserve both logical URL
and canonical source path. Do not run CMake, qmake, Qt tooling or project scripts.
Unsupported expansion, conditionals, generators or binary plugin metadata must
remain explicit limitations rather than evaluated code.

**Acceptance cases.** A literal resource alias maps to the intended in-corpus QML
file, including case-sensitive filenames and portable separators. Compare CMake
and qmake fixtures declaring the same simple module in both initial Qt 6 profiles;
both build forms are required for the first target. Test conflicting URIs,
overlapping qrc aliases, missing files, duplicate entries, relative paths, malformed
XML/metadata, conditional build statements, unknown variable expansion, and
resource paths escaping the approved corpus. XML readers must not resolve external
entities. A project with no Qt commands must not gain fabricated Qt modules.
Generated `.qmltypes` cannot overwrite real source provenance. `.qrc` or build
metadata-only changes trigger safe resolution before optimized invalidation exists.
Loader/access facts from QML-04c must resolve the same intended component through
literal file/resource URLs and accepted `loadFromModule` URI/type mappings; missing
or conflicting metadata must not select an unrelated equal-name component.

**Proposed focused commands.**

```text
uv run --frozen python -X utf8 -m pytest tests/test_qt_project_metadata.py tests/test_qt_resource_resolution.py tests/test_qml_metadata.py tests/test_qt_cpp_bridge.py tests/test_qml_cpp_access.py tests/test_detect.py tests/test_manifest_ingest.py tests/test_non_regular_files.py tests/test_security.py -q --tb=short
```

**Exit gate and PR boundary.** Prefer one PR for static CMake/qmake module records
and one for qrc/resource resolution. Named-file discovery is shared and tested.
Every supported construct has an explicit static policy and unresolved fallback.
No implicit build execution, external traversal or unconditional generated-source
indexing. Metadata enriches QML/C++ indexes without redefining Graphify's build.

## QML-06 — Incremental updates, watch and caches

**Scope and code paths.** Integrate accepted fact/index contracts with
`graphify/cache.py`, `graphify/manifest.py`, `graphify/watch.py`, the CLI's incremental
extraction path, `graphify/resolver_registry.py`, and the language resolver. Add
`tests/test_qml_incremental.py`, `tests/test_qt_watch_metadata.py`, and
`tests/fixtures/qml/incremental/`. Keep per-file syntax caching distinct from
project-dependent resolution; parser/fact-contract changes invalidate compatible
namespaces, while module/resource/registration changes invalidate their dependents.

Record explicit dependencies from a file's raw imports/references to relevant
module, registration, resource and build metadata. Re-resolve the dependent closure
for changed, added, moved and deleted inputs. If the closure is uncertain, fall back
to a safe full project resolution. Avoid reparsing unchanged source solely because
resolved facts changed, while preserving correctness ahead of optimization.
Resolver activation cannot depend solely on changed `.qml` suffixes. Named metadata
files and C++-only changes must update unchanged QML consumers.
The reverse direction also applies: QML declaration/objectName/signal edits must
re-resolve unchanged C++ loader, lookup, property, invocation and connection sites.
Keep context/initial-property providers and connection/disconnect site ownership
in the dependency index instead of treating them as anonymous global name facts.

**Acceptance cases.** Cold extraction, warm cached extraction, forced rebuild and
incremental update produce equivalent canonical nodes/edges/provenance for the
same final corpus. Test QML-only edits, imported-component deletion, qmldir-only
version/export changes, C++ registration-only edits, qrc alias renames, CMake/qmake
membership changes, same-mtime content changes, parser/fact schema upgrades,
checkout relocation and custom output directories. Watch batches recognize named
files and preserve existing debounce/locking/retry rules. Unsupported or partial
re-extraction cannot erase valid prior graph state or poison caches. Edge removal
and repointing are verified even when total node count remains unchanged.
For `QML-016-AC04` and `QML-017-AC04`, mutate a signal/slot signature, connection or
disconnect declaration, QML `objectName`/function/property, loader URL/module,
resource mapping and C++ context/initial-property provider. Verify both integration
directions equal a clean rebuild, while preserving distinct direct-call, emission,
connection and access facts and removing only source-backed stale results.

**Proposed focused commands.**

```text
uv run --frozen python -X utf8 -m pytest tests/test_qml_incremental.py tests/test_qt_watch_metadata.py tests/test_qt_signals_slots.py tests/test_qml_cpp_access.py tests/test_incremental.py tests/test_incremental_mtime_collision.py tests/test_watch.py tests/test_watch_manifest_location.py tests/test_cache.py tests/test_partial_cache.py tests/test_stale_prune.py tests/test_incomplete_build_guard.py tests/test_stat_index_portability.py -q --tb=short
```

**Exit gate and PR boundary.** A dependency-invalidation PR and a watcher integration
PR are acceptable when each has faithful parity tests and a safe fallback. Preserve
atomic writes, shrink guards, retained semantic layers and unresolved pending work.
Record invalidation cost and cache-hit/reparse evidence on the public fixture
corpus; do not invent a performance target before measuring the baseline. Remove
the earlier conservative full-rebuild limitation only after these cases pass.

## QML-07 — Consumers, support matrix and upstream delivery

**Scope and code paths.** Audit and extend only the consumers that need explicit
Qt/QML behavior: `graphify/cli.py`, `graphify/affected.py`, `graphify/analyze.py`,
`graphify/export.py`, `graphify/exporters/`, `graphify/callflow_html.py`,
`graphify/serve.py`, and `graphify/report.py`. Use source fragments under
`tools/skillgen/fragments/` for generated assistant guidance; never hand-edit the
generated skill bodies. Add `tests/test_qml_consumers.py` and
`tests/test_qml_end_to_end.py`; expand existing format, query and MCP tests.

**Acceptance cases.** A public mixed Qt/C++/QML/JavaScript fixture can be indexed,
queried, traversed by affected/path tools, exported and served via the offline MCP
test transport. Source locations, scope, ambiguity, relation direction and QML
context survive supported format round trips. Binding dependencies appear in
affected analysis under the declared policy; signal relationships are not mislabeled
as runtime calls in callflow. Existing non-QML queries and exports stay equivalent.
Test JSON, HTML and supported knowledge/document exports; test optional graph-DB
serialization with isolated transports, not production services. Queries and
generated guidance describe the feature subset actually present.
Include questions about a C++ signal's declared receivers and emission sites,
QML signal-to-C++ slot paths, C++ signal-to-QML handlers, and C++ lookup/invocation
of QML members. Query/affected, JSON/export reload and MCP must preserve source
direction, `metadata.qt.bridge_direction` and scoped object provenance, and
distinguish direct calls from emitted signals, declared connections,
disconnect statements and property access. Explicitly exercise the consumer parts
of `QML-016-AC04` and `QML-017-AC04`; diagram visibility alone is insufficient.

Publish a matrix with syntax/version fixtures, module forms, build/resource forms,
bridge evidence, incremental behavior, consumer formats and installation platforms.
Mark each cell verified, partial, unsupported or unverified with its exact test
evidence. Dynamic runtime lookup, plugin loading, uncertain context objects and Qt SDK types
remain explicit limitations unless separately implemented and verified. Document
CLI examples, dependency installation, diagnostic meanings and update migration.

**Proposed focused and artifact commands.** MCP coverage must execute in a job with
the optional MCP dependency, not pass solely through skipped tests.

```text
uv run --frozen python -X utf8 -m pytest tests/test_qml_consumers.py tests/test_qml_end_to_end.py tests/test_qt_signals_slots.py tests/test_qml_cpp_access.py tests/test_query_cli.py tests/test_query_mcp_direction.py tests/test_affected_cli.py tests/test_export.py tests/test_cli_export.py tests/test_callflow_html.py tests/test_serve.py tests/test_serve_http.py tests/test_wheel_packaging.py -q --tb=short
uv run --frozen python -m tools.skillgen --bless
uv run --frozen python -m tools.skillgen --check
uv run --frozen python -m tools.skillgen --audit-coverage
uv run --frozen python -m tools.skillgen --schema-singleton
uv run --frozen python -m tools.skillgen --monolith-roundtrip
uv run --frozen python -m tools.skillgen --always-on-roundtrip
```

**Exit gate and PR boundary.** Split consumer corrections from docs/generated
guidance when useful; each fixes a proven gap with regression evidence. Run the
complete upstream suite and relevant install/platform jobs on the final reviewed
SHA. Prepare small upstream PRs with the problem, supported subset, invariants,
test results and remaining gaps. Rebase or merge current upstream under repository
policy, rerun affected verification, and obtain maintainer review. Release only
with truthful capability and dependency notes; do not equate this plan's completion
with unrestricted QML runtime understanding or accepted upstream integration.

## First executable task and rollout

Start with QML-00 on a focused branch from the reviewed current upstream `v8`
baseline. Its ready specification is:

1. Review PR #1748 at its current recorded head and decide which portions can be
   reused or supplemented without duplicating upstream work. Record gaps and
   license/attribution implications; an open PR's own success claims are inputs to
   verification, not local proof. If it merges meanwhile, refresh the upstream
   baseline and turn later increments into focused gap PRs.
2. Reproduce the recorded baseline and inventory the existing extraction/ID/cache
   contracts. Record the actual source SHA and environment instead of relying on
   a floating version name.
3. Add a public synthetic parser corpus with a `Main.qml` containing a root object,
   `id`, one property, signal and method, plus a nested object. Separate fixtures
   cover aliases, inline components, import forms, JS scopes, CRLF/Unicode,
   unfinished braces, and metadata. Keep expected facts and limitations explicit;
   no private project sources.
4. Probe candidate parsers in isolated environments and record AST node/range and
   recovery evidence. Test installed/offline invocation and unavailable-parser
   behavior. Document the selected parser version, license, optional/default
   dependency policy, API/ABI compatibility and supported platform evidence.
5. Commit the parser ADR, fixture coverage and requirement/traceability updates as
   a reviewable PR. No production dispatch changes are required to accept the
   spike. Failed packaging or syntax gates return to the decision; they do not
   become undocumented extraction heuristics.
6. After review, implement QML-01 as the next PR with minimal declaration extraction
   and an explicitly bounded support claim. Expand the subset one increment at a
   time. Keep each later capability disabled, unresolved or accurately documented
   until its acceptance cases and consumer behavior are verified.

For every release candidate, validate a fresh install and an existing graph/cache
upgrade. An incompatible fact or parser contract requires a reviewed cache
invalidation/migration note. Keep prior valid graphs recoverable and preserve the
upstream semantic layer. A feature is ready for wider rollout when its advertised
matrix has evidence; remaining unsupported runtime behavior is part of the public
contract, not a reason to fabricate relationships.
