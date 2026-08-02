# GitHub Copilot SDK backend

Graphify's `copilot-sdk` backend uses the official Python package `github-copilot-sdk` as the preferred GitHub Copilot transport and retains the existing `copilot-cli` backend as an automatic fallback. It supports semantic extraction, LLM-assisted deduplication, community naming, PR triage, and raster-image attachments.

The backend is explicit-only. Graphify does not select Copilot merely because the SDK package or a `copilot` executable is installed. Corpus content is sent through Copilot only after `--backend copilot-sdk` or `--backend copilot-cli` is selected.

## Architecture

```text
Graphify
   |
   | preferred
   v
GitHub Copilot Python SDK
   |
   | JSON-RPC over stdio
   v
Enterprise-authenticated Copilot CLI runtime
   |
   v
GitHub Copilot service

If SDK startup or request handling fails:
Graphify -> one-shot copilot-cli fallback -> GitHub Copilot service
```

Graphify keeps one SDK client and headless runtime alive for the process, but creates a new isolated session with a unique ID for every LLM request. Before returning, it disconnects and permanently deletes that session. This avoids a full runtime startup per document chunk without carrying conversation state from one Graphify request into another.

## Requirements and installation

The official Python SDK requires Python 3.11 or newer. Graphify itself continues to support Python 3.10, so the dependency is optional and guarded by a Python-version marker.

For a tool installation, choose Python 3.11 or newer explicitly:

```bash
uv tool install --python 3.12 "graphifyy[copilot]"
```

Alternative installs:

```bash
pipx install --python python3.12 "graphifyy[copilot]"
python -m pip install "graphifyy[copilot]"

# From a Graphify source checkout:
python -m pip install -e ".[copilot]"
```

On Python 3.10, `--backend copilot-sdk` remains a valid explicit backend, but the SDK cannot load and Graphify immediately uses the installed `copilot-cli` fallback. To require the SDK and reject fallback, use Python 3.11+ and set `GRAPHIFY_COPILOT_SDK_FALLBACK=0`.

## GitHub Enterprise Cloud setup

Graphify uses the enterprise login and credential store owned by the official Copilot CLI. Authenticate the managed CLI first:

```bash
copilot version
copilot login --host https://example.ghe.com
```

Pin the host when launching Graphify so another stored account cannot be selected accidentally.

### bash or zsh

```bash
export COPILOT_GH_HOST=example.ghe.com
graphify extract ./docs \
  --backend copilot-sdk \
  --model auto
```

### PowerShell

```powershell
$env:COPILOT_GH_HOST = "example.ghe.com"
graphify extract ./docs `
  --backend copilot-sdk `
  --model auto
```

The organization or enterprise providing the Copilot seat must permit Copilot CLI/SDK use, and the requested model must be available under that policy.

## Runtime selection

For managed enterprise workstations, Graphify defaults to the system-installed `copilot` executable. This is the same executable authenticated with `copilot login --host ...` and is easier for administrators to inventory and approve.

Resolution order is:

1. `GRAPHIFY_COPILOT_SDK_CLI_PATH`
2. `COPILOT_CLI_PATH`
3. `copilot.cmd` on Windows, then `copilot`
4. `copilot` on other platforms

To use the SDK's version-pinned downloaded runtime instead of the system executable:

```bash
export GRAPHIFY_COPILOT_SDK_USE_BUNDLED_CLI=1
python -m copilot download-runtime
```

Bundled-runtime mode is opt-in because it may introduce a second Copilot executable outside the workstation's normal software-management path. Authentication still comes from the signed-in user or supported token environment variables.

## Model selection

Precedence for `copilot-sdk` is:

1. `--model`
2. `GRAPHIFY_COPILOT_SDK_MODEL`
3. `GRAPHIFY_COPILOT_MODEL`
4. `COPILOT_MODEL`
5. `auto`

`auto` lets Copilot select an eligible model. A specific model name is still subject to enterprise policy and account entitlement.

The standalone `copilot-cli` backend retains its existing precedence: `--model`, `GRAPHIFY_COPILOT_CLI_MODEL`, `COPILOT_MODEL`, then `auto`.

## Isolation and safety behavior

For SDK requests, Graphify:

- starts the client with `mode="empty"`, so ambient CLI filesystem, shell, MCP, skill, and workspace capabilities are not exposed by default;
- uses a newly created empty temporary working directory and temporary `COPILOT_HOME` rather than the source repository or the user's normal Copilot state directory;
- supplies an empty tool allowlist and no MCP servers;
- rejects every permission request as a second line of defense;
- disables persistent Copilot memory and infinite-session persistence;
- disables remote sessions and does not configure SDK telemetry;
- creates a fresh uniquely identified session per request, then disconnects and permanently deletes it after the response;
- preserves `COPILOT_GH_HOST` and the normal Copilot authentication environment without parsing, printing, or persisting token values; and
- fails closed when the installed SDK lacks any required isolation or session-deletion option, and discards the runtime if cleanup cannot be verified, then uses the separately hardened CLI fallback when enabled.

The model still receives every document chunk sent for semantic extraction. These controls limit local agent capabilities; they do not constitute authorization to process any particular category of data. Enterprise policy, approved-use boundaries, and user-scoped Copilot configuration still apply.

## Image handling

The SDK backend sends raster images as first-class file attachments with an absolute path. The Copilot runtime reads and encodes the image. Graphify therefore does not load the image into a base64 request body.

If an SDK request falls back to the one-shot CLI backend, the CLI path has no equivalent attachment channel in this integration. Graphify changes the fallback prompt so it accurately describes the image as an unseen file reference rather than claiming the pixels were attached.

## Automatic CLI fallback

Fallback is enabled by default. It covers Python 3.10, a missing or incompatible SDK package, runtime startup errors, JSON-RPC transport failures, request timeouts, and other SDK exceptions. Graphify prints one warning for each distinct SDK failure and runs that request through `copilot-cli`.

Disable fallback when validation requires proof that the SDK path was used:

```bash
export GRAPHIFY_COPILOT_SDK_FALLBACK=0
```

When both transports fail, Graphify reports both causes in one error. The CLI fallback uses the same requested model and the same enterprise host/authentication environment.

## Concurrency

SDK requests are serial by default even though the runtime is persistent. Semantic extraction can generate many prompts and retries; serial dispatch avoids accidental bursts against an enterprise seat and simplifies session isolation.

After validating account and policy limits, parallel dispatch can be enabled with:

```bash
export GRAPHIFY_COPILOT_SDK_PARALLEL=1
```

`--max-concurrency` then controls the upper bound. The standalone CLI transport has its own `GRAPHIFY_COPILOT_CLI_PARALLEL=1` opt-in.

## Authentication troubleshooting

Check the host and any token variables that can override the stored enterprise login:

```bash
printf '%s\n' "$COPILOT_GH_HOST"
env | grep -E '^(COPILOT_GITHUB_TOKEN|GH_TOKEN|GITHUB_TOKEN)='
```

PowerShell:

```powershell
$env:COPILOT_GH_HOST
Get-ChildItem Env:COPILOT_GITHUB_TOKEN,Env:GH_TOKEN,Env:GITHUB_TOKEN -ErrorAction SilentlyContinue
```

Then validate the CLI independently and retry a small approved corpus:

```bash
copilot version
copilot login --host https://example.ghe.com
COPILOT_GH_HOST=example.ghe.com graphify extract ./docs \
  --backend copilot-sdk --model auto
```

Common failures:

- **SDK not installed or Python too old:** install `graphifyy[copilot]` under Python 3.11+, or permit the CLI fallback.
- **System CLI not found:** install the official CLI, set `GRAPHIFY_COPILOT_SDK_CLI_PATH`, or explicitly opt into the SDK-downloaded runtime.
- **Wrong account or host:** repeat the GHE.com login, set `COPILOT_GH_HOST`, and remove conflicting token variables.
- **Login works in the standalone CLI but the SDK reports no stored login:** Graphify deliberately gives the SDK runtime a temporary `COPILOT_HOME`. OAuth credentials in the system keychain remain available, but a plaintext file fallback stored only under the user's normal `COPILOT_HOME` is not copied. Use the automatic `copilot-cli` fallback, or a policy-approved token environment variable, on hosts without a credential store.
- **SDK/CLI version mismatch:** upgrade the system CLI or use `GRAPHIFY_COPILOT_SDK_USE_BUNDLED_CLI=1` with the SDK's matching downloaded runtime.
- **Model unavailable:** use `--model auto` or select a model enabled by enterprise policy.
- **Timeout:** increase `GRAPHIFY_API_TIMEOUT`; Graphify discards the failed SDK runtime before the next attempt.
- **Malformed graph JSON:** Graphify marks a hollow result as truncated and adaptively retries smaller chunks; lowering `--token-budget` can help.

## Accounting and limitations

The SDK response currently does not provide Graphify with provider-style token and billing fields, so Graphify records character-based token estimates and `$0` in its own provider-cost estimator. Copilot requests can still consume GitHub AI credits or another plan allowance.

The repository tests replace the SDK, runtime, executable, network, and credentials with fakes. They verify lifecycle reuse, temporary Copilot state, per-request session isolation and deletion, cleanup-failure handling, tool denial, enterprise-host inheritance, image attachments, Python-version behavior, SDK-to-CLI fallback, and dispatch through extraction/deduplication/labeling/triage. They do not authenticate to an external GitHub host or transmit user data.

For the standalone fallback transport, see [GitHub Copilot CLI backend](copilot-cli-backend.md).
