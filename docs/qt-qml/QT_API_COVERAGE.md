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
| Signals, slots, emission and connections; REQ-QML-016 | Explicit event facts, supported member pointers, overload selectors/casts, lambdas/functors, SIGNAL/SLOT and literal flags | Source-local alias authority is corrected in INC-QML-19; qualified source identities are corrected in INC-QML-21; INC-QML-11 adds bounded public ancestor lookup with canonical declaring-member, shadowing, diamond and access rejection; INC-QML-28 retains explicit unknown emission sites. Const/non-const selector spellings do not prove qualifier-aware overload identity. QPrivateSignal reflected signatures, auto-connect by name and QMetaMethod endpoint flows need coverage. Runtime delivery/thread behavior is not modeled. |
| Properties and reflection; REQ-QML-008/017 | Q_PROPERTY facts, selected READ/WRITE/RESET/NOTIFY links, property/setProperty, QQmlProperty read/write and literal invokeMethod | Receiver ownership is corrected in INC-QML-17; static SDK API identity is corrected in INC-QML-22/24. Native property handlers use accepted NOTIFY signals in INC-QML-27. Retained BINDABLE attributes do not establish generated-accessor/dependency semantics. QMetaMethod::invoke and metaObject/index/property handle chains are omitted. |
| QObject lookup; REQ-QML-017 | Root handles and literal objectName/findChild routes | Accepted receiver subtree/depth is corrected in INC-QML-17; unsupported/widget/unknown construction remains unresolved. findChildren is omitted. QML id is not an objectName; runtime reparenting cannot be guessed. |
| Context/initial providers; REQ-QML-008/017/018 | Direct source-established root context and initial-property forms; duplicate/conditional evidence | Exact lexical engines/providers are corrected in INC-QML-18, including component loadUrl association in INC-QML-20. INC-QML-08b adds accepted one-pointer/lvalue-reference declared factory/member APIs and bounded typed child-service calls/subscriptions. Original operator/CV/owner/accessor/NOTIFY/callback proof is required; runtime conversion, allocation and const-correct invocation remain unproved. Unknown aliases, assignment and expired/conditional lifetime remain conservative exclusions. |
| Declarative registration; REQ-QML-008 | Seven allowed macro names: QML_ELEMENT, QML_NAMED_ELEMENT, QML_ANONYMOUS, QML_SINGLETON, QML_UNCREATABLE, QML_ADDED_IN_VERSION, QML_REMOVED_IN_VERSION | Bounded combinations/version forms only. FOREIGN, EXTENDED, ATTACHED, EXTRA_VERSION and other unknown modifiers paired with a recognized base marker are explicitly unsupported. Standalone QML_INTERFACE/QML_VALUE_TYPE and namespace/value/container admission are missing. |
| Procedural registration; REQ-QML-008 | Five name routes: qmlRegisterType, qmlRegisterUncreatableType, qmlRegisterSingletonType, qmlRegisterSingletonInstance, qmlRegisterAnonymousType, with bounded template/literal arguments; explicit-template singleton factory callbacks can establish declared type | Name support does not cover every overload. Other discovered qmlRegister calls retain unsupported reasons. URL, QJSValue callback without explicit type, inferred-template, extended/revision/module/import/metaobject forms are outside the accepted subset. Callback execution/result/lifetime is not modeled. Source-local simple aliases are corrected in INC-QML-19; header alias targets remain excluded; qualified producer IDs are corrected in INC-QML-21. |
| Loading/creation; REQ-QML-017 | load/loadFromModule/setSource, rootObject/rootObjects, create/createWithInitialProperties, initial properties and literal-URL QQmlComponent construction | Literal engine URL constructors and component loadUrl/create are corrected in INC-QML-20, including declaration-owned engine providers and bounded URL/overload authority. Engine module constructors/loadData, component setData/beginCreate/completeCreate and dynamic source/lifetime remain omitted. |
| Enums, flags, gadgets and namespaces; candidate exposure scope | Some annotation tokens are normalized; Q_GADGET marks a class | Normalized Q_ENUM/Q_FLAG/Q_ENUM_NS/Q_FLAG_NS are not an enum/namespace API bridge. Q_NAMESPACE/_EXPORT and Q_GADGET_EXPORT recognition is missing. Acceptance is required before adding those capabilities. |
| Wrappers and ordinary calls; generic profile | Accepted helper contexts include QStringLiteral, QLatin1String, QString, QByteArray, QUrl and fromLocalFile | Support is context-specific; computed/localized strings do not prove literal targets. External SDK declarations and overloads are not automatically admitted. |
| Build/module/resource metadata; REQ-QML-009/018 | Static literal CMake/qmake, qmldir, qmltypes and qrc with bounded paths/conflict handling | INC-QML-08a accepts bounded current-file literal $$PWD paths and separates tooling/build/analysis roots. Relevant arbitrary expansion, conditions and execution remain excluded. The functions index is not build-hook acceptance. |
| Timers, blockers, deletion and ownership | Generic call/source facts may be visible | singleShot delivery, blockSignals/QSignalBlocker, deleteLater and QML ownership transitions have no runtime model. Separate acceptance is required for an extension. |
| Other Qt modules and test/platform macros | Generic extraction where supported by the existing source parser | No individually verified API/overload or macro-expansion promise. Graphify does not execute QtTest macros, discover SDK internals or run corpus code. |

## Named macro accountability

The audit reviews macro mechanisms separately from ordinary C++ syntax. The
following names have explicit producer and ordinary regression assignments.
Recognized/normalized tokens alone are never evidence of the Qt relationship.

| Macro | Analyzed behavior and boundary | Acceptance / exact evidence |
| --- | --- | --- |
| Q_INVOKABLE | Source member receives the invokable role, exact owner, access, signature and original span. Accepted exposure/member lookup makes it available to QML; annotation alone does not prove registration or runtime invocation. | REQ-QML-008-AC02/AC03; `tests/test_qt_cpp_exposure.py::test_members_properties_and_notify_have_exact_original_evidence`; `tests/test_qt_cpp_syntax.py::test_missing_canonical_ids_are_not_reconstructed` |
| Q_PROPERTY | Source property type and selected READ/WRITE/RESET/NOTIFY links retain owner/spans; an ordinary same-named function cannot become a NOTIFY signal. BINDABLE/generated dependency behavior and arbitrary accessor overloads remain outside the verified profile. | REQ-QML-008-AC02/AC03; `tests/test_qt_cpp_exposure.py::test_members_properties_and_notify_have_exact_original_evidence`; `tests/test_qt_cpp_exposure.py::test_notify_same_name_ordinary_function_is_not_signal` |
| QML_ELEMENT | Source registration requires accepted class identity and build/module membership. Missing/conflicting membership cannot create an arbitrary QML provider; supported related naming/version modifiers and rejected unknown modifiers are listed in the mechanism matrix. | REQ-QML-008-AC01/AC03; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_project_admission.py::test_qml008_ac03_macro_without_membership_or_wrong_module_does_not_guess` |
| Q_SLOTS / Q_SIGNALS | Access sections retain slot/signal roles, access and original positions. Connections/emissions use their distinct event facts; source declarations do not prove delivery/thread order. | REQ-QML-016-AC01–AC04; `tests/test_qt_cpp_syntax.py::test_access_sections_keep_original_roles_offsets`; `tests/test_qt_signals_slots.py::test_macro_sections_private_meta_slots_and_comments` |
| Q_SLOT / Q_SIGNAL | Per-member annotations retain slot/signal roles separately from ordinary methods and legacy SIGNAL/SLOT string syntax. Correct source owner and endpoint identity remain required. | REQ-QML-016-AC01/AC02; `tests/test_qt_cpp_syntax.py::test_annotations_legacy_calls_and_ordinary_emit_are_distinct` |

Shared rejection evidence covers comments, quoted/raw literals, preprocessor
definitions, malformed/partial source and original Unicode/CRLF spans in
`tests/test_qt_cpp_syntax.py`. Related Q_OBJECT, Q_GADGET, emission and registration
families appear in the mechanism matrix. Q_ENUM/Q_FLAG normalization is not a
verified enum bridge; unknown/foreign/extended/attached registration modifiers
retain explicit exclusions. The audit does not claim every macro expansion,
wrapper, conditional compilation branch or Qt SDK version is implemented.

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
source/artifact evidence. INC-QML-21–27 extend the corrected source profile; final artifact/contribution evidence is recorded in validation. INC-QML-08/11/15 have implemented bounded source profiles; current installed and contribution evidence is assigned in validation. INC-QML-29 adds canonical reference-return callables; INC-QML-30/31 govern logical affected direction and serialization integrity. Other omitted
families are explicit scope candidates requiring acceptance and compatibility
decisions before admission, rather than promises to model the whole SDK.
Update this matrix with newly accepted mechanisms or changed exclusions and bind
each behavior to an existing or new stable requirement and independent evidence.

## Explicit exposure-chapter review

The [C++ attribute chapter review](EXPOSURE_CHAPTER_REVIEW.md) maps property,
NOTIFY, signal, slot, invokable and provider mechanisms to existing acceptance
IDs. INC-QML-27 corrects native property handlers and explicit parameter authority.
INC-QML-21/22/24 correct source and SDK identity; INC-QML-23/25/26 correct retained
publication and complete-refresh cleanup. These implemented bounded forms
supersede the earlier finding dispositions without erasing their baseline evidence.
List/gadget/value ownership, runtime overload dispatch and method rebinding remain
explicit semantic exclusions or unverified forms. Macro spellings do not establish
those additional mechanisms.

## Final adoption evidence boundary

The current bounded Windows source and reviewed installed profile includes
INC-QML-11/15/08 and INC-QML-28–38. Mechanism proof and per-occurrence transport
survive assembly/serialization/reload; typed uses/read/call/connect/disconnect
facts retain their original endpoint roles and direction. Local installed
acceptance, actual CMake/qmake CLI profiles and retained full-gate/platform limits
are recorded in [final validation](VALIDATION.md#final-adoption-delivery).
Earlier revision records do not establish whole-SDK or runtime compatibility.
