"""#4432 — the node-ID rule in the prompts contradicted `ids.py` for non-ASCII paths.

The extraction prompt told the model "Node ID format: lowercase, only
``[a-z0-9_]``", but `ids.normalize_id` keeps anything matching a word character
after casefolding, so a Cyrillic or CJK path keeps its letters:

    docs/tz/ЛЗ4_обоснование.md  ->  docs_tz_лз4_обоснование

A model cannot satisfy both halves of that contradiction, so for a non-ASCII
path it improvises a stem per chunk and per run, and `_semantic_id_remap` has
nothing canonical to remap onto. The AST node and the semantic nodes for the
same file then land under different ids.

The invariant this file pins: every prompt that states the node-ID rule must
describe the same character class `ids.py` actually produces. A rule that says
ASCII-only is wrong, because `make_id` provably is not ASCII-only.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from graphify.ids import make_id, normalize_id

REPO_ROOT = Path(__file__).resolve().parents[1]
FRAGMENT_DIR = REPO_ROOT / "tools" / "skillgen" / "fragments" / "references" / "shared"
LLM_PROMPT = REPO_ROOT / "graphify" / "llm.py"

# Every surface that states the rule to a model.
PROMPT_SURFACES = [
    LLM_PROMPT,
    FRAGMENT_DIR / "extraction-spec.md",
    FRAGMENT_DIR / "extraction-spec-compact.md",
]


def _ascii_only_claims(text: str) -> list[str]:
    """Sentences claiming ids are ASCII-only, which `ids.py` contradicts."""
    hits = []
    for line in text.splitlines():
        if "Node ID format" not in line:
            continue
        # The wrong form names the ASCII class without qualifying it.
        if re.search(r"only\s*`?\[a-z0-9_\]`?", line) and "non-ASCII" not in line:
            hits.append(line.strip())
    return hits


@pytest.mark.parametrize("path", PROMPT_SURFACES, ids=lambda p: p.name)
def test_prompt_does_not_claim_ascii_only_ids(path: Path):
    """A prompt must not tell the model to emit only ASCII ids.

    `make_id` keeps Cyrillic/CJK, so an ASCII-only instruction makes the model
    and the AST extractor disagree on the id for the same file.
    """
    assert path.exists(), path
    claims = _ascii_only_claims(path.read_text(encoding="utf-8"))
    assert claims == [], (
        f"{path.name} still tells the model ids are ASCII-only, but make_id keeps "
        f"non-ASCII letters: {claims}"
    )


def test_ids_keep_non_ascii_as_the_prompt_now_describes():
    """The documented behaviour and `make_id` agree on a non-ASCII path."""
    cyrillic = "docs/tz/ЛЗ4_обоснование"
    cjk = "文档/中文名"

    assert make_id(cyrillic) == "docs_tz_лз4_обоснование"
    assert make_id(cjk) == "文档_中文名"

    # The property the prompt now describes: word characters survive, and
    # every run of non-word characters became a single underscore.
    for raw in (cyrillic, cjk):
        result = normalize_id(raw)
        assert re.fullmatch(r"\w+", result), result
        assert result == re.sub(r"[^\w]+", "_", raw.casefold())


def test_ascii_input_is_still_lowercased_ascii():
    """The ASCII half of the rule is unchanged — this is not a relaxation."""
    assert make_id("src/auth/session.py", "ValidateToken") == "src_auth_session_py_validatetoken"
    assert normalize_id("FooBar") == "foobar"
    assert normalize_id("a..b") == "a_b"
