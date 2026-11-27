# Install sandbox instructions

## Required context

Before changing target-related data or code that consumes it, read `README.md`
and `specs/README.md`.

Before a non-trivial architecture, refactor, or replacement change:

1. Extract the observable contracts from the CLI, documented artifacts, YAML
   schema, status semantics, and behavioral tests.
2. Propose the target module responsibilities, boundary types, call flow,
   failure handling, and test seams before implementation.
3. Inspect the existing implementation afterward for missed behavior. Do not
   let its current topology, private names, or call structure define the new
   design without an explicit design review.

## Catalog and oracle authority

Classify each new piece of data before deciding where it belongs:

- An irreducible target fact belongs in that target's YAML spec.
- A deterministic derivation belongs in Python.
- A cross-target harness policy belongs in generic Python that operates on the
  loaded catalog, without naming real targets.
- A product observation belongs in a report or defect record until it is
  independently established as an oracle fact.

The YAML filename stems and the validated specs loaded from them are the
current authority for catalog membership and target facts. Never introduce a
Python collection of real target names as a second catalog, target grouping,
or policy input.

Keep schema vocabulary, validation, defaults, and generic derivation in
Python. The present YAML shape is not permanent: simplify the schema when a
field can be derived safely from filename, scope, existing facts, or a
target-independent convention.

The harness oracle must remain independent of the product being tested. Never
derive expected effects or target membership from product output, discovery,
or behavior observed during the run.

Report product defects exposed by the sandbox. Do not change production
behavior unless the request explicitly includes that fix.

## Code quality is part of correctness

Passing tests is necessary but not sufficient. A change is incomplete when it
leaves a major responsibility, coupling, type-design, complexity, or legacy
preservation finding unresolved.

Prefer explicit, domain-named code over clever compression. Build only
abstractions that own a real decision, state, resource, or varying policy. Do
not add ceremonial layers that only rename procedural steps.

For every non-trivial change, the implementation plan must identify:

- each module to create or modify and its one primary responsibility;
- each stateful collaborator, the state or resource it owns, and the decisions
  it is allowed to make;
- each deterministic transformation that will remain a pure function;
- each named type that crosses a module boundary;
- the end-to-end call flow and failure path;
- the test seams and the observable behavior they prove;
- each existing surface classified under the legacy policy below.

Do not begin implementation when these boundaries are still ambiguous.

## Responsibility boundaries

Keep these concerns separate unless a smaller design can demonstrate one
cohesive responsibility:

- application orchestration and phase sequencing;
- subprocess command construction and execution;
- sandbox root preparation and filesystem mutation;
- filesystem observation and snapshots;
- effect-specific behavioral validation;
- package installation and runtime probes;
- artifact allocation, metadata persistence, and retention;
- console and file logging;
- manifest and report rendering;
- YAML loading, schema validation, and typed conversion.

An orchestrator coordinates collaborators; it must not implement their
filesystem, validation, subprocess, persistence, or rendering details.

A module should have one primary reason to change. File size alone does not
require arbitrary splitting, but a production module above 400 lines requires
an explicit responsibility review. Do not keep unrelated responsibilities
together merely because they participate in one end-to-end workflow.

Avoid import cycles and hidden global ownership. Make side effects visible at
named boundaries.

## Classes and functions

Use classes when a collaborator owns mutable lifecycle state, a resource, a
policy, or a family of interchangeable behavior. A class must have a clear
responsibility and meaningful invariants; do not create namespace classes,
pass-through facades, or wrappers whose methods only call legacy functions.

Use pure functions for deterministic parsing, comparison, transformation,
command construction, and rendering when no state or resource ownership is
needed.

Keep functions focused on one level of abstraction. A production function
exceeding any of these thresholds requires decomposition or a written design
justification:

- 40 statements;
- McCabe complexity 8;
- eight decision branches.

These are review triggers, not permission to split code into arbitrary
one-line helpers. Decomposition must create meaningful responsibilities or
pure transformations.

Catch broad exceptions only at an application boundary that can classify the
failure, preserve diagnostics, and return the correct public result. Internal
code should catch the narrow failures it can actually handle.

## Modeling and type design

Use named dataclasses, enums, protocols, discriminated unions, or TypedDicts at
important boundaries. Keep untyped mappings at parsing or serialization edges;
do not pass `dict[str, object]` or loosely shaped dictionaries through the
application as an implicit contract.

Do not model distinct behavioral variants as one dataclass containing many
kind-specific optional fields. Prefer specialized models or a discriminated
union whose valid states are explicit.

Make invalid states difficult or impossible to construct. Validate external
input once, convert it to typed models, and keep internal code operating on
those models.

Dispatch on an effect kind, phase kind, command mode, or result state at one
explicit owner. Do not repeat growing `if kind` or `if mode` trees across
multiple modules. Adding a variant should have a clear extension point and a
bounded set of files to change.

## Legacy and compatibility policy

Existing internal code is not a compatibility contract.

Preserve only:

- documented CLI behavior;
- documented YAML and artifact formats;
- observable filesystem and status semantics;
- explicitly approved internal interfaces with a demonstrated consumer.

Private functions, current module boundaries, internal call order, helper
names, and tests coupled to implementation details do not become contracts
merely because they already exist.

Before implementation, classify every affected legacy surface as exactly one
of:

- `current_contract`: externally consumed or explicitly approved and therefore
  preserved;
- `replace_and_delete`: internal implementation that must be replaced and
  removed;
- `temporary_bridge`: an exceptional, human-approved compatibility boundary
  with a named consumer, owner, removal condition, and test.

An unclassified legacy surface is a blocker. Do not silently preserve it,
broaden the task to protect it, or create compatibility machinery for it.

The following approaches are forbidden unless a specific external contract
requires them and the exception is approved before implementation:

- wrapping the existing implementation in new classes;
- adding facades, adapters, proxies, aliases, or shims around private legacy
  code;
- retaining the old execution path as a fallback;
- keeping duplicate old and new implementations after cutover;
- preserving private signatures only because existing tests import them;
- moving legacy code into new files without changing ownership and boundaries;
- extract-method refactors that leave the same god function or god module in
  control;
- speculative backward compatibility for unknown callers;
- deferring deletion to an unspecified future cleanup.

For replacement work, build the new path independently from behavioral
contracts. New production code must not call the legacy path. Cutover and
legacy deletion belong in the same change or in an explicitly approved,
bounded sequence whose deletion step is already defined. A migration slice
must reduce legacy ownership, not only add another surface beside it.

Prefer deleting unnecessary concepts and updating their call sites and tests
over preserving them through translation layers. Fail clearly when obsolete
usage remains instead of silently supporting it.

## Testing boundaries

Tests should protect observable behavior and intentional architectural seams,
not accidental private structure.

- Preserve tests that prove documented CLI, artifact, status, filesystem,
  catalog, and oracle behavior.
- Rewrite or remove tests whose only purpose is to freeze private helper names,
  module layout, call order, or an implementation-specific decomposition.
- Test pure rules directly and exercise real temporary filesystems for
  filesystem behavior where practical.
- Inject subprocess execution, clocks, and other expensive or nondeterministic
  boundaries when that creates a real test seam. Do not mock every internal
  call or duplicate the implementation in the test.
- A green test suite does not overrule a major design-quality finding.

Review the current change proportionally. Record unrelated historical debt,
but do not broaden a bounded task indefinitely or use existing debt to justify
adding more of the same structure.

## Required completion evidence

Before declaring a non-trivial change complete, report:

- the observable contracts preserved or intentionally changed;
- the final responsibility of every changed production module;
- the named types crossing important boundaries;
- the legacy surfaces deleted and a search proving no production imports or
  runtime paths still reference them;
- every remaining compatibility layer and its approved consumer and removal
  condition; normally this list is empty;
- the longest or most complex changed functions and any threshold exceptions;
- lint, type-check, unit-test, and behavioral-test commands and results;
- the independent design-review verdict when the workflow provides a reviewer;
- any unresolved structural finding.

An implementation agent must not declare success solely because tests pass. A
reviewer may reject behaviorally correct code for weak responsibility
boundaries, unnecessary compatibility, duplicate paths, untyped contracts, or
unresolved god functions and god modules.
