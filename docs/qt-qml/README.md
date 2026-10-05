# Qt and QML support foundation

INC-QML-00 through INC-QML-07 implement optional QML declarations/imports, scoped
bindings/aliases/JavaScript/handlers, native Qt C++ signals/connections/slots,
registered C++ APIs and literal QML object access. See [implemented scope](IMPLEMENTATION.md)
and [validation](VALIDATION.md) for individual gates and revision-specific evidence.
Literal CMake/qmake/resource/type-description admission and configuration/update
parity are implemented. INC-QML-07 completes consumer/export/assistant support and the declared hosted
source/artifact matrix; see the exact revision evidence in VALIDATION.md.

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
| [Follow-up audit](FOLLOWUP_AUDIT.md) | Current scope defects, public reproductions and contribution compliance |
| [Qt API coverage](QT_API_COVERAGE.md) | Mechanism-based support, exclusions and unverified API families |
| [Native navigation review](VIEWER_SYSTEM_REVIEW.md) | Physical browser/device acceptance procedure and evidence gap |
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
equivalence. The [platform matrix](PLATFORM_MATRIX.md) records successful INC-QML-03
through INC-QML-07 hosted Linux/Windows/macOS lanes at their respective heads.
INC-QML-07 has local and reviewed-head hosted evidence for that declared matrix.
Qt 5.15 is later, separately verified work.

Qt signals, slots, emissions and `QObject::connect` are explicit requirements,
as is bidirectional QML/C++ integration: C++ APIs supplied to QML and C++ access
to QML-created objects, signals, properties and methods. The current catalog has
21 Qt/QML requirements and 85 assigned acceptance criteria, alongside four shared
requirements and 14 criteria, with individual traceability. INC-QML-17–48 include
completed corrections and reviewed runner evidence. Current-upstream integration
and the followed-metadata provenance correction are INC-QML-49/50; acceptance of
that combined revision requires its own evidence.

The [INC-QML-00 decision](PARSER_DECISION.md) selects the optional, pinned language-pack
adapter. The source analysis requires no Qt runtime, compiler or JavaScript
execution. Scope and unresolved-coverage limits are in [architecture](ARCHITECTURE.md).

The plan retains INC-QML-00 through INC-QML-07, with INC-QML-04a/INC-QML-04b/INC-QML-04c separating exposure,
native events and reverse object access. Native C++ event work can follow INC-QML-00
alongside the QML lane; metadata readers can follow INC-QML-02. Every acceptance ID
has an individual evidence or remaining-gap assignment in traceability. Early graph/persistence/update
safety is required when a capability is enabled, before later optimization.


Use project-root updates for Qt scoped facts. `GRAPHIFY_QML_IMPORT_ROOTS` accepts
an ordered project-relative JSON list for lookup within the accepted corpus.
CLI/watch and the generated assistant AST stage inspect this configuration;
only the graph publication owner commits the analysis checkpoint. Static literal
metadata never invokes a build or runtime engine. The [export matrix](EXPORT_MATRIX.md)
states which consumers retain complete facts, which omit them, and which live
service checks remain unexecuted.

## Community navigation

HTML export recovers missing large-graph communities locally and fills names
from structural hubs. Select All starts checked and displays all exported view
data. Large source graphs still use the complete labeled community aggregate
within the display cap. Community filters, search, Select All and Select None
remain available. Middle-button dragging pans the graph; the wheel changes zoom.
The full source graph remains available for scoped queries.
Aggregated HTML states its source-detail omissions; camera/filter state is
temporary. Checked-default startup is locally verified through exporter/CLI,
emitted-script and reviewed installed-artifact checks. Browser visual inspection,
other-platform and hosted checks are not claimed for this revision.
See [REQ-QML-019](../REQUIREMENTS.md#req-qml-019--readable-large-graph-html-export)
and [INC-QML-09](PLAN.md#inc-qml-09--readable-large-graph-html-export) for acceptance
and the exact local evidence boundaries.
