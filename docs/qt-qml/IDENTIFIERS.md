# Qt/QML document identifiers

Requirements and delivery increments use distinct namespaces:

- Requirements use `REQ-QML-NNN`, for example `REQ-QML-018`.
- Acceptance criteria use `REQ-QML-NNN-ACNN`, for example `REQ-QML-018-AC02`.
- Increments use `INC-QML-NN`; work packages add a letter, for example `INC-QML-08a`.
- Architecture decisions retain their existing `D1` format.

Distinct prefixes identify whether a reference describes required behavior or a
delivery stage. Numeric identities, criterion numbers, package suffixes, behavior
and evidence assignments remain stable. Do not renumber or reuse an identity.

This is the canonical alias catalog. Every legacy identifier below permanently
refers to the same current identity. Use current IDs in new documents and source
annotations. Existing test names, comments, issues and evidence remain valid under
these mappings. Preserve recorded test names, generated artifacts, historical
logs, commit/branch names, URLs and license notices.

Current internal links use current headings; existing heading links retain their
legacy targets. Navigation follows
[GitHub custom-anchor syntax](https://docs.github.com/en/get-started/writing-on-github/getting-started-with-writing-and-formatting-on-github/basic-writing-and-formatting-syntax#custom-anchors).

Future requirements continue with `REQ-QML-019`; future top-level increments
continue with `INC-QML-09`. These counters describe different concerns and need
not advance together. Extend this catalog when retiring or migrating an ID;
never transfer an alias to unrelated behavior. Document identifiers do not change
runtime schemas or parser contracts.

The eighteen requirements comprise seventy-four criteria. The initial seventeen
requirements/sixty-eight criteria and six `REQ-QML-018` adoption criteria retain
separate support/evidence profiles. Implementation and verification status belong
to [requirements](../REQUIREMENTS.md) and [traceability](../../tests/TRACEABILITY.md).
This catalog establishes identity, not implementation or verification.

## Requirement aliases

- QML-001 -> [REQ-QML-001](../REQUIREMENTS.md#req-qml-001--parser-availability-and-compatibility)
- QML-002 -> [REQ-QML-002](../REQUIREMENTS.md#req-qml-002--corpus-discovery)
- QML-003 -> [REQ-QML-003](../REQUIREMENTS.md#req-qml-003--source-backed-declarations-and-identity)
- QML-004 -> [REQ-QML-004](../REQUIREMENTS.md#req-qml-004--imports-and-module-resolution)
- QML-005 -> [REQ-QML-005](../REQUIREMENTS.md#req-qml-005--component-and-member-scopes)
- QML-006 -> [REQ-QML-006](../REQUIREMENTS.md#req-qml-006--bindings-and-property-aliases)
- QML-007 -> [REQ-QML-007](../REQUIREMENTS.md#req-qml-007--javascript-handlers-and-signals)
- QML-008 -> [REQ-QML-008](../REQUIREMENTS.md#req-qml-008--qtc-exposure-bridge)
- QML-009 -> [REQ-QML-009](../REQUIREMENTS.md#req-qml-009--qt-project-and-resource-metadata)
- QML-010 -> [REQ-QML-010](../REQUIREMENTS.md#req-qml-010--deterministic-graph-and-provenance)
- QML-011 -> [REQ-QML-011](../REQUIREMENTS.md#req-qml-011--incremental-correctness)
- QML-012 -> [REQ-QML-012](../REQUIREMENTS.md#req-qml-012--failure-handling-and-persistence)
- QML-013 -> [REQ-QML-013](../REQUIREMENTS.md#req-qml-013--user-facing-graph-consumers)
- QML-014 -> [REQ-QML-014](../REQUIREMENTS.md#req-qml-014--platform-and-compatibility-evidence)
- QML-015 -> [REQ-QML-015](../REQUIREMENTS.md#req-qml-015--documentation-and-upstream-delivery)
- QML-016 -> [REQ-QML-016](../REQUIREMENTS.md#req-qml-016--qt-c-signals-slots-and-connections)
- QML-017 -> [REQ-QML-017](../REQUIREMENTS.md#req-qml-017--bidirectional-qml-and-c-object-integration)
- QML-018 -> [REQ-QML-018](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)

## Acceptance criterion aliases

All mappings preserve the requirement and acceptance numbers. Existing tests with
`qmlNNN_acNN` names remain evidence for the corresponding current criterion.

- QML-001-AC01 -> [REQ-QML-001-AC01](../REQUIREMENTS.md#req-qml-001--parser-availability-and-compatibility)
- QML-001-AC02 -> [REQ-QML-001-AC02](../REQUIREMENTS.md#req-qml-001--parser-availability-and-compatibility)
- QML-001-AC03 -> [REQ-QML-001-AC03](../REQUIREMENTS.md#req-qml-001--parser-availability-and-compatibility)
- QML-001-AC04 -> [REQ-QML-001-AC04](../REQUIREMENTS.md#req-qml-001--parser-availability-and-compatibility)
- QML-002-AC01 -> [REQ-QML-002-AC01](../REQUIREMENTS.md#req-qml-002--corpus-discovery)
- QML-002-AC02 -> [REQ-QML-002-AC02](../REQUIREMENTS.md#req-qml-002--corpus-discovery)
- QML-002-AC03 -> [REQ-QML-002-AC03](../REQUIREMENTS.md#req-qml-002--corpus-discovery)
- QML-002-AC04 -> [REQ-QML-002-AC04](../REQUIREMENTS.md#req-qml-002--corpus-discovery)
- QML-003-AC01 -> [REQ-QML-003-AC01](../REQUIREMENTS.md#req-qml-003--source-backed-declarations-and-identity)
- QML-003-AC02 -> [REQ-QML-003-AC02](../REQUIREMENTS.md#req-qml-003--source-backed-declarations-and-identity)
- QML-003-AC03 -> [REQ-QML-003-AC03](../REQUIREMENTS.md#req-qml-003--source-backed-declarations-and-identity)
- QML-003-AC04 -> [REQ-QML-003-AC04](../REQUIREMENTS.md#req-qml-003--source-backed-declarations-and-identity)
- QML-004-AC01 -> [REQ-QML-004-AC01](../REQUIREMENTS.md#req-qml-004--imports-and-module-resolution)
- QML-004-AC02 -> [REQ-QML-004-AC02](../REQUIREMENTS.md#req-qml-004--imports-and-module-resolution)
- QML-004-AC03 -> [REQ-QML-004-AC03](../REQUIREMENTS.md#req-qml-004--imports-and-module-resolution)
- QML-004-AC04 -> [REQ-QML-004-AC04](../REQUIREMENTS.md#req-qml-004--imports-and-module-resolution)
- QML-005-AC01 -> [REQ-QML-005-AC01](../REQUIREMENTS.md#req-qml-005--component-and-member-scopes)
- QML-005-AC02 -> [REQ-QML-005-AC02](../REQUIREMENTS.md#req-qml-005--component-and-member-scopes)
- QML-005-AC03 -> [REQ-QML-005-AC03](../REQUIREMENTS.md#req-qml-005--component-and-member-scopes)
- QML-005-AC04 -> [REQ-QML-005-AC04](../REQUIREMENTS.md#req-qml-005--component-and-member-scopes)
- QML-006-AC01 -> [REQ-QML-006-AC01](../REQUIREMENTS.md#req-qml-006--bindings-and-property-aliases)
- QML-006-AC02 -> [REQ-QML-006-AC02](../REQUIREMENTS.md#req-qml-006--bindings-and-property-aliases)
- QML-006-AC03 -> [REQ-QML-006-AC03](../REQUIREMENTS.md#req-qml-006--bindings-and-property-aliases)
- QML-006-AC04 -> [REQ-QML-006-AC04](../REQUIREMENTS.md#req-qml-006--bindings-and-property-aliases)
- QML-007-AC01 -> [REQ-QML-007-AC01](../REQUIREMENTS.md#req-qml-007--javascript-handlers-and-signals)
- QML-007-AC02 -> [REQ-QML-007-AC02](../REQUIREMENTS.md#req-qml-007--javascript-handlers-and-signals)
- QML-007-AC03 -> [REQ-QML-007-AC03](../REQUIREMENTS.md#req-qml-007--javascript-handlers-and-signals)
- QML-007-AC04 -> [REQ-QML-007-AC04](../REQUIREMENTS.md#req-qml-007--javascript-handlers-and-signals)
- QML-008-AC01 -> [REQ-QML-008-AC01](../REQUIREMENTS.md#req-qml-008--qtc-exposure-bridge)
- QML-008-AC02 -> [REQ-QML-008-AC02](../REQUIREMENTS.md#req-qml-008--qtc-exposure-bridge)
- QML-008-AC03 -> [REQ-QML-008-AC03](../REQUIREMENTS.md#req-qml-008--qtc-exposure-bridge)
- QML-008-AC04 -> [REQ-QML-008-AC04](../REQUIREMENTS.md#req-qml-008--qtc-exposure-bridge)
- QML-009-AC01 -> [REQ-QML-009-AC01](../REQUIREMENTS.md#req-qml-009--qt-project-and-resource-metadata)
- QML-009-AC02 -> [REQ-QML-009-AC02](../REQUIREMENTS.md#req-qml-009--qt-project-and-resource-metadata)
- QML-009-AC03 -> [REQ-QML-009-AC03](../REQUIREMENTS.md#req-qml-009--qt-project-and-resource-metadata)
- QML-009-AC04 -> [REQ-QML-009-AC04](../REQUIREMENTS.md#req-qml-009--qt-project-and-resource-metadata)
- QML-010-AC01 -> [REQ-QML-010-AC01](../REQUIREMENTS.md#req-qml-010--deterministic-graph-and-provenance)
- QML-010-AC02 -> [REQ-QML-010-AC02](../REQUIREMENTS.md#req-qml-010--deterministic-graph-and-provenance)
- QML-010-AC03 -> [REQ-QML-010-AC03](../REQUIREMENTS.md#req-qml-010--deterministic-graph-and-provenance)
- QML-010-AC04 -> [REQ-QML-010-AC04](../REQUIREMENTS.md#req-qml-010--deterministic-graph-and-provenance)
- QML-011-AC01 -> [REQ-QML-011-AC01](../REQUIREMENTS.md#req-qml-011--incremental-correctness)
- QML-011-AC02 -> [REQ-QML-011-AC02](../REQUIREMENTS.md#req-qml-011--incremental-correctness)
- QML-011-AC03 -> [REQ-QML-011-AC03](../REQUIREMENTS.md#req-qml-011--incremental-correctness)
- QML-011-AC04 -> [REQ-QML-011-AC04](../REQUIREMENTS.md#req-qml-011--incremental-correctness)
- QML-012-AC01 -> [REQ-QML-012-AC01](../REQUIREMENTS.md#req-qml-012--failure-handling-and-persistence)
- QML-012-AC02 -> [REQ-QML-012-AC02](../REQUIREMENTS.md#req-qml-012--failure-handling-and-persistence)
- QML-012-AC03 -> [REQ-QML-012-AC03](../REQUIREMENTS.md#req-qml-012--failure-handling-and-persistence)
- QML-012-AC04 -> [REQ-QML-012-AC04](../REQUIREMENTS.md#req-qml-012--failure-handling-and-persistence)
- QML-013-AC01 -> [REQ-QML-013-AC01](../REQUIREMENTS.md#req-qml-013--user-facing-graph-consumers)
- QML-013-AC02 -> [REQ-QML-013-AC02](../REQUIREMENTS.md#req-qml-013--user-facing-graph-consumers)
- QML-013-AC03 -> [REQ-QML-013-AC03](../REQUIREMENTS.md#req-qml-013--user-facing-graph-consumers)
- QML-013-AC04 -> [REQ-QML-013-AC04](../REQUIREMENTS.md#req-qml-013--user-facing-graph-consumers)
- QML-014-AC01 -> [REQ-QML-014-AC01](../REQUIREMENTS.md#req-qml-014--platform-and-compatibility-evidence)
- QML-014-AC02 -> [REQ-QML-014-AC02](../REQUIREMENTS.md#req-qml-014--platform-and-compatibility-evidence)
- QML-014-AC03 -> [REQ-QML-014-AC03](../REQUIREMENTS.md#req-qml-014--platform-and-compatibility-evidence)
- QML-014-AC04 -> [REQ-QML-014-AC04](../REQUIREMENTS.md#req-qml-014--platform-and-compatibility-evidence)
- QML-015-AC01 -> [REQ-QML-015-AC01](../REQUIREMENTS.md#req-qml-015--documentation-and-upstream-delivery)
- QML-015-AC02 -> [REQ-QML-015-AC02](../REQUIREMENTS.md#req-qml-015--documentation-and-upstream-delivery)
- QML-015-AC03 -> [REQ-QML-015-AC03](../REQUIREMENTS.md#req-qml-015--documentation-and-upstream-delivery)
- QML-015-AC04 -> [REQ-QML-015-AC04](../REQUIREMENTS.md#req-qml-015--documentation-and-upstream-delivery)
- QML-016-AC01 -> [REQ-QML-016-AC01](../REQUIREMENTS.md#req-qml-016--qt-c-signals-slots-and-connections)
- QML-016-AC02 -> [REQ-QML-016-AC02](../REQUIREMENTS.md#req-qml-016--qt-c-signals-slots-and-connections)
- QML-016-AC03 -> [REQ-QML-016-AC03](../REQUIREMENTS.md#req-qml-016--qt-c-signals-slots-and-connections)
- QML-016-AC04 -> [REQ-QML-016-AC04](../REQUIREMENTS.md#req-qml-016--qt-c-signals-slots-and-connections)
- QML-017-AC01 -> [REQ-QML-017-AC01](../REQUIREMENTS.md#req-qml-017--bidirectional-qml-and-c-object-integration)
- QML-017-AC02 -> [REQ-QML-017-AC02](../REQUIREMENTS.md#req-qml-017--bidirectional-qml-and-c-object-integration)
- QML-017-AC03 -> [REQ-QML-017-AC03](../REQUIREMENTS.md#req-qml-017--bidirectional-qml-and-c-object-integration)
- QML-017-AC04 -> [REQ-QML-017-AC04](../REQUIREMENTS.md#req-qml-017--bidirectional-qml-and-c-object-integration)
- QML-018-AC01 -> [REQ-QML-018-AC01](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)
- QML-018-AC02 -> [REQ-QML-018-AC02](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)
- QML-018-AC03 -> [REQ-QML-018-AC03](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)
- QML-018-AC04 -> [REQ-QML-018-AC04](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)
- QML-018-AC05 -> [REQ-QML-018-AC05](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)
- QML-018-AC06 -> [REQ-QML-018-AC06](../REQUIREMENTS.md#req-qml-018--installed-project-adoption-hardening)

## Increment and package aliases

Packages retain their parent increment and suffix. Links lead to the owning
increment section; completion and dependencies remain in the [plan](PLAN.md).

- QML-00 -> [INC-QML-00](PLAN.md#inc-qml-00--baseline-and-parser-decision)
- QML-01 -> [INC-QML-01](PLAN.md#inc-qml-01--discovery-and-minimal-declarations)
- QML-01a -> [INC-QML-01a](PLAN.md#inc-qml-01--discovery-and-minimal-declarations)
- QML-01b -> [INC-QML-01b](PLAN.md#inc-qml-01--discovery-and-minimal-declarations)
- QML-02 -> [INC-QML-02](PLAN.md#inc-qml-02--modules-and-component-scope)
- QML-02a -> [INC-QML-02a](PLAN.md#inc-qml-02--modules-and-component-scope)
- QML-02b -> [INC-QML-02b](PLAN.md#inc-qml-02--modules-and-component-scope)
- QML-02c -> [INC-QML-02c](PLAN.md#inc-qml-02--modules-and-component-scope)
- QML-03 -> [INC-QML-03](PLAN.md#inc-qml-03--bindings-aliases-javascript-and-signals)
- QML-03a -> [INC-QML-03a](PLAN.md#inc-qml-03--bindings-aliases-javascript-and-signals)
- QML-03b -> [INC-QML-03b](PLAN.md#inc-qml-03--bindings-aliases-javascript-and-signals)
- QML-03c -> [INC-QML-03c](PLAN.md#inc-qml-03--bindings-aliases-javascript-and-signals)
- QML-04 -> [INC-QML-04](PLAN.md#inc-qml-04--qtc-exposure-signals-and-access-to-qml)
- QML-04a -> [INC-QML-04a](PLAN.md#inc-qml-04--qtc-exposure-signals-and-access-to-qml)
- QML-04b -> [INC-QML-04b](PLAN.md#inc-qml-04--qtc-exposure-signals-and-access-to-qml)
- QML-04c -> [INC-QML-04c](PLAN.md#inc-qml-04--qtc-exposure-signals-and-access-to-qml)
- QML-05 -> [INC-QML-05](PLAN.md#inc-qml-05--build-module-and-resource-metadata)
- QML-06 -> [INC-QML-06](PLAN.md#inc-qml-06--incremental-updates-watch-and-caches)
- QML-06a -> [INC-QML-06a](PLAN.md#inc-qml-06--incremental-updates-watch-and-caches)
- QML-06b -> [INC-QML-06b](PLAN.md#inc-qml-06--incremental-updates-watch-and-caches)
- QML-07 -> [INC-QML-07](PLAN.md#inc-qml-07--consumers-support-matrix-and-upstream-delivery)
- QML-07a -> [INC-QML-07a](PLAN.md#inc-qml-07--consumers-support-matrix-and-upstream-delivery)
- QML-07b -> [INC-QML-07b](PLAN.md#inc-qml-07--consumers-support-matrix-and-upstream-delivery)
- QML-08 -> [INC-QML-08](PLAN.md#inc-qml-08--installed-project-adoption-hardening)
- QML-08a -> [INC-QML-08a](PLAN.md#inc-qml-08--installed-project-adoption-hardening)
- QML-08b -> [INC-QML-08b](PLAN.md#inc-qml-08--installed-project-adoption-hardening)
- QML-08c -> [INC-QML-08c](PLAN.md#inc-qml-08--installed-project-adoption-hardening)
