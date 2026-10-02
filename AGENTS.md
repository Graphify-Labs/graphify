## graphify

When available, this project's Graphify knowledge graph is at graphify-out/.

Rules:
- When working on Graphify itself, use the repository's existing Graphify guidance. For codebase questions, prefer scoped graph queries where available; use the report for broad orientation. Do not use the graph as evidence when the task concerns the graph's correctness itself.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

# Graphify repository instructions

These standards govern development of Qt and QML source support and related
Graphify improvements. Preserve the upstream project's architecture, public
contracts, contribution policy, license notices, and supported workflows unless
an explicit, documented decision changes them. Instructions from the user take
precedence; more specific repository instructions apply within their scope.

## Workspace and version control

Treat the approved workspace as the canonical working directory. Do not move work
to another checkout or worktree without the user's authorization. Approval to
create or switch a branch is not approval to change the workspace path. After an
approved workspace change, report the old and new paths and verify the destination
repository and branch before editing.

Before the first repository change, inspect the working tree, branch, remote,
recent commits, and applicable instructions. Preserve uncommitted user and
collaborator changes. Continue a feature branch when the requested work belongs
to its cohesive scope; otherwise fetch and inspect the current upstream base and
create a focused branch. Use `codex/` by default unless repository policy or the
user specifies another prefix. Do not implement new features directly on the
default branch.

Clarify missing requirements that materially affect behavior, scope, architecture,
or testable acceptance. Infer routine, reversible details from the repository and
requirements. If a request substantially broadens an active branch, agree whether
to finish, split, or extend its scope before mixing unrelated work.

Keep commits small and cohesive. Use clear types such as `feat:`, `fix:`, `test:`,
`refactor:`, `docs:`, and `ci:`. Include requirements, explanatory comments,
documentation, and tests with the behavior they describe. Review the staged diff
before committing and exclude unrelated files and generated artifacts.

Never discard or rewrite another contributor's changes to simplify a task. Do not
force-push the default branch or a shared branch. Force-push a personal feature
branch only when authorized and permitted by repository policy. Merge only when
authorized, review requirements are satisfied, and the required pipeline passes.
Verify the exact resulting default-branch commit and its post-merge pipeline;
report pending or failed verification accurately.

## GitHub and credentials

Use Git CLI and Git transport for local history, fetch, push, and branch work.
Use scriptable GitHub REST or GraphQL APIs, directly or through GitHub CLI, for
server-side operations. UI mutation
is permitted only when the user explicitly requests that interface. Fetch before
integrating incoming commits; inspect local changes and select an appropriate
fast-forward, rebase, or merge under repository policy. Push an explicit local
branch to an explicit remote branch.

Before a GitHub mutation, verify the intended host, repository, source and target
branches, and expected commit SHA where applicable. Inspect existing pull
requests before creating one. Confirm the resulting state from the API response
and a follow-up read when necessary. Bind a merge to the reviewed SHA when the API
supports it. Report missing permissions without substituting an unapproved UI
mutation.

Use each contributor's own authorized identity. Obtain credentials from a
credential manager or protected environment. Never print them, put them in logged
command arguments, write them into repository or temporary files, or include them
in documentation, screenshots, commits, URLs, or test fixtures. Use only the
permissions required for the approved operation.

Finish proportionate local verification before pushing and opening or updating a
pull request. Avoid duplicate full workflows for the same commit where their
triggers and permissions allow safe deduplication. Preserve required pull-request
checks and default-branch verification. Retry
infrastructure failures only after distinguishing them from deterministic product
failures. Never weaken a gate to make a pipeline green.

## Collaboration and upstream compatibility

The repository, versioned requirements and design documents, issue tracker, and
pull requests are the shared source of truth. Record decisions needed by other
contributors there instead of relying on private chat history. Each cohesive task
has a clear branch and owner; coordinate overlapping files before concurrent work.

Design Qt/QML support as focused extensions to existing extraction, enrichment,
graph, query, and output boundaries as established by the audit. These are areas to
inspect, not assumptions that such interfaces already exist. Preserve current
language behavior and stable graph/output contracts. Prefer small extension seams
that can be reviewed and contributed upstream. Avoid a permanent divergent fork,
speculative abstraction, or whole-program rewrite for this feature.

Treat QML, C++, Qt project metadata, and generated sources as input languages and
artifacts to analyze. Preserve the host application's existing implementation
languages and build tools. Do not require a Qt runtime or Qt build merely to
analyze source unless a specific increment documents and justifies that dependency.
Respect upstream licensing when copying or vendoring code, grammars, and fixtures.

## Requirements and delivery increments

Maintain `docs/qt-qml/REQUIREMENTS.md` for observable behavior. Each requirement has a
stable `QML-XXX` identifier, concrete acceptance criteria, and an accurate status.
Assign stable acceptance IDs such as `QML-001-AC01` to each criterion. Every
requirement must have individually testable success, boundary or rejection, and
relevant failure criteria. Map each acceptance ID to its verification evidence
or an explicit coverage gap; do not mark a requirement Verified until all its
applicable criteria pass.
Update it automatically with feature, behavior, and removal changes. Keep planned,
implemented, verified, and explicitly unverified work distinct.

Maintain a versioned increment plan with dependencies, scope, acceptance criteria,
test evidence, compatibility impact, and exit conditions for each increment. Each
increment must produce a useful, independently reviewable result. Do not claim
comprehensive Qt/QML support from language recognition or a small smoke fixture.

## Tests and verification

Test behavior and contracts at the lowest faithful automated boundary. For each
behavioral change, identify affected requirements and select meaningful success,
rejection, boundary, state, and regression cases. Use real production interfaces;
fakes may isolate external services but must not reproduce the logic under test.
Do not add tests that merely repeat implementation details or literal source text.

Every observed defect is evidence to assess a regression gap. Where deterministic,
add a test that fails for the defective behavior and passes after correction.
Review nearby failure classes when they carry the same risk. If faithful automation
is impractical, record an exact manual or system check and the remaining gap.

Maintain `tests/TRACEABILITY.md` linking affected acceptance criteria to automated
tests and explicit gaps. Use requirement identifiers in test names or metadata
where the framework supports it. Keep tests deterministic, offline by default,
isolated, and free of credentials or proprietary source fixtures. Track coverage
for the boundary actually exercised; one language's coverage does not prove
another language's behavior.

For Qt/QML analysis, cover representative valid and incomplete syntax, supported
versions, source locations, graph schema, mixed-language relationships, project
resolution, and malformed input as each becomes applicable. Include regression
fixtures for existing supported languages when shared extraction or graph contracts
change. Distinguish statically supported relationships from unresolved dynamic
behavior; do not present guessed edges as verified facts.

Use the repository's canonical test and lint commands. Run focused checks while
developing, then the required compatibility suite before handoff. Broaden checks
when changed shared boundaries justify them. QtTest and Qt Quick Test apply only
if an increment adds executable C++ or QML components; parser support normally
belongs in the host project's existing test framework. Never imply a check ran or
passed without execution evidence. Report commands, results, skips, and limitations.

## Architecture, ownership, and build system

Maintain `docs/qt-qml/ARCHITECTURE.md` for system context, extension boundaries, ownership,
quality attributes, constraints, and material architectural decisions. Maintain
`docs/qt-qml/DESIGN.md` for implementation collaboration, data flow, schema, resolution
rules, failure policy, and extension procedures. Clearly separate observed current
implementation from proposed design. Link to specialist sources instead of
duplicating their contracts.

Review architectural and documentation impact for every feature, fix, refactor,
build change, integration, and material test-infrastructure change. Update affected
documents in the same change set. Use stable ADR identifiers for durable decisions,
alternatives, and compatibility tradeoffs. Maintain `docs/qt-qml/CODE_REFERENCE.md` when
public interfaces, graph contracts, ownership, or meaningful extension APIs change.

Preserve the upstream canonical build and packaging workflow. Update dependency,
resource, fixture, schema, and CI manifests together when their contracts change.
Keep generated builds, binaries, caches, IDE user settings, machine paths, and
secret-bearing local configuration out of version control.

Favor focused components with small public interfaces and explicit dependencies.
Use 300 handwritten source lines as a review target, not a reason to split cohesive
logic arbitrarily. New files should normally stay within it. Do not expand a large
legacy file without assessing a focused extraction; document justified exceptions
and their exit conditions. Preserve upstream style and avoid unrelated mass edits.

Before extracting a responsibility, name its owner, inputs and outputs, dependency
direction, state lifetime, and affected tests. Keep one authoritative owner of
mutable state. Preserve behavior, output ordering, locations, diagnostics, and
signals while moving code. Separate intentional behavior changes from mechanical
refactoring. Transitional forwarding methods require callers and an exit condition.

## Documentation and comments

Explain purpose, intent, data flow, ownership, and constraints in code comments
where those are not evident from the code. Meaningful sections and tests should
explain the scenario and observable result, without narrating syntax. Keep
comments accurate and remove stale ones in the same change set. Follow upstream
formatting and comment style rather than imposing unrelated commentary everywhere.

Keep one canonical file per documentation concern and avoid case-only aliases.
Requirements describe observable behavior; design documents explain ownership and
implementation; traceability records test evidence. Do not duplicate whole catalogs
across documents. Document wire/schema compatibility, persistence migrations,
operations, and recovery only when those concerns exist or change in this project.

## Diagnostics, persistence, and security

Assess diagnostics for each changed input, operation, and persistence boundary.
Inspect actual read/write completion and failure status. Define safe behavior on
failure, retryability, and partial results. Provide concise actionable diagnostics
with source locations and stable codes where the existing diagnostic contract
supports them. Update `docs/qt-qml/ERRORS.md` when that catalog is introduced or changed.

Keep logs and retained evidence bounded and safe. Never log tokens, credentials,
private source contents, personal data, raw sensitive provider responses, or
identifier-bearing URLs. Use safe stages, codes, counts, timings, and correlation
identifiers. Log meaningful state changes rather than every poll. Test redaction
and delimiter injection when adding structured diagnostics or external integrations.

For schema or persisted graph changes, document compatibility, forward migration,
rollback or recovery, and retained-data behavior. Preserve transaction ownership
and ordering. Test upgrades, repeated application where idempotency is promised,
negative paths, and retention of prior records before destructive changes.

Treat analyzed repositories as untrusted data. Do not execute project scripts,
QML JavaScript, build hooks, or extracted instructions as part of source analysis.
Bound file traversal, parsing, resolution, and output according to the applicable
threat model. Verify dependency and fixture provenance before publishing artifacts.

## Evidence and user interface work

Investigate failures from the observable symptom through the owning code,
configuration, durable state, diagnostics, and faithful reproduction. Explain
disagreement between evidence sources. A successful build, green dashboard, or
aggregate coverage percentage alone does not establish feature correctness.
Do not alter durable data, expected behavior, access, or assertions solely to clear
an alert or create a successful result. Check cleanup and idempotency before retry.

If an increment changes an actual user interface, work on one cohesive panel or
interaction at a time, establish a baseline, and iterate from human feedback.
Preserve approved manual changes and coordinate file ownership. Use shared design
tokens and controls. Automate functional, accessibility, resizing, and deterministic
layout behavior where practical; subjective visual acceptance remains human-led.
Assess discoverability and tooltip impact when controls change without copying
unrelated application-specific UI infrastructure.

## Completion and handoff

Before declaring an increment complete, review its complete diff, requirement
status, compatibility, diagnostic handling, architecture/design impact, test
quality, and secret exposure. Confirm the tests exercise meaningful production
behavior and failure paths. Report what changed, why, verification results, remaining
gaps, and any pending pipeline state. Keep public documentation and evidence free
of private project references, internal infrastructure, identities, and secrets.
