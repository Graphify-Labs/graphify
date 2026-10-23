# Jev Memory Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Measure whether bounded Jev relevance decisions improve Graphify node discovery using selected real claude-mem observations from one approved evaluation repository, with source provenance and no mutation of its structural graph.

**Architecture:** A runner developed in the public Graphify fork reads a pinned `graph.json` from a selected evaluation repository, gets the same ten candidates for both ranking arms from Graphify's existing scorer, and optionally reranks them from validated Jev decisions above a calibrated threshold. Only when the first three ranked IDs change does it send those IDs to `graphify query --seed`; every unavailable, invalid, or unchanged-seed case calls the original unseeded `graphify query`. It writes decision metadata next to the selected graph and leaves Graphify's build, `graph.json`, and learning sidecar untouched.

**Tech Stack:** Python 3.10+, existing NetworkX/Graphify code, Python standard library HTTP/JSON, pytest; optional OpenRouter Decisions API with pinned `typesafe/jev-1.14` after explicit approval.

**Spec:** `.specs/tasks/draft/jev-memory-pilot.feature.md`

## Global Constraints

- Base implementation on the fork task branch from upstream `v8`; `fork/main` is stale. Target a current fork `v8` for the eventual single pilot PR.
- Use public/synthetic observation records only for committed tests in the fork. Select real evaluation records through the supported memory bridge and a separate privacy review. Keep real records, questions, labels, and payload previews in a mode-0700 directory outside every Git worktree; never read the claude-mem database.
- Cap each question at ten graph nodes, three observation records, thirty typed pair decisions, and one Jev request.
- Keep the complete serialized Jev request at or below 24 KiB; reject a larger request locally rather than entering Jev's slower long-context mode.
- Default to offline mode. Do not use an OpenRouter key, send any request, or route to a paid model without a separate explicit user approval in the current conversation.
- Do not change `graph.json`, `.graphify_learning.json`, Graphify's default query behavior, or its `EXTRACTED`/`INFERRED` edge definitions.
- Run Python tests and lint on Mac through `mac-gate`; Graphify has no Next.js build or Vercel Preview gate.

## Review Focus

1. A graph whose `built_at_commit` differs from the checked-out source, or whose candidate source files have uncommitted edits, must fail before excerpts are read; pin this in Task 1.
2. Duplicate labels or missing node IDs must not resolve by guesswork; pin this in Task 1.
3. Extra observation fields must not reach the network payload or sidecar; pin this with a synthetic canary in Tasks 2–3, then human-review every real summary and dry-run payload.
4. Missing, extra, or malformed Jev answers must invalidate the whole request and leave the baseline ordering intact; pin this in Task 3.
5. Queries with no relevant candidate must be represented in the evaluation; pin this in Task 4.

---

## File map

- Create `tools/jev_memory_pilot.py`: local candidate selection, observation validation, decision application, sidecar, query execution, CLI.
- Create `tools/jev_memory_pilot_api.py`: optional, single-request Jev HTTP boundary and strict typed response parsing.
- Create `tests/test_jev_memory_pilot.py`: deterministic fixtures for candidate, ranking, provenance, staleness, dry-run, fallback, and CLI behavior.
- Create `tests/test_jev_memory_pilot_api.py`: mock HTTP transport and response-shape tests; never call a network endpoint.
- Create `tests/fixtures/jev_memory_pilot.json`: public/synthetic observation and small question fixtures only; the real evaluation corpus remains under `~/.local/share/jev-memory-pilot/<repo-hash>/` outside any Git checkout.
- Create `docs/jev-memory-pilot-evaluation.md`: labeling rules, paired metrics, actual results after a permitted run, and the upstream/no-upstream decision.
- Read, do not modify: `graphify/serve.py` (`_read_graph`, `_query_terms`, `_score_query`), `graphify/cli.py` (`query --seed`), `graphify/reflect.py`, `graphify/export.py`.

### Task 1: Pin the candidate pool and baseline

**Files:** Create `tools/jev_memory_pilot.py`; create `tests/test_jev_memory_pilot.py`; create `tests/fixtures/jev_memory_pilot.json`.

**Interfaces:** `candidate_pool(graph_path: Path, repo: Path, question: str) -> list[dict]` returns at most ten ordered records with `node_id`, `label`, `type`, `source_file`, `source_location`, and `baseline_rank`. `load_case(path: Path, case_id: str, graph_node_ids: set[str], project: str) -> dict` selects one case by ID from the fixture or private corpus, validates its question and gold node IDs against the full graph, and resolves at most three selected observations from that project. Task 2 consumes these exact fields.

- [ ] **Step 1: Write failing candidate tests.** Use a tiny JSON node-link graph built in `tmp_path`, with two same-label nodes in different files and `built_at_commit` set to the test repo HEAD. Also edit a candidate source file without committing and assert rejection. Pin the critical assertions:

```python
pool = candidate_pool(graph_path, repo, "same_label")
assert len({item["node_id"] for item in pool}) == len(pool)
assert [item["baseline_rank"] for item in pool] == list(range(1, len(pool) + 1))
graph_data["built_at_commit"] = "0" * 40
graph_path.write_text(json.dumps(graph_data))
with pytest.raises(ValueError, match="graph commit differs"):
    candidate_pool(graph_path, repo, "same_label")
graph_data["built_at_commit"] = subprocess.check_output(
    ["git", "rev-parse", "HEAD"], cwd=repo, text=True
).strip()
graph_path.write_text(json.dumps(graph_data))
source_path.write_text("def edited(): pass\n")
with pytest.raises(ValueError, match="source has uncommitted edits"):
    candidate_pool(graph_path, repo, "same_label")
```
- [ ] **Step 2: Run the focused test through the Mac queue.** Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot.py -q`; expect the new import/function tests to fail.
- [ ] **Step 3: Implement graph pinning and the baseline.** The core candidate path is:

```python
def candidate_pool(graph_path: Path, repo: Path, question: str) -> list[dict]:
    from graphify.serve import _query_terms, _read_graph, _score_query

    graph = _read_graph(str(graph_path))
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip()
    if graph.graph.get("_built_at_commit") != head:
        raise ValueError("graph commit differs from source HEAD; rebuild the graph")
    ranked = _score_query(graph, _query_terms(question), collect_per_term_seeds=False).ranked
    sources = sorted({source for _, nid in ranked[:10]
                      if isinstance(source := graph.nodes[nid].get("source_file"), str)
                      and source})
    for source in sources:
        if subprocess.run(["git", "ls-files", "--error-unmatch", "--", source],
                          cwd=repo, capture_output=True).returncode != 0:
            raise ValueError("candidate source is not tracked at graph HEAD")
    if sources and subprocess.run(["git", "diff", "--quiet", "HEAD", "--", *sources],
                                  cwd=repo).returncode != 0:
        raise ValueError("source has uncommitted edits; rebuild the graph")
    return [
        {
            "node_id": node_id,
            "label": graph.nodes[node_id].get("label", node_id),
            "type": graph.nodes[node_id].get("type", ""),
            "source_file": graph.nodes[node_id].get("source_file", ""),
            "source_location": graph.nodes[node_id].get("source_location", ""),
            "baseline_rank": rank,
        }
        for rank, (_, node_id) in enumerate(ranked[:10], start=1)
    ]
```

- [ ] **Step 4: Add the public fixture and validate its schema.** Give each observation `id`, `project`, `date`, `summary`, and `source_ref`; give each case `id`, `question`, `relevant_node_ids`, `relevant_pairs`, and `observation_ids`. For example:

```json
{"observations":[{"id":"synthetic-001","project":"graphify","date":"2026-10-17","summary":"A synthetic issue describes ambiguous seed labels.","source_ref":"synthetic-001"}],"cases":[{"id":"q001","question":"How are ambiguous seeds handled?","relevant_node_ids":["graphify/affected.py::resolve_seed"],"relevant_pairs":[["graphify/affected.py::resolve_seed","synthetic-001"]],"observation_ids":["synthetic-001"]}]}
```

Reject duplicate IDs, missing fields, more than three observations, unknown node IDs against `graph_node_ids`, and an observation whose `project` differs from the selected `project`. Do not require gold IDs to appear in the ten candidates: those misses define the candidate-recall ceiling. Test an untracked candidate source as well as the dirty tracked source. Keep the fixture free of names, emails, secrets, private paths, and raw claude-mem text.
- [ ] **Step 5: Run the focused tests and commit.** Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot.py -q`; then `git add tools/jev_memory_pilot.py tests/test_jev_memory_pilot.py tests/fixtures/jev_memory_pilot.json` and `git commit -m 'test: pin graph candidate baseline'`.

### Task 2: Add an offline decision runner and provenance sidecar

**Files:** Modify `tools/jev_memory_pilot.py`; modify `tests/test_jev_memory_pilot.py`.

**Interfaces:** `apply_decisions(candidates: list[dict], observations: list[dict], answers: dict[tuple[str, str], dict], *, eligible_node_ids: set[str], threshold: float) -> tuple[list[dict], list[dict]]` returns the candidate ranking and validated suggestion records. `read_sidecar(path: Path, graph_path: Path, head: str) -> dict` reads metadata only if its graph SHA and HEAD still match. Task 3 supplies normalized `answers` keyed by `(node_id, observation_id)` tuples and `eligible_node_ids` from nodes with a committed excerpt; neither ID needs escaping.

- [ ] **Step 1: Write failing tests for no-op fallback and source integrity.** Test relevant, unrelated, insufficient, tied, unknown, and missing pair decisions. Require a complete set of eligible pairs before any promotion; an incomplete or extra answer set falls back to baseline as a whole. Assert only a valid relevant pair above the threshold can promote a candidate, ties preserve `baseline_rank`, and every suggestion contains the original node and observation IDs. Reject sidecar reads after changing either its graph SHA or HEAD. Compare the no-key/error Graphify answer byte-for-byte with the original unseeded `graphify query`, since Graphify's own `_pick_seeds` can differ from the top three scoring rows. Hash `graph.json` and `.graphify_learning.json` before and after; assert both hashes stay equal. Pin the no-op case:

```python
ordered, suggestions = apply_decisions(candidates, observations, {}, eligible_node_ids=set(), threshold=0.8)
assert [row["node_id"] for row in ordered] == [row["node_id"] for row in candidates]
assert suggestions == []
```
- [ ] **Step 2: Run the focused test.** Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot.py -q`; expect the new decision tests to fail.
- [ ] **Step 3: Implement deterministic promotion.** Sort by a validated relevant probability, then baseline rank; ignore every other decision:

```python
def apply_decisions(candidates: list[dict], observations: list[dict], answers: dict, *, eligible_node_ids: set[str], threshold: float):
    valid_obs = sorted(item["id"] for item in observations)
    expected = {(item["node_id"], obs_id) for item in candidates for obs_id in valid_obs
                if item["node_id"] in eligible_node_ids}
    if not answers or set(answers) != expected:
        return candidates, []
    if any(not isinstance(answer, dict)
           or answer.get("choice") not in {"relevant", "unrelated", "insufficient_evidence"}
           or isinstance(answer.get("probability"), bool)
           or not isinstance(answer.get("probability"), (int, float))
           or not math.isfinite(answer["probability"])
           or not 0 <= answer["probability"] <= 1
           for answer in answers.values()):
        return candidates, []
    suggestions = []
    weight = {item["node_id"]: 0.0 for item in candidates}
    for item in candidates:
        for obs_id in valid_obs:
            answer = answers.get((item["node_id"], obs_id))
            if answer is None or answer["choice"] != "relevant":
                continue
            probability = answer.get("probability")
            if probability < threshold:
                continue
            weight[item["node_id"]] = max(weight[item["node_id"]], float(probability))
            suggestions.append({"node_id": item["node_id"], "observation_id": obs_id,
                                "probability": float(probability), "status": "suggestion"})
    ordered = sorted(candidates, key=lambda item: (-weight[item["node_id"]], item["baseline_rank"]))
    return ordered, suggestions
```

- [ ] **Step 4: Add local output.** In fixture mode, show selected candidate/observation IDs and pair count with no credential access. Make one subprocess call to the existing query CLI, appending repeatable `--seed` flags only if the first three ranked IDs differ from the baseline. The CLI loads the graph once. Force `GRAPHIFY_QUERY_LOG_DISABLE=1` for this subprocess because an inherited opt-in query log could write real evaluation questions outside the restricted corpus. Keep Graphify's answer text intact; append a separate `Suggested memory link` line for each suggestion with the node ID, its `source_file:source_location`, observation ID, and `source_ref`, visibly labeled as model-ranked. Write `graphify-out/jev-memory-decisions.json` with `schema_version: 1`, graph SHA-256, HEAD, actual response model ID, query ID/SHA-256, all candidate and observation IDs, and validated decisions using `graphify.paths.write_json_atomic`. Get `case_id` from `load_case`; use the returned model ID only after a valid Jev response, otherwise `None` and an empty decision list. Refuse to read a sidecar whose graph SHA or HEAD differs; never store the raw query or observation summaries.

```python
assisted_used = [x["node_id"] for x in ordered[:3]] != [x["node_id"] for x in candidates[:3]]
chosen = [item["node_id"] for item in ordered[:3]] if assisted_used else []
args = [sys.executable, "-m", "graphify", "query", question, "--graph", str(graph_path)]
if assisted_used:
    args.extend(arg for node_id in chosen for arg in ("--seed", node_id))
query_env = {**os.environ, "GRAPHIFY_QUERY_LOG_DISABLE": "1"}
query_text = subprocess.run(args, check=True, capture_output=True, text=True, env=query_env).stdout
by_id = {item["node_id"]: item for item in candidates}
observations_by_id = {item["id"]: item for item in observations}
for item in suggestions:
    node = by_id[item["node_id"]]
    obs = observations_by_id[item["observation_id"]]
    query_text += (f'\nSuggested memory link: {item["node_id"]} '
                   f'({node["source_file"]}:{node["source_location"]}) '
                   f'↔ {obs["id"]} [{obs["source_ref"]}]')
sidecar_path = graph_path.parent / "jev-memory-decisions.json"
metadata_without_raw_text = {
    "schema_version": 1,
    "graph_sha256": hashlib.sha256(graph_path.read_bytes()).hexdigest(),
    "head": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=repo, text=True).strip(),
    "model": model_id,
    "query_id": case_id,
    "query_sha256": hashlib.sha256(question.encode()).hexdigest(),
    "candidate_ids": [item["node_id"] for item in candidates],
    "selected_nodes": chosen,
    "observation_ids": [item["id"] for item in observations],
    "decisions": [
        {"node_id": node_id, "observation_id": obs_id,
         "choice": answer["choice"], "probability": answer["probability"]}
        for (node_id, obs_id), answer in sorted(answers.items())
    ],
    "redaction_version": 1,
    "created_at": datetime.now(timezone.utc).isoformat(),
}
write_json_atomic(sidecar_path, metadata_without_raw_text, indent=2)

def read_sidecar(path: Path, graph_path: Path, head: str) -> dict:
    data = json.loads(path.read_text())
    if (data.get("schema_version") != 1 or data.get("head") != head
            or data.get("graph_sha256") != hashlib.sha256(graph_path.read_bytes()).hexdigest()):
        raise ValueError("stale Jev memory sidecar")
    return data
```
- [ ] **Step 5: Run the focused tests and commit.** Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot.py -q`; then commit the two touched files with `git commit -m 'feat: add offline memory decision runner'`.

### Task 3: Add a gated Jev adapter

**Files:** Create `tools/jev_memory_pilot_api.py`; create `tests/test_jev_memory_pilot_api.py`; modify `tools/jev_memory_pilot.py`.

**Interfaces:** `make_request(repo: Path, question: str, candidates: list[dict], observations: list[dict]) -> tuple[dict, dict[str, tuple[str, str]]]` returns one Decisions API payload and its local request-key map. `parse_answers(response: dict, pair_map: dict[str, tuple[str, str]]) -> dict[tuple[str, str], dict]` returns only validated `choice`/probability pairs. `call_jev(payload: dict, api_key: str, *, timeout_s: int = 15) -> dict` makes one POST and never retries. Task 4 uses response usage/cost metadata.

- [ ] **Step 1: Write failing API tests.** Mock `urllib.request.urlopen`. Assert zero calls in default/dry-run mode and for an empty candidate/pair set; one call in explicit live mode; no retry after timeout or uncertain response; fail closed for missing/extra answers, bad types, probabilities outside `[0,1]`, missing `usage.cost` during evaluation, and a serialized request above 24 KiB. Assert request state contains only reviewed code excerpts and allowlisted observation fields. Pin the uncertain-write case:

```python
with patch("urllib.request.urlopen", side_effect=TimeoutError) as post:
    with pytest.raises(TimeoutError):
        call_jev(payload, "test-key")
assert post.call_count == 1
```
- [ ] **Step 2: Run the focused test.** Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot_api.py -q`; expect the new tests to fail.
- [ ] **Step 3: Build the typed request and dry-run.** Use one `choice` question per candidate–observation pair, with criteria `relevant`, `unrelated`, and `insufficient_evidence`. Keep node excerpts and observation summaries once each in `state`; pair entries contain only references. Accept only repo-relative code `source_file` paths ending in `.py`, `.ts`, `.tsx`, `.js`, or `.jsx` and containing no `..` segment; read committed source with `git show HEAD:<source_file>` (never the mutable worktree), use the Graphify node's line number, and cap each excerpt at 300 characters. If the path or line is missing, omit every pair for that candidate and keep its baseline rank; never substitute another file. Give each pair a stable short request key (`p000`…`p029`) and keep `request_key -> (node_id, observation_id)` locally; never concatenate IDs into a key. The `summary` field is explicitly human-redacted at corpus selection; slicing it to 300 characters is only a size bound, not privacy protection. Add a dry-run that renders this exact payload without reading credentials: print synthetic payloads and save private payloads only in the restricted local directory. A request body has this shape:

```python
def committed_excerpt(repo: Path, candidate: dict) -> str | None:
    source = candidate["source_file"]
    if not isinstance(source, str):
        return None
    path = PurePosixPath(source)
    if (path.is_absolute() or ".." in path.parts
            or path.suffix not in {".py", ".ts", ".tsx", ".js", ".jsx"}):
        return None
    match = re.search(r"\bL(\d+)", str(candidate["source_location"]))
    if not match or int(match.group(1)) < 1:
        return None
    try:
        code = subprocess.check_output(["git", "show", f"HEAD:{source}"], cwd=repo).decode()
        return code.splitlines()[int(match.group(1)) - 1][:300]
    except (subprocess.CalledProcessError, IndexError, UnicodeDecodeError):
        return None

public_nodes = [
    {"id": item["node_id"], "label": item["label"], "type": item["type"],
     "excerpt": committed_excerpt(repo, item)}
    for item in candidates
]
public_nodes = [item for item in public_nodes if item["excerpt"]]
redacted_observations = [
    {"id": item["id"], "summary": item["summary"][:300]}
    for item in observations
]
pair_refs = [
    {"key": f"p{index:03d}", "node_id": node["id"], "observation_id": obs["id"]}
    for index, (node, obs) in enumerate(itertools.product(public_nodes, redacted_observations))
]
pair_map = {pair["key"]: (pair["node_id"], pair["observation_id"]) for pair in pair_refs}

payload = {
    "model": "typesafe/jev-1.14",
    "state": {"question": question, "nodes": public_nodes,
              "observations": redacted_observations, "pairs": pair_refs},
    "questions": {
        pair["key"]: {
            "type": "choice",
            "instructions": f'Classify only the pair with key {pair["key"]!r} in state.pairs using its node and observation references.',
            "criteria": {
                "relevant": "The observation directly helps answer the question about this code node.",
                "unrelated": "The observation concerns a different behavior or node.",
                "insufficient_evidence": "The supplied excerpts do not establish relevance.",
            },
        }
        for pair in pair_refs
    },
}
return payload, pair_map
```

- [ ] **Step 4: Implement one-call transport and strict response parsing.** Serialize with `json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()` and reject `len(body) > 24 * 1024` before retrieving a key. Use `urllib.request.Request("https://openrouter.ai/api/alpha/decisions", data=body, headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")` and `urlopen(..., timeout=15)` exactly once. Require the answer-key set to match exactly, `type == "choice"`, a permitted `choice`, three finite probabilities in `[0,1]`, and finite nonnegative `usage.cost` for an evaluation record. If any answer is invalid, discard the whole response and keep baseline order. Never print the key or response body. Normalize the API's `probabilities[choice]` to `probability` only after validation.

```python
def call_jev(payload: dict, api_key: str, *, timeout_s: int = 15) -> dict:
    body = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode()
    if len(body) > 24 * 1024:
        raise ValueError("Jev request exceeds 24 KiB")
    request = urllib.request.Request(
        "https://openrouter.ai/api/alpha/decisions", body,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout_s) as response:
        return json.load(response)

def parse_answers(response: dict, pair_map: dict[str, tuple[str, str]]) -> dict:
    choices = {"relevant", "unrelated", "insufficient_evidence"}
    raw = response.get("answers")
    usage = response.get("usage")
    cost = usage.get("cost") if isinstance(usage, dict) else None
    if (not isinstance(raw, dict) or set(raw) != set(pair_map)
            or isinstance(cost, bool) or not isinstance(cost, (int, float))
            or not math.isfinite(cost) or cost < 0):
        raise ValueError("incomplete Jev answer or missing actual cost")
    normalized = {}
    for key, item in raw.items():
        if not isinstance(item, dict) or item.get("type") != "choice":
            raise ValueError("invalid Jev choice answer")
        choice, probabilities = item.get("choice"), item.get("probabilities")
        if choice not in choices or not isinstance(probabilities, dict) or set(probabilities) != choices:
            raise ValueError("invalid Jev choice labels")
        if any(isinstance(value, bool) or not isinstance(value, (int, float))
               or not math.isfinite(value) or not 0 <= value <= 1
               for value in probabilities.values()):
            raise ValueError("invalid Jev probabilities")
        normalized[pair_map[key]] = {"choice": choice, "probability": probabilities[choice]}
    return normalized
```
- [ ] **Step 5: Add the live gate and commit without using it.** Live mode requires a command flag, a manually supplied project-scoped key, a positive per-run request cap, and prior approval for paid use and payload class. On a transport or parse error, set normalized answers to `{}`, write a short diagnostic to stderr, and call the unseeded Graphify query; never write invalid raw answers to the sidecar. Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot_api.py tests/test_jev_memory_pilot.py -q` and `mac-gate uv run --frozen ruff check tools/jev_memory_pilot*.py tests/test_jev_memory_pilot*.py`; commit with `git commit -m 'feat: add opt-in Jev decision adapter'`. Do not make a live request during implementation.

### Task 4: Evaluate paired results and decide on contribution

**Files:** Modify `tests/fixtures/jev_memory_pilot.json`; create `docs/jev-memory-pilot-evaluation.md`; modify `tests/test_jev_memory_pilot.py`.

**Interfaces:** `evaluate(cases: list[dict], baseline: dict[str, dict], assisted: dict[str, dict]) -> dict` joins both arms by case ID. Each arm's case record has `ranked_node_ids`, `candidate_node_ids`, `latency_ms`, `request_count`, and `usage_cost`; the assisted record also has `suggestions` as node/observation ID pairs. Set cost to zero only when request count is zero; a called request without actual `usage.cost` is an error. The result reports candidate recall, precision@5, recall@5, unsupported memory suggestion count/fraction, paired per-question differences, p50/p95 latency, actual request count, and cost. It accepts only pre-labeled cases; it never asks Jev to assign ground truth.

- [ ] **Step 1: Select the real evaluation repository and freeze ground truth.** Use the memory bridge to confirm at least three relevant, safely redacted observations and a current graph for one repository; if that is not possible, stop the product-value claim and report technical feasibility only. Save the selected observations and at least 30 human-labeled questions under `~/.local/share/jev-memory-pilot/<repo-hash>/` with directory mode 0700, outside every Git worktree; include zero-relevant, ambiguous-label, stale-code, and unrelated-memory cases. Record pinned graph SHA/HEAD, relevant node IDs, and relevant node–observation pairs as two-element arrays. Use ten predeclared cases for threshold calibration and at least 20 held-out cases for the result. Baseline and assisted arms must use the same ten candidates per case.
- [ ] **Step 2: Write failing metric tests.** For a small known fixture, assert exact precision@5 and recall@5 fractions, zero-relevant-case handling, candidate recall ceiling, and paired differences. Define candidate recall per case as gold node IDs present in the ten-candidate pool divided by all gold node IDs; report zero-relevant cases separately. Define precision@5 as relevant IDs in the first five divided by five; define recall@5 only for cases with at least one relevant ID. Include a gold node outside the candidate pool in the test, so a missed retrieval cannot be hidden. Assert a missing actual cost cannot be presented as zero cost. Pin one fraction:

```python
assert precision_at_k(["a", "b", "c", "d", "e"], {"a", "c"}, 5) == 2 / 5
```
- [ ] **Step 3: Implement the report calculation and run offline tests.** Use set intersection on frozen relevant IDs. Count an unsupported suggestion when its node–observation pair is absent from the frozen relevant-pair set; divide by all displayed suggestions, with `0/0` reported as `not_applicable`. The baseline has no memory suggestions, so never compare its false-link fraction to the assisted arm. Run `mac-gate uv run --frozen pytest tests/test_jev_memory_pilot.py tests/test_jev_memory_pilot_api.py -q` and `mac-gate uv run --frozen ruff check tools/jev_memory_pilot*.py tests/test_jev_memory_pilot*.py`.

```python
def precision_at_k(ranked: list[str], relevant: set[str], k: int = 5) -> float:
    return len(set(ranked[:k]) & relevant) / k

def recall_at_k(ranked: list[str], relevant: set[str], k: int = 5) -> float | None:
    return len(set(ranked[:k]) & relevant) / len(relevant) if relevant else None
```
- [ ] **Step 4: Request the live gate.** Render at most 30 exact redacted payloads to mode-0600 files under `~/.local/share/jev-memory-pilot/<repo-hash>/` and inspect them locally before any network call. Committed code can still contain private material, so approve each excerpt and summary in the outbound bytes. Show the user the payload class, maximum 30 requests, current model price, and proposed dollar cap without pasting private excerpts into chat. Wait for explicit approval before supplying a key or making the first call. Choose the threshold from the ten calibration cases using only their labels and decisions, with zero unsupported suggestions as a constraint; freeze it, then use it on the held-out cases. Record actual response usage/cost and latency for each question; stop at the cap or first unexpected response.

```python
repo_hash = hashlib.sha256(str(repo.resolve()).encode()).hexdigest()[:12]
private_dir = Path.home() / ".local/share/jev-memory-pilot" / repo_hash
private_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
fd = os.open(private_dir / f"{case_id}.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
with os.fdopen(fd, "wb") as handle:
    handle.write(json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode())
```
- [ ] **Step 5: Decide and commit.** Compare paired precision@5, recall@5, unsupported suggestion count/fraction, and candidate recall on the real held-out cohort. State prominently that these measure candidate ranking, not Graphify answer quality or runtime causality. Claim a pilot gain only if held-out precision@5 improves and no unsupported memory suggestion is displayed. Publish only aggregate metrics and synthetic examples; do not commit the real corpus, source snippets, or query text. If a reusable Graphify gap remains, document that exact gap for a separate upstream task. Commit the public report/fixtures with `git commit -m 'docs: report Jev memory pilot evaluation'` and open one PR from the task branch to the fork's current `v8` after applicable gates.

## Final verification

- Run `mac-gate uv run --frozen pytest tests/ -q --tb=short`, `mac-gate uv run --frozen ruff check tools/jev_memory_pilot*.py tests/test_jev_memory_pilot*.py`, and the actual skillgen CI checks: `mac-gate uv run --frozen python -m tools.skillgen --check`, `--audit-coverage`, `--schema-singleton`, `--monolith-roundtrip`, and `--always-on-roundtrip` (each as its own queued command). Confirm the PR's `test`, `skillgen-check`, `pi-guard`, and `security-scan` jobs finish green at the latest SHA; the Pi guard and security jobs are remote checks for this additive Python pilot. All local test/lint gates stay inside `mac-gate`.
- Create the local graph with `env -u GEMINI_API_KEY -u GOOGLE_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u OPENROUTER_API_KEY uv run --frozen graphify extract . --code-only` if the worktree has none. After code changes, run `env -u GEMINI_API_KEY -u GOOGLE_API_KEY -u OPENAI_API_KEY -u ANTHROPIC_API_KEY -u OPENROUTER_API_KEY uv run --frozen graphify update .` as required by this repo's `AGENTS.md`; after the final commit, update once more so `built_at_commit` matches HEAD. Run `graphify diagnose multigraph --graph graphify-out/graph.json --json --max-examples 3` and compare its SHA-256 before/after a decision run. Investigate any graph shrinkage before accepting output.
- Do not claim a live Jev result, current memory relevance, upstream acceptance, or deployment from offline tests or a green PR alone.

## References verified for this plan

- Graphify `v8` source: `graphify/serve.py` exposes `_score_query`, `_read_graph`, and explicit `seeds`; `graphify/cli.py` supports repeatable `query --seed`.
- OpenRouter Jev guide: https://openrouter.ai/docs/guides/community/jev (typed choices, endpoint, `usage.cost`, and long-context warning).
- Pinned Jev model: https://openrouter.ai/typesafe/jev-1.14 (version and current catalog entry; recheck price before the live gate).
