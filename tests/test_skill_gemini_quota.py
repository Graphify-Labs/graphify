"""The skill must tell a Gemini free-tier run which quota error is worth
retrying (#2840).

A free-tier key fails with either a per-minute input-token cap, which clears
after a short wait, or a per-day request cap, which does not: each retry spends
another of the day's requests. Without the error strings in the skill, the agent
retries the daily cap with backoff and lower concurrency before giving up. The
skill also says that switching to subagents does not reuse Gemini's cache
entries; the last test pins the fact that makes that statement true.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from graphify.cache import prompt_fingerprint  # noqa: E402
from graphify.llm import _extraction_system  # noqa: E402
from tools.skillgen import gen  # noqa: E402

_GEMINI_CALL = 'extract_corpus_parallel(files, backend="gemini")'


def _gemini_bodies():
    arts = gen.render_all(gen.load_platforms())
    bodies = [a for a in arts if _GEMINI_CALL in a.content]
    assert bodies, "no rendered skill body routes semantic extraction to Gemini"
    return bodies


def test_every_gemini_body_names_both_free_tier_quota_errors():
    for a in _gemini_bodies():
        assert "generate_content_free_tier_input_token_count" in a.content, a.path
        assert "generate_content_free_tier_requests" in a.content, a.path


def test_daily_cap_says_stop_retrying_and_fall_back_to_subagents():
    for a in _gemini_bodies():
        line = next(
            ln for ln in a.content.splitlines()
            if "`generate_content_free_tier_requests`" in ln
        )
        assert "per-day" in line, a.path
        assert "Stop calling `extract_corpus_parallel`" in line, a.path
        assert "subagents" in line, a.path


def test_gemini_and_subagent_prompts_fingerprint_differently():
    # The skill tells the agent that a Gemini -> subagent switch re-extracts the
    # files Gemini finished, because cache entries are keyed by prompt
    # fingerprint. If the two prompts ever fingerprint the same, that sentence
    # becomes false and must be removed.
    spec = REPO_ROOT / "graphify" / "skills" / "claude" / "references" / "extraction-spec.md"
    assert prompt_fingerprint(_extraction_system(deep=False)) != prompt_fingerprint(spec)
