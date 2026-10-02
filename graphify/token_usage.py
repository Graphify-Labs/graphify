"""Honest query token accounting independent of any model provider."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Callable, Sequence


Tokenizer = Callable[[str], Sequence[int]]


@dataclass(frozen=True)
class TextMeasurement:
    tokens: int
    exact: bool
    method: str
    characters: int

    def to_dict(self) -> dict:
        return asdict(self)


def measure_text(text: str, *, tokenizer: Tokenizer | None = None) -> TextMeasurement:
    """Measure with a supplied model tokenizer or label the fallback estimate."""

    if tokenizer is not None:
        return TextMeasurement(len(tokenizer(text)), True, "model_tokenizer", len(text))
    # The fallback is intentionally never described as billable or exact.
    return TextMeasurement(max(1, (len(text) + 3) // 4), False, "character_estimate", len(text))


@dataclass(frozen=True)
class QueryUsage:
    query_tokens: int
    evidence_tokens: int
    token_count_exact: bool
    measurement_method: str
    llm_invoked: bool
    model_input_tokens: int
    model_output_tokens: int
    follow_up_count: int

    @classmethod
    def for_retrieval(
        cls,
        *,
        query: str,
        evidence: str,
        tokenizer: Tokenizer | None = None,
        follow_up_count: int = 0,
    ) -> "QueryUsage":
        query_measurement = measure_text(query, tokenizer=tokenizer)
        evidence_measurement = measure_text(evidence, tokenizer=tokenizer)
        return cls(
            query_tokens=query_measurement.tokens,
            evidence_tokens=evidence_measurement.tokens,
            token_count_exact=query_measurement.exact and evidence_measurement.exact,
            measurement_method=query_measurement.method,
            llm_invoked=False,
            model_input_tokens=0,
            model_output_tokens=0,
            follow_up_count=max(0, int(follow_up_count)),
        )

    def to_dict(self) -> dict:
        return asdict(self)
