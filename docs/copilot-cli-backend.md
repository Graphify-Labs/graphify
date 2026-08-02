# GitHub Copilot CLI backend

> For new Graphify integrations, prefer [`--backend copilot-sdk`](copilot-sdk-backend.md). It keeps a structured persistent runtime, supports image attachments, and automatically uses this CLI adapter as its fallback. The explicit `copilot-cli` backend remains useful for Python 3.10, diagnostics, enterprise SDK/CLI compatibility issues, and deployments that do not permit the Python SDK package.

Graphify's `copilot-cli` backend uses the official GitHub Copilot CLI as a local subprocess for semantic extraction, LLM-assisted deduplication, community naming, and PR triage. It is designed for accounts whose authentication and model access are managed by GitHub Enterprise Cloud, including GHE.com data-residency hosts.

## Why the CLI integration

The Copilot CLI already owns OAuth device-flow authentication, enterprise SSO, host selection, model policy, and credential storage. Graphify therefore does not implement GitHub's authentication flow, exchange tokens, or write an enterprise access token. It starts the CLI with the normal inherited environment and credential-store access required for that login. This also avoids depending on undocumented Copilot HTTP endpoints.

The backend is explicit-only: Graphify will not select it just because a `copilot` executable is installed. Pass `--backend copilot-cli` whenever corpus content should be sent through Copilot.

## GitHub Enterprise Cloud setup

First verify that Copilot CLI is installed and that your organization or enterprise has enabled the Copilot CLI policy for your assigned seat:

```bash
copilot version
copilot login --host https://example.ghe.com
```

The OAuth device flow opens a browser. Complete your enterprise sign-in and any required SSO authorization. Then pin the host for Graphify runs so another stored GitHub account cannot be selected accidentally.

### bash or zsh

```bash
export COPILOT_GH_HOST=example.ghe.com
graphify extract ./docs --backend copilot-cli --model auto
```

### PowerShell

```powershell
$env:COPILOT_GH_HOST = "example.ghe.com"
graphify extract ./docs --backend copilot-cli --model auto
```

`auto` lets Copilot choose from models permitted by the enterprise policy. A specific permitted model can be supplied with `--model`. Precedence is:

1. `--model`
2. `GRAPHIFY_COPILOT_CLI_MODEL`
3. `COPILOT_MODEL`
4. `auto`

## Execution and safety behavior

For each Graphify LLM request, the backend:

- resolves `copilot.cmd` first on Windows and `copilot` elsewhere;
- sends the prompt through standard input rather than command-line arguments;
- requests silent output and runs in a newly created empty temporary working directory;
- capability-detects and applies current CLI hardening flags, including disabling custom repository instructions, interactive questions, automatic updates, experimental features, built-in MCP servers, remote control, and remote export;
- denies the built-in `memory`, `read`, `shell`, `url`, and `write` tool classes;
- disables prompt-mode project extensions, repository hooks, workspace MCP loading, and MCP tool snapshot caching through child-process environment settings; and
- inherits `COPILOT_GH_HOST`, token environment variables, and Copilot CLI credential-store access without parsing, printing, or persisting credential values.

These controls reduce the local agent surface, but they do not rewrite user-scoped Copilot plugins, skills, MCP configuration, or enterprise-managed settings. The fresh temporary directory avoids repository resources and location-scoped approvals from the source tree; administrators should still review user and managed Copilot configuration before approving regulated workloads. The prompt and source material are sent to the model service selected by GitHub Copilot and governed by the enterprise's policies. These controls are not a substitute for organizational authorization to process a particular data type.

## Session data and billing

Copilot CLI stores session data locally. On current CLI releases Graphify adds `--no-remote-export`, which prevents the Graphify invocation from being exported or synchronized to GitHub. Local session state remains. GitHub gates remote-session options by account capability; if the CLI rejects the opt-out flag, Graphify warns and retries without it. Configure `"remoteExport": false` in Copilot's settings as a backstop and review the applicable enterprise policy.

Graphify's own cost report shows zero provider API dollars because Copilot does not expose API-style token accounting to this integration. The reported token counts are character-based estimates. The underlying Copilot interaction can consume AI credits or another plan allowance controlled by GitHub and the applicable enterprise policy.

## Concurrency

Graphify runs Copilot CLI requests serially by default. A single semantic extraction can produce many prompts because files are chunked and a truncated response can be bisected and retried. Serial execution avoids concurrent local sessions and unexpected bursts against enterprise limits.

Set this only after confirming the account and policy tolerate parallel sessions:

```bash
export GRAPHIFY_COPILOT_CLI_PARALLEL=1
```

`--max-concurrency` then controls the upper bound as it does for other Graphify backends.

## Authentication troubleshooting

Check the selected host and remove token variables that could override the stored enterprise OAuth login:

```bash
printf '%s\n' "$COPILOT_GH_HOST"
env | grep -E '^(COPILOT_GITHUB_TOKEN|GH_TOKEN|GITHUB_TOKEN)='
```

PowerShell equivalent:

```powershell
$env:COPILOT_GH_HOST
Get-ChildItem Env:COPILOT_GITHUB_TOKEN,Env:GH_TOKEN,Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
```

Then repeat the login and run a small, approved test corpus:

```bash
copilot login --host https://example.ghe.com
COPILOT_GH_HOST=example.ghe.com graphify extract ./docs --backend copilot-cli --model auto
```

Common errors:

- **CLI not found**: install the official GitHub Copilot CLI and confirm `copilot version` works in the same shell that launches Graphify.
- **Not authenticated or wrong account**: repeat `copilot login --host https://example.ghe.com`, set `COPILOT_GH_HOST`, and remove conflicting token variables.
- **Model unavailable**: use `--model auto` or select a model enabled by enterprise policy.
- **Copilot CLI disabled**: an enterprise or organization administrator must enable the Copilot CLI policy and the user must have an eligible seat.
- **Hollow or malformed graph output**: Graphify treats it as truncation and retries smaller chunks. Lower `--token-budget`, use a stronger permitted model, or increase `GRAPHIFY_API_TIMEOUT` when needed.

## Current limitations

- Raster images are described to Copilot as references; use `copilot-sdk` when first-class image attachments are required.
- Silent text output does not identify the actual model selected by `auto`, so Graphify records the requested model value.
- Copilot CLI may export OpenTelemetry traces or metrics when enabled by process environment or enterprise-managed settings. Graphify does not override those administrator controls.
- There is no live enterprise-environment test in the repository test suite. Tests mock the executable, process environment, stdin, output, and failure modes so they require no credentials and send no data externally.
