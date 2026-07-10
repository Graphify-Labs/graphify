# graphify reference: evals, embeddings, history, skill health

Load this when the user wants to **measure retrieval quality**, enable **semantic
search**, **diff the graph across time**, or **check skill freshness**. None of
these run in a default build; each is an explicit command against an existing
`graphify-out/graph.json`. All are deterministic and API-free except `embed`,
which uses a local embedding model.

## Relevance evals — `graphify bench`

Measures whether `graphify query` returns the *right* nodes, against a fixture of
`{question -> expected nodes}` cases. Metrics: P@k, Recall@k, MRR, nDCG@k.

```bash
graphify bench --init          # scaffold graphify-out/evals.jsonl from prominent nodes
# edit the fixture: each line is {"query": "...", "expect": ["label_or_file", ...]}
graphify bench                 # run + print the metrics table
graphify bench --save          # append the run to .graphify-evals/eval-results.jsonl
graphify bench --replay        # diff metrics vs the last saved run; exit 1 on regression
```

An `expect` entry matches a result node by its label, id, or source file (full
path or basename). Use `--replay` in CI or a pre-commit hook to catch a change
that quietly degrades retrieval. `--k N` sets the rank cutoff (default 10);
`--json` emits machine-readable output; `--semantic` includes the embedding
backend in the ranking under test.

## Semantic search — `graphify embed`

Builds a one-time embedding sidecar next to `graph.json` so `graphify query
--semantic` can match on meaning, not just tokens. Local-only: uses Ollama
(`nomic-embed-text` by default) or `sentence-transformers` if installed — no API
key, no network beyond localhost.

```bash
graphify embed                 # build (or refresh) graphify-out/embeddings.npz
graphify embed --force         # rebuild even if the sidecar is current
graphify query "fuzzy question" --semantic   # now fuses cosine similarity into ranking
```

`--semantic` also **seeds** the traversal from the nearest embeddings when no
label matches the wording, which is how it answers questions whose vocabulary
appears nowhere in the graph. Set `GRAPHIFY_EMBED_BACKEND` (`ollama` |
`sentence-transformers`) and `GRAPHIFY_EMBED_MODEL` to override auto-detection.

## Structural history — `graphify chronicle`

Diffs two graph snapshots to show how the codebase's *structure* moved: nodes and
edges added/removed, god-nodes (high-degree hubs) that emerged or vanished, and
community shifts. Surfaces architectural drift a line diff can't.

```bash
graphify chronicle OLD.json NEW.json            # diff two snapshot files
graphify chronicle --rev HEAD~20                # vs the working-tree graph
graphify chronicle --rev v1.0 --rev2 v2.0       # commit vs commit
```

The `--rev` form reads snapshots straight from git history (`git show
REV:graphify-out/graph.json`) — cheap and API-free — so it needs the graph to be
committed. `--top-god N` sets the hub-ranking depth to compare (default 15);
`--json` emits the full diff.

## Skill freshness — `graphify skill check-update`

Reports whether the installed graphify skill (SKILL.md + references) matches the
running package, across every platform it's installed on, and names any migration
a re-install would apply.

```bash
graphify skill status          # human-readable per-platform report
graphify skill check-update    # same, but exit 1 when any skill has drifted (cron/CI)
```

When it flags drift, run `graphify install` to re-render the skill from the
current package. `--json` emits machine-readable output.
