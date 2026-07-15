# RFC: file-level node summaries

This RFC proposes an optional way for graphify to expose compact file-level
summaries for AI coding agents.

## Problem

`graph.json` gives agents graph structure, source files, node labels, and
relationships. That helps avoid reading an entire repository, but agents still
often need to inspect raw files just to answer a basic navigation question:

> What is this file or node responsible for?

A short summary near the graph node could reduce repeated file reads during
`graphify query`, `graphify explain`, MCP node lookup, and graph navigation.

## Goals

- Help agents choose relevant files with less context.
- Preserve graphify's offline, deterministic behavior by default.
- Keep the first implementation small and reviewable.
- Avoid adding long prose to `GRAPH_REPORT.md`.
- Leave room for a future opt-in LLM-generated summary backend.

## Non-goals

- Summarizing every function, method, or local symbol in the first version.
- Calling an LLM or remote API by default.
- Replacing `graphify explain`; summaries should make `explain` more useful.
- Turning `GRAPH_REPORT.md` into a full per-file index.

## Shared constraints for either option

- Start with file-level nodes only.
- Keep each summary bounded, for example one sentence or roughly 200-300
  characters.
- Generate deterministic summaries first from existing local signal:
  module docstrings, top comments, exported symbols, imports, relation counts,
  and community/context data.
- Do not emit summaries by default until the storage model is agreed on.
- Display a summary in `graphify explain <node>` when one exists.
- Include summaries in `graphify serve` / MCP node lookup when one exists.

## Proposed summary contents

Each file-level summary should give an agent enough signal to decide whether to
inspect the file, without replacing the file or bloating graph output.

Recommended fields:

| Field | Why it helps agents |
| --- | --- |
| `summary` | One bounded sentence describing the file's responsibility. This is the main token-saving field. |
| `source_file` | Lets the agent jump to the right file without resolving a node ID manually. |
| `label` | Keeps the summary readable in CLI, MCP, and UI contexts. |
| `generated_by` | Distinguishes deterministic summaries from future LLM-generated summaries. |
| `summary_version` | Allows the format to evolve without guessing how an older summary was produced. |

Recommended signal inside the `summary` sentence:

| Signal | Why it belongs in the sentence |
| --- | --- |
| Module docstring or top comment | Usually the highest-quality human-authored purpose statement. |
| Exported classes/functions/symbols | Tells the agent what API surface the file provides. |
| Important imports or dependencies | Reveals whether the file belongs to auth, database, UI, CLI, test, etc. |
| Dominant graph relations | Shows whether the file mainly calls, imports, defines, contains, or references other nodes. |
| Community or nearby hub label | Gives architectural context without reading the whole community report. |
| Source location coverage when available | Helps distinguish a file-level summary from a symbol-level explanation. |

Example:

```json
{
  "label": "extract.py",
  "source_file": "graphify/extract.py",
  "summary": "Extracts source files into graph nodes and relationships; defines language parsers and import/call extraction helpers.",
  "generated_by": "deterministic",
  "summary_version": 1
}
```

The summary should not include long call chains, full dependency lists, raw code,
or every symbol in the file. Those details already belong in the graph and can
be fetched through `graphify explain`, `graphify query`, or direct file reads
when needed.

## Option A: `summary` attribute in `graph.json`

Add an optional `summary` field to file-level nodes:

```json
{
  "id": "graphify_extract",
  "label": "extract.py",
  "file_type": "code",
  "source_file": "graphify/extract.py",
  "summary": "Extracts source files into graph nodes and relationships using language-specific parsers."
}
```

Possible user flow:

```bash
graphify . --summarize-nodes
graphify explain "extract.py"
```

Pros:

- Single artifact for graph consumers.
- Matches NetworkX node attributes and existing node metadata.
- Easy for `explain`, `serve`, visualizers, and MCP tools to consume.
- No sidecar freshness or node-ID join logic.

Cons:

- Adds text to the core graph artifact.
- Expands the graph schema surface.
- Consumers that dump all of `graph.json` into an LLM context would pay for all
  summaries at once.

## Option B: sidecar `node-summaries.json`

Write summaries to a separate artifact keyed by node ID:

```json
{
  "version": 1,
  "generator": "deterministic",
  "nodes": {
    "graphify_extract": {
      "label": "extract.py",
      "source_file": "graphify/extract.py",
      "summary": "Extracts source files into graph nodes and relationships using language-specific parsers."
    }
  }
}
```

Possible user flow:

```bash
graphify summarize
graphify explain "extract.py"
```

Pros:

- Keeps `graph.json` lean and topology-focused.
- Makes summaries clearly optional.
- Can be regenerated independently.
- Provides a natural place for future generator metadata.

Cons:

- Adds a second artifact that consumers must discover and load.
- Introduces freshness and synchronization questions.
- Every consumer that wants summaries must join by node ID.

## Suggested first implementation once storage is chosen

1. Add deterministic file-level summary generation.
2. Store summaries using the selected option.
3. Surface summaries in `graphify explain`.
4. Surface summaries in `graphify serve` / MCP node lookup.
5. Add tests for default behavior, generated summaries, missing summaries, and
   bounded summary length.

## Follow-up ideas

- Add opt-in LLM-generated summaries with explicit provider/backend selection.
- Extend summaries to class or module-level nodes if file-level summaries prove
  useful.
- Allow `graphify query` to include summaries for returned nodes under a budget.
- Add cache/freshness metadata if summaries are generated separately from the
  main graph.

## Questions for maintainers and users

1. Should graphify prefer one artifact (`graph.json`) or keep generated text in a
   sidecar?
2. Should deterministic file-level summaries be generated during graph creation,
   or only through an explicit command such as `graphify summarize`?
3. Is `summary` the right term, or would `synopsis` better communicate a short,
   bounded description?
4. What summary length budget would be acceptable for large repositories?
