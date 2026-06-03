# Math in the Paper

## 1. Token Reduction Ratio (Section 4.2, E1)

R = T_raw / T_graph

Where:
- T_raw = sum of tokens across all corpus files (naive baseline)
- T_graph = tokens in the BFS subgraph returned for a question
- R = 71.5 for the 52-file mixed corpus

More precisely:
T_raw = sum_{f in F} |tokens(f)|
T_graph = |tokens(subgraph(q, G, d))| for question q, graph G, depth d

## 2. Node Scoring / Query Matching (Section 3.6)

score(n, q) = 1000 * [exact(n,q)] + 100 * [prefix(n,q)] + 1.0 * [substr(n,q)] + 0.5 * [file(n,q)]

Where n is a node, q is the query, and [] is Iverson bracket notation.
This is IDF-inspired: rare tokens get high weight, common ones low.

IDF weight for a query term t:
w(t) = log(|V| / df(t))
where |V| = vocabulary size, df(t) = nodes whose label contains t.

Effective seed nodes S = argmax_{|S|=K} sum_{n in S} score(n, q)

## 3. Hub-Aware BFS (Section 3.6, Algorithm 1)

Let deg(n) = degree of node n in G.
tau = p99({deg(n) : n in V})  [99th percentile degree, min 50]

BFS_hub(G, S, d):
  visited = S
  frontier = S
  for i in 1..d:
    next = {}
    for n in frontier:
      if deg(n) < tau:          -- only expand non-hub nodes
        next += neighbors(n) \ visited
    visited += next
    frontier = next
  return induced_subgraph(G, visited)

Key insight: hub nodes (n where deg(n) >= tau) are INCLUDED in visited
(so they appear in context) but NOT expanded (their neighbors not added).
This prevents god-node explosion.

## 4. Confidence Scoring (Section 3.3)

Three-class tagging:
- EXTRACTED: relation explicit in source (import stmt, call expr, type annotation)
  confidence c = 1.0
- INFERRED: relation reasoned by LLM subagent from context
  confidence c in [0.75, 1.0), threshold 0.75
- AMBIGUOUS: uncertain, flagged for review
  confidence c < 0.75

Extraction quality metric:
Q_ext = |E_EXTRACTED| / |E_total|

Measured across corpora:
- graphify source: Q_ext = 0.899
- karpathy-repos:  Q_ext = 0.779
- mixed-corpus:    Q_ext = 0.500

## 5. Community Detection Objective (Section 3.5)

Leiden optimizes modularity Q:

Q = (1/2m) * sum_{ij} [A_ij - (k_i * k_j)/(2m)] * delta(c_i, c_j)

Where:
- m = number of edges
- A_ij = adjacency matrix
- k_i = degree of node i
- c_i = community of node i
- delta = Kronecker delta

Hub exclusion: nodes with k_i >= tau are excluded from the partition 
before running Leiden, then reinserted into their highest-modularity community.

Community ID total order (deterministic):
rank(C) = (-|C|, sorted(str(n) for n in C))
So larger communities get smaller IDs; ties broken lexicographically.

## 6. Parallel Speedup (Section 4.4)

Speedup S_p = T_seq / T_par

With p = 8 workers on 1,247 files:
S_8 = 4.32s / 1.28s = 3.38x

Theoretical (Amdahl's law):
S_p = 1 / (s + (1-s)/p)
where s = sequential fraction.
From observed: s ≈ 1 - (S_p * (1 - 1/p))^{-1} ... ≈ 0.08 (8% sequential)
