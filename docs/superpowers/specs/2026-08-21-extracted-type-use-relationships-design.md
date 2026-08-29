# Extracted Type-Use Relationships — Design

**Date:** 2026-08-21
**Status:** Approved

## Problem

Graphify's Python cross-file resolver currently turns every reference to an
imported symbol inside a class or function into the same edge:

```json
{
  "relation": "uses",
  "confidence": "INFERRED",
  "confidence_score": 0.95
}
```

That is appropriate for an imported name whose role is only known from a body
reference. It is inaccurate for a parameter, return, or field annotation. Those
annotations are direct syntax-tree evidence, so they should not be presented as
model-inferred relationships. The generic edge also hides whether the type is
accepted, returned, or stored.

DebtGPS exposed the practical impact: 38 relationships involving its canonical
`Debt` type were reported as inferred even though every relationship was backed
by a concrete Python annotation or constructor reference.

## Constraint: One Edge Per Endpoint Pair

Graphify builds an `nx.Graph` or `nx.DiGraph`, not a multigraph. A source and
target therefore retain one edge in the built graph even if raw extraction
emits several relations between them.

Emitting separate `accepts_type`, `returns_type`, and `field_type` edges would
lose information when one symbol uses the same type in multiple roles. It could
also overwrite a more specific runtime `calls` edge unless every downstream
edge-selection rule were updated.

The design must preserve all annotation roles in one edge and must not weaken a
runtime relationship.

## Chosen Model

An exact annotation produces one `uses_type` edge per source-target pair:

```json
{
  "source": "api_transform",
  "target": "models_payload",
  "relation": "uses_type",
  "context": "type_annotation",
  "type_roles": ["parameter", "return"],
  "confidence": "EXTRACTED",
  "confidence_score": 1.0,
  "source_file": "api.py",
  "source_location": "L12",
  "weight": 1.0
}
```

`type_roles` is a sorted, unique list. Supported roles are:

- `parameter`: a top-level function or method parameter annotation;
- `return`: a top-level function or method return annotation;
- `field`: an annotated class attribute;
- `nested_parameter`: a parameter annotation on a function nested inside the
  source symbol;
- `nested_return`: a return annotation on a function nested inside the source
  symbol;
- `nested_field`: an annotated assignment inside a nested class owned by the
  source symbol.

Nested roles prevent a factory such as `order_custom()` from falsely claiming
that its own signature accepts `Debt` when the annotation actually belongs to
the closure it returns.

## Extraction Flow

The Python cross-file import resolver will continue to resolve imported names
against source-backed in-corpus definitions. While walking each source symbol,
it will classify identifier occurrences by syntax context:

1. Detect whether an imported identifier occurs inside a parameter annotation,
   return annotation, or annotated class field.
2. Record the role and first evidence line per source-target pair.
3. Aggregate all roles for that pair into one `uses_type` edge.
4. Continue collecting non-annotation body references as generic `uses` facts.
5. Preserve the existing extracted `calls` relationship for runtime constructor
   and function calls.

Annotations nested inside generic containers retain the surrounding role. For
example, both `list[Debt]` and `Debt | None` record the role of the full
annotation rather than treating `Debt` as an unclassified body reference.

Forward-reference string annotations are included when their imported symbol
can be resolved exactly. Arbitrary strings are not evaluated.

## Edge Precedence and Compatibility

`uses_type` is a generic relationship for graph-construction precedence. A
specific runtime edge such as `calls`, `inherits`, or `implements` wins when the
same endpoints carry both facts. This keeps `analyze_refinance() -> Debt` as a
runtime construction relationship while annotation-only ordering functions use
`uses_type`.

Raw extraction may contain both facts. The built graph keeps the specific fact;
diagnostics and future multigraph output can still inspect the raw evidence.

Existing `uses` consumers remain supported:

- runtime and otherwise-unclassified imported-name references still emit
  `uses/INFERRED`;
- query and display code accepts the new relation without special handling;
- call-flow and affected traversals do not treat type-only relationships as
  runtime calls;
- gap and centrality analysis may traverse `uses_type` as ordinary structural
  connectivity, but must not apply the cross-language inferred-edge penalty to
  an extracted edge.

No semantic-cache migration is required because these are deterministic AST
relationships. A code graph rebuild replaces the old inferred edges.

## Error Handling and Conservatism

- An unresolved, ambiguous, external, or star-imported annotation does not bind
  to an arbitrary local type.
- Built-in annotations such as `str`, `int`, and `list` do not create local type
  nodes.
- Malformed syntax continues to fail open under the extractor's existing error
  handling; it must not fabricate a type relationship.
- Duplicate annotation occurrences merge their roles and keep the earliest
  evidence line.
- A runtime reference and an annotation reference may coexist in raw output,
  but graph construction must retain the specific runtime relation.

## Verification Contract

Tests will establish the behavior before implementation:

1. Parameter-only annotation emits `uses_type`, role `parameter`, and
   `EXTRACTED 1.0`.
2. Return-only annotation emits role `return`.
3. A parameter-and-return use of the same type produces one edge with both
   sorted roles.
4. A class attribute annotation emits role `field`.
5. A nested closure records nested roles on its owning source symbol.
6. A runtime constructor call remains `calls/EXTRACTED`, not `uses_type`, in the
   built graph.
7. A non-annotation body reference retains `uses/INFERRED 0.95` when no more
   specific runtime relationship is available.
8. Import aliases, generics, unions, forward references, ambiguity, and built-in
   exclusions retain their existing safety behavior.
9. Incremental extraction produces the same type edge as a full extraction.
10. Rebuilding DebtGPS changes the 34 production annotation-only `Debt` edges
    from inferred `uses` to extracted `uses_type`. Its four test constructor
    sites must not be mislabeled as annotation-backed `uses_type`; when the
    existing call resolver resolves them, they remain extracted runtime facts.
    The refinance constructor relationship remains an extracted runtime fact.

## Scope

This change applies to Python cross-file annotation resolution. It does not
redesign Graphify as a multigraph, change semantic-LLM extraction, or rewrite
the established `references` contexts produced by other language extractors.
Cross-language unification can be designed separately after this Python model
has proven stable.
