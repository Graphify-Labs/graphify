# GitHub Copilot SDK backend

Graphify can use an existing GitHub Copilot subscription for semantic
extraction. The backend is optional and explicit. Graphify never auto-selects
it.

## Install and run

The official Python SDK requires Python 3.11 or later. Install and authenticate
the [official Copilot CLI](https://docs.github.com/en/copilot/how-tos/copilot-cli/set-up/install-copilot-cli)
before the first Graphify request; the Python package supplies the SDK runtime,
but it does not add a `copilot` executable to Graphify's virtual environment.

```bash
uv tool install --python 3.12 "graphifyy[copilot]"
copilot login
graphify extract ./docs --backend copilot-sdk
```

For GitHub Enterprise Cloud with data residency, sign in to the correct host
and keep that host in the environment used by Graphify:

```bash
copilot login --host https://example.ghe.com
export COPILOT_GH_HOST=example.ghe.com
graphify extract ./docs --backend copilot-sdk
```

PowerShell:

```powershell
$env:COPILOT_GH_HOST = "example.ghe.com"
graphify extract ./docs --backend copilot-sdk
```

## Request isolation

Each request uses:

- a fresh SDK client and session;
- an empty temporary working and configuration directory;
- no tools, MCP servers, skills, memory, hooks, or host Git operations;
- rejected permission requests;
- disabled session storage, remote sessions, and session telemetry.

The SDK reads the existing Copilot login from `COPILOT_HOME` or the default
Copilot home. Graphify does not copy or persist Copilot credentials.

The selected model still receives the document chunks and image attachments.
Use this backend only for data approved for the signed-in Copilot account and
its enterprise policy.

## Failure behavior

Graphify does not fall back to another backend. A startup failure happens
before source data is sent and can be retried safely. A timeout or connection
failure after dispatch has an unknown outcome, so Graphify reports it and does
not replay the request.

The SDK can download its platform runtime when the client is first constructed.
That one-time setup can take longer than `GRAPHIFY_API_TIMEOUT`, but Graphify
checks the deadline again and will not dispatch source data after it expires.
Run `python -m copilot download-runtime` from the same Python environment before
the first Graphify request when a strict startup limit is required.

Cleanup is bounded. If cleanup fails after a valid response arrived, Graphify
keeps the valid response and emits a warning.

## Configuration

Model precedence is:

1. `--model`
2. `GRAPHIFY_COPILOT_SDK_MODEL`
3. `GRAPHIFY_COPILOT_MODEL`
4. `COPILOT_MODEL`
5. the account or runtime default

Optional settings:

- `GRAPHIFY_COPILOT_REASONING_EFFORT`: `low`, `medium`, `high`, `xhigh`, or `max`
- `GRAPHIFY_COPILOT_CONTEXT_TIER`: `default` or `long_context`
- `GRAPHIFY_API_TIMEOUT`: whole-request timeout in seconds
- `GRAPHIFY_COPILOT_SDK_PARALLEL=1`: allow concurrent requests; serial is the default

## Images and usage

Raster images are sent as inline blob attachments with relative display names.
Absolute host paths are not exposed as attachment names.

When the SDK supplies usage events, Graphify records token counts and the
per-call premium-request multiplier. It does not mix that value with nano-AI
units or convert it into a USD price claim.

## Live verification

The normal test suite mocks the SDK and needs no account. An authenticated live
check is opt-in:

```bash
GRAPHIFY_COPILOT_E2E=1 \
GRAPHIFY_COPILOT_E2E_HOME="$HOME" \
uv run --extra copilot pytest tests/e2e/test_copilot_sdk_live.py -q
```

`GRAPHIFY_COPILOT_E2E_HOME` is explicit because the normal test harness replaces
`HOME` to protect developer configuration. The live test uses only a synthetic
one-line document and does not inspect the repository.
