# Contributing to Graphify

Graphify is a graph-building system whose correctness depends on preserving provenance, deterministic extraction, and safe incremental updates. A contribution is not complete because the new code works on the happy path; it is complete when the relevant invariant is explicit, tested, and preserved across rebuilds.

## Before You Start
- Read [ARCHITECTURE.md](ARCHITECTURE.md)
- Read [SECURITY.md](SECURITY.md) when relevant
- Understand `v8` is the active development branch
- Use `graphify-out/GRAPH_REPORT.md` for repository orientation

## What We Value

1. **Preserve correctness, not merely successful execution**. A failed, partial, smaller, or differently keyed extraction must not overwrite valid persisted state or poison incremental caches.
2. **Preserve provenance; incidental richness is not evidence**. A real source-backed record must not lose to a richer sourceless stub. A location without a corresponding source file is not sufficient provenance.
3. **Keep deterministic extraction deterministic**. AST extraction, symbol identity, traversal order, merge behavior, and other structural passes must not depend on filesystem ordering, ambient environment state, network calls, or nondeterministic model output.
4. **Keep inference visibly separate from extracted fact**. Never turn uncertainty into false certainty just because a richer result looks better. Preserve the distinction between extracted fact, inference, and ambiguity.
5. **Prefer fail-closed behavior over guessed relationships**.
6. **Treat persistent graph/cache state as data that can be corrupted**.
7. **Make bug fixes prove the old failure with a regression test**. Demonstrate the old failure, not merely exercise the new code.
8. **Keep PRs narrow and reviewable**. Small, auditable diffs beat clever broad fixes.
9. **Document heuristic boundaries and unsupported cases**.
10. **Never hand-edit generated artifacts**. Edit the source fragment, run the generator, and run the corresponding verification checks.
11. **Do not let ambient environment state affect tests**. Tests must be deterministic with respect to the contributor's shell environment.
12. **Treat paths, source text, model output, URLs, and generated commands as untrusted**. Never construct shell commands or Python source by interpolating free text.
13. **Check cross-platform behavior when touching filesystem/process/install logic**. A change is not considered cross-platform-safe merely because it passes on Linux.
14. **Update documentation when behavior or invariants change**. Documentation is part of the behavior contract.
15. **Use Graphify itself to understand Graphify**, except when the graph is the thing being debugged. 

## Repository Architecture
- **Pipeline**: `detect()` → `extract()` → `build()` → `cluster()` → `analyze()` → `report.generate()` → `export.to_*()`
- **Where extractors live**: `graphify/extractors/`
- **Generated skills vs source fragments**: Skill files in `graphify/` are generated from fragments in `tools/skillgen/`. 
- **What is generated and what is authoritative**: `tools/skillgen/fragments/` is authoritative.

## Development Setup

```bash
# Fork and clone the repository
git clone https://github.com/<your-username>/graphify.git
cd graphify
git remote add upstream https://github.com/Graphify-Labs/graphify.git
git fetch upstream
git checkout -b my-feature-branch upstream/v8  # Always branch off upstream v8, never commit directly to v8

# Set up the environment
uv sync
uv run pre-commit install

# Run the test suite to confirm your setup
uv run pytest tests/ -q

# Run linters and type checkers before pushing
uv run ruff check .
uv run pyright
```

- **Python versions**: 3.10+
- **uv**: We use `uv` for dependency management.

## Working on the Codebase
- **Use graphify itself**: Before making non-trivial architectural changes, use `graphify query ...` to navigate the codebase rather than blind grepping. Do not use the graph as evidence when the task concerns the graph's own correctness.
- **Update graph after code changes**: `graphify update .`
- **Root/path invariants**: Paths resolve relative to the calling module or scan root.
- **Cache considerations**: Be aware of relative/absolute path caching across rebuilds.
- **Generated skill files**: Regenerate with `uv run python -m tools.skillgen --bless`. Never hand-edit the generated files directly.
- **Corpus boundaries**: Do not create a second interpretation of the corpus boundary. Reuse the existing detection/ignore semantics whenever another pass walks project files (e.g. `.graphifyignore`).
- **Cross-platform**: Windows portability is a first-class contribution concern. Path separators, symlinks, absolute/relative paths, hash seeds, and shell interpolation must work correctly on Windows.

## Making a Change
1. Find or create an issue
2. Reproduce
3. Identify invariant
4. Make smallest fix
5. Add regression test
6. Run targeted tests
7. Run full suite (`uv run pytest tests`)
8. Run lint/type checks (`uv run ruff check .`, `uv run pyright`)
9. Regenerate artifacts if you touched their sources (`uv run python -m tools.skillgen --bless`).

## Tests
- **pytest**: The primary test runner.
- **Fixture conventions**: New language extractors need fixtures under `tests/fixtures/` and tests in `tests/test_languages.py`.
- **Environment isolation**: Tests must not accidentally depend on the contributor's ambient environment. When writing backend/provider tests, explicitly isolate or clear environment variables (e.g., `OPENAI_API_KEY`, `OLLAMA_HOST`).
- **Deterministic tests**: Ensure tests don't rely on ambient state or ordering.
- **Regression-test expectations**: Test must fail on pre-fix and pass on post-fix.

## Language Extractors
- **Extractor module**: Defines logic for each language AST.
- **Dispatch table**: Registers the parser and language.
- **Tree-sitter dependency**: Use ASTs where possible.
- **Fixture**: Ensure comprehensive test cases in `tests/fixtures/`.
- **Cross-file resolution considerations**: Resolution stays local to AST paths.

## Generated Skills and Monoliths
- Source fragments are authoritative.
- Run skillgen (`uv run python -m tools.skillgen --bless`).
- Never casually edit generated artifacts.
- Sanctioned round-trip changes only.
- Preserve multiset checks.

## Data Integrity Rules
- **Zero-node guard**: Must run before writes.
- **Shrink guard**: Must not persist smaller corrupt graphs. (Note: forced writes can bypass this).
- `to_json` before report side effects.
- **Cache consistency**: Must be maintained across absolute/relative paths. (e.g., The Windows absolute-path issue taught us that earlier side effects that persist bad absolute-path entries into the semantic cache are still data loss, even if the final graph write passes the shrink guard).
- **Provenance**: Must be preserved.
- **Cross-file edges**: Must be preserved during incremental updates, even if node count is unchanged.

## Security
- Review [SECURITY.md](SECURITY.md).
- Any change touching generated skill instructions, shell commands, subprocesses, URL ingestion, path handling, prompts, or serialization must be reviewed as a security-sensitive change.
- Never interpolate untrusted content into shell/Python.

## Commit Messages
Use a conventional-commit prefix (e.g., `fix:`, `feat:`, `docs:`, `fix(extract):`) and make the subject describe the change. Explain why in the body when the change is non-trivial. Reference the relevant issue/PR.
- **AI Authorship Disclosure**: If an AI coding assistant materially contributed to the implementation, disclose it in the commit metadata according to the repository's authorship convention (e.g., `Co-Authored-By: Claude <noreply@anthropic.com>`). Do not attribute code to a model that did not contribute.

## Pull Requests
- One concern per PR.
- No unrelated changes.
- Describe problem / implementation / verification.
- List commands actually run.
- Document limitations / unsupported cases.
- Keep description synchronized with final implementation.
- Rebase/resolve conflicts before requesting final review.

## Issue Reports
### Bugs
Include exact version/commit, environment, minimal reproduction, expected vs actual, logs, graph/cache artifacts where relevant, and whether a clean checkout reproduced it.

### Feature Requests
Focus on the problem first, proposed behavior, alternatives, and compatibility considerations.

## Review Expectations
- Correctness, regression coverage, scope, determinism, provenance, security, and documentation.

## Release / Generated Artifacts
- **What gets regenerated**: Skill files via skillgen, HTML exports.
- **What should not be committed**: Local cache (`.graphify_cached.json`), generated node artifacts outside of the expected outputs.

## Getting Help
- **Discord**: Join the [Graphify Discord](https://discord.gg/XDnKVpzdXB) for questions and discussion.
- **Issues**: Search [existing issues](https://github.com/Graphify-Labs/graphify/issues) before opening a new one.
- **Discussions**: Use GitHub issues for bugs and feature requests, Discord for open-ended questions.

## Further Reading
- [README.md](README.md)
- [ARCHITECTURE.md](ARCHITECTURE.md)
- [SECURITY.md](SECURITY.md)
- [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md)
- [RELEASING.md](RELEASING.md) (maintainers)
