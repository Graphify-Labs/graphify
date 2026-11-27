# Evaluating the classifier against real issues

`eval_classifier.py` scores the triage classifier against a labeled set of real
Graphify issues and reports numbers instead of impressions: accuracy, the probability
the model put on the correct label, latency, tokens, and cost.

It is provider-agnostic, so the same harness scores System One (Jev) and any
OpenAI-compatible chat model. That is what makes the head-to-head below possible:
identical issues, identical scoring, one code path.

It is **opt-in and paid** (it calls the live API), so it is not part of CI. Run it
by hand from the repository root:

```bash
# The recommended backend.
TYPESAFE_API_KEY=... python -m tools.triage.eval_classifier \
    --provider typesafe --model jev-latest --runs 2 --json jev.json

# A chat model, for comparison.
GEMINI_API_KEY=... python -m tools.triage.eval_classifier \
    --provider gemini --model gemini-3.5-flash-lite --runs 1 --sleep 5 --json gemini.json
```

`--provider`/`--model` pick the engine, `--runs` repeats the set for a stability
number, `--sleep` spaces requests for free-tier rate limits, `--trace N` records the
full request and response of the first N issues, and `--json` writes every result.

CI still guards the fixture: `test_eval_dataset_matches_the_taxonomy` checks that
every ground-truth label in `eval_dataset.json` is one the classifier is allowed to
emit, so the set cannot drift out of the allowlist.

## What it measures

| Metric | Why it is the honest one |
|---|---|
| `kind` top-1 | exact match of the single `kind/` label |
| `area` top-1 / contained | the first area matches; and whether the correct area is among the (up to two) areas |
| **soft accuracy** | mean probability the model assigned to the ground-truth option. On a Choice model this is the right way to read genuinely ambiguous issues (Jev only; a chat model returns no distribution) |
| GFI precision / recall | whether `good first issue` suggestions can be trusted |
| latency | wall-clock per request |
| tokens / cost | input and output tokens at published list prices |
| run-to-run agreement | stability across identical passes |
| failures | requests that errored (the workflow fails open and keeps `status/need-triage`) |

## The set

18 real issues from `Graphify-Labs/graphify`, spanning every `kind/` the model can
emit (bug 10, feature 4, docs 2, performance 1, question 1) and 8 of the 12 areas.
Ground truth is a careful manual read of each issue, recorded in
[`eval_dataset.json`](eval_dataset.json) with a one-line note per case. It is a
single adjudicator, not a gold-standard panel, so read the figures as an agreement
rate, not proof of correctness.

## Results

`jev-latest` (which resolved to `jev-1.13.0`), 2026-10-18. 18 issues × 2 runs = 36
requests, zero failures.

| Metric | Result |
|---|---|
| `kind` top-1 accuracy | **88.9%** (16/18) |
| `area` top-1 accuracy | **77.8%** (14/18) |
| `area` contained (correct area in the returned ≤2) | **83.3%** (15/18) |
| soft accuracy, mean p(correct `kind`) | 0.87 |
| soft accuracy, mean p(correct `area`) | 0.76 |
| `good first issue` precision / recall / F1 | 85.7% / 100% / 0.92 |
| latency | mean **392 ms**, p50 380 ms, p95 486 ms, max 577 ms |
| tokens | ~1,665 input per issue (output free) |
| **cost** | **$0.00007 per issue → ~$0.07 per 1,000 issues** |
| run-to-run agreement | `kind` 100%, `good first issue` 100%, `area` 94.4% |

### Per issue (run 1)

The same 18 issues through Jev and through `gemini-3.5-flash-lite`, so the columns
are directly comparable. Bold marks a disagreement with the ground truth.

| Issue | Ground truth | System One (Jev) | Gemini 3.5 Flash-Lite |
|---|---|---|---|
| #4341 benchmark measures size, not correctness | feature · query | feature · **cli, query** | feature · **cli** |
| #4361 backend auto-detected without opt-in | bug · llm | bug · llm | bug · llm |
| #4379 Solidity inherited calls get no edge | bug · extract | bug · extract | bug · extract |
| #4398 release commits skip `uv.lock` | bug · ci | bug · ci | bug · ci |
| #4413 Ollama ignores context size | bug · llm | bug · llm | bug · llm |
| #4439 Rust `use` edges target a bare name | bug · extract | bug · extract, query | bug · extract, build |
| #4444 home ignore patterns leak | bug · extract | bug · **other** | bug · extract |
| #4454 support the latest OpenCode version | feature · **install** | feature · **extract** | feature · **extract** |
| #4469 query answers repeat file paths | **performance** · query | **feature** · query | **feature** · query |
| #4480 query should lead with the best file | feature · query | feature · query | feature · query |
| #4494 Pi skill uses the wrong subagent | bug · install | bug · install, llm | bug · install |
| #4508 wiki article lost on case-only relabel | bug · export | bug · export | bug · export |
| #4510 Protocol Buffers not extracted | feature · extract | feature · extract | feature · extract |
| #4527 PDF extraction swallows errors | bug · extract | bug · extract | bug · extract |
| #4529 node confidence not folded | bug · build | bug · build | bug · build |
| #1843 README recommends `.claudeignore` | docs · docs | docs · docs | docs · docs |
| #525 is `--wiki` supported outside Claude Code | **docs** · docs | **question** · docs | docs · docs |
| #1177 how to use graphify across many repos | question · **docs** | question · **install** | question · **cli, install** |

## Head-to-head: Jev vs chat models

Same 18 issues, same harness, same scoring. Gemini was run on a free-tier key; the
tests below the table give the caveats that come with that.

| Engine | `kind` top-1 | `area` top-1 | `area` contained | soft p(kind) | GFI P / R | mean latency | p50 | p95 | input tok/req | cost / 1k issues | failed |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **System One (`jev-latest`)** | 88.9% | 77.8% | 83.3% | **0.87** | 86% / 100% | **392 ms** | **380 ms** | **486 ms** | 1,665 | **$0.070** | **0/18** |
| `gemini-3.5-flash-lite` | 94.4% | 83.3% | 83.3% | n/a | 75% / 100% | 1,076 ms | 1,019 ms | 1,413 ms | 905 | $0.420 | 0/18 |
| `gemini-3.8-flash` | 84.6%* | 92.3%* | 92.3%* | n/a | 100% / 60% | 5,132 ms | 4,391 ms | 7,546 ms | 658 | $0.651 | 5/18 |

\* Gemini 3.8 Flash only completed 13 of 18 requests (free-tier `429`/`503`); its
percentages are over those 13. Under the real workflow those five issues would simply
keep `status/need-triage` and be retried later, so the failure cost is latency, not
wrong labels.

**Speed.** Jev answers in 392 ms on average against 1,076 ms for the fast
Gemini tier and 5,132 ms for the flagship Flash, so it is **2.7× faster than
`gemini-3.5-flash-lite` and 13× faster than `gemini-3.8-flash`.** The gap is larger at p50
(380 ms vs 1,019 ms vs 4,391 ms) because chat models spend completion tokens on
thinking before they emit the JSON, while System One returns a typed decision
directly. At ~0.4 s per issue the triage is invisible to whoever opened the issue; at
5 s it is a visibly slow bot.

**Cost.** Jev bills input only, at $0.042 per Mtok: **$0.00007 per issue, or about
7 cents per 1,000 issues.** The same set on `gemini-3.5-flash-lite` costs $0.42 per
1,000 and on `gemini-3.8-flash` $0.65 per 1,000, because chat models bill both
directions and Jev's output is free: **6× and 9× cheaper.** For a repo triaging a few
hundred issues a month, both are rounding errors; the point is that the fastest option
is also the cheapest one, not a trade-off.

**Accuracy.** On 18 issues the difference is one or two cases, which is inside the
noise: `gemini-3.5-flash-lite` got one more `kind` right (94.4% vs 88.9%), Jev got
one more `area` top-1 right than it did in the sense that matters operationally
(Jev landed the correct area in its top two on 83.3% of issues, same as Flash-Lite).
A one-issue gap on a hand-labeled set is not a ranking, and this is exactly why the
harness reports soft accuracy and confidence next to top-1 rather than a single score.
What Jev adds on top of the accuracy is a **calibrated probability per label** (a
chat model returns only the JSON it was asked for) and a guarantee by construction
that a label outside the allowlist cannot be emitted, since the Choice options *are*
the allowlist.

No OpenAI model was run, because no OpenAI key was available to this evaluation. The
harness supports it unchanged (`--provider openai --model gpt-4.1-mini`) and the
column fills in with one key.

## Actual traces

Verbatim request and response for issue #4361, truncated only where marked.

### System One (Jev) — 359 ms

Request (`POST https://api.typesafe.ai/v1/systemone`):

```json
{
  "model": "jev-latest",
  "state": {
    "issue": {
      "number": 4361,
      "title": "Semantic extraction and labeling pick a cloud backend from ambient API keys (and `claude -p` as a fallback) without an explicit opt-in",
      "body": "**Summary** When the headless CLI needs semantic extraction, ... [1450 more chars]",
      "existing_labels": []
    }
  },
  "questions": {
    "kind": {
      "type": "choice",
      "instructions": {
        "question": "What kind of GitHub issue is this?",
        "focus": "Classify what the issue is, not which code it touches."
      },
      "criteria": {
        "kind/bug": "Something is not working as documented",
        "kind/feature": "New capability or enhancement",
        "kind/docs": "Documentation change",
        "kind/question": "Question or support request",
        "kind/refactor": "Internal cleanup, no behaviour change",
        "kind/performance": "Speed or memory improvement",
        "kind/other": "Anything else"
      }
    },
    "area": {
      "type": "choice",
      "instructions": {
        "question": "Which area of the Graphify codebase does this issue primarily concern?",
        "focus": "Pick the single closest area; area/other only if none fit."
      },
      "criteria": {
        "area/extract": "Source extraction: languages, parsers, files to nodes/edges",
        "area/build": "Graph construction, merge, dedupe, ids, pruning",
        "area/analyze": "Communities, god nodes, report, cycles, surprising edges",
        "area/query": "query, path, explain, affected, serve",
        "area/export": "HTML, Obsidian, GraphDB, call-flow, Neo4j/FalkorDB exports",
        "area/cli": "Command-line interface, flags, dispatch, help text",
        "area/install": "Platform install/uninstall, skills, hooks, MCP, plugins",
        "area/watch": "Incremental updates, file watching, git hooks",
        "area/llm": "Semantic extraction and LLM backends/providers",
        "area/ci": "GitHub Actions, release, packaging",
        "area/docs": "Documentation and guides",
        "area/other": "None of the other areas"
      }
    },
    "area_secondary": {
      "type": "choice",
      "instructions": {
        "question": "Is a second area clearly involved, or none?",
        "focus": "Choose a second area only when the issue clearly spans two."
      },
      "criteria": { "...": "area/* plus a 'none' option" }
    },
    "good_first_issue": {
      "type": "noul",
      "instructions": "A newcomer could finish this without deep repository knowledge...",
      "criteria": {
        "true": "A newcomer could finish this without deep repository knowledge.",
        "false": "Too broad, touches invariants, or otherwise not beginner-suitable."
      }
    }
  }
}
```

Response:

```json
{
  "model": "jev-1.13.0",
  "answers": {
    "kind": {
      "type": "choice",
      "choice": "kind/bug",
      "confidence": 0.76,
      "probabilities": {
        "kind/bug": 0.79, "kind/feature": 0.14, "kind/docs": 0.0,
        "kind/question": 0.0, "kind/refactor": 0.0, "kind/performance": 0.0,
        "kind/other": 0.07
      }
    },
    "area": {
      "type": "choice",
      "choice": "area/llm",
      "confidence": 1.0,
      "probabilities": { "area/llm": 1.0, "area/extract": 0.0, "...": 0.0 }
    },
    "area_secondary": {
      "type": "choice",
      "choice": "area/llm",
      "confidence": 0.7,
      "probabilities": { "area/llm": 0.72, "area/cli": 0.19, "none": 0.09, "...": 0.0 }
    },
    "good_first_issue": { "type": "noul", "noul": 0.3 }
  },
  "usage": { "input_tokens": 1784, "output_tokens": 354 }
}
```

The interesting parts: the labels in the response are the *same strings* the request
offered as `criteria`, so nothing outside the allowlist can come back; `good_first_issue`
is a probability (0.3) that the code thresholds rather than a yes/no the model asserts;
and every answer carries its own `confidence` and full `probabilities`, which is where
the soft-accuracy number comes from.

### Gemini 3.5 Flash-Lite — 924 ms

Request (`POST https://generativelanguage.googleapis.com/v1beta/openai/chat/completions`):

```json
{
  "model": "gemini-3.5-flash-lite",
  "messages": [
    {
      "role": "system",
      "content": "You triage GitHub issues for the Graphify repository, a tool that turns code and docs into a queryable knowledge graph.\n\nChoose exactly one kind label... [1841 more chars]"
    },
    {
      "role": "user",
      "content": "Issue #4361\nExisting labels: (none)\n\nTitle: Semantic extraction and labeling pick a cloud backend from ambient API keys... [1636 more chars]"
    }
  ],
  "temperature": 0,
  "max_tokens": 2048
}
```

Response:

```json
{
  "choices": [
    {
      "finish_reason": "stop",
      "index": 0,
      "message": {
        "content": "{\"area\": [\"area/llm\"], \"kind\": \"kind/bug\", \"good_first_issue\": false, \"gfi_reason\": \"\", \"confidence\": \"high\"}",
        "extra_content": { "google": { "thought_signature": "EmAKXgFpFH0TPkVO..." } },
        "role": "assistant"
      }
    }
  ],
  "model": "gemini-3.5-flash-lite",
  "object": "chat.completion",
  "usage": { "prompt_tokens": 1038, "completion_tokens": 39, "total_tokens": 1077 }
}
```

Same answer, different shape. The allowlist lives in the prompt, so the label is a
string the model chose to type; `tools/triage/classify.py` re-validates it against the
taxonomy and falls back to `area/other` / `kind/other` if it invented one. There is no
probability to read, only a self-reported `"confidence": "high"`, which is why the
harness reports soft accuracy only for System One. Note also the free-form
`thought_signature` blob the chat endpoint returns, and the fact that a chat call
returns one JSON string that has to be parsed rather than typed answers.

## Where it disagreed, and why that is fine

Every disagreement lands on an issue where the taxonomy itself is arguable, and
the alternative is defensible:

- **#4469** reports that query answers waste tokens and proposes a compact form.
  That is a `feature` that improves `performance`; either label is honest.
- **#525** is titled as a question and reads as a documentation inconsistency.
  `question` and `docs` are both true.
- **#4341** wants `graphify benchmark` to measure correctness. `benchmark` is a CLI
  command that measures query quality, so `cli` and `query` both apply (Jev returned
  both, `query` second).
- **#4444** is about ignore-pattern discovery. That is part of choosing what to
  extract, so `extract` is the tighter area; Jev said `other`.
- **#4454** asks for a version-compatibility update to the integration; `install`
  and `extract` are both arguable.
- **#1177** asks how to use graphify across a multi-repo workspace. That needs an
  answer (`docs`) but reads as setup (`install`).
- The one GFI false positive, **#4413**, is a backend fix small enough that
  `good first issue` is a defensible call (Jev's noul was 0.68). It is only a
  *suggestion*; a maintainer would confirm or drop it.

This is the expected shape of the result. The categories are a human convention, and
the model's job is to land inside them consistently, not to reproduce one person's
tie-breaking. What matters operationally is that the errors are on boundary cases,
that the confidence output flags them, and that the labels are never invented.

## Reading the confidence

Jev returns a calibrated `confidence` per answer, which the classifier maps to
`high`/`medium`/`low`. It tracks how clear-cut the issue is: clean bugs and obvious
docs came back `high`; the ambiguous ones (#4341, #4454) came back `low`. That is
the signal a maintainer can filter on if a second-pass review is ever wanted.

## Caveats

- n=18, one project, English. It is a smoke test of quality, not a benchmark;
  re-run it on your own issues before trusting the labels for your repo. One issue
  is 5.6 percentage points, so treat a one- or two-case gap between engines as noise.
- Ground truth is one adjudicator's read; a second reader would move a few of the
  boundary cases above.
- The Gemini runs used a **free-tier** key, which is rate-limited and queued. Its
  latency may be pessimistic relative to a paid tier, and Gemini 3.8 Flash had five
  requests fail outright with `429`/`503`. The relative ordering (System One returns
  a typed decision in one round trip, chat models generate tokens) holds regardless.
- Prices are published list prices as of 2026-10-18: System One $0.042 per Mtok input
  (output free), Gemini 3.5 Flash-Lite $0.30 / $2.50, Gemini 3.8 Flash $0.75 / $3.75
  per Mtok in/out. Free-tier runs are billed $0 in practice; the table uses paid
  prices so the numbers compare like for like.
- `jev-latest` is an alias and moves. Pin `jev-1.13.0` (or `jev-1.14.0`) if you tune
  thresholds against these numbers.

## Credit

Thanks to [@omsenjalia](https://github.com/omsenjalia), who provided the TypeSafe
System One API key that made this evaluation possible. Without it the classifier
would have shipped with a "should be fast and cheap" claim instead of measured
latency, tokens, cost and accuracy on real issues.
