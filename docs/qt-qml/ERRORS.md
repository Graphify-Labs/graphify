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

Failures emit no authoritative declarations/edges. CLI/watch reject before graph
reconciliation, reports/HTML, root marker and manifest updates. Prior bytes remain
intact under forced, equal-count and edge-only losses. Earlier scan/stat bookkeeping
is outside that boundary. QML/qmldir bypass AST cache reads/writes until QML-06 adds
parser/fact-version invalidation. QML/metadata changes, and JS changes in a corpus
containing QML, conservatively refresh accepted code. Generic JS facts retain
their ordinary cache/extraction behavior; overlays are source-owned QML facts.

Coverage codes are metadata on source-owned sites, rather than parse/write
failures. Reasons include missing roots/versions or members, duplicate providers,
internal exports, missing singleton pragma, resource `prefer` paths without an
index, inheritance/module/alias cycles or limits, JS lexical shadowing, computed
targets, reassigned callable values, runtime `Connections` targets, mixed-handler
style suppression and attached-provider absence. A coverage gap can coexist with
successful extraction; its site has no arbitrarily selected target edge.

Literal transport permits at most 50 string companions, each at most 512 encoded
bytes. The getter validates companion-map/field types and base64/UTF-8 before
lookup. `QML_METADATA` is the low-level rejection prefix, not a separate logger;
the owning extraction/join guard controls the public failure marker. Script-file
fan-out limit is retained as `qml_failures` even where no parser diagnostic is
available. Force cannot override either marker at publication.
