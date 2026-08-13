# graphify bundle metadata (`metadata.json`)

When a `graphify --update` output is published for other machines/CI jobs to
pull (rather than generated locally), it ships as one atomic bundle:
`graph.json` + `GRAPH_REPORT.md` + `manifest.json` + a small `metadata.json`
describing the bundle itself.

`metadata.json` exists because the bundle has two independent consumers that
must never drift apart on what fields to expect:

- **Writer**: the CI job that runs `graphify --update` and publishes the
  bundle (e.g. a scheduled graph-refresh workflow).
- **Reader**: the fetch script that pulls the bundle down and validates it
  before swapping it into a local `graphify-out/`, ahead of graphify's own
  `CLAUDE.md` directive / `PreToolUse` hook consuming it.

Both of those typically live in consuming repos outside this one, but both are built
against graphify's own output format, so this repo is the natural single
source of truth for the contract between them -- one documented schema
instead of two independently-evolving assumptions.

**Schema**: [`graph-bundle-metadata.schema.json`](./graph-bundle-metadata.schema.json)
(JSON Schema, draft 2020-12).

## Example

```json
{
  "schema_version": 1,
  "source_sha": "e4bfd2ad1a9393251023a4edef93e93dc798afc7",
  "graphify_version": "0.9.41",
  "generated_at": "2026-08-13T02:00:00Z",
  "bundle": {
    "graph": "graph.json",
    "report": "GRAPH_REPORT.md",
    "manifest": "manifest.json"
  }
}
```

## What each field is for

- `source_sha` / `generated_at`: staleness. A consumer compares `source_sha`
  against its local `HEAD` (ancestry check, not a race guard -- the bundle's
  own publish path is already serialized by a CI `concurrency:` group); when
  that comparison isn't possible, `generated_at` backs a TTL fallback.
- `graphify_version`: a hard compatibility gate. A version mismatch against
  the locally-installed `graphify --version` means the fetch script refuses
  to load the bundle and prints the exact upgrade command, rather than
  risking a schema-mismatched `graph.json` being consulted silently.
- `bundle`: where the other three files live inside the archive, so the
  reader doesn't hardcode filenames independently of what the writer chose.

`manifest.json` rides along for the *writer's* own benefit (restoring
incremental-extraction continuity across ephemeral CI runners between
scheduled runs) -- ordinary consumers only need `graph.json` and
`GRAPH_REPORT.md`.
