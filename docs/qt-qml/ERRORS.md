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
| QML_LIMIT | error | Input over 5 MB, AST over 100,000 nodes/depth 256, semantic field over 512 encoded bytes | Reduce input or extend bounded profile |
| QML_EMPTY | info | Empty editor file | Add a component |
| QML_GRAPH_PRESERVED | error | Failed/omitted/partial QML | Correct failure and retry; force cannot bypass |
| QML_ROOT_MISMATCH | error | Unsafe scoped-ID subfolder rebase | Update absolute project root |
| QML_ROOT | error | Source is outside explicit root | Use an accepted source within the scan root |

Failures emit no authoritative declarations/edges. CLI/watch reject before graph
reconciliation, reports/HTML, root marker and manifest updates. Prior bytes remain
intact under forced, equal-count and edge-only losses. Earlier scan/stat bookkeeping
is outside that boundary. QML bypasses AST cache reads/writes until QML-06 adds
parser/fact-version invalidation. Qt edits conservatively refresh accepted code.
