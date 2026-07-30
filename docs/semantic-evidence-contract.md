# Semantic evidence contract

This contract applies to LLM-produced semantic fragments. Deterministic AST
extractors retain their language-specific relation labels and provenance rules.

## Relation vocabulary

Semantic edge `relation` values are closed:

- `calls`
- `implements`
- `references`
- `cites`
- `conceptually_related_to`
- `shares_data_with`
- `semantically_similar_to`
- `rationale_for`

Semantic hyperedge `relation` values are also closed:

- `participate_in`
- `implement`
- `form`

The semantic-fragment validator rejects a missing, null, malformed, or unknown
relation before any fragment in the batch is merged or persisted.

## Exact source provenance

Every semantic node, edge, and hyperedge must contain:

- `source_file`: the exact path key captured in the pre-dispatch source
  manifest;
- `source_location`: an exact span in that source; and
- after validation, `source_sha256`: the lowercase SHA-256 digest from the
  trusted pre-dispatch snapshot.

UTF-8 text uses one-based line spans:

- `L7` for one line;
- `L7-L12` for an inclusive multi-line span.

PDF and raster sources use zero-based, half-open byte spans:

- `B120-B384`.

The whole file is a valid exact span when a binary format provides no finer
stable mapping. It is represented explicitly as `B0-B<size>`; null or omitted
locations are never evidence.

Before semantic extraction starts, `graphify snapshot-sources` resolves every
semantic source beneath the corpus root, including cache hits and sources that
will be dispatched, and records its raw SHA-256 digest, addressing mode, and
extent. The parent retains the printed manifest SHA-256 seal; workers receive
neither that seal nor authority to replace the snapshot. Before merge, Graphify
verifies that seal, resolves and reads each source once, and prepares an
immutable validation session shared by every cached and new fragment. It reads
each source once more immediately before the atomic output replacement.
Validation fails closed if a path is missing, outside the root, no longer a
regular file, resolves differently, has changed content, or contains an invalid
or out-of-range span. Manifest and fragment readers enforce their byte cap on a
single open descriptor, source snapshots and rechecks stream their hash/extent
calculation, and output paths may not alias a manifested source.

For native extraction, provenance is also limited to the bytes shown to the
provider. Only complete original source lines wholly contained in a capped
whole-file prompt or `FileSlice` are citeable; a partial boundary line grants no
authority over its unseen prefix or suffix. Local slice line numbers are not
accepted as whole-file line numbers. A `FileSlice` of a byte-addressed source
grants no provenance authority because character slice offsets cannot identify
exact original byte offsets. Raster images are authorized only when their
pixels are attached to a vision request or exposed to the path-based vision
backend; unreadable, oversized, or non-vision image inputs are excluded rather
than treated as source-backed references.

## Merge boundary

The generated extraction skills write one JSON fragment per worker. They first
snapshot the complete semantic source set, merge new worker chunks, and then
validate cached and new fragments together:

```bash
graphify snapshot-sources .graphify_semantic_sources.txt \
  --root "$ROOT" \
  --out "$OUT/.graphify_source_manifest.json"
# Retain the printed digest as MANIFEST_SHA256 in the parent process/context.

graphify merge-chunks "$OUT"/.graphify_chunk_*.json \
  --source-manifest "$OUT/.graphify_source_manifest.json" \
  --manifest-sha256 MANIFEST_SHA256 \
  --out "$OUT/.graphify_semantic_new.json"

graphify merge-semantic \
  --cached "$OUT/.graphify_cached.json" \
  --new "$OUT/.graphify_semantic_new.json" \
  --source-manifest "$OUT/.graphify_source_manifest.json" \
  --manifest-sha256 MANIFEST_SHA256 \
  --out "$OUT/.graphify_semantic.json"
```

`merge-chunks` validates the complete batch before sanitizing, constructing, or
atomically writing its output. `merge-semantic` repeats that package-owned
acceptance step across cache hits and new records under the same sealed
all-source manifest. Worker fragments retain per-fragment record-count caps;
the bounded aggregate may exceed one worker's count and 25 MiB byte cap, but
the combined raw worker inputs and serialized output, and the combined raw
cached-plus-new inputs and serialized result, remain subject to a separate
50 MiB JSON byte cap. The rationale sanitizer runs only
after every input passes validation, and it folds rationale text into a target
only when the target's citation covers the supporting rationale and edge spans.
One invalid input or a source that changes before replacement rejects the batch
and preserves any existing output.

Native `graphify extract` applies the same validator to each provider response
before adaptive merge or cache checkpointing, derives cache keys from the same
bytes whose digest it validates, and rechecks accepted semantic sources before
final graph persistence.

## Compatibility

Semantic fragments produced by an older Graphify prompt may have open-ended
relation labels or null/missing source locations. They are not upgraded,
rewritten, or accepted as source evidence. Re-extract the affected sources with
a Graphify version that implements this contract. Semantic cache reads require
the current extraction-prompt fingerprint and never fall back to flat
unknown-vintage cache entries. A prompt-scoped entry whose bound
`source_sha256` no longer matches the current source is also a cache miss; older
installed skill flows that omit the prompt therefore re-extract instead of
replaying unqualified evidence.

The accepted `source_sha256` identifies the exact snapshot even if a source is
edited after extraction completes. A later qualification must compare the
current file to that digest; Graphify does not claim that a mutable source will
remain unchanged forever after output publication.
