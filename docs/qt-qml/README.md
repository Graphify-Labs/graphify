# Qt and QML support foundation

QML-00 through QML-04 now implement optional QML declarations/imports, scoped
bindings/aliases/JavaScript/handlers, native Qt C++ signals/connections/slots,
registered C++ APIs and literal QML object access. See [implemented scope](IMPLEMENTATION.md)
and [validation](VALIDATION.md) for individual gates and revision-specific evidence.
CMake/qmake/resource/type-description public admission, configuration/update parity
and final consumer/release evidence continue in QML-05, QML-06 and QML-07.

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
| [Design](DESIGN.md) | Source-fact/resolver contracts and explicitly planned Qt interfaces |
| [Requirements](../REQUIREMENTS.md) | Observable acceptance criteria and status |
| [Increment plan](PLAN.md) | Ordered, independently reviewable feature increments |
| [Development](DEVELOPMENT.md) | Environment, GitHub workflow, verification, and upstream delivery |
| [Code reference](CODE_REFERENCE.md) | Implemented owners/APIs and proposed extension files |
| [Diagnostics](ERRORS.md) | Source, coverage, transport and publication failure contracts |
| [Validation](VALIDATION.md) | Commands actually run and their results |
| [Test traceability](../../tests/TRACEABILITY.md) | Individual acceptance evidence, ownership and remaining gaps |

Repository development rules are in [AGENTS.md](../../AGENTS.md), together with
the existing [contribution policy](../../CONTRIBUTING.md). The root
[ARCHITECTURE.md](../../ARCHITECTURE.md) remains the upstream system description;
this directory records the local Qt/QML extension and its remaining design.

The agreed first target is **Qt 6 with both CMake and qmake metadata support**.
Qt 6.5 and 6.8 are source fixture profiles, not claims of installed SDK/runtime
equivalence. Executed host evidence is Windows x64/Python 3.10/3.12/3.13/3.14; Linux/macOS lanes
pass for QML-03 on hosted CI. Newer Qt revisions need their own hosted proof.
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


QML-05 public metadata admission and module/resource bridge joins are implemented
and locally verified. QML-06 refresh parity and QML-07 consumer/release proof
remain open. Static literal metadata never invokes a build or runtime engine.


QML-06 update/configuration parity is implemented. Use project-root updates for
Qt scoped facts. GRAPHIFY_QML_IMPORT_ROOTS accepts an ordered relative JSON list
for CLI/watch lookup within the accepted corpus. QML-07 consumer/release proof
remains open; hosted evidence must match its final revision.
