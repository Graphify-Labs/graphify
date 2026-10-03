# Qt and QML support foundation

QML-00 and QML-01 declarations/safety are implemented locally. See
[executed increments](IMPLEMENTATION.md) for acceptance gates still in progress.
Later metadata, C++ bridges and full release validation remain planned.

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
| [Architecture](ARCHITECTURE.md) | Proposed boundaries, parser decision, support matrix, and ADRs |
| [Design](DESIGN.md) | Proposed interface contracts and implementation rules |
| [Requirements](../REQUIREMENTS.md) | Observable acceptance criteria and status |
| [Increment plan](PLAN.md) | Ordered, independently reviewable feature increments |
| [Development](DEVELOPMENT.md) | Environment, GitHub workflow, verification, and upstream delivery |
| [Code reference](CODE_REFERENCE.md) | Existing owners and proposed extension files |
| [Validation](VALIDATION.md) | Commands actually run and their results |
| [Test traceability](../../tests/TRACEABILITY.md) | Planned test ownership and current coverage gaps |

Repository development rules are in [AGENTS.md](../../AGENTS.md), together with
the existing [contribution policy](../../CONTRIBUTING.md). The root
[ARCHITECTURE.md](../../ARCHITECTURE.md) remains the upstream system description;
this directory records the proposed Qt/QML extension.

The agreed first target is **Qt 6 with both CMake and qmake metadata support**.
Qt 6.5 and 6.8 are proposed fixture profiles; the exact application/SDK versions
can refine those profiles during QML-00. Qt 5.15 is later, separately verified work.

Qt signals, slots, emissions and `QObject::connect` are explicit requirements,
as is bidirectional QML/C++ integration: C++ APIs supplied to QML and C++ access
to QML-created objects, signals, properties and methods. Each of the 17 requirements
has four assigned acceptance criteria, with individual traceability entries.

Start with **QML-00**, the baseline and parser compatibility spike. Its exit gate
selects a parser and records a supported-syntax matrix before implementation
begins. A file-extension change alone is not QML support.

The plan retains QML-00 through QML-07, with QML-04a/04b/04c separating exposure,
native events and reverse object access. Native C++ event work can follow QML-00
alongside the QML lane; metadata readers can follow QML-02. Every acceptance ID
has a planned completion increment in traceability. Early graph/persistence/update
safety is required when a capability is enabled, before later optimization.
