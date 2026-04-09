---
name: graphify-enrich
description: Enrich corpus INDEX.md files from a graphify knowledge graph — Claude Code generates folder summaries using its own model (no ANTHROPIC_API_KEY needed)
trigger: /graphify-enrich
---

# graphify-enrich skill

Enrich INDEX.md files for a corpus using the graphify knowledge graph.
Claude Code generates folder summaries; graphify CLI handles all structural work.

## Usage

```
/graphify-enrich <corpus_path> [--index-dir <dir>] [--master-only] [--dry-run]
```

**Arguments:**
- `corpus_path` — path to the corpus root (must contain `graphify-out/graph.json`)
- `--index-dir <dir>` — write INDEX.md files here instead of into the corpus (recommended for keeping corpus clean)
- `--master-only` — write root INDEX.md only, skip per-folder files
- `--dry-run` — preview without writing files

## Prerequisites

`graphify-out/graph.json` must exist. If it does not:
```bash
graphify <corpus_path>
```
Run the full graphify pipeline first, then come back to this skill.

## Workflow

### Step 1 — Structural pass (graphify CLI)

Run:
```bash
graphify enrich <corpus_path> [--index-dir <dir>] [--master-only] [--dry-run]
```

This writes INDEX.md files containing:
- YAML frontmatter (folder, entities, last_enriched)
- Documents list
- Key entities list
- Connected folders (cross-references)
- Summary section with plain entity-list fallback

### Step 2 — Read the knowledge graph

Read `<corpus_path>/graphify-out/graph.json`. Structure:
```json
{
  "nodes": [{"id": "...", "label": "...", "source_file": "...", "file_type": "...", "community": 0}],
  "links": [{"source": "...", "target": "...", "relation": "...", "confidence": "..."}]
}
```

Group nodes by `parent folder` of their `source_file` path, relative to `corpus_path`.
Exclude any node whose `source_file` contains `graphify-out`.

### Step 3 — Generate folder summaries

For each folder group, write a 2-3 sentence plain-English summary:
- What kinds of files/entities live here
- What purpose this folder serves in the corpus
- Any notable cross-folder relationships visible from the edges

Rules:
- Be specific and factual
- No bullet points
- No hedging phrases ("appears to contain", "seems to be")
- Use the entity labels and relation types from the graph as evidence

### Step 4 — Patch Summary sections in INDEX.md files

For each INDEX.md written in Step 1, patch the summary:

**Case A — file has `## What's here` section:**
Replace the body of that section with the generated summary.
Preserve the heading line. Replace everything until the next `##` heading.

**Case B — file has `## Summary` section:**
Same as Case A — replace body, preserve heading.

**Case C — neither section exists:**
Insert after the closing `---` of the YAML frontmatter:
```
## What's here

<generated summary>

```

Do NOT touch any other section: Key Entities, Documents, Connected Folders,
Key Files, Subfolders, Cross-References, Open Items, Type, Owner, Status.

### Step 5 — Update master INDEX.md

Read `<index-dir>/INDEX.md` (or `<corpus_path>/INDEX.md` if no --index-dir).
In the `## Folder map` table, the `What's there` column may be empty or contain
a plain entity list. Replace each cell with the one-sentence version of the
folder summary (first sentence only, truncated to ~100 chars if needed).

### Step 6 — Commit

```bash
git add <index-dir or corpus_path>
git commit -m "enrich: update INDEX.md summaries via Claude Code"
```

## Notes

- If a folder has no INDEX.md (e.g. --master-only was used), skip it silently
- If graph.json has no nodes for a folder that has an INDEX.md, leave the Summary as-is
- The graphify CLI step (Step 1) is always required even on re-runs — it updates entities and cross-refs
