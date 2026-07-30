"""Distribution-level extraction-skill contracts for semantic evidence."""

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
VERBOSE_SPEC = (
    ROOT / "tools/skillgen/fragments/references/shared/extraction-spec.md"
)
COMPACT_SPEC = (
    ROOT / "tools/skillgen/fragments/references/shared/extraction-spec-compact.md"
)
CORE = ROOT / "tools/skillgen/fragments/core/core.md"
MONOLITHS = (
    ROOT / "tools/skillgen/fragments/core/aider.md",
    ROOT / "tools/skillgen/fragments/core/devin.md",
)
OPENCODE_DISPATCH = (
    ROOT / "tools/skillgen/fragments/dispatch/opencode-mention.md"
)
CODEX_DISPATCH = (
    ROOT / "tools/skillgen/fragments/dispatch/codex-agenttask.md"
)

EDGE_VOCABULARY = (
    "calls|implements|references|cites|conceptually_related_to|"
    "shares_data_with|semantically_similar_to|rationale_for"
)
HYPEREDGE_VOCABULARY = "participate_in|implement|form"


def test_shared_extraction_specs_require_closed_relations_and_exact_provenance() -> None:
    for path in (VERBOSE_SPEC, COMPACT_SPEC):
        text = path.read_text(encoding="utf-8")
        assert EDGE_VOCABULARY in text
        assert HYPEREDGE_VOCABULARY in text
        assert "source_location\":null" not in text
        assert "L<start>-L<end>" in text
        assert "B<start>-B<end>" in text
        assert "Missing, null, malformed, stale, or non-resolving provenance" in text
        assert "return only a completion status" in text
        assert "Return the same JSON inline" not in text


def test_split_skill_snapshots_sources_and_uses_the_package_validator() -> None:
    text = CORE.read_text(encoding="utf-8")
    assert "graphify snapshot-sources" in text
    assert ".graphify_semantic_sources.txt" in text
    assert "--source-manifest graphify-out/.graphify_source_manifest.json" in text
    assert "--manifest-sha256" in text
    assert "Do not merge chunks with inline JSON concatenation" in text
    assert "graphify merge-semantic" in text
    assert "rm -f graphify-out/.graphify_chunk_*.json" in text


def test_monolithic_skills_use_the_same_package_owned_validation_seam() -> None:
    for path in MONOLITHS:
        text = path.read_text(encoding="utf-8")
        assert "graphify snapshot-sources" in text
        assert "--source-manifest" in text
        assert "--manifest-sha256" in text
        assert "source_location\":null" not in text
        assert "prompt_file = Path(graphify.__file__).with_name(" in text
        assert text.count("prompt_file=prompt_file") >= 2


def test_opencode_dispatch_requires_chunk_files_and_package_merge() -> None:
    text = OPENCODE_DISPATCH.read_text(encoding="utf-8")
    assert "CHUNK_PATH" in text
    assert "must write" in text
    assert "inline response" in text
    assert "graphify merge-chunks" in text
    assert "Accumulate nodes/edges/hyperedges across all results" not in text


def test_codex_dispatch_requires_distinct_chunk_files_not_inline_json() -> None:
    text = CODEX_DISPATCH.read_text(encoding="utf-8")
    assert "CHUNK_PATH substituted" in text
    assert "inline return is only a completion status" in text
    assert "return the JSON inline" not in text
