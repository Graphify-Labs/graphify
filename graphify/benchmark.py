"""Token-reduction benchmark - measures how much context graphify saves vs naive full-corpus approach."""
from __future__ import annotations
import sys
from typing import Any

from graphify.build import edge_data
from graphify.helix.model import graphify_attributes, node_attributes
from graphify.helix.persistence import DEFAULT_PROJECT_STORE, load_graph
from graphify.serve import _query_terms


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


def _query_subgraph_tokens(G: Any, question: str, depth: int = 3) -> int:
    """Run BFS from best-matching nodes and return estimated tokens in the subgraph context."""
    terms = _query_terms(question)
    scored = []
    for node in G.nodes():
        nid, data = node.id, graphify_attributes(node.attributes)
        label = data.get("label", "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    start_nodes = [nid for _, nid in scored[:3]]
    if not start_nodes:
        return 0

    from helixdb import TraversalOptions

    traversal = G.traverse(TraversalOptions(
        seeds=tuple(start_nodes), max_depth=depth, direction="both"
    ))
    visited = {visit.node_id for visit in traversal.visits}

    lines = []
    for nid in visited:
        d = node_attributes(G, nid)
        lines.append(f"NODE {d.get('label', nid)} src={d.get('source_file', '')} loc={d.get('source_location', '')}")
    for traversed in traversal.discovery_edges:
        u, v = traversed.source, traversed.target
        if u in visited and v in visited:
            d = edge_data(G, u, v)
            lines.append(f"EDGE {node_attributes(G, u).get('label', u)} --{d.get('relation', '')}--> {node_attributes(G, v).get('label', v)}")

    return _estimate_tokens("\n".join(lines))


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
    G = load_graph(graph_path or DEFAULT_PROJECT_STORE).graph

    if corpus_words is None:
        # Rough estimate: each node label is ~3 words, plus source context
        corpus_words = G.node_count * 50

    assert corpus_words is not None
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
        "nodes": G.node_count,
        "edges": G.edge_count,
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
