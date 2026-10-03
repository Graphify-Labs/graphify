# Qt/QML export capabilities

Status: INC-QML-07 source implementation. This matrix describes accepted static
source facts, not Qt runtime delivery or database-service verification. The
canonical requirement is [REQ-QML-013-AC03](../REQUIREMENTS.md). A presentation export
is an inspection aid; retain `graph.json` when exporting one.

| Consumer or format | Retained Qt/QML information | Direction and reload | Explicit limitations |
| --- | --- | --- | --- |
| Graphify JSON | Node/occurrence identities, complete `metadata.qml`/`metadata.qt`, literal transport, original source spans, relation/context/confidence, existing attributes | `to_json` and `load_node_link_graph` preserve typed source direction for both default undirected and directed graphs | Graphify's normal internal-marker sanitation and persistence guards apply. This is the canonical semantic backup. |
| Directed GraphML | Complete metadata and attributes as JSON string properties; source paths/locations, relation/context/confidence, canonical IDs | Directed graph endpoints survive `networkx.read_graphml`; decode JSON-valued properties before semantic lookup | No automatic Graphify GraphML importer. XML-incompatible control characters follow existing export sanitation. |
| Undirected GraphML | Same source facts and JSON-valued properties as directed GraphML | Undirected topology survives; internal `_src`/`_tgt` markers are omitted | Logical dependency direction is not a promised reload contract. Use directed GraphML or canonical JSON for direction-sensitive work. |
| Cypher file, Qt/QML graph | Public scalar node/edge fields; complete nested facts in `metadata_json`, existing attributes in `attributes_json`; source paths/locations, context/confidence | Typed logical endpoints become relationship endpoints and `graphify_source`/`graphify_target`; stable `graphify_fact_key` retains distinct accepted mechanisms | Offline text/payload tests pass. No database engine was executed. Ordinary non-Qt graphs retain the existing writer. |
| Neo4j/FalkorDB direct push, Qt/QML graph | Same metadata/attribute JSON property representation plus existing scalar properties and canonical IDs | Parameterized upserts use typed logical endpoints and a stable relationship fact key | Actual production driver-boundary payloads are tested with recording SDK sinks. Live insertion/readback is unexecuted and outside the advertised static profile. Upserts do not remove stale records; replacing a prior graph needs an explicit database ownership/cleanup policy. |
| Ordinary `graph.html` | Full source-owned Qt/QML payload metadata, existing attributes, a readable semantic projection, locations and typed relationship evidence; projected fields participate in search and detail views | Visual arrows use logical endpoints; actual written payload and detail-rendering JavaScript are tested | Not a Graphify reload format. Community aggregation explicitly reports omitted source details; retain JSON. A pre-existing user search namespace is preserved without treating it as authoritative Qt/QML semantics. No Qt runtime equivalence is claimed. |
| Call-flow HTML | Distinct typed dependency/event/access tables, endpoint IDs, source locations, inferred confidence and runtime-delivery uncertainty | Relationship tables retain source direction; emissions/connections remain separate from direct call tables | Not a full fact or AST backup. Only the selected report sections are included; use JSON for omitted declarations/metadata. |
| Obsidian notes | Human-readable labels, declaration sources/locations, connection labels/confidence and community notes | Wikilinks expose neighborhood relationships | Complete semantic metadata, endpoint proof, edge context and byte spans are omitted. Notes do not establish logical call/event direction or round-trip identity. |
| Obsidian Canvas | Node cards/file links, communities and relationship/confidence labels | Visual endpoint references follow the existing layout exporter | At most 200 highest-weight edges; metadata, source ranges and contexts are omitted. Raw undirected arc order is not a logical dependency contract. |
| SVG | Labels, community colors, topology and extracted/inferred edge styling | Static lines; no semantic importer | Optional `svg` extra required. Source facts, endpoint evidence, context, byte spans and logical arrow direction are omitted. The local SVG test is skipped when the optional renderer is absent. |
| Wiki | Community/declaration orientation, source links and graph-level confidence statistics | Human-readable navigation | Not a complete semantic export. Use canonical JSON for source-site facts and endpoint evidence. |
| General report | Separate QML/Qt source-owned fact counts for resolved, ambiguous, dynamic, unsupported, unavailable and error states, plus other states and invalid metadata | Counts survive canonical JSON reload; the report does not mutate the accepted graph | Counts describe retained source facts, not a percentage of language support. Static resolution does not prove runtime behavior. A graph cannot establish that omitted or failed source extraction succeeded; consult diagnostics and canonical JSON. |

## Database property contract

`graphify/qt_export.py` owns the Qt-aware scalar payload and Cypher script. Nested
maps are serialized as exact JSON strings because database properties do not accept
arbitrary nested maps. Consumers decode `metadata_json` to recover the existing
versioned QML/Qt contract and literal transport; no new runtime interpretation is
introduced. Existing attributes remain separately recoverable from
`attributes_json`. Public scalar properties retain their names.

Qt/QML transport reserves `metadata_json` and `attributes_json`, plus the edge
properties `graphify_source`, `graphify_target` and `graphify_fact_key`. A collision
raises `QT_EXPORT_PROPERTY_COLLISION` instead of overwriting accepted properties.
The complete graph is checked before a direct SDK connection is created or any
index/write operation starts; Cypher validation completes before the atomic file
write. Tests preserve an existing output file and prove no SDK connection is
created on rejection. Other public scalar properties remain recoverable.

Non-interpolated string literals and escaped property identifiers protect the
offline Cypher text boundary. Direct SDK writers use parameters. The relevant
primary specifications are Neo4j's [property value types](https://neo4j.com/docs/cypher-manual/current/values-and-types/property-structural-constructed/)
and [literal escaping](https://neo4j.com/docs/cypher-manual/current/values-and-types/boolean-numeric-string/).
Transport preservation does not assert a live server accepts every statement.

The upsert relationship key represents the accepted source/target and current
public fact payload. Identical re-pushes are stable; changed facts can leave earlier
database relationships present. Graph-level clustering/hyperedge collections are
not part of this node/edge payload contract. Graphify has no database-to-Graphify
round-trip importer in this increment.

## Executed evidence and optional service validation

`tests/test_qt_qml_export_consumers.py` exercises actual native facade extraction,
directed GraphML readback, repeated native calls/reads through both JSON graph
orientations, and a directed QML-call-to-C++ path with separate call-site and
declaration sources. `tests/test_qt_export_matrix.py` exercises the actual Cypher
file, both SDK writer boundaries, parallel mechanisms, literal escaping, ordinary
writer compatibility, and actual Canvas/Obsidian outputs. Existing graph-database
index tests retain the generic push sequencing contract. Reserved-property
collision cases exercise rejection before file replacement or SDK creation.

`tests/test_qt_graph_html_payload.py` checks the actual written full HTML payload,
readable details, escaping, preserved user attributes and explicit omission in
community aggregation. `tests/test_qt_html_consumers.py` checks the production
call-flow artifact and separation of events from ordinary calls.
`tests/test_qt_source_coverage_report.py` checks production reports after actual
extraction and JSON reload, including invalid metadata and future-contract guards.

`tests/test_qt_mcp_consumers.py` and `tests/test_qt_mcp_stdio.py` exercise the
production HTTP and stdio protocol boundaries with the installed MCP SDK, comparing
query/path results and source/confidence evidence with the CLI. This executed
protocol evidence is distinct from the recording database SDK sinks. Exact
commands/results belong in
[VALIDATION.md](VALIDATION.md) and [traceability](../../tests/TRACEABILITY.md).

Live database verification is explicitly unexecuted. It is outside this static
source-support profile and is not an additional release gate. The recording SDK
tests establish the production payload and invocation boundary, not live engine
acceptance or readback.

If live integration is later requested and authorized, use an isolated disposable
database, record engine/SDK versions, and export a public native fixture with the
production APIs. Read back canonical IDs and decoded properties to compare exact
metadata, source ranges, logical endpoints, context/confidence and repeated source
occurrences; an identical re-push should retain the same count. Record redacted
failures and clean up only the authorized disposable database. Corpus execution,
production graph replacement and cleanup need their own scope and ownership
decision; no account access or live-service result is assumed here.
