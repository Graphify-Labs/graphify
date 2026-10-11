"""Pipeline steps as importable functions, so the CLI can run them without the
skill shipping inline Python (#197).

The agent skill used to carry each pipeline step as a ``python -c "..."`` block
inside a bash string. That delivery mechanism is what triggers Claude Code's
``command_substitution`` and "newline followed by #" approval prompts, once per
step, and it forces the skill to resolve an interpreter path through
``$(cat graphify-out/.graphify_python)``. Exposing the same steps as subcommands
lets the skill issue plain ``graphify pipeline <step> <args>`` calls: no inline
script, no command substitution, and ``Bash(graphify *)`` becomes an allowlistable
prefix.

Each function is a transcription of the block it replaces — the same calls, the
same order, the same sidecar paths — so a run produces the same graph.json it did
before. The logic still lives in ``graphify.detect`` / ``extract`` / ``cache`` /
``build`` / ``cluster`` / ``analyze`` / ``report`` / ``export`` / ``diagnostics``;
the one intentional hardening is that ``step_merge_chunks`` routes subagent output
through the same size/id validation as ``graphify merge-chunks`` (#825) rather than
trusting it verbatim as the old block did.

Two paths matter and they are deliberately separate:

``scan_path``
    the corpus being indexed. Passed to ``detect``, and used as the ``root`` that
    relativises node source_file keys and manifest keys, so the build and a later
    ``--update`` share a base (#1361, #1417).

``out``
    where the per-run sidecars live — ``<out>/graphify-out/``. Defaults to the
    current working directory, which is where the skill's own bash blocks wrote
    them (``graphify-out/.graphify_detect.json`` relative to cwd), and is where
    Part C globs (#1392).
"""

from __future__ import annotations

import glob as _glob
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from graphify.paths import write_json_atomic

from graphify.paths import GRAPHIFY_OUT as _GRAPHIFY_OUT

_DETECT_JSON = ".graphify_detect.json"
_AST_JSON = ".graphify_ast.json"
_SEMANTIC_JSON = ".graphify_semantic.json"
_SEMANTIC_NEW_JSON = ".graphify_semantic_new.json"
_CACHED_JSON = ".graphify_cached.json"
_UNCACHED_TXT = ".graphify_uncached.txt"
_ANALYSIS_JSON = ".graphify_analysis.json"
_EXTRACT_JSON = ".graphify_extract.json"

def _empty_semantic() -> dict[str, Any]:
    """A fresh empty semantic payload. Returns new lists each call — callers may
    mutate the result, so the lists must not be shared module state."""
    return {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "input_tokens": 0,
        "output_tokens": 0,
    }


class PipelineError(RuntimeError):
    """A pipeline step refused to run.

    Raised instead of ``sys.exit`` so the CLI can print one clean error line and
    so library callers get a catchable exception. The skill treats every one of
    these as "stop and report to the user", never "continue with a partial graph".
    """


def _out_dir(out: Path | str | None) -> Path:
    """The pipeline output directory (``<out>/graphify-out/`` by default).

    Honors the ``GRAPHIFY_OUT`` env override the rest of the CLI uses (#686): an
    absolute value wins outright, a bare name is joined under ``out`` (or the cwd).
    Mirrors ``cli``'s ``out_root / _GRAPHIFY_OUT``.
    """
    go = Path(_GRAPHIFY_OUT)
    if go.is_absolute():
        return go
    base = Path(out) if out is not None else Path(".")
    return base / go


def _read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def _load(path: Path, what: str) -> dict:
    data = _read_json(path)
    if data is None:
        raise PipelineError(
            f"{what} missing: {path} was not found. "
            "Run the preceding pipeline step first."
        )
    return data


def _scan(scan_path: Path | str | None) -> Path:
    """The corpus root, defaulting to cwd when a step doesn't need one."""
    return Path(scan_path) if scan_path is not None else Path(".")


# --------------------------------------------------------------------------
# Step 2 - detect
# --------------------------------------------------------------------------


def _persisted_corpus_shaping(
    out_dir: Path, gitignore: bool | None, exclude: list[str] | None
) -> tuple[bool, list[str] | None]:
    """Fill in the corpus-shaping options a rebuild should reuse.

    An explicit flag wins; otherwise reuse what a prior build persisted for this
    graph (``graphify-out/.graphify_build.json``), matching the skill's own detect
    step. ``gitignore`` defaults to True and ``exclude`` to [] when nothing is
    persisted, so a first run is unchanged.
    """
    from graphify.watch import _read_build_excludes, _read_build_gitignore

    if exclude is None:
        exclude = _read_build_excludes(out_dir) or None
    if gitignore is None:
        gitignore = _read_build_gitignore(out_dir)
    return gitignore, exclude


def step_detect(
    path: str | Path,
    *,
    out: Path | str | None = None,
    gitignore: bool | None = None,
    google_workspace: bool = False,
    exclude: list[str] | None = None,
) -> dict:
    """Scan ``path`` and write ``<out>/graphify-out/.graphify_detect.json``.

    Returns the detection dict so a caller can print the corpus summary without
    re-reading the sidecar. ``gitignore``/``exclude`` default to the values
    persisted for this graph by a prior build (see :func:`_persisted_corpus_shaping`).
    """
    from graphify.detect import detect

    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    gitignore, exclude = _persisted_corpus_shaping(out_dir, gitignore, exclude)

    # cache_root is the directory that CONTAINS graphify-out, not graphify-out
    # itself: detect() appends the output dir to it (detect.py:2065) and the stat
    # cache lives at `<cache_root>/graphify-out/cache/stat-index.json`
    # (cache.py::_stat_index_file). Passing `out_dir` here would nest a second
    # graphify-out. None (the default) matches the old skill's `detect(INPUT_PATH)`,
    # which let detect anchor the cache at the scan root.
    cache_root = Path(out) if out is not None else None

    result = detect(
        Path(path),
        gitignore=gitignore,
        google_workspace=google_workspace or None,
        extra_excludes=exclude or None,
        cache_root=cache_root,
    )
    # Written with write_json_atomic, not a shell redirect, so the same call
    # renders on PowerShell hosts without console-encoding drift (#2528).
    write_json_atomic(out_dir / _DETECT_JSON, result, ensure_ascii=False)
    return result


# --------------------------------------------------------------------------
# Part A - AST extraction for code files
# --------------------------------------------------------------------------


def step_extract_ast(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
) -> dict:
    """Run AST extraction over the code files ``step_detect`` found.

    Reads ``.graphify_detect.json``, writes ``.graphify_ast.json``. A code-only
    corpus still gets a well-formed empty sidecar so Part C's merge has its input.
    """
    from graphify.extract import collect_files, extract

    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    detect_result = _load(out_dir / _DETECT_JSON, "detection sidecar")

    code_files: list[Path] = []
    for f in detect_result.get("files", {}).get("code", []):
        fp = Path(f)
        code_files.extend(collect_files(fp) if fp.is_dir() else [fp])

    if code_files:
        result = extract(code_files, cache_root=_scan(path))
    else:
        result = {"nodes": [], "edges": [], "input_tokens": 0, "output_tokens": 0}

    write_json_atomic(out_dir / _AST_JSON, result, indent=2, ensure_ascii=False)
    return result


# --------------------------------------------------------------------------
# Part B, fast path - empty semantic sidecar
# --------------------------------------------------------------------------


def step_empty_semantic(*, out: Path | str | None = None) -> dict:
    """Write an empty ``.graphify_semantic.json``.

    Part C reads that file unconditionally, so a code-only corpus (no docs,
    papers or images, therefore no semantic subagents) needs it to exist.
    """
    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(out_dir / _SEMANTIC_JSON, _empty_semantic(), ensure_ascii=False)
    return _empty_semantic()


# --------------------------------------------------------------------------
# Part B, step B0 - cache check
# --------------------------------------------------------------------------


def step_cache_check(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    prompt_file: str | Path | None = None,
    mode: str | None = None,
) -> dict:
    """Decide which detected content files still need semantic extraction.

    Writes ``.graphify_cached.json`` (hits) and ``.graphify_uncached.txt`` (misses).
    Only documents, papers and images are checked: code is already covered
    structurally by the AST pass, and flattening every category here would make
    subagents re-read every source file (#1392). Video is transcribed to a
    document in Step 2.5 before it gets here.

    On a full cache hit the ``.graphify_cached.json`` sidecar is *deleted* rather
    than left stale, so the later merge can never pick up a prior run's leftovers
    (#1392). Leftover chunk files from an interrupted run are cleared too, since
    nothing has been dispatched yet at this point.
    """
    from graphify.cache import check_semantic_cache

    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    detect_result = _load(out_dir / _DETECT_JSON, "detection sidecar")

    all_files = [
        f
        for cat in ("document", "paper", "image")
        for f in detect_result["files"].get(cat, [])
    ]

    cached_nodes, cached_edges, cached_hyperedges, uncached = check_semantic_cache(
        all_files, root=_scan(path), mode=mode, prompt_file=prompt_file
    )

    cached_path = out_dir / _CACHED_JSON
    if cached_nodes or cached_edges or cached_hyperedges:
        write_json_atomic(
            cached_path,
            {"nodes": cached_nodes, "edges": cached_edges, "hyperedges": cached_hyperedges},
            ensure_ascii=False,
        )
    elif cached_path.exists():
        cached_path.unlink()

    (out_dir / _UNCACHED_TXT).write_text("\n".join(uncached), encoding="utf-8")
    for stale in out_dir.glob(".graphify_chunk_*.json"):
        stale.unlink()

    return {"checked": len(all_files), "hits": len(all_files) - len(uncached), "misses": len(uncached)}


# --------------------------------------------------------------------------
# Part B - collect subagent chunks
# --------------------------------------------------------------------------


def step_merge_chunks(
    *,
    out: Path | str | None = None,
    pattern: str = ".graphify_chunk_*.json",
) -> dict:
    """Merge ``.graphify_chunk_NN.json`` into ``.graphify_semantic_new.json``.

    Uses ``graphify.semantic_cleanup``'s validated loader, the same path
    ``graphify merge-chunks`` takes, so untrusted subagent output is size-capped
    and id-validated before it reaches the graph (#825).
    """
    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)

    chunks = sorted(_glob.glob(str(out_dir / pattern)))
    if not chunks:
        # The all-cached path reaches B3 with nothing to merge, and B3's merge is
        # the only step that writes .graphify_semantic.json — Part C reads it
        # unconditionally. So zero chunks is a valid empty merge, not an error:
        # write the empty sidecar and let save-cache/merge-semantic run (#1392).
        empty = _empty_semantic()
        write_json_atomic(out_dir / _SEMANTIC_NEW_JSON, empty, indent=2, ensure_ascii=False)
        return empty

    from graphify.semantic_cleanup import load_validated_semantic_fragment

    merged: dict[str, Any] = {
        "nodes": [], "edges": [], "hyperedges": [],
        "input_tokens": 0, "output_tokens": 0,
    }
    seen: set[str] = set()
    valid = 0
    for cf in chunks:
        chunk, errs = load_validated_semantic_fragment(Path(cf))
        if errs:
            print(
                f"[graphify pipeline merge-chunks] warning: skipping invalid chunk {cf}: "
                f"{'; '.join(errs[:3])}"
            )
            continue
        valid += 1
        for n in chunk.get("nodes", []):
            if n.get("id") not in seen:
                seen.add(n["id"])
                merged["nodes"].append(n)
        merged["edges"].extend(chunk.get("edges", []))
        merged["hyperedges"].extend(chunk.get("hyperedges", []))
        # A chunk is untrusted, so a non-numeric token count must not abort the
        # merge with a TypeError after sibling chunks already merged.
        for tok in ("input_tokens", "output_tokens"):
            v = chunk.get(tok, 0)
            merged[tok] += v if isinstance(v, (int, float)) else 0

    if not valid:
        raise PipelineError(
            f"no valid chunks to merge; refusing to write {out_dir / _SEMANTIC_NEW_JSON}"
        )

    write_json_atomic(out_dir / _SEMANTIC_NEW_JSON, merged, indent=2, ensure_ascii=False)
    return merged


# --------------------------------------------------------------------------
# Part B - cache write, then cached + new merge
# --------------------------------------------------------------------------


def step_save_cache(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    prompt_file: str | Path | None = None,
    mode: str | None = None,
) -> int:
    """Stamp this run's semantic output into the cache.

    ``prompt_file`` must be the same extraction prompt Step B0 passed, so an entry
    is attributed to the prompt that produced it and a run under a changed prompt
    re-extracts instead of replaying stale results (#1939).
    """
    from graphify.cache import save_semantic_cache

    out_dir = _out_dir(out)
    new = _read_json(out_dir / _SEMANTIC_NEW_JSON) or {"nodes": [], "edges": [], "hyperedges": []}
    uncached_path = out_dir / _UNCACHED_TXT
    uncached = []
    if uncached_path.exists():
        uncached = [ln for ln in uncached_path.read_text(encoding="utf-8").splitlines() if ln]

    return save_semantic_cache(
        new.get("nodes", []),
        new.get("edges", []),
        new.get("hyperedges", []),
        root=_scan(path),
        allowed_source_files=uncached,
        prompt_file=prompt_file,
        mode=mode,
    )


def step_merge_semantic(*, out: Path | str | None = None) -> dict:
    """Merge cached + newly-extracted results into ``.graphify_semantic.json``."""
    out_dir = _out_dir(out)
    cached = _read_json(out_dir / _CACHED_JSON) or {"nodes": [], "edges": [], "hyperedges": []}
    new = _read_json(out_dir / _SEMANTIC_NEW_JSON) or {"nodes": [], "edges": [], "hyperedges": []}

    seen: set[str] = set()
    nodes: list[dict] = []
    for n in cached.get("nodes", []) + new.get("nodes", []):
        if n.get("id") not in seen:
            seen.add(n["id"])
            nodes.append(n)

    merged = {
        "nodes": nodes,
        "edges": cached.get("edges", []) + new.get("edges", []),
        "hyperedges": cached.get("hyperedges", []) + new.get("hyperedges", []),
        "input_tokens": new.get("input_tokens", 0),
        "output_tokens": new.get("output_tokens", 0),
    }
    write_json_atomic(out_dir / _SEMANTIC_JSON, merged, indent=2, ensure_ascii=False)
    return merged


# --------------------------------------------------------------------------
# Part C - merge AST + semantic
# --------------------------------------------------------------------------


def step_merge_extraction(*, out: Path | str | None = None) -> dict:
    """Merge ``.graphify_ast.json`` + ``.graphify_semantic.json`` -> ``.graphify_extract.json``."""
    out_dir = _out_dir(out)
    ast = _load(out_dir / _AST_JSON, "AST sidecar")
    sem = _load(out_dir / _SEMANTIC_JSON, "semantic sidecar")

    seen = {n["id"] for n in ast["nodes"]}
    merged_nodes = list(ast["nodes"])
    for n in sem["nodes"]:
        if n["id"] not in seen:
            merged_nodes.append(n)
            seen.add(n["id"])

    merged = {
        "nodes": merged_nodes,
        "edges": ast["edges"] + sem["edges"],
        "hyperedges": sem.get("hyperedges", []),
        "input_tokens": sem.get("input_tokens", 0),
        "output_tokens": sem.get("output_tokens", 0),
    }
    write_json_atomic(out_dir / _EXTRACT_JSON, merged, indent=2, ensure_ascii=False)
    return merged


# --------------------------------------------------------------------------
# Step 4 - build, cluster, analyze, report
# --------------------------------------------------------------------------


def step_build(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    directed: bool = False,
    force: bool = False,
) -> dict:
    """Build the graph, cluster it, analyze it, and write the outputs.

    Writes ``graph.json``, ``GRAPH_REPORT.md`` and ``.graphify_analysis.json``.
    Raises :class:`PipelineError` on an empty graph or a refused shrink — both are
    cases where writing the report would describe a graph ``graph.json`` does not
    contain (#479, #1392).
    """
    from graphify.analyze import god_nodes, surprising_connections, suggest_questions
    from graphify.build import build_from_json
    from graphify.cluster import cluster, score_all
    from graphify.export import to_json
    from graphify.report import generate

    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    scan = _scan(path)

    extraction = _load(out_dir / _EXTRACT_JSON, "merged extraction")
    detection = _load(out_dir / _DETECT_JSON, "detection sidecar")

    # root= mirrors the --update runbook (#1361): relativize source_file to the
    # same base so a full build and an incremental --update never drift apart.
    G = build_from_json(extraction, root=str(scan), directed=directed)
    # Guard BEFORE any write: an empty extraction must not clobber a good
    # graph.json / GRAPH_REPORT.md / analysis sidecar.
    if G.number_of_nodes() == 0:
        raise PipelineError(
            "graph is empty - extraction produced no nodes. Possible causes: "
            "all files were skipped, a binary-only corpus, or extraction failed."
        )

    communities = cluster(G)
    cohesion = score_all(G, communities)
    tokens = {
        "input": extraction.get("input_tokens", 0),
        "output": extraction.get("output_tokens", 0),
    }
    gods = god_nodes(G)
    surprises = surprising_connections(G, communities)
    labels = {cid: "Community " + str(cid) for cid in communities}
    questions = suggest_questions(G, communities, labels)

    # Export FIRST and honour the #479 shrink-guard: to_json returns False
    # (writing nothing) when the new graph is smaller than the existing graph.json.
    # Only write the report and sidecar when the graph was actually written, so
    # they never describe a graph graph.json doesn't contain (#1392).
    wrote = to_json(G, communities, str(out_dir / "graph.json"), force=force)
    if not wrote:
        raise PipelineError(
            "refused to shrink graphify-out/graph.json (the existing graph has more "
            "nodes; #479). If the shrink is intentional (you deleted files), re-run "
            "a full build with --force."
        )

    report = generate(
        G, communities, cohesion, labels, gods, surprises,
        detection, tokens, str(scan), suggested_questions=questions,
    )
    (out_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")

    analysis = {
        "communities": {str(k): v for k, v in communities.items()},
        "cohesion": {str(k): v for k, v in cohesion.items()},
        "gods": gods,
        "surprises": surprises,
        "questions": questions,
    }
    write_json_atomic(out_dir / _ANALYSIS_JSON, analysis, indent=2, ensure_ascii=False)

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "communities": len(communities),
    }


# --------------------------------------------------------------------------
# Step 4.5 - graph health check
# --------------------------------------------------------------------------


def step_diagnose(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    directed: bool = False,
) -> dict:
    """Run the read-only integrity gate over the merged extraction.

    Never raises on a damaged graph — the caller surfaces the warning and the graph
    stays usable, per the skill's Honesty Rules.
    """
    from graphify.diagnostics import diagnose_extraction

    extraction = _load(_out_dir(out) / _EXTRACT_JSON, "merged extraction")
    return diagnose_extraction(extraction, directed=directed, root=str(_scan(path)))


# --------------------------------------------------------------------------
# Step 5 - apply curated community labels
# --------------------------------------------------------------------------


def step_label(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    labels: dict[int | str, str],
    directed: bool = False,
    force: bool = False,
) -> dict:
    """Regenerate the report and ``graph.json`` with curated community labels.

    ``labels`` maps a community id to its 2-5 word name. Labels affect question
    phrasing, so the questions are regenerated too (#2490).
    """
    from graphify.analyze import suggest_questions
    from graphify.build import build_from_json
    from graphify.export import to_json
    from graphify.report import generate

    out_dir = _out_dir(out)
    scan = _scan(path)

    extraction = _load(out_dir / _EXTRACT_JSON, "merged extraction")
    detection = _load(out_dir / _DETECT_JSON, "detection sidecar")
    analysis = _load(out_dir / _ANALYSIS_JSON, "analysis sidecar")

    G = build_from_json(extraction, root=str(scan), directed=directed)
    communities = {int(k): v for k, v in analysis["communities"].items()}
    cohesion = {int(k): v for k, v in analysis["cohesion"].items()}
    tokens = {
        "input": extraction.get("input_tokens", 0),
        "output": extraction.get("output_tokens", 0),
    }
    int_labels = {int(k): v for k, v in labels.items()}

    questions = suggest_questions(G, communities, int_labels)
    report = generate(
        G, communities, cohesion, int_labels,
        analysis["gods"], analysis["surprises"],
        detection, tokens, str(scan), suggested_questions=questions,
    )
    (out_dir / "GRAPH_REPORT.md").write_text(report, encoding="utf-8")
    write_json_atomic(
        out_dir / ".graphify_labels.json",
        {str(k): v for k, v in int_labels.items()},
        ensure_ascii=False,
    )
    # Re-export so graph.json nodes carry the curated community_name (#2490). Same
    # extraction as step_build, so the #479 shrink-guard passes on node count; if it
    # still refuses, report the guard rather than forcing past it.
    wrote = to_json(G, communities, str(out_dir / "graph.json"),
                    community_labels=int_labels, force=force)
    if not wrote:
        raise PipelineError(
            "refused to shrink graphify-out/graph.json (the existing graph has more "
            "nodes; #479). If the shrink is intentional (you deleted files), re-run "
            "a full build with --force."
        )
    return {"labels": len(int_labels)}


# --------------------------------------------------------------------------
# Step 9 - save manifest, update the cost tracker
# --------------------------------------------------------------------------


def step_save_manifest(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    kind: str = "both",
) -> dict:
    """Stamp the manifest for ``--update`` and append to the cost tracker.

    Only semantic files that actually produced output get stamped: a doc whose
    chunk failed must stay unstamped so the next ``--update`` re-queues it instead
    of marking it done and losing its content forever (#2015). Files dispatched this
    run but not stamped carry a stale ``semantic_hash``, cleared so
    ``detect_incremental`` re-queues them (#1948).
    """
    from graphify.cli import _stamped_manifest_files
    from graphify.detect import save_manifest

    out_dir = _out_dir(out)
    scan = _scan(path)

    detect_result = _load(out_dir / _DETECT_JSON, "detection sidecar")
    extract_result = _load(out_dir / _EXTRACT_JSON, "merged extraction")

    # In --update mode 'all_files' carries the full corpus and 'files' the changed
    # subset; a full rebuild populates only 'files', so the fallback covers both.
    corpus = detect_result.get("all_files") or detect_result["files"]
    manifest_files = _stamped_manifest_files(corpus, extract_result, scan)

    semantic_types = ("document", "paper", "image")
    dispatched = {
        f for t, fl in detect_result["files"].items() if t in semantic_types for f in fl
    }
    stamped = {f for fl in manifest_files.values() for f in fl}
    cleared = dispatched - stamped
    # scan_corpus is the RAW full corpus (not the stamp-filtered subset) so in-root
    # files newly excluded since the last run are dropped rather than masquerading
    # as deletions; untouched files' prior rows are preserved (#1908).
    scan_corpus = {f for fl in corpus.values() for f in fl}

    save_manifest(
        manifest_files,
        manifest_path=str(out_dir / "manifest.json"),
        kind=kind,
        root=scan,
        scan_corpus=scan_corpus,
        clear_semantic=cleared or None,
    )

    input_tok = extract_result.get("input_tokens", 0)
    output_tok = extract_result.get("output_tokens", 0)

    cost_path = out_dir / "cost.json"
    cost = _read_json(cost_path) or {
        "runs": [], "total_input_tokens": 0, "total_output_tokens": 0,
    }
    cost["runs"].append({
        "date": datetime.now(timezone.utc).isoformat(),
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "files": detect_result.get("total_files", 0),
    })
    cost["total_input_tokens"] += input_tok
    cost["total_output_tokens"] += output_tok
    write_json_atomic(cost_path, cost, indent=2, ensure_ascii=False)

    return {
        "input_tokens": input_tok,
        "output_tokens": output_tok,
        "runs": len(cost["runs"]),
        "total_input_tokens": cost["total_input_tokens"],
        "total_output_tokens": cost["total_output_tokens"],
    }


# --------------------------------------------------------------------------
# query reference - vocabulary extraction
# --------------------------------------------------------------------------


def step_vocab(*, out: Path | str | None = None) -> dict:
    """Extract the graph's token vocabulary into ``.vocab.txt``.

    The query CLI matches on case-folded substrings with no stemming or synonyms,
    so a question phrased in different vocabulary than the graph's labels returns
    nothing. The reference reads this file and picks real tokens from it before
    traversing, so expansion can never invent a token the graph lacks.
    """
    import re

    out_dir = _out_dir(out)
    graph_path = out_dir / "graph.json"
    data = _load(graph_path, "graph")
    vocab: set[str] = set()
    for n in data.get("nodes", []):
        for c in re.findall(r"[^\W\d_]+", n.get("label", "") or "", re.UNICODE):
            parts = re.findall(r"[A-Z]+(?=[A-Z][a-z])|[A-Z]?[a-z]+|[A-Z]+", c) or [c]
            for p in parts:
                t = p.lower()
                if 3 <= len(t) <= 30:
                    vocab.add(t)
    (out_dir / ".vocab.txt").write_text("\n".join(sorted(vocab)), encoding="utf-8")
    return {"tokens": len(vocab)}


# --------------------------------------------------------------------------
# transcribe reference - video/audio to text
# --------------------------------------------------------------------------


def step_transcribe(*, out: Path | str | None = None) -> dict:
    """Transcribe the detected video/audio files into ``.graphify_transcripts.json``.

    Reads ``GRAPHIFY_WHISPER_PROMPT`` / ``GRAPHIFY_WHISPER_MODEL`` from the
    environment (the reference exports them). The JSON is written from Python, not
    a shell redirect, because Whisper prints progress to stdout which would
    otherwise corrupt the file (#1392).
    """
    import os

    from graphify.transcribe import transcribe_all

    out_dir = _out_dir(out)
    detect = _load(out_dir / _DETECT_JSON, "detection sidecar")
    video_files = detect.get("files", {}).get("video", [])
    prompt = os.environ.get(
        "GRAPHIFY_WHISPER_PROMPT", "Use proper punctuation and paragraph breaks."
    )
    transcript_paths = transcribe_all(video_files, initial_prompt=prompt)
    write_json_atomic(out_dir / ".graphify_transcripts.json", transcript_paths, ensure_ascii=False)
    return {"transcripts": transcript_paths}


# --------------------------------------------------------------------------
# update reference - incremental re-extraction
# --------------------------------------------------------------------------


def step_detect_incremental(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
) -> dict:
    """Diff the corpus against the manifest and write the incremental sidecars.

    Writes ``.graphify_incremental.json`` (the raw result) and populates
    ``.graphify_detect.json`` so the Steps 3A-6 blocks, which read it
    unconditionally, see the right state for an incremental run: ``files`` is the
    changed subset and ``all_files`` the full corpus.
    """
    from graphify.detect import detect_incremental

    out_dir = _out_dir(out)
    out_dir.mkdir(parents=True, exist_ok=True)
    gitignore, exclude = _persisted_corpus_shaping(out_dir, None, None)
    result = detect_incremental(
        _scan(path),
        manifest_path=str(out_dir / "manifest.json"),
        extra_excludes=exclude or None,
        gitignore=gitignore,
    )
    write_json_atomic(out_dir / ".graphify_incremental.json", result, ensure_ascii=False)
    write_json_atomic(
        out_dir / _DETECT_JSON,
        {
            "files": result.get("new_files", {}),
            "all_files": result.get("files", {}),
            "total_files": result.get("new_total", 0),
            "total_words": result.get("total_words", 0),
            "skipped_sensitive": result.get("skipped_sensitive", []),
            "needs_graph": True,
        },
        ensure_ascii=False,
    )
    return result


#: Extensions the update flow treats as "code" (structural extraction only).
_CODE_EXTS = frozenset({
    ".py", ".ts", ".js", ".go", ".rs", ".java", ".cpp", ".c", ".rb", ".swift",
    ".kt", ".cs", ".scala", ".php", ".cc", ".cxx", ".hpp", ".h", ".kts", ".lua",
    ".toc", ".f", ".F", ".f90", ".F90", ".f95", ".F95", ".f03", ".F03", ".f08", ".F08",
})


def step_code_only_check(*, out: Path | str | None = None) -> dict:
    """Report whether every changed file is a code file.

    A code-only change needs no semantic extraction, so the update flow can skip
    Step 3B entirely (no LLM, no subagents).
    """
    out_dir = _out_dir(out)
    result = _read_json(out_dir / ".graphify_incremental.json") or {}
    new_files = result.get("new_files", {})
    all_changed = [f for files in new_files.values() for f in files]
    code_only = all(Path(f).suffix.lower() in _CODE_EXTS for f in all_changed)
    return {"code_only": code_only, "changed": len(all_changed)}


def step_empty_extract(*, out: Path | str | None = None) -> dict:
    """Create an empty ``.graphify_extract.json`` for a deletions-only update.

    The merge step needs an extraction to prune against; without it a
    deletions-only run has nothing to merge. Only written when the file is absent.
    """
    out_dir = _out_dir(out)
    p = out_dir / _EXTRACT_JSON
    if p.exists():
        return {"created": False}
    out_dir.mkdir(parents=True, exist_ok=True)
    write_json_atomic(p, _empty_semantic(), ensure_ascii=False)
    return {"created": True}


def step_update_merge(
    path: str | Path | None = None,
    *,
    out: Path | str | None = None,
    directed: bool = False,
) -> dict:
    """Merge this run's extraction into the existing graph, then re-stamp the manifest.

    Uses ``build_merge`` (reads graph.json directly, preserving edge direction,
    #801). ``prune_sources`` is ONLY the genuinely deleted files: changed files are
    reconciled by ``build_merge``'s replace-on-re-extract (#1344, #1178). ``root=``
    relativizes prune paths to match the graph's relative ``source_file`` values,
    or nothing prunes and stale nodes accumulate (#1361).

    Manifest stamping mirrors the extract path: only semantic files that actually
    produced output are stamped, and files dispatched-but-not-stamped have their
    stale ``semantic_hash`` cleared so the next update re-queues them (#2015, #1948).
    """
    from graphify.build import build_merge
    from graphify.cli import _stamped_manifest_files
    from graphify.detect import save_manifest

    out_dir = _out_dir(out)
    scan = _scan(path)
    new_extraction = _load(out_dir / _EXTRACT_JSON, "merged extraction")
    incremental = _load(out_dir / ".graphify_incremental.json", "incremental sidecar")
    deleted = list(incremental.get("deleted_files", []))
    prune = list(deleted) or None

    G = build_merge(
        [new_extraction],
        graph_path=str(out_dir / "graph.json"),
        prune_sources=prune,
        root=str(scan),
        directed=directed,
    )

    merged_out = {
        "nodes": [{"id": n, **d} for n, d in G.nodes(data=True)],
        "edges": [
            # Explicit source/target last so they win over any stale attrs in d.
            {**{k: val for k, val in d.items() if k not in ("_src", "_tgt", "source", "target")},
             "source": d.get("_src", u), "target": d.get("_tgt", v)}
            for u, v, d in G.edges(data=True)
        ],
        "hyperedges": list(G.graph.get("hyperedges", [])),
        "input_tokens": new_extraction.get("input_tokens", 0),
        "output_tokens": new_extraction.get("output_tokens", 0),
    }
    write_json_atomic(out_dir / _EXTRACT_JSON, merged_out, ensure_ascii=False)

    manifest_files = _stamped_manifest_files(incremental["files"], new_extraction, scan)
    semantic_types = ("document", "paper", "image")
    dispatched = {
        f for t, fl in incremental.get("new_files", {}).items() if t in semantic_types for f in fl
    }
    stamped = {f for fl in manifest_files.values() for f in fl}
    cleared = dispatched - stamped
    scan_corpus = {f for fl in incremental["files"].values() for f in fl}
    save_manifest(
        manifest_files,
        manifest_path=str(out_dir / "manifest.json"),
        root=scan,
        scan_corpus=scan_corpus,
        clear_semantic=cleared or None,
    )

    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "merged_nodes": len(merged_out["nodes"]),
    }


def step_graph_diff(
    *,
    out: Path | str | None = None,
    directed: bool = False,
) -> dict | None:
    """Summarize how the update changed the graph, vs the pre-merge backup.

    Reads ``.graphify_old.json`` (the reference copies graph.json there before the
    merge). Returns ``None`` when there is no backup.
    """
    from graphify.analyze import graph_diff
    from graphify.build import build_from_json
    from graphify.paths import load_node_link_graph

    out_dir = _out_dir(out)
    old = _read_json(out_dir / ".graphify_old.json")
    if old is None:
        return None
    new_extract = _load(out_dir / _EXTRACT_JSON, "merged extraction")
    G_new = build_from_json(new_extract, directed=directed)
    G_old = load_node_link_graph(old)
    return graph_diff(G_old, G_new)


# --------------------------------------------------------------------------
# cleanup
# --------------------------------------------------------------------------


def step_cleanup(*, out: Path | str | None = None) -> list[str]:
    """Remove the per-run sidecars. Returns the paths actually removed.

    ``graph.json``, ``GRAPH_REPORT.md``, ``manifest.json`` and ``cost.json`` are
    deliberately untouched — those are the durable outputs.
    """
    out_dir = _out_dir(out)
    removed: list[str] = []
    for name in (
        _DETECT_JSON, _EXTRACT_JSON, _AST_JSON, _SEMANTIC_JSON,
        _ANALYSIS_JSON, _CACHED_JSON, _UNCACHED_TXT, _SEMANTIC_NEW_JSON,
    ):
        p = out_dir / name
        if p.exists():
            p.unlink()
            removed.append(str(p))
    for stale in out_dir.glob(".graphify_chunk_*.json"):
        stale.unlink()
        removed.append(str(stale))
    needs_update = out_dir / ".needs_update"
    if needs_update.exists():
        needs_update.unlink()
        removed.append(str(needs_update))
    return removed