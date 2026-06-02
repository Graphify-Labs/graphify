"""Tests for the tools/skillgen generator and the claude lean-core split.

skillgen renders graphify's committed skill artifacts from human-edited
fragments. These tests lock in the anti-drift guards (``--check``,
``--audit-coverage``), the render idempotency, and the lean-core invariant: the
core runs a default extraction with zero reference reads, on-demand content
lives only in the references, and no reference duplicates core content.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# tests/ -> repo root is one parent up; put it on the path so tools.skillgen
# imports regardless of pytest's import mode.
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools.skillgen import gen  # noqa: E402


def test_audit_coverage_passes():
    """Every v8 heading lands in the lean core or exactly one reference."""
    platforms = gen.load_platforms()
    problems = gen.audit_coverage(platforms["claude"])
    assert problems == [], "\n".join(problems)


def test_check_passes():
    """The committed artifacts and the expected/ snapshot match a fresh render.

    This is the CI / pre-commit drift guard. A failure here means someone
    hand-edited a generated file or forgot to re-run the generator.
    """
    platforms = gen.load_platforms()
    artifacts = gen.render_all(platforms, only="claude")
    problems = gen.check(artifacts)
    assert problems == [], "\n".join(problems)


def test_render_is_idempotent():
    """Rendering twice yields byte-identical output (no timestamps/versions)."""
    platforms = gen.load_platforms()
    first = gen.render_all(platforms, only="claude")
    second = gen.render_all(platforms, only="claude")
    assert [(a.path, a.content) for a in first] == [(a.path, a.content) for a in second]


def test_render_output_is_lf_only():
    """Generated artifacts use LF newlines and end in exactly one newline."""
    platforms = gen.load_platforms()
    for art in gen.render_all(platforms, only="claude"):
        assert "\r" not in art.content, art.path
        assert art.content.endswith("\n"), art.path
        assert not art.content.endswith("\n\n"), art.path


def test_no_version_or_timestamp_in_output():
    """No generated artifact carries the package version string."""
    from graphify.__main__ import __version__

    platforms = gen.load_platforms()
    for art in gen.render_all(platforms, only="claude"):
        assert __version__ not in art.content, f"{art.path} leaked a version string"


def _claude_artifacts():
    platforms = gen.load_platforms()
    arts = gen.render_all(platforms, only="claude")
    core = next(a for a in arts if a.path == "graphify/skill.md")
    refs = {a.path.rsplit("/", 1)[-1]: a.content for a in arts if a.path != "graphify/skill.md"}
    return core.content, refs


def test_lean_core_has_no_reference_only_content():
    """The core must not inline the execution detail of an on-demand reference.

    The ``## Usage`` flag table in the core deliberately lists every command,
    including the on-demand ones (it is the --help payload), so the markers
    below are execution-detail lines that never appear in that table.
    """
    core, _ = _claude_artifacts()
    # The full embedded subagent prompt lives only in extraction-spec.md.
    assert '"file_type":"code|document|paper|image|rationale|concept"' not in core
    # The incremental-update merge machinery lives only in update.md.
    assert "from graphify.build import build_merge" not in core
    assert "graphify cluster-only ." not in core
    # The vocab-expansion query flow lives only in query.md.
    assert "Constrained query expansion" not in core
    assert "save-result --question" not in core
    # The export commands live only in exports.md.
    assert "graphify export wiki" not in core
    assert "graphify export neo4j" not in core
    # The add / watch / hook flows live only in their references.
    assert "from graphify.ingest import ingest" not in core
    assert "graphify hook install" not in core
    assert "python3 -m graphify.watch" not in core


def test_lean_core_runs_default_pipeline_with_zero_references():
    """The default code-corpus run must be fully described inside the core."""
    core, _ = _claude_artifacts()
    # The whole default pipeline (detect -> AST -> build -> label -> HTML ->
    # report) must be present in the core so a plain run reads no reference.
    for needed in (
        "### Step 1 - Ensure graphify is installed",
        "### Step 2 - Detect files",
        "### Step 3 - Extract entities and relationships",
        "#### Part A - Structural extraction for code files",
        "#### Part C - Merge AST + semantic into final extraction",
        "### Step 4 - Build graph, cluster, analyze, generate outputs",
        "### Step 5 - Label communities",
        "### Step 6 - Generate Obsidian vault (opt-in) + HTML",
        "### Step 9 - Save manifest, update cost tracker, clean up, and report",
        "## Honesty Rules",
        "graphify export html",
    ):
        assert needed in core, f"lean core is missing default-pipeline content: {needed!r}"


def test_references_contain_no_core_pipeline_content():
    """No reference fragment may duplicate the core build pipeline."""
    _, refs = _claude_artifacts()
    # Distinctive lines from the core build/label steps must not appear in any
    # reference, or the same content would be double-homed.
    core_only_markers = (
        "from graphify.cluster import cluster, score_all",
        "### Step 4 - Build graph, cluster, analyze, generate outputs",
        "### Step 5 - Label communities",
        "## Honesty Rules",
    )
    for name, body in refs.items():
        for marker in core_only_markers:
            assert marker not in body, f"reference {name} leaked core content: {marker!r}"


def test_reference_pointers_in_core_resolve_to_real_fragments():
    """Every references/<name>.md the core points at is actually rendered."""
    import re

    core, refs = _claude_artifacts()
    pointed = set(re.findall(r"references/([\w-]+)\.md", core))
    rendered = {name[: -len(".md")] for name in refs}
    missing = pointed - rendered
    assert not missing, f"core points at references that were not rendered: {missing}"


def test_query_heading_is_homed_in_core_stub_only():
    """The query section heading is the lean-core stub; query.md re-homes the rest."""
    core, refs = _claude_artifacts()
    core_headings = set(gen.headings(core))
    query_headings = set(gen.headings(refs["query.md"]))
    assert "## For /graphify query" in core_headings
    assert "## For /graphify query" not in query_headings
    # The deeper query content moved into the reference.
    assert "## For /graphify path" in query_headings
    assert "## For /graphify explain" in query_headings
    assert "## For /graphify path" not in core_headings


def test_eight_references_render_for_claude():
    """claude renders exactly the eight on-demand fragments from the design."""
    _, refs = _claude_artifacts()
    assert sorted(refs) == [
        "add-watch.md",
        "exports.md",
        "extraction-spec.md",
        "github-and-merge.md",
        "hooks.md",
        "query.md",
        "transcribe.md",
        "update.md",
    ]


def test_headings_helper_ignores_code_fence_comments():
    """The fence-aware heading scanner must skip '#' lines inside code fences."""
    md = (
        "# Real Heading\n"
        "\n"
        "```bash\n"
        "# not a heading, a shell comment\n"
        "echo hi\n"
        "```\n"
        "\n"
        "## Another Real One\n"
    )
    assert gen.headings(md) == ["# Real Heading", "## Another Real One"]


def test_enum_is_full_six_value_superset_in_extraction_spec():
    """Decision A: the file_type enum is the full six-value superset."""
    _, refs = _claude_artifacts()
    spec = refs["extraction-spec.md"]
    assert "`code`, `document`, `paper`, `image`, `rationale`, `concept`" in spec
    assert '"file_type":"code|document|paper|image|rationale|concept"' in spec


# --- codex + windows (the divergent split hosts) -------------------------------


def _platform_artifacts(key):
    platforms = gen.load_platforms()
    arts = gen.render_all(platforms, only=key)
    skill_dst = platforms[key].skill_dst
    core = next(a for a in arts if a.path == skill_dst)
    refs = {a.path.rsplit("/", 1)[-1]: a.content for a in arts if a.path != skill_dst}
    return core.content, refs


def test_check_passes_for_codex_and_windows():
    """The committed codex/windows artifacts match a fresh render and expected/."""
    platforms = gen.load_platforms()
    for key in ("codex", "windows"):
        artifacts = gen.render_all(platforms, only=key)
        problems = gen.check(artifacts)
        assert problems == [], f"[{key}]\n" + "\n".join(problems)


def test_audit_coverage_passes_for_codex_and_windows():
    """Every v8 heading single-homes for the cli-inline split hosts too."""
    platforms = gen.load_platforms()
    for key in ("codex", "windows"):
        problems = gen.audit_coverage(platforms[key])
        assert problems == [], f"[{key}]\n" + "\n".join(problems)


def test_descriptions_are_preserved_verbatim():
    """Each platform keeps its own v8 frontmatter description, never unified."""
    core_claude, _ = _platform_artifacts("claude")
    core_codex, _ = _platform_artifacts("codex")
    core_windows, _ = _platform_artifacts("windows")
    # claude keeps its own wording; codex/windows share the v8 progressive-host
    # wording. They are NOT unified to one description in this stage.
    assert "treat the question as a /graphify query." in core_claude
    assert "Provides persistent graph with god nodes" in core_codex
    assert "Provides persistent graph with god nodes" in core_windows
    assert "treat the question as a /graphify query." not in core_codex


def test_windows_frontmatter_name_and_shell_and_extra():
    """windows: graphify-windows name, powershell install, troubleshooting tail."""
    core, _ = _platform_artifacts("windows")
    assert core.startswith("---\nname: graphify-windows\n")
    assert "```powershell" in core
    assert "function Find-GraphifyPython" in core
    assert "## Troubleshooting" in core
    assert "### PowerShell 5.1: Vertical scrolling stops working" in core
    # The troubleshooting section sits before Honesty Rules, single separator.
    assert "\n4. **Skip graspologic**" in core
    assert core.index("## Troubleshooting") < core.index("## Honesty Rules")


def test_codex_dispatch_is_agenttask_and_collects_in_memory():
    """codex: spawn/wait/close_agent dispatch needing multi_agent = true."""
    core, _ = _platform_artifacts("codex")
    assert "spawn_agent" in core
    assert "wait_agent" in core
    assert "close_agent" in core
    assert "multi_agent = true" in core
    assert "Codex collects in memory" in core
    # The B2 dispatch slot itself (Codex heading -> Step B3) must not carry the
    # claude Agent-tool example. The shared Step B3 prose mentions the agent type
    # in a re-run hint, so scope the check to the dispatch block only.
    b2 = core[core.index("**Step B2"):core.index("**Step B3")]
    assert "Concrete example for 3 chunks" not in b2
    assert "Agent tool call 1" not in b2


def test_codex_and_windows_unify_enum_to_six_values():
    """codex (was 4-value) and windows (was 5-value) now carry the superset."""
    for key in ("codex", "windows"):
        _, refs = _platform_artifacts(key)
        spec = refs["extraction-spec.md"]
        assert "`code`, `document`, `paper`, `image`, `rationale`, `concept`" in spec
        assert '"file_type":"code|document|paper|image|rationale|concept"' in spec
        # No legacy 4-value enum survives anywhere in the rendered bundle.
        for body in refs.values():
            assert '"file_type":"code|document|paper|image"' not in body


def test_codex_uses_compact_extraction_windows_uses_verbose():
    """The extraction variant differs: codex compact, windows verbose."""
    _, codex_refs = _platform_artifacts("codex")
    _, windows_refs = _platform_artifacts("windows")
    assert "(compact)" in codex_refs["extraction-spec.md"]
    assert "(compact)" not in windows_refs["extraction-spec.md"]


def test_cli_inline_query_stub_has_no_vocab_expansion():
    """cli-inline hosts get the NetworkX-fallback stub, not vocab-expansion."""
    for key in ("codex", "windows"):
        core, refs = _platform_artifacts(key)
        # The core stub points at the query reference without the vocab step.
        assert "expand the question against the graph's own vocabulary" not in core
        assert "NetworkX traversal" in core
        # The query reference carries the path/explain headings but not the
        # claude-only vocab-expansion sub-headings.
        q = refs["query.md"]
        assert "## For /graphify path" in q
        assert "## For /graphify explain" in q
        assert "Constrained query expansion" not in q


def test_schema_singleton_passes_across_all_platforms():
    """The file_type enum is the six-value superset in every rendered artifact."""
    platforms = gen.load_platforms()
    problems = gen.schema_singleton(platforms)
    assert problems == [], "\n".join(problems)


def test_schema_singleton_catches_legacy_enums():
    """The guard's line scanner flags 4- and 5-value pipe enums, not the superset."""
    four = 'file_type":"code|document|paper|image"'
    five = 'file_type":"code|document|paper|image|rationale"'
    superset = '"file_type":"code|document|paper|image|rationale|concept"'
    assert gen.legacy_enum_lines(four) == [four]
    assert gen.legacy_enum_lines(five) == [five]
    # The full six-value superset is never flagged.
    assert gen.legacy_enum_lines(superset) == []
    assert gen.legacy_enum_lines("no enum here") == []
