# Validated knowledge ingestion TDD evidence

## Source

The user approved implementation of the recommended Graphify and Jcode validated
knowledge plan. This document covers the first Graphify milestone: native
`lat.md` ingestion, integrity checking, implementation linkage, and retrieval.

## User journeys

1. As an agent, I can query curated design constraints together with source-code
   symbols so that I do not miss project invariants before editing code.
2. As a maintainer, I can validate wiki links, source links, and required
   implementation mentions so that project knowledge does not silently drift.
3. As a project adopting lat.md, I can use Graphify's normal update workflow
   without running a second retrieval service.

## Requirement-to-check evidence

| # | Guarantee | Test or command | Type | Result |
|---|---|---|---|---|
| 1 | Headings become stable knowledge sections with first-paragraph summaries | `test_lattice_markdown_emits_stable_sections_summaries_and_wiki_edges` | Unit | PASS |
| 2 | Inline and fenced examples are ignored while source links become `documents` edges | `test_lattice_ignores_example_links_and_emits_source_documentation_edges` | Integration | PASS |
| 3 | `@lat` comments connect a knowledge section to its implementation file | `test_full_extract_links_at_lat_comment_to_knowledge_section` | Integration | PASS |
| 4 | Cross-file shorthand wiki links resolve to full stable section IDs | `test_full_extract_resolves_cross_file_short_wiki_reference` | Integration | PASS |
| 5 | Broken, ambiguous, and missing implementation references are diagnosed | `test_validate_lattice_reports_broken_ambiguous_and_unimplemented_required_sections` | Unit | PASS |
| 6 | Invalid lattices return structured JSON and exit code 1 | `test_check_knowledge_cli_returns_json_and_nonzero_for_invalid_lattice` | CLI acceptance | PASS |
| 7 | Query scoring searches summaries and returns the summary in bounded output | `test_query_retrieves_lattice_summary_after_normal_extraction` | Public retrieval | PASS |
| 8 | A real valid lattice is accepted through the public CLI | `uv run python -m graphify check-knowledge /home/sergey/.jcode/scratch/graphify-lattice-valid --json` | CLI acceptance | PASS, 2 sections, 0 errors |
| 9 | The implementation is compatible with the official lat.md repository | `validate_lattice(Path('/home/sergey/.jcode/scratch/lat.md-official'))` | Real integration | PASS, 24 files, 192 sections, 0 errors |
| 10 | Dotted lattice filenames remain knowledge references rather than source paths | `test_dotted_lattice_file_reference_is_not_misclassified_as_source` | Integration | PASS |
| 11 | Incremental lattice updates rediscover mentions in unchanged source files | `test_lattice_change_rescans_unchanged_source_mentions` | Incremental integration | PASS |
| 12 | Source links cannot escape the project root | `test_source_reference_cannot_escape_project_root` | Security | PASS |
| 13 | Code-mention validation honors Graphify ignore rules | `test_validation_respects_graphifyignore_when_scanning_code_mentions` | Integration | PASS |
| 14 | Adjacent extraction, CLI, query, and security behavior remains intact | focused regression command below | Regression | PASS, 460 tests |

## RED evidence

1. `uv run pytest -q tests/test_lattice_ingest.py` failed during collection with
   `ModuleNotFoundError: graphify.lattice_ingest` before production code existed.
2. After the first minimal implementation, the strengthened tests failed because
   cross-file shorthand links were pruned and summary-only queries returned
   `No matching nodes found.`
3. The source-link compatibility test failed because no `documents` edge was
   emitted before Markdown-aware parsing was implemented.
4. Independent review added four regressions which initially failed: incremental
   `@lat` rediscovery, dotted lattice filenames, source-root containment, and
   ignore-aware validation scanning.

Checkpoint commits:

- `79fe28b` specifies the initial missing behavior.
- `cee64f3` specifies cross-file resolution and public retrieval behavior.

## GREEN evidence

- `uv run pytest -q tests/test_lattice_ingest.py`: 11 passed.
- `uv run pytest -q tests/test_lattice_ingest.py tests/test_manifest_ingest.py tests/test_languages.py tests/test_cli_export.py tests/test_query_cli.py tests/test_security.py`: 460 passed.
- `env -u DEEPSEEK_API_KEY -u DEEPSEEK_BASE_URL uv run pytest -q --ignore=tests/test_falkordb_integration.py`: 4,157 passed, 1 skipped. The excluded integration requires a FalkorDB server with the `GRAPH.QUERY` module; the available localhost service was plain Redis.
- `uv run ruff check graphify/lattice_ingest.py graphify/extract.py graphify/serve.py graphify/cli.py graphify/__main__.py tests/test_lattice_ingest.py`: passed.
- GREEN implementation checkpoint: `5dcee5a`.

## Coverage

`uv run pytest -q tests/test_lattice_ingest.py --cov=graphify.lattice_ingest --cov-report=term-missing --cov-fail-under=80`

The initial seven-test milestone reached 89% statement coverage. The final
eleven-test suite adds independent-review coverage for incremental, security,
ignore, and dotted-filename edge cases.

## Known boundaries

- Graphify validates that referenced source files exist. Symbol-level source-link
  validation is deferred to the next milestone, where links will resolve against
  Graphify's language-aware symbol index.
- This milestone does not add a separate lat.md semantic index or service.
  Curated summaries participate directly in Graphify's existing query scorer.
- Jcode changes are intentionally deferred until the Graphify public graph and
  CLI contract is committed and stable.
