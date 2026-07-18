# Benchmark Methodology: Statistical Rigor

## Design: Paired Comparative Trial

This is a **paired comparative trial** where each task is run twice:
- **Treatment A** (baseline): Agent solves task WITHOUT Graphify
- **Treatment B** (intervention): Agent solves same task WITH pre-computed Graphify graph

### Why Paired?

- Eliminates variance from task difficulty variation
- Allows within-subject effect size calculation
- Smaller sample size needed for significance

## Hypotheses

**Primary hypothesis (H1):** Graphify improves agent success rate on large repos.
$$P(\text{success}|\text{with Graphify}) > P(\text{success}|\text{without})$$

**Secondary hypothesis (H2):** Graphify reduces token consumption per successful task.
$$E[\text{tokens}|\text{success, with Graphify}] < E[\text{tokens}|\text{success, without}]$$

**Tertiary hypothesis (H3):** Graphify reduces reasoning steps (turns).
$$E[\text{turns}|\text{success, with Graphify}] < E[\text{turns}|\text{success, without}]$$

## Sample Size & Power

For binary success rate:
- Assume baseline success = 60%, treatment success = 75% (15 percentage point lift)
- Desired power = 80% (β = 0.2), α = 0.05
- **Required**: n ≈ 60 tasks across all fixtures
- **Practical target**: 5 tasks × 3 fixtures × 4 runs = 60 observations

For continuous metrics (tokens, turns):
- Assume baseline μ = 5000 tokens, σ = 1500
- Assume intervention reduces by 20%: μ = 4000
- Effect size d = 0.67 (medium)
- **Required**: n ≈ 36 paired observations
- **Practical target**: Same 60 (exceeded by design)

## Success Evaluation

Each task is evaluated by:

1. **Automated checks** (fast):
   - Code parses without syntax errors
   - All imports resolve
   - Unit tests pass

2. **Semantic checks** (careful):
   - The solution addresses the stated problem
   - No obvious logical errors
   - Follows repo coding conventions

3. **Human review** (validation):
   - A domain expert reviews ambiguous cases
   - Marks as Correct / Incorrect / Partial

### Scoring

| Outcome | Code | Points |
|---------|------|--------|
| Full success | ✓✓✓ | 1.0 |
| Partial success | ✓✓− | 0.5 |
| Failed | ✗ | 0.0 |

## Token Accounting

Count tokens using the agent's LLM's tokenizer:

```
Total Tokens = Input Tokens + Output Tokens
```

**Input**: 
- Task description
- Code context (repo files)
- Graph context (if treatment)
- Conversation history

**Output**:
- Agent's reasoning
- Code suggestions
- Refinements

Track separately:
- Tokens WITHOUT graph
- Tokens WITH graph
- Graph payload size (to compute savings)

## Turns & Reasoning

A "turn" is one complete agent cycle:

```
Human: [question]
↓ (agent processes)
Agent: [reasoning + code suggestion]
↓ (human feedback)
Human: [feedback or next task]
```

Count until:
- Agent produces final answer, OR
- Agent gives up / says "I can't"
- Turn limit reached (max 10 to prevent runaway)

## Statistical Tests

### 1. Success Rate Comparison (Primary)

Use **McNemar's test** for paired binary data:

```
         With Graph
         ✓      ✗
Without  ✓  a    b
         ✗  c    d

Statistic = (b - c)² / (b + c)
df = 1, critical value ≈ 3.84 (α = 0.05)
```

Report: 
- Success rate with/without (%)
- Difference ± 95% CI
- McNemar p-value

### 2. Token Reduction (Secondary)

Use **paired t-test**:

```
Differences: d_i = tokens_without_i - tokens_with_i
t = mean(d) / (sd(d) / √n)
df = n - 1
```

Report:
- Mean ± SD for each condition
- Mean difference ± 95% CI
- Cohen's d (effect size)
- Two-tailed p-value

### 3. Turn Reduction (Secondary)

Same as token test (paired t-test on turn counts).

## Multi-Comparison Correction

If testing multiple hypotheses:
- Use **Bonferroni correction**: α' = 0.05 / number_of_tests
- Report both raw and corrected p-values
- Or use **False Discovery Rate (FDR)** control

## Interpreting Results

### Significance vs Effect Size

| p-value | 95% CI includes 0? | Decision |
|---------|-------------------|----------|
| < 0.05 | No | Significant, likely real |
| < 0.05 | Yes | Unlikely (report anyway) |
| > 0.05 | Yes | Not significant |
| > 0.05 | No | Borderline; report with caution |

### Effect Size Interpretation (Cohen's d)

| Range | Interpretation |
|-------|-----------------|
| 0.0 – 0.2 | Negligible |
| 0.2 – 0.5 | Small |
| 0.5 – 0.8 | Medium |
| > 0.8 | Large |

## Potential Confounds

### Control for:

1. **Task difficulty** — use difficulty ratings in stratified analysis
2. **LLM version** — run all tasks with same model snapshot
3. **Agent strategy** — use identical prompts with/without graph
4. **Time-of-day effects** — randomize order
5. **Cold starts** — warm up API connections before timing

### Document:

- LLM model name and version (e.g., `claude-opus-4-6-20250514`)
- API rate limits and throttling
- Any retries or errors during runs
- Wall-clock time vs token count (distinguish latency from capability)

## Reproducibility Checklist

- [ ] All fixtures are under version control or downloadable
- [ ] Task definitions are checked in as JSON
- [ ] Random seeds are fixed (or documented)
- [ ] API keys/credentials are NOT in repository
- [ ] Raw results are saved with timestamps
- [ ] Code is documented and tested

## Reporting Template

```markdown
## Benchmark Results: [Fixture Name]

**Setup**
- Fixture: [name], [file count] files, [LOC] lines of code
- Tasks: [n] tasks across [categories]
- Agent: [model name and version]
- Runs: [n] trials per task
- Date: [ISO date]

### Primary Result: Success Rate

| Condition | Success Rate | 95% CI |
|-----------|--------------|--------|
| Without Graphify | 62% (31/50) | [55–69%] |
| With Graphify | 76% (38/50) | [68–84%] |
| **Difference** | +14pp | [2–26pp] |

**McNemar's Test**: χ² = 5.2, p = 0.022 ✓ Significant

### Secondary Results

**Token Efficiency**
- Without: 5,821 ± 1,340 tokens
- With: 4,235 ± 980 tokens
- Reduction: 27% ± 8% (p < 0.001, d = 1.1)

**Turn Efficiency**
- Without: 5.2 ± 1.8 turns
- With: 3.4 ± 1.2 turns
- Reduction: 35% ± 12% (p = 0.002, d = 1.0)

### Conclusion

Graphify demonstrates statistically significant improvements across all metrics on [Fixture Name]. Evidence supports the hypothesis that Graphify improves agent performance on large repos.
```

## References

- Agresti, A. (2018). Statistical methods for the social sciences. *Pearson*.
- McNemar, Q. (1947). Note on the sampling error of the difference between correlated proportions. *Psychometrika*.
- Cohen, J. (1988). Statistical power analysis for the behavioral sciences.

