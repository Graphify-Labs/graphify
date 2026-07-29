"""`graphify merge-chunks` — concatenate semantic subagent chunk files.

Moved verbatim from the merge-chunks branch of cli.dispatch_command as the
first step of the __main__/cli command split (issue #1212). See
graphify/commands/MIGRATION.md.
"""
from __future__ import annotations

import sys
from pathlib import Path


def merge_chunks() -> None:
    # graphify merge-chunks <chunk_glob_or_files...> --out <path>
    # Concatenates .graphify_chunk_*.json files written by semantic subagents.
    # Deduplicates nodes by id (first writer wins). Sums token counts.
    import glob as _glob
    if len(sys.argv) < 3:
        print("Usage: graphify merge-chunks <chunk_files...> --out <path>", file=sys.stderr)
        sys.exit(1)
    out_path: Path | None = None
    chunk_args: list[str] = []
    i = 2
    while i < len(sys.argv):
        if sys.argv[i] == "--out" and i + 1 < len(sys.argv):
            out_path = Path(sys.argv[i + 1])
            i += 2
        else:
            chunk_args.append(sys.argv[i])
            i += 1
    if not out_path:
        print("error: --out <path> required", file=sys.stderr)
        sys.exit(1)
    chunk_files: list[str] = []
    for arg in chunk_args:
        expanded = _glob.glob(arg)
        chunk_files.extend(sorted(expanded) if expanded else [arg])
    merged: dict = {"nodes": [], "edges": [], "hyperedges": [], "input_tokens": 0, "output_tokens": 0}
    seen_ids: set[str] = set()
    valid_chunks = 0
    # These chunk files are untrusted subagent output. load_validated_...
    # stats the file size BEFORE reading it (so a multi-GB chunk can't blow up
    # memory), parses the JSON, and validates the security caps + the node/
    # edge id charset that blocks path traversal (#825) — the same enforcement
    # the skill merge path applies. A bad chunk is skipped with a warning
    # while valid siblings still merge; if every chunk is invalid, fail
    # closed instead of reporting success and replacing --out with an empty
    # semantic layer. Deliberately NOT wired into
    # build_from_json/load_graph_json, which must keep loading valid
    # pre-existing graphs. file_type is left to build's coercion (#840).
    from graphify.semantic_cleanup import load_validated_semantic_fragment
    for cf in chunk_files:
        chunk, _chunk_errs = load_validated_semantic_fragment(Path(cf))
        if _chunk_errs:
            print(
                f"[graphify merge-chunks] warning: skipping invalid chunk {cf}: "
                f"{'; '.join(_chunk_errs[:3])}",
                file=sys.stderr,
            )
            continue
        valid_chunks += 1
        for n in chunk.get("nodes", []):
            if n.get("id") not in seen_ids:
                seen_ids.add(n["id"])
                merged["nodes"].append(n)
        merged["edges"].extend(chunk.get("edges", []))
        merged["hyperedges"].extend(chunk.get("hyperedges", []))
        # Coerce token counts: a chunk is untrusted, so a non-numeric
        # input_tokens/output_tokens must not abort the whole merge with a
        # TypeError after other chunks already merged.
        for _tok in ("input_tokens", "output_tokens"):
            _v = chunk.get(_tok, 0)
            merged[_tok] += _v if isinstance(_v, (int, float)) else 0
    if not valid_chunks:
        print(
            f"[graphify merge-chunks] error: no valid chunks to merge; "
            f"refusing to write {out_path}",
            file=sys.stderr,
        )
        sys.exit(1)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    from graphify.paths import write_json_atomic as _wja
    _wja(out_path, merged, ensure_ascii=False)
    chunk_summary = (
        f"{valid_chunks} chunks"
        if valid_chunks == len(chunk_files)
        else f"{valid_chunks} of {len(chunk_files)} chunks"
    )
    print(
        f"Merged {chunk_summary}: {len(merged['nodes'])} nodes, {len(merged['edges'])} edges, "
        f"{merged['input_tokens']:,} in / {merged['output_tokens']:,} out tokens"
    )
