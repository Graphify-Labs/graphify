"""LLM semantic judgment layer for graphify analysis outputs.

Rankings produced by the deterministic heuristics in :mod:`graphify.analyze`
(``surprising_connections``, ``suggest_questions``) and the LLM community
labels in :mod:`graphify.llm` are refined by a configured LLM backend: each
candidate is verified ("is this really surprising / worth asking / an accurate
name?") and re-ranked by the model's assessment, replacing the hand-written
weight guesses with a calibrated second opinion.

Design contract (see research.md, D3/D4/D6/D7/D8):
- **Thin interface, deterministic fallback.** Every entry point here may only
  *re-rank or re-word* the candidates it was given; it must never change *which*
  candidates exist and must return the input unchanged on any failure. The
  heuristic rankings are the fail-open base: no LLM reachable means the exact
  current behaviour.
- **Reuse the existing provider mechanism.** Backend resolution, keys, custom
  ``~/.graphify/providers.json`` providers, prompt-injection defanging and
  token accounting all come from :mod:`graphify.llm` (``detect_backend``,
  ``_call_llm``); nothing here reaches the network by itself.
- **Metadata out, never source.** Prompts carry node labels, relation types,
  confidence tags and community member labels — never file contents.
- **Bounded cost.** Surprise candidates are pre-truncated to
  ``surprise_candidates`` (default ``3 * top_n``) before the model call; question
  candidates are capped with ``question_cap``; labels are validated per batch.
- **Pure-pass-through guarantees.** If the LLM reply cannot be parsed, every
  candidate is kept in its original order; if a reply names only *some*
  candidates, the unnamed ones keep the original order and are appended after
  the named (re-ranked) ones so nothing is lost.

Entry points:
- :func:`reorder_surprises` — verify + re-rank surprising-connection candidates.
- :func:`refine_questions` — filter/re-word suggested questions.
- :func:`validate_community_labels` — check LLM community names, fall back to
  hub labels for the ones the model does not confirm.
- :func:`llm_backend` — shared backend resolution used by the CLI/watch/MCP
  pipeline entry points.

The analyze wiring is backend-optional and auto-detects a backend when one is
configured; everything degrades to the pure heuristic output when none exists.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from graphify.llm import _call_llm, detect_backend

# ── shared helpers ────────────────────────────────────────────────────────────

# Default number of surprise candidates submitted for LLM verification. The
# heuristic pass produces a full ranking; only the top fraction is worth model
# attention (cost control — see research.md §9).
DEFAULT_SURPRISE_CANDIDATES = 12
# Cap for question candidates submitted in one refinement call.
DEFAULT_QUESTION_CAP = 18
# Batches for community-label validation — one JSON verdicts call per batch.
DEFAULT_LABEL_BATCH = 40
# Upper bound for a single refinement/verification call, whatever the candidate
# count (safety net; larger corpora are handled in batches).
MAX_ITEMS_PER_CALL = 60

# Env switch to hard-disable the semantic layer even when a backend exists in
# the environment (CI, hermetic runs, cost control).
_ENV_DISABLE = "GRAPHIFY_SEMANTIC_REJECT"
# Env switch for the label-validation mirror (kept separate so one pipeline can
# be tuned without the other).
_ENV_LABEL_DISABLE = "GRAPHIFY_LABEL_SEMANTIC_REJECT"


def _env_flag(*names: str) -> bool:
    for name in names:
        import os
        if os.environ.get(name, "").strip().lower() in ("1", "true", "yes"):
            return True
    return False


def semantic_rejects_enabled() -> bool:
    """True when the semantic re-ranking layer may run (backend present and not
    disabled by env)."""
    if _env_flag(_ENV_DISABLE):
        return False
    try:
        return detect_backend() is not None
    except Exception:
        return False


def _model_score(value: Any) -> float | None:
    """Parse a model verdict score: True/1/'yes' -> 1.0, 'weak'/'maybe' -> 0.5,
    'no'/False/0 -> 0.0, a numeric string 0..1 -> the number, else None."""
    if isinstance(value, bool):
        return 1.0 if value else 0.0
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        v = value.strip().lower()
        if v in ("true", "yes", "y", "1"):
            return 1.0
        if v in ("weak", "maybe", "0.5"):
            return 0.5
        if v in ("false", "no", "n", "0"):
            return 0.0
        try:
            num = float(v)
        except ValueError:
            return None
        if num <= 0:
            return 0.0
        return 1.0 if num >= 1 else num
    return None


def _safe_json_load(text: str) -> Any:
    """Tolerant JSON extraction for model replies: fences, fenced blocks and a
    first-``{``/last-``}`` object are tried in order. Never raises; returns the
    parsed value (usually a dict) or None. Deliberately quiet on failure — the
    caller falls back, no stderr noise."""
    if not isinstance(text, str):
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        # Drop the outermost fenced block.
        fence = stripped.split("\n", 1)
        body = fence[1] if len(fence) > 1 else ""
        close = body.rfind("```")
        if close != -1:
            body = body[:close]
        stripped = body.strip()
    candidates = [stripped]
    start, end = stripped.find("{"), stripped.rfind("}")
    if start != -1 and end > start:
        candidates.append(stripped[start : end + 1])
    for cand in candidates:
        try:
            return json.loads(cand)
        except (json.JSONDecodeError, ValueError):
            continue
    return None


def _batch_items(items: list[Any], batch: int) -> list[list[Any]]:
    if batch <= 0:
        return [items] if items else []
    return [items[i : i + batch] for i in range(0, len(items), batch)]


def _candidate_label(candidate: dict) -> str:
    return str(candidate.get("label") or candidate.get("source") or candidate.get("id") or "")


# ── surprises: verify + re-rank ───────────────────────────────────────────────


def _parse_surprise_verdicts(text: str) -> dict[str, float] | None:
    """Parse the model's JSON ``{index: score}`` verdicts into {index: 0..1}.

    ``index`` is the 1-based candidate number used in the prompt. Returns None
    when nothing usable was parsed (the caller falls back to original order).
    """
    parsed = _safe_json_load(text)
    if not isinstance(parsed, dict):
        return None
    out: dict[str, float] = {}
    for key, value in parsed.items():
        score = _model_score(value)
        if score is None:
            continue
        try:
            idx = int(str(key).strip())
        except (TypeError, ValueError):
            continue
        if 1 <= idx <= MAX_ITEMS_PER_CALL:
            out[str(idx)] = score
    return out or None


def reorder_surprises(
    candidates: list[dict],
    *,
    top_n: int = 5,
    backend: str | None = None,
    model: str | None = None,
    surprise_candidates: int = DEFAULT_SURPRISE_CANDIDATES,
) -> list[dict]:
    """Verify and re-rank surprising-connection candidates with the LLM.

    Exact-copy guarantee (fail-open contract): the returned list always
    contains every candidate from the (possibly truncated) input list, ordered:
    1. candidates the model judged surprising, by model score desc
       (ties -> original order),
    2. candidates it judged *not* surprising, in original order.
    A parse failure, backend error, or an empty candidate list returns the
    input unchanged (a copy).
    """
    if not candidates:
        return []
    try:
        verdicts = _verdict_candidates(
            candidates, top_n, surprise_candidates, backend=backend, model=model
        )
        if not verdicts:
            return list(candidates)
        return _apply_verdicts(candidates, verdicts)
    except Exception as exc:  # noqa: BLE001 - fail-open discipline
        print(
            f"[graphify semantic] surprise re-ranking skipped ({exc}); "
            "keeping heuristic order.",
            file=sys.stderr,
        )
        return list(candidates)


def _verdict_candidates(
    candidates: list[dict],
    top_n: int,
    surprise_candidates: int,
    *,
    backend: str | None,
    model: str | None,
) -> dict[str, float] | None:
    """Ask the model ``genuinely surprising?`` for the top candidates. Returns
    {candidate_index: score} or None when there is nothing to judge / no LLM."""
    pool = candidates[: max(top_n, surprise_candidates)]
    if not pool:
        return None
    if backend is None:
        try:
            backend = detect_backend()
        except Exception:
            return None
    if not backend or _env_flag(_ENV_DISABLE):
        return None

    lines: list[str] = []
    for i, cand in enumerate(pool, start=1):
        src = _candidate_label(cand)
        tgt = str(cand.get("target") or cand.get("label") or "")
        rel = cand.get("relation", "")
        conf = cand.get("confidence", "EXTRACTED")
        why = str(cand.get("why") or cand.get("note") or "").strip()
        parts = [f'{i}. "{src}" --{rel}--> "{tgt}"', f"   confidence: {conf}"]
        if why:
            parts.append(f"   reason: {why}")
        lines.append("\n".join(parts))

    prompt = (
        "You are evaluating surprising connections discovered in a code "
        "knowledge graph. For each numbered candidate, judge how genuinely "
        "surprising or insightful the connection is for someone trying to "
        "understand the codebase architecture.\n"
        "Rules:\n"
        "- 'yes' = genuinely surprising / non-obvious / insightful\n"
        "- 'weak' = mildly interesting but not deeply surprising\n"
        "- 'no' = obvious, mechanical, or low-value connection\n"
        "Respond ONLY with a JSON object mapping each candidate index (as a "
        "string, e.g. \"1\") to one of: 1.0 (yes), 0.5 (weak), 0.0 (no). "
        "No prose.\n\n"
        + "\n".join(lines)
    )
    try:
        text = _call_llm(prompt, backend=backend, max_tokens=1024, model=model)
    except Exception:
        return None
    return _parse_surprise_verdicts(text)


def _apply_verdicts(candidates: list[dict], verdicts: dict[str, float]) -> list[dict]:
    """Stable partition by verdict: positively-scored first (score desc, tie
    original order), then the rest (score 0 or unjudged) in original order."""
    judged: list[tuple[int, float]] = []
    for i in range(len(candidates)):
        score = verdicts.get(str(i + 1))
        if score is not None:
            judged.append((i, score))
    judged.sort(key=lambda t: (-t[1], t[0]))
    keep_idx = {i for i, s in judged if s > 0}
    ordered = [candidates[i] for i, _ in judged if i in keep_idx]
    tail = [c for i, c in enumerate(candidates) if i not in keep_idx]
    return ordered + tail


# ── questions: keep/filter + re-word ──────────────────────────────────────────


def refine_questions(
    questions: list[dict],
    *,
    top_n: int = 7,
    backend: str | None = None,
    model: str | None = None,
    question_cap: int = DEFAULT_QUESTION_CAP,
) -> list[dict]:
    """Filter and re-word suggested questions with the LLM.

    Keeps candidates the model rates as worth asking (score > 0), re-worded
    when the model provided a better phrasing, then truncates to ``top_n``. On
    any failure (no backend, parse error, exception) returns the input
    truncated to ``top_n`` — identical to the pre-layer behaviour. The
    no-signal placeholder question is never re-worded or dropped.
    """
    if not questions:
        return []
    if len(questions) == 1 and questions[0].get("type") == "no_signal":
        return list(questions)
    pool = questions[: min(len(questions), max(question_cap, 1))]
    try:
        if backend is None:
            backend = detect_backend()
        if not backend or _env_flag(_ENV_DISABLE):
            return list(questions[:top_n])
        refined = _refine_question_pool(pool, backend=backend, model=model)
        return _apply_question_refinements(pool, refined, top_n)
    except Exception as exc:  # noqa: BLE001 - fail-open discipline
        print(
            f"[graphify semantic] question refinement skipped ({exc}); "
            "keeping template questions.",
            file=sys.stderr,
        )
        return list(questions[:top_n])


def _refine_question_pool(
    pool: list[dict], *, backend: str, model: str | None
) -> list[dict]:
    """One batched call: for each candidate ask keep? + better wording.
    Returns a list of {index, keep (0/0.5/1), question?} for the items the
    model answered; missing entries mean "no opinion" (keep original)."""
    lines: list[str] = []
    for i, q in enumerate(pool, start=1):
        qtype = q.get("type", "?")
        text = str(q.get("question") or "").strip()
        why = str(q.get("why") or "").strip()
        lines.append(f'{i}. [{qtype}] {text}' + (f"  (why: {why})" if why else ""))
    prompt = (
        "You are curating suggested questions for a code knowledge graph. "
        "For each numbered question decide whether it is genuinely worth "
        "asking someone who is trying to understand this codebase, and if you "
        "can phrase it more precisely, provide a better wording.\n"
        "Respond ONLY with a JSON object keyed by question index (string), "
        "each value an object with:\n"
        '  "keep": true | false | "maybe"\n'
        '  "question": optional improved wording (only when you improve it)\n'
        "Keep the question only when it targets a real, actionable ambiguity "
        "or knowledge gap. No prose.\n\n"
        + "\n".join(lines)
    )
    try:
        text = _call_llm(prompt, backend=backend, max_tokens=2048, model=model)
    except Exception:
        return []
    return _parse_question_refinements(text)


def _parse_question_refinements(text: str) -> list[dict]:
    """Parse the batched keep/reword reply into [{index, keep, question}],
    skipping malformed entries. ``keep`` is normalised to 1.0/0.5/0.0;
    unknown values -> 1.0 (fail-open on the side of keeping)."""
    parsed = _safe_json_load(text)
    if not isinstance(parsed, dict):
        return []
    out: list[dict] = []
    for key, value in parsed.items():
        try:
            idx = int(str(key).strip())
        except (TypeError, ValueError):
            continue
        if not 1 <= idx <= MAX_ITEMS_PER_CALL:
            continue
        if not isinstance(value, dict):
            continue
        keep_raw = value.get("keep")
        rewording = value.get("question")
        if isinstance(rewording, str) and not rewording.strip():
            rewording = None
        if rewording is not None and len(rewording.split()) > 80:
            rewording = None
        if keep_raw is None:
            keep = 1.0
        elif isinstance(keep_raw, bool):
            keep = 1.0 if keep_raw else 0.0
        elif isinstance(keep_raw, (int, float)):
            keep = float(keep_raw)
        else:
            s = str(keep_raw).strip().lower()
            if s in ("true", "yes", "keep"):
                keep = 1.0
            elif s == "maybe":
                keep = 0.5
            elif s in ("false", "no", "drop"):
                keep = 0.0
            else:
                keep = 1.0
        out.append({"index": idx, "keep": keep, "question": rewording})
    return out


def _apply_question_refinements(
    pool: list[dict], refined: list[dict], top_n: int
) -> list[dict]:
    """Merge model opinions onto the pool: drop keep=0, re-word when given,
    stable original order for equal keep. The result is truncated to top_n."""
    by_idx = {r["index"]: r for r in refined}
    kept: list[tuple[float, int, dict]] = []
    for i, q in enumerate(pool):
        opinion = by_idx.get(i + 1)
        if opinion is not None and opinion["keep"] <= 0:
            continue
        keep = opinion["keep"] if opinion is not None else 1.0
        item = dict(q)
        if opinion is not None and opinion.get("question"):
            item["question"] = opinion["question"]
            why = str(item.get("why") or "")
            if "semantic refinement" not in why:
                item["why"] = (why + " (semantic refinement)").strip()
        kept.append((keep, i, item))
    kept.sort(key=lambda t: (-t[0], t[1]))
    return [item for _, _, item in kept][:top_n]


# ── labels: validate + fall back to hub ───────────────────────────────────────


def _parse_label_verdicts(text: str) -> dict[str, float] | None:
    """Parse ``{id: "yes"/"no"}`` label verdicts into {cid_str: 0..1}."""
    parsed = _safe_json_load(text)
    if not isinstance(parsed, dict):
        return None
    out: dict[str, float] = {}
    for key, value in parsed.items():
        score = _model_score(value)
        if score is None:
            continue
        out[str(key)] = score
    return out or None


def validate_community_labels(
    names: dict[int, str],
    communities: dict[int, list[str]],
    G,
    *,
    backend: str | None = None,
    model: str | None = None,
    label_batch: int = DEFAULT_LABEL_BATCH,
    usage_out: dict | None = None,
) -> dict[int, str]:
    """Semantic check of LLM community names against their member labels.

    For each community the model is shown its candidate name plus a sample of
    member labels (up to 6) and asked: does this name accurately summarise the
    community? Names confirmed (score > 0.75) are kept; names the model rejects
    — or communities it did not judge — fall back to the deterministic hub
    label via :func:`graphify.cluster.label_communities_by_hub`.

    Fail-open: no backend / parse failure / exception returns ``names``
    unchanged. A rejected name therefore degrades to the *hub* name, never to
    ``Community N``, unless the hub labeler itself cannot name it.
    """
    if not names or not communities:
        return dict(names) if names else {}
    to_judge = {
        cid: members
        for cid, members in communities.items()
        if cid in names
        and str(names[cid]).strip()
        and str(names[cid]).strip() != f"Community {cid}"
    }
    if not to_judge:
        return dict(names)
    try:
        if backend is None:
            backend = detect_backend()
        if not backend or _env_flag(_ENV_LABEL_DISABLE):
            return dict(names)
        verdicts = _label_verdicts(
            to_judge, names, G, backend=backend, model=model,
            label_batch=label_batch, usage_out=usage_out,
        )
    except Exception as exc:  # noqa: BLE001 - fail-open discipline
        print(
            f"[graphify semantic] label validation skipped ({exc}); "
            "keeping LLM names.",
            file=sys.stderr,
        )
        return dict(names)
    if not verdicts:
        return dict(names)
    try:
        from graphify.cluster import label_communities_by_hub
        hub = label_communities_by_hub(G, communities)
    except Exception:
        hub = {}
    out = dict(names)
    for cid_key, score in verdicts.items():
        cid = _cid_int(cid_key)
        if cid is None or cid not in out:
            continue
        if score > 0.75:
            continue
        fallback = hub.get(cid)
        if fallback and str(fallback).strip() and str(fallback) != f"Community {cid}":
            out[cid] = fallback
    return out


def _cid_int(key: Any) -> int | None:
    try:
        return int(key)
    except (TypeError, ValueError):
        return None


_LABEL_SAMPLE = 6


def _label_verdicts(
    to_judge: dict[int, list[str]],
    names: dict[int, str],
    G,
    *,
    backend: str,
    model: str | None,
    label_batch: int,
    usage_out: dict | None,
) -> dict[str, float]:
    """Batched ``is this name accurate?`` calls. Returns {cid_str: score}."""
    verdicts: dict[str, float] = {}
    batches = _batch_items(sorted(to_judge.items()), max(1, label_batch))
    for batch in batches:
        lines: list[str] = []
        for cid, members in batch:
            sample: list[str] = []
            for nid in members:
                if nid not in G.nodes:
                    continue
                label = str(G.nodes[nid].get("label") or nid).strip().strip("()")[:60]
                if label and label not in sample:
                    sample.append(label)
                if len(sample) >= _LABEL_SAMPLE:
                    break
            name = str(names.get(cid, "")).strip()
            lines.append(
                f"- id: {cid}\n  name: \"{name}\"\n"
                f"  members: {', '.join(sample) if sample else '(none visible)'}"
            )
        if not lines:
            continue
        prompt = (
            "You are quality-checking names given to communities (clusters) in "
            "a code knowledge graph. For each community decide whether its name "
            "accurately summarises what the community is about, based on the "
            "member labels.\n"
            "Rules:\n"
            "- 'yes' = the name is an accurate, meaningful summary\n"
            "- 'no' = the name is wrong, generic (e.g. echoes an id), or misleading\n"
            "Respond ONLY with a JSON object mapping each community id (as a "
            "string) to \"yes\" or \"no\". No prose.\n\n"
            + "\n\n".join(lines)
        )
        try:
            text = _call_llm(
                prompt, backend=backend, max_tokens=1024, model=model,
                usage_out=usage_out,
            )
        except Exception as exc:
            print(
                f"[graphify semantic] label validation batch failed ({exc}); "
                "keeping LLM names for this batch.",
                file=sys.stderr,
            )
            continue
        parsed = _parse_label_verdicts(text)
        if parsed:
            verdicts.update(parsed)
    return verdicts


# ── pipeline entry point ──────────────────────────────────────────────────────


def llm_backend(
    *, explicit: str | None = None
) -> tuple[str | None, str | None]:
    """Resolve the semantic layer's backend. Returns ``(backend, model)``.

    Precedence: explicit backend > environment (``detect_backend``) > None.
    Kept as the single resolution point for wiring (CLI/watch/MCP all funnel
    through this so behavior — and env kill-switches — stay consistent).
    """
    if explicit:
        return explicit, None
    try:
        backend = detect_backend()
    except Exception:
        backend = None
    if not backend:
        return None, None
    return backend, None