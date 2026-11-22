# Token guard: keeping the Claude Code context small

Most of what a long Claude Code session costs is not new work. It is the same
context being read again on every request. On the machine this was built on,
58,000 requests over two months averaged 356k tokens of context each, and
requests sent with more than 200k of context accounted for 88% of all tokens.
Tool output was the main thing filling that context, and two thirds of it came
from Bash.

Three commands address this. They need no graph and work in any directory.

## `graphify usage`: see where the tokens went

Reads the Claude Code transcripts under `~/.claude/projects` (or
`$CLAUDE_CONFIG_DIR/projects`) and reports totals by model, day and project,
context size per request, the heaviest sessions, an estimate of fixed
per-session overhead, tool-result size per tool, and repeated reads.

```bash
graphify usage                 # terminal summary
graphify usage --days 7        # last week only
graphify usage --project myapp # one project
graphify usage --html          # self-contained report at graphify-out/usage.html
graphify usage --json          # machine-readable
```

Only counts, sizes, file paths, model names and dates are reported. Prompt
text and file contents are never written to the report.

## `graphify token-guard`: hooks that keep context from growing

```bash
graphify token-guard install            # user settings: applies to every session
graphify token-guard install --project  # ./.claude/settings.json only
graphify token-guard status
graphify token-guard uninstall
```

`install` adds these Claude Code hooks and leaves every other setting alone:

| Hook | Event | What it does |
|---|---|---|
| `bash-cap` | PostToolUse, Bash | Output above 20,000 characters is cut to its head and tail. The full output is saved to a file and the path is stated in the cut. |
| `budget` | UserPromptSubmit | When the context first passes 200k tokens, and at every further 100k, states the size and that `/compact` or a fresh session would shrink it. |
| `reread` | PreToolUse, Read | A second read of a file that is unchanged and already in context is declined once. Asking again is allowed. |
| `read-done` | PostToolUse, Read | Records the range a Read returned, for `reread`. PostToolUse runs only after the tool succeeded, so a Read that failed or was blocked is never counted as in context. |
| `reset` | SessionStart, compact | Compaction drops file contents from context, so the read records are cleared. |
| `daily` | SessionStart, startup | Once a day, shows what the guard kept out of context the day before. |

Every hook fails open: on any error it prints nothing and the tool call
proceeds unchanged.

`reread` declines only what `read-done` recorded. Settings written by an
earlier version have no `read-done` entry: nothing is recorded there, so
nothing is declined, until `graphify token-guard install` is run again (it
replaces its own entries and adds the missing one). `uninstall` removes only
commands of the form `<graphify> token-guard <hook>`; a command of your own
that merely contains those words is left as it is.

### What it saved

```bash
graphify token-guard savings           # last 7 days
graphify token-guard savings --days 30 --json
```

The figures are the characters the guard kept out of context, with tokens
estimated at four characters each. That is a lower bound: anything kept out of
context would also have been re-read on every later request in that session.
To measure the overall effect, compare `graphify usage --days 7` before and
after a week of use.

### Settings

| Variable | Default | Effect |
|---|---|---|
| `GRAPHIFY_TOKEN_GUARD` | on | `0` turns all hooks off |
| `GRAPHIFY_CONTEXT_BUDGET` | `200000` | first context level that triggers a notice; `0` disables |
| `GRAPHIFY_CONTEXT_BUDGET_STEP` | `100000` | spacing of further notices |
| `GRAPHIFY_BASH_CAP` | `20000` | character cap for Bash output; `0` disables |
| `GRAPHIFY_TOKEN_GUARD_DAILY` | on | `0` turns off the daily notice |
| `GRAPHIFY_TOKEN_GUARD_DIR` | `~/.cache/graphify/token-guard` | where state and saved outputs live |

## `graphify handoff`: leave a bloated session behind

Writes `graphify-out/HANDOFF.md`, a note of about 1,500 tokens built from the
session transcript, git state and the knowledge graph, with no LLM call. Start
a new session, have it read that file, and continue without carrying the old
context.

```bash
graphify handoff            # most recent session for this directory
graphify handoff --stdout
graphify handoff --session <id>
```

`--session` takes a full session id or a prefix of one. A prefix that matches
more than one session is an error: the matching ids are listed and nothing is
written.

The note contains your prompts (truncated, with secrets masked), file paths,
edit counts and a git summary. It contains no tool output and no file bodies.

## What this does not do

A model reads its whole context on every request; no tool removes that. These
commands keep the context smaller and tell you when to shrink it. Fixed
overhead from MCP servers, skills and instruction files is reported by
`graphify usage` but not reduced by the guard.
