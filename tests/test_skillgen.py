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


def test_extraction_states_no_api_key_required_for_every_host():
    """Regression for #1461: every skill body that describes Step 3 extraction must
    state up front that no API key is required, tell the agent never to prompt for or
    block on one, and give a terminal-only (non-subagent) fallback.

    Hermes (and the other AGENTS.md hosts) run the CLI directly and can't dispatch
    subagents; the old text framed the no-key path only as 'dispatch subagents as
    written', so those agents looped for minutes insisting on a missing API key.
    """
    platforms = gen.load_platforms()
    arts = gen.render_all(platforms)
    bodies = [a for a in arts
              if "### Step 3 - Extract entities and relationships" in a.content]
    assert bodies, "no rendered skill body contains the Step 3 extraction section"
    for a in bodies:
        assert "graphify needs no API key" in a.content, a.path
        assert "Never ask the user for one, and never block on one." in a.content, a.path
        # the no-key fallback must not be framed *only* around subagent dispatch
        assert "cannot dispatch subagents" in a.content, a.path
        # where a host prints the GEMINI key tip, the clarity must precede it (be
        # hoisted) rather than sit buried after the key check (aider/devin print no
        # tip — they are the model themselves — so the check only applies if present)
        tip = "Tip: set `GEMINI_API_KEY`"
        if tip in a.content:
            assert a.content.index("graphify needs no API key") < a.content.index(tip), \
                f"{a.path}: no-key clarity is not hoisted above the GEMINI tip"


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


UNIFIED_DESCRIPTION = (
    "Use for any question about a codebase, its architecture, file relationships, "
    "or project content — especially when graphify-out/ exists, where the question "
    "should be treated as a graphify query first. Turns any input (code, docs, "
    "papers, images, videos) into a persistent knowledge graph with god nodes, "
    "community detection, and query/path/explain tools."
)


def test_descriptions_are_unified():
    """Every platform now carries one unified frontmatter description, byte for byte.

    The two drifted v8 descriptions (claude's short one and the richer 14-host
    line) were collapsed into a single discovery-tuned line that leads with the
    use-condition. Every split host and both monoliths must carry it verbatim,
    and none of the old wording may survive.
    """
    expected_line = f'description: "{UNIFIED_DESCRIPTION}"'
    platforms = gen.load_platforms()
    for key, p in platforms.items():
        body = gen.render(p)[0].content
        assert expected_line in body, f"[{key}] missing the unified description line"
        # None of the drifted v8 wording may survive on any platform.
        assert "Provides persistent graph with god nodes" not in body, f"[{key}] kept old wording"
        assert "treat the question as a /graphify query." not in body, f"[{key}] kept old wording"
        assert "clustered communities" not in body, f"[{key}] kept old wording"


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


def test_every_platform_query_has_expansion_and_fallback():
    """#1325: the unified query reference ships BOTH the vocab-expansion step and
    the inline NetworkX fallback to every platform (previously split so no host
    got both — Claude had expansion but no fallback; the rest the reverse)."""
    for key in ("claude", "codex", "windows", "opencode"):
        core, refs = _platform_artifacts(key)
        # Core stub mentions both the vocab-expansion step and the inline fallback.
        assert "expand the question against the graph's own vocabulary" in core
        assert "NetworkX traversal" in core
        # The query reference carries expansion, fallback, and path/explain.
        q = refs["query.md"]
        assert "Constrained query expansion" in q
        assert "If the CLI is unavailable" in q
        assert "## For /graphify path" in q
        assert "## For /graphify explain" in q


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


# --- the remaining progressive hosts -------------------------------------------

_PROGRESSIVE_HOSTS = (
    "opencode",
    "kilo",
    "copilot",
    "claw",
    "droid",
    "amp",
    "trae",
    "kiro",
    "pi",
    "vscode",
)


def test_all_progressive_hosts_check_and_audit_clean():
    """check + audit-coverage pass for every rendered progressive host."""
    platforms = gen.load_platforms()
    for key in _PROGRESSIVE_HOSTS:
        arts = gen.render_all(platforms, only=key)
        assert gen.check(arts) == [], f"[{key}] check\n" + "\n".join(gen.check(arts))
        probs = gen.audit_coverage(platforms[key])
        assert probs == [], f"[{key}] audit\n" + "\n".join(probs)


def test_no_host_has_trigger_in_frontmatter():
    """No split host emits a trigger: field — not part of Agent Skills spec (#1180)."""
    for key in ("claude", "codex", "opencode", "kilo", "copilot", "claw", "droid",
                "amp", "trae", "vscode", "kiro", "pi"):
        core, _ = _platform_artifacts(key)
        head = core.split("---", 2)[1]
        assert "trigger:" not in head, f"[{key}] unexpectedly has a trigger: line"


def test_kilo_renders_its_rules_tail_section():
    """kilo gets the Kilo-specific rules tail before Honesty Rules."""
    core, _ = _platform_artifacts("kilo")
    assert "## Kilo-specific rules" in core
    assert core.index("## Kilo-specific rules") < core.index("## Honesty Rules")


def test_dispatch_variants_are_host_specific():
    """Each dispatch variant lands in the right host's B2 slot."""
    expect = {
        "opencode": "@mention",
        "droid": "Task(description=",
        "amp": "Task(description=",
        "trae": "Task(description=",
        "vscode": "paste each response back",
    }
    for key, marker in expect.items():
        core, _ = _platform_artifacts(key)
        b2 = core[core.index("**Step B2"):core.index("**Step B3")]
        assert marker.lower() in b2.lower(), f"[{key}] dispatch slot missing {marker!r}"


def test_compact_extraction_hosts_use_the_compact_spec():
    """kiro, pi, claw use the compact extraction body; the rest use verbose."""
    for key in ("kiro", "pi", "claw"):
        _, refs = _platform_artifacts(key)
        assert "(compact)" in refs["extraction-spec.md"], f"[{key}] not compact"
    for key in ("opencode", "kilo", "copilot", "droid", "amp", "trae", "vscode"):
        _, refs = _platform_artifacts(key)
        assert "(compact)" not in refs["extraction-spec.md"], f"[{key}] should be verbose"


def test_every_split_host_renders_eight_references():
    """All twelve split hosts render exactly the eight on-demand references."""
    platforms = gen.load_platforms()
    expected = [
        "add-watch.md",
        "exports.md",
        "extraction-spec.md",
        "github-and-merge.md",
        "hooks.md",
        "query.md",
        "transcribe.md",
        "update.md",
    ]
    for key, p in platforms.items():
        if p.bucket != "split":
            continue
        _, refs = _platform_artifacts(key)
        assert sorted(refs) == expected, f"[{key}] reference set drift: {sorted(refs)}"


# --- the aider + devin monoliths -----------------------------------------------


def test_monoliths_render_inline_single_file_no_references():
    """aider and devin render one inline body, no split and no references dir."""
    platforms = gen.load_platforms()
    for key in ("aider", "devin"):
        assert platforms[key].bucket == "monolith"
        arts = gen.render(platforms[key])
        assert len(arts) == 1, f"[{key}] monolith should render exactly one file"
        assert arts[0].path == f"graphify/skill-{key}.md"
        assert "references/" not in arts[0].content or "see `references/" not in arts[0].content.lower()


def test_monolith_roundtrip_passes_for_aider_and_devin():
    """Each monolith is diff-clean vs v8 except the file_type enum unification."""
    platforms = gen.load_platforms()
    for key in ("aider", "devin"):
        problems = gen.monolith_roundtrip(platforms[key])
        assert problems == [], f"[{key}]\n" + "\n".join(problems)


def test_monoliths_change_only_sanctioned_lines():
    """Every line that differs from pristine v8 is a sanctioned change-class.

    The round-trip (multiset diff vs the pinned v8 blob) must come back clean:
    each added/removed line matches one of the documented sanctioned predicates
    in gen — the enum unification, the unified description, the chunk-cleanup
    rewrite (#1172), and the four #1392 runbook fixes. Anything else is drift.
    """
    platforms = gen.load_platforms()
    for key in ("aider", "devin"):
        assert gen.monolith_roundtrip(platforms[key]) == []
        # The six-value superset replaced the five-value enum in both files.
        rendered = gen.render(platforms[key])[0].content
        assert gen.ENUM_VALUES in rendered
        assert UNIFIED_DESCRIPTION in rendered


def test_monoliths_carry_the_1392_runbook_fixes():
    """The four #1392 data-loss/correctness fixes are present in both monoliths.

    The round-trip allows these change-classes; this test asserts they are
    actually applied, so a regression that drops a fix fails here even though the
    round-trip (which only forbids *unsanctioned* drift) would still pass.
    """
    platforms = gen.load_platforms()
    for key in ("aider", "devin"):
        body = gen.render(platforms[key])[0].content

        # #6/#7 directed propagation: no bare build_from_json call survives, and
        # the IS_DIRECTED substitution instruction is present.
        assert "directed=IS_DIRECTED" in body
        assert "build_from_json(extraction)" not in body
        assert "Substitute it everywhere it appears" in body

        # #10 content-only semantic scope: code is no longer flattened in.
        assert "for cat in ('document', 'paper', 'image')" in body
        assert "detect['files'].values()" not in body

        # #12 stale-cache unlink on a miss.
        assert ".graphify_cached.json').unlink(missing_ok=True)" in body

        # #18/#20 zero-node guard before any write, report/analysis gated on
        # to_json's return.
        lines = body.splitlines()
        build_i = next(i for i, l in enumerate(lines) if "G = build_from_json(extraction, directed=IS_DIRECTED)" in l)
        guard_i = next(i for i, l in enumerate(lines[build_i:], build_i) if "number_of_nodes() == 0" in l)
        report_i = next(i for i, l in enumerate(lines[build_i:], build_i) if "GRAPH_REPORT.md').write_text(report)" in l)
        wrote_i = next(i for i, l in enumerate(lines[build_i:], build_i) if l.strip().startswith("wrote = to_json("))
        # guard fires right after the build, before the graph/report are written.
        assert build_i < guard_i < wrote_i < report_i, f"[{key}] Step 4 ordering not fixed"
        assert "if not wrote:" in body


def test_generated_runbooks_pass_root_to_save_manifest():
    """#1417: every save_manifest call in a shipped runbook threads root=.

    Without root=, save_manifest stores absolute path keys, so a clone or move
    breaks --update (every cached file misses and the whole corpus re-extracts).
    The full-build (skill.md / monoliths) and the --update reference all relativize
    the manifest to the scan root via root='INPUT_PATH'. This guards the actual
    shipped artifacts; --check keeps them in sync with the fragments.
    """
    targets = [
        REPO_ROOT / "graphify" / "skill.md",
        REPO_ROOT / "graphify" / "skill-aider.md",
        REPO_ROOT / "graphify" / "skill-devin.md",
    ]
    targets += sorted((REPO_ROOT / "graphify" / "skills").glob("*/references/update.md"))
    checked = 0
    for path in targets:
        for ln in path.read_text(encoding="utf-8").splitlines():
            if "save_manifest(" in ln and "import" not in ln:
                checked += 1
                assert "root=" in ln, (
                    f"{path.relative_to(REPO_ROOT)}: save_manifest without root= (#1417): {ln.strip()!r}"
                )
    assert checked >= 4, f"expected save_manifest calls across the runbooks, found {checked}"


def test_devin_keeps_its_multi_field_frontmatter():
    """devin renders inline, so its 4+-field frontmatter is preserved verbatim."""
    platforms = gen.load_platforms()
    body = gen.render(platforms["devin"])[0].content
    head = body.split("---", 2)[1]
    assert "argument-hint:" in head
    assert "model:" in head
    assert "allowed-tools:" in head


# --- the always-on instruction blocks (D2-a) -----------------------------------


def test_always_on_renders_six_blocks():
    """render_always_on yields exactly the six always-on instruction files."""
    arts = gen.render_always_on()
    paths = sorted(a.path for a in arts)
    assert paths == [
        "graphify/always_on/agents-md.md",
        "graphify/always_on/antigravity-rules.md",
        "graphify/always_on/claude-md.md",
        "graphify/always_on/gemini-md.md",
        "graphify/always_on/kiro-steering.md",
        "graphify/always_on/vscode-instructions.md",
    ]


def test_always_on_included_in_full_render_not_per_platform():
    """A full render carries the always-on files; a --platform render does not."""
    platforms = gen.load_platforms()
    full = {a.path for a in gen.render_all(platforms)}
    claude_only = {a.path for a in gen.render_all(platforms, only="claude")}
    assert "graphify/always_on/claude-md.md" in full
    assert "graphify/always_on/claude-md.md" not in claude_only


def test_always_on_roundtrip_is_byte_faithful():
    """Each always_on/*.md reproduces its former __main__.py constant byte for byte.

    This is the load-bearing fidelity check behind the D2-a extraction: the
    install-string / issue-#580 tests still import the constants from
    graphify.__main__, so the packaged markdown must round-trip exactly or those
    contracts silently change.
    """
    problems = gen.always_on_roundtrip()
    assert problems == [], "\n".join(problems)


def test_extracted_constants_equal_the_packaged_always_on_files():
    """The live module constants now equal the packaged files they read at load."""
    from graphify import __main__ as mainmod

    pairs = {
        "_CLAUDE_MD_SECTION": "claude-md",
        "_AGENTS_MD_SECTION": "agents-md",
        "_GEMINI_MD_SECTION": "gemini-md",
        "_VSCODE_INSTRUCTIONS_SECTION": "vscode-instructions",
        "_ANTIGRAVITY_RULES": "antigravity-rules",
        "_KIRO_STEERING": "kiro-steering",
    }
    pkg = Path(mainmod.__file__).parent
    for const_name, basename in pairs.items():
        on_disk = (pkg / "always_on" / f"{basename}.md").read_text(encoding="utf-8")
        assert getattr(mainmod, const_name) == on_disk, const_name


def test_always_on_files_are_guarded_by_check(tmp_path):
    """A hand-edit of an always_on/*.md is caught by --check (the drift guard)."""
    platforms = gen.load_platforms()
    arts = gen.render_all(platforms)
    # The committed + expected/ snapshots match a fresh render.
    assert gen.check(arts) == [], "\n".join(gen.check(arts))
    # A mutated artifact is flagged.
    mutated = [
        gen.RenderedArtifact(a.path, a.content + "drift\n")
        if a.path == "graphify/always_on/claude-md.md"
        else a
        for a in arts
    ]
    problems = gen.check(mutated)
    assert any("always_on/claude-md.md" in p for p in problems)


# --- the per-host coverage audit (the systemic guard) --------------------------


def test_audit_coverage_passes_for_every_split_host():
    """Every split host's render single-homes its own v8 body's headings."""
    platforms = gen.load_platforms()
    for key, p in platforms.items():
        if p.bucket != "split":
            continue
        problems = gen.audit_coverage(p)
        assert problems == [], f"[{key}]\n" + "\n".join(problems)


def test_audit_reads_each_host_against_its_own_v8_body():
    """The audit baseline is the host's OWN v8 skill body, not claude's monolith.

    This is the structural fix: a per-host body, so a drop on one host surfaces.
    """
    assert gen._v8_baseline_ref("claude") == "47042beb05d1f6dd2186c0c499ae2840ce604ead:graphify/skill.md"
    assert gen._v8_baseline_ref("trae") == "47042beb05d1f6dd2186c0c499ae2840ce604ead:graphify/skill-trae.md"
    assert gen._v8_baseline_ref("vscode") == "47042beb05d1f6dd2186c0c499ae2840ce604ead:graphify/skill-vscode.md"


def test_audit_catches_an_induced_per_host_drop():
    """Re-inducing the trae regression (claude-flavored hooks) fails the audit.

    Pointing trae back at the shared CLAUDE.md hooks body drops the
    '## For native AGENTS.md integration (Trae)' heading from its render. The
    per-host audit must catch that against trae's own v8 body. The old audit
    (every host vs claude's monolith) could not see it, because claude's monolith
    never had that heading.
    """
    import dataclasses

    platforms = gen.load_platforms()
    regressed = dataclasses.replace(platforms["trae"], hooks_variant="claude-md")
    problems = gen.audit_coverage(regressed)
    assert any("native AGENTS.md integration (Trae)" in p for p in problems), problems


def test_audit_catches_a_dropped_non_allowlisted_heading():
    """A core fragment that drops a real v8 heading fails the audit.

    Guards that the audit is not a rubber stamp: a host whose v8 has a heading
    that is neither allowlisted nor present anywhere in the render must fail.
    """
    platforms = gen.load_platforms()
    trae = platforms["trae"]
    real_arts = gen.render(trae)
    # Drop the Honesty Rules heading from the rendered core to simulate a real
    # content loss, then re-run the single-home check by hand against trae's v8.
    v8_headings = gen.headings(gen._git_show(gen._v8_baseline_ref("trae")))
    assert "## Honesty Rules" in v8_headings
    by_path = {a.path: a.content for a in real_arts}
    core_no_honesty = by_path[trae.skill_dst].replace("## Honesty Rules", "## Closing notes")
    core_headings = set(gen.headings(core_no_honesty))
    allowlist = gen._audit_allowlist("trae")
    homes = [h for h in v8_headings if h == "## Honesty Rules" and h in core_headings]
    assert "## Honesty Rules" not in allowlist
    assert homes == [], "a dropped, non-allowlisted heading should have no home"


def test_git_show_validators_skip_cleanly_without_origin_v8(monkeypatch, tmp_path, capsys):
    """On a shallow checkout (no origin/v8) the validators skip with exit 0.

    CI sets fetch-depth: 0 so they run for real; this guards the fallback so a
    shallow clone gets a clear message instead of a crash.
    """
    import subprocess as sp

    repo = tmp_path / "shallow"
    repo.mkdir()
    sp.run(["git", "init", "-q", str(repo)], check=True)
    monkeypatch.setattr(gen, "REPO_ROOT", repo)
    assert gen._v8_available() is False
    for flag in ("--audit-coverage", "--monolith-roundtrip", "--always-on-roundtrip"):
        assert gen.main([flag]) == 0
    out = capsys.readouterr()
    assert "SKIPPED" in out.err
    assert "fetch-depth: 0" in out.err


def test_audit_allowlist_documents_only_consolidations():
    """The allowlist holds only the wave-2/3 consolidations, nothing genuine.

    A genuine drop (trae's native AGENTS.md integration) must never be in the
    allowlist, or the guard would rubber-stamp the regression it exists to catch.
    """
    all_allowlisted = set(gen.SHARED_INTRO_ALLOWLIST)
    for hs in gen._CONSOLIDATION_ALLOWLIST.values():
        all_allowlisted |= set(hs)
    assert "## For native AGENTS.md integration (Trae)" not in all_allowlisted
    # Only the two minimal-body hosts carry per-host consolidations.
    assert set(gen._CONSOLIDATION_ALLOWLIST) == {"kilo", "vscode"}


# --- the trae / trae-cn native AGENTS.md integration fix -----------------------


def test_trae_renders_native_agents_md_integration_not_claude():
    """trae wires `graphify trae install` -> AGENTS.md, never `graphify claude install`."""
    core, refs = _platform_artifacts("trae")
    hooks = refs["hooks.md"]
    # The hooks reference carries the v8 native AGENTS.md integration section.
    assert "## For native AGENTS.md integration (Trae)" in hooks
    assert "graphify trae install" in hooks
    assert "graphify trae-cn install" in hooks
    assert "writes a `## graphify` section to the local `AGENTS.md`" in hooks
    # The claude-flavored install command must NOT appear for trae.
    assert "graphify claude install" not in hooks
    assert "native CLAUDE.md integration" not in hooks
    # The lean-core pointer names AGENTS.md, not CLAUDE.md.
    assert "## For the commit hook and native AGENTS.md integration" in core
    assert "wire graphify into a project's AGENTS.md" in core
    assert "native CLAUDE.md integration" not in core


def test_trae_dispatch_carries_the_no_pretooluse_caveat():
    """trae's B2 dispatch block restores the v8 no-PreToolUse-hook caveat."""
    core, _ = _platform_artifacts("trae")
    b2 = core[core.index("**Step B2"):core.index("Pass the extraction prompt")]
    assert "Trae does NOT support PreToolUse hooks" in b2
    assert "AGENTS.md rules are the always-on mechanism instead" in b2


def test_trae_hooks_reference_includes_the_pretooluse_note():
    """The trae hooks reference keeps the v8 PreToolUse note in full."""
    _, refs = _platform_artifacts("trae")
    hooks = refs["hooks.md"]
    assert "Unlike Claude Code, Trae does NOT support PreToolUse hooks" in hooks
    assert "Run `/graphify --update` manually after code changes" in hooks


def test_claude_flavored_hosts_keep_their_hooks_text_unchanged():
    """Hosts whose v8 shipped the claude-flavored hooks keep it (faithful to them).

    droid's v8 dispatch never had the Trae caveat and its hooks section names
    CLAUDE.md; restoring trae must not bleed into droid or any other host.
    """
    for key in ("claude", "droid", "codex", "windows", "kilo", "vscode"):
        core, refs = _platform_artifacts(key)
        hooks = refs["hooks.md"]
        assert "graphify claude install" in hooks, f"[{key}] lost the claude install command"
        assert "native CLAUDE.md integration" in hooks, f"[{key}] lost the CLAUDE.md heading"
        assert "Trae does NOT support PreToolUse hooks" not in core, f"[{key}] leaked the trae caveat"
        assert "Trae does NOT support PreToolUse hooks" not in hooks, f"[{key}] leaked the trae caveat"
        assert "## For the commit hook and native CLAUDE.md integration" in core, f"[{key}] pointer drifted"


# --- the amp native AGENTS.md integration (the 13th split host) ----------------


def test_amp_renders_native_agents_md_integration_v8_faithfully():
    """amp wires `graphify amp install` -> AGENTS.md exactly as its v8 body had it.

    amp shares the agents-md hooks variant with trae but renders its OWN wording:
    a bare "## For native AGENTS.md integration" heading (no "(Trae)" suffix),
    single-line install/uninstall commands (no trae-cn alt), and crucially NO
    PreToolUse caveat (amp's v8 never carried one).
    """
    core, refs = _platform_artifacts("amp")
    hooks = refs["hooks.md"]
    # amp's bare v8 heading and Amp-worded prose.
    assert "## For native AGENTS.md integration" in hooks
    assert "## For native AGENTS.md integration (Trae)" not in hooks
    assert "make graphify always-on in Amp sessions" in hooks
    assert "instructs Amp to check the graph" in hooks
    # amp's single-line install/uninstall, no trae-cn alt comments.
    assert "graphify amp install" in hooks
    assert "graphify amp uninstall  # remove the section" in hooks
    assert "graphify trae install" not in hooks
    assert "graphify trae-cn" not in hooks
    assert "or: graphify" not in hooks
    # No claude flavoring on amp.
    assert "graphify claude install" not in hooks
    assert "native CLAUDE.md integration" not in hooks
    # The lean-core pointer names AGENTS.md, not CLAUDE.md.
    assert "## For the commit hook and native AGENTS.md integration" in core
    assert "wire graphify into a project's AGENTS.md" in core
    assert "native CLAUDE.md integration" not in core


def test_amp_has_no_pretooluse_caveat_anywhere():
    """amp's v8 had no no-PreToolUse-hooks note, so neither its core nor hooks may.

    This is the explicit guard against injecting trae-specific wording into amp.
    The caveat belongs to trae alone; amp uses the plain task-tool-disk dispatch
    and a caveat-free AGENTS.md integration section.
    """
    core, refs = _platform_artifacts("amp")
    hooks = refs["hooks.md"]
    assert "PreToolUse" not in core, "amp leaked a PreToolUse caveat into its core"
    assert "PreToolUse" not in hooks, "amp leaked a PreToolUse caveat into its hooks reference"
    assert "Trae does NOT support" not in core
    assert "Trae does NOT support" not in hooks
    # amp's dispatch is the plain task-tool-disk block (no trae caveat line).
    b2 = core[core.index("**Step B2"):core.index("Pass the extraction prompt")]
    assert "Trae" not in b2


def test_amp_audit_coverage_passes_against_its_own_v8():
    """The per-host audit (the guard amp is the exact case for) passes for amp.

    amp was omitted from wave 3's render list, so its v8 body was never audited
    against a lean split. The audit reads origin/v8:graphify/skill-amp.md and
    confirms every heading single-homes in amp's core + references.
    """
    platforms = gen.load_platforms()
    assert gen._v8_baseline_ref("amp") == "47042beb05d1f6dd2186c0c499ae2840ce604ead:graphify/skill-amp.md"
    problems = gen.audit_coverage(platforms["amp"])
    assert problems == [], "\n".join(problems)


# --- the generic agents platform (#1432) ---------------------------------------


def test_agents_renders_its_own_agents_md_hooks_wording():
    """`agents` re-homes amp's agents-md body but with its OWN install wording.

    It shares amp's bare, caveat-free `## For native AGENTS.md integration`
    section (no `(Trae)` suffix, no PreToolUse note) but points at
    `graphify agents install` and is worded for an unspecified host.
    """
    core, refs = _platform_artifacts("agents")
    hooks = refs["hooks.md"]
    assert "## For native AGENTS.md integration" in hooks
    assert "## For native AGENTS.md integration (Trae)" not in hooks
    assert "make graphify always-on in your agent sessions" in hooks
    assert "graphify agents install" in hooks
    assert "graphify agents uninstall  # remove the section" in hooks
    # No amp/trae/claude wording leaks into the agents render.
    assert "graphify amp install" not in hooks
    assert "graphify trae" not in hooks
    assert "graphify claude install" not in hooks
    assert "PreToolUse" not in hooks and "PreToolUse" not in core
    # The lean-core pointer names AGENTS.md, not CLAUDE.md.
    assert "## For the commit hook and native AGENTS.md integration" in core
    assert "native CLAUDE.md integration" not in core


def test_agents_body_matches_amp_modulo_hooks_wording():
    """The agents skill body is amp's body verbatim (it re-homes amp's bundle).

    The two platforms differ only in the hooks reference's install/uninstall
    command wording — everything else (core, query, extraction spec, the other
    six references) is byte-identical, which is why agents audits cleanly against
    amp's v8 baseline.
    """
    platforms = gen.load_platforms()
    amp = {a.path.rsplit("/", 1)[-1]: a.content for a in gen.render(platforms["amp"])}
    agents = {a.path.rsplit("/", 1)[-1]: a.content for a in gen.render(platforms["agents"])}
    # The lean-core skill body is identical (frontmatter + steps, no hooks ref).
    assert amp["skill-amp.md"] == agents["skill-agents.md"]
    # Every reference except hooks.md is byte-identical.
    for name in amp:
        if name in ("skill-amp.md", "hooks.md"):
            continue
        assert amp[name] == agents[name], f"{name} drifted between amp and agents"
    assert amp["hooks.md"] != agents["hooks.md"]


def test_agents_audit_baseline_is_amps_v8_body():
    """`agents` is a post-v8 platform, so its audit baseline is amp's v8 body."""
    platforms = gen.load_platforms()
    assert gen._v8_baseline_ref("agents") == "47042beb05d1f6dd2186c0c499ae2840ce604ead:graphify/skill-amp.md"
    problems = gen.audit_coverage(platforms["agents"])
    assert problems == [], "\n".join(problems)
