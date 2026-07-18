# Graphify Agent Performance Benchmarks

This directory contains a reproducible benchmark framework to measure whether Graphify improves coding agent performance on large repositories.

## Motivation

The core question: **Does Graphify improve agent task success rates, or is it just a visualization/compression tool?**

We address this by running controlled tasks with and without Graphify, measuring:
- **Success rate** — did the agent complete the task correctly?
- **Token efficiency** — how many tokens did it consume?
- **Time to solution** — how many agent turns did it take?
- **Confidence** — agent's own assessment of solution quality

## Benchmark Methodology

### Test Setup

Each benchmark consists of:
1. **Target repository** — a real codebase of varying size/complexity
2. **Task set** — 5–10 concrete coding problems (bug fixes, feature adds, refactoring)
3. **Control runs** — execute each task WITHOUT Graphify
4. **Treatment runs** — execute each task WITH Graphify (pre-computed graph)
5. **Metrics collection** — token usage, success rate, reasoning chain

### Task Categories

#### 1. Bug Fixes
- Locate a bug in the codebase from a description
- Fix it correctly
- Example: "The auth module drops requests with custom headers; find and fix"

#### 2. Feature Additions
- Add a new feature that integrates with existing code
- Must work with the existing architecture
- Example: "Add rate-limiting to the API endpoints"

#### 3. Refactoring & Understanding
- Understand call flow and refactor for clarity/performance
- Example: "Reduce the number of database queries in the user service"

#### 4. Architecture Questions
- Answer questions about how the system is structured
- Example: "What is the data flow from user input to storage?"

### Metrics

| Metric | Type | Range | Interpretation |
|--------|------|-------|-----------------|
| **Success** | Binary | 0/1 | Did the agent produce a correct, working solution? |
| **Token Count** | Integer | >0 | Total tokens (input + output) consumed |
| **Turns** | Integer | >0 | Number of agent reasoning steps |
| **Time (s)** | Float | >0 | Wall-clock time in seconds |
| **Confidence** | Float | 0–1 | Agent's self-reported confidence in the solution |
| **Code Quality** | Categorical | {poor, ok, good} | Does the solution follow repo patterns? |

### Statistical Analysis

For each task, compute:
- **Success rate with Graphify** vs **without** (% difference)
- **Mean token reduction** when using Graphify
- **Mean turn reduction** (lower = more efficient reasoning)
- **Effect size** (Cohen's d for token/turn counts)

Report results with 95% confidence intervals.

## Directory Structure

```
benchmarks/
├── README.md                      # This file
├── methodology.md                 # Detailed statistical approach
├── fixtures/                      # Benchmark repositories
│   ├── httpx_mini/               # Small HTTP client library (~6 files)
│   ├── django_subset/            # Medium web framework (~50 files)
│   └── kubernetes_sample/        # Large distributed system (~200 files)
├── tasks/                         # Task definitions by category
│   ├── bug_fixes.json
│   ├── feature_additions.json
│   ├── refactoring.json
│   └── architecture_qa.json
├── runner.py                      # Test harness (runs tasks, collects metrics)
├── evaluator.py                   # Score results (correct/incorrect)
├── results/                       # Output directory
│   ├── raw/                       # Per-run data (JSON)
│   ├── aggregated.json           # Summary statistics
│   └── report.md                 # Human-readable findings
└── examples/                      # Worked examples
    └── benchmark_run_001.log      # Example of a complete run
```

## Running Benchmarks

### Prerequisites

```bash
# Install Graphify + dev dependencies
uv sync --all-extras

# Install benchmark dependencies
pip install anthropic openai gemini-api  # Your LLM provider(s)
```

### Quick Start

```bash
# Run all benchmarks with Claude backend
python benchmarks/runner.py \
  --backend claude \
  --fixtures all \
  --tasks all \
  --runs 3

# Run a specific fixture
python benchmarks/runner.py \
  --fixtures httpx_mini \
  --tasks bug_fixes \
  --runs 5 \
  --backend claude
```

### Interpreting Output

After each run, you'll see:

```
✓ Task: "Fix auth module header bug"
  Success: YES
  Tokens: 4,235 (with graph) vs 5,821 (without) → 27% reduction
  Turns: 3 vs 5 → 40% faster
  Confidence: 0.92
```

Results are saved to `results/raw/` as JSON, then aggregated into `results/aggregated.json` and `results/report.md`.

## Extending Benchmarks

### Add a New Task

Edit `benchmarks/tasks/bug_fixes.json`:

```json
{
  "id": "auth-header-bug",
  "title": "Fix auth module header bug",
  "description": "The auth module drops requests with custom headers. Find the root cause and fix it.",
  "target_files": ["auth.py"],
  "difficulty": "medium",
  "expected_changes": {
    "insertions": 5,
    "deletions": 2
  },
  "verification_script": "test_auth_headers.py",
  "tags": ["auth", "headers", "bug"]
}
```

### Add a New Fixture

1. Clone a real repository or create a synthetic one
2. Place it in `benchmarks/fixtures/<name>/`
3. Add metadata: `benchmarks/fixtures/<name>/metadata.json`

```json
{
  "name": "my_project",
  "description": "A sample project for benchmarking",
  "size_mb": 12,
  "file_count": 45,
  "language": "python",
  "graph_tokens": 8500,
  "graph_nodes": 342,
  "graph_edges": 1205
}
```

## Interpreting Results

### Success Rate

If Graphify improves success rate from 65% → 78%:
- **Interpretation**: Graphify helps agents navigate complex repos and make better decisions
- **Statistical test**: Binomial test (p < 0.05 = significant)

### Token Efficiency

If mean token count drops from 6,200 → 4,800 (23% reduction):
- **Interpretation**: Graphify reduces the search space; agents find answers faster
- **Effect**: This saves cost on API-based models

### Turn Efficiency

If mean turns drop from 6 → 4 (33% reduction):
- **Interpretation**: Agents reason more directly with Graphify; fewer backtracking steps

### What Doesn't Prove Graphify Works

- ❌ Smaller graphs (that's compression, not capability improvement)
- ❌ Prettier visualizations (that's UX, not performance)
- ❌ Longer reports (that's information density, not agent intelligence)

## Reporting

Each benchmark run generates:

1. **results/raw/<timestamp>.json** — raw metrics per task
2. **results/aggregated.json** — summary statistics
3. **results/report.md** — human-readable findings

Include these in discussions/PRs to substantiate claims about Graphify's impact.

## Contributing

To add benchmarks:

1. Create a new task in `tasks/`
2. Add fixtures (if needed) to `benchmarks/fixtures/`
3. Run locally and validate results
4. Open a PR with reproducible results

## References

- Original discussion: [Graphify-Labs/graphify#1328](https://github.com/Graphify-Labs/graphify/discussions/1328)
- Methodology paper: [How to Benchmark Code Understanding Tools](docs/methodology.md)
