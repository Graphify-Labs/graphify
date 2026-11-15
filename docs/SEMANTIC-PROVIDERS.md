# Optional semantic provider guide

## What this adds

Graphify already parses popular web languages locally with tree-sitter. This
extension adds optional compiler/language-server evidence. The AST graph remains
the always-available baseline; provider facts are additive, provenance-tagged
evidence and never replace native extraction.

| Provider | Languages | Evidence level in this repository |
|---|---|---|
| rust-analyzer | Rust | real-tool smoke + protocol tests |
| typescript-language-server | TypeScript, JavaScript, JSX/TSX | real-tool smoke + protocol tests |
| Pyright | Python | real-tool smoke + protocol tests |
| Eclipse JDT LS | Java | protocol tests; external binary not exercised in CI |
| JetBrains Kotlin LSP | Kotlin | protocol tests; external binary not exercised in CI |
| csharp-ls | C# | protocol tests; external binary not exercised in CI |
| gopls | Go | protocol tests; external binary not exercised in CI |
| Phpactor | PHP | protocol tests; external binary not exercised in CI |
| Ruby LSP | Ruby | protocol tests; external binary not exercised in CI |

Provider projects: [rust-analyzer](https://github.com/rust-lang/rust-analyzer),
[TypeScript language server](https://github.com/typescript-language-server/typescript-language-server),
[Eclipse JDT LS](https://github.com/eclipse-jdtls/eclipse.jdt.ls),
[Kotlin LSP](https://github.com/Kotlin/kotlin-lsp),
[csharp-ls](https://github.com/razzmatazz/csharp-language-server),
[Pyright](https://github.com/microsoft/pyright),
[gopls](https://github.com/golang/tools/tree/master/gopls),
[Phpactor](https://github.com/phpactor/phpactor), and
[Ruby LSP](https://github.com/Shopify/ruby-lsp).

Production images should pin and verify each selected provider version. Do not
install every language server in every image: construct domain-specific images
from the same registry contract.

Validated with real local tools during development:

- `rust-analyzer 1.95.0` on a real Cargo workspace;
- `typescript-language-server 6.0.0` with `TypeScript 6.0.3` on a real strict
  TypeScript workspace.
- `Pyright 1.1.409` on a real two-file Python workspace.

TypeScript 7.0.2 was rejected by the tested language-server release during
initialization, which is why container builds must pin the compiler/server pair
rather than installing unbounded `latest` versions. Java, Kotlin, C#, Go, PHP
and Ruby use the same protocol-tested bounded LSP contract, but remain honestly
marked as not real-tool-tested until their optional binaries join the integration
matrix.

`auto` selection requires both a matching source file and a project marker. This
prevents a polyglot repository from launching language servers for incidental
examples or vendored snippets. Explicit `--provider` selection intentionally
overrides that convenience check.

## Safety and failure behavior

- Native AST extraction is never disabled by a provider result.
- Provider subprocesses use argv execution with `shell=False`.
- Provider subprocesses receive an allowlisted toolchain environment rather
  than an unfiltered copy of unrelated credentials.
- The LSP client advertises no workspace-edit support and rejects edit requests.
- The workspace, file count, source size, symbol count, RPC message size,
  request count and timeout are bounded.
- Source symlinks escaping the workspace are ignored.
- Output contains symbols, locations and relationships, not source text,
  process environment, server stderr or model chain-of-thought.
- Missing providers return `unavailable`; exhausted limits return
  `budget_exhausted`. Neither condition silently expands a budget.
- Enrichment is additive and writes a separate output graph by default.
- A semantic symbol is merged into an AST node only on one unambiguous
  `(source_file, label)` match. Ambiguous matches stay separate.
- Every fact includes provider kind, run ID, timestamp, confidence and source
  range metadata. A registered profile is never described as real-tool proof.

Language servers are external executables and may invoke project tooling (for
example, compiler checks or build scripts). Run them only on trusted workspaces,
or inside an appropriately isolated environment. Installing or running a
language server is never part of Graphify's default extraction path.

## Commands

```bash
uv sync
uv run graphify-semantic list
uv run graphify extract /path/to/repo --code-only
uv run graphify-semantic run /path/to/repo \
  --provider auto \
  --max-files 200 \
  --max-symbols 5000 \
  --max-relationship-requests 500 \
  --request-timeout 20 \
  --out /path/to/repo/graphify-out/semantic-runs.json
uv run graphify-semantic merge \
  /path/to/repo/graphify-out/graph.json \
  /path/to/repo/graphify-out/semantic-runs.json \
  --out /path/to/repo/graphify-out/graph.semantic.json
```

Select explicit providers when `auto` is too broad:

```bash
uv run graphify-semantic run . \
  --provider rust-analyzer \
  --provider typescript-language-server \
  --out graphify-out/semantic-runs.json
```

## Adding another language

Custom manifests are trusted configuration because they choose an executable.
They are strictly shape-checked and commands must be argv arrays.

```json
{
  "name": "dart-analysis-server",
  "languages": ["dart"],
  "extensions": [".dart"],
  "command": ["dart", "language-server", "--protocol=lsp"],
  "binary_env": "GRAPHIFY_SEMANTIC_DART_BINARY",
  "project_markers": ["pubspec.yaml"],
  "initialization_options": {}
}
```

No runner or merger change is needed.
