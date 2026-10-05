# Qt/QML diagnostics

Adapters own source diagnostics; the writer owns publication guards. Paths are
relative/bounded; messages omit source content and dependency exception details.

| Code | Severity | Trigger | Recovery |
| --- | --- | --- | --- |
| QML_PARSER_MISSING | error | Optional parser absent | Install graphifyy[qml] |
| QML_PARSER_LOAD | error | Parser cannot load | Reinstall pinned extra |
| QML_READ | error | Read/UTF-8 failure | Restore readable UTF-8 source |
| QML_SYNTAX | error | Incomplete/malformed grammar | Correct source |
| QML_UNSUPPORTED | error | Unsupported top-level syntax | Use/extend tested profile |
| QML_ANALYSIS_FAILED | error | Unexpected source-analysis/collector failure | Correct analyzer failure and retry; no partial declarations are authoritative |
| QML_LIMIT | error | Input over 5 MB, AST over 100,000 nodes/depth 256, semantic field over 512 encoded bytes | Reduce input or extend bounded profile |
| QML_EMPTY | info | Empty editor file | Add a component |
| QML_GRAPH_PRESERVED | error | Failed/omitted/partial QML | Correct failure and retry; force cannot bypass |
| QML_ROOT_MISMATCH | error | Unsafe scoped-ID subfolder rebase | Update absolute project root |
| QML_ROOT | error | Source is outside explicit root | Use an accepted source within the scan root |
| QML_RESOLUTION_FAILED | error | Project join raises | Correct join failure, retry; graph publication is rejected |
| QML_METADATA | rejection prefix | Invalid literal-transport map, field type, base64/UTF-8 or rejected membership declaration/input identity | Restore readable accepted input and re-extract valid source facts; joins surface the failure as QML_RESOLUTION_FAILED |
| QML-META-001 | error | Malformed/unsupported qmldir directive | Correct directive to supported literal subset |
| QML-META-002 | error | Metadata read/root/size failure | Restore readable in-root metadata |
| QML-RESOLVE-001 | coverage | Unavailable/ambiguous/dynamic lookup site | Supply supported corpus evidence; no guessed edge is emitted |
| QML-EXPRESSION-001 | coverage | Unresolved, ambiguous, dynamic or unsupported read/call/alias/handler site | Inspect site reason and supported scope/import evidence; no guessed edge |
| QML_SCRIPT_READ | error | Accepted imported script is unreadable or invalid UTF-8 | Restore readable UTF-8 script and retry |
| QML_SCRIPT_PARSER | error | JavaScript parser cannot load for imported-script overlay | Restore the installed JavaScript parser dependency |
| QML_SCRIPT_SYNTAX | error | Imported-script AST has syntax errors | Correct the script before publication |
| QML_SCRIPT_UNSUPPORTED | error | Classic Qt directives occur in an ECMAScript `.mjs` module | Use supported classic `.js` directives or supported ESM syntax |
| QML_SCRIPT_LIMIT | error/failure marker | Imported script exceeds 5 MB, 100,000 AST nodes/depth 256, or overlay graph exceeds 256 files | Reduce input/accepted dependencies or extend a measured bounded profile |
| QT_CPP_READ / QT_CPP_ROOT | error | Unreadable UTF-8 source or source outside the accepted root | Restore readable accepted source; retry without expanding the scan |
| QT_CPP_PARSER / QT_CPP_SYNTAX | error | C++ parser failure or incomplete supported Qt syntax | Restore parser dependency or correct the source |
| QT_CPP_LIMIT / QT_LIMIT | error | Bounded source, AST, parameters or semantic transport exceeds its limit | Reduce input or extend the measured profile |
| QT_METADATA | rejection prefix | Invalid versioned Qt literal transport | Re-extract valid source facts; the join guard rejects publication |

Failures emit no authoritative declarations/edges. CLI/watch reject before graph
reconciliation, reports/HTML, root marker and manifest updates. Prior bytes remain
intact under forced, equal-count and edge-only losses. Earlier scan/stat bookkeeping
is outside that boundary. QML and supported Qt metadata bypass AST cache
reads/writes. Native syntax in an explicit Qt context also bypasses syntax cache;
plain generic C++ keeps its existing portable cache. INC-QML-06 fingerprints installed
parser/package/fact/policy versions, ordered import roots and admission configuration.
Qt/provider/script/configuration changes conservatively refresh accepted code.
Generic JS keeps its existing extraction/cache-bypass policy; overlays are
source-owned QML facts rebuilt for the current run.

Coverage codes are metadata on source-owned sites, rather than parse/write
failures. Reasons include missing roots/versions or members, duplicate providers,
internal exports, missing singleton pragma, resource `prefer` paths without an
index, inheritance/module/alias cycles or limits, JS lexical shadowing, computed
targets, reassigned callable values, runtime `Connections` targets, mixed-handler
style suppression and attached-provider absence. A coverage gap can coexist with
successful extraction; its site has no arbitrarily selected target edge.

Native registration coverage belongs to `QtQmlBridgeIndex`, not the parser or
graph writer. `native_class_definition_unavailable` with status `unavailable`
means the accepted class ID has no source record explicitly proving a complete
class body. Forward declarations and legacy records without `is_definition`
cannot establish a provider. Reanalyse accepted sources with Qt policy 6 and
AST cache schema 7; if the
body is outside the accepted corpus, supply that source through the supported
scope rather than guessing a target. A complete body without accepted meta-object
evidence retains `unsupported` / `native_class_metaobject_unavailable`.
`test_req_qml008_ac02_missing_body_proof_cannot_become_a_native_provider` covers
forward-only and legacy metadata rejection. Genuine competing complete bodies
retain ambiguity; source-owned unresolved facts remain visible in exports.

Ownership recovery does not add a new success or write-failure code. Exact
canonical definition provenance and complete class evidence permit normal source
edges; missing or conflicting evidence does not. Qt policy 6 forces unchanged-
input refresh after the correction. A malformed native refresh still reaches
`QT_CPP_SYNTAX` and the existing publication guard, preserving the prior graph,
manifest, Qt stamp and root marker even under force. Corrected retry commits the
new state only after normal graph/manifest completion.
Borrowed unchanged-header bodies preserve their original source/span identity;
two representations of that same body do not create a false ambiguous owner.
Distinct source bodies still remain ambiguous. The accepted-context regressions
in `test_qt_cpp_context_ownership.py` cover both outcomes without mutating borrowed
data or relaxing the complete-body guard.

Literal transport permits at most 50 string companions, each at most 512 encoded
bytes. The getter validates companion-map/field types and base64/UTF-8 before
lookup. `QML_METADATA` is the low-level rejection prefix, not a separate logger;
the owning extraction/join guard controls the public failure marker. Script-file
fan-out limit is retained as `qml_failures` even where no parser diagnostic is
available. Force cannot override either marker at publication.


INC-QML-05 metadata codes QML_PROJECT_READ/LIMIT, QML_PROJECT_UNSUPPORTED,
QML_CMAKE_SYNTAX, QML_QRC_ENTITY/PATH/SYNTAX and QML_TYPES_SYNTAX/UNSUPPORTED describe bounded read/root,
work, unsupported build/type and resource XML failures. Failed/partial accepted
metadata reaches the existing publication guard. QML_TYPES_CONFLICT is a warning
that retains source and generated facts. Duplicate providers/aliases are coverage
ambiguity, not permission to choose the first record.


Qt configuration errors use bounded QT_CONFIG / QT_CONFIG_LIMIT messages and reject
before publication. Incompatible/missing .qt_analysis.json forces a refresh; it
never authorizes reading a previously accepted/deleted provider. State is committed
after graph and manifest success. Native scoped root mismatch uses the existing
QML_ROOT_MISMATCH rejection and retains prior durable outputs.

INC-QML-07 export direction validation uses `QT_EXPORT_DIRECTION` when stored logical
endpoint markers do not name the current accepted edge pair. Correct/re-extract
the graph before exporting; marker text cannot authorize a different endpoint.
Consumer coverage displays unresolved site reasons without converting them into
parser failures or a successful runtime dispatch claim. Presentation omissions
and live database gaps are explicit in [EXPORT_MATRIX.md](EXPORT_MATRIX.md).

Adoption syntax recovery for valid empty parameter defaults, standalone
`Q_UNUSED` statements and numeric digit separators changes neither diagnostic
IDs nor failure ownership.
Supported input passes the existing syntax stage; incomplete parentheses, damaged
defaults, malformed source and unsupported ordinary call/value contexts retain
`QT_CPP_SYNTAX` where applicable. Recovery changes only a bounded parse view,
never source files or graph-write protection. See DESIGN.md for ownership and
IMPLEMENTATION.md for executed positive/rejection and original-byte regressions.

## HTML view diagnostics

These CLI errors belong to HTML view preparation/publication; they do not describe
Qt source parsing or an application's runtime import state. Messages retain safe
stage/recovery guidance and omit raw backend exceptions or source content.

| Code | Severity / owning boundary | Outcome and recovery |
| --- | --- | --- |
| `HTML_GROUPING_INVALID` | Error / HTML grouping preparation | Saved membership cannot be recovered as a complete partition, or local clustering fails. Prior HTML/graph are retained. Inspect grouping/backend configuration and retry with accepted graph data. |
| `HTML_VIEW_UNAVAILABLE` | Error / HTML aggregate projection | A bounded useful community view is unavailable or explicitly skipped. Prior HTML/graph are retained. Inspect the partition or choose a focused graph. |
| `HTML_VIEW_FAILED` | Error / HTML preparation or publication | The prepared view exceeds the supported aggregate limit, or output replacement fails. Prior HTML/graph are retained. Use a focused graph for oversized views; check output access for publication failure, then retry. |

The CLI exits nonzero for these outcomes and cannot announce a new written file.
Successful retry uses the normal atomic writer. Clustering labels and source
payloads stay local; HTML aggregation identifies omitted occurrence-level facts.


Constructor/source-containment corrections add no diagnostic code or persistence
boundary. Rejected constructor class proof retains source-site evidence with
unavailable native ownership; it is different from a parser failure. Unknown
emission targets and unproved QML handles retain existing coverage reasons.
Malformed native input or failed joins still reject publication with the existing
stage-specific errors. AST schema 7 retires incompatible caches; prior valid
graph/manifest/root/Qt state survives a failed refresh. Corrected retry uses the
normal publication sequence. Internal-only or genuinely unlinked community counts
are successful view states, not HTML publication failures.

## Project-membership coverage (INC-QML-14)

INC-QML-39 compares supplied input identity inside the canonical root. Valid
short-path and parent-directory aliases no longer cause a false join failure.
Foreign/conflicting input identity retains the bounded `QML_METADATA` rejection
and owning `QML_RESOLUTION_FAILED` publication guard. Persistent path-resolution
failure is bounded at the membership helper, but the pipeline diagnostic handler
can resolve it again and expose the backend exception. INC-QML-41 owns that
reproduced diagnostic gap; complete bounded failure annotation is not yet verified.
Rejected updates preserve prior graph/manifest/root/Qt-state products; restore accessible,
matching accepted inputs before retrying. Path metadata resolution neither opens
new source content nor expands the corpus. The membership helper omits raw OS
exception bodies; INC-QML-41 must preserve that boundary through publication.

The initial INC-QML-14 profile is locally verified. INC-QML-39 adds accepted
input-alias coverage; focused/broader source regressions pass. A fresh artifact
reproduces the separate facade gap assigned to INC-QML-40; complete installed alias
and current hosted proof remain pending. Current Qt policy 18 and AST schema 12 are unchanged
by this correction.
`membership_resolution` sites retain the
source declaration, original span, bounded evidence/candidates and status/reason.
Missing, duplicate, conditional, generated or out-of-root targets retain ordinary
`QML-RESOLVE-001` coverage semantics with no target edge. Unresolved membership is
different from a malformed source or failed graph write; the site does not permit
reading a new path or executing a build/QML/plugin to obtain a target.

Invalid metadata/transport or unexpected projection failure uses the existing
reader diagnostics or `QML_RESOLUTION_FAILED` pipeline guard. No new parser code,
logger or publication bypass is introduced. Prior durable products remain subject
to the normal failure-retention boundary, including force. The initial
INC-QML-14 Qt policy 6 with AST schema 7 has local same-version refresh, failed-refresh retention,
corrected retry and repeat proof. The reviewed installed public fixture rejects
malformed qrc under force/partial options while retaining graph, manifest, analysis
state and root marker; repaired and repeated updates succeed. Earlier policy-5
evidence remains tied to its original revision. Continue using the installed artifact's normal
`graphify update .` workflow after installation rather than editing graph facts.

## Follow-up semantic audit

The [follow-up audit](FOLLOWUP_AUDIT.md) found wrong targets labeled resolved and
literal loaders omitted from special source facts. Successful publication or an
absence of parser/join exceptions does not detect those semantic failures.
INC-QML-17–20 now have bounded source/artifact correction evidence. The original audit added no diagnostic code,
runtime failure policy or persistence bypass.

For each correction, diagnostic review must distinguish an evidenced successful
target, an unsupported/ambiguous receiver or declaration, a genuinely failed
analysis, and failed publication/recovery. Unavailable identity retains source
provenance and no guessed target edge; actual failures retain prior durable
products under the existing guards. Stable new reasons/codes, severity, owning
boundary and retry behavior must be specified and tested before implementation
claims. Native browser/device gaps have their own
[system review procedure](VIEWER_SYSTEM_REVIEW.md), without fabricated graph errors.

## Receiver-owned coverage (INC-QML-17)

The reverse-access index retains successful targets only for accepted receiving
objects and member roles. Unsupported search flags use
`find_child_options_unsupported`; missing or rejected construction evidence uses
`construction_parent_evidence_missing`, `construction_parent_unestablished` or
`object_parenting_unestablished`; missing descendants retain
`object_name_unavailable`. Duplicate accepted descendants remain ambiguous.
Possible QML parenting changes use `component_parenting_mutated`; observed C++
setParent attempts retain `runtime_parent_mutation` source sites and invalidate
only an established receiver's component tree. Readonly writes retain
`readonly_property`. These are bounded coverage reasons under the existing
resolution contract, not new parser errors or runtime validation.

Accepted member access preserves property read/write versus invokable-call
direction and native endpoint roles. Unknown source ownership retains no guessed
edge. Genuine parse/join failures still use the existing stage guards; an actual
graph replacement failure preserves accepted graph, manifest, root and Qt stamp.
Repair/retry uses the normal update/watch sequence. Policy 7 refreshes unchanged
accepted Qt inputs; no writer, schema migration or corpus execution is introduced.

## Declaration identity rejection (INC-QML-18)

Engine/provider/handle identity is owned by the accepted C++ syntax index. Its
`status` and `reason` fields distinguish missing declarations, unsupported
expressions, duplicate declarations, conditional/deferred ownership and observed
reassignment. The context adapter propagates a precise role identity failure;
mixed initial-property failures retain the aggregate unavailable reason instead
of falsely attributing all rejected entries to one cause. Expired source provider
lifetime cannot create a binding.

These bounded source-site diagnostics use existing Qt metadata transport, severity
and publication contracts. They do not introduce a logger or success warning.
Recovery is correction of source/provenance followed by ordinary update; retries
do not grant identity. Policy 8 forces old derived overlays to refresh. Actual
analysis/write failures retain the previous four durable graph products.

## Native type authority (INC-QML-19)

The type index retains `native_type_expression_unsupported`,
`native_type_binding_ambiguous`, `native_type_binding_conditional`,
`native_type_alias_cycle_or_limit`, `native_type_alias_unsupported`,
`native_type_declaration_not_visible` and `native_type_included_alias_unavailable`
reasons. Registrations retain unavailable type evidence; event sites retain
unresolved endpoint authority. Corrupted accepted alias/include transport raises
`QT_METADATA` instead of selecting a global target. Existing Qt diagnostic and
failed-publication contracts apply; no separate logger or execution is added.

Construction ancestry rejection remains a source parenting-unavailable result.
It preserves accepted registration/member facts while refusing an unproved child
tree. A shadowed findChild filter retains `find_child_type_unsupported`. Correct
the source/provenance and run ordinary update; policy 9 refreshes old overlays.

## Literal loader rejection and recovery (INC-QML-20)

Successful literal routes retain resolved source ownership, with no claim of
runtime object creation. Unsupported constructor identity/arguments retain
`loader_constructor_identity_or_overload_unestablished`; method/root overloads
retain `loader_overload_unestablished`. Missing component engine authority retains
`component_engine_unestablished`. Conditional loads use `conditional_component_load`,
unknown URL expressions `computed_url`, and absent/duplicate source selection
`unique_source_loader_unestablished`. Existing declaration/lifetime reasons remain
more precise than a generic provider failure. These are bounded resolution
status/reason fields, not new exception codes or a separate logger.

The owning collector/index/resolver preserves original source context and no
guessed target. Correct the source/configuration and use ordinary update; policy
10 retires old derived facts. Actual parse/join/write exceptions use existing
stage diagnostics and publication guards. Manual/watch tests force parse and
replace failure, preserve the four prior products and prove repaired retry.

Full Windows testing found an unchanged atomic-write exception: a read-only
destination may be replaced before displaced-file cleanup raises. INC-QML-23
retains that integrity/recovery gap under REQ-QML-018-AC06. Prior generic retention
statements describe the executed failure profiles, not this failing OS boundary.

## Retained publication and source rejection (INC-QML-21–27)

Qualified source proof, SDK-name shadows and invalid native notification evidence
retain unresolved/ambiguous source results without guessed targets. Static API
identity rejection uses `reflection_api_type_unestablished`; loader overload/type,
declaration-identity and unavailable signal reasons retain their owning collectors.
Complete-source namespace overflow grants no partial join authority. Successful
resolution adds no warning; source corrections recover through normal update.

| Code | Severity and owner | Outcome and recovery |
| --- | --- | --- |
| `GRAPH_PUBLICATION_FAILED` | Error; caller-owned product preparation/commit | Update returns failure and prior accepted products survive recoverable faults. Correct permissions/source/output conditions and retry the ordinary update. First-build failure accepts no product cohort. |
| `GRAPH_PUBLICATION_RECOVERY` | Integrity error; publication rollback | A second restoration failure leaves recovery snapshots on disk. Stop accepting the mixed output, restore the complete prior cohort from the retained owned snapshot, correct the OS failure and rebuild. An automatic retry alone is not restoration proof. |
| `GRAPH_PUBLICATION_CLEANUP` | Warning after committed success; error after an uncommitted run; owned transaction cleanup | Accepted committed products remain coherent. Retained scratch files need cleanup after releasing locks/permissions; failed preparation preserves prior products. Cleanup failure never retroactively turns coherent committed success into false rollback evidence. |

Diagnostics expose bounded stages/codes, not private filesystem paths or serializer
bodies. Internal exception chaining retains the failure cause for local debugging.
Owned `.gfy-publish-*` directories contain `old`, `stage` and `restore` products.
On recovery, retain the `old` snapshot until every required destination has been
restored and read back; remove owned scratch only after that verification. A
missing original product is restored to absence. Follow configured output symlink
targets; never delete or move an unchecked computed path. Do not publish these
local snapshots because their contents belong to the analyzed project.

Individual writer restore failures likewise preserve a recovery backup when one
exists, or explicitly report that no prior backup exists. Ordinary read-only
destinations reject before displacement. The transaction does not promise atomic
visibility across products under process termination, power loss or racing writers.
Successful AST cache facts may survive publication failure; graph/root/manifest/
Qt stamp remain the accepted cohort. Schema 9/policy 12 retire older analysis facts;
rollback/downgrade uses the matching analyzer and a fresh build.

### Native property notification outcomes

`QtMemberViews.property_notify` owns `native_property_notify_unavailable`,
`native_property_notify_provenance_unavailable`,
`native_property_has_no_notify_signal`, `native_property_notify_accessor_not_unique`
and `native_property_notify_is_not_signal`. They retain unavailable, ambiguous or
unsupported resolution status, original handler/property context and no guessed
subscription. Successful admission records `native_property_notify_signal` with
the actual canonical native signal. These are source-resolution reasons under
the existing QML diagnostic boundary, not parser/write exception codes. Correct
registration, property or accessor evidence and run ordinary update; retries do
not grant missing provider or native signal authority.


## Inherited endpoint coverage (INC-QML-11)

The event index retains bounded coverage reasons under the existing Qt resolution
status contract: `inheritance_identity_unavailable` for missing/incomplete/invalid
canonical ancestry, `inheritance_cycle_or_limit` for a cycle or the 32-class
budget, and `inheritance_access_unavailable` for absent/invalid/nonpublic base
access on external member-pointer routes. Successful lookup preserves the exact
declaring member and source occurrence; it adds no warning. Shadowed or competing
members retain existing unavailable/ambiguous outcomes and no guessed edge.

These are source-analysis coverage outcomes, not parser or persistence failures.
Correct the source/provenance and run ordinary update; retry does not establish
missing authority. Actual parser/join/write failures still use the existing stage
guards and publication transaction. Executed malformed-input and real read-only
manifest failures preserve previous products and allow repaired retry. Policy 13
refreshes old derived ancestry. INC-QML-28 separately preserves explicitly spelled
emission occurrences when declaration evidence is absent.


## Constructor proof rejection (INC-QML-15)

Accepted signatures retain exact constructor/source ownership without new success
warnings. Unsupported/conditional types, duplicate bodies/signatures, invalid
span/ID/encoded signature, missing admitted dependency and potential local angle
include retain no canonical native owner. Generic `cpp_constructor` facts expose
`ambiguous`, `type_authorized` and `owner_bound`; existing Qt class-binding status
and reasons report the resulting unavailable authority. These are coverage
outcomes, not parser exceptions. Correct source/evidence and perform ordinary
update; retries do not grant missing type identity.

Malformed source and genuine read/cache/join/write exceptions use existing stage
contracts. Real read-only and late OS replacement failure tests preserve previous
accepted graph products and existing successful content-keyed cache entries,
then prove repaired retry. Schema 10/policy 14 retire old name-collapsed facts;
[D20](ARCHITECTURE.md#d20--constructor-signatures-authorize-identity-and-joins)
defines rebuild/downgrade behavior. No new logger, compiler execution or diagnostic
code is introduced.

## Explicit source emission outcomes (INC-QML-28)

An accepted annotation creates an observed emission without a success warning.
Missing, ambiguous, private or computed receiver/endpoint evidence retains the
site's unavailable status and existing signal-resolution reason. A local marker
override or inert/unevaluated syntax grants no explicit role. Same-spelled APIs
do not override an accepted emission mechanism. These are source-coverage outcomes,
not generic parser failures. Existing QT_CPP_SYNTAX and stage-specific update/write
errors still reject genuine failure and preserve prior accepted products. Repair
source or declarations and retry normally; no new code or runtime delivery claim
is introduced. Policy 15 refreshes unchanged derived sites.

## qmake adoption rejection (INC-QML-08a)

Supported literal metadata and header classification add no success warning.
Relevant unevaluated metadata uses the existing QML_PROJECT_UNSUPPORTED boundary.
New bounded reasons are `qmake_pwd_reassignment`, `qmake_scope_limit`,
`qmake_path_limit` and `qmake_path_outside_accepted_root`. Conditional/expanded,
unknown statement and unbalanced scope reasons remain applicable. Ignored build
settings and observed assignments are coverage facts, not branch execution.
Repair the source or explicitly configured safe roots and retry ordinary analysis;
expansion does not become supported by force. Parse/root/publication failure keeps
the existing product-cohort and successful source-cache retention contract. Header
classification supplies no Qt semantic authority and introduces no separate code.

## Typed API coverage and integrity (INC-QML-08b)

Accepted static API/provider/subscription joins add no success warning. Unsupported
declarator shapes retain `api_type_shape_unsupported` or
`provider_type_shape_unsupported`; conditional return authority retains
`conditional_api_type`. Missing, conflicting, cyclic and over-depth child chains
remain unresolved/unsupported with `context_child_property_unavailable`,
`context_child_type_unavailable_or_cycle` or `context_type_chain_limit`. Invalid
root/provider provenance retains existing bounded identity reasons. Serialized
type, owner, callable, source range, READ/NOTIFY and callback proof is independently
revalidated; corrupted proof cannot restore a link merely because a target exists.

Correct declarations, lexical bindings or source-backed metadata and retry normal
analysis. Rejection grants no runtime allocation/conversion or alias authority.
Genuine parser/resolver/publication errors retain their owning stage diagnostics
and prior products, with corrected retry and repeat evidence. Source-cache entries
may be added after successful extraction but do not accept graph publication.
No new diagnostic code, logger or corpus execution is introduced.

## Direction rejection and publication (INC-QML-30/31)

Accepted logical pairs add no warning. Read-only affected queries ignore invalid
complete/partial/foreign/ill-typed pairs, preserving graph bytes and source-owner
boundaries. Typed reload leaves explicitly corrupted markers intact for rejection;
it restores direction only when both markers are absent.

JSON serialization reports the existing stable **QT_EXPORT_DIRECTION** code at
the error severity, with bounded repair/re-extract guidance, and returns failure
before writing. Native directed contradictions also reject; force cannot bypass
the integrity check. The diagnostic includes no raw endpoint, path or source data.
External Qt preflight/Cypher keep their established complete-marker interpretation
on bidirectional storage wrappers while rejecting invalid pair membership and
types. JSON's native directed persistence is the stricter boundary.

Prior JSON bytes and the coordinated graph/HTML/report/manifest/checkpoint cohort
remain retained on rejection. The established owning publication stage still
reports an actual rollback or cleanup failure separately. Correct the source or
transport and retry normally; successful extraction/cache writes alone do not
accept publication. Real manual/watch rejection, nonempty source-cache retention,
repair and byte-identical repeated output are ordinary regression evidence.

## Initial raw-update repetition (INC-QML-32)

An unchanged first-repeat run reports the existing no-change completion and
preserves accepted graph bytes/mtime. Representation-only empty-list omissions
add no warning. Meaningful diagnostics, malformed values and changed source facts
remain observable; genuine parser/publication failures keep their existing owning
codes and prior product retention. Corrected source or writable output retries
normally. No new diagnostic, writer or rollback owner is introduced.

## File-role rejection and candidate preflight (INC-QML-33/34)

A malformed or foreign generic C++ file record grants no membership or containment
endpoint. Membership retains its existing unavailable/duplicate reason; a file
link cannot repair an unresolved native callable or type. Correct source/metadata
and repeat normal extraction. No additional source reads or corpus execution occur.

QT_EXPORT_DIRECTION also applies before raw publication and clustered no-change
acceptance. Its error identifies invalid logical-pair transport without exposing
the pair's arbitrary strings. The updater returns failure, retains the prior
product cohort and existing successful AST cache entries, and accepts no candidate
checkpoint. Force cannot bypass it. Repair/re-extract then retry normally.

## Relationship and occurrence integrity (INC-QML-35–37)

Unproved prior imports cannot authorize orphan retirement. Complete extraction
may remove their deleted source edge while conserving the unproved placeholder;
candidate integrity applies to surviving/new relationships. Still-referenced
external endpoints remain. Cleanup emits no new warning on successful completion.

A relationship inconsistent with its source mechanism grants no typed bridge.
The graph builder rejects it before generic relationship handling, keeping the
source occurrence and uncertainty without inventing a call or subscription.
Corrupt Qt literal transport retains QT_METADATA/QML_RESOLUTION_FAILED handling;
transport limits are not relaxed. Per-occurrence annotation prevents successful
source analysis from generating recursive literal maps or false parse failures.
Genuine parser, resolver and publication failures retain their existing bounded
diagnostics, prior product cohort and successful AST cache entries; repair retries
the ordinary path. Runtime Qt execution remains outside analysis.
