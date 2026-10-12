"""Classify one GitHub issue into ``area/`` and ``kind/`` labels with a single model call.

Why this shape:

* The model may only choose from a fixed allowlist defined in :mod:`tools.triage.taxonomy`
  and must reply with a JSON object. Anything outside the allowlist is dropped, so a
  hallucinated label can never reach the repository. On TypeSafe System One the
  allowlist IS the Choice's options, so the API enforces the same guarantee.
* The classifier never fails the workflow: no API key, a network error, a timeout, or
  malformed output all yield a ``{"action": "skipped"|"failed"}`` result, so the issue
  simply keeps ``status/need-triage``. Fail open, never mislabel.
* The HTTP call is separated from the pure parse/normalise logic so tests never touch
  the network.

Run as ``python -m tools.triage.classify`` with the issue JSON on stdin (or in
``ISSUE_JSON``). Prints exactly one JSON object on stdout:

    {"action": "triaged", "area": [...], "kind": "kind/...", "good_first_issue": bool, ...}
    {"action": "skipped", "reason": "..."}

Always exits 0; the workflow decides what to do with the result.
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass

from tools.triage import taxonomy as tax

# Works with any OpenAI-compatible provider. Resolution:
#   TRIAGE_MODEL      one or more model ids, comma-separated; each entry may be
#                     prefixed `provider:model` to mix providers in a fallback
#                     chain, e.g. "openai:gpt-4.1-mini,gemini-3.8-flash".
#   TRIAGE_PROVIDER   default provider for unprefixed entries (else auto-detected).
#   TRIAGE_BASE_URL   override the default provider's base URL.
#   TRIAGE_API_KEY    override the default provider's key.
#   TRIAGE_TIMEOUT    seconds per call (default 60).
#   TRIAGE_MAX_TOKENS completion budget (default 2048).
# With nothing set, the provider is auto-detected from whichever standard key is
# present (OPENAI_API_KEY, GEMINI_API_KEY/GOOGLE_API_KEY, DEEPSEEK_API_KEY, ...).
DEFAULT_PROVIDER = "gemini"

MAX_AREAS = 2
MAX_BODY_CHARS = 6000
MAX_REASON_CHARS = 280
# Reasoning models (e.g. gemini-3.x-flash) emit thinking tokens before the JSON,
# all counted against the completion budget. Too small a cap truncates the reply
# (finish_reason=length) and the issue is skipped, so leave generous room.
MAX_TOKENS = 2048
_VALID_CONFIDENCE = ("high", "medium", "low")


@dataclass(frozen=True)
class Provider:
    """An OpenAI-compatible endpoint and the env var(s) that hold its key."""

    base_url: str
    default_model: str
    key_envs: tuple[str, ...]


# Mirrors graphify's own backend table where possible, so a key that already works
# for `graphify extract` works here too. Any other OpenAI-compatible gateway
# (LiteLLM, vLLM, Azure, ...) works via TRIAGE_BASE_URL + TRIAGE_API_KEY.
PROVIDERS: dict[str, Provider] = {
    # TypeSafe System One / Jev: typed decisions (choice/noul), not chat. See
    # call_typesafe below. Kept first so a TYPESAFE_API_KEY wins auto-detection.
    "typesafe": Provider(
        "https://api.typesafe.ai", "jev-latest", ("TYPESAFE_API_KEY", "JEV_API_KEY")
    ),
    "openai": Provider("https://api.openai.com/v1", "gpt-4.1-mini", ("OPENAI_API_KEY",)),
    "gemini": Provider(
        "https://generativelanguage.googleapis.com/v1beta/openai/",
        "gemini-3-flash-preview",
        ("GEMINI_API_KEY", "GOOGLE_API_KEY"),
    ),
    "deepseek": Provider("https://api.deepseek.com", "deepseek-v4-flash", ("DEEPSEEK_API_KEY",)),
    "kimi": Provider("https://api.moonshot.ai/v1", "kimi-k2.6", ("MOONSHOT_API_KEY",)),
    "groq": Provider("https://api.groq.com/openai/v1", "llama-3.3-70b-versatile", ("GROQ_API_KEY",)),
    "openrouter": Provider(
        "https://openrouter.ai/api/v1", "openai/gpt-4.1-mini", ("OPENROUTER_API_KEY",)
    ),
    "ollama": Provider("http://localhost:11434/v1", "qwen2.5-coder:7b", ("OLLAMA_API_KEY",)),
}

# Auto-detection order when TRIAGE_PROVIDER is unset. Ollama is excluded: it needs
# no key, so it would otherwise always "win" over a real, keyed provider.
_PROVIDER_ORDER = ("typesafe", "openai", "gemini", "deepseek", "kimi", "groq", "openrouter")

# Back-compat aliases for the single-provider defaults.
DEFAULT_BASE_URL = PROVIDERS[DEFAULT_PROVIDER].base_url
DEFAULT_MODEL = PROVIDERS[DEFAULT_PROVIDER].default_model


@dataclass(frozen=True)
class Config:
    """One resolved candidate model to try (endpoint + model + key)."""

    base_url: str
    model: str
    api_key: str
    timeout: int
    max_tokens: int
    provider: str = ""


def _provider_key(env: dict, name: str) -> str:
    provider = PROVIDERS.get(name)
    if provider is None:
        return ""
    return next((env[key] for key in provider.key_envs if env.get(key)), "")


def detect_provider(env: dict) -> str:
    """The provider for unprefixed models: explicit choice, else the first key present."""
    explicit = (env.get("TRIAGE_PROVIDER") or "").strip().lower()
    if explicit in PROVIDERS:
        return explicit
    return next((name for name in _PROVIDER_ORDER if _provider_key(env, name)), DEFAULT_PROVIDER)


def _split_candidate(entry: str, default_name: str) -> tuple[str, str]:
    """Split ``provider:model`` into (provider, model); unprefixed uses the default."""
    if ":" in entry:
        head, rest = entry.split(":", 1)
        if head.strip().lower() in PROVIDERS:
            return head.strip().lower(), rest.strip()
    return default_name, entry


def _as_int(env: dict, name: str, default: int) -> int:
    try:
        return int(env.get(name) or default)
    except (TypeError, ValueError):
        return default


def load_candidates(env: dict | None = None) -> list[Config]:
    """Resolve the ordered list of models to try. Empty when no key is available."""
    env = os.environ if env is None else env
    timeout = _as_int(env, "TRIAGE_TIMEOUT", 60)
    max_tokens = _as_int(env, "TRIAGE_MAX_TOKENS", MAX_TOKENS)

    default_name = detect_provider(env)
    default_provider = PROVIDERS[default_name]
    default_base = (env.get("TRIAGE_BASE_URL") or default_provider.base_url).rstrip("/")
    default_key = env.get("TRIAGE_API_KEY") or _provider_key(env, default_name)

    raw = env.get("TRIAGE_MODEL") or default_provider.default_model
    candidates: list[Config] = []
    seen: set[tuple[str, str]] = set()
    for entry in (part.strip() for part in raw.split(",")):
        if not entry:
            continue
        name, model = _split_candidate(entry, default_name)
        if not model:
            continue
        if name == default_name:
            base_url, api_key = default_base, default_key
        else:
            base_url = PROVIDERS[name].base_url.rstrip("/")
            api_key = _provider_key(env, name)
        if not api_key:
            continue
        signature = (base_url, model)
        if signature in seen:
            continue
        seen.add(signature)
        candidates.append(
            Config(
                base_url=base_url,
                model=model,
                api_key=api_key,
                timeout=timeout,
                max_tokens=max_tokens,
                provider=name,
            )
        )
    return candidates


def load_config(env: dict | None = None) -> Config | None:
    """The first candidate, or ``None`` when no provider key is configured."""
    candidates = load_candidates(env)
    return candidates[0] if candidates else None


def _slim_issue(issue: object) -> dict:
    """Keep only the fields the prompt needs, and cap the body length."""
    if not isinstance(issue, dict):
        return {}
    raw_labels = issue.get("labels") or []
    names = [
        label.get("name")
        for label in raw_labels
        if isinstance(label, dict) and label.get("name")
    ]
    body = issue.get("body") or ""
    return {
        "number": issue.get("number"),
        "title": str(issue.get("title") or "").strip(),
        "body": str(body)[:MAX_BODY_CHARS],
        "labels": names,
    }


def build_messages(issue: dict) -> list[dict]:
    """The system + user messages sent to the model, allowlist included."""
    areas = "\n".join(f"- {label.name}: {label.description}" for label in tax.AREAS)
    kinds = "\n".join(f"- {label.name}: {label.description}" for label in tax.KINDS)
    system = (
        "You triage GitHub issues for the Graphify repository, a tool that turns "
        "code and docs into a queryable knowledge graph.\n\n"
        "Choose exactly one kind label and one (or two) area labels, only from these "
        "lists. Never invent a label. Use kind/other or area/other when nothing fits; "
        "do not force a match.\n\n"
        f"Allowed kind labels (choose exactly one):\n{kinds}\n\n"
        f"Allowed area labels (choose one, or two only when clearly split):\n{areas}\n\n"
        f"Good-first-issue rule: {tax.GFI_DEFINITION}\n\n"
        "Reply with ONLY a JSON object, no prose and no code fences:\n"
        '{"area": ["area/example"], "kind": "kind/example", '
        '"good_first_issue": false, "gfi_reason": "", "confidence": "low"}'
    )
    existing = ", ".join(issue.get("labels") or []) or "(none)"
    user = (
        f"Issue #{issue.get('number')}\n"
        f"Existing labels: {existing}\n\n"
        f"Title: {issue.get('title') or '(no title)'}\n\n"
        f"Body:\n{issue.get('body') or '(empty)'}"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def _extract_json_object(text: str) -> dict | None:
    """Parse the first JSON object in a model reply, tolerating code fences and prose."""
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped).strip()
    # raw_decode from the first "{" that parses, so a valid object followed by a
    # second object or trailing prose (e.g. an echoed example) still resolves to
    # the first object rather than failing on the whole string.
    decoder = json.JSONDecoder()
    for index, char in enumerate(stripped):
        if char != "{":
            continue
        try:
            parsed, _end = decoder.raw_decode(stripped[index:])
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None


def normalise(raw: dict) -> dict:
    """Force a model reply onto the allowlist. Never raises, never invents a label."""
    if not isinstance(raw, dict):
        raw = {}
    areas = raw.get("area")
    if isinstance(areas, str):
        areas = [areas]
    if not isinstance(areas, list):
        areas = []
    picked: list[str] = []
    for value in areas:
        if isinstance(value, str) and value in tax.MODEL_SELECTABLE_AREA and value not in picked:
            picked.append(value)
    picked = picked[:MAX_AREAS] or ["area/other"]

    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in tax.MODEL_SELECTABLE_KIND:
        kind = "kind/other"

    confidence = raw.get("confidence")
    if confidence not in _VALID_CONFIDENCE:
        confidence = "low"

    return {
        "area": picked,
        "kind": kind,
        "good_first_issue": raw.get("good_first_issue") is True,
        "gfi_reason": str(raw.get("gfi_reason") or "").strip()[:MAX_REASON_CHARS],
        "confidence": confidence,
    }


def parse_reply(text: str) -> dict | None:
    """Turn a model reply into a normalised decision, or ``None`` when unusable."""
    raw = _extract_json_object(text)
    if raw is None:
        return None
    return normalise(raw)


def classify_issue(issue: dict, call_model: Callable[[dict], str]) -> dict | None:
    """Classify ``issue`` via ``call_model``; ``None`` on any failure (caller fails open)."""
    try:
        reply = call_model(issue)
        return parse_reply(reply)
    except Exception:
        # Network, timeout, provider error, or an unexpected shape in the reply:
        # never raise into CI, and never let a malformed reply produce labels.
        return None


def call_model(config: Config, messages: list[dict]) -> str:
    """One OpenAI-compatible chat completion. Raises on any transport/HTTP error."""
    payload = {
        "model": config.model,
        "messages": messages,
        "temperature": 0,
        "max_tokens": config.max_tokens,
    }
    request = urllib.request.Request(
        f"{config.base_url}/chat/completions",
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config.timeout) as response:
        data = json.loads(response.read().decode("utf-8"))
    return data["choices"][0]["message"]["content"]


# --- TypeSafe System One / Jev -------------------------------------------
# Jev is not a chat model: it takes `state` plus typed `questions` and returns
# typed `answers` (choice / noul / score), each with a calibrated confidence.
# The triage maps onto three primitives, so a label can never be invented (the
# options ARE the allowlist) and every answer carries its own confidence:
#   kind           Choice   -> one kind/* option
#   area           Choice   -> one area/* option
#   area_secondary Choice   -> a second area/*, or "none"
#   good_first_issue Noul   -> probability, thresholded in code
# Docs: https://docs.typesafe.ai/api

_TYPESAFE_NONE = "none"
_GFI_THRESHOLD = 0.5


def build_systemone_questions() -> dict:
    """The typed questions sent to Jev, built from the taxonomy allowlist."""
    area_criteria = {label.name: label.description for label in tax.AREAS}
    secondary_criteria = dict(area_criteria)
    secondary_criteria[_TYPESAFE_NONE] = "No clearly involved second area"
    return {
        "kind": {
            "type": "choice",
            "instructions": {
                "question": "What kind of GitHub issue is this?",
                "focus": "Classify what the issue is, not which code it touches.",
            },
            "criteria": {label.name: label.description for label in tax.KINDS},
        },
        "area": {
            "type": "choice",
            "instructions": {
                "question": (
                    "Which area of the Graphify codebase does this issue primarily "
                    "concern?"
                ),
                "focus": "Pick the single closest area; area/other only if none fit.",
            },
            "criteria": area_criteria,
        },
        "area_secondary": {
            "type": "choice",
            "instructions": {
                "question": "Is a second area clearly involved, or none?",
                "focus": "Choose a second area only when the issue clearly spans two.",
            },
            "criteria": secondary_criteria,
        },
        "good_first_issue": {
            "type": "noul",
            "instructions": tax.GFI_DEFINITION,
            "criteria": {
                "true": "A newcomer could finish this without deep repository knowledge.",
                "false": "Too broad, touches invariants, or otherwise not beginner-suitable.",
            },
        },
    }


def call_typesafe(config: Config, issue: dict) -> dict:
    """One System One evaluation. Raises on any transport/HTTP error."""
    body = {
        "model": config.model,
        "state": {
            "issue": {
                "number": issue.get("number"),
                "title": issue.get("title"),
                "body": issue.get("body"),
                "existing_labels": issue.get("labels"),
            }
        },
        "questions": build_systemone_questions(),
    }
    request = urllib.request.Request(
        f"{config.base_url}/v1/systemone",
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=config.timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _choice_of(answer: object) -> str | None:
    if isinstance(answer, dict) and isinstance(answer.get("choice"), str):
        return answer["choice"]
    return None


def _confidence_label(value: object) -> str:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return "low"
    if numeric >= 0.75:
        return "high"
    if numeric >= 0.5:
        return "medium"
    return "low"


def typesafe_decision(response: dict) -> dict | None:
    """Map a System One response onto our decision shape, or None when unusable."""
    answers = response.get("answers") if isinstance(response, dict) else None
    if not isinstance(answers, dict):
        return None

    kind = _choice_of(answers.get("kind"))
    if kind not in tax.MODEL_SELECTABLE_KIND:
        kind = "kind/other"

    areas: list[str] = []
    for key in ("area", "area_secondary"):
        picked = _choice_of(answers.get(key))
        if picked in tax.MODEL_SELECTABLE_AREA and picked not in areas:
            areas.append(picked)
    areas = areas[:MAX_AREAS] or ["area/other"]

    gfi_answer = answers.get("good_first_issue")
    gfi = False
    if isinstance(gfi_answer, dict):
        try:
            gfi = float(gfi_answer.get("noul", 0)) >= _GFI_THRESHOLD
        except (TypeError, ValueError):
            gfi = False

    confidences: list[float] = []
    for key in ("kind", "area"):
        answer = answers.get(key)
        if isinstance(answer, dict):
            try:
                confidences.append(float(answer.get("confidence")))
            except (TypeError, ValueError):
                pass

    return {
        "area": areas,
        "kind": kind,
        "good_first_issue": gfi,
        "gfi_reason": "",
        "confidence": _confidence_label(min(confidences) if confidences else None),
    }


def classify_with_config(issue: dict, config: Config) -> dict | None:
    """Classify with one candidate, dispatching on the provider. None on failure."""
    try:
        if config.provider == "typesafe":
            return typesafe_decision(call_typesafe(config, issue))
        return parse_reply(call_model(config, build_messages(issue)))
    except Exception:
        # Network, timeout, provider error, or an unexpected shape: never raise
        # into CI, never produce labels from a failure.
        return None


def _emit(result: dict) -> None:
    """Print the decision JSON on stdout (the workflow writes it to a file)."""
    json.dump(result, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")


def main() -> int:
    raw = os.environ.get("ISSUE_JSON") or ""
    if not raw and not sys.stdin.isatty():
        raw = sys.stdin.read()
    try:
        issue = _slim_issue(json.loads(raw))
    except (ValueError, TypeError):
        _emit({"action": "skipped", "reason": "unparseable issue payload"})
        return 0

    candidates = load_candidates()
    if not candidates:
        _emit(
            {
                "action": "skipped",
                "reason": (
                    "no provider key (set TRIAGE_API_KEY or a provider key such as "
                    "OPENAI_API_KEY / GEMINI_API_KEY)"
                ),
            }
        )
        return 0

    tried: list[str] = []
    for candidate in candidates:
        tried.append(f"{candidate.provider}:{candidate.model}")
        decision = classify_with_config(issue, candidate)
        if decision is not None:
            _emit(
                {
                    "action": "triaged",
                    "provider": candidate.provider,
                    "model": candidate.model,
                    **decision,
                }
            )
            return 0

    attempted = ", ".join(tried)
    print(f"[triage] all candidate models failed: {attempted}", file=sys.stderr)
    _emit({"action": "skipped", "reason": f"classification failed for: {attempted}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
