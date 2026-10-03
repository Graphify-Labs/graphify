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
| QML_METADATA | rejection prefix | Invalid literal-transport map, field type, base64 or UTF-8 | Re-extract valid source facts; joins surface the failure as QML_RESOLUTION_FAILED |
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
cannot establish a provider. Reanalyse accepted sources with Qt policy 5 and
AST cache schema 7; if the
body is outside the accepted corpus, supply that source through the supported
scope rather than guessing a target. A complete body without accepted meta-object
evidence retains `unsupported` / `native_class_metaobject_unavailable`.
`test_req_qml008_ac02_missing_body_proof_cannot_become_a_native_provider` covers
forward-only and legacy metadata rejection. Genuine competing complete bodies
retain ambiguity; source-owned unresolved facts remain visible in exports.

Ownership recovery does not add a new success or write-failure code. Exact
canonical definition provenance and complete class evidence permit normal source
edges; missing or conflicting evidence does not. Qt policy 5 forces unchanged-
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
are successful view states, not HTML publication failures. REQ-QML-020 projection
and any additional diagnostics remain planned.
