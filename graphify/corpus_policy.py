"""One source of truth for corpus advisories and partition decisions.

The detector historically warned at 500,000 words while generated agent skills
partitioned at 2,000,000 words or 500 files. Keeping both decisions here makes
the distinction explicit: an advisory is about expected cost; a partition gate
protects extraction reliability. Counts are words, never model tokens.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass


SMALL_CORPUS_WORDS = 50_000
LARGE_CORPUS_ADVISORY_WORDS = 500_000
PARTITION_WORDS = 2_000_000
PARTITION_FILES = 500


@dataclass(frozen=True)
class CorpusAssessment:
    """Actionable scan policy returned alongside ordinary detection data."""

    total_files: int
    total_words: int
    advisory: bool
    partition_required: bool
    reasons: tuple[str, ...]
    message: str
    existing_graph: bool = False

    def to_dict(self) -> dict:
        """Return a JSON-compatible representation for CLI and skill consumers."""

        payload = asdict(self)
        payload["reasons"] = list(self.reasons)
        return payload


def assess_corpus(
    *,
    total_files: int,
    total_words: int,
    existing_graph: bool = False,
) -> CorpusAssessment:
    """Classify a corpus without conflating fresh extraction with graph query.

    Existing graphs bypass this fresh-build partition policy because querying an
    already materialized graph neither reparses files nor performs semantic
    extraction. A rebuild still calls this function with ``existing_graph=False``.
    """

    files = max(0, int(total_files))
    words = max(0, int(total_words))
    if existing_graph:
        return CorpusAssessment(
            files,
            words,
            advisory=False,
            partition_required=False,
            reasons=(),
            message="Existing graph query: fresh-extraction corpus limits do not apply.",
            existing_graph=True,
        )

    reasons: list[str] = []
    if files > PARTITION_FILES:
        reasons.append("file_count")
    if words > PARTITION_WORDS:
        reasons.append("word_count")
    if reasons:
        dimensions = f"{files:,} files · ~{words:,} words"
        return CorpusAssessment(
            files,
            words,
            advisory=True,
            partition_required=True,
            reasons=tuple(reasons),
            message=(
                f"Large fresh-extraction corpus: {dimensions}. Partition into deterministic "
                "leaves before extraction; query results can be merged into one graph."
            ),
        )

    if words >= LARGE_CORPUS_ADVISORY_WORDS:
        return CorpusAssessment(
            files,
            words,
            advisory=True,
            partition_required=False,
            reasons=("large_but_supported",),
            message=(
                f"Large corpus advisory: {files:,} files · ~{words:,} words. It can be "
                "processed as one graph, but semantic extraction may be expensive."
            ),
        )

    if words < SMALL_CORPUS_WORDS:
        return CorpusAssessment(
            files,
            words,
            advisory=True,
            partition_required=False,
            reasons=("small_corpus",),
            message=(
                f"Corpus is ~{words:,} words and may fit in one context window; a graph is "
                "optional unless structural navigation is the goal."
            ),
        )

    return CorpusAssessment(
        files,
        words,
        advisory=False,
        partition_required=False,
        reasons=(),
        message="Corpus is within the single-graph extraction policy.",
    )
