# Qt API mechanism coverage

Status: bounded correction inventory, not complete Qt API support. Baseline inventory implementation:
`95adbdc165f44a96bf275a7870bb1da4d82a5bea`. Qt's
[combined function and macro index](https://doc.qt.io/qt-6/functions.html) is a
family checklist. Acceptance tests mechanisms that change graph meaning, rather
than testing every indexed function independently.

## Inventory and evidence boundary

On 4 October 2026 the moving index identifies Qt 6.12. This comparison pins Qt 6.8
contracts; existing syntax fixtures also include Qt 6.5. The downloaded index has 15,757 rows,
15,749 distinct displayed names and 33,972 owner-document links. Those are not
overload counts, supported API counts or executed tests. HTML SHA-256:
`5614dd3bcbaf3f2ddca346b6aecc1859bc7b7d6e26c3620bc81280328683e368`.
The complete local inventory remains ignored audit evidence.

Every indexed name has a policy route; every overload has not been reviewed.
Ordinary calls/declarations use generic source extraction where admitted syntax
supports it. External Qt targets without accepted SDK declarations can remain
unresolved. This does not assert exact overloads, Qt semantics or runtime effects.
Unknown macros may affect parsing and cannot be presumed harmless or supported.

Use four classes: **explicit semantic support**, **explicit conservative
exclusion**, **generic extraction only**, and **unverified/omitted**. A family can
contain several classes. Token normalization, retained text and a name whitelist
do not establish semantic acceptance.

## Mechanism matrix

| Mechanism / criteria | Current semantic handling | Partial, excluded or omitted forms |
| --- | --- | --- |
| Signals, slots, emission and connections; REQ-QML-016 | Explicit event facts, supported member pointers, overload selectors/casts, lambdas/functors, SIGNAL/SLOT and literal flags | Source-local alias authority is corrected in INC-QML-19; same-file qualified identities remain INC-QML-21; ancestor lookup remains INC-QML-11. Const/non-const selector spellings do not prove qualifier-aware overload identity. QPrivateSignal reflected signatures, auto-connect by name and QMetaMethod endpoint flows need coverage. Runtime delivery/thread behavior is not modeled. |
| Properties and reflection; REQ-QML-008/017 | Q_PROPERTY facts, selected READ/WRITE/RESET/NOTIFY links, property/setProperty, QQmlProperty read/write and literal invokeMethod | Receiver ownership is corrected in INC-QML-17; shadowed static API identity remains INC-QML-22. Retained BINDABLE attributes do not establish generated-accessor/dependency semantics. QMetaMethod::invoke and metaObject/index/property handle chains are omitted. |
| QObject lookup; REQ-QML-017 | Root handles and literal objectName/findChild routes | Accepted receiver subtree/depth is corrected in INC-QML-17; unsupported/widget/unknown construction remains unresolved. findChildren is omitted. QML id is not an objectName; runtime reparenting cannot be guessed. |
| Context/initial providers; REQ-QML-008/017/018 | Direct source-established root context and initial-property forms; duplicate/conditional evidence | Exact lexical engines/providers are corrected in INC-QML-18, including component loadUrl association in INC-QML-20. Factory/member providers and child-service chains remain INC-QML-08. Unknown aliases, assignment and expired/conditional lifetime remain conservative exclusions. |
| Declarative registration; REQ-QML-008 | Seven allowed macro names: QML_ELEMENT, QML_NAMED_ELEMENT, QML_ANONYMOUS, QML_SINGLETON, QML_UNCREATABLE, QML_ADDED_IN_VERSION, QML_REMOVED_IN_VERSION | Bounded combinations/version forms only. FOREIGN, EXTENDED, ATTACHED, EXTRA_VERSION and other unknown modifiers paired with a recognized base marker are explicitly unsupported. Standalone QML_INTERFACE/QML_VALUE_TYPE and namespace/value/container admission are missing. |
| Procedural registration; REQ-QML-008 | Five name routes: qmlRegisterType, qmlRegisterUncreatableType, qmlRegisterSingletonType, qmlRegisterSingletonInstance, qmlRegisterAnonymousType, with bounded template/literal arguments; explicit-template singleton factory callbacks can establish declared type | Name support does not cover every overload. Other discovered qmlRegister calls retain unsupported reasons. URL, QJSValue callback without explicit type, inferred-template, extended/revision/module/import/metaobject forms are outside the accepted subset. Callback execution/result/lifetime is not modeled. Source-local simple aliases are corrected in INC-QML-19; header targets and qualified ID collisions retain explicit gaps. |
| Loading/creation; REQ-QML-017 | load/loadFromModule/setSource, rootObject/rootObjects, create/createWithInitialProperties, initial properties and literal-URL QQmlComponent construction | Literal engine URL constructors and component loadUrl/create are corrected in INC-QML-20, including declaration-owned engine providers and bounded URL/overload authority. Engine module constructors/loadData, component setData/beginCreate/completeCreate and dynamic source/lifetime remain omitted. |
| Enums, flags, gadgets and namespaces; candidate exposure scope | Some annotation tokens are normalized; Q_GADGET marks a class | Normalized Q_ENUM/Q_FLAG/Q_ENUM_NS/Q_FLAG_NS are not an enum/namespace API bridge. Q_NAMESPACE/_EXPORT and Q_GADGET_EXPORT recognition is missing. Acceptance is required before adding those capabilities. |
| Wrappers and ordinary calls; generic profile | Accepted helper contexts include QStringLiteral, QLatin1String, QString, QByteArray, QUrl and fromLocalFile | Support is context-specific; computed/localized strings do not prove literal targets. External SDK declarations and overloads are not automatically admitted. |
| Build/module/resource metadata; REQ-QML-009/018 | Static literal CMake/qmake, qmldir, qmltypes and qrc with bounded paths/conflict handling | Arbitrary expansion, conditions and execution are excluded; broader qmake adoption remains INC-QML-08. The functions index is not build-hook acceptance. |
| Timers, blockers, deletion and ownership | Generic call/source facts may be visible | singleShot delivery, blockSignals/QSignalBlocker, deleteLater and QML ownership transitions have no runtime model. Separate acceptance is required for an extension. |
| Other Qt modules and test/platform macros | Generic extraction where supported by the existing source parser | No individually verified API/overload or macro-expansion promise. Graphify does not execute QtTest macros, discover SDK internals or run corpus code. |

## Owners and official contracts

`qt_cpp_syntax` owns normalization; `qt_cpp_exposure` owns annotations;
`qt_cpp_events`/`QtEventIndex` own native event endpoints;
`qt_cpp_registration` owns registration admission; `qt_cpp_access`/
`QtQmlAccessIndex` own loading and access; `qt_context_bindings` owns provider
joins; `QtMemberViews` admits property/member roles into the QML bridge.
[CODE_REFERENCE.md](CODE_REFERENCE.md) records the extension seams.

Reviewed Qt 6.8 contracts:
[QObject macros](https://doc.qt.io/qt-6.8/qobject.html#macros),
[properties](https://doc.qt.io/qt-6.8/properties.html),
[QMetaObject](https://doc.qt.io/qt-6.8/qmetaobject.html),
[QMetaMethod](https://doc.qt.io/qt-6.8/qmetamethod.html),
[registration macros](https://doc.qt.io/qt-6.8/qqmlintegration-h.html),
[registration functions](https://doc.qt.io/qt-6.8/qqml-h.html),
[application engine](https://doc.qt.io/qt-6.8/qqmlapplicationengine.html),
[component](https://doc.qt.io/qt-6.8/qqmlcomponent.html), and
[context](https://doc.qt.io/qt-6.8/qqmlcontext.html). These define Qt behavior;
repository tests establish Graphify's evidence.

## Acceptance strategy

For each admitted mechanism test hand-checked success, rejection, ambiguity,
receiver/lexical scope, comments/literals, malformed input and original-byte spans.
Check identity, mechanism/direction and provenance through extraction, build,
persisted reload, query/affected and cold/warm/manual/watch. Include stale-edge
removal, actual failure retention and corrected retry. Reuse mechanism tests for
ordinary members; test exceptional APIs that take distinct production paths.

INC-QML-17–20 correct A10–A13 and bounded literal loader provenance with recorded
source/artifact evidence. INC-QML-08/11/15/21/22/23 remain open. Other omitted
families are explicit scope candidates requiring acceptance and compatibility
decisions before admission, rather than promises to model the whole SDK.
Update this matrix with newly accepted mechanisms or changed exclusions and bind
each behavior to an existing or new stable requirement and independent evidence.
