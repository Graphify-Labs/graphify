# Qt API mechanism coverage

Status: Qt6.12 corrective implementation in progress, not complete Qt API support. Historical mechanism inventory baseline:
`95adbdc165f44a96bf275a7870bb1da4d82a5bea`. Qt's
[combined function and macro index](https://doc.qt.io/qt-6/functions.html) is a
family checklist. Acceptance tests mechanisms that change graph meaning, rather
than testing every indexed function independently.

## Inventory and evidence boundary

The historical 4 October 2026 comparison observed Qt 6.12 in the moving index
but pinned its mechanism contracts to Qt 6.8; existing syntax fixtures also include
Qt 6.5. Those references do not establish the new 31 October Qt6.12 support. The downloaded index has 15,757 rows,
15,757 distinct displayed names (the earlier 15,749 count incorrectly split qualified conversion-operator names at a colon) and 33,972 owner-document links. Those are not
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
| Signals, slots, emission and connections; REQ-QML-016 | Explicit event facts, supported member pointers, overload selectors/casts, lambdas/functors, SIGNAL/SLOT and literal flags | Source-local alias authority is corrected in INC-QML-19; qualified source identities are corrected in INC-QML-21; INC-QML-11 adds bounded public ancestor lookup with canonical declaring-member, shadowing, diamond and access rejection; INC-QML-28 retains explicit unknown emission sites; INC-QML-98 rejects source-redefined emission prefixes and preserves ordinary same-spelled identifiers/directive bytes. Const/non-const selector spellings do not prove qualifier-aware overload identity. QPrivateSignal reflected signatures, auto-connect by name and QMetaMethod endpoint flows need coverage. Runtime delivery/thread behavior is not modeled. |
| Properties and reflection; REQ-QML-008/017 | Q_PROPERTY facts, selected READ/WRITE/RESET/NOTIFY links, property/setProperty, QQmlProperty read/write and literal invokeMethod; INC-QML-66 retains separate VIRTUAL/OVERRIDE source flags and QML virtual/override/final modifiers | Receiver ownership is corrected in INC-QML-17; static SDK API identity is corrected in INC-QML-22/24. Native property handlers use accepted NOTIFY signals in INC-QML-27. Retained BINDABLE attributes do not establish generated-accessor/dependency semantics. QMetaMethod::invoke and metaObject/index/property handle chains are omitted. |
| QObject lookup; REQ-QML-017 | Root handles and literal objectName/findChild routes | Accepted receiver subtree/depth is corrected in INC-QML-17; unsupported/widget/unknown construction remains unresolved. findChildren is omitted. QML id is not an objectName; runtime reparenting cannot be guessed. |
| Context/initial providers; REQ-QML-008/017/018 | Direct source-established root context and initial-property forms; duplicate/conditional evidence | Exact lexical engines/providers are corrected in INC-QML-18, including component loadUrl association in INC-QML-20. INC-QML-08b adds accepted one-pointer/lvalue-reference declared factory/member APIs and bounded typed child-service calls/subscriptions. Original operator/CV/owner/accessor/NOTIFY/callback proof is required; runtime conversion, allocation and const-correct invocation remain unproved. Unknown aliases, assignment and expired/conditional lifetime remain conservative exclusions. INC-QML-68 adds source-only setExternalSingletonInstance setup for a proven engine, exact macro-registered singleton class and unique later load; it neither changes global provider selection nor proves runtime initialization/lifetime. |
| Declarative registration; REQ-QML-008 | Seven allowed macro names: QML_ELEMENT, QML_NAMED_ELEMENT, QML_ANONYMOUS, QML_SINGLETON, QML_UNCREATABLE, QML_ADDED_IN_VERSION, QML_REMOVED_IN_VERSION | Bounded combinations/version forms only. FOREIGN, EXTENDED, ATTACHED, EXTRA_VERSION and other unknown modifiers paired with a recognized base marker are explicitly unsupported. Standalone QML_INTERFACE/QML_VALUE_TYPE and namespace/value/container provider semantics remain outside the accepted bridge subset; source gadget/namespace annotation admission is separate. |
| Procedural registration; REQ-QML-008 | Five name routes: qmlRegisterType, qmlRegisterUncreatableType, qmlRegisterSingletonType, qmlRegisterSingletonInstance, qmlRegisterAnonymousType, with bounded template/literal arguments; explicit-template singleton factory callbacks can establish declared type | Name support does not cover every overload. Other discovered qmlRegister calls retain unsupported reasons. URL, QJSValue callback without explicit type, inferred-template, extended/revision/module/import/metaobject forms are outside the accepted subset. Callback execution/result/lifetime is not modeled. Source-local simple aliases are corrected in INC-QML-19; header alias targets remain excluded; qualified producer IDs are corrected in INC-QML-21. |
| Loading/creation; REQ-QML-017 | load/loadFromModule/setSource, rootObject/rootObjects, create/createWithInitialProperties, initial properties and literal-URL QQmlComponent construction | Literal engine URL constructors and component loadUrl/create are corrected in INC-QML-20, including declaration-owned engine providers and bounded URL/overload authority. Engine module constructors/loadData, component setData/beginCreate/completeCreate and dynamic source/lifetime remain omitted. |
| Enums, flags, gadgets and namespaces; candidate exposure scope | INC-QML-63 admits Q_GADGET/_EXPORT and Q_NAMESPACE/_EXPORT source markers, ordered access resets and original-byte qualified namespace facts. INC-QML-64 emits scoped QML enum values and supported type-qualified reads | Normalized Q_ENUM/Q_FLAG/Q_ENUM_NS/Q_FLAG_NS are not an enum/namespace API bridge. These markers do not grant QObject/registration authority or a C++ enum-to-QML value bridge. Native QMetaEnum/flag conversion and gadget/namespace value-provider semantics remain outside the verified subset. |
| Wrappers and ordinary calls; generic profile | Accepted helper contexts include QStringLiteral, QLatin1String, QString, QByteArray, QUrl and fromLocalFile | Support is context-specific; computed/localized strings do not prove literal targets. External SDK declarations and overloads are not automatically admitted. |
| Build/module/resource metadata; REQ-QML-009/018 | Static literal CMake/qmake, qmldir, qmltypes and qrc with bounded paths/conflict handling. INC-QML-65 admits typed Qt6.12 tooling fields (including opaque descriptions), while INC-QML-67 separates literal source exported names/versions/internal visibility from physical files and resource aliases. INC-QML-53 adds ordered private C/C++ target additions, separate explicit nonnative tooling and literal target-form PREFIX/FILES resource aliases; source aliases replace physical resource URLs. Native HEADER_FILE_ONLY inputs retain membership; explicit and module resource providers share ambiguity handling. INC-QML-93 adds explicit caller-admitted literal target include roots; INC-QML-95 proves only negative source-effect disjointness and never generates positive owners. | INC-QML-08a accepts bounded current-file literal $$PWD paths and separates tooling/build/analysis roots. Unknown/duplicate/not-yet-declared module targets, bare QML target-source registration, source-property scope selectors, late property changes, discarded resource content, inferred resource prefixes/options, relevant arbitrary expansion, conditions and execution remain excluded. Literal native RC-only metadata can be ignored only after proving it cannot affect analyzed membership/URLs. The functions index is not build-hook acceptance. |
| Timers, blockers, deletion and ownership | Generic call/source facts may be visible | singleShot delivery, blockSignals/QSignalBlocker, deleteLater and QML ownership transitions have no runtime model. Separate acceptance is required for an extension. |
| Other Qt modules and test/platform macros | Generic extraction where supported by the existing source parser. INC-QML-75/78 retain twenty source-only data/retry forms; INC-QML-81 adds supported Qt/Quick launchers, INC-QML-82 focus assertions and INC-QML-92 bounded Windows convention syntax. INC-QML-93/95 add caller-admitted literal build roots and negative source-effect proof, with opaque local binders and original spans | Retry arguments may repeat and cannot prove unique setup/order. Test execution, data-column/type agreement, arbitrary macro expansion, generated main functions, SDK internals and runtime results are not established. None of these source-only profiles executes a test or generated main. Unknown generated-resource/property/filter build effects retain unavailable context; final platform/installed evidence remains separate. |

The policy-25 RC prerequisite refinement has local source verification under INC-QML-53: only
literal native-RC source lists with `INCLUDE_DIRECTORIES`/`OBJECT_DEPENDS` qualify
for the build-only exemption. Include/prerequisite values remain uninterpreted,
including conditions/computed values; source selectors, mixed/runtime/unknown
properties and malformed syntax still reject. It adds no QML/C++ provider,
runtime QRC URL or out-of-corpus admission. The earlier policy-24 table/profile
does not verify this changed boundary. Current policy-25 source and isolated
artifact/install cases pass; hosted evidence remains pending.

## Named macro accountability

The audit reviews macro mechanisms separately from ordinary C++ syntax. The
following names have explicit producer and ordinary regression assignments.
Recognized/normalized tokens alone are never evidence of the Qt relationship.

| Macro | Analyzed behavior and boundary | Acceptance / exact evidence |
| --- | --- | --- |
| Q_INVOKABLE | Source member receives the invokable role, exact owner, access, signature and original span. QML authority also requires the declaring class's source-owned Q_OBJECT proof, accepted exposure and canonical ownership. Annotation alone does not prove registration or runtime invocation. | REQ-QML-008-AC02/AC03; REQ-QML-022-AC03/AC06; `tests/test_qt_metaobject_authority.py`; `tests/test_qt_cpp_exposure.py::test_members_properties_and_notify_have_exact_original_evidence`; `tests/test_qt_cpp_syntax.py::test_missing_canonical_ids_are_not_reconstructed` |
| Q_PROPERTY | Source property type and selected READ/WRITE/RESET/NOTIFY links retain owner/spans; an ordinary same-named function cannot become a NOTIFY signal. BINDABLE/generated dependency behavior and arbitrary accessor overloads remain outside the verified profile. | REQ-QML-008-AC02/AC03; `tests/test_qt_cpp_exposure.py::test_members_properties_and_notify_have_exact_original_evidence`; `tests/test_qt_cpp_exposure.py::test_notify_same_name_ordinary_function_is_not_signal` |
| QML_ELEMENT | Source registration requires accepted class identity and build/module membership. Missing/conflicting membership cannot create an arbitrary QML provider; supported related naming/version modifiers and rejected unknown modifiers are listed in the mechanism matrix. | REQ-QML-008-AC01/AC03; `tests/test_qt_project_admission.py::test_qml008_ac01_public_element_build_membership_and_canonical_member_endpoints`; `tests/test_qt_project_admission.py::test_qml008_ac03_macro_without_membership_or_wrong_module_does_not_guess` |
| Q_SLOTS / Q_SIGNALS | Access sections retain slot/signal roles, access and original positions. Connections/emissions use their distinct event facts; source declarations do not prove delivery/thread order. | REQ-QML-016-AC01–AC04; `tests/test_qt_cpp_syntax.py::test_access_sections_keep_original_roles_offsets`; `tests/test_qt_signals_slots.py::test_macro_sections_private_meta_slots_and_comments` |
| Q_SLOT / Q_SIGNAL | Per-member annotations retain slot/signal roles separately from ordinary methods and legacy SIGNAL/SLOT string syntax. Correct source owner and endpoint identity remain required. | REQ-QML-016-AC01/AC02; `tests/test_qt_cpp_syntax.py::test_annotations_legacy_calls_and_ordinary_emit_are_distinct` |
| Q_OBJECT | A distinct original-byte marker belongs to the actual canonical class through a retained ownership edge. QObject ancestry alone does not supply that class's own metaobject members. Missing or conditional source proof remains unavailable; corrupt promised proof rejects. Ordinary typed receiver methods/slots retain their separate accepted roles. | REQ-QML-022-AC03/AC06; `tests/test_qt_metaobject_authority.py`; `tests/test_qt_metaobject_events.py`; `tests/test_qt_metaobject_context.py`; `tests/test_qt_metaobject_updates.py` |

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

Historical Qt 6.8 mechanism references (the pinned Qt 6.12 audit is below):
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

The historical bounded Windows source and reviewed installed checkpoint includes
INC-QML-11/15/08 and INC-QML-28–38. It does not verify INC-QML-61–97. Mechanism proof and per-occurrence transport
survive assembly/serialization/reload; typed uses/read/call/connect/disconnect
facts retain their original endpoint roles and direction. Local installed
acceptance, actual CMake/qmake CLI profiles and retained full-gate/platform limits
are recorded in [final validation](VALIDATION.md#final-adoption-delivery).
Earlier revision records do not establish whole-SDK or runtime compatibility.


## Qt 6.12.0 inventory checkpoint (INC-QML-61)

A fresh bounded check at 11:37 UTC on 31 October 2026 confirms 6.12.0 is the
latest published 6.12 patch in the [official release table](https://doc.qt.io/qt-6/qt-releases.html)
and [release directory](https://download.qt.io/official_releases/qt/6.12/).
The exact previously missing OPC UA owner still returns 404. These three fresh
responses have separate retrieval/content identities; the original inventory
hashes remain unchanged and no moving or unrelated owner is substituted.

The 31 October 2026 inventory uses the versioned Qt 6.12.0 HTML references,
including [classes](https://doc.qt.io/qt-6.12/classes.html),
[functions/macros](https://doc.qt.io/qt-6.12/functions.html),
[QML types](https://doc.qt.io/qt-6.12/qmltypes.html),
[QML value types](https://doc.qt.io/qt-6.12/qmlvaluetypes.html), namespaces and
module member pages. HTML structural extraction is the documented fallback after
QDoc XML index endpoints returned 404. The indexed totals are 2,045 C++ classes,
1,242 QML types, 70 QML value types and 15,757 function/macro name rows with
33,972 owner links. These include links outside the pinned module profile.

The bounded crawler retrieved 3,468 of 3,469 versioned owner pages and accounted
for 81,472 structured declaration/enum-value/constant records. The derived
record-stream SHA-256 is
`1ff12f59b82bd62c932843e01dac5ec04fa1946a4a9c3fb2fade98f143fd5c2a`.
API names, qualified owners, declaration anchors and overloads remain separate.
Inherited declarations are accounted at their declaring owner. There are 329
owners without a structured declaration heading; prose/table-only facts and
undocumented/private SDK entities are not claimed exhaustive. An initial bounded
rejection of the large OPC UA enum page was retained before a single documented
larger-page retrieval; its records are included without changing runtime limits.
Raw third-party descriptive HTML is not distributed with Graphify.

| Structured documented fact | Count |
| --- | ---: |
| C++ functions | 30,653 |
| C++ properties / signals / slots | 3,339 / 1,409 / 653 |
| C++ enum declarations / enum values | 1,363 / 32,473 |
| Type aliases / macros / variables / namespace constants | 514 / 382 / 463 / 167 |
| QML properties / methods / signals | 7,398 / 1,518 / 1,084 |
| QML property groups / enum declarations | 53 / 3 |

Of the function-index owner links, 33,058 resolve to captured declaration anchors;
22 lack the expected anchor and remain documentation-accounting gaps. The linked
[OPC UA NodeIdType page](https://doc.qt.io/qt-6.12/qml-qtopcua-opcuanodeidtype.html)
returns 404. A further 101 independently versioned owners (78 Qt WebEngine,
23 Qt PDF), covering 892 function links, are excluded from frozen Qt6.12 facts.
Qt's [separate module release announcement](https://www.qt.io/blog/qt-webengine-will-release-separate)
explains their independent 6.140 versioning alongside Qt6.12. Exact immutable
release-source/document mapping was unavailable; moving snapshot APIs are not
silently substituted. These categories reconcile all 33,972 function links.

This inventory is an accountability checklist, not 81,472 verified Graphify
capabilities. The mechanism matrix remains authoritative for explicit semantics,
conservative exclusion, generic source handling and unverified forms. INC-QML-62
onward correct demonstrated source/metadata gaps through neutral regressions under
REQ-QML-022. No SDK, application component, build hook or runtime API executes.

The derived stream also has a complete machine-readable policy partition: all
81,472 records (including distinct overloads and duplicate owners) map by input
ordinal and line digest to 31 rules covering all 15 fact kinds. Its route-stream
SHA-256 is `83ae27d0532cda225a47a86316da1c7fff48b23d6c38bc470c2944af634a4cde`.
Rules map to the matrix and acceptance criteria, with separate source-route and
individual-SDK-verification fields. They are policy accounting, not per-API test
results: 307 unmatched documented macros remain unverified; generic declarations
still need an admitted syntax/profile and canonical source evidence. The pinned
metadata-generator audit, CMake property audit and persistence/platform evidence
are separate sidecars, not invented SDK-declaration counts. The missing/external
owner and anchor gaps above remain outside that derived-record total.

The separate index sidecar accounts for 3,520 owner/type/module rows: 2,045 C++
classes, 1,242 QML types, 70 values, 40 namespaces, 54 C++ modules and 69 QML modules.
Its route-stream SHA-256 is
`3be197c27f4e3b54c132985374ccf535162e1f544742fdc9797317f7cd53441a`.
There are 117 outside-profile index-row occurrences; this is not the distinct
101 separately versioned owner count. These are complete policy/accounting
partitions for the captured inputs, not individual SDK-symbol verification.
The final classifier/source/matrix binding is regenerated after source freeze;
intermediate runtime digests do not establish final delivered behavior.


Corpus-led compatibility corrections INC-QML-104/105/106 extend the existing
source profiles under REQ-QML-022-AC02/AC04/AC06. Legacy tooling `isConstant`
remains raw type-bearing member evidence, distinct from Qt6.12's modern
type/property/method flags. A uniquely proven same-unit C++ member prototype/body
pair keeps actual declaration identity and original body navigation; ordinary
methods remain unexposed, while invokable/slot endpoints still require all
existing class/metaobject/provider proof. Duplicate or conditional bodies, mismatched
signatures and callback data remain unavailable. C# local-function receiver
captures borrow source-proven type windows with static/shadow/order guards; no
function-local variable graph is added. Their exact tests, native outcomes and
remaining package/corpus/hosted gates belong in [traceability](../../tests/TRACEABILITY.md).
These corrections do not change inventory totals or verify additional SDK APIs
merely by matching their spelling.

INC-QML-107–109 correct direct ordinary-call retention, source-owned local callback
shadows and enclosing-class versus namespace lookup. Shared read-only member-pair
proof preserves actual direct/facade callers. A bounded original-AST class-role
witness prevents omitted ancestors from becoming namespace authority; uncertain,
conditional, anonymous, template/union and unsupported qualified out-of-line class
profiles remain unavailable. INC-QML-110–112 address confirmed literal class,
member and alias identity collisions. These are existing source mechanism
corrections, not additions to SDK inventory counts or a claim that every documented
class/member/API executes correctly. Fresh final-source package, corpus and
committed-head hosted gates remain required before delivery acceptance.

INC-QML-113 corrects the bounded lexical admission of plain struct callable `.h`
inputs while retaining C callback/data/attribute and inert/executable exclusions.
Selecting the C++ producer is independent of Qt annotation/native proof and adds
no individually verified SDK symbols to the inventory.

INC-QML-114 preserves a source-local unavailable C++ type lookup through later
unique-label reconciliation and persisted consumers. The rejection belongs to
one reference, so separate valid uses keep their existing targets. Bounded source
context and independent typed promises reject damaged transport rather than
inventing a declaration or native authority. This is a source-mechanism correction
under the existing criteria, with AST37/Qt31 migration, not an increase in the
documented API inventory or individually verified SDK totals.

The INC104–114 local source checkpoint has 2,048 combined compatibility passes and four
explicit unavailable-preprocessor skips. Fresh isolated core/QML-watch consumers
verify the same 383 raw Git/package/installed payload files, including 246 Python
modules, with 31/35 frozen dependency profiles. Those are source/artifact mechanism
checks, not 81,472 SDK semantic tests. Complete source/corpus and reviewed-head
hosted evidence remain separately recorded in traceability. A fresh official
release check on 31 October 2026 at 19:42 UTC confirms
[Qt 6.12.0](https://download.qt.io/official_releases/qt/6.12/) remains the latest
6.12 patch; the pinned inventory/release inputs are unchanged. Missing owners,
anchors, separately versioned modules and unverified macros above remain explicit.

That383-file artifact predates INC117/118 and does not verify their later source
contracts. Source-only complete observation composition and original anonymous
namespace witnesses add no individually verified Qt SDK symbols or inventory
rows. Their AST38/Qt32 source, package, complete corpus and reviewed-head hosted
evidence must be rebound separately. Optional-wheel per-case XML and test-only
cold-reference output isolation likewise change evidence ownership, not SDK
semantic coverage. The same documented static-profile and unverified inventory
limits continue to apply.

The subsequent INC119 checkpoint makes AST39/Qt33 current. Actual direct C++
definition/prototype producers retain source provenance before assembly, without
granting additional SDK/native authority. The new raw-Git wheel has385 payloads,
including248 Python files; fresh offline core/QML-watch profiles independently
match all of them before and after FAST8 plus the complete existing CLI,
failure-retention/recovery and source-observation probes. This is installed
mechanism evidence, not additional individually verified SDK symbols. Full-source,
reference-corpus and reviewed-head hosted evidence have their own identities and
acceptance in traceability; none is inferred from the inventory counts.
