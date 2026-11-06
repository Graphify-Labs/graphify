"""Offline evaluation of the triage classifier against a labeled set of issues.

Opt-in and paid: it calls a live API, so it is not part of CI. Run it by hand from
the repository root, once per engine you want to compare::

    TYPESAFE_API_KEY=... python -m tools.triage.eval_classifier \
        --provider typesafe --model jev-latest --runs 2 --json jev.json

    GEMINI_API_KEY=... python -m tools.triage.eval_classifier \
        --provider gemini --model gemini-3.5-flash-lite --runs 1 --sleep 5 --json gemini.json

Each run classifies the labeled issues in ``eval_dataset.json`` through the exact
code path the workflow uses and reports:

* top-1 accuracy for ``kind`` and ``area`` against the hand-adjudicated ground truth
* soft accuracy: the mean probability put on the ground-truth option (System One
  only; chat providers do not return a probability distribution)
* area containment: whether the ground-truth area is among the returned (<=2) areas
* good-first-issue precision / recall against the ground truth
* wall-clock latency (mean / p50 / p95), input/output tokens, and cost

Ground truth is a careful manual read of each issue, not a gold-standard human
panel, so read the absolute figures as an agreement rate, not a proof of quality.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from pathlib import Path

from tools.triage import classify

DATASET_PATH = Path(__file__).with_name("eval_dataset.json")

# Published list prices, USD per 1M tokens (input, output), for the paid tier.
# System One bills input only. Free-tier API keys are billed $0 in practice; these
# numbers are the apples-to-apples paid price. Override with --price-in/--price-out.
PRICES: dict[str, tuple[float, float]] = {
    "typesafe": (0.042, 0.0),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.1-flash-lite": (0.25, 1.50),
}


def _key_for(provider: str) -> str:
    entry = classify.PROVIDERS.get(provider)
    if entry is not None:
        for name in entry.key_envs:
            if os.environ.get(name):
                return os.environ[name].strip()
    return (os.environ.get("TRIAGE_API_KEY") or "").strip()


def _build_config(provider: str, model: str, timeout: int) -> classify.Config:
    if provider not in classify.PROVIDERS:
        raise SystemExit(f"unknown provider {provider!r}; known: {', '.join(classify.PROVIDERS)}")
    entry = classify.PROVIDERS[provider]
    base_url = (os.environ.get("TRIAGE_BASE_URL") or entry.base_url).rstrip("/")
    max_tokens = (
        0
        if provider == "typesafe"
        else int(os.environ.get("TRIAGE_MAX_TOKENS") or classify.MAX_TOKENS)
    )
    return classify.Config(
        base_url=base_url,
        model=model,
        api_key=_key_for(provider),
        timeout=timeout,
        max_tokens=max_tokens,
        provider=provider,
    )


def _pct(values: list[float], pct: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    if len(ordered) == 1:
        return ordered[0]
    index = max(0, min(len(ordered) - 1, round(pct * (len(ordered) - 1))))
    return ordered[index]


def _tokens(usage: dict) -> tuple[int, int]:
    """Normalise token counts across the System One and OpenAI-compatible shapes."""
    tin = usage.get("input_tokens") or usage.get("prompt_tokens") or 0
    tout = usage.get("output_tokens") or usage.get("completion_tokens") or 0
    return int(tin), int(tout)


def _run_one(config: classify.Config, case: dict, trace: bool) -> dict:
    """One evaluation of one issue, mirroring the workflow's issue shape."""
    issue = {
        "number": case["number"],
        "title": case["title"],
        "body": case["body"],
        "labels": case.get("existing_labels") or [],
    }
    started = time.perf_counter()
    try:
        if config.provider == "typesafe":
            request_body = classify.build_systemone_body(config, issue)
            response = classify.call_typesafe(config, issue)
            decision = classify.typesafe_decision(response)
            answers = response.get("answers") or {}
            kind_probs = (answers.get("kind") or {}).get("probabilities") or {}
            area_probs = (answers.get("area") or {}).get("probabilities") or {}
            gfi_noul = (answers.get("good_first_issue") or {}).get("noul")
        else:
            messages = classify.build_messages(issue)
            request_body = {
                "model": config.model,
                "messages": messages,
                "temperature": 0,
                "max_tokens": config.max_tokens,
            }
            response = classify.call_model_raw(config, messages)
            content = response["choices"][0]["message"]["content"]
            decision = classify.parse_reply(content)
            kind_probs, area_probs, gfi_noul = {}, {}, None
    except Exception as exc:  # noqa: BLE001 - report failures, never crash the run
        return {"number": case["number"], "error": f"{type(exc).__name__}: {exc}"}

    elapsed_ms = (time.perf_counter() - started) * 1000.0
    tin, tout = _tokens(response.get("usage") or {})
    decision = decision or {}
    result = {
        "number": case["number"],
        "ms": round(elapsed_ms, 1),
        "model": response.get("model") or config.model,
        "unusable": decision == {},
        "kind": decision.get("kind"),
        "areas": decision.get("area") or [],
        "good_first_issue": bool(decision.get("good_first_issue")),
        "confidence": decision.get("confidence"),
        "kind_probs": kind_probs,
        "area_probs": area_probs,
        "area_secondary": None,
        "gfi_noul": gfi_noul,
        "input_tokens": tin,
        "output_tokens": tout,
    }
    if trace:
        result["request"] = request_body
        result["response"] = response
    return result


def _score(cases: list[dict], results: dict[int, dict]) -> dict:
    kind_hits = area_top1_hits = area_contained = 0
    kind_mass: list[float] = []
    area_mass: list[float] = []
    tp = fp = fn = tn = 0
    scored = 0
    for case in cases:
        run = results[case["number"]]
        if "error" in run:
            continue
        scored += 1
        expected = case["expected"]
        if run["kind"] == expected["kind"]:
            kind_hits += 1
        if run["kind_probs"]:
            kind_mass.append(float(run["kind_probs"].get(expected["kind"], 0.0)))

        areas = run["areas"]
        if areas and areas[0] == expected["area"]:
            area_top1_hits += 1
        if expected["area"] in areas:
            area_contained += 1
        if run["area_probs"]:
            area_mass.append(float(run["area_probs"].get(expected["area"], 0.0)))

        want, got = expected["good_first_issue"], run["good_first_issue"]
        if want and got:
            tp += 1
        elif want and not got:
            fn += 1
        elif not want and got:
            fp += 1
        else:
            tn += 1

    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return {
        "attempted": len(cases),
        "scored": scored,
        "failed": len(cases) - scored,
        "kind_top1": kind_hits / scored if scored else 0.0,
        "kind_soft": statistics.fmean(kind_mass) if kind_mass else None,
        "area_top1": area_top1_hits / scored if scored else 0.0,
        "area_contained": area_contained / scored if scored else 0.0,
        "area_soft": statistics.fmean(area_mass) if area_mass else None,
        "gfi_precision": precision,
        "gfi_recall": recall,
        "gfi_f1": (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0,
        "gfi_counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
    }


def _stability(first: dict[int, dict], second: dict[int, dict]) -> dict:
    both = [n for n in first if "error" not in first[n] and "error" not in second.get(n, {})]
    total = len(both) or 1
    return {
        "pairs": len(both),
        "kind_agreement": sum(1 for n in both if first[n]["kind"] == second[n]["kind"]) / total,
        "area_agreement": sum(
            1 for n in both if sorted(first[n]["areas"]) == sorted(second[n]["areas"])
        )
        / total,
        "gfi_agreement": sum(
            1 for n in both if first[n]["good_first_issue"] == second[n]["good_first_issue"]
        )
        / total,
    }


def _cost(
    results: list[dict[int, dict]], price_in: float, price_out: float
) -> tuple[int, int, float]:
    tin = sum(r.get("input_tokens", 0) for run in results for r in run.values())
    tout = sum(r.get("output_tokens", 0) for run in results for r in run.values())
    return tin, tout, tin / 1e6 * price_in + tout / 1e6 * price_out


def _print_report(label, cases, runs) -> None:
    by_number = {c["number"]: c for c in cases}
    print(f"\nPer-issue (run 1)  [{label}]")
    print("-" * 100)
    print(
        f"{'issue':>6}  {'kind':<16} {'area':<26} {'gfi':<4} {'ms':>7}  {'p(kind)':>7} {'p(area)':>7}"
    )
    print("-" * 100)
    for number, run in runs[0].items():
        expected = by_number[number]["expected"]
        if "error" in run:
            print(f"{number:>6}  ERROR {run['error'][:70]}")
            continue
        got_kind = (run["kind"] or "?").replace("kind/", "")
        mark = (
            "ok"
            if run["kind"] == expected["kind"]
            else "->" + expected["kind"].replace("kind/", "")
        )
        areas = ",".join(a.replace("area/", "") for a in run["areas"]) or "?"
        pk = run["kind_probs"].get(expected["kind"], 0)
        pa = run["area_probs"].get(expected["area"], 0)
        ps = f"{pk:>7.2f} {pa:>7.2f}" if run["kind_probs"] else f"{'n/a':>15}"
        print(
            f"{number:>6}  {got_kind:<10} {mark:<5} {areas:<24} {str(run['good_first_issue']):<4} {run['ms']:>7.0f}  {ps}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Evaluate the triage classifier on labeled issues."
    )
    parser.add_argument("--provider", default="typesafe", help="provider id (default typesafe)")
    parser.add_argument("--model", default="jev-latest", help="model id or alias")
    parser.add_argument("--runs", type=int, default=1, help="repeats per issue, for stability")
    parser.add_argument(
        "--sleep", type=float, default=0.0, help="seconds between requests (rate limits)"
    )
    parser.add_argument("--timeout", type=int, default=60, help="seconds per request")
    parser.add_argument("--only", default="", help="comma-separated issue numbers")
    parser.add_argument(
        "--trace", type=int, default=0, help="include full request/response for N issues"
    )
    parser.add_argument("--price-in", type=float, default=None, help="USD per Mtok input")
    parser.add_argument("--price-out", type=float, default=None, help="USD per Mtok output")
    parser.add_argument("--json", dest="json_path", default="", help="write full results here")
    parser.add_argument("--dataset", default=str(DATASET_PATH), help="labeled dataset path")
    args = parser.parse_args()

    provider = args.provider.lower()
    if provider == "typesafe":
        args.model = args.model or "jev-latest"
    if not _key_for(provider):
        print(f"no key for {provider}: set its provider key or TRIAGE_API_KEY", file=sys.stderr)
        return 2

    dataset = json.loads(Path(args.dataset).read_text(encoding="utf-8"))
    cases = dataset["cases"]
    if args.only:
        wanted = {int(n) for n in args.only.split(",") if n.strip()}
        cases = [c for c in cases if c["number"] in wanted]
    if not cases:
        print("no cases selected", file=sys.stderr)
        return 2

    price = PRICES.get(provider if provider == "typesafe" else args.model, (0.0, 0.0))
    price_in = args.price_in if args.price_in is not None else price[0]
    price_out = args.price_out if args.price_out is not None else price[1]

    config = _build_config(provider, args.model, args.timeout)
    label = f"{provider}:{args.model}"
    runs: list[dict[int, dict]] = []
    for index in range(max(1, args.runs)):
        print(f"run {index + 1}/{args.runs}  [{label}] ...", file=sys.stderr)
        current: dict[int, dict] = {}
        for position, case in enumerate(cases):
            if args.sleep and (position or index):
                time.sleep(args.sleep)
            current[case["number"]] = _run_one(
                config, case, trace=index == 0 and position < args.trace
            )
        runs.append(current)

    first = runs[0]
    summary = _score(cases, first)
    stability = _stability(first, runs[1]) if len(runs) > 1 else {}
    _print_report(label, cases, runs)

    tin, tout, cost = _cost(runs, price_in, price_out)
    requests = sum(len(run) for run in runs)
    latencies = [r["ms"] for r in first.values() if "error" not in r]

    print("\nSummary")
    print("-" * 100)
    print(f"engine                   : {label}")
    print(
        f"scored / attempted       : {summary['scored']} / {summary['attempted']}  ({summary['failed']} failed)  runs: {len(runs)}"
    )
    print(f"kind  top-1 accuracy     : {summary['kind_top1']:.1%}")
    print(
        f"area  top-1 accuracy     : {summary['area_top1']:.1%}   contained: {summary['area_contained']:.1%}"
    )
    if summary["kind_soft"] is not None:
        print(
            f"soft accuracy            : p(kind) {summary['kind_soft']:.3f}   p(area) {summary['area_soft']:.3f}"
        )
    else:
        print("soft accuracy            : n/a (chat provider returns no probability distribution)")
    print(
        f"good-first-issue         : precision {summary['gfi_precision']:.1%}  recall {summary['gfi_recall']:.1%}  {summary['gfi_counts']}"
    )
    if latencies:
        print(
            f"latency (wall, run 1)    : mean {statistics.fmean(latencies):.0f} ms   p50 {_pct(latencies, 0.5):.0f} ms   p95 {_pct(latencies, 0.95):.0f} ms   max {max(latencies):.0f} ms"
        )
    print(
        f"tokens ({len(runs)} runs)          : input {tin}  output {tout}  ({tin / requests:.0f} in/request)"
    )
    if price_in or price_out:
        print(
            f"cost (paid list price)   : ${cost:.5f} total   ${cost / requests:.6f}/request   ${1000 * cost / requests:.3f}/1000 issues"
        )
    else:
        print(
            "cost (paid list price)   : n/a (no price for this model; pass --price-in/--price-out)"
        )
    if stability:
        print(
            f"run-to-run agreement     : kind {stability['kind_agreement']:.1%}  area {stability['area_agreement']:.1%}  gfi {stability['gfi_agreement']:.1%}  (n={stability['pairs']})"
        )

    if args.json_path:
        payload = {
            "engine": label,
            "provider": provider,
            "model": args.model,
            "runs": len(runs),
            "summary": summary,
            "stability": stability,
            "price": {"input_per_mtok": price_in, "output_per_mtok": price_out},
            "totals": {"input_tokens": tin, "output_tokens": tout, "cost_usd": cost},
            "results": runs,
        }
        Path(args.json_path).write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"wrote {args.json_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
