# Install sandbox instructions

Before changing target-related data or code that consumes it, read
`README.md` and `specs/README.md`.

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
