# Proposed implementation contracts

Status: proposed. These interfaces are design constraints for the increments;
they are not existing Graphify APIs or claims of implemented behavior.
See [ARCHITECTURE.md](ARCHITECTURE.md) for the system design and ADRs.

## Ownership and dependency direction

Detection owns corpus inclusion. The QML extractor consumes an already accepted
source file and returns source-local facts. A Qt project index consumes accepted
metadata and C++ facts. The Qt/QML resolver joins those facts after extraction;
it does not rescan ignored directories or reinterpret corpus boundaries.
The graph builder and persistence pipeline remain authoritative for output.

New responsibilities should normally live under `graphify/extractors/` or focused
resolver modules, with thin registration calls in existing large modules. Avoid
moving unrelated language code as part of a feature PR.

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

## Graph projection and compatibility

Project accepted facts into existing node/file types and relation/context fields
where their semantics fit. Cross-file resolution remains inference unless the
existing evidence rules justify an extracted relation. Preserve the literal
reference's source span and the definition's provenance separately.

The baseline builder uses simple graphs. Before bindings and signals share
endpoints, establish a nonlossy representation for distinct facts and confirm
JSON/export/query round trips. A global migration to a multigraph is a separate
architecture decision; it must not be smuggled into a language-parser PR.

Any new fields need compatible defaults, serialization tests, and a cache/version
decision. Remapping IDs must also remap resolver-fact keys, references, and provider
indexes, not just node IDs and edge endpoints.

## Qt events and bidirectional object boundaries

QML-008 supplies the registered C++ surface to QML. QML-016 adds native C++
signal/slot semantics independently of the QML parser. QML-017 follows C++
consumers of QML objects and literal context/initial-property providers back to
their scoped declarations. These are proposed contracts, not existing support.

Retain source-owned emission, connection, disconnect, load, lookup and member
access sites. Existing `contains`, `uses` and `references` relations project
their endpoints; `metadata.qt` retains endpoint roles, signatures, conditions,
declared connection flags, source spans and `bridge_direction`. Proposed context
names include `qt_signal_emit`, `qt_connect_signal`, `qt_connect_receiver`,
`qt_disconnect`, `qt_cpp_qml_load`, `qt_cpp_qml_find_child`,
`qt_cpp_qml_property_read`, `qt_cpp_qml_property_write`, `qt_cpp_qml_invoke`,
`qt_context_exposure` and `qt_initial_property`.

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

File-content hashes alone cannot validate links dependent on module manifests,
C++ registrations, resource aliases, import configuration, or parser upgrades.
Track provider/consumer dependencies and invalidate affected resolution when
providers change, including changes with no modified QML file.

Until dependency-aware updates are verified, a conservative Qt project resolution
rebuild is acceptable if bounded and documented. Never cache an empty result from
an unavailable parser as successful analysis. Implement and test the conservative
fallback before enabling its update/watch path; otherwise reject that unsupported
operation before writing graph/cache state. A warning does not make stale output
acceptable. Preserve prior valid persisted state when extraction fails under the
existing write guards, and distinguish deletion from failure before using an
intentional destructive-update path.

## Verification boundaries

Test production extractor, resolver, build, serialization, update, and consumer
interfaces. Fixture output must be hand-checked against source facts, not generated
from the implementation under test. Compare normalized output across cold/warm,
full/incremental, relative/absolute, and Windows/POSIX cases.

Each feature increment updates [requirements](../REQUIREMENTS.md),
[traceability](../../tests/TRACEABILITY.md), support documentation, and any changed
design decisions in the same PR. Dynamic object creation, arbitrary plugin code,
full preprocessing, and arbitrary build-script evaluation remain explicit limits.
