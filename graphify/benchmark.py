"""Token-reduction benchmark - measures how much context graphify saves vs naive full-corpus approach."""
from __future__ import annotations
import json
import sys
import networkx as nx

from graphify.build import edge_data
from graphify.serve import _query_terms
from graphify.paths import default_graph_json as _default_graph_json

from graphify.serve import _query_graph_text
from graphify.token_usage import Tokenizer


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


def _query_subgraph_tokens(G: nx.Graph, question: str, depth: int = 3) -> int:
    """Run BFS from best-matching nodes and return estimated tokens in the subgraph context."""
    terms = _query_terms(question)
    scored = []
    for nid, data in G.nodes(data=True):
        label = (data.get("label") or "").lower()
        score = sum(1 for t in terms if t in label)
        if score > 0:
            scored.append((score, nid))
    scored.sort(reverse=True)
    start_nodes = [nid for _, nid in scored[:3]]
    if not start_nodes:
        return 0

    visited: set[str] = set(start_nodes)
    frontier = set(start_nodes)
    edges_seen: list[tuple] = []
    for _ in range(depth):
        next_frontier: set[str] = set()
        for n in frontier:
            for neighbor in G.neighbors(n):
                if neighbor not in visited:
                    next_frontier.add(neighbor)
                    edges_seen.append((n, neighbor))
        visited.update(next_frontier)
        frontier = next_frontier

    lines = []
    for nid in visited:
        d = G.nodes[nid]
        lines.append(f"NODE {d.get('label', nid)} src={d.get('source_file', '')} loc={d.get('source_location', '')}")
    for u, v in edges_seen:
        if u in visited and v in visited:
            d = edge_data(G, u, v)
            lines.append(f"EDGE {G.nodes[u].get('label', u)} --{d.get('relation', '')}--> {G.nodes[v].get('label', v)}")

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
    graph_path = graph_path or _default_graph_json()
    # Size-cap check + links/edges normalization + node-link parse. A raw
    # --no-cluster graph stores edges under "edges" and used to KeyError
    # here (#2212).
    from graphify.paths import load_node_link_graph
    G = load_node_link_graph(graph_path)

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


def benchmark_queries(
    graph_path: str,
    cases: list[dict],
    *,
    tokenizer: Tokenizer | None = None,
    max_nodes: int = 80,
    token_budget: int = 2_000,
) -> dict:
    """Measure evidence recall and retrieval tokens against explicit expectations.

    This complements the historical corpus-reduction estimate. Expected node
    labels and relation names make correctness independently auditable, while
    the structured query packet reports exact counts only when the caller
    supplies the tokenizer for the model being benchmarked.
    """

    from graphify.paths import load_node_link_graph

    graph = load_node_link_graph(graph_path)
    results: list[dict] = []
    for case in cases:
        question = str(case.get("question", ""))
        raw = _query_graph_text(
            graph,
            question,
            response_format="evidence_json",
            max_nodes=max_nodes,
            token_budget=token_budget,
            graph_path=graph_path,
            tokenizer=tokenizer,
        )
        payload = json.loads(raw)
        actual_nodes = {str(node.get("label", "")) for node in payload.get("nodes", [])}
        actual_relations = {
            str(edge.get("relation", "")) for edge in payload.get("edges", [])
        }
        expected_nodes = {str(value) for value in case.get("expected_nodes", [])}
        expected_relations = {
            str(value) for value in case.get("expected_relations", [])
        }
        missing_nodes = sorted(expected_nodes - actual_nodes)
        missing_relations = sorted(expected_relations - actual_relations)
        expected_count = len(expected_nodes) + len(expected_relations)
        found_count = expected_count - len(missing_nodes) - len(missing_relations)
        correctness = 1.0 if expected_count == 0 else found_count / expected_count
        results.append({
            "question": question,
            "correctness": round(correctness, 4),
            "missing_nodes": missing_nodes,
            "missing_relations": missing_relations,
            "usage": payload["usage"],
            "coverage": payload["coverage"],
        })

    average = (
        sum(case["correctness"] for case in results) / len(results)
        if results else 0.0
    )
    return {
        "graph_path": str(graph_path),
        "cases": results,
        "average_correctness": round(average, 4),
        "total_evidence_tokens": sum(
            case["usage"]["evidence_tokens"] for case in results
        ),
        "token_count_exact": bool(results) and all(
            case["usage"]["token_count_exact"] for case in results
        ),
        "model_input_tokens": 0,
        "model_output_tokens": 0,
    }
