# Qt and QML support foundation

QML-00 through QML-06 implement optional QML declarations/imports, scoped
bindings/aliases/JavaScript/handlers, native Qt C++ signals/connections/slots,
registered C++ APIs and literal QML object access. See [implemented scope](IMPLEMENTATION.md)
and [validation](VALIDATION.md) for individual gates and revision-specific evidence.
Literal CMake/qmake/resource/type-description admission and configuration/update
parity are implemented. QML-07 adds local consumer/export/assistant support;
hosted proof for its final revision remains pending.

The goal is to add reliable, local analysis of Qt/QML projects to Graphify and
contribute that support upstream in small pull requests. Graphify keeps its
existing Python implementation, graph contracts, CLI, and packaging workflow.

The audited baseline is the official
[Graphify-Labs/graphify](https://github.com/Graphify-Labs/graphify) repository,
active development branch `v8`, commit
`0b60d47e6cd9338c51143f39f35b6c45c8453385`, package version `0.9.74`.
The checkout was fetched on 2026-10-03. A moving branch or newer release must be
audited again before carrying these conclusions forward.

| Document | Purpose |
| --- | --- |
| [Audit](AUDIT.md) | Observed extension points, gaps, and risks in the baseline |
| [Architecture](ARCHITECTURE.md) | Implemented boundaries, future design, support matrix, and ADRs |
| [Design](DESIGN.md) | Implemented source-fact, resolver, Qt and publication contracts |
| [Requirements](../REQUIREMENTS.md) | Observable acceptance criteria and status |
| [Increment plan](PLAN.md) | Ordered, independently reviewable feature increments |
| [Development](DEVELOPMENT.md) | Environment, GitHub workflow, verification, and upstream delivery |
| [Code reference](CODE_REFERENCE.md) | Implemented owners/APIs and compatibility boundaries |
| [Platform matrix](PLATFORM_MATRIX.md) | Revision-specific install and hosted evidence |
| [Export matrix](EXPORT_MATRIX.md) | Semantic transports, presentation views and explicit omissions |
| [Diagnostics](ERRORS.md) | Source, coverage, transport and publication failure contracts |
| [Validation](VALIDATION.md) | Commands actually run and their results |
| [Test traceability](../../tests/TRACEABILITY.md) | Individual acceptance evidence, ownership and remaining gaps |

Repository development rules are in [AGENTS.md](../../AGENTS.md), together with
the existing [contribution policy](../../CONTRIBUTING.md). The root
[ARCHITECTURE.md](../../ARCHITECTURE.md) remains the upstream system description;
this directory records the local Qt/QML extension and its remaining design.

The agreed first target is **Qt 6 with both CMake and qmake metadata support**.
Qt 6.5 and 6.8 are source fixture profiles, not claims of installed SDK/runtime
equivalence. The [platform matrix](PLATFORM_MATRIX.md) records successful QML-03
through QML-06 hosted Linux/Windows/macOS lanes at their respective heads.
QML-07 has local evidence; its final reviewed-head hosted proof remains open.
Qt 5.15 is later, separately verified work.

Qt signals, slots, emissions and `QObject::connect` are explicit requirements,
as is bidirectional QML/C++ integration: C++ APIs supplied to QML and C++ access
to QML-created objects, signals, properties and methods. Each of the 17 requirements
has four assigned acceptance criteria, with individual traceability entries.

The [QML-00 decision](PARSER_DECISION.md) selects the optional, pinned language-pack
adapter. The source analysis requires no Qt runtime, compiler or JavaScript
execution. Scope and unresolved-coverage limits are in [architecture](ARCHITECTURE.md).

The plan retains QML-00 through QML-07, with QML-04a/04b/04c separating exposure,
native events and reverse object access. Native C++ event work can follow QML-00
alongside the QML lane; metadata readers can follow QML-02. Every acceptance ID
has a planned completion increment in traceability. Early graph/persistence/update
safety is required when a capability is enabled, before later optimization.


Use project-root updates for Qt scoped facts. `GRAPHIFY_QML_IMPORT_ROOTS` accepts
an ordered project-relative JSON list for lookup within the accepted corpus.
CLI/watch and the generated assistant AST stage inspect this configuration;
only the graph publication owner commits the analysis checkpoint. Static literal
metadata never invokes a build or runtime engine. The [export matrix](EXPORT_MATRIX.md)
states which consumers retain complete facts, which omit them, and which live
service checks remain unexecuted.
