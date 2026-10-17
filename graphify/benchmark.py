"""Token-reduction benchmark - measures how much context graphify saves vs naive full-corpus approach."""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

import networkx as nx

from graphify.serve import _query_graph_text, _read_graph
from graphify.paths import default_graph_json as _default_graph_json


_CHARS_PER_TOKEN = 4  # standard approximation


def _safe(unicode_char: str, ascii_fallback: str) -> str:
    """Return unicode_char if stdout can encode it, else ascii_fallback.

    Windows consoles often default to cp1252 which cannot encode box-drawing
    or arrow glyphs; printing them raises UnicodeEncodeError mid-output.
    """
    encoding = getattr(sys.stdout, "encoding", None) or ""
    try:
        unicode_char.encode(encoding)
        return unicode_char
    except (UnicodeEncodeError, LookupError):
        return ascii_fallback


def _hr(width: int = 50) -> str:
    """Horizontal rule that survives non-UTF-8 stdout (e.g. Windows cp1252 console)."""
    return _safe("─", "-") * width


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _query_subgraph_tokens(G: nx.Graph, question: str, depth: int = 3, token_budget: int = 2000) -> int:
    """Estimated tokens of the answer query_graph returns for ``question`` (BFS,
    the MCP tool's defaults), 0 when nothing in the graph matches it. The
    answer is the real one an agent receives: seeds, budget cut and notices."""
    text = _query_graph_text(G, question, mode="bfs", depth=depth, token_budget=token_budget)
    if text == "No matching nodes found.":
        return 0
    return _estimate_tokens(text)


_SAMPLE_QUESTIONS = [
    "how does authentication work",
    "what is the main entry point",
    "how are errors handled",
    "what connects the data layer to the api",
    "what are the core abstractions",
]


def run_benchmark(
    graph_path: str | None = None,
    corpus_words: int | None = None,
    questions: list[str] | None = None,
) -> dict:
    """Measure token reduction: corpus tokens vs graphify query tokens.

    Args:
        graph_path: path to the built graph
        corpus_words: total word count from detect() output; if None, estimated from graph
        questions: list of questions to benchmark; defaults to _SAMPLE_QUESTIONS

    Returns dict with: corpus_tokens, avg_query_tokens, reduction_ratio, per_question
    """
    graph_path = graph_path or _default_graph_json()
    # Loaded exactly as the MCP server loads it (size cap, links/edges
    # normalization for a raw --no-cluster graph, #2212), so every answer
    # measured is the one query_graph returns.
    G = _read_graph(str(graph_path))

    if corpus_words is None:
        # Rough estimate: each node label is ~3 words, plus source context
        corpus_words = G.number_of_nodes() * 50

    corpus_tokens = corpus_words * 100 // 75  # words → tokens (100 words ≈ 133 tokens)

    qs = questions or _SAMPLE_QUESTIONS
    per_question = []
    for q in qs:
        qt = _query_subgraph_tokens(G, q)
        if qt > 0:
            per_question.append({"question": q, "query_tokens": qt, "reduction": round(corpus_tokens / qt, 1)})

    if not per_question:
        return {"error": "No matching nodes found for sample questions. Build the graph first."}

    avg_query_tokens = sum(p["query_tokens"] for p in per_question) // len(per_question)
    reduction_ratio = round(corpus_tokens / avg_query_tokens, 1) if avg_query_tokens > 0 else 0

    return {
        "corpus_tokens": corpus_tokens,
        "corpus_words": corpus_words,
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "avg_query_tokens": avg_query_tokens,
        "reduction_ratio": reduction_ratio,
        "per_question": per_question,
    }


def print_benchmark(result: dict) -> None:
    """Print a human-readable benchmark report."""
    if "error" in result:
        print(f"Benchmark error: {result['error']}")
        return

    print(f"\ngraphify token reduction benchmark")
    print(_hr(50))
    arrow = _safe("→", "->")
    print(f"  Corpus:          {result['corpus_words']:,} words {arrow} ~{result['corpus_tokens']:,} tokens (naive)")
    print(f"  Graph:           {result['nodes']:,} nodes, {result['edges']:,} edges")
    print(f"  Avg query cost:  ~{result['avg_query_tokens']:,} tokens")
    print(f"  Reduction:       {result['reduction_ratio']}x fewer tokens per query")
    print(f"\n  Per question:")
    for p in result["per_question"]:
        print(f"    [{p['reduction']}x] {p['question'][:55]}")
    print()


# ── Answer-quality benchmark ─────────────────────────────────────────────────
# The token benchmark above says how small an answer is, not whether it is the
# right one. This one asks query_graph each question exactly as the MCP tool
# does and checks where the files a right answer names first appear in what
# the agent is shown.

_ANSWER_NODE_RE = re.compile(r"^NODE .*? \[src=(.*?) loc=", re.M)


def load_benchmark_questions(path: str | Path) -> list[dict]:
    """Read benchmark questions: a JSON list, or JSON Lines, of objects
    ``{"question": "...", "files": ["pkg/module.py", ...]}``, where ``files`` are
    the repo-relative files a right answer names (e.g. the files a fix changed)."""
    text = Path(path).read_text(encoding="utf-8").strip()
    if not text:
        return []
    items = json.loads(text) if text.startswith("[") else [
        json.loads(line) for line in text.splitlines() if line.strip()
    ]
    questions = []
    for i, item in enumerate(items, 1):
        question = item.get("question") if isinstance(item, dict) else None
        files = item.get("files") if isinstance(item, dict) else None
        if not isinstance(question, str) or not question.strip():
            raise ValueError(f"question {i}: needs a non-empty \"question\" string")
        if not isinstance(files, list) or not files or not all(isinstance(f, str) and f for f in files):
            raise ValueError(f"question {i}: needs a non-empty \"files\" list of paths")
        questions.append({"question": question, "files": [_norm_path(f) for f in files]})
    return questions


def _norm_path(path: str) -> str:
    path = path.replace("\\", "/").strip()
    while path.startswith("./"):
        path = path[2:]
    return path


def _answer_files(text: str) -> list[str]:
    """Files of the NODE lines a query_graph answer shows, in the order shown."""
    files: list[str] = []
    for match in _ANSWER_NODE_RE.finditer(text):
        path = _norm_path(match.group(1))
        if path and path not in files:
            files.append(path)
    return files


def _score_answer(question: str, expected: list[str], text: str) -> dict:
    """One question's row: where the first expected file sits among the files
    the answer shows (None when it shows none), and the answer's size."""
    shown = _answer_files(text)
    wanted = set(expected)
    return {
        "question": question,
        "files": expected,
        "rank": next((i for i, f in enumerate(shown) if f in wanted), None),
        "tokens": len(text) // 3,
        # query_graph's own notice: every node fit, so edges were kept past the budget
        "over_budget": "[i] Complete answer over budget" in text,
        "files_shown": len(shown),
        "top_files": shown[:5],
    }


def run_answer_benchmark(
    graph_path: str | None,
    questions: list[dict],
    *,
    depth: int = 3,
    token_budget: int = 2000,
) -> dict:
    """Ask query_graph each question (BFS, the MCP tool's defaults) and score it.

    Per question: ``rank`` is the position (0-based) of the first expected file
    among the distinct files the answer shows, None when none is shown;
    ``tokens`` uses the ~3 chars/token rule the budget itself uses; ``over_budget``
    is query_graph's own "Complete answer over budget" notice (the header and
    notices sit outside the budget by design, so a raw size check would not do).
    Returns per_question plus hit@1 / hit@3 / hit@5 / found counts.
    """
    from graphify.serve import _load_graph, _query_graph_text

    G = _load_graph(str(graph_path or _default_graph_json()))
    per_question = [
        _score_answer(item["question"], item["files"],
                      _query_graph_text(G, item["question"], mode="bfs", depth=depth, token_budget=token_budget))
        for item in questions
    ]
    ranks = [p["rank"] for p in per_question]
    tokens = sorted(p["tokens"] for p in per_question)
    n = len(per_question)
    return {
        "nodes": G.number_of_nodes(),
        "edges": G.number_of_edges(),
        "questions": n,
        "depth": depth,
        "token_budget": token_budget,
        "hit_at_1": sum(1 for r in ranks if r is not None and r < 1),
        "hit_at_3": sum(1 for r in ranks if r is not None and r < 3),
        "hit_at_5": sum(1 for r in ranks if r is not None and r < 5),
        "found": sum(1 for r in ranks if r is not None),
        "median_tokens": tokens[n // 2] if n else 0,
        "over_budget": sum(1 for p in per_question if p["over_budget"]),
        "per_question": per_question,
    }


def print_answer_benchmark(result: dict) -> None:
    """Print a human-readable answer-quality report."""
    n = result["questions"]
    if not n:
        print("Answer benchmark: no questions.")
        return
    pct = lambda k: f"{result[k]}/{n} ({100 * result[k] / n:.0f}%)"  # noqa: E731
    print("\ngraphify answer benchmark")
    print(_hr(50))
    print(f"  Graph:           {result['nodes']:,} nodes, {result['edges']:,} edges")
    print(f"  Questions:       {n} (query_graph, BFS depth {result['depth']}, ~{result['token_budget']}-token budget)")
    print(f"  Expected file shown first:      {pct('hit_at_1')}")
    print(f"  Expected file in first 3 files: {pct('hit_at_3')}")
    print(f"  Expected file in first 5 files: {pct('hit_at_5')}")
    print(f"  Expected file anywhere:         {pct('found')}")
    print(f"  Answer size:     median ~{result['median_tokens']:,} tokens; {result['over_budget']} kept past the budget "
          f"(query_graph's \"complete answer over budget\")")
    missed = [p for p in result["per_question"] if p["rank"] is None]
    if missed:
        print("\n  Not found:")
        for p in missed[:20]:
            print(f"    - {p['question'][:70]}")
        if len(missed) > 20:
            print(f"    ... and {len(missed) - 20} more")
    print()
