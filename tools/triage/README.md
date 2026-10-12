# Issue triage

Automated first-pass triage for issues in this repository. Every issue is stamped
on open, then a classifier picks `area/` and `kind/` labels from a fixed allowlist
and suggests a good first issue — the same shape of automation most production
open-source projects run today.

## What it does

1. **`status/need-triage` on open.** `.github/workflows/issue-triage.yml` stamps
   every new issue so nothing is lost. No model involved.
2. **`area/` + `kind/` classification.** One model call (or a fallback chain)
   reads the issue title and body, chooses labels **only from a fixed allowlist**,
   and replies with JSON. A `github-script` step applies the labels and sets
   `status/bot-triaged`.
3. **`good first issue` is only suggested.** A wrong `good first issue` hurts a
   beginner more than none, so the bot posts a comment and adds
   `status/gfi-suggested` for a maintainer to confirm. It never applies
   `good first issue` itself.

If there is no API key configured, or the model errors, the classifier fails
**open**: the issue keeps `status/need-triage` and nothing is mislabelled.

## The taxonomy

`taxonomy.py` is the single source of truth:

- `area/*` — where the work lands (12 labels). The model picks one, or two.
- `kind/*` — what the issue is (7 labels). The model picks exactly one.
- `status/*` — workflow state (`need-triage`, `bot-triaged`, `gfi-suggested`).
  Never chosen by the model.

`sync_labels.py` creates/updates exactly these labels on the repo (idempotent).
Pre-existing labels (`bug`, `enhancement`, `good first issue`, ...) are untouched.
It runs from `labels-sync.yml` whenever `taxonomy.py` changes, and again as the
first job of `issue-triage.yml` so a fresh repo cannot fail on a missing label.

## Configuration

Works with any provider. Set one key as a repository **secret** and it is
auto-detected; nothing else is required:

| Provider | Secret | Default model | API |
|---|---|---|---|
| **TypeSafe (System One / Jev)** | `TYPESAFE_API_KEY` (or `JEV_API_KEY`) | `jev-latest` | typed questions |
| OpenAI | `OPENAI_API_KEY` | `gpt-4.1-mini` | chat |
| Gemini | `GEMINI_API_KEY` / `GOOGLE_API_KEY` | `gemini-3-flash-preview` | chat |
| DeepSeek | `DEEPSEEK_API_KEY` | `deepseek-v4-flash` | chat |
| Groq | `GROQ_API_KEY` | `llama-3.3-70b-versatile` | chat |
| OpenRouter | `OPENROUTER_API_KEY` | `openai/gpt-4.1-mini` | chat |
| Kimi | `MOONSHOT_API_KEY` | `kimi-k2.6` | chat |
| Ollama | `OLLAMA_API_KEY` (any value; local) | `qwen2.5-coder:7b` | chat |

**TypeSafe / Jev** is the recommended backend (it is what the Graphify bot routes
decisions through). It is not a chat model — the classifier sends typed
`questions` and gets typed `answers`, so labels are type-safe by construction:

- `kind` → a `choice` over the `kind/*` allowlist
- `area` → a `choice` over the `area/*` allowlist
- `area_secondary` → a second `choice`, or `none`
- `good_first_issue` → a `noul` (yes/no probability), thresholded in code

Each answer carries a calibrated `confidence`, mapped to our `high`/`medium`/`low`.
Endpoint: `POST https://api.typesafe.ai/v1/systemone`; see
<https://docs.typesafe.ai/api>. Everything else is an OpenAI-compatible chat
provider. Auto-detection order: TypeSafe, OpenAI, Gemini, DeepSeek, Kimi, Groq,
OpenRouter (Ollama is never auto-selected). Any OpenAI-compatible gateway
(LiteLLM, vLLM, Azure, ...) works via `TRIAGE_BASE_URL` + `TRIAGE_API_KEY`.

### Variables (optional overrides)

| Variable | Meaning | Default |
|---|---|---|
| `TRIAGE_PROVIDER` | provider for unprefixed models | auto-detected |
| `TRIAGE_MODEL` | model id, or a comma-separated list for fallback | provider default |
| `TRIAGE_BASE_URL` | override the default provider's base URL | provider endpoint |
| `TRIAGE_MAX_TOKENS` | completion budget | `2048` |
| `TRIAGE_TIMEOUT` | seconds per call | `60` |
| `TRIAGE_DRY_RUN` | report proposed labels in a comment, change nothing | unset |

`TRIAGE_API_KEY` overrides the default provider's key.

### Combinations (fallback chain)

`TRIAGE_MODEL` may be a comma-separated list; the models are tried **in order**
and the first one that returns usable JSON wins. This is the robust setting given
transient 429/503s, and it can mix providers with a `provider:` prefix:

```
TRIAGE_MODEL = "openai:gpt-4.1-mini, gemini:gemini-3.8-flash, gemini-2.5-flash"
```

Prefixed entries use that provider's own key; unprefixed entries use the default
provider. If every model fails, the classifier fails open and the issue keeps
`status/need-triage`.

Reasoning models (for example `gemini-3.x-flash`) spend completion tokens on
thinking before they emit the JSON, so a small `TRIAGE_MAX_TOKENS` truncates the
reply (`finish_reason=length`) and the issue is skipped. The default leaves room;
raise it for chattier models, or list a non-reasoning model as a fallback.

## Local use

```bash
# Classify an issue payload (same JSON the workflow passes):
echo '{"number":1,"title":"Crash on parse","body":"..."}' \
  | OPENAI_API_KEY=... python -m tools.triage.classify
# or GEMINI_API_KEY=... , or any gateway via TRIAGE_API_KEY=... TRIAGE_BASE_URL=...

# Create/update the labels (needs a token with issues:write):
GITHUB_TOKEN=... GITHUB_REPOSITORY=owner/repo python -m tools.triage.sync_labels
```

Tests: `pytest tests/test_triage.py` (pure logic, no network).

## Tuning

- Allowed labels and their descriptions: edit `taxonomy.py`. Both the model
  allowlist and the created labels follow automatically.
- The good-first-issue definition: `taxonomy.GFI_DEFINITION`.
- To re-triage an issue, remove **both** its `area/` labels and
  `status/bot-triaged`, then reopen it. `bot-triaged` alone still short-circuits
  triage, so removing only `area/` is not enough. There is no manual-dispatch
  trigger; a fresh `opened`/`reopened` event is what re-runs it.
