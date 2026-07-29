# Curriculum timing tables

Use this reference when a corpus contains course plans, pacing histories,
assignment schedules, release/due-date schedules, or tables aligning learning
activities to weeks or dates.

## Evidence authorities

Classify each source independently from its title, headings, and stated purpose:

- `proposed_future`: proposed, recommended, draft, or future teaching plans.
- `current_release`: the active release/due-date schedule or current planning
  authority.
- `historical`: dated records, semester reconstructions, commit histories, or
  reports of what occurred.
- `unspecified_schedule`: timing content whose authority is not explicit.

Never merge authorities merely because they mention the same assignment, topic,
or week. Differences are competing schedules, not contradictions in historical
evidence.

## Extraction rules

- Treat assignment numbers as identifiers. Never derive a week from an
  assignment number or folder prefix.
- Read every meaningful row in a Markdown timing/alignment table.
- Preserve multiple assignments in one row and assignments spanning rows.
- Interpret explicit `begin`/`start` and `finish`/`complete` language as
  start/finish timing. Do not infer a span from assignment order.
- Create authority-scoped timing concepts. A proposed Week 5 and a current
  release Week 5 are distinct nodes.
- Preserve release candidates and due weeks separately.
- Attach `source_file`, line-level `source_location`, authority, assignment
  identifier, and week to every normalized relationship.
- Dates stay dates. Convert a date to a week only when the source explicitly
  supplies that week in the same row.
- Historical topic pacing does not become proposed assignment timing.
- If a row is ambiguous, retain it as ambiguous evidence or fail validation;
  never silently invent the missing value.

## Deterministic normalization and validation

After semantic extraction and before graph build, run:

```bash
$(cat graphify-out/.graphify_python) \
  SKILL_DIR/scripts/curriculum_tables.py extract \
  --root INPUT_PATH \
  --input graphify-out/.graphify_extract.json \
  --output graphify-out/.graphify_extract.curriculum.json \
  --expectations graphify-out/.curriculum_table_expectations.json
mv graphify-out/.graphify_extract.curriculum.json graphify-out/.graphify_extract.json
```

After `graph.json` is written, run the fail-closed validator:

```bash
$(cat graphify-out/.graphify_python) \
  SKILL_DIR/scripts/curriculum_tables.py validate \
  --root INPUT_PATH \
  --graph graphify-out/graph.json \
  --report graphify-out/curriculum-table-validation.json
```

Stop when validation fails. The validator checks skipped source rows, assignments
without timing, missing timing concepts, invented relationships, row provenance,
and collapsed schedule authorities. It also reports competing planning schedules.

The normalizer is generic. Do not pass course-specific assignment counts, week
counts, filenames, or expected mappings.
