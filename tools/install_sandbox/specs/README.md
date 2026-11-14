# Install sandbox spec authority

This directory is the source-controlled target-fact catalog for the Tier 1
install sandbox. This guide describes the current YAML/loader boundary; it
does not make the current fields or file shape permanent.

## Data flow

```text
specs/*.yaml
    |
    v
YAML raw mappings
    |
    v
validated typed catalog (TargetSpec, ScopeSpec, Effect)
    |
    v
target/scope and aggregate scenarios
    |
    v
generic lifecycle execution and validation
```

`yaml.safe_load()` produces ordinary mappings and lists. The loader validates
their vocabulary and values, applies generic defaults, and converts them to
typed models. `load_catalog()` keys those models by YAML filename stem. The
runner then iterates the typed catalog to create scenarios; lifecycle and
effect code interpret those scenarios without maintaining target-name tables.

The YAML is the oracle for expected Graphify-owned file effects. It must not be
generated from the installer output or behavior it is meant to test.

## Current ownership

| Concern | Current owner |
| --- | --- |
| Catalog membership, target identity, and order | `*.yaml` filename stems, sorted lexically |
| Supported and unsupported scopes, expected effects, command-mode exceptions, limitations, and aggregate-uninstall eligibility | Each target's YAML |
| Allowed schema vocabulary, validation, typed conversion, and defaults | `specs.py` and `models.py` |
| Scenario construction, command derivation, lifecycle steps, filesystem checks, and reporting | Generic Python over the loaded catalog |

Current loader defaults include `file` for an omitted effect kind, `exact` for
an omitted payload mode, and no direct command mode when `install_mode` or
`uninstall_mode` is omitted. Defaults are schema behavior, so they belong in
Python rather than being repeated in every target.

JSON effects whose current installer deliberately creates and preserves the
pre-modification `<name>.graphify-bak` file declare
`preserves_backup: true`. The target spec owns whether that artifact exists;
the loader derives its sibling path and the lifecycle validator proves that it
retains the seeded user JSON through uninstall.

## Classify data before adding it

Use one of these categories:

1. **Irreducible target fact.** A fact that differs by target and cannot be
   inferred safely, such as an expected path, payload source, marker, or
   documented target limitation. Put it in that target's YAML.
2. **Deterministic derivation.** A value that follows from filename, scope,
   existing facts, or a target-independent convention. Derive it in Python
   instead of storing it.
3. **Cross-target harness policy.** A generic rule such as which lifecycle
   phases to run or how to validate unexpected changes. Implement it once in
   Python and apply it to the loaded catalog. Do not encode the policy with a
   list of real target names.
4. **Product observation.** Something the current installer happens to do.
   Record it as evidence or a product defect. Do not turn it into the expected
   result merely because the harness observed it.

An observation may motivate a spec correction, but the expected fact needs an
independent basis. Otherwise a product bug can redefine the oracle and make
its own test pass.

## `universal_uninstall_scopes` today

`universal_uninstall_scopes` is an explicit present-day policy fact: it states
which supported scopes for a target participate in the grouped
universal-uninstall scenarios. The runner obtains each group by filtering the
loaded catalog on this field.

The field is explicit because eligibility is not currently safe to infer from
scope support, effect paths, or command mode. This is not a commitment to keep
the field forever. If a target-independent derivation becomes correct and
provable, move that rule to Python and remove the redundant declarations.

Repeated values alone do not prove that an oracle fact is derivable. A common
value can still encode target-specific knowledge, and moving it into code
without a valid rule would only hide a target-name grouping.

## Catalog-driven iteration

Do not create a parallel catalog or grouping:

```python
# Forbidden: placeholder names standing in for a manually maintained real list.
TARGETS = ("target_one", "target_two")
UNIVERSAL_USER_TARGETS = {"target_one"}
```

Iterate the authoritative catalog and select on typed facts:

```python
catalog = load_catalog(spec_dir)

for target in catalog.values():
    run_target(target)

selected = [
    target
    for target in catalog.values()
    if scope in target.universal_uninstall_scopes
]
```

The same rule applies to tests. Unit tests may use small fictional catalogs,
but production target names must not become a second catalog or policy table
in Python.

## Change checklist

Before adding or changing target-related data:

- Read the parent sandbox README and this guide.
- Classify the proposed data as a target fact, derivation, harness policy, or
  product observation.
- For a proposed field, show why it cannot be derived safely from filename,
  scope, existing facts, or a target-independent convention.
- Keep target-specific facts in YAML and schema vocabulary, validation,
  defaults, and generic mechanics in Python.
- Confirm no Python collection of real target names was introduced for
  catalog membership, grouping, or policy.
- Confirm expected results remain independent of the product being tested.
- Treat a failing product observation as a defect; do not weaken the oracle or
  change production behavior unless that work was explicitly requested.
- Update this guide if the ownership boundary changes, without describing the
  resulting schema as immutable.
