## graphify

When available, this project's Graphify knowledge graph is at graphify-out/.

Rules:
- When working on Graphify itself, use the repository's existing Graphify guidance. For codebase questions, prefer scoped graph queries where available; use the report for broad orientation. Do not use the graph as evidence when the task concerns the graph's correctness itself.
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)

# Graphify repository instructions

These standards govern Qt/QML source support and related Graphify improvements.
Preserve upstream architecture, contribution policy, public contracts, licensing,
and supported workflows unless an explicit, documented decision changes them.
User instructions take precedence; more specific repository instructions apply
within their scope. Follow the exact [extractor migration playbook](graphify/extractors/MIGRATION.md)
for mechanical extractor ports; its verbatim-move constraints take precedence over
general refactoring and commenting rules below.

The [audit](docs/qt-qml/AUDIT.md) describes the inspected baseline. The
[requirements](docs/REQUIREMENTS.md), [architecture](docs/qt-qml/ARCHITECTURE.md),
[design](docs/qt-qml/DESIGN.md), [increment plan](docs/qt-qml/PLAN.md), and
[traceability](tests/TRACEABILITY.md) describe the proposed extension and its
evidence. Planned support, planned tests, and workflow policy are not implemented
capabilities. Reverify moving upstream and service configuration before relying
on an old snapshot.

## Workspace and version control discipline

Treat the approved workspace as the canonical working directory. Do not move work
to another checkout or worktree without the user's authorization. Approval to
create or switch a branch is not approval to change the workspace path. After an
approved workspace change, report both paths and verify the destination repository
and branch before editing.

Before the first repository change, inspect the working tree, branch, remotes,
recent commits, applicable instructions, and overlapping work. Preserve user and
collaborator changes. Continue a feature branch when the work belongs to its
cohesive scope; otherwise inspect the current upstream base and create a focused
branch. Use `codex/` unless the user or repository policy specifies another prefix.
Do not implement new features directly on the default branch.

Clarify unresolved behavior that materially affects scope, architecture, or
testable acceptance while continuing independent authorized work. Infer routine,
reversible implementation details from agreed requirements and repository context.
Record a scope decision before mixing unrelated work into an active increment.

Keep commits small and cohesive. Use clear types such as `feat:`, `fix:`, `test:`,
`refactor:`, `docs:`, and `ci:`. Include requirements, comments, documentation, and
tests with the behavior they describe. Review the staged and complete diff before
committing; exclude unrelated changes, local configuration, and generated outputs
unless those outputs are required by the upstream generation workflow.

Never discard or rewrite another contributor's work to simplify a task. Do not
force-push the default or a shared branch. Rewrite a personal feature branch only
when authorized and permitted by repository policy. Coordinate Git operations
with the collaboration rules below.

## GitHub API and credential discipline

Use Git CLI and Git transport for local history, fetch, push, and branch work.
Use scriptable GitHub REST or GraphQL APIs, directly or through GitHub CLI, for
server-side operations. UI mutation requires the user's explicit instruction to
use that interface. Fetch before integrating incoming commits; inspect local work
and choose a fast-forward, rebase, or merge under repository policy. Push an
explicit local branch to an explicit remote branch.

Before a server mutation, verify the host, repository, source and target branches,
and expected commit SHA where applicable. Inspect existing pull requests before
creating overlapping work. Confirm resulting state from the API response and a
follow-up read when necessary. Report missing permissions without substituting an
unapproved UI mutation. Account access does not authorize unrelated operations.

Obtain credentials from a credential manager or protected environment. Never print
them, put them in logged arguments, write them into repository or temporary files,
or include them in documentation, screenshots, URLs, commits, or fixtures. Use
only the permissions needed for the authorized operation. Preserve upstream
license and attribution notices when reusing code, grammars, or fixtures.

### Efficient pull-request pipeline sequencing

When publication is in scope, finish proportionate local verification, push the
explicit feature branch, and create or update its pull request promptly. Let the
pull-request event own full pre-merge validation for the reviewed revision. Do not
first dispatch a duplicate full feature-branch workflow or start another while
the intended run is queued or active.

Inspect actual workflow triggers before dispatching. When changing CI, avoid
equivalent push/PR duplication while retaining required default-branch, release,
and merge-queue checks. Use workflow-specific concurrency for obsolete PR runs;
do not cancel required post-merge proof or cleanup when another commit arrives.
Merge-group checks test a different integration commit and are not duplicate PR
checks. These are configuration requirements when those workflows are introduced,
not claims that the baseline already implements them.

Record PR head SHA, base SHA, tested checkout SHA, workflow, event, run URL, and
conclusion. A PR run may test a synthetic merge commit; distinguish it from the
source head and eventual merged commit. New source commits, changed integration
bases, and changed workflows need evidence applicable to the new reviewed state.

For a failed gate, inspect the exact job and logs, reproduce at the lowest faithful
boundary, correct the behavior and regression/documentation gap, and push the new
SHA for normal validation. Retry an individual infrastructure failure only after
distinguishing it from a deterministic product failure. Never weaken assertions,
required checks, or protection rules merely to obtain a successful result.

Merge only when authorized, review requirements are satisfied, and required checks
for the reviewed state pass. Re-read the PR before merging and bind the operation
to its reviewed head SHA where the API permits. Confirm the resulting default-
branch commit and intended changes under the selected merge method; squash and
rebase need not retain source ancestry. Track required automatic post-merge
validation for that exact resulting SHA to a terminal result. Pre-merge and
post-merge validation are distinct controls.

### Protected proof pipeline sequencing

This policy applies when an increment introduces protected proof, rehearsal,
publication, or deployment. The audited baseline has no protected proof workflow;
do not describe this policy as existing protection or introduce infrastructure
solely to satisfy a hypothetical future need.

Design the normal sequence as successful PR validation, an authorized merge bound
to the reviewed head, then validation and protected proof of the exact resulting
default-branch commit. Proof depends on mandatory validation and verified revision
identity. Avoid a third full validation workflow solely to expose a proof job.

Run privileged jobs only from an explicitly trusted workflow and permitted ref,
with approved environment protection and least necessary permissions. Verify the
repository, workflow revision, event, ref, checkout SHA, environment, and required
validation evidence before releasing credentials or performing protected actions.
Prefer bounded credentials with constrained trust claims where supported.

PR code and artifacts are untrusted. Do not use `pull_request_target`, privileged
`workflow_run`, or another privileged event to check out and execute an untrusted
PR revision or executable artifacts with secrets or write credentials. Verify
originating repository, event, run, revision, and integrity before a downstream
proof consumes validation artifacts through a documented trust boundary.

If proof selection requires temporary enablement before its intended trigger,
prepare narrowly scoped, expiring, single-use authorization after pre-merge gates
pass and before the guarded merge. Bind it to the reviewed head, base, and intended
operation; verify the actual merge result and proof checkout before consuming it.
Do not assume the eventual merge SHA is known beforehand or let a repository-wide
flag authorize unrelated revisions.

Use GitHub's actual workflow, input, variable, and environment semantics. Variables
are not inherently protected secrets or exact-SHA authorization. Document when
each gate is evaluated; do not transplant another CI platform's variable-scope or
pipeline-creation assumptions. See the official [event documentation](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows)
and [environment protection documentation](https://docs.github.com/en/actions/how-tos/deploy/configure-and-manage-deployments/manage-environments).

If an automatic run omits required proof, report the sequencing miss. Use one
deliberate recovery invocation of the documented trusted workflow for the intended
revision, retaining all validation and protection gates. Reuse prior validation
only when the workflow verifies trustworthy evidence for that same revision.
Do not hide the miss with ambiguous retries or repeated full pipelines.

Revoke temporary enablement and credentials as applicable after success, failure,
cancellation, or timeout; verify absence and required resource cleanup. Include
abandoned pre-merge activation in cleanup. Cancellation does not prove cleanup
ran. Unconfirmed cleanup remains outstanding work.

## Requirements discipline

Whenever a user requests a new feature, behavioural change, or removal of existing
behaviour, update `docs/REQUIREMENTS.md` in the same change set without waiting for a
separate request.

Each requirement must:

1. Have a stable identifier.
2. Describe externally observable behaviour.
3. Include concrete, independently testable acceptance criteria.
4. State its implementation status accurately.
5. Be updated when implementation behaviour changes.

Assign each acceptance criterion a stable identifier in the established scheme.
Include success, boundary or rejection, and relevant failure outcomes; explain
inapplicable categories. These obligations apply to all product requirements,
including corrections discovered during development or troubleshooting.

Follow any pre-existing numbering standard in the owning document or component.
Preserve requirement `QML-001` style IDs, criterion `QML-001-AC01` style IDs,
`QML-00` style increment IDs, and existing `D1` style architecture decision IDs.
Extend the same scheme for new entries; do not introduce competing IDs, renumber existing
entries, or reuse retired IDs for unrelated behavior. Preserve external references
when reorganizing documentation.

Identify affected acceptance IDs before implementation. Update requirements,
design, comments, tests, and traceability together when behavior changes. Do not
silently weaken acceptance to match an implementation. Maintain planned,
implemented, verified, and explicitly unverified states; invalidate stale
verification evidence when contracts change.

When requirements, code, documentation, and tests disagree, record the discrepancy
and establish intended behavior from agreed requirements and design before changing
code or expectations. Explain corrected requirements or expectations in the change
set. Resolve material uncertainty with the user while continuing independent work.

Map every affected acceptance ID to an exact automated test or explicit manual/
system gap in `tests/TRACEABILITY.md`. Record applicability, profile/platform,
executed command, result, and limitations. A requirement is Verified only when
every applicable criterion individually passes. Skips, unexecuted checks, aggregate
counts, and a happy path do not establish verification. A not-applicable decision
needs a specific documented reason, not a way to bypass a failed criterion.

Maintain `docs/qt-qml/PLAN.md` with dependencies, scope, acceptance IDs, evidence,
compatibility impact, and exit conditions. Each increment produces a useful,
independently reviewable result. Language admission or one smoke fixture does not
establish comprehensive Qt/QML support.

## Collaboration discipline

The repository, versioned requirements/design, issues, and PRs are the shared source
of truth. Record architectural decisions, workflow changes, ownership, compatibility
constraints, and handoffs there; private chat history is not a durable contract.

Before changing a component, inspect the working tree, branch, relevant incoming
changes, known overlapping issues/PRs, and active contributor or agent work. Agree
file and behavior ownership before concurrent edits. Keep one active owner for
conflict-prone files. If overlap appears, stop the conflicting edits and resolve
ownership or split responsibilities; continue independent authorized work.

Coordinate before editing files the user or another contributor is changing.
Preserve saved and unsaved work; inspect available editor/tool state and ask only
where missing information would make the operation disruptive. Before switching
branches, integrating, rebasing, merging, or deleting branches, verify there is no
unfinished operation or collaborator work that the operation would disrupt.

Independent contributors use their own authorized identities and credentials;
never share personal tokens. Give each cohesive independent task a focused branch.
Delegated agents within one authorized task may share its checkout with disjoint
editing responsibilities and one integration owner. They must coordinate staging,
commits, and other Git mutations; delegation does not require inventing identities
or copying credentials.

Integrate through reviewed commits and versioned handoffs, not unreviewed file
copies between checkouts. Handoffs identify changed contracts, acceptance IDs,
verification, remaining gaps, and ownership. Review overlapping upstream work
before duplicating a feature, replacing old function bodies, or creating a PR.

## Application-language discipline

Graphify's runtime, extraction pipeline, resolvers, graph processing, CLI, and
service integrations remain Python. Implement Qt/QML support through existing or
deliberately documented extension boundaries. Do not rewrite the host application
in C++/QML or add a second runtime because the analyzed corpus uses those languages.

C++, QML, JavaScript, CMake, qmake, Qt resource/type metadata, and generated sources
are analysis inputs and fixtures. Ordinary analysis must not execute corpus code,
load QML components, run project build hooks, or require a Qt SDK.

Native parser bindings or executable Qt compatibility fixtures require a documented
increment covering purpose, dependency/licensing impact, supported installation
matrix, ownership, and verification. Keep validation oracles separate from the
Graphify runtime. Qt 6 with both CMake and qmake is the agreed initial target;
legacy profiles require separate acceptance and evidence.

Preserve native Qt mechanisms in analysis: signals, slots, emissions, connections,
meta-object access, and both directions of QML/C++ integration. Keep connection
facts distinct from direct calls; preserve uncertainty, scope, and provenance.
Do not fabricate runtime ordering, thread safety, or dynamic targets from static
evidence, or conflate QML `id` with `objectName`.

## Build-system and packaging discipline

Preserve Graphify's Python/uv packaging workflow. CMake and qmake support describes
analyzed projects; neither becomes Graphify's host build system. Changes to language,
canonical build system, or packaging architecture need an explicit design decision.

Update `pyproject.toml`, lockfile, package manifests, parser/fixture resources, and
CI together when their contracts change. Verify optional dependency absence,
offline installation/runtime behavior, packaging contents, parser API compatibility,
and supported platforms as applicable. Respect licensing and provenance.

Keep builds, binaries, caches, IDE user settings, personal machine paths, and
secret-bearing configuration out of version control. Use upstream generators for
generated assistant artifacts; do not hand-edit generated output.

## Automated-testing discipline

Meaningful tests accompany each feature, behavior change, bug fix, and refactor
without a separate request. Documentation-only changes need proportionate document
checks. Verbatim extractor ports follow their migration playbook; add missing
characterization in a separate preparatory change rather than modifying forbidden
test files during the mechanical port.

Before implementation, record a small acceptance matrix covering relevant success,
rejection, boundaries, state transitions, persistence, diagnostics, and regressions.
For analyzer changes, include source ranges, scope/ambiguity, malformed or partial
input, false-positive protection, mixed-language relationships, stable IDs,
cold/warm and full/incremental parity, stale-edge removal, and graph/export
preservation where affected. Include metadata-only, C++-only, and QML-only updates
when they can invalidate shared analysis.

Every failure exposed by development, manual, integration, or system verification
automatically creates a regression-coverage obligation for its correction.
Reproduce it at the lowest faithful automated production boundary and add coverage
that fails before the fix. Review adjacent risks: paired settings, validation order,
retries, state transitions, persistence ordering, rollback, and diagnostics where
relevant. Literal-only assertions do not prove an interaction defect is fixed.

Exercise production interfaces. Fakes may isolate external or expensive boundaries
but must not reproduce the behavior being tested. Test seams must be used by the
real production path. Keep tests deterministic, offline by default, isolated, and
free of credentials or proprietary source.

If faithful reproduction needs unavailable external/native infrastructure, retain
the strongest deterministic offline contract/integration protection and record an
exact system procedure: fixture/setup, action, expected evidence, failure signature,
cleanup/rollback, owner, and remaining gap. Manual checks supplement available
automation. Do not claim verification until the required evidence exists.

Test actual persistence completion and failure, not only in-memory results. Force
at least one real failure at each new persistence boundary. Verify rejected/failed
operations preserve prior graph/cache/data unless acceptance explicitly defines a
partial update; prove recovery and repeat application where idempotency is promised.

Update traceability with the production change. Map acceptance IDs to exact tests
and distinguish unit, integration, packaging, consumer, and system evidence. Use
acceptance IDs in names or metadata where practical. Python coverage measures
Graphify; it does not prove execution coverage of analyzed C++/QML applications.
QtTest/Qt Quick Test applies to executable Qt components or selected validation
oracles; source analysis uses the existing Python test framework.

Run focused tests during development and required compatibility, lint, type,
packaging, and generated-artifact checks before code handoff as applicable. Shared
boundary changes require unrelated-language regressions. Report exact commands,
failures, skips, baseline exceptions, and unavailable dependencies. Inspect meaningful
uncovered changed branches; overall coverage or successful parsing alone does not
prove resolution correctness. Change CI when new evidence needs dependencies,
platform jobs, services, artifacts, or reports; discovered-but-skipped tests do not pass.

Before completion, confirm every changed behavior and applicable criterion has
executable coverage or an explicit gap, tests exercise production and failure paths,
and regression assertions exclude the original failure. Requirements, design,
comments, tests, and traceability must agree. Resolve or explicitly report new
failures and lost meaningful coverage. Do not weaken assertions, remove regressions,
or change durable data merely to make checks pass.

## Code-commenting discipline

Maintain explanatory comments automatically with features, behavior changes, and
refactors. Explain each new module's purpose and significant cohesive sections'
responsibilities, ownership, data flow, and constraints. A clear module docstring
or existing section commentary may satisfy that purpose; avoid duplicate prose.

Place concise commentary before introduced or meaningfully changed cohesive blocks
in production code, tests, build scripts, and resource manifests. Explain why the
block exists, what it owns, and important resolution, ordering, persistence, or
testing constraints. Follow upstream formatting and avoid unrelated mass edits.
Verbatim migration work preserves existing text under its specialized playbook.

Test commentary identifies the acceptance/regression scenario, fixture state,
action, and observable outcome; descriptive test docstrings may supply it. Build,
dependency, and resource commentary explains group responsibilities and necessary
synchronization of packages, grammars, fixtures, manifests, and CI.

For maintained QML examples or actual UI components, explain meaningful component
roles, nested ownership, and important input/layout boundaries. Document parser
fixtures without obscuring deliberate malformed syntax or changing the test case.
Do not narrate self-evident syntax, comment every line, or repeat trivial properties.
Update/remove stale comments in the same change set and check their consistency
with requirements, production behavior, and tests before completion.

## Error and diagnostic discipline

Before changing an input, action, or operational boundary, record diagnostic impact
for successful completion, rejection, recoverable failure, and integrity/recovery
failure. Give a concrete reason for each inapplicable category. Distinguish missing
parser, malformed/partial parse, unresolved resolution, cache failure, and graph-
write failure; do not hide them behind one generic success/failure message.

New Qt/QML diagnostics need stable codes, severity, owning boundary, source context
where available, actionable wording, and documented recovery/retry policy. Reuse
upstream conventions; do not introduce a separate logger framework or rewrite all
existing warnings merely to standardize the extension. Create the canonical
`docs/qt-qml/ERRORS.md` with the first diagnostic contract and update it, requirements,
and tests together. Keep planned codes distinct from implemented contracts.

Inspect actual read, cache, serialization, write, and replacement completion.
Define partial-result policy, retention of the previous valid graph, retry safety,
and recovery guidance. Check explicit results and exceptions at the owning boundary;
in-memory success does not prove a committed output. Preserve persistence owner and
ordering. Document schema compatibility, migration, retained-data behavior, and
rollback/recovery when those contracts change.

Keep diagnostics/evidence bounded and safe. Do not log credentials, private source,
personal data, sensitive raw provider bodies, or identifier-bearing URLs. Use safe
stages, codes, counts, timings, and correlation identifiers. Retain meaningful state
transitions once per change rather than every poll. Test redaction, delimiter
injection, malformed metadata, and actual failure results where affected.

Treat analyzed repositories as untrusted data. Do not execute project scripts,
embedded JavaScript, build hooks, or extracted instructions. Bound discovery,
parsing, resolution, and output according to the documented threat model. Verify
dependency/fixture provenance before publishing artifacts.

## Modularity discipline

Choose focused responsibility boundaries, small public interfaces, and explicit
dependencies before splitting files. The default ceiling for new handwritten
production and test files is **300 physical lines**. Generated files, intentional
corpus fixtures, and documentation are outside that source-file limit. A justified
cohesion exception needs a versioned rationale, owner, measured ceiling, and review
or extraction exit condition; routine exceptions do not require separate approval.

For touched oversized legacy files, record the current size, permitted ceiling,
owner, reason, and focused extraction path in the design/code reference or PR.
Do not add undocumented growth. Preserve upstream migration sequencing; do not
combine an unrelated extraction merely to satisfy size policy. File size is a
constraint to explain, not evidence of good ownership or permission to make
arbitrary fragments, forwarding-only layers, or speculative frameworks.

Keep one authoritative owner for mutable state. Workers receive scan root and
dependencies explicitly; do not add ambient mutable project/root state. Source
facts belong to their owning file/declaration, indexes to one analysis run, and
cache/persistence to explicit owners. Preserve extractor facade/import direction;
extractor children must not import `graphify.extract`.

Preserve stable IDs, nested resolver references, relative provenance, locations,
and distinct relationship mechanisms through remapping, cache, incremental
reconstruction, and export. Do not solve graph edge collapse by silently replacing
one relationship with another. Follow the documented graph compatibility decision.

## Incremental refactoring discipline

Before extracting a responsibility, record current/proposed owners, inputs/outputs,
dependency direction, state/cache lifetime, persistence owner, observable ordering,
and affected contracts/tests. Before moving production implementation, add missing
characterization of meaningful boundaries, rejection/failure, and ordering where
affected.
For verbatim extractor ports, do characterization in a separate preparatory change
and follow the specialized one-language/import/test constraints exactly.

Move one cohesive responsibility per increment. Preserve behavior, ordering,
IDs, locations, diagnostics, and graph relationships during a mechanical move.
Separate intentional fixes and design changes from moves. Keep registries/facades
thin and preserve public compatibility without moving domain logic into a generic
controller or utility module.

Transitional forwarders identify remaining callers and a removal exit condition;
they must not become permanent duplicate owners. Report actual responsibility
removed, remaining debt, and the next cohesive step. Fewer lines or additional
files alone do not establish a completed refactor.

## Architecture and design documentation discipline

The root `ARCHITECTURE.md` remains the upstream system description. Maintain
`docs/qt-qml/ARCHITECTURE.md` for extension context, ownership, constraints, quality
attributes, and durable decisions; `docs/qt-qml/DESIGN.md` for interfaces, data flow,
schema, resolution, failure policy, and extension procedures. Separate observed current
implementation, proposed design, implemented behavior, and verified support.

Review documentation impact for every feature, fix, refactor, build/integration
change, and material test-infrastructure change, even when public API names stay
the same. Examine ownership, dependency direction, cache/persistence ordering,
recovery, worker/root handling, schema, and consumer compatibility. Update affected
documents in the same change set, or record why no update is needed.

Use stable ADR identities for material decisions, alternatives, tradeoffs, and
compatibility constraints; do not renumber them during editing. Update
`docs/qt-qml/CODE_REFERENCE.md` when public interfaces, ownership, graph contracts,
or meaningful extension seams change. Document migrations and operational recovery
only where those concerns exist or change; proposed files/APIs must remain labeled.

Keep one canonical source per concern and avoid case-only filename aliases.
Requirements describe behavior, design describes ownership/implementation,
traceability records evidence, and the error catalog defines diagnostic contracts.
Link specialist contracts rather than duplicating catalogs. Verify local links,
acceptance references, status consistency, and relevant generated documentation.
Private projects, infrastructure, personal paths, and secrets must not enter public
policy, examples, fixtures, comments, or retained evidence.

## Evidence-led troubleshooting discipline

Trace symptoms through discovery, parser, source facts, resolution, graph projection,
cache/update, persistence, and the affected consumer. Inspect the owning code,
configuration, diagnostics, and actual durable outputs at each relevant boundary.
Use the smallest faithful reproduction and explain disagreement between sources.
A successful build, green dashboard, parser success, or aggregate coverage does
not prove correct resolution, persisted output, or feature acceptance.

Bind evidence to source/configuration revision, parser/dependency versions, fixture
state, platform, and actual stage under investigation. Compare cold/warm and
full/incremental results when relevant. Inspect prior persisted results, partial
state, and stale-edge cleanup rather than assuming logs reflect durable success.

Before retrying, identify the failed boundary, check cleanup and idempotency, and
verify another attempt is not active. Preserve the failed evidence. Do not alter
durable data, expected behavior, assertions, permissions, polling deadlines, or
protection merely to clear an alert or produce a successful result. Changes to
those contracts require evidence and a documented reason.

Inspect necessary sensitive evidence only through authorized protected channels;
retain redacted conclusions and minimal public reproductions. Turn confirmed
failures into regression obligations and diagnostic/documentation improvements.
Distinguish product defects, configuration errors, infrastructure failures,
unsupported inputs, and unresolved analysis instead of conflating them.

## Audit completion and handoff discipline

At the end of an audit, review this standard against actual findings and agreed
development requirements. Strengthen reusable rules where the evidence exposes a
gap, preserve upstream constraints, and sanitize any imported private reference.
Record remaining implementation and verification gaps explicitly.

Before declaring an increment complete, review its complete diff, each affected
acceptance criterion, collaboration ownership, test quality, diagnostic handling,
modularity, architecture/design impact, compatibility, and public-data safety.
Report what changed, why, exact verification and limitations, and pending work.
Documentation-only policy changes do not imply runtime features were implemented.

For published delivery, distinguish local checks, PR validation, merge-group checks,
post-merge validation, and protected proof. Report relevant source/integration/
resulting SHAs, workflow URLs, and terminal conclusions. A green aggregate does
not prove omitted, skipped, or `continue-on-error` gates passed. Required proof or
cleanup still pending/failed means merged delivery is not fully verified. State
remote verification limits when it is outside the authorized scope.

If an increment changes an actual UI, work on one cohesive interaction, establish
a baseline, preserve approved manual changes, and iterate from human feedback.
Automate functional, accessibility, resizing, and deterministic layout behavior
where practical; subjective visual acceptance remains human-led. Source-analysis
fixtures do not imply Graphify has a Qt UI.
